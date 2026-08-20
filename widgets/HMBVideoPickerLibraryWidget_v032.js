// HMB VideoPicker dashboard cache version v032.
const COLOR_RGB = {
  Red: [255, 0, 0],
  Green: [0, 255, 0],
  Blue: [0, 0, 255],
  Yellow: [255, 230, 0],
  Orange: [255, 133, 46],
  Purple: [145, 71, 255],
  Pink: [232, 77, 145],
  "Sky Blue": [92, 184, 255],
  Mint: [102, 235, 186],
  Beige: [219, 199, 163],
};

const FALLBACK_MARKER_OPTIONS = [
  "Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink",
  "Sky Blue", "Mint", "Beige", "Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern",
];
const HMB_DEFAULT_NODE_WIDTH = 1400;
const HMB_DEFAULT_NODE_HEIGHT = 1200;
const HMB_MIN_NODE_WIDTH = 760;
const HMB_MIN_NODE_HEIGHT = 1151;
// ImageAsset parity: a disconnected Picker starts with Shot 01 only. Compact
// height follows the authoritative Shot count and whether each Shot owns media;
// it is never preallocated for five rows or fifty empty cards.
const HMB_VIDEO_PICKER_COMPACT_BOOTSTRAP_HEIGHT = 158;
// Editor 0.122 allocates a custom parameter row from its visibility:hidden
// measurement copy.  Keep that copy state-aware instead of forcing the live
// adaptive-row ancestors to a widget-owned height.
const HMB_VIDEO_PICKER_COMPACT_MEASUREMENT_BASE_HEIGHT = 72;
const HMB_VIDEO_PICKER_COMPACT_FIXED_SHOT_HEIGHT = 180;
const HMB_VIDEO_PICKER_COMPACT_EMPTY_SHOT_HEIGHT = 86;
const HMB_VIDEO_PICKER_COMPACT_SHOT_GAP = 6;
const HMB_VIDEO_PICKER_EXPANDED_MEASUREMENT_HEIGHT = HMB_MIN_NODE_HEIGHT;
const HMB_PICKER_CONTENT_FALLBACK_HEIGHT = 960;
const HMB_PICKER_VIEWPORT_STAGE_MIN_HEIGHT = 360;
const HMB_PICKER_OUTLINER_BODY_MIN_HEIGHT = 300;
const HMB_PICKER_OUTLINER_PANEL_MIN_HEIGHT = 480;
const HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT = 636;
const HMB_PLAYBLAST_RESOLUTIONS = [
  { value: "1280x720", width: 1280, height: 720, label: "1280 × 720" },
  { value: "1920x1080", width: 1920, height: 1080, label: "1920 × 1080" },
];
const HMB_RIGHT_SECTION_DEFAULT_HEIGHTS = { settings: 217, color: 628, log: 208 };
const HMB_ACTIVITY_LOG_MAX_ROWS = 80;
const HMB_ACTIVITY_LOG_MESSAGE_MAX_CHARS = 260;
const HMB_PICKER_MAX_SELECTED_VIDEOS = 10;
// Each ImageAsset-authored Shot owns an ordered, bounded video strip. Up to ten
// actual cards fit on a row; empty capacity is intentionally not rendered.
export const HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS = HMB_PICKER_MAX_SELECTED_VIDEOS;
export const HMB_PICKER_MAX_ASSETS_PER_SHOT = 10;
const HMB_PICKER_MAX_SNAPSHOTS = 10;
const HMB_SHOT_ROUTING_MAX_SHOTS = 5;
const HMB_PICKER_DEFAULT_WORKSPACE_UUID = "00000000-0000-4000-8000-000000000001";
// These identities mirror Python's UUID5("hmb-video-picker-workspace:N")
// values so a legacy browser migration and the authoritative backend echo use
// the same keyed rows without a remount or rename-input blink.
const HMB_PICKER_FIXED_WORKSPACE_UUIDS = Object.freeze([
  HMB_PICKER_DEFAULT_WORKSPACE_UUID,
  "a79ca5de-3d50-52c9-b3b7-fb88dea8fc49",
  "1a585168-2d9d-5aea-8023-bee2e9f65eac",
  "0baa7a58-f985-5157-adb9-61029a3ccdde",
  "d0d657d2-5a3d-530f-82f8-886067369fba",
]);
export const HMB_PICKER_MAX_TOTAL_ASSETS = HMB_SHOT_ROUTING_MAX_SHOTS * HMB_PICKER_MAX_ASSETS_PER_SHOT;
const HMB_SHOT_DISCOVER_EVENT = "hmb-shot-routing-discover-v1";
export const HMB_PICKER_VIDEO_PRELOAD_TIMEOUT_MS = 15000;
export const HMB_PICKER_OUTLINER_ROW_HEIGHT = 29;
export const HMB_PICKER_OUTLINER_WINDOW_ROWS = 180;
export const HMB_PICKER_OUTLINER_OVERSCAN_ROWS = 18;
export const HMB_PICKER_OUTLINER_SEARCH_RENDER_DELAY_MS = 140;
export const HMB_PICKER_COMMAND_ACK_TIMEOUT_MS = 20000;
export const HMB_PICKER_WORKSPACE_ECHO_TIMEOUT_MS = 1500;
export const HMB_PICKER_BROWSE_POLL_DELAYS_MS = Object.freeze([0, 120, 300, 700, 1500, 3000]);
export const HMB_PICKER_PAINT_FIRST_FALLBACK_MS = 120;
const HMB_PICKER_GUARDED_COMMAND_OPTIONS = Object.freeze({ ["reserveVisibility"]: true });
// View mode belongs to one loaded Picker runtime and never to React Flow DOM.
const hmbVideoPickerViewModeRegistry = new Map();
const hmbVideoPickerViewModeFallbackRegistry = new WeakMap();
let hmbVideoPickerPaintFirstSequence = 0;

// Jewel Night is the single Shot-routing palette shared by ImageAsset,
// Prompt, Agent, and VideoPicker. Shot 1 intentionally preserves the
// established generator-order pink.
export const HMB_PICKER_SHOT_COLOR_PALETTE = Object.freeze({
  1: Object.freeze({ accent: "#F472B6", rgb: [244, 114, 182], deep: "#BE185D", deepRgb: [190, 24, 93], secondary: "#D946EF", secondaryRgb: [217, 70, 239], text: "#F8C6DF", soft: "#F3A8CE", strong: "#FFE4F2" }),
  2: Object.freeze({ accent: "#3B82F6", rgb: [59, 130, 246], deep: "#1D4ED8", deepRgb: [29, 78, 216], secondary: "#60A5FA", secondaryRgb: [96, 165, 250], text: "#DBEAFE", soft: "#93C5FD", strong: "#EFF6FF" }),
  3: Object.freeze({ accent: "#10B981", rgb: [16, 185, 129], deep: "#047857", deepRgb: [4, 120, 87], secondary: "#34D399", secondaryRgb: [52, 211, 153], text: "#D1FAE5", soft: "#6EE7B7", strong: "#ECFDF5" }),
  4: Object.freeze({ accent: "#8B5CF6", rgb: [139, 92, 246], deep: "#6D28D9", deepRgb: [109, 40, 217], secondary: "#A78BFA", secondaryRgb: [167, 139, 250], text: "#EDE9FE", soft: "#C4B5FD", strong: "#F5F3FF" }),
  5: Object.freeze({ accent: "#EAB308", rgb: [234, 179, 8], deep: "#A16207", deepRgb: [161, 98, 7], secondary: "#FACC15", secondaryRgb: [250, 204, 21], text: "#FEF3C7", soft: "#FDE68A", strong: "#FFFBEB" }),
});

export function hmbPickerShotPalette(value) {
  const number = Number(value);
  const shotNumber = Number.isInteger(number) && number >= 1 && number <= HMB_SHOT_ROUTING_MAX_SHOTS
    ? number : 1;
  return { number: shotNumber, ...HMB_PICKER_SHOT_COLOR_PALETTE[shotNumber] };
}

export function hmbPickerShotCssVariables(value) {
  const palette = hmbPickerShotPalette(value);
  const rgb = palette.rgb.join(",");
  const deepRgb = palette.deepRgb.join(",");
  const secondaryRgb = palette.secondaryRgb.join(",");
  return {
    "--hmb-head-top": `rgba(${deepRgb},.58)`,
    "--hmb-head-mid": `rgba(${deepRgb},.27)`,
    "--hmb-hover": `rgba(${rgb},.09)`,
    "--hmb-selected": `linear-gradient(90deg,rgba(${deepRgb},.30),rgba(${secondaryRgb},.20))`,
    "--hmb-primary-top": palette.accent,
    "--hmb-primary-bottom": palette.deep,
    "--hmb-primary-line": palette.soft,
    "--hmb-secondary": palette.secondary,
    "--hmb-focus": palette.accent,
    "--hmb-accent": palette.accent,
    "--hmb-accent-2": palette.secondary,
    "--hmb-glow": `rgba(${rgb},.18)`,
    "--selection-rgb": rgb,
    "--selection-deep-rgb": deepRgb,
    "--selection-secondary-rgb": secondaryRgb,
    "--selection-text": palette.text,
    "--selection-soft": palette.soft,
    "--selection-strong": palette.strong,
    "--selection-card": `rgba(${deepRgb},.44)`,
  };
}

export function hmbPickerShotPaletteStyle(value) {
  return Object.entries(hmbPickerShotCssVariables(value))
    .map(([name, color]) => `${name}:${color}`)
    .join(";");
}

function hmbApplyPickerShotPalette(root, value) {
  if (!root?.style?.setProperty) return;
  const palette = hmbPickerShotPalette(value);
  root.setAttribute?.("data-shot-number", String(palette.number));
  Object.entries(hmbPickerShotCssVariables(palette.number)).forEach(([name, color]) => {
    root.style.setProperty(name, color);
  });
}

export function hmbScopeWidgetCss(cssText, rootSelector) {
  const css = String(cssText || "");
  const root = String(rootSelector || "").trim();
  if (!root) return css;
  const rootToken = new RegExp(`${root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\w-])`);
  const matchingBrace = (start) => {
    let depth = 0;
    let quote = "";
    let comment = false;
    for (let index = start; index < css.length; index += 1) {
      const char = css[index];
      const next = css[index + 1];
      if (comment) { if (char === "*" && next === "/") { comment = false; index += 1; } continue; }
      if (quote) { if (char === "\\") index += 1; else if (char === quote) quote = ""; continue; }
      if (char === "/" && next === "*") { comment = true; index += 1; continue; }
      if (char === "\"" || char === "'") { quote = char; continue; }
      if (char === "{") depth += 1;
      else if (char === "}" && --depth === 0) return index;
    }
    return css.length - 1;
  };
  const scopeRange = (start, end) => {
    let output = "";
    let cursor = start;
    while (cursor < end) {
      const open = css.indexOf("{", cursor);
      if (open < 0 || open >= end) { output += css.slice(cursor, end); break; }
      const close = matchingBrace(open);
      if (close >= end) { output += css.slice(cursor, end); break; }
      const header = css.slice(cursor, open);
      const trimmed = header.trim();
      if (trimmed.startsWith("@")) {
        const nested = /^@(media|container|supports|layer|document)\b/i.test(trimmed);
        output += `${header}{${nested ? scopeRange(open + 1, close) : css.slice(open + 1, close)}}`;
      } else {
        const leading = header.match(/^\s*/)?.[0] || "";
        const selectors = trimmed.split(",").map((selector) => {
          const cleanSelector = selector.trim();
          if (!cleanSelector) return cleanSelector;
          if (rootToken.test(cleanSelector)) return cleanSelector.replaceAll(":root", root);
          if (cleanSelector.includes(":root")) return cleanSelector.replaceAll(":root", root);
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

const HMB_SCOPED_STYLE_CACHE_LIMIT = 8;
const HMB_SCOPED_STYLE_CACHE = new Map();

export function hmbCachedScopeWidgetCss(cssText, rootSelector) {
  const css = String(cssText || "");
  const root = String(rootSelector || "").trim();
  const key = `${root}\u0000${css}`;
  if (HMB_SCOPED_STYLE_CACHE.has(key)) {
    const cached = HMB_SCOPED_STYLE_CACHE.get(key);
    HMB_SCOPED_STYLE_CACHE.delete(key);
    HMB_SCOPED_STYLE_CACHE.set(key, cached);
    return cached;
  }
  const scoped = hmbScopeWidgetCss(css, root);
  HMB_SCOPED_STYLE_CACHE.set(key, scoped);
  while (HMB_SCOPED_STYLE_CACHE.size > HMB_SCOPED_STYLE_CACHE_LIMIT) {
    HMB_SCOPED_STYLE_CACHE.delete(HMB_SCOPED_STYLE_CACHE.keys().next().value);
  }
  return scoped;
}

export function hmbScopeWidgetStyleMarkup(markup, rootSelector) {
  return String(markup || "").replace(/<style>([\s\S]*?)<\/style>/g, (_match, css) => (
    `<style>${hmbCachedScopeWidgetCss(css, rootSelector)}</style>`
  ));
}

function hmbNormalizeRightSectionHeights(value) {
  const source = value && typeof value === "object" ? value : {};
  return Object.fromEntries(Object.entries(HMB_RIGHT_SECTION_DEFAULT_HEIGHTS).map(([key, fallback]) => {
    const height = Number(source[key]);
    return [key, clamp(Number.isFinite(height) ? Math.round(height) : fallback, 96, 900)];
  }));
}

function hmbSectionHeightStyle(heights, key) {
  const value = Number(heights?.[key] || HMB_RIGHT_SECTION_DEFAULT_HEIGHTS[key] || 0);
  return value > 0 ? `height:${Math.round(value)}px` : "";
}

function hmbFlexPanelHeightStyle(value, minimum) {
  const height = Number(value || 0);
  return height >= minimum
    ? `height:${Math.round(height)}px;flex:0 0 ${Math.round(height)}px`
    : "";
}

const TEXT = {
  en: {
    load: "LOAD",
    browse: "BROWSE",
    scenePath: "Maya .mb/.ma absolute path",
    pickPreview: "PICK & SNAPSHOT",
    playblast: "PLAYBLAST",
    read: "READ",
    stop: "STOP",
    readRequestedMessage: "READ requested. Starting the background Maya scene read...",
    readPressedLog: "READ button pressed. Starting the background Maya scene read.",
    stopRequestedMessage: "STOP requested. Cancelling the active READ operation...",
    stopPressedLog: "STOP button pressed. Starting READ cancellation.",
    sceneSyncLog: "Python reader completed the Maya camera, frame, FPS, and Outliner scan without rendering video.",
    sceneDetectedLog: "Maya file detected in LOAD. Submitting the path through the widget parameter.",
    sceneScanning: "SCANNING SCENE",
    resyncRequired: "RESYNC REQUIRED",
    outliner: "OUTLINER",
    filteredPolygon: "Asset Roots Only",
    search: "Search asset roots...",
    name: "Name",
    viewport: "VIEWPORT",
    preview: "Video",
    camera: "Camera",
    cameraPrefix: "CAM",
    noCamera: "No camera found",
    noPreviewTitle: "No video loaded",
    noPreviewBody: "READ loads scene data first. Choose outputs, then press Generate Playblast.",
    previousSnapshot: "Previous snapshot",
    playVideo: "Play",
    pauseVideo: "Pause",
    nextSnapshot: "Next snapshot",
    snapshot: "Snapshot",
    deleteSnapshot: "Delete Snapshot",
    originalPreview: "Original Playblast",
    mask: "Mask",
    depth: "Depth",
    motionGuide: "Motion Guide",
    frameLabel: "Frame",
    presetActor: "Preset Actor",
    presetGhost: "Preset Ghost",
    presetGhostScope: "Available for Actor and Background",
    presetObject: "Preset Object",
    resolution: "Resolution",
    frameRange: "Frame Range",
    frameStep: "Frame Step",
    fps: "FPS",
    format: "Format",
    quality: "Quality",
    high: "High",
    generate: "Generate Playblast",
    language: "EN",
    reference: "REF",
    mesh: "MESH",
    outputOn: "Included in Playblast",
    outputOff: "Excluded from Playblast",
    expandNode: "Expand group",
    collapseNode: "Collapse group",
    selectCamera: "Select Camera",
    singleCamera: "Fixed camera",
    fixed: "FIXED",
    registered: "Registered",
    renderable: "Renderable",
    cameraLabel: "Camera",
    viewport2: "Viewport 2.0",
    burnIn: "Burn In",
    ready: "READY",
    sceneReady: "SCENE READY",
    metadataIncomplete: "METADATA INCOMPLETE",
    readingScene: "READING",
    running: "RUNNING",
    generatingVideo: "GENERATING",
    generatingOriginal: "ORIGINAL PREVIEW",
    outlinerReady: "OUTLINER READY",
    videoReady: "VIDEO READY",
    failed: "FAILED",
    activityLog: "ACTIVITY LOG",
    clearLog: "Clear",
    noActivity: "No activity yet.",
    elapsed: "Elapsed",
    cancelling: "CANCELLING",
    cancelled: "CANCELLED",
    mayaVersion: "Maya",
    autoDetect: "Auto detect highest",
    resizeSection: "Drag to resize this section",
    selectedVideos: "Selected",
    selectedVideoOrder: "SELECTED VIDEO / GENERATOR ORDER",
    selectVideoAsset: "Select",
    deselectVideoAsset: "Deselect",
    previewLarge: "Large Preview",
    deleteVideoAsset: "Delete from history",
    importVideoAsset: "Load",
    emptyVideoHistory: "Generate a playblast to add a video for this cut.",
    dragVideoOrder: "Drag selected cards to change @video order.",
    previewLoadFailed: "The selected video could not be loaded. The previous preview is still shown.",
    previewPlayFailed: "Video playback was blocked or failed. Retry playback after checking the codec and browser media permission.",
    retryPreview: "Retry",
  },
  ko: {
    originalPreview: "\uC6D0\uBCF8 \uD50C\uB808\uC774\uBE14\uB77C\uC2A4\uD2B8",
    generatingOriginal: "\uC6D0\uBCF8 \uD504\uB9AC\uBDF0",
    browse: "찾아보기",
    scenePath: "Maya .mb/.ma 절대 경로",
    load: "불러오기",
    pickPreview: "컬러 선택 및 스냅샷",
    playblast: "플레이블라스트",
    read: "읽기",
    stop: "정지",
    readRequestedMessage: "읽기 요청. 백그라운드 Maya 씬 읽기를 시작합니다...",
    readPressedLog: "읽기 버튼을 눌렀습니다. 백그라운드 Maya 씬 읽기를 시작합니다.",
    stopRequestedMessage: "정지 요청. 실행 중인 읽기 작업을 취소합니다...",
    stopPressedLog: "정지 버튼을 눌렀습니다. 읽기 취소 작업을 시작합니다.",
    sceneSyncLog: "Python 리더가 영상 렌더 없이 Maya 카메라, 프레임, FPS, 아웃라이너 메타데이터 읽기를 완료했습니다.",
    sceneDetectedLog: "불러오기에서 Maya 파일을 감지했습니다. 위젯 파라미터를 통해 경로를 제출합니다.",
    sceneScanning: "씬 검사 중",
    resyncRequired: "재동기화 필요",
    outliner: "아웃라이너",
    filteredPolygon: "에셋 루트만 표시",
    search: "에셋 루트 검색...",
    name: "이름",
    status: "상태",
    viewport: "뷰포트",
    preview: "비디오",
    camera: "카메라",
    cameraPrefix: "카메라",
    noCamera: "카메라 없음",
    noPreviewTitle: "불러온 비디오 없음",
    noPreviewBody: "READ는 씬 메타데이터만 불러옵니다. 뷰포트 영상이 필요할 때만 원본 플레이블라스트를 켜세요.",
    previousSnapshot: "이전 스냅샷",
    playVideo: "재생",
    pauseVideo: "멈춤",
    nextSnapshot: "다음 스냅샷",
    snapshot: "스냅샷",
    deleteSnapshot: "스냅샷 삭제",
    frameLabel: "프레임",
    colorAssignment: "컬러 지정",
    presetActor: "프리셋 액터",
    presetGhost: "프리셋 고스트",
    presetGhostScope: "캐릭터와 배경에 공통 적용",
    presetObject: "프리셋 오브젝트",
    target: "대상",
    color: "컬러",
    resolution: "해상도",
    frameRange: "프레임 범위",
    frameStep: "프레임 간격",
    fps: "FPS",
    format: "형식",
    quality: "품질",
    high: "높음",
    generate: "플레이블라스트 생성",
    addVideo: "비디오 슬롯 추가",
    deleteVideo: "비디오 슬롯 삭제",
    clearVideo: "현재 비디오 슬롯 지우기",
    moveVideoUp: "현재 비디오를 위로 이동",
    moveVideoDown: "현재 비디오를 아래로 이동",
    language: "한국어",
    assigned: "지정",
    visible: "표시",
    hidden: "숨김",
    animVis: "가시성 애니메이션",
    drivenVis: "연결 가시성",
    parentHidden: "부모 숨김",
    layerHidden: "레이어 숨김",
    overrideHidden: "오버라이드 숨김",
    reference: "레퍼런스",
    mesh: "메시",
    outputOn: "플레이블라스트 포함",
    outputOff: "플레이블라스트 제외",
    expandNode: "그룹 펼치기",
    collapseNode: "그룹 접기",
    unassignedBlack: "컬러가 지정되지 않은 오브젝트와 눈 아이콘으로 제외한 항목은 플레이블라스트 출력에서 제외됩니다.",
    selectCamera: "카메라 선택",
    singleCamera: "고정 카메라",
    currentVideo: "현재 비디오",
    fixed: "고정",
    registered: "등록됨",
    renderable: "렌더 가능",
    cameraLabel: "카메라",
    viewport2: "뷰포트 2.0",
    burnIn: "프레임 정보 표시",
    ready: "준비",
    sceneReady: "씬 준비",
    metadataIncomplete: "메타데이터 미완료",
    readingScene: "읽는 중",
    running: "실행 중",
    generatingVideo: "생성 중",
    outlinerReady: "아웃라이너 준비",
    videoReady: "비디오 준비",
    failed: "실패",
    activityLog: "작업 로그",
    clearLog: "지우기",
    noActivity: "아직 작업 기록이 없습니다.",
    elapsed: "경과",
    cancelling: "취소 중",
    cancelled: "취소됨",
    mayaVersion: "Maya",
    autoDetect: "최고 버전 자동 검출",
    resizeSection: "드래그하여 이 영역 크기 변경",
    selectedVideos: "선택",
    selectedVideoOrder: "선택 비디오 / 생성기 순서",
    selectVideoAsset: "선택",
    deselectVideoAsset: "선택 해제",
    previewLarge: "크게 보기",
    deleteVideoAsset: "히스토리에서 삭제",
    importVideoAsset: "검색",
    emptyVideoHistory: "플레이블라스트를 생성하면 현재 컷 영상이 추가됩니다.",
    dragVideoOrder: "선택된 카드를 드래그하여 @video 순서를 변경합니다.",
  },
};

TEXT.ko.originalPreview = "\uC6D0\uBCF8 \uD50C\uB808\uC774\uBE14\uB77C\uC2A4\uD2B8";
TEXT.ko.generatingOriginal = "\uC6D0\uBCF8 \uD504\uB9AC\uBDF0";
TEXT.ko.noPreviewBody = "READ \uD6C4 \uCD9C\uB825\uC744 \uC120\uD0DD\uD558\uACE0 Generate Playblast\uB97C \uB204\uB974\uC138\uC694.";
TEXT.ko.mask = "\uB9C8\uC2A4\uD06C";
TEXT.ko.depth = "Depth";
TEXT.ko.motionGuide = "\uBAA8\uC158 \uAC00\uC774\uB4DC";
TEXT.ko.importVideoAsset = "\uAC80\uC0C9";
TEXT.ko.previewLoadFailed = "\uC120\uD0DD\uD55C \uBE44\uB514\uC624\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD574 \uC774\uC804 \uD504\uB9AC\uBDF0\uB97C \uC720\uC9C0\uD569\uB2C8\uB2E4.";
TEXT.ko.previewPlayFailed = "\uBE44\uB514\uC624 \uC7AC\uC0DD\uC774 \uCC28\uB2E8\uB418\uC5C8\uAC70\uB098 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4. \uCF54\uB371\uACFC \uBE0C\uB77C\uC6B0\uC800 \uBBF8\uB514\uC5B4 \uAD8C\uD55C\uC744 \uD655\uC778\uD55C \uB4A4 \uB2E4\uC2DC \uC7AC\uC0DD\uD558\uC138\uC694.";
TEXT.ko.retryPreview = "\uB2E4\uC2DC \uC2DC\uB3C4";

function clean(value) {
  return String(value == null ? "" : value).trim();
}

export function hmbPickerCommandPayload(stateValue, payload = {}) {
  const cloned = payload && typeof payload === "object" ? JSON.parse(JSON.stringify(payload)) : {};
  // A LOAD command captures its target Shot at click time.  Do not replace an
  // explicit valid target with a later active-page echo while a native file
  // browser is opening.
  cloned.picker_shot_uuid = hmbUuid(cloned.picker_shot_uuid)
    || hmbUuid(stateValue?.active_picker_shot_uuid);
  return cloned;
}

function hmbUuid(value) {
  const text = clean(value).toLowerCase();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(text)
    ? text
    : "";
}

export function hmbNewPickerShotUuid() {
  try {
    const uuid = hmbUuid(globalThis?.crypto?.randomUUID?.());
    if (uuid) return uuid;
  } catch (_error) {}
  const bytes = Array.from({ length: 16 }, () => Math.floor(Math.random() * 256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.map((value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function hmbFixedPickerShotUuid(number) {
  const index = Math.max(0, Math.min(
    HMB_PICKER_FIXED_WORKSPACE_UUIDS.length - 1,
    Math.floor(Number(number || 1)) - 1,
  ));
  return HMB_PICKER_FIXED_WORKSPACE_UUIDS[index] || HMB_PICKER_DEFAULT_WORKSPACE_UUID;
}

export function hmbPickerWorkspaceAssetUids(row) {
  const seen = new Set();
  const assets = [];
  for (const rawUid of (Array.isArray(row?.video_asset_uids) ? row.video_asset_uids : [])) {
    const uid = clean(rawUid);
    if (!uid || seen.has(uid)) continue;
    seen.add(uid);
    assets.push(uid);
    if (assets.length >= HMB_PICKER_MAX_ASSETS_PER_SHOT) break;
  }
  return assets;
}

export function hmbValidateShotRoutingUiCatalog(value) {
  const required = [
    "schema", "version", "publisher_kind", "publisher_instance_uuid",
    "channel_uuid", "generation", "shots",
  ].sort().join("\u0000");
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (Object.keys(value).sort().join("\u0000") !== required) return null;
  if (value.schema !== "hmb-shot-routing-ui-catalog" || value.version !== 1 || value.publisher_kind !== "image_asset") return null;
  const publisherInstanceUuid = hmbUuid(value.publisher_instance_uuid);
  const channelUuid = hmbUuid(value.channel_uuid);
  const generation = Number(value.generation);
  if (!publisherInstanceUuid || !channelUuid || !Number.isInteger(generation) || generation <= 0) return null;
  if (!Array.isArray(value.shots) || value.shots.length < 1 || value.shots.length > HMB_SHOT_ROUTING_MAX_SHOTS) return null;
  const seenIds = new Set();
  const seenNumbers = new Set();
  const shots = [];
  for (const raw of value.shots) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    if (Object.keys(raw).sort().join("\u0000") !== ["name", "number", "revision", "shot_uuid"].sort().join("\u0000")) return null;
    const shotUuid = hmbUuid(raw.shot_uuid);
    const number = raw.number;
    const revision = raw.revision;
    const name = clean(raw.name);
    if (
      !shotUuid || seenIds.has(shotUuid) || !name
      || typeof raw.name !== "string" || raw.name !== name || name.length > 128
      || !Number.isInteger(number) || number < 1 || number > HMB_SHOT_ROUTING_MAX_SHOTS || seenNumbers.has(number)
      || !Number.isInteger(revision) || revision < 0
    ) return null;
    seenIds.add(shotUuid);
    seenNumbers.add(number);
    shots.push({ shot_uuid: shotUuid, number, name, revision });
  }
  shots.sort((left, right) => left.number - right.number);
  return {
    schema: "hmb-shot-routing-ui-catalog",
    version: 1,
    publisher_kind: "image_asset",
    publisher_instance_uuid: publisherInstanceUuid,
    channel_uuid: channelUuid,
    generation,
    shots,
  };
}

export function hmbPickerShotCatalogMatchesAcceptedChannel(state, catalogValue) {
  const catalog = hmbValidateShotRoutingUiCatalog(catalogValue);
  const acceptedPublisher = hmbUuid(state?.shot_publisher_instance_uuid);
  const acceptedChannel = hmbUuid(state?.channel_uuid);
  return !!catalog
    && !!acceptedPublisher
    && !!acceptedChannel
    && catalog.publisher_instance_uuid === acceptedPublisher
    && catalog.channel_uuid === acceptedChannel;
}

function hmbNormalizePickerShotRows(state) {
  state.shot_publisher_instance_uuid = hmbUuid(state.shot_publisher_instance_uuid);
  state.channel_uuid = hmbUuid(state.channel_uuid);
  state.shot_uuid = hmbUuid(state.shot_uuid);
  state.shot_number = Number.isInteger(Number(state.shot_number))
    && Number(state.shot_number) >= 1 && Number(state.shot_number) <= HMB_SHOT_ROUTING_MAX_SHOTS
    ? Number(state.shot_number)
    : 0;
  state.shot_name = clean(state.shot_name).slice(0, 128);
  const knownVideoUids = new Set(
    (Array.isArray(state.videos) ? state.videos : []).map((item) => clean(item?.video_uid || item?.source_uid)).filter(Boolean),
  );
  const seen = new Set();
  const rows = [];
  for (const raw of (Array.isArray(state.shot_selections) ? state.shot_selections : []).slice(0, HMB_SHOT_ROUTING_MAX_SHOTS)) {
    const shotUuid = hmbUuid(raw?.shot_uuid);
    if (!shotUuid || seen.has(shotUuid)) continue;
    seen.add(shotUuid);
    const numberValue = Number(raw?.number);
    const number = Number.isInteger(numberValue) && numberValue >= 1 && numberValue <= HMB_SHOT_ROUTING_MAX_SHOTS
      ? numberValue
      : rows.length + 1;
    const selectedVideoUids = [];
    for (const rawUid of (Array.isArray(raw?.selected_video_uids) ? raw.selected_video_uids : [])) {
      const uid = clean(rawUid);
      if (uid && knownVideoUids.has(uid) && !selectedVideoUids.includes(uid)) selectedVideoUids.push(uid);
      if (selectedVideoUids.length >= HMB_PICKER_MAX_SELECTED_VIDEOS) break;
    }
    rows.push({
      shot_uuid: shotUuid,
      number,
      name: clean(raw?.name).slice(0, 128) || `Shot ${number}`,
      revision: Math.max(0, Math.floor(Number(raw?.revision || 0))),
      selected_video_uids: selectedVideoUids,
    });
  }
  if (state.shot_uuid && !seen.has(state.shot_uuid) && rows.length < HMB_SHOT_ROUTING_MAX_SHOTS) {
    rows.push({
      shot_uuid: state.shot_uuid,
      number: state.shot_number || rows.length + 1,
      name: state.shot_name || `Shot ${state.shot_number || rows.length + 1}`,
      revision: 0,
      selected_video_uids: [],
    });
  }
  const active = rows.find((row) => row.shot_uuid === state.shot_uuid);
  if (active) {
    state.shot_number = active.number;
    state.shot_name = active.name;
  }
  state.shot_selections = rows;
  return state;
}

function hmbPickerWorkspaceProjection(state) {
  const selected = hmbSelectedVideoAssets(state)
    .map((item) => clean(item.video_uid || item.source_uid))
    .filter(Boolean)
    .slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
  const activeWorkspace = hmbActivePickerWorkspace(state);
  const assets = hmbPickerWorkspaceAssetUids(activeWorkspace);
  const requestedPreview = clean(state?.preview_video_uid || state?.selected_video_uid);
  const previewUid = (assets.length ? assets : selected).includes(requestedPreview)
    ? requestedPreview
    : (selected[0] || assets[0] || "");
  return {
    selected_video_uids: selected,
    preview_video_uid: previewUid,
    scene_draft_path: clean(state?.scene_draft_path),
    current_frame: Number.isFinite(Number(state?.current_frame)) ? Number(state.current_frame) : 0,
    viewport_mode: clean(state?.viewport_mode).toLowerCase() === "snapshot" ? "snapshot" : "video",
    active_snapshot_uid: clean(state?.active_snapshot_uid),
    selected_video_slot: Math.max(1, Math.floor(Number(state?.selected_video_slot || 1))),
  };
}

function hmbPickerAuthoritativeRemoteRows(state) {
  if (!hmbUuid(state?.shot_publisher_instance_uuid) || !hmbUuid(state?.channel_uuid)) return [];
  const seenUuids = new Set();
  const seenNumbers = new Set();
  const rows = [];
  for (const raw of (Array.isArray(state?.shot_selections) ? state.shot_selections : [])) {
    const shotUuid = hmbUuid(raw?.shot_uuid);
    const number = Math.floor(Number(raw?.number || 0));
    if (
      !shotUuid || seenUuids.has(shotUuid) || seenNumbers.has(number)
      || number < 1 || number > HMB_SHOT_ROUTING_MAX_SHOTS
    ) continue;
    seenUuids.add(shotUuid);
    seenNumbers.add(number);
    rows.push({
      shot_uuid: shotUuid,
      number,
      name: clean(raw?.name).slice(0, 128) || `Shot ${number}`,
      revision: Math.max(0, Math.floor(Number(raw?.revision || 0))),
    });
  }
  return rows.sort((left, right) => left.number - right.number).slice(0, HMB_SHOT_ROUTING_MAX_SHOTS);
}

function hmbPickerWorkspaceRowsForMigration(state) {
  const remoteRows = hmbPickerAuthoritativeRemoteRows(state);
  const descriptors = remoteRows.length
    ? remoteRows
    : [{ shot_uuid: "", number: 1, name: "Shot 1", revision: 0 }];
  const legacyLocalRow = Array.isArray(state?.picker_shots) && state.picker_shots.length === 1
    ? state.picker_shots[0]
    : null;
  const projection = hmbPickerWorkspaceProjection(state);
  const catalogUids = (Array.isArray(state?.videos) ? state.videos : [])
    .map((item, index) => hmbVideoAssetUid(item, index))
    .filter(Boolean)
    .slice(0, HMB_PICKER_MAX_ASSETS_PER_SHOT);
  return descriptors.map((remote, index) => {
    const number = index + 1;
    const first = index === 0;
    const videoAssetUids = first ? catalogUids : [];
    const selectedVideoUids = first
      ? projection.selected_video_uids.filter((uid) => videoAssetUids.includes(uid))
      : [];
    return {
      workspace_uuid: first
        ? (hmbUuid(legacyLocalRow?.workspace_uuid) || hmbFixedPickerShotUuid(number))
        : hmbFixedPickerShotUuid(number),
      number,
      name: first && legacyLocalRow?.custom_name === true
        ? clean(legacyLocalRow?.name)
        : (clean(remote?.name) || `Shot ${number}`),
      custom_name: first && legacyLocalRow?.custom_name === true,
      revision: first ? Math.max(0, Math.floor(Number(legacyLocalRow?.revision || 0))) : 0,
      bound_shot_uuid: hmbUuid(remote?.shot_uuid),
      video_asset_uids: videoAssetUids,
      selected_video_uids: selectedVideoUids,
      preview_video_uid: selectedVideoUids.includes(projection.preview_video_uid)
        ? projection.preview_video_uid
        : (videoAssetUids[0] || ""),
    };
  });
}

export function hmbNormalizePickerWorkspaceRows(state) {
  const catalogRecords = (Array.isArray(state?.videos) ? state.videos : [])
    .map((item, index) => ({ item, uid: hmbVideoAssetUid(item, index) }))
    .filter((record) => !!record.uid);
  const knownVideoUids = new Set(catalogRecords.map((record) => record.uid));
  const remoteRows = hmbPickerAuthoritativeRemoteRows(state);
  const remoteByUuid = new Map(remoteRows.map((row) => [row.shot_uuid, row]));
  const descriptors = remoteRows.length
    ? remoteRows
    : [{ shot_uuid: "", number: 1, name: "Shot 1", revision: 0 }];
  const sourceRows = (Array.isArray(state?.picker_shots) ? state.picker_shots : [])
    .filter((row) => row && typeof row === "object")
    .slice(0, HMB_SHOT_ROUTING_MAX_SHOTS);
  const rawRows = sourceRows.length ? sourceRows : hmbPickerWorkspaceRowsForMigration(state);
  const existingMultipageState = sourceRows.length > 1;
  const rawByBoundUuid = new Map();
  const rawByNumber = new Map();
  for (const raw of rawRows) {
    const boundUuid = hmbUuid(raw?.bound_shot_uuid);
    const number = Math.max(1, Math.floor(Number(raw?.number || 1)));
    if (boundUuid && !rawByBoundUuid.has(boundUuid)) rawByBoundUuid.set(boundUuid, raw);
    if (!rawByNumber.has(number)) rawByNumber.set(number, raw);
  }

  const hasDurableBindings = rawByBoundUuid.size > 0;
  const usedRawRows = new Set();
  const seenWorkspaceUuids = new Set();
  const claimedVideoUids = new Set();
  const rows = [];
  for (const descriptor of descriptors) {
    const desiredBoundUuid = hmbUuid(descriptor?.shot_uuid);
    const number = rows.length + 1;
    let raw = desiredBoundUuid ? rawByBoundUuid.get(desiredBoundUuid) : null;
    if (!raw && (!hasDurableBindings || sourceRows.length <= 1)) raw = rawByNumber.get(number) || null;
    if (!raw && !desiredBoundUuid) raw = rawRows.find((candidate) => !usedRawRows.has(candidate)) || null;
    if (raw) usedRawRows.add(raw);

    let workspaceUuid = hmbUuid(raw?.workspace_uuid) || hmbFixedPickerShotUuid(number);
    if (seenWorkspaceUuids.has(workspaceUuid)) workspaceUuid = hmbNewPickerShotUuid();
    seenWorkspaceUuids.add(workspaceUuid);
    const rawNumber = Math.max(1, Math.floor(Number(raw?.number || number)));
    const rawName = clean(raw?.name).slice(0, 128);
    const customName = raw?.custom_name === true
      || (raw?.custom_name == null && !!rawName && rawName !== `Shot ${rawNumber}`);
    const rawAssetUids = Array.isArray(raw?.video_asset_uids)
      ? raw.video_asset_uids
      : (Array.isArray(raw?.video_uids)
        ? raw.video_uids
        : (Array.isArray(raw?.selected_video_uids) ? raw.selected_video_uids : []));
    const videoAssetUids = [];
    for (const rawUid of rawAssetUids) {
      const uid = clean(rawUid);
      if (!uid || !knownVideoUids.has(uid) || claimedVideoUids.has(uid)) continue;
      claimedVideoUids.add(uid);
      videoAssetUids.push(uid);
      if (videoAssetUids.length >= HMB_PICKER_MAX_ASSETS_PER_SHOT) break;
    }
    const selectedVideoUids = [];
    for (const rawUid of (Array.isArray(raw?.selected_video_uids) ? raw.selected_video_uids : [])) {
      const uid = clean(rawUid);
      if (uid && videoAssetUids.includes(uid) && !selectedVideoUids.includes(uid)) selectedVideoUids.push(uid);
      if (selectedVideoUids.length >= HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS) break;
    }
    let previewVideoUid = clean(raw?.preview_video_uid);
    if (!videoAssetUids.includes(previewVideoUid)) previewVideoUid = selectedVideoUids[0] || videoAssetUids[0] || "";
    rows.push({
      workspace_uuid: workspaceUuid,
      number,
      name: customName
        ? (rawName || `Shot ${number}`)
        : (clean(descriptor?.name).slice(0, 128) || `Shot ${number}`),
      custom_name: customName,
      revision: Math.max(0, Math.floor(Number(raw?.revision || 0))),
      bound_shot_uuid: desiredBoundUuid,
      video_asset_uids: videoAssetUids,
      selected_video_uids: selectedVideoUids,
      preview_video_uid: previewVideoUid,
      scene_draft_path: clean(raw?.scene_draft_path),
      current_frame: Number.isFinite(Number(raw?.current_frame)) ? Number(raw.current_frame) : 0,
      viewport_mode: clean(raw?.viewport_mode).toLowerCase() === "snapshot" ? "snapshot" : "video",
      active_snapshot_uid: clean(raw?.active_snapshot_uid),
      selected_video_slot: Math.max(1, Math.floor(Number(raw?.selected_video_slot || 1))),
    });
  }

  const requestedActiveUuid = hmbUuid(state?.active_picker_shot_uuid);
  let active = rows.find((row) => row.workspace_uuid === requestedActiveUuid) || null;
  if (!active) {
    const requestedBoundUuid = hmbUuid(state?.shot_uuid);
    active = rows.find((row) => row.bound_shot_uuid === requestedBoundUuid && !!requestedBoundUuid) || rows[0];
  }

  if (sourceRows.length <= 1) {
    // A legacy or independent Picker represented one page. Keep that catalog
    // on Shot 01; newly discovered ImageAsset Shots start empty.
    for (const record of catalogRecords) {
      if (claimedVideoUids.has(record.uid) || rows[0].video_asset_uids.length >= HMB_PICKER_MAX_ASSETS_PER_SHOT) continue;
      rows[0].video_asset_uids.push(record.uid);
      claimedVideoUids.add(record.uid);
    }
  } else {
    // Per-record owner tags recover missing membership only for retained
    // workspaces. A tag for a deleted ImageAsset Shot is intentionally not
    // reassigned by position.
    for (const record of catalogRecords) {
      if (claimedVideoUids.has(record.uid)) continue;
      const hintedWorkspaceUuid = hmbUuid(record.item?.picker_shot_uuid);
      const hintedRow = rows.find((row) => row.workspace_uuid === hintedWorkspaceUuid);
      if (!hintedRow || hintedRow.video_asset_uids.length >= HMB_PICKER_MAX_ASSETS_PER_SHOT) continue;
      hintedRow.video_asset_uids.push(record.uid);
      claimedVideoUids.add(record.uid);
    }
    const orphanTargets = [active, ...rows.filter((row) => row !== active)].filter(Boolean);
    for (const record of catalogRecords) {
      if (claimedVideoUids.has(record.uid) || hmbUuid(record.item?.picker_shot_uuid)) continue;
      const target = orphanTargets.find((row) => row.video_asset_uids.length < HMB_PICKER_MAX_ASSETS_PER_SHOT);
      if (!target) break;
      target.video_asset_uids.push(record.uid);
      claimedVideoUids.add(record.uid);
    }
  }

  if (requestedActiveUuid && active.workspace_uuid === requestedActiveUuid) {
    const projection = hmbPickerWorkspaceProjection(state);
    const assetSet = new Set(active.video_asset_uids);
    projection.selected_video_uids = projection.selected_video_uids
      .filter((uid) => assetSet.has(uid))
      .slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
    if (!assetSet.has(projection.preview_video_uid)) {
      projection.preview_video_uid = projection.selected_video_uids[0] || active.preview_video_uid || active.video_asset_uids[0] || "";
    }
    const workspaceChanged = [
      JSON.stringify(active.selected_video_uids) !== JSON.stringify(projection.selected_video_uids),
      active.preview_video_uid !== projection.preview_video_uid,
      active.scene_draft_path !== projection.scene_draft_path,
      Number(active.current_frame) !== Number(projection.current_frame),
      active.viewport_mode !== projection.viewport_mode,
      active.active_snapshot_uid !== projection.active_snapshot_uid,
      Number(active.selected_video_slot) !== Number(projection.selected_video_slot),
    ].some(Boolean);
    Object.assign(active, projection);
    if (workspaceChanged) active.revision += 1;
  }

  const ownedVideoUids = new Set(rows.flatMap((row) => row.video_asset_uids));
  const ownerByVideoUid = new Map(rows.flatMap((row) => (
    row.video_asset_uids.map((uid) => [uid, row.workspace_uuid])
  )));
  state.videos = catalogRecords
    .filter((record) => ownedVideoUids.has(record.uid))
    .map((record) => ({ ...record.item, picker_shot_uuid: ownerByVideoUid.get(record.uid) || "" }));

  const remote = remoteByUuid.get(active.bound_shot_uuid) || null;
  if (remote) {
    state.shot_uuid = remote.shot_uuid;
    state.shot_number = remote.number;
    state.shot_name = remote.name;
  } else {
    active.bound_shot_uuid = "";
    state.shot_uuid = "";
    state.shot_number = 0;
    state.shot_name = "";
  }
  state.picker_shots = rows;
  state.active_picker_shot_uuid = active.workspace_uuid;
  const representativeProjection = hmbApplyVideoAssetSelection(
    state,
    active.selected_video_uids,
    active.preview_video_uid,
  );
  state.picker_shots = representativeProjection.picker_shots;
  state.videos = representativeProjection.videos;
  state.preview_video_uid = active.preview_video_uid || "";
  state.selected_video_uid = active.preview_video_uid || "";
  state.selected_video_path = active.preview_video_uid
    ? hmbVideoAssetPath(state.videos.find((item) => clean(item.video_uid) === active.preview_video_uid))
    : "";
  state.selected_video_slot = Math.max(1, active.selected_video_uids.indexOf(active.preview_video_uid) + 1);
  return state;
}

export function hmbActivePickerWorkspace(state) {
  const rows = Array.isArray(state?.picker_shots) ? state.picker_shots : [];
  return rows.find((row) => hmbUuid(row?.workspace_uuid) === hmbUuid(state?.active_picker_shot_uuid)) || rows[0] || null;
}

function hmbProjectPickerWorkspace(state, workspace) {
  if (!workspace) return state;
  const projected = hmbApplyVideoAssetSelection(
    state,
    workspace.selected_video_uids,
    workspace.preview_video_uid,
  );
  Object.assign(projected, {
    scene_draft_path: clean(workspace.scene_draft_path),
    current_frame: Number(workspace.current_frame || 0),
    viewport_mode: clean(workspace.viewport_mode) === "snapshot" ? "snapshot" : "video",
    active_snapshot_uid: clean(workspace.active_snapshot_uid),
    selected_video_slot: Math.max(1, Math.floor(Number(workspace.selected_video_slot || 1))),
  });
  const remote = (Array.isArray(projected.shot_selections) ? projected.shot_selections : [])
    .find((row) => hmbUuid(row?.shot_uuid) === hmbUuid(workspace.bound_shot_uuid));
  if (remote && projected.shot_publisher_instance_uuid && projected.channel_uuid) {
    projected.shot_uuid = remote.shot_uuid;
    projected.shot_number = remote.number;
    projected.shot_name = remote.name;
  } else {
    workspace.bound_shot_uuid = "";
    projected.shot_uuid = "";
    projected.shot_number = 0;
    projected.shot_name = "";
  }
  return projected;
}

export function hmbSwitchLocalPickerShot(stateValue, requestedWorkspaceUuid) {
  const state = normalize(stateValue);
  const requested = hmbUuid(requestedWorkspaceUuid);
  const target = state.picker_shots.find((row) => row.workspace_uuid === requested);
  if (!target || requested === state.active_picker_shot_uuid) return state;
  state.active_picker_shot_uuid = requested;
  return normalize(hmbProjectPickerWorkspace(state, target));
}

export function hmbAddLocalPickerShot(stateValue) {
  // ImageAsset owns Shot creation. Keep this compatibility entry point inert
  // for older hosts that retained a local +Shot button.
  return normalize(stateValue);
}

export function hmbRenameLocalPickerShot(stateValue, workspaceUuid, requestedName) {
  const state = normalize(stateValue);
  const target = state.picker_shots.find((row) => row.workspace_uuid === hmbUuid(workspaceUuid));
  const name = clean(requestedName).slice(0, 128);
  if (!target || !name || target.name === name) return state;
  target.name = name;
  target.custom_name = true;
  target.revision += 1;
  return normalize(state);
}

export function hmbDeleteLocalPickerShot(stateValue, workspaceUuid) {
  void workspaceUuid;
  // ImageAsset owns Shot deletion. The next authoritative catalog echo removes
  // the matching UUID-bound Picker row; there is no local delete control.
  return normalize(stateValue);
}

export function hmbBindActivePickerShot(stateValue, requestedShotUuid = "") {
  void requestedShotUuid;
  // ImageAsset publishes the complete ordered Shot catalog. Manual binding
  // would let a hidden legacy selector detach a page from that authority, so
  // retain this compatibility entry point as an exact no-op.
  return normalize(stateValue);
}

export function hmbApplyPickerShotCatalog(stateValue, catalogValue, requestedShotUuid = "") {
  const catalog = hmbValidateShotRoutingUiCatalog(catalogValue);
  const state = normalize(stateValue);
  if (!catalog) return state;
  if (
    state.shot_publisher_instance_uuid
    && state.shot_publisher_instance_uuid !== catalog.publisher_instance_uuid
  ) return state;
  if (state.channel_uuid && state.channel_uuid !== catalog.channel_uuid) return state;
  const requested = hmbUuid(requestedShotUuid || state.shot_uuid);
  const target = requested
    ? catalog.shots.find((item) => item.shot_uuid === requested) || null
    : null;
  const existingRows = new Map(
    (Array.isArray(state.shot_selections) ? state.shot_selections : []).map((row) => [hmbUuid(row?.shot_uuid), row]),
  );
  const rows = catalog.shots.map((shot) => {
    const existing = existingRows.get(shot.shot_uuid);
    return {
      shot_uuid: shot.shot_uuid,
      number: shot.number,
      name: shot.name,
      revision: Math.max(0, Math.floor(Number(existing?.revision || 0))),
      selected_video_uids: existing
        ? [...(Array.isArray(existing.selected_video_uids) ? existing.selected_video_uids : [])]
        : [],
    };
  });
  const targetRow = target ? rows.find((row) => row.shot_uuid === target.shot_uuid) || null : null;
  const next = normalize({
    ...state,
    shot_publisher_instance_uuid: catalog.publisher_instance_uuid,
    channel_uuid: catalog.channel_uuid,
    shot_uuid: targetRow?.shot_uuid || "",
    shot_number: targetRow?.number || 0,
    shot_name: targetRow?.name || "",
    shot_selections: rows,
  });
  return targetRow ? hmbBindActivePickerShot(next, targetRow.shot_uuid) : next;
}

export function hmbSwitchPickerShot(stateValue, requestedShotUuid = "") {
  return hmbBindActivePickerShot(stateValue, requestedShotUuid);
}

function videoSourceUrl(value) {
  const text = clean(value);
  if (!text) return "";
  if (/^(blob:|data:|https?:|file:)/i.test(text)) return text;
  const normalized = text.replace(/\\/g, "/");
  if (/^[A-Za-z]:\//.test(normalized)) return encodeURI(`file:///${normalized}`);
  if (normalized.startsWith("//")) return encodeURI(`file:${normalized}`);
  return encodeURI(normalized);
}

export function hmbNormalizeMayaScenePath(value) {
  let text = clean(value);
  if (!text || text.length > 32767 || /[\u0000\r\n]/.test(text)) return "";
  if (
    text.length >= 2
    && ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'")))
  ) {
    text = clean(text.slice(1, -1));
  }
  if (!text || /[\u0000\r\n<>"|?*]/.test(text) || /[\\/]fakepath[\\/]/i.test(text)) return "";
  if (/^file:\/\//i.test(text)) {
    text = text.replace(/^file:\/\//i, "");
    if (/^\/[A-Za-z]:\//.test(text)) text = text.slice(1);
    else if (!text.startsWith("/")) text = `//${text}`;
    try { text = decodeURIComponent(text); } catch (_error) { return ""; }
  }
  if (!text || /[\u0000\r\n<>"|?*]/.test(text)) return "";
  const absoluteWindows = /^[A-Za-z]:[\\/]/.test(text);
  const absoluteUnc = /^(?:\\\\|\/\/)[^\\/\s]+[\\/][^\\/]+/.test(text);
  const absolutePosix = /^\/(?!\/)/.test(text);
  if (!absoluteWindows && !absoluteUnc && !absolutePosix) return "";
  const pathTail = absoluteWindows
    ? text.slice(3)
    : absoluteUnc
      ? text.replace(/^(?:\\\\|\/\/)[^\\/]+[\\/][^\\/]+[\\/]?/, "")
      : text.slice(1);
  if (absoluteWindows && text.slice(2).includes(":")) return "";
  if (absoluteUnc && text.includes(":")) return "";
  if (/(?:^|[\t ])(?:[A-Za-z]:[\\/]|\\\\|\/\/|\/)/.test(pathTail)) return "";
  if (/(?:^|[\s\]])(?:SUCCESS|ERROR|WARNING|INFO)(?:\s|$)/i.test(text)) return "";
  if (/\.(?:ma|mb)(?:\s|[\\/]).*\.(?:ma|mb)$/i.test(text)) return "";
  return /\.(?:ma|mb)$/i.test(text) ? text : "";
}

function isMayaScenePath(value) {
  return Boolean(hmbNormalizeMayaScenePath(value));
}

function videoPickerNodeRoot(container) {
  // Strict widget boundary: no React Flow/node/canvas traversal.
  return container || null;
}

export function hmbMayaPathFromElement(element) {
  if (!element) return "";
  const values = [
    element.value,
    element.getAttribute?.("value"),
    element.getAttribute?.("title"),
    element.getAttribute?.("data-path"),
  ];
  for (const value of values) {
    const path = hmbNormalizeMayaScenePath(value);
    if (path) return path;
  }
  return "";
}

const HMB_NATIVE_PICKER_CACHE_TTL_MS = 350;

export function hmbInvalidateNativeMayaPickerCache(container) {
  if (container) delete container.__hmbNativeMayaPickerCache;
}

function hmbNativeMayaPickerSnapshot(container) {
  const cached = container?.__hmbNativeMayaPickerCache;
  if (
    cached
    && Date.now() - Number(cached.createdAtMs || 0) <= HMB_NATIVE_PICKER_CACHE_TTL_MS
    && cached.root?.isConnected !== false
    && Array.isArray(cached.elements)
    && Array.isArray(cached.hosts)
    && cached.elements.every((element) => element?.isConnected !== false)
    && cached.hosts.every((host) => host?.isConnected !== false)
  ) {
    return cached;
  }
  const root = videoPickerNodeRoot(container);
  if (!root?.querySelectorAll) return { root, elements: [], hosts: [], createdAtMs: Date.now() };
  const elementSelectors = [
    '[data-parameter-name="MAYA_SCENE"] input',
    '[data-parameter-name="MAYA_SCENE"] textarea',
    '[data-parameter="MAYA_SCENE"] input',
    '[data-parameter="MAYA_SCENE"] textarea',
    '[data-parameter-key="MAYA_SCENE"] input',
    '[data-parameter-key="MAYA_SCENE"] textarea',
    'input[name="MAYA_SCENE"]',
    'textarea[name="MAYA_SCENE"]',
    'input[id*="MAYA_SCENE" i]',
    'textarea[id*="MAYA_SCENE" i]',
    'input[aria-label*="MAYA_SCENE" i]',
    'textarea[aria-label*="MAYA_SCENE" i]',
    'input[placeholder*=".mb" i]',
    'input[placeholder*=".ma" i]',
    'input[type="file"][accept*=".mb" i]',
    'input[type="file"][accept*=".ma" i]',
  ];
  const elements = [];
  const seen = new Set();
  for (const selector of elementSelectors) {
    for (const element of root.querySelectorAll(selector)) {
      if (container.contains?.(element) || seen.has(element)) continue;
      seen.add(element);
      elements.push(element);
    }
  }
  const hosts = [];
  const seenHosts = new Set();
  const addHost = (host) => {
    if (!host || host === root || container.contains?.(host) || host.contains?.(container) || seenHosts.has(host)) return;
    seenHosts.add(host);
    hosts.push(host);
  };
  const hostSelectors = [
    '[data-parameter-name="MAYA_SCENE"]',
    '[data-parameter="MAYA_SCENE"]',
    '[data-parameter-key="MAYA_SCENE"]',
    '[data-parameter-id*="MAYA_SCENE" i]',
    '[aria-label*="MAYA_SCENE" i]',
  ];
  for (const selector of hostSelectors) {
    for (const host of root.querySelectorAll(selector)) addHost(host);
  }
  for (const element of elements) {
    const explicitHost = element.closest?.(
      '[data-parameter-name], [data-parameter], [data-parameter-key], [data-parameter-id], [role="group"]',
    );
    if (explicitHost && explicitHost !== root && !explicitHost.contains?.(container)) {
      addHost(explicitHost);
      continue;
    }
    let candidate = element.parentElement;
    for (let depth = 0; candidate && candidate !== root && depth < 4; depth += 1, candidate = candidate.parentElement) {
      if (candidate.querySelector?.('button, [role="button"], input[type="file"]')) {
        addHost(candidate);
        break;
      }
    }
  }
  // Native-field discovery is intentionally restricted to explicit parameter
  // metadata and the exact value controls above. A broad label/span/div walk
  // is both expensive on large Griptape canvases and can adopt log text that
  // merely happens to start with "MAYA SCENE".
  const snapshot = { root, elements, hosts, createdAtMs: Date.now() };
  if (container) container.__hmbNativeMayaPickerCache = snapshot;
  return snapshot;
}

function nativeMayaPickerElements(container) {
  return hmbNativeMayaPickerSnapshot(container).elements;
}

function nativeMayaPickerHosts(container) {
  return hmbNativeMayaPickerSnapshot(container).hosts;
}

export function hmbNativeMayaScenePath(container) {
  for (const element of nativeMayaPickerElements(container)) {
    const candidate = hmbMayaPathFromElement(element);
    if (candidate) return candidate;
  }
  for (const host of nativeMayaPickerHosts(container)) {
    const direct = hmbMayaPathFromElement(host);
    if (direct) return direct;
    for (const element of host.querySelectorAll?.("input, textarea, [value], [title], [data-path]") || []) {
      const candidate = hmbMayaPathFromElement(element);
      if (candidate) return candidate;
    }
  }
  return "";
}

export function hmbIsExactNativeMayaPickerTarget(container, target) {
  if (!container || !target || container.contains?.(target)) return false;
  const snapshot = hmbNativeMayaPickerSnapshot(container);
  return snapshot.elements.includes(target) || snapshot.hosts.includes(target);
}

export function hmbNativeMayaBrowseSessionActive(container, nowMs = Date.now()) {
  return Number(container?.__hmbNativePickerDeadlineMs || 0) > Number(nowMs || 0);
}

export function hmbClaimNativeMayaBrowseSession(container, actionId, previousPath = "", deadlineMs = 0) {
  const ownerActionId = clean(actionId);
  if (!container || !ownerActionId) return false;
  container.__hmbNativePickerBrowseActionId = ownerActionId;
  container.__hmbNativePickerPreviousPath = hmbNormalizeMayaScenePath(previousPath);
  container.__hmbNativePickerDeadlineMs = Math.max(Date.now() + 1, Number(deadlineMs || 0));
  return true;
}

export function hmbNativeMayaBrowseSessionOwnedBy(container, actionId) {
  const ownerActionId = clean(actionId);
  return !!ownerActionId
    && clean(container?.__hmbNativePickerBrowseActionId) === ownerActionId;
}

export function hmbClearNativeMayaBrowseSession(container, actionId = "") {
  if (!container) return false;
  const ownerActionId = clean(actionId);
  if (ownerActionId && !hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)) return false;
  delete container.__hmbNativePickerBrowseActionId;
  delete container.__hmbNativePickerPreviousPath;
  delete container.__hmbNativePickerDeadlineMs;
  return true;
}

export function hmbPrepareMayaSceneDraftRuntime(container, runtimeInstanceId) {
  if (!container) return false;
  const runtimeId = clean(runtimeInstanceId);
  const ownsRuntime = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbMayaSceneDraftRuntimeInstanceId",
  );
  const runtimeChanged = (
    !ownsRuntime
    || clean(container.__hmbMayaSceneDraftRuntimeInstanceId) !== runtimeId
  );
  if (runtimeChanged) {
    delete container.__hmbMayaSceneDraftPath;
    delete container.__hmbNativePickerPreviousPath;
    delete container.__hmbNativePickerDeadlineMs;
    delete container.__hmbNativePickerBrowseActionId;
    hmbInvalidateNativeMayaPickerCache(container);
  }
  container.__hmbMayaSceneDraftRuntimeInstanceId = runtimeId;
  return runtimeChanged;
}

export function hmbResolveMayaSceneDraftPath(container, state) {
  const source = state && typeof state === "object" ? state : {};
  return (
    hmbNormalizeMayaScenePath(container?.__hmbMayaSceneDraftPath)
    || hmbNormalizeMayaScenePath(source.scene_draft_path)
    || hmbNormalizeMayaScenePath(source.scene_request_path)
    || hmbNormalizeMayaScenePath(source.scene_path)
  );
}

export function hmbCollapseNativeMayaLayoutRows(container, cachedHosts = null) {
  void container;
  void cachedHosts;
  return 0;
}

function openNativeMayaPicker(container) {
  const controls = [];
  const seen = new Set();
  const controlDescription = (control) => clean(
    `${clean(control?.textContent)} ${clean(control?.getAttribute?.("title"))} ${clean(control?.getAttribute?.("aria-label"))}`,
  );
  const opensAssociatedFile = (control) => /(?:^|\s)(?:open\s+(?:file|folder|url)|launch|associated|external|reveal|show\s+in\s+(?:folder|explorer))(?:\s|$)/i.test(
    controlDescription(control),
  );
  const addControl = (control) => {
    if (!control || container.contains?.(control) || seen.has(control) || opensAssociatedFile(control)) return;
    seen.add(control);
    controls.push(control);
  };
  for (const element of nativeMayaPickerElements(container)) {
    if (element.matches?.('input[type="file"]')) addControl(element);
  }
  for (const host of nativeMayaPickerHosts(container)) {
    for (const control of host.querySelectorAll?.('input[type="file"], button, [role="button"]') || []) {
      addControl(control);
    }
  }
  controls.sort((left, right) => {
    const score = (control) => {
      if (control.matches?.('input[type="file"]')) return 3;
      return /browse|picker|select|choose|찾아|선택/i.test(controlDescription(control)) ? 2 : 1;
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

function concealNativeMayaPicker(container) {
  // MAYA_SCENE is hidden by Python ui_options. Do not rewrite any native
  // parameter row or shared host wrapper from the browser widget.
  void container;
}

export function hmbExtractMayaScenePath(value) {
  if (value == null) return "";
  if (Array.isArray(value)) {
    for (const item of value) {
      const path = hmbExtractMayaScenePath(item);
      if (path) return path;
    }
    return "";
  }
  if (typeof value === "object") {
    for (const key of ["path", "file_path", "filepath", "value", "uri", "url", "filename"]) {
      const path = hmbExtractMayaScenePath(value[key]);
      if (path) return path;
    }
    return "";
  }
  const text = clean(value).replace(/^['"]|['"]$/g, "");
  if (!text) return "";
  if (text[0] === "[" || text[0] === "{") {
    try { return hmbExtractMayaScenePath(JSON.parse(text)); } catch (_error) {}
  }
  return hmbNormalizeMayaScenePath(text);
}

function normalizeActivityLog(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") {
      const message = clean(item);
      return message ? { time: "", level: hmbActivityLevelFromStatus("", message), message } : null;
    }
    if (!item || typeof item !== "object") return null;
    const message = clean(item.message);
    if (!message) return null;
    const level = clean(item.level)
      ? hmbNormalizeActivityLevel(item.level)
      : hmbActivityLevelFromStatus("", message);
    return { time: clean(item.time), level, message };
  }).filter(Boolean).slice(-HMB_ACTIVITY_LOG_MAX_ROWS);
}

export function hmbNormalizeActivityLevel(value) {
  const level = clean(value).toUpperCase();
  if (["ERROR", "ERR", "FAILED", "FAILURE", "FATAL", "CRITICAL", "EXCEPTION"].includes(level)) return "ERROR";
  if (["WARNING", "WARN", "CAUTION", "CANCELLED", "CANCELED"].includes(level)) return "WARNING";
  if (["SUCCESS", "OK", "DONE", "COMPLETE", "COMPLETED"].includes(level)) return "SUCCESS";
  return "INFO";
}

export function hmbSummarizeActivityMessage(value, maximumCharacters = HMB_ACTIVITY_LOG_MESSAGE_MAX_CHARS) {
  const singleLine = clean(value).replace(/\s+/g, " ");
  if (!singleLine) return "";
  const maximum = clamp(Math.floor(Number(maximumCharacters) || HMB_ACTIVITY_LOG_MESSAGE_MAX_CHARS), 96, 1000);
  const dagPaths = Array.from(singleLine.matchAll(/(?:^|[\s,;:[('"=])(\|[^,;\s\]\)'"]+)/g))
    .map((match) => ({
      path: clean(match[1]),
      index: Number(match.index || 0) + Math.max(0, String(match[0] || "").indexOf(match[1])),
    }))
    .filter((item) => (item.path.match(/\|/g) || []).length >= 2);
  if (dagPaths.length > 1) {
    const prefix = singleLine.slice(0, dagPaths[0].index).replace(/[\s:;,\[(]+$/g, "");
    const summary = `${prefix || "Maya scene path details"} — ${dagPaths.length} DAG paths omitted; see the Maya log file.`;
    return summary.length <= maximum ? summary : `${summary.slice(0, maximum - 1).trimEnd()}…`;
  }
  const displayLine = dagPaths.length === 1
    ? `${singleLine.slice(0, dagPaths[0].index)}[DAG path]${singleLine.slice(dagPaths[0].index + dagPaths[0].path.length)}`
    : singleLine;
  if (displayLine.length <= maximum) return displayLine;
  const suffix = "… [details truncated; see Maya log]";
  return `${displayLine.slice(0, Math.max(1, maximum - suffix.length)).trimEnd()}${suffix}`;
}

function hmbActivityLevelFromStatus(status, message = "") {
  const statusKey = clean(status).toUpperCase();
  const messageKey = clean(message).toUpperCase();
  if (
    /(?:^|_)(?:FAILED|FAILURE|ERROR|FATAL|CRITICAL|EXCEPTION)(?:$|_)/.test(statusKey)
    || /\b(?:FAILED|FAILURE|ERROR|FATAL|CRITICAL|EXCEPTION)\b/.test(messageKey)
  ) return "ERROR";
  if (
    /(?:^|_)(?:WARNING|WARN|CANCELLED|CANCELED|METADATA_INCOMPLETE)(?:$|_)/.test(statusKey)
    || /\b(?:WARNING|WARN|CANCELLED|CANCELED|TIMED OUT|TIMEOUT)\b/.test(messageKey)
  ) return "WARNING";
  if (["SCENE_READY", "OUTLINER_READY", "VIDEO_READY", "COMPLETE", "COMPLETED", "SUCCESS"].includes(statusKey)) return "SUCCESS";
  return "INFO";
}

function hmbActivityLevelPriority(level) {
  return ({ INFO: 0, SUCCESS: 1, WARNING: 2, ERROR: 3 })[hmbNormalizeActivityLevel(level)] || 0;
}

function hmbActivityLogRowFromText(value) {
  const line = clean(value);
  if (!line) return null;
  if (/^(?:(?:[-*]|\d+[.):])\s*|\[\s*)?["']?\|[^,;\s\]\)"']+["']?\s*[,;\]]?$/.test(line)) return null;
  const structured = line.match(/^\[([^\]]*)\]\s+([A-Za-z_]+)\s+(.*)$/);
  if (structured) {
    const structuredLevel = hmbNormalizeActivityLevel(structured[2]);
    return {
      time: clean(structured[1]),
      level: structuredLevel === "INFO" && clean(structured[2]).toUpperCase() !== "INFO"
        ? hmbActivityLevelFromStatus("", structured[3])
        : structuredLevel,
      message: hmbSummarizeActivityMessage(structured[3]),
    };
  }
  const prefixed = line.match(/^(ERROR|ERR|FAILED|FAILURE|FATAL|CRITICAL|EXCEPTION|WARNING|WARN|SUCCESS|INFO)(?:\s*[:\-]\s*|\s+)(.*)$/i);
  if (prefixed) {
    return {
      time: "",
      level: hmbNormalizeActivityLevel(prefixed[1]),
      message: hmbSummarizeActivityMessage(prefixed[2]),
    };
  }
  return { time: "", level: hmbActivityLevelFromStatus("", line), message: hmbSummarizeActivityMessage(line) };
}

export function hmbActivityLogRowsForDisplay(state) {
  const source = state && typeof state === "object" ? state : {};
  const explicitText = String(source.activity_log_text == null ? "" : source.activity_log_text);
  let rows = [];
  if (explicitText || source.activity_log_text_user_edited || source.activity_log_cleared) {
    rows = explicitText.split(/\r?\n/).map(hmbActivityLogRowFromText).filter(Boolean);
  } else {
    rows = activityLogForDisplay(source).map((entry) => ({
      time: clean(entry.time),
      level: hmbNormalizeActivityLevel(entry.level),
      message: hmbSummarizeActivityMessage(entry.message),
    })).filter((entry) => entry.message);
  }
  const compactRows = [];
  const compactIndex = new Map();
  rows.forEach((entry) => {
    const signature = clean(entry.message).toLowerCase();
    if (!signature) return;
    if (!compactIndex.has(signature)) {
      compactIndex.set(signature, compactRows.length);
      compactRows.push(entry);
      return;
    }
    const index = compactIndex.get(signature);
    const existing = compactRows[index];
    const strongestLevel = hmbActivityLevelPriority(entry.level) > hmbActivityLevelPriority(existing.level)
      ? hmbNormalizeActivityLevel(entry.level)
      : hmbNormalizeActivityLevel(existing.level);
    compactRows[index] = { ...existing, time: clean(entry.time) || clean(existing.time), level: strongestLevel };
  });
  rows = compactRows;
  const represented = new Map();
  rows.forEach((entry, index) => {
    const signature = clean(entry.message).toLowerCase();
    if (signature) represented.set(signature, index);
  });
  const addNotification = (level, message) => {
    const summary = hmbSummarizeActivityMessage(message);
    const signature = summary.toLowerCase();
    if (!summary) return;
    const normalizedLevel = hmbNormalizeActivityLevel(level);
    if (represented.has(signature)) {
      const index = represented.get(signature);
      if (hmbActivityLevelPriority(normalizedLevel) > hmbActivityLevelPriority(rows[index]?.level)) {
        rows[index] = { ...rows[index], level: normalizedLevel };
      }
      return;
    }
    const prefixIndex = rows.findIndex((entry) => {
      const existing = clean(entry.message).toLowerCase();
      return existing.length >= 24 && (
        signature.startsWith(`${existing} —`)
        || existing.startsWith(`${signature} —`)
      );
    });
    if (prefixIndex >= 0) {
      const existing = rows[prefixIndex];
      const existingSignature = clean(existing.message).toLowerCase();
      const strongestLevel = hmbActivityLevelPriority(normalizedLevel) > hmbActivityLevelPriority(existing.level)
        ? normalizedLevel
        : hmbNormalizeActivityLevel(existing.level);
      const strongestMessage = summary.length >= clean(existing.message).length ? summary : clean(existing.message);
      rows[prefixIndex] = { ...existing, level: strongestLevel, message: strongestMessage };
      represented.delete(existingSignature);
      represented.set(strongestMessage.toLowerCase(), prefixIndex);
      return;
    }
    rows.push({ time: "", level: normalizedLevel, message: summary });
    represented.set(signature, rows.length - 1);
  };
  (Array.isArray(source.warnings) ? source.warnings : []).forEach((warning) => addNotification("WARNING", warning));
  addNotification(hmbActivityLevelFromStatus(source.status, source.message), source.message);
  return rows.slice(-HMB_ACTIVITY_LOG_MAX_ROWS);
}

export function hmbStateWithNotificationsLogged(next, previous = {}) {
  let state = next && typeof next === "object" ? { ...next } : {};
  const priorMessage = clean(previous?.message);
  const nextMessage = clean(state.message);
  const priorWarnings = new Set((Array.isArray(previous?.warnings) ? previous.warnings : []).map(clean).filter(Boolean));
  const notificationsByMessage = new Map();
  const addNotification = (level, message) => {
    const summary = hmbSummarizeActivityMessage(message);
    if (!summary) return;
    const signature = summary.toLowerCase();
    const normalizedLevel = hmbNormalizeActivityLevel(level);
    const existing = notificationsByMessage.get(signature);
    if (!existing || hmbActivityLevelPriority(normalizedLevel) > hmbActivityLevelPriority(existing.level)) {
      notificationsByMessage.set(signature, { level: normalizedLevel, message: summary });
    }
  };
  (Array.isArray(state.warnings) ? state.warnings : [])
    .map(clean)
    .filter((warning) => warning && !priorWarnings.has(warning))
    .forEach((message) => addNotification("WARNING", message));
  if (nextMessage && nextMessage !== priorMessage) {
    addNotification(hmbActivityLevelFromStatus(state.status, nextMessage), nextMessage);
  }
  const loggedMessages = new Map();
  normalizeActivityLog(state.activity_log).forEach((entry) => {
    loggedMessages.set(hmbSummarizeActivityMessage(entry.message).toLowerCase(), hmbNormalizeActivityLevel(entry.level));
  });
  for (const notification of notificationsByMessage.values()) {
    const signature = notification.message.toLowerCase();
    const loggedLevel = loggedMessages.get(signature);
    if (loggedLevel && hmbActivityLevelPriority(loggedLevel) >= hmbActivityLevelPriority(notification.level)) continue;
    state = appendActivityLog(state, notification.level, notification.message);
    loggedMessages.set(signature, notification.level);
  }
  return state;
}

function currentLogTime() {
  try {
    return new Date().toLocaleTimeString("en-GB", { hour12: false });
  } catch (_error) {
    return "";
  }
}

function formatActivityLogEntry(entry) {
  if (!entry || !clean(entry.message)) return "";
  return `[${clean(entry.time) || "--:--:--"}] ${hmbNormalizeActivityLevel(entry.level)}  ${clean(entry.message)}`;
}

function structuredActivityLogText(state) {
  return activityLogForDisplay(state).map(formatActivityLogEntry).filter(Boolean).join("\n");
}

function editableActivityLogText(state) {
  const explicit = String(state?.activity_log_text == null ? "" : state.activity_log_text);
  if (explicit || state?.activity_log_text_user_edited || state?.activity_log_cleared) return explicit;
  return structuredActivityLogText(state);
}

function appendActivityLog(state, level, message) {
  const entry = { time: currentLogTime(), level: hmbNormalizeActivityLevel(level), message: hmbSummarizeActivityMessage(message) };
  if (!entry.message) return state;
  const existingText = editableActivityLogText(state);
  const line = formatActivityLogEntry(entry);
  return {
    ...state,
    activity_log: [...normalizeActivityLog(state.activity_log), entry].slice(-HMB_ACTIVITY_LOG_MAX_ROWS),
    activity_log_text: (existingText ? `${existingText.replace(/\s+$/, "")}\n${line}` : line).slice(-32000),
    activity_log_cleared: false,
  };
}

function activityLogForDisplay(state) {
  const entries = normalizeActivityLog(state.activity_log);
  if (entries.length || state.activity_log_cleared || !state.native_read_ready || !clean(state.scene_path)) return entries;
  const sceneName = clean(state.scene_path).replace(/\\/g, "/").split("/").pop() || clean(state.scene_path);
  const cameraNames = (Array.isArray(state.cameras) ? state.cameras : [])
    .map((item) => clean(item?.name || item?.full_path))
    .filter(Boolean);
  return [
    { time: "", level: "SUCCESS", message: `Maya scene loaded: ${sceneName}.` },
    { time: "", level: "INFO", message: `Frame information: start ${Number(state.start_frame || 0)}, current ${Number(state.current_frame || 0)}, end ${Number(state.end_frame || 0)}, FPS ${Number(state.source_fps || 0)}.` },
    { time: "", level: "INFO", message: `User cameras (${cameraNames.length}): ${cameraNames.join(", ") || "none"}.` },
    { time: "", level: "SUCCESS", message: "The atomic Maya READ snapshot is displayed." },
  ];
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function hmbActivityLogRowHtml(entry) {
  const level = hmbNormalizeActivityLevel(entry?.level);
  const message = hmbSummarizeActivityMessage(entry?.message);
  if (!message) return "";
  return `<div class="activity-log-row" data-level="${level}" role="listitem"><span class="activity-log-time">[${escapeHtml(clean(entry?.time) || "--:--:--")}]</span><span class="activity-log-level">${level}</span><span class="activity-log-message">${escapeHtml(message)}</span></div>`;
}

function hmbActivityLogHtml(state, tr) {
  const rows = hmbActivityLogRowsForDisplay(state);
  if (!rows.length) return `<div class="activity-log-empty">${escapeHtml(tr?.noActivity || "No activity yet.")}</div>`;
  return rows.map(hmbActivityLogRowHtml).filter(Boolean).join("");
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, Number(value)));
}

function hmbVideoAssetHash(value) {
  let hash = 2166136261;
  for (const character of String(value || "")) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function hmbSnapshotUid(item, snapshotIndex = 0) {
  const explicit = clean(item?.snapshot_uid || item?.snapshot_id || item?.uid);
  if (explicit) return explicit;
  const identity = [
    clean(item?.path || item?.snapshot_path),
    clean(item?.url || item?.media_url || item?.snapshot_url),
    clean(item?.sha256 || item?.content_sha256 || item?.snapshot_sha256),
    clean(item?.video_uid),
    Number(item?.render_video_slot || item?.video_slot || 1),
    Number(item?.frame || item?.snapshot_frame || 0),
    Number(item?.created_at_ms || item?.created_at || 0),
    Number(snapshotIndex || 0),
  ].join("|");
  return `snapshot-${hmbVideoAssetHash(identity)}`;
}

export function hmbSnapshotHistory(state) {
  return (Array.isArray(state?.snapshots) ? state.snapshots : [])
    .map((item, snapshotIndex) => ({ item, snapshotIndex }))
    .filter(({ item }) => (
      item
      && typeof item === "object"
      && !!clean(item.url || item.media_url || item.path || item.snapshot_path)
    ))
    .map(({ item, snapshotIndex }) => ({
      ...item,
      snapshot_uid: hmbSnapshotUid(item, snapshotIndex),
      __snapshot_index: snapshotIndex,
    }))
    .sort((left, right) => (
      Number(left.created_at_ms || 0) - Number(right.created_at_ms || 0)
      || left.__snapshot_index - right.__snapshot_index
    ))
    .slice(-HMB_PICKER_MAX_SNAPSHOTS)
    .map((item) => {
      const next = { ...item };
      delete next.__snapshot_index;
      delete next.data_uri;
      delete next.snapshot_data_uri;
      return next;
    });
}

function hmbSnapshotMediaUrl(item) {
  const explicit = clean(item?.url || item?.media_url || item?.snapshot_url);
  return explicit && !explicit.startsWith("data:")
    ? explicit
    : videoSourceUrl(item?.path || item?.snapshot_path);
}

function hmbVideoAssetUid(item, catalogIndex = 0) {
  const explicit = clean(item?.video_uid || item?.source_uid || item?.asset_uid);
  if (explicit) return explicit;
  const identity = [
    clean(item?.project_video_path),
    clean(item?.video_path),
    clean(item?.video_url),
    clean(item?.run_id || item?.bundle_run_id || item?.pair_run_id),
    clean(item?.generation_role || item?.video_role || item?.media_kind),
    Number(item?.created_at_ms || item?.created_at || 0),
    Number(catalogIndex || 0),
  ].join("|");
  return `video-${hmbVideoAssetHash(identity)}`;
}

function hmbVideoAssetPath(item) {
  return clean(item?.video_url || item?.project_video_path || item?.video_path);
}

function hmbVideoAssetHasMedia(item) {
  return !!hmbVideoAssetPath(item);
}

export function hmbSelectedVideoAssets(state) {
  const source = Array.isArray(state?.videos) ? state.videos : [];
  const indexed = source
    .filter((item) => item && typeof item === "object" && hmbVideoAssetHasMedia(item))
    .map((item, catalogIndex) => ({
      ...item,
      video_uid: hmbVideoAssetUid(item, catalogIndex),
      __catalog_index: catalogIndex,
    }));
  const activeWorkspace = hmbActivePickerWorkspace(state);
  if (activeWorkspace && Array.isArray(activeWorkspace.selected_video_uids)) {
    const allowedAssets = Object.prototype.hasOwnProperty.call(activeWorkspace, "video_asset_uids")
      ? new Set(hmbPickerWorkspaceAssetUids(activeWorkspace))
      : null;
    const orderedUids = Array.from(new Set(activeWorkspace.selected_video_uids.map(clean).filter(Boolean)))
      .filter((uid) => !allowedAssets || allowedAssets.has(uid))
      .slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
    const byUid = new Map(indexed.map((item) => [clean(item.video_uid), item]));
    return orderedUids.map((uid, index) => {
      const item = byUid.get(uid);
      if (!item) return null;
      const next = {
        ...item,
        selected: true,
        selection_order: index + 1,
        video_slot: index + 1,
      };
      delete next.__catalog_index;
      return next;
    }).filter(Boolean);
  }
  const explicitSelection = indexed.some((item) => (
    Object.prototype.hasOwnProperty.call(item, "selected")
    || Math.floor(Number(item.selection_order || 0)) > 0
  ));
  const selected = indexed.filter((item) => (
    explicitSelection
      ? item.selected === true || (item.selected !== false && Number(item.selection_order || 0) > 0)
      : true
  ));
  selected.sort((left, right) => {
    const leftOrder = explicitSelection
      ? Number(left.selection_order || left.video_slot || left.__catalog_index + 1)
      : Number(left.video_slot || left.__catalog_index + 1);
    const rightOrder = explicitSelection
      ? Number(right.selection_order || right.video_slot || right.__catalog_index + 1)
      : Number(right.video_slot || right.__catalog_index + 1);
    return leftOrder - rightOrder || left.__catalog_index - right.__catalog_index;
  });
  // Keep the bounded ordered selection visible to workspace migration.  The
  // preview is independent from generator order and may point at any member.
  return selected.slice(0, HMB_PICKER_MAX_SELECTED_VIDEOS).map((item, index) => {
    const next = {
      ...item,
      selected: true,
      selection_order: index + 1,
      video_slot: index + 1,
    };
    delete next.__catalog_index;
    return next;
  });
}

function hmbApplyVideoAssetSelection(state, orderedUids, requestedPreviewUid = "") {
  const source = Array.isArray(state?.videos) ? state.videos : [];
  const pickerShots = Array.isArray(state?.picker_shots)
    ? state.picker_shots.map((row) => {
      const cloned = {
        ...row,
        selected_video_uids: Array.isArray(row?.selected_video_uids) ? [...row.selected_video_uids] : [],
      };
      if (Array.isArray(row?.video_asset_uids)) cloned.video_asset_uids = [...row.video_asset_uids];
      else delete cloned.video_asset_uids;
      return cloned;
    })
    : [];
  const activeWorkspaceUuid = hmbUuid(state?.active_picker_shot_uuid);
  const activeWorkspace = pickerShots.find((row) => hmbUuid(row?.workspace_uuid) === activeWorkspaceUuid)
    || pickerShots[0]
    || null;
  const sourceUids = source.map((item, catalogIndex) => hmbVideoAssetUid(item, catalogIndex));
  const knownUids = new Set(sourceUids);
  const hasOwnedAssetContract = !!activeWorkspace
    && Object.prototype.hasOwnProperty.call(activeWorkspace, "video_asset_uids");
  const ownedUids = hasOwnedAssetContract
    ? hmbPickerWorkspaceAssetUids(activeWorkspace)
    : sourceUids.filter(Boolean);
  const ownedUidSet = new Set(ownedUids);
  const candidates = Array.from(new Set(
    (Array.isArray(orderedUids) ? orderedUids : []).map(clean).filter(Boolean),
  )).filter((uid) => knownUids.has(uid) && ownedUidSet.has(uid));
  const uniqueOrder = candidates.slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
  const orderByUid = new Map(uniqueOrder.map((uid, index) => [uid, index + 1]));
  const videos = source.map((item, catalogIndex) => {
    const uid = hmbVideoAssetUid(item, catalogIndex);
    const selectionOrder = Number(orderByUid.get(uid) || 0);
    const next = {
      ...item,
      video_uid: uid,
      selected: selectionOrder > 0,
      selection_order: selectionOrder,
      video_slot: selectionOrder,
    };
    if (next.frame_metadata && typeof next.frame_metadata === "object") {
      next.frame_metadata = {
        ...next.frame_metadata,
        video_slot: selectionOrder > 0 ? `@video${selectionOrder}` : "",
      };
    }
    if (Array.isArray(next.markers)) {
      next.markers = next.markers.map((marker) => ({
        ...marker,
        video_slot: selectionOrder > 0 ? selectionOrder : Number(marker?.video_slot || 1),
      }));
    }
    return next;
  });
  const byUid = new Map(videos.map((item) => [clean(item.video_uid), item]));
  let previewUid = clean(requestedPreviewUid || state?.preview_video_uid || state?.selected_video_uid);
  if (!byUid.has(previewUid) || !ownedUidSet.has(previewUid)) {
    previewUid = uniqueOrder[0] || ownedUids.find((uid) => byUid.has(uid)) || "";
  }
  const preview = byUid.get(previewUid) || null;
  const previewOrder = Number(orderByUid.get(previewUid) || 0);
  const selectedSlot = previewOrder > 0
    ? previewOrder
    : clamp(Number(state?.selected_video_slot || 1), 1, Math.max(1, uniqueOrder.length));
  if (activeWorkspace) {
    const workspaceChanged = JSON.stringify(activeWorkspace.selected_video_uids) !== JSON.stringify(uniqueOrder)
      || clean(activeWorkspace.preview_video_uid) !== previewUid;
    activeWorkspace.selected_video_uids = [...uniqueOrder];
    activeWorkspace.preview_video_uid = previewUid;
    activeWorkspace.selected_video_slot = selectedSlot;
    if (workspaceChanged) activeWorkspace.revision = Math.max(0, Math.floor(Number(activeWorkspace.revision || 0))) + 1;
  }
  return {
    ...state,
    picker_shots: pickerShots,
    videos,
    video_library_version: 1,
    max_selected_videos: HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS,
    active_slot_count: Math.max(1, uniqueOrder.length),
    selected_video_slot: selectedSlot,
    preview_video_uid: previewUid,
    selected_video_uid: previewUid,
    selected_video_path: hmbVideoAssetPath(preview),
  };
}

export function hmbToggleVideoAssetSelection(state, uid) {
  const targetUid = clean(uid);
  if (!targetUid) return { ...state };
  const ordered = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  const index = ordered.indexOf(targetUid);
  const replacement = [...ordered];
  if (index >= 0) replacement.splice(index, 1);
  else if (replacement.length < HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS) replacement.push(targetUid);
  const currentPreview = clean(state?.preview_video_uid || state?.selected_video_uid);
  const requestedPreview = index < 0
    ? targetUid
    : (currentPreview === targetUid ? (replacement[0] || "") : currentPreview);
  const next = hmbApplyVideoAssetSelection(state, replacement, requestedPreview);
  if (!replacement.length) {
    next.preview_video_uid = "";
    next.selected_video_uid = "";
    next.selected_video_path = "";
    next.selected_video_slot = 1;
  }
  return next;
}

export function hmbMoveSelectedVideoAsset(state, uid, targetIndex) {
  const targetUid = clean(uid);
  const ordered = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  const currentIndex = ordered.indexOf(targetUid);
  if (currentIndex < 0 || !ordered.length) return { ...state };
  const destination = clamp(Math.floor(Number(targetIndex || 0)), 0, ordered.length - 1);
  ordered.splice(currentIndex, 1);
  ordered.splice(destination, 0, targetUid);
  // Generator order and preview/playback are independent state. Reordering a
  // card must not silently route the dragged clip into the shared viewport or
  // interrupt a clip that is already playing.
  const retainedPreviewUid = clean(state?.preview_video_uid || state?.selected_video_uid);
  return hmbApplyVideoAssetSelection(state, ordered, retainedPreviewUid);
}

function hmbApplySelectedVideoAssetOrderToDomNormalized(container, normalized, tr = null, locked = false) {
  const compactRows = Array.from(container?.querySelectorAll?.(
    "[data-picker-shot-row][data-picker-shot-layout='compact']",
  ) || []);
  for (const rowElement of compactRows) {
    const workspaceUuid = hmbUuid(rowElement.getAttribute?.("data-picker-shot-row"));
    const workspace = normalized.picker_shots.find(
      (row) => hmbUuid(row?.workspace_uuid) === workspaceUuid,
    );
    if (!workspace) continue;
    const selectedUids = Array.from(new Set(
      (Array.isArray(workspace.selected_video_uids) ? workspace.selected_video_uids : [])
        .map(clean).filter(Boolean),
    )).slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
    const selectedOrder = new Map(selectedUids.map((uid, index) => [uid, index + 1]));
    const selectionFull = selectedUids.length >= HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS;
    for (const card of rowElement.querySelectorAll?.("[data-video-uid]") || []) {
      const uid = clean(card.getAttribute?.("data-video-uid"));
      const order = Number(selectedOrder.get(uid) || 0);
      const selectedAsset = order > 0;
      const blocked = !selectedAsset && selectionFull;
      card.classList?.toggle?.("selected", selectedAsset);
      card.setAttribute?.("data-selected-video-order", String(order));
      const selectionSurface = card.querySelector?.("[data-toggle-video-uid]");
      if (selectionSurface) {
        const disabled = !!locked || blocked;
        if ("disabled" in selectionSurface) selectionSurface.disabled = disabled;
        selectionSurface.setAttribute?.("aria-disabled", disabled ? "true" : "false");
        selectionSurface.setAttribute?.("aria-pressed", selectedAsset ? "true" : "false");
        const title = clean(selectionSurface.textContent);
        if (tr && title) {
          selectionSurface.setAttribute?.(
            "aria-label",
            `${title}: ${selectedAsset ? tr.deselectVideoAsset : tr.selectVideoAsset}`,
          );
        }
      }
    }
    const status = rowElement.querySelector?.(".compact-shot-status");
    if (status) {
      status.textContent = `VIDEOS ${hmbPickerWorkspaceAssetUids(workspace).length}/10 · USE ${selectedUids.length}`;
    }
  }
  const grid = container?.querySelector?.(".video-asset-grid");
  if (!grid || typeof grid.querySelectorAll !== "function" || typeof grid.appendChild !== "function") {
    return hmbSelectedVideoAssets(normalized).map((item) => clean(item.video_uid));
  }
  const cards = Array.from(grid.querySelectorAll("[data-video-uid]") || []);
  if (!cards.length) return [];
  const selectedUids = hmbSelectedVideoAssets(normalized).map((item) => clean(item.video_uid));
  const selectedOrder = new Map(selectedUids.map((uid, index) => [uid, index + 1]));
  const cardByUid = new Map(cards.map((card) => [clean(card.getAttribute?.("data-video-uid")), card]));
  const orderedCards = [
    ...selectedUids.map((uid) => cardByUid.get(uid)).filter(Boolean),
    ...cards.filter((card) => !selectedOrder.has(clean(card.getAttribute?.("data-video-uid")))),
  ];
  orderedCards.forEach((card, index) => {
    const current = grid.children?.[index] || null;
    if (current === card) return;
    if (typeof grid.insertBefore === "function") grid.insertBefore(card, current);
    else grid.appendChild(card);
  });
  for (const card of cards) {
    const uid = clean(card.getAttribute?.("data-video-uid"));
    const order = Number(selectedOrder.get(uid) || 0);
    const selectedAsset = order > 0;
    const blocked = !selectedAsset
      && selectedUids.length >= HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS;
    card.setAttribute?.("data-selected-video-order", String(order));
    if (selectedAsset) {
      card.classList?.add?.("selected");
      card.classList?.remove?.("selection-blocked");
      card.setAttribute?.("data-selected-video-uid", uid);
      card.setAttribute?.("draggable", locked || selectedUids.length < 2 ? "false" : "true");
    } else {
      card.classList?.remove?.("selected");
      if (blocked) card.classList?.add?.("selection-blocked");
      else card.classList?.remove?.("selection-blocked");
      card.removeAttribute?.("data-selected-video-uid");
      card.setAttribute?.("draggable", "false");
    }
    let badge = card.querySelector?.(".selected-video-order");
    if (selectedAsset && !badge) {
      const ownerDocument = card.ownerDocument || (typeof document !== "undefined" ? document : null);
      const thumb = card.querySelector?.(".video-asset-thumb");
      if (ownerDocument?.createElement && thumb) {
        badge = ownerDocument.createElement("span");
        badge.className = "selected-video-order";
        const playButton = thumb.querySelector?.("[data-play-video-uid]");
        if (playButton && typeof thumb.insertBefore === "function") thumb.insertBefore(badge, playButton);
        else thumb.appendChild?.(badge);
      }
    }
    if (badge && selectedAsset) badge.textContent = String(order).padStart(2, "0");
    if (badge && !selectedAsset) badge.remove?.();
    const selectionSurface = card.querySelector?.("[data-toggle-video-uid]");
    if (selectionSurface) {
      const disabled = blocked || locked;
      if ("disabled" in selectionSurface) selectionSurface.disabled = disabled;
      selectionSurface.setAttribute?.("aria-disabled", disabled ? "true" : "false");
      selectionSurface.setAttribute?.("aria-pressed", selectedAsset ? "true" : "false");
      selectionSurface.setAttribute?.("tabindex", disabled ? "-1" : "0");
      const title = clean(card.querySelector?.("[data-play-video-uid]")?.getAttribute?.("data-video-title"));
      if (tr && title) {
        selectionSurface.setAttribute?.(
          "aria-label",
          `${title}: ${selectedAsset ? tr.deselectVideoAsset : tr.selectVideoAsset}`,
        );
      }
    }
    const playButton = card.querySelector?.("[data-play-video-uid]");
    if (playButton) {
      playButton.disabled = !!locked;
      playButton.setAttribute?.("aria-disabled", locked ? "true" : "false");
    }
    const deleteButton = card.querySelector?.("[data-delete-video-uid]");
    if (deleteButton) {
      deleteButton.disabled = !!locked;
      deleteButton.setAttribute?.("aria-disabled", locked ? "true" : "false");
    }
  }
  const count = container?.querySelector?.(".video-selected-count");
  if (count) count.textContent = `${Math.min(selectedUids.length, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS)}/${HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS}`;
  return selectedUids;
}

export function hmbApplySelectedVideoAssetOrderToDom(container, state, tr = null, locked = false) {
  return hmbApplySelectedVideoAssetOrderToDomNormalized(container, normalize(state), tr, locked);
}

function hmbApplyPickerShotFeedbackNormalized(container, normalized, tr = null, locked = false) {
  const hasLocalWorkspaceRows = Array.isArray(normalized?.picker_shots) && normalized.picker_shots.length > 0;
  const activeWorkspace = hmbActivePickerWorkspace(normalized);
  hmbApplyPickerShotPalette(
    container?.querySelector?.(".hmbvp"),
    hasLocalWorkspaceRows ? (activeWorkspace?.number || 1) : (Number(normalized?.shot_number || 1)),
  );
  const selector = container?.querySelector?.("#shot-selector");
  if (selector) {
    const shotUuid = clean(normalized.shot_uuid);
    const options = Array.from(selector.options || []);
    if (options.some((option) => clean(option?.value) === shotUuid)) selector.value = shotUuid;
  }
  return hmbApplySelectedVideoAssetOrderToDomNormalized(container, normalized, tr, locked);
}

export function hmbApplyPickerShotFeedback(container, state, tr = null, locked = false) {
  return hmbApplyPickerShotFeedbackNormalized(container, normalize(state), tr, locked);
}

function hmbVideoAssetCardFromDragEvent(container, event) {
  const card = event?.target?.closest?.("[data-video-uid]") || null;
  if (!card) return null;
  if (typeof container?.contains === "function" && !container.contains(card)) return null;
  return card;
}

function hmbClearVideoAssetDropTargets(container) {
  Array.from(container?.querySelectorAll?.(".video-asset-card.drop-target") || []).forEach((card) => {
    card.classList?.remove?.("drop-target");
  });
}

export function hmbInstallVideoAssetDragReorder(container, options = {}) {
  if (!container || typeof container.addEventListener !== "function") return () => {};
  const currentState = typeof options.currentState === "function" ? options.currentState : () => ({});
  const commitState = typeof options.commitState === "function" ? options.commitState : () => {};
  const interactionLocked = () => (
    typeof options.locked === "function" ? !!options.locked() : options.locked === true
  );
  const listeners = [];
  const listen = (eventName, handler) => {
    container.addEventListener(eventName, handler, true);
    listeners.push([eventName, handler]);
  };
  const releaseClickSuppression = () => {
    setTimeout(() => { delete container.__hmbSuppressVideoSelectionClick; }, 0);
  };
  const clearCandidate = () => {
    const session = container.__hmbVideoDragSession;
    if (session && typeof session === "object") {
      session.targetUid = "";
      session.targetIndex = -1;
    }
    hmbClearVideoAssetDropTargets(container);
  };
  const clearSession = () => {
    hmbClearVideoAssetDropTargets(container);
    Array.from(container.querySelectorAll?.(".video-asset-card.dragging") || []).forEach((card) => {
      card.classList?.remove?.("dragging");
    });
    delete container.__hmbVideoDragSession;
    delete container.__hmbDraggedVideoUid;
    releaseClickSuppression();
  };
  const setCandidate = (card, event) => {
    const session = container.__hmbVideoDragSession;
    const targetUid = clean(card?.getAttribute?.("data-video-uid"));
    const liveState = currentState();
    const liveWorkspaceUuid = hmbUuid(hmbActivePickerWorkspace(liveState)?.workspace_uuid);
    if (
      !session
      || !session.workspaceUuid
      || liveWorkspaceUuid !== session.workspaceUuid
      || !targetUid
      || targetUid === clean(session.sourceUid)
      || !card?.hasAttribute?.("data-selected-video-uid")
    ) {
      clearCandidate();
      return false;
    }
    const selected = hmbSelectedVideoAssets(liveState);
    const targetIndex = selected.findIndex((item) => clean(item.video_uid) === targetUid);
    if (targetIndex < 0) {
      clearCandidate();
      return false;
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();
    try { if (event?.dataTransfer) event.dataTransfer.dropEffect = "move"; } catch (_error) {}
    hmbClearVideoAssetDropTargets(container);
    card.classList?.add?.("drop-target");
    session.targetUid = targetUid;
    session.targetIndex = targetIndex;
    return true;
  };
  const finalize = (reason) => {
    const session = container.__hmbVideoDragSession;
    if (!session || session.committed) return false;
    const liveState = currentState();
    const liveWorkspaceUuid = hmbUuid(hmbActivePickerWorkspace(liveState)?.workspace_uuid);
    if (!session.workspaceUuid || liveWorkspaceUuid !== session.workspaceUuid) {
      clearSession();
      return false;
    }
    const selected = hmbSelectedVideoAssets(liveState);
    const sourceUid = clean(session.sourceUid);
    const targetUid = clean(session.targetUid);
    const sourceIndex = selected.findIndex((item) => clean(item.video_uid) === sourceUid);
    const targetIndex = selected.findIndex((item) => clean(item.video_uid) === targetUid);
    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
      clearSession();
      return false;
    }
    session.committed = true;
    const nextState = hmbMoveSelectedVideoAsset(liveState, sourceUid, targetIndex);
    const details = { reason: clean(reason), sourceUid, targetUid, sourceIndex, targetIndex };
    // Release the native-drag latches before a host echo can synchronously morph
    // the card grid. The optimistic DOM move keeps the new order visible even
    // when Griptape consumes an otherwise identical local state echo.
    clearSession();
    hmbApplySelectedVideoAssetOrderToDom(container, nextState);
    commitState(nextState, details);
    return true;
  };

  // A normal Griptape props update cleans up and reinstalls this controller
  // while retaining the same container. Preserve an in-flight native drag
  // across that remount and restore its visual source/target markers.
  const retainedSession = container.__hmbVideoDragSession;
  if (interactionLocked() && retainedSession) {
    clearSession();
  } else if (retainedSession) {
    const sourceCard = Array.from(container.querySelectorAll?.("[data-video-uid]") || [])
      .find((card) => clean(card.getAttribute?.("data-video-uid")) === clean(retainedSession.sourceUid));
    const targetCard = Array.from(container.querySelectorAll?.("[data-video-uid]") || [])
      .find((card) => clean(card.getAttribute?.("data-video-uid")) === clean(retainedSession.targetUid));
    sourceCard?.classList?.add?.("dragging");
    targetCard?.classList?.add?.("drop-target");
  }

  listen("dragstart", (event) => {
    const card = hmbVideoAssetCardFromDragEvent(container, event);
    if (
      interactionLocked()
      || !card
      || hmbSelectedVideoAssets(currentState()).length < 2
      || card.getAttribute?.("draggable") !== "true"
      || !card.hasAttribute?.("data-selected-video-uid")
      || event?.target?.closest?.("[data-play-video-uid], [data-delete-video-uid]")
    ) {
      event?.preventDefault?.();
      return;
    }
    const sourceUid = clean(card.getAttribute?.("data-video-uid"));
    if (!sourceUid) {
      event?.preventDefault?.();
      return;
    }
    const liveState = currentState();
    const workspaceUuid = hmbUuid(hmbActivePickerWorkspace(liveState)?.workspace_uuid);
    if (!workspaceUuid) {
      event?.preventDefault?.();
      return;
    }
    container.__hmbVideoDragSession = {
      sourceUid,
      workspaceUuid,
      targetUid: "",
      targetIndex: -1,
      committed: false,
    };
    container.__hmbDraggedVideoUid = sourceUid;
    container.__hmbSuppressVideoSelectionClick = true;
    card.classList?.add?.("dragging");
    event?.stopPropagation?.();
    try {
      if (event?.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData?.("text/plain", sourceUid);
      }
    } catch (_error) {}
  });
  listen("dragover", (event) => {
    if (!container.__hmbVideoDragSession) return;
    const card = hmbVideoAssetCardFromDragEvent(container, event);
    if (!setCandidate(card, event)) clearCandidate();
  });
  listen("dragleave", (event) => {
    if (event?.target !== container) return;
    const related = event?.relatedTarget || null;
    if (!related || typeof container.contains !== "function" || !container.contains(related)) clearCandidate();
  });
  listen("drop", (event) => {
    const session = container.__hmbVideoDragSession;
    if (!session) return;
    const card = hmbVideoAssetCardFromDragEvent(container, event);
    if (card) setCandidate(card, event);
    if (!clean(session.targetUid)) {
      clearSession();
      return;
    }
    event?.preventDefault?.();
    event?.stopPropagation?.();
    finalize("drop");
  });
  listen("dragend", () => {
    // Embedded graph hosts can swallow the target's bubble-phase drop after a
    // card morph. The last valid capture-phase target is still authoritative.
    if (!finalize("dragend")) clearSession();
  });

  return () => {
    listeners.forEach(([eventName, handler]) => container.removeEventListener?.(eventName, handler, true));
    hmbClearVideoAssetDropTargets(container);
    Array.from(container.querySelectorAll?.(".video-asset-card.dragging") || []).forEach((card) => {
      card.classList?.remove?.("dragging");
    });
    // Do not clear __hmbVideoDragSession here: this same cleanup runs before
    // every host-driven widget morph. The newly installed delegated controller
    // resumes the retained session and dragend remains able to finalize it.
  };
}

export function hmbPreviewVideoAsset(state, uid) {
  const targetUid = clean(uid);
  const source = Array.isArray(state?.videos) ? state.videos : [];
  const activeWorkspace = hmbActivePickerWorkspace(state);
  const hasOwnedAssetContract = !!activeWorkspace
    && Object.prototype.hasOwnProperty.call(activeWorkspace, "video_asset_uids");
  const activeAssets = new Set(hmbPickerWorkspaceAssetUids(activeWorkspace));
  const exists = (!hasOwnedAssetContract || activeAssets.has(targetUid))
    && source.some((item, index) => hmbVideoAssetUid(item, index) === targetUid);
  if (!targetUid || !exists) return { ...state };
  const ordered = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  return hmbApplyVideoAssetSelection(state, ordered, targetUid);
}

export function hmbDeleteVideoAsset(state, uid) {
  const targetUid = clean(uid);
  if (!targetUid) return { ...state };
  const source = Array.isArray(state?.videos) ? state.videos : [];
  const remaining = source.filter((item, index) => hmbVideoAssetUid(item, index) !== targetUid);
  if (remaining.length === source.length) return { ...state };
  const pickerShots = (Array.isArray(state?.picker_shots) ? state.picker_shots : []).map((row) => {
    const videoAssetUids = hmbPickerWorkspaceAssetUids(row).filter((candidate) => candidate !== targetUid);
    const selectedVideoUids = (Array.isArray(row?.selected_video_uids) ? row.selected_video_uids : [])
      .map(clean)
      .filter((candidate) => candidate && candidate !== targetUid && videoAssetUids.includes(candidate));
    const previewVideoUid = clean(row?.preview_video_uid) === targetUid
      ? (selectedVideoUids[0] || videoAssetUids[0] || "")
      : clean(row?.preview_video_uid);
    const changed = videoAssetUids.length !== hmbPickerWorkspaceAssetUids(row).length
      || selectedVideoUids.length !== (Array.isArray(row?.selected_video_uids) ? row.selected_video_uids.length : 0)
      || previewVideoUid !== clean(row?.preview_video_uid);
    return {
      ...row,
      video_asset_uids: videoAssetUids,
      selected_video_uids: selectedVideoUids,
      preview_video_uid: previewVideoUid,
      revision: Math.max(0, Math.floor(Number(row?.revision || 0))) + (changed ? 1 : 0),
    };
  });
  const nextState = { ...state, videos: remaining, picker_shots: pickerShots };
  const ordered = hmbSelectedVideoAssets(nextState).map((item) => clean(item.video_uid));
  const activeWorkspace = hmbActivePickerWorkspace(nextState);
  const requestedPreview = clean(activeWorkspace?.preview_video_uid)
    || ordered[0]
    || hmbPickerWorkspaceAssetUids(activeWorkspace)[0]
    || "";
  return hmbApplyVideoAssetSelection(nextState, ordered, requestedPreview);
}

function defaultState() {
  return {
    schema: "maya-video-picker-state",
    state_revision: 0,
    state_writer: "",
    state_published_at_ms: 0,
    frontend_seen_revision: 0,
    scene_stage: "EMPTY",
    scene_draft_path: "",
    marker_catalog: {
      schema: "hmb-marker-catalog",
      version: 4,
      character: FALLBACK_MARKER_OPTIONS.slice(0, 7).map((name) => ({ name })),
      background: FALLBACK_MARKER_OPTIONS.slice(7).map((name) => ({ name })),
      options: [...FALLBACK_MARKER_OPTIONS],
    },
    marker_catalog_version: 4,
    scene_request_path: "",
    mode: "maya",
    status: "READY",
    message: "Browse to a Maya scene, then press READ.",
    video_path: "",
    video_url: "",
    original_video_path: "",
    original_video_url: "",
    original_enabled: false,
    mask_enabled: true,
    original_preview_enabled: false,
    depth_enabled: false,
    motion_guide_enabled: false,
    depth_video_slot: 0,
    motion_guide_video_slot: 0,
    snapshot_active: false,
    snapshot_frame: 0,
    snapshot_video_slot: 0,
    snapshot_data_uri: "",
    snapshot_path: "",
    snapshot_url: "",
    snapshot_sha256: "",
    snapshots: [],
    active_snapshot_uid: "",
    viewport_mode: "video",
    scene_path: "",
    native_read_ready: false,
    native_read_mode: "",
    native_source_version: "",
    native_metadata: {},
    camera: "",
    selected_camera: "",
    source_fps: 0,
    output_fps: 24,
    output_width: 1280,
    output_height: 720,
    source_frame_count: 0,
    output_frame_count: 0,
    decoded_frame_count: 0,
    source_duration_seconds: 0,
    output_duration_seconds: 0,
    frame_metadata: {},
    start_frame: 0,
    end_frame: 0,
    current_frame: 0,
    has_maya_frame_range: false,
    markers: [],
    warnings: [],
    activity_log: [],
    activity_log_text: "",
    activity_log_text_user_edited: false,
    activity_log_cleared: false,
    maya_executable: "",
    maya_version: "",
    maya_available: false,
    active_process_pid: 0,
    active_process_kind: "",
    last_log_path: "",
    log_folder: "",
    operation_kind: "",
    operation_video_slot: 0,
    operation_started_at_ms: 0,
    operation_finished_at_ms: 0,
    last_operation_seconds: 0,
    run_id: "",
    selected_video_slot: 1,
    active_slot_count: 1,
    preview_video_uid: "",
    selected_video_uid: "",
    selected_video_path: "",
    video_library_version: 1,
    max_selected_videos: HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS,
    pending_action: "",
    pending_action_id: "",
    backend_ack_action_id: "",
    runtime_instance_id: "",
    node_width: 0,
    node_height: 0,
    outliner_panel_height: 0,
    viewport_panel_height: 0,
    right_section_heights: { ...HMB_RIGHT_SECTION_DEFAULT_HEIGHTS },
    ui_layout_version: 6,
    ui_theme: "P",
    selected_outliner_path: "",
    selected_outliner_name: "",
    selected_outliner_uuid: "",
    selected_color: "",
    outliner_nodes: [],
    outliner_expanded: [],
    outliner_search: "",
    cameras: [],
    videos: [],
    slot_assignments: [{ video_slot: 1, bindings: [] }],
    slot_visibility: [{ video_slot: 1, hidden_paths: [] }],
    shot_publisher_instance_uuid: "",
    channel_uuid: "",
    shot_uuid: "",
    shot_number: 0,
    shot_name: "",
    shot_selections: [],
    picker_shots: [],
    active_picker_shot_uuid: "",
    language: "ko",
  };
}

function normalizeMarker(item, fallbackSlot = 1, order = 1) {
  if (!item || typeof item !== "object") return null;
  const color = clean(item.color);
  const assetId = clean(item.asset_id);
  if (!color || !assetId) return null;
  return {
    color,
    asset_id: assetId,
    subject_root: clean(item.subject_root || item.full_dag_path),
    group_name: clean(item.group_name) || assetId,
    full_dag_path: clean(item.full_dag_path || item.subject_root),
    maya_uuid: clean(item.maya_uuid),
    reference_node: clean(item.reference_node),
    reference_file: clean(item.reference_file),
    proxy_manager: clean(item.proxy_manager),
    proxy_tag: clean(item.proxy_tag),
    video_slot: clamp(item.video_slot || fallbackSlot, 1, HMB_PICKER_MAX_SELECTED_VIDEOS),
    picker_order: Math.max(1, Number(item.picker_order || order)),
  };
}

function normalizeBinding(item, fallbackSlot = 1, order = 1) {
  if (!item || typeof item !== "object") return null;
  const fullPath = clean(item.full_dag_path || item.subject_root);
  const groupName = clean(item.group_name || item.display_name || fullPath.split("|").pop());
  return {
    group_name: groupName,
    full_dag_path: fullPath,
    maya_uuid: clean(item.maya_uuid),
    reference_node: clean(item.reference_node),
    reference_file: clean(item.reference_file),
    proxy_manager: clean(item.proxy_manager),
    proxy_tag: clean(item.proxy_tag),
    color: clean(item.color),
    enabled: item.enabled !== false,
    video_slot: clamp(item.video_slot || fallbackSlot, 1, HMB_PICKER_MAX_SELECTED_VIDEOS),
    picker_order: Math.max(1, Number(item.picker_order || order)),
  };
}

function hmbPickerBindingIdentity(item) {
  const mayaUuid = clean(item?.maya_uuid).toLowerCase();
  if (mayaUuid) return `uuid:${mayaUuid}`;
  const fullPath = clean(item?.full_dag_path || item?.subject_root)
    .replace(/\\/g, "/")
    .toLowerCase();
  return fullPath ? `path:${fullPath}` : "";
}

function hmbDedupePickerBindings(items, fallbackSlot = 1) {
  const seen = new Set();
  const result = [];
  (Array.isArray(items) ? items : []).forEach((item, index) => {
    const binding = normalizeBinding(item, fallbackSlot, index + 1);
    if (!binding) return;
    const identity = hmbPickerBindingIdentity(binding);
    if (identity && seen.has(identity)) return;
    if (identity) seen.add(identity);
    result.push({
      ...binding,
      video_slot: fallbackSlot,
      picker_order: result.length + 1,
    });
  });
  return result;
}

function normalizeVideo(item, catalogIndex = 0) {
  if (!item || typeof item !== "object") return null;
  const rawSlot = Math.floor(Number(item.video_slot || item.selection_order || 0));
  const slot = rawSlot > 0
    ? clamp(rawSlot, 1, HMB_PICKER_MAX_SELECTED_VIDEOS)
    : 0;
  const normalized = {
    ...item,
    video_slot: slot,
    video_path: clean(item.video_path),
    video_url: clean(item.video_url),
    camera: clean(item.camera),
    markers: Array.isArray(item.markers) ? item.markers.map((marker, index) => normalizeMarker(marker, slot || 1, index + 1)).filter(Boolean) : [],
  };
  normalized.video_uid = hmbVideoAssetUid(item, catalogIndex);
  const explicitSelection = Object.prototype.hasOwnProperty.call(item, "selected")
    || Object.prototype.hasOwnProperty.call(item, "selection_order");
  if (explicitSelection) {
    const selectionOrder = Math.max(0, Math.floor(Number(item.selection_order || 0)));
    normalized.selected = Object.prototype.hasOwnProperty.call(item, "selected")
      ? item.selected === true
      : selectionOrder > 0;
    normalized.selection_order = selectionOrder;
  } else {
    delete normalized.selected;
    delete normalized.selection_order;
  }
  normalized.created_at_ms = Math.max(0, Math.floor(Number(item.created_at_ms || item.created_at || 0)));
  normalized.source_fps = Math.max(0, Number(item.source_fps || 0));
  normalized.output_fps = Math.max(0, Number(item.output_fps || 0));
  normalized.source_frame_count = Math.max(0, Math.round(Number(item.source_frame_count || 0)));
  normalized.output_frame_count = Math.max(0, Math.round(Number(item.output_frame_count || 0)));
  normalized.decoded_frame_count = Math.max(0, Math.round(Number(item.decoded_frame_count || item.output_frame_count || item.source_frame_count || 0)));
  normalized.source_duration_seconds = Math.max(0, Number(item.source_duration_seconds || 0));
  normalized.output_duration_seconds = Math.max(0, Number(item.output_duration_seconds || 0));
  normalized.start_frame = Number(item.start_frame || 0);
  normalized.end_frame = Number(item.end_frame || 0);
  normalized.has_maya_frame_range = Boolean(item.has_maya_frame_range);
  const metadataSource = item.frame_metadata
    && typeof item.frame_metadata === "object"
    && Object.keys(item.frame_metadata).length
    ? item.frame_metadata
    : item;
  normalized.frame_metadata = {
    ...normalizeVideoFrameMetadata(metadataSource, slot || 1),
    video_slot: `@video${slot || 1}`,
  };
  return normalized;
}

function normalizeVideoFrameMetadata(value, fallbackSlot = 1) {
  const raw = value && typeof value === "object" ? value : {};
  const resolution = raw.resolution && typeof raw.resolution === "object"
    ? raw.resolution
    : {};
  const slotMatch = clean(raw.video_slot).match(/(\d+)/);
  const slot = clamp(slotMatch ? Number(slotMatch[1]) : fallbackSlot, 1, HMB_PICKER_MAX_SELECTED_VIDEOS);
  const fps = Math.max(0, Number(raw.fps || raw.source_fps || raw.output_fps || 0));
  const frameCount = Math.max(0, Math.round(Number(
    raw.frame_count
    || raw.decoded_frame_count
    || raw.output_frame_count
    || raw.source_frame_count
    || 0
  )));
  const explicitMayaRange = raw.has_maya_frame_range
    || raw.maya_start_frame != null
    || raw.maya_end_frame != null
    || (
      raw.start_frame != null
      && raw.end_frame != null
      && (Number(raw.start_frame) !== 0 || Number(raw.end_frame) !== 0)
    );
  const startFrame = Number.isFinite(Number(raw.start_frame))
    ? Math.round(Number(raw.start_frame))
    : 1;
  const rawEnd = Number(raw.end_frame);
  const endFrame = Number.isFinite(rawEnd) && (explicitMayaRange || rawEnd >= startFrame)
    ? Math.round(rawEnd)
    : frameCount > 0
      ? startFrame + frameCount - 1
      : startFrame - 1;
  const rangeCount = endFrame >= startFrame ? endFrame - startFrame + 1 : 0;
  const conflict = Boolean(raw.conflict)
    || (frameCount > 0 && rangeCount > 0 && frameCount !== rangeCount);
  const structurallyValid = fps > 0 && frameCount > 0 && endFrame >= startFrame;
  const width = Math.max(0, Math.round(Number(
    raw.width || raw.output_width || raw.source_width || resolution.width || 0
  )));
  const height = Math.max(0, Math.round(Number(
    raw.height || raw.output_height || raw.source_height || resolution.height || 0
  )));
  return {
    video_slot: `@video${slot}`,
    fps,
    start_frame: startFrame,
    end_frame: endFrame,
    frame_count: frameCount,
    duration_seconds: Math.max(0, Number(raw.duration_seconds || raw.source_duration_seconds || raw.output_duration_seconds || (fps > 0 ? frameCount / fps : 0))),
    timebase: clean(raw.timebase),
    width,
    height,
    resolution: { width, height },
    available_color_picks: Array.from(new Set(
      (Array.isArray(raw.available_color_picks) ? raw.available_color_picks : [])
        .map(clean)
        .filter(Boolean),
    )),
    conflict,
    valid: raw.valid !== false && structurallyValid && !conflict,
    warnings: (Array.isArray(raw.warnings) ? raw.warnings : []).map(clean).filter(Boolean),
  };
}

export function formatFrameTimecode(frame, startFrame, fpsValue) {
  const fps = Math.max(0.000001, Number(fpsValue || 0));
  const nominalFps = Math.max(1, Math.round(fps));
  const elapsedFrames = Math.max(0, Math.round(Number(frame) - Number(startFrame)));
  const frames = elapsedFrames % nominalFps;
  const totalSeconds = Math.floor(elapsedFrames / nominalFps);
  const seconds = totalSeconds % 60;
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = totalMinutes % 60;
  const hours = Math.floor(totalMinutes / 60);
  return [hours, minutes, seconds, frames].map((value) => String(value).padStart(2, "0")).join(":");
}

function normalizeAssignments(value, activeCount, videos) {
  const bySlot = new Map();
  if (Array.isArray(value)) {
    value.forEach((entry) => {
      if (!entry || typeof entry !== "object") return;
      const slot = clamp(entry.video_slot || 1, 1, activeCount);
      const bindings = hmbDedupePickerBindings(entry.bindings, slot);
      bySlot.set(slot, bindings);
    });
  }
  (Array.isArray(videos) ? videos : []).forEach((video) => {
    const slot = clamp(video?.video_slot || 1, 1, activeCount);
    if (bySlot.has(slot) && bySlot.get(slot)?.length) return;
    const inferred = Array.isArray(video?.markers)
      ? video.markers.map((marker, index) => normalizeBinding({
          group_name: marker.group_name || marker.asset_id,
          full_dag_path: marker.full_dag_path || marker.subject_root,
          maya_uuid: marker.maya_uuid,
          reference_node: marker.reference_node,
          reference_file: marker.reference_file,
          proxy_manager: marker.proxy_manager,
          proxy_tag: marker.proxy_tag,
          color: marker.color,
        }, slot, index + 1)).filter(Boolean)
      : [];
    bySlot.set(slot, inferred);
  });
  return Array.from({ length: activeCount }, (_, index) => ({ video_slot: index + 1, bindings: bySlot.get(index + 1) || [] }));
}

function normalize(value) {
  let source = {};
  if (value && typeof value === "object") source = value;
  else if (typeof value === "string") {
    try { source = JSON.parse(value); } catch (_error) {}
  }
  const state = { ...defaultState(), ...(source && typeof source === "object" ? source : {}) };
  const rawCatalog = state.marker_catalog && typeof state.marker_catalog === "object" ? state.marker_catalog : {};
  const catalogRows = [
    ...(Array.isArray(rawCatalog.character) ? rawCatalog.character : []),
    ...(Array.isArray(rawCatalog.background) ? rawCatalog.background : []),
  ];
  const catalogOptions = catalogRows.map((item) => clean(item?.name)).filter(Boolean);
  state.marker_catalog = {
    schema: "hmb-marker-catalog",
    version: Number(rawCatalog.version || state.marker_catalog_version || 3),
    character: Array.isArray(rawCatalog.character) ? rawCatalog.character : [],
    background: Array.isArray(rawCatalog.background) ? rawCatalog.background : [],
    options: catalogOptions.length === 14 ? catalogOptions : [...FALLBACK_MARKER_OPTIONS],
  };
  state.marker_catalog_version = Number(state.marker_catalog.version || 3);
  state.state_revision = Math.max(0, Math.floor(Number(state.state_revision || 0)));
  state.state_writer = clean(state.state_writer);
  state.state_published_at_ms = Math.max(0, Math.floor(Number(state.state_published_at_ms || 0)));
  state.frontend_seen_revision = Math.max(0, Math.floor(Number(state.frontend_seen_revision || 0)));
  ["scene_stage", "scene_draft_path", "scene_request_path"].forEach((key) => { state[key] = clean(state[key]); });
  state.active_slot_count = clamp(state.active_slot_count || 1, 1, HMB_PICKER_MAX_SELECTED_VIDEOS);
  state.selected_video_slot = clamp(state.selected_video_slot || 1, 1, state.active_slot_count);
  state.pending_action = clean(state.pending_action);
  state.pending_action_id = clean(state.pending_action_id);
  state.backend_ack_action_id = clean(state.backend_ack_action_id);
  state.runtime_instance_id = clean(state.runtime_instance_id);
  state.maya_executable = clean(state.maya_executable);
  state.maya_version = clean(state.maya_version);
  state.maya_available = Boolean(state.maya_available && state.maya_executable);
  state.active_process_pid = Math.max(0, Math.floor(Number(state.active_process_pid || 0)));
  state.active_process_kind = clean(state.active_process_kind);
  const requestedResolution = HMB_PLAYBLAST_RESOLUTIONS.find(
    (item) => item.width === Number(state.output_width) && item.height === Number(state.output_height),
  ) || HMB_PLAYBLAST_RESOLUTIONS[0];
  state.output_width = requestedResolution.width;
  state.output_height = requestedResolution.height;
  state.node_width = Number(state.node_width || 0) > 0 ? clamp(Math.round(Number(state.node_width)), HMB_MIN_NODE_WIDTH, 6000) : 0;
  state.node_height = Number(state.node_height || 0) > 0 ? clamp(Math.round(Number(state.node_height)), HMB_MIN_NODE_HEIGHT, 6000) : 0;
  state.outliner_panel_height = Number(state.outliner_panel_height || 0) > 0
    ? clamp(Math.round(Number(state.outliner_panel_height)), HMB_PICKER_OUTLINER_PANEL_MIN_HEIGHT, 6000)
    : 0;
  state.viewport_panel_height = Number(state.viewport_panel_height || 0) > 0
    ? clamp(Math.round(Number(state.viewport_panel_height)), HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT, 6000)
    : 0;
  const sourceLayoutVersion = Math.max(1, Math.floor(Number(source?.ui_layout_version || 1)));
  // v3 repairs outer heights saved by the former Picker height propagation.
  // Internal panel sizes remain untouched; only the stale React Flow height is
  // released once so the measured bottom-edge alignment can take over.
  if (sourceLayoutVersion < 4) state.node_height = 0;
  if (sourceLayoutVersion < 2) {
    const legacyHeights = source?.right_section_heights && typeof source.right_section_heights === "object"
      ? source.right_section_heights
      : {};
    const legacySettings = clamp(Math.round(Number(legacyHeights.settings || 190)), 96, 900);
    const legacyColor = clamp(Math.round(Number(legacyHeights.color || 412)), 96, 900);
    const legacyLog = clamp(Math.round(Number(legacyHeights.log || 208)), 96, 900);
    state.right_section_heights = hmbNormalizeRightSectionHeights({
      settings: legacySettings,
      color: legacyColor + legacyLog + 8,
      log: legacyLog,
    });
    const legacyViewportHeight = Number(source?.viewport_panel_height || 0);
    if (legacyViewportHeight > 0) {
      state.viewport_panel_height = clamp(
        Math.round(legacyViewportHeight - legacyLog - 8),
        HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT,
        6000,
      );
    }
  } else {
    state.right_section_heights = hmbNormalizeRightSectionHeights(state.right_section_heights);
  }
  if (sourceLayoutVersion === 5) {
    state.right_section_heights.settings = clamp(
      Number(state.right_section_heights.settings || 285) - 68,
      96,
      900,
    );
  }
  state.ui_layout_version = 6;
  // P is now the only base design. Shot routing owns the accent palette.
  state.ui_theme = "P";
  state.selected_outliner_path = clean(state.selected_outliner_path);
  state.selected_outliner_name = clean(state.selected_outliner_name);
  state.selected_outliner_uuid = clean(state.selected_outliner_uuid);
  state.selected_color = clean(state.selected_color);
  if (state.selected_color && !state.marker_catalog.options.includes(state.selected_color)) state.selected_color = "";
  state.selected_camera = clean(state.selected_camera);
  state.video_url = clean(state.video_url);
  state.original_video_path = clean(state.original_video_path);
  state.original_video_url = clean(state.original_video_url);
  state.original_enabled = !!state.original_enabled;
  state.mask_enabled = state.mask_enabled !== false;
  state.original_preview_enabled = !!state.original_preview_enabled;
  state.depth_enabled = !!state.depth_enabled;
  state.motion_guide_enabled = !!state.motion_guide_enabled;
  for (const key of ["depth_video_slot", "motion_guide_video_slot"]) {
    const typedSlot = Math.floor(Number(state[key] || 0));
    state[key] = typedSlot >= 2 && typedSlot <= HMB_PICKER_MAX_SELECTED_VIDEOS ? typedSlot : 0;
  }
  state.snapshot_active = !!state.snapshot_active;
  state.snapshot_frame = Number.isFinite(Number(state.snapshot_frame))
    ? Number(state.snapshot_frame)
    : Number(state.current_frame || 0);
  state.snapshot_video_slot = clamp(
    Math.floor(Number(state.snapshot_video_slot || 0)),
    0,
    state.active_slot_count,
  );
  state.snapshot_data_uri = "";
  state.snapshot_path = clean(state.snapshot_path);
  state.snapshot_url = clean(state.snapshot_url).startsWith("data:") ? "" : clean(state.snapshot_url);
  state.snapshot_sha256 = /^[0-9a-f]{64}$/i.test(clean(state.snapshot_sha256))
    ? clean(state.snapshot_sha256).toLowerCase()
    : "";
  const snapshotByUid = new Map();
  const rawSnapshots = Array.isArray(state.snapshots) ? state.snapshots : [];
  rawSnapshots.forEach((raw, snapshotIndex) => {
    if (!raw || typeof raw !== "object") return;
    const path = clean(raw?.path || raw?.snapshot_path);
    const url = clean(raw?.url || raw?.media_url || raw?.snapshot_url);
    if (!path && (!url || url.startsWith("data:"))) return;
    const snapshotUid = hmbSnapshotUid(raw, snapshotIndex);
    if (snapshotByUid.has(snapshotUid)) return;
    const renderVideoSlot = clamp(
      Math.floor(Number(raw?.render_video_slot || raw?.video_slot || 1)),
      1,
      HMB_PICKER_MAX_SELECTED_VIDEOS,
    );
    snapshotByUid.set(snapshotUid, {
      snapshot_uid: snapshotUid,
      video_uid: clean(raw?.video_uid),
      render_video_slot: renderVideoSlot,
      video_slot: renderVideoSlot,
      frame: Number(raw?.frame || raw?.snapshot_frame || 0),
      path,
      url: url.startsWith("data:") ? "" : url,
      sha256: /^[0-9a-f]{64}$/i.test(clean(raw?.sha256 || raw?.content_sha256))
        ? clean(raw?.sha256 || raw?.content_sha256).toLowerCase()
        : "",
      created_at_ms: Math.max(0, Number(raw?.created_at_ms || raw?.created_at || 0)),
    });
  });
  if (state.snapshot_active && state.snapshot_video_slot && (state.snapshot_path || state.snapshot_url)) {
    const matchingSnapshot = Array.from(snapshotByUid.values()).find((item) => (
      clean(item.path) === state.snapshot_path
      && Number(item.frame || 0) === Number(state.snapshot_frame || 0)
    ));
    const snapshotUid = clean(state.active_snapshot_uid)
      || clean(matchingSnapshot?.snapshot_uid)
      || hmbSnapshotUid({
        video_uid: clean(state.preview_video_uid || state.selected_video_uid),
        video_slot: state.snapshot_video_slot,
        frame: state.snapshot_frame,
        path: state.snapshot_path,
        url: state.snapshot_url,
        sha256: state.snapshot_sha256,
      }, rawSnapshots.length);
    snapshotByUid.set(snapshotUid, {
      snapshot_uid: snapshotUid,
      video_uid: clean(matchingSnapshot?.video_uid || state.preview_video_uid || state.selected_video_uid),
      render_video_slot: state.snapshot_video_slot,
      video_slot: state.snapshot_video_slot,
      frame: state.snapshot_frame,
      path: state.snapshot_path,
      url: state.snapshot_url,
      sha256: state.snapshot_sha256,
      created_at_ms: Math.max(0, Number(matchingSnapshot?.created_at_ms || state.operation_finished_at_ms || 0)),
    });
  }
  state.snapshots = Array.from(snapshotByUid.values()).sort((left, right) => (
    Number(left.created_at_ms || 0) - Number(right.created_at_ms || 0)
    || clean(left.snapshot_uid).localeCompare(clean(right.snapshot_uid))
  )).slice(-HMB_PICKER_MAX_SNAPSHOTS);
  const retainedSnapshotByUid = new Map(
    state.snapshots.map((item) => [clean(item.snapshot_uid), item]),
  );
  let activeSnapshotUid = clean(state.active_snapshot_uid);
  if (!retainedSnapshotByUid.has(activeSnapshotUid) && state.snapshot_active) {
    const compatibilitySnapshot = state.snapshots.find((item) => (
      clean(item.path) === state.snapshot_path
      && Number(item.frame || 0) === Number(state.snapshot_frame || 0)
    ));
    activeSnapshotUid = clean(compatibilitySnapshot?.snapshot_uid);
  }
  const requestedViewportMode = clean(source?.viewport_mode).toLowerCase();
  let viewportMode = ["snapshot", "video"].includes(requestedViewportMode)
    ? requestedViewportMode
    : (state.snapshot_active && activeSnapshotUid ? "snapshot" : "video");
  if (viewportMode === "snapshot" && !retainedSnapshotByUid.has(activeSnapshotUid)) {
    activeSnapshotUid = clean(state.snapshots.at(-1)?.snapshot_uid);
  }
  const activeSnapshot = retainedSnapshotByUid.get(activeSnapshotUid) || null;
  if (activeSnapshot) {
    state.snapshot_active = viewportMode === "snapshot";
    state.active_snapshot_uid = activeSnapshotUid;
    state.snapshot_frame = Number(activeSnapshot.frame || 0);
    state.snapshot_video_slot = Number(activeSnapshot.render_video_slot || activeSnapshot.video_slot || 1);
    state.snapshot_data_uri = "";
    state.snapshot_path = clean(activeSnapshot.path);
    state.snapshot_url = clean(activeSnapshot.url);
    state.snapshot_sha256 = clean(activeSnapshot.sha256);
  } else {
    state.snapshot_active = false;
    state.active_snapshot_uid = "";
    state.snapshot_video_slot = 0;
    state.snapshot_data_uri = "";
    state.snapshot_path = "";
    state.snapshot_url = "";
    state.snapshot_sha256 = "";
    viewportMode = "video";
  }
  state.viewport_mode = viewportMode;
  state.native_read_ready = !!state.native_read_ready;
  state.native_read_mode = clean(state.native_read_mode);
  state.native_source_version = clean(state.native_source_version);
  state.native_metadata = state.native_metadata && typeof state.native_metadata === "object" ? { ...state.native_metadata } : {};
  state.outliner_search = clean(state.outliner_search);
  state.language = clean(state.language).toLowerCase() === "en" ? "en" : "ko";
  state.outliner_nodes = Array.isArray(state.outliner_nodes) ? state.outliner_nodes.filter((item) => item && typeof item === "object") : [];
  state.outliner_expanded = Array.isArray(state.outliner_expanded) ? state.outliner_expanded.map(clean).filter(Boolean) : [];
  state.cameras = Array.isArray(state.cameras) ? state.cameras.filter((item) => item && typeof item === "object") : [];
  state.videos = Array.isArray(state.videos)
    ? state.videos.map((item, index) => normalizeVideo(item, index)).filter(Boolean)
    : [];
  const catalogHasExplicitSelection = state.videos.some((item) => (
    Object.prototype.hasOwnProperty.call(item || {}, "selected")
    || Object.prototype.hasOwnProperty.call(item || {}, "selection_order")
  ));
  // A local interaction may update the active catalog projection immediately
  // before its workspace row is echoed back.  Preserve that live draft when
  // explicit catalog flags exist; otherwise the workspace row is authoritative.
  const selectedVideoUids = hmbSelectedVideoAssets(
    catalogHasExplicitSelection ? { videos: state.videos } : state,
  ).map((item) => clean(item.video_uid));
  Object.assign(
    state,
    hmbApplyVideoAssetSelection(
      state,
      selectedVideoUids,
      clean(state.preview_video_uid || state.selected_video_uid),
    ),
  );
  hmbNormalizePickerShotRows(state);
  hmbNormalizePickerWorkspaceRows(state);
  state.slot_assignments = normalizeAssignments(state.slot_assignments, state.active_slot_count, state.videos);
  const visibilityBySlot = new Map();
  for (const raw of Array.isArray(state.slot_visibility) ? state.slot_visibility : []) {
    const slot = clamp(Math.floor(Number(raw?.video_slot || 1)), 1, state.active_slot_count);
    const hiddenPaths = Array.isArray(raw?.hidden_paths) ? raw.hidden_paths.map(clean).filter(Boolean) : [];
    visibilityBySlot.set(slot, Array.from(new Set(hiddenPaths)));
  }
  state.slot_visibility = Array.from({ length: state.active_slot_count }, (_item, index) => ({
    video_slot: index + 1,
    hidden_paths: visibilityBySlot.get(index + 1) || [],
  }));
  state.markers = Array.isArray(state.markers) ? state.markers.map((marker, index) => normalizeMarker(marker, state.selected_video_slot, index + 1)).filter(Boolean) : [];
  state.warnings = Array.isArray(state.warnings) ? state.warnings.map(clean).filter(Boolean) : [];
  state.activity_log = normalizeActivityLog(state.activity_log);
  state.activity_log_text = String(state.activity_log_text == null ? "" : state.activity_log_text).slice(-32000);
  state.activity_log_text_user_edited = !!state.activity_log_text_user_edited;
  state.activity_log_cleared = !!state.activity_log_cleared;
  ["maya_executable", "maya_version", "last_log_path", "log_folder", "operation_kind"].forEach((key) => { state[key] = clean(state[key]); });
  state.operation_video_slot = clamp(
    Math.floor(Number(state.operation_video_slot || 0)),
    0,
    HMB_PICKER_MAX_SELECTED_VIDEOS,
  );
  state.operation_started_at_ms = Math.max(0, Number(state.operation_started_at_ms || 0));
  state.operation_finished_at_ms = Math.max(0, Number(state.operation_finished_at_ms || 0));
  state.last_operation_seconds = Math.max(0, Number(state.last_operation_seconds || 0));
  return state;
}

function hmbPickerStateFromProps(props) {
  if (!props || typeof props !== "object") return {};
  return props.value ?? props.parameterValue ?? props.defaultValue;
}

function hmbPickerStateEchoValue(value) {
  const comparable = normalize(value);
  // Griptape's before_value_set merge legitimately rewrites transport-only
  // ownership metadata on an otherwise identical widget echo. Those fields do
  // not change visible or persisted picker content; every functional backend
  // field (status, message, ack, progress, log, media, etc.) remains part of
  // this exact signature and therefore still forces an authoritative update.
  comparable.state_writer = "";
  comparable.frontend_seen_revision = 0;
  return JSON.stringify(comparable);
}

export function hmbReleasePickerWorkspacePublication(container, generation) {
  if (!container) return false;
  const ownedGeneration = Number(generation || 0);
  if (
    !ownedGeneration
    || Number(container.__hmbPickerWorkspacePublicationGeneration || 0) !== ownedGeneration
  ) return false;
  if (container.__hmbPickerWorkspacePublicationUnlockTimer) {
    try { clearTimeout(container.__hmbPickerWorkspacePublicationUnlockTimer); } catch (_error) {}
  }
  delete container.__hmbPickerWorkspacePublicationUnlockTimer;
  delete container.__hmbPickerWorkspacePublicationPending;
  delete container.__hmbPickerWorkspacePublicationEchoValue;
  delete container.__hmbPickerWorkspacePublicationUnlock;
  return true;
}

export function hmbBeginPickerWorkspacePublication(container, value, onUnlock = null) {
  if (!container) return 0;
  if (container.__hmbPickerWorkspacePublicationUnlockTimer) {
    try { clearTimeout(container.__hmbPickerWorkspacePublicationUnlockTimer); } catch (_error) {}
  }
  const generation = Number(container.__hmbPickerWorkspacePublicationGeneration || 0) + 1;
  container.__hmbPickerWorkspacePublicationGeneration = generation;
  container.__hmbPickerWorkspacePublicationPending = true;
  container.__hmbPickerWorkspacePublicationEchoValue = hmbPickerStateEchoValue(value);
  container.__hmbPickerWorkspacePublicationUnlock = typeof onUnlock === "function" ? onUnlock : null;
  container.__hmbPickerWorkspacePublicationUnlockTimer = setTimeout(() => {
    const callback = container.__hmbPickerWorkspacePublicationUnlock;
    if (!hmbReleasePickerWorkspacePublication(container, generation)) return;
    if (container.__hmbVideoPickerDeleted !== true && typeof callback === "function") callback(generation);
  }, HMB_PICKER_WORKSPACE_ECHO_TIMEOUT_MS);
  return generation;
}

export function hmbPickerWorkspacePublicationMatchesEcho(container, value) {
  const expected = container?.__hmbPickerWorkspacePublicationEchoValue;
  if (!expected || container?.__hmbPickerWorkspacePublicationPending !== true) return false;
  try { return expected === hmbPickerStateEchoValue(value); } catch (_error) { return false; }
}

export function hmbClearPendingPickerStateEcho(container) {
  if (!container) return;
  if (container.__hmbPendingPickerStateEchoTimer) {
    try { clearTimeout(container.__hmbPendingPickerStateEchoTimer); } catch (_error) {}
  }
  delete container.__hmbPendingPickerStateEchoes;
  delete container.__hmbPendingPickerStateEchoTimer;
}

export function hmbDeliverPickerStateIfMounted(container, onChange, value) {
  if (!container || container.__hmbVideoPickerDeleted === true) {
    return { delivered: false, result: undefined };
  }
  if (typeof onChange !== "function") {
    return { delivered: false, result: undefined };
  }
  return { delivered: true, result: onChange(value) };
}

export function hmbPickerStatePublicationIdentity(value) {
  const source = value && typeof value === "object" ? value : {};
  return [
    clean(source.runtime_instance_id),
    Number(source.state_revision || 0),
    Number(source.state_published_at_ms || 0),
    clean(source.state_writer),
  ].join("\u0000");
}

export function hmbPendingPickerStateOwnedBy(container, value) {
  const pending = container?.__hmbPendingPickerState;
  if (!pending || typeof pending !== "object") return false;
  return hmbPickerStatePublicationIdentity(pending) === hmbPickerStatePublicationIdentity(value);
}

export function hmbPickerStateRollbackFallback(container, failedState) {
  const rollback = container?.__hmbLastPickerStateRollback;
  if (
    !rollback
    || rollback.failed_identity !== hmbPickerStatePublicationIdentity(failedState)
    || !rollback.state
    || typeof rollback.state !== "object"
  ) return null;
  return normalize(rollback.state);
}

export function hmbRollbackFailedPickerStatePublication(
  container,
  failedState,
  previousPendingState = null,
  previousAuthoritativeState = null,
) {
  if (!container) return false;
  const failedIdentity = hmbPickerStatePublicationIdentity(failedState);
  if (!(container.__hmbFailedPickerStatePublications instanceof Set)) {
    container.__hmbFailedPickerStatePublications = new Set();
  }
  // A failed predecessor remains invalid even when a newer publication owns
  // the optimistic state by the time its Promise rejects. Record every
  // failure before the ownership check so a later rollback can walk past it.
  container.__hmbFailedPickerStatePublications.add(failedIdentity);
  while (container.__hmbFailedPickerStatePublications.size > 64) {
    const oldestIdentity = container.__hmbFailedPickerStatePublications.values().next().value;
    container.__hmbFailedPickerStatePublications.delete(oldestIdentity);
  }
  delete container.__hmbLastPickerStateRollback;
  if (!hmbPendingPickerStateOwnedBy(container, failedState)) return false;
  const nearestValidPredecessor = (candidate) => {
    let current = candidate && typeof candidate === "object" ? normalize(candidate) : null;
    const seen = new Set();
    while (current) {
      const identity = hmbPickerStatePublicationIdentity(current);
      if (!identity || seen.has(identity)) return null;
      seen.add(identity);
      if (!container.__hmbFailedPickerStatePublications.has(identity)) return current;
      current = container.__hmbPickerStatePublicationPredecessors?.get?.(identity) || null;
    }
    return null;
  };
  const authoritative = container.__hmbAuthoritativePickerState;
  const authoritativeStillOwnsFailure = (
    authoritative
    && hmbPickerStatePublicationIdentity(authoritative) === failedIdentity
    && hmbPickerStateEchoValue(authoritative) === hmbPickerStateEchoValue(failedState)
  );
  const pendingFallback = nearestValidPredecessor(previousPendingState);
  if (!authoritativeStillOwnsFailure && authoritative && typeof authoritative === "object") {
    // A newer backend authority supersedes the failed optimistic publication.
    // Reveal that authority instead of resurrecting an older predecessor.
    container.__hmbPendingPickerState = normalize(authoritative);
  } else if (pendingFallback) {
    container.__hmbPendingPickerState = pendingFallback;
  } else {
    delete container.__hmbPendingPickerState;
  }
  if (authoritativeStillOwnsFailure) {
    const authoritativeFallback = nearestValidPredecessor(previousAuthoritativeState);
    if (authoritativeFallback) {
      container.__hmbAuthoritativePickerState = authoritativeFallback;
    } else {
      delete container.__hmbAuthoritativePickerState;
    }
  }
  const resolvedFallback = (
    container.__hmbAuthoritativePickerState
    && typeof container.__hmbAuthoritativePickerState === "object"
  )
    ? normalize(container.__hmbAuthoritativePickerState)
    : (
      container.__hmbPendingPickerState
      && typeof container.__hmbPendingPickerState === "object"
        ? normalize(container.__hmbPendingPickerState)
        : null
    );
  container.__hmbLastPickerStateRollback = {
    failed_identity: failedIdentity,
    state: resolvedFallback,
    visible_error_owned: authoritativeStillOwnsFailure,
  };
  hmbClearPendingPickerStateEcho(container);
  return true;
}

export function hmbRememberPendingPickerStateEcho(container, value, props = {}) {
  if (!container) return;
  const normalized = normalize(value);
  const pending = {
    value: hmbPickerStateEchoValue(normalized),
    disabled: Boolean(props && props.disabled),
    revision: Number(normalized.state_revision || 0),
    publishedAtMs: Number(normalized.state_published_at_ms || 0),
  };
  const prior = Array.isArray(container.__hmbPendingPickerStateEchoes)
    ? container.__hmbPendingPickerStateEchoes
    : [];
  const queue = prior.filter((item) => (
    item
    && (
      item.value !== pending.value
      || item.disabled !== pending.disabled
    )
  ));
  queue.push(pending);
  container.__hmbPendingPickerStateEchoes = queue.slice(-16);
  if (container.__hmbPendingPickerStateEchoTimer) {
    try { clearTimeout(container.__hmbPendingPickerStateEchoTimer); } catch (_error) {}
  }
  container.__hmbPendingPickerStateEchoTimer = setTimeout(() => {
    hmbClearPendingPickerStateEcho(container);
  }, HMB_PICKER_WORKSPACE_ECHO_TIMEOUT_MS);
}

export function hmbConsumePendingPickerStateEcho(container, nextProps = {}) {
  const pending = container && container.__hmbPendingPickerStateEchoes;
  if (!Array.isArray(pending) || !pending.length) return false;

  let incoming = null;
  let incomingValue = "";
  try {
    incoming = normalize(hmbPickerStateFromProps(nextProps));
    incomingValue = hmbPickerStateEchoValue(incoming);
  } catch (_error) {
    return false;
  }

  // Only the exact optimistic value emitted by this widget is disposable.
  // Python-owned responses, command acknowledgements, progress, and terminal
  // states change functional fields in the signature and must continue through
  // the authoritative update path. state_writer itself is transport metadata:
  // the Python merge can set it to "python" on a normal local echo.
  if (clean(incoming.pending_action) || clean(incoming.pending_action_id)) return false;

  const incomingDisabled = Boolean(nextProps && nextProps.disabled);
  const matchIndex = pending.findIndex((item) => (
    item
    && item.value === incomingValue
    && item.disabled === incomingDisabled
    && Number(item.revision || 0) === Number(incoming.state_revision || 0)
    && Number(item.publishedAtMs || 0) === Number(incoming.state_published_at_ms || 0)
  ));
  if (matchIndex < 0) return false;

  pending.splice(matchIndex, 1);
  if (!pending.length) {
    hmbClearPendingPickerStateEcho(container);
  }
  return true;
}

function selectedVideo(state, slot) {
  return hmbSelectedVideoAssets(state)[Math.max(0, Number(slot || 1) - 1)] || null;
}

function previewVideo(state) {
  const uid = clean(state?.preview_video_uid || state?.selected_video_uid);
  const source = Array.isArray(state?.videos) ? state.videos : [];
  const byUid = source.find((item, index) => hmbVideoAssetUid(item, index) === uid);
  return byUid || selectedVideo(state, state?.selected_video_slot || 1);
}

function selectedBindings(state, slot) {
  const item = state.slot_assignments.find((entry) => Number(entry.video_slot || 0) === slot);
  return item && Array.isArray(item.bindings)
    ? hmbDedupePickerBindings(item.bindings, slot)
    : [];
}

function selectedFrameMetadata(state, video, slot) {
  const nestedMetadata = video && video.frame_metadata && typeof video.frame_metadata === "object"
    && Object.keys(video.frame_metadata).length
    ? video.frame_metadata
    : video;
  const videoMetadata = normalizeVideoFrameMetadata(nestedMetadata, slot);
  if (videoMetadata.frame_count > 0 && videoMetadata.fps > 0) return videoMetadata;
  return normalizeVideoFrameMetadata({
    video_slot: slot,
    fps: state.source_fps || state.output_fps,
    start_frame: state.start_frame,
    end_frame: state.end_frame,
    frame_count: state.decoded_frame_count || state.output_frame_count || state.source_frame_count,
    duration_seconds: state.source_duration_seconds || state.output_duration_seconds,
    width: video?.output_width || state.output_width,
    height: video?.output_height || state.output_height,
    has_maya_frame_range: state.has_maya_frame_range || state.native_read_ready,
    available_color_picks: selectedBindings(state, slot).map((item) => item.color).filter(Boolean),
  }, slot);
}

function mayaScenePathKey(value) {
  return clean(value)
    .replace(/^["']|["']$/g, "")
    .replace(/\\/g, "/")
    .replace(/\/+/g, "/")
    .toLowerCase();
}

export function pickerButtonAvailability(
  rawState,
  draftPathValue = "",
  localReadPending = false,
  localOriginalPending = false,
) {
  const state = rawState && typeof rawState === "object" ? rawState : {};
  const status = clean(state.status).toUpperCase();
  const sceneStage = clean(state.scene_stage).toUpperCase();
  const operationKind = clean(state.operation_kind);
  const draftPath = clean(
    draftPathValue
    || state.scene_draft_path
    || state.scene_request_path
    || state.scene_path,
  ).replace(/^["']|["']$/g, "");
  const validFile = isMayaScenePath(draftPath);
  const mayaAvailable = Boolean(state.maya_available && clean(state.maya_executable));
  const terminalFailure = ["FAILED", "CANCELLED"].includes(status)
    || ["FAILED", "LOAD_FAILED", "CANCELLED", "STALE_RESULT_DISCARDED"].includes(sceneStage);
  const stopping = status === "CANCELLING" || sceneStage === "CANCELLING";
  const operationStartedAt = Math.max(0, Number(state.operation_started_at_ms || 0));
  const operationFinishedAt = Math.max(0, Number(state.operation_finished_at_ms || 0));
  const operationLifecycleOpen = ["read_scene", "render_original_preview", "run_video", "render_snapshot"]
    .includes(operationKind)
    && (
      Number(state.active_process_pid || 0) > 0
      || (operationStartedAt > 0 && operationFinishedAt < operationStartedAt)
    );
  const operationBusy = !terminalFailure && (
    stopping
    || !!localReadPending
    || !!localOriginalPending
    || ["READING_SCENE", "RUNNING", "GENERATING_VIDEO", "GENERATING_ORIGINAL", "SNAPSHOT_RENDERING"].includes(status)
    || ["MAYA_READING", "PYTHON_COMMAND_RECEIVED", "ORIGINAL_RENDERING", "SNAPSHOT_RENDERING"].includes(sceneStage)
    || operationLifecycleOpen
  );
  const completedScenePath = mayaScenePathKey(state.scene_path);
  const selectedScenePath = mayaScenePathKey(draftPath);
  const sceneChanged = validFile && (!completedScenePath || selectedScenePath !== completedScenePath);
  const readSnapshotReady = !!state.native_read_ready
    && ["OUTLINER_READY", "VIDEO_READY"].includes(sceneStage)
    && !sceneChanged;

  const outlinerReady = Array.isArray(state.outliner_nodes) && state.outliner_nodes.length > 0;
  const cameras = Array.isArray(state.cameras) ? state.cameras : [];
  const cameraReady = cameras.length > 0 && !!clean(state.selected_camera || state.camera);
  const frameStart = Number(state.start_frame);
  const frameEnd = Number(state.end_frame);
  const frameRangeReady = Number.isFinite(frameStart)
    && Number.isFinite(frameEnd)
    && frameEnd >= frameStart
    && Number(state.source_fps || 0) > 0;
  const outputReady = frameRangeReady
    && Number(state.output_width || 0) > 0
    && Number(state.output_height || 0) > 0
    && Number(state.output_fps || state.source_fps || 0) > 0;
  const maskGenerationSelected = Object.prototype.hasOwnProperty.call(state, "mask_enabled")
    ? !!state.mask_enabled
    : true;
  const generationOutputSelected = !!state.original_enabled
    || maskGenerationSelected
    || !!state.depth_enabled
    || !!state.motion_guide_enabled;
  const activeSnapshotUid = clean(state.active_snapshot_uid);
  const snapshotAvailable = hmbSnapshotHistory(state)
    .some((item) => clean(item.snapshot_uid) === activeSnapshotUid)
    || (
      !!state.snapshot_active
      && !!clean(state.snapshot_path || state.snapshot_url)
    );

  return {
    readEnabled: mayaAvailable && validFile && !operationBusy && !localReadPending && !localOriginalPending && (terminalFailure || !readSnapshotReady),
    stopEnabled: (operationBusy || !!localReadPending || !!localOriginalPending) && !stopping,
    playblastEnabled: !operationBusy
      && !terminalFailure
      && readSnapshotReady
      && cameraReady
      && outputReady
      && generationOutputSelected,
    originalPreviewToggleEnabled: !operationBusy
      && !terminalFailure
      && readSnapshotReady
      && outlinerReady
      && cameraReady
      && frameRangeReady,
    snapshotEnabled: !operationBusy
      && !terminalFailure
      && readSnapshotReady
      && cameraReady
      && outputReady,
    snapshotDeleteEnabled: !operationBusy && snapshotAvailable,
    operationBusy,
    sceneChanged,
    readSnapshotReady,
  };
}

export function hmbClaimPickerCommandSubmission(container, action, actionId) {
  const resolvedActionId = clean(actionId);
  if (!container || !resolvedActionId || container.__hmbPickerOperationSubmissionPending) return false;
  container.__hmbPickerOperationSubmissionPending = true;
  container.__hmbPickerOperationActionId = resolvedActionId;
  container.__hmbPickerOperationAction = clean(action);
  return true;
}

export function hmbClearPickerCommandSubmission(container, actionId) {
  const resolvedActionId = clean(actionId);
  if (
    !container
    || !resolvedActionId
    || clean(container.__hmbPickerOperationActionId) !== resolvedActionId
  ) return false;
  delete container.__hmbPickerOperationSubmissionPending;
  delete container.__hmbPickerOperationActionId;
  delete container.__hmbPickerOperationAction;
  return true;
}

export function hmbApplyPickerCommandGuardToDom(container, busy, action = "") {
  if (!container?.querySelector) return false;
  const pending = !!busy;
  const pendingAction = clean(action);
  const controls = [
    "#read-scene",
    "#stop-read",
    "#run-video",
    "#create-snapshot",
    "#delete-snapshot",
    "#browse-maya-scene",
    "#maya-scene-path",
    "#playblast-resolution",
    "#original-preview-toggle",
    "#mask-playblast-toggle",
    "#depth-playblast-toggle",
    "#motion-guide-toggle",
    "#shot-selector",
  ];
  if (pending) {
    for (const selector of controls) {
      const control = container.querySelector(selector);
      if (control) control.disabled = true;
    }
    for (const control of container.querySelectorAll?.("[data-camera-path], [data-color]") || []) {
      control.disabled = true;
    }
  }
  for (const [selector, command] of [
    ["#run-video", "run_video"],
    ["#create-snapshot", "render_snapshot"],
    ["#delete-snapshot", "delete_snapshot"],
  ]) {
    const control = container.querySelector(selector);
    if (!control) continue;
    if (pending && pendingAction === command) control.setAttribute?.("aria-busy", "true");
    else control.removeAttribute?.("aria-busy");
  }
  return true;
}

export function hmbApplyPickerCommandAvailabilityToDom(container, availability = {}) {
  if (!container?.querySelector) return false;
  const mapping = [
    ["#read-scene", "readEnabled"],
    ["#stop-read", "stopEnabled"],
    ["#run-video", "playblastEnabled"],
    ["#create-snapshot", "snapshotEnabled"],
    ["#delete-snapshot", "snapshotDeleteEnabled"],
  ];
  for (const [selector, field] of mapping) {
    const control = container.querySelector(selector);
    if (control) control.disabled = !availability[field];
  }
  return true;
}

function setSlotBindings(state, slot, bindings) {
  return {
    ...state,
    slot_assignments: Array.from({ length: state.active_slot_count }, (_, index) => {
      const currentSlot = index + 1;
      return {
        video_slot: currentSlot,
        bindings: hmbDedupePickerBindings(
          currentSlot === slot ? bindings : selectedBindings(state, currentSlot),
          currentSlot,
        ),
      };
    }),
  };
}

function markerCatalogRows(markerCatalog) {
  const catalog = markerCatalog && typeof markerCatalog === "object" ? markerCatalog : {};
  return [
    ...(Array.isArray(catalog.character) ? catalog.character : []),
    ...(Array.isArray(catalog.background) ? catalog.background : []),
  ];
}

export function hmbPickerPaletteGroups(markerCatalog) {
  const catalog = markerCatalog && typeof markerCatalog === "object" ? markerCatalog : {};
  const characterRows = Array.isArray(catalog.character) ? catalog.character : [];
  const backgroundRows = Array.isArray(catalog.background) ? catalog.background : [];
  const names = (rows) => rows.map((item) => clean(item?.name)).filter(Boolean);
  const actor = names(characterRows);
  const ghost = names(backgroundRows.filter(
    (item) => clean(item?.kind).toLowerCase() === "solid",
  ));
  const object = names(backgroundRows.filter(
    (item) => clean(item?.kind).toLowerCase() === "pattern",
  ));
  const ordered = [...actor, ...ghost, ...object];
  if (
    actor.length === 7
    && ghost.length === 3
    && object.length === 4
    && new Set(ordered).size === 14
  ) {
    return { actor, ghost, object };
  }
  return {
    actor: FALLBACK_MARKER_OPTIONS.slice(0, 7),
    ghost: FALLBACK_MARKER_OPTIONS.slice(7, 10),
    object: FALLBACK_MARKER_OPTIONS.slice(10, 14),
  };
}

export function hmbPickerMarkerAllowsRepeat(name, markerCatalog) {
  const markerName = clean(name);
  const catalog = markerCatalog && typeof markerCatalog === "object" ? markerCatalog : {};
  const background = Array.isArray(catalog.background) && catalog.background.length
    ? catalog.background
    : FALLBACK_MARKER_OPTIONS.slice(7).map((fallbackName) => ({ name: fallbackName }));
  return background.some((item) => clean(item?.name) === markerName);
}

function markerRgb(name, markerCatalog) {
  const row = markerCatalogRows(markerCatalog).find((item) => clean(item?.name) === clean(name));
  const source = Array.isArray(row?.rgb) && row.rgb.length === 3 ? row.rgb : COLOR_RGB[name];
  if (!Array.isArray(source) || source.length !== 3) return [100, 116, 139];
  return source.map((channel) => {
    const numeric = Number(channel);
    const scaled = numeric >= 0 && numeric <= 1 ? numeric * 255 : numeric;
    return Math.max(0, Math.min(255, Math.round(scaled)));
  });
}

export function hmbPickerColorStyle(name, markerCatalog) {
  if (name === "Direction Checker") return "background-color:#000;background-image:linear-gradient(45deg,#fff 25%,transparent 25%),linear-gradient(-45deg,#fff 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#fff 75%),linear-gradient(-45deg,transparent 75%,#fff 75%);background-size:10px 10px;background-position:0 0,0 5px,5px -5px,-5px 0";
  if (name === "Sky Grid") return "background-color:#5cb8ff;background-image:linear-gradient(rgba(255,255,255,.9) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.9) 1px,transparent 1px);background-size:7px 7px";
  if (name === "Floor Grid") return "background-color:#ad925f;background-image:linear-gradient(#ffe9a6 1px,transparent 1px),linear-gradient(90deg,#ffe9a6 1px,transparent 1px);background-size:7px 7px";
  if (name === "Position Pattern") return "background:conic-gradient(from 45deg,#ff4d4d 0 25%,#52d68b 0 50%,#4a74ff 0 75%,#ffe04a 0)";
  const rgb = markerRgb(name, markerCatalog);
  return `background:rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function hmbPickerComposedParent(element) {
  if (!element) return null;
  if (element.parentElement) return element.parentElement;
  try {
    const root = element.getRootNode?.();
    if (root?.host && root.host !== element) return root.host;
  } catch (_error) {}
  try {
    const frameElement = element.ownerDocument?.defaultView?.frameElement;
    if (frameElement && frameElement !== element) return frameElement;
  } catch (_error) {}
  return null;
}

export function hmbFindVideoPickerReactFlowNode(container) {
  void container;
  return null;
}

export function hmbVideoPickerNodeIdentity(container) {
  if (!container) return null;
  // View mode is widget-session state. Never walk into React Flow to discover
  // an identity: reading the host node made later code treat the canvas shell
  // as VideoPicker-owned geometry. The runtime id is stable for every remount
  // in one loaded workflow; a reload intentionally starts in compact mode.
  const runtimeId = clean(container.__hmbVideoPickerRuntimeInstanceId);
  return runtimeId ? `runtime:${runtimeId}` : container;
}

export function hmbVideoPickerStoredViewMode(container) {
  const identity = hmbVideoPickerNodeIdentity(container);
  if (!identity) return null;
  if (typeof identity === "string") {
    return hmbVideoPickerViewModeRegistry.has(identity)
      ? hmbVideoPickerViewModeRegistry.get(identity) === true
      : null;
  }
  return hmbVideoPickerViewModeFallbackRegistry.has(identity)
    ? hmbVideoPickerViewModeFallbackRegistry.get(identity) === true
    : null;
}

export function hmbRememberVideoPickerViewMode(container, expanded) {
  const resolved = expanded === true;
  const identity = hmbVideoPickerNodeIdentity(container);
  if (identity) {
    if (typeof identity === "string") hmbVideoPickerViewModeRegistry.set(identity, resolved);
    else hmbVideoPickerViewModeFallbackRegistry.set(identity, resolved);
  }
  if (container) container.__hmbVideoPickerExpanded = resolved;
  return resolved;
}

function hmbPickerDeleteEditingTarget(event) {
  return Boolean(event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbPickerDeleteEditingTarget(event)) return false;
  // Node selection and Delete ownership belong to the host canvas.
  void container;
  return false;
}

const HMB_PICKER_INTERNAL_HEADER_INTERACTIVE_SELECTOR = [
  "button", "input", "select", "textarea", "a", "summary", "[role='button']",
  "[contenteditable='true']", "[contenteditable='']", ".nodrag",
  "video", "audio", "[data-no-picker-toggle]",
].join(",");
function hmbVideoPickerPaintFirstJobs(container, create = false) {
  if (!container) return null;
  if (!(container.__hmbVideoPickerPaintFirstJobs instanceof Map) && create) {
    container.__hmbVideoPickerPaintFirstJobs = new Map();
  }
  return container.__hmbVideoPickerPaintFirstJobs instanceof Map
    ? container.__hmbVideoPickerPaintFirstJobs
    : null;
}

function hmbCancelVideoPickerPaintFirstJobHandles(job) {
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

function hmbSettleVideoPickerPaintFirstTask(container, channel, job, run) {
  if (!container || !job || job.settled) return false;
  const jobs = hmbVideoPickerPaintFirstJobs(container, false);
  if (jobs?.get(channel) !== job) return false;
  job.settled = true;
  hmbCancelVideoPickerPaintFirstJobHandles(job);
  jobs.delete(channel);
  if (!jobs.size) delete container.__hmbVideoPickerPaintFirstJobs;
  if (!run) return true;
  if (container.__hmbVideoPickerDeleted === true) return false;
  job.task(job.token);
  return true;
}

export function hmbVideoPickerPaintFirstTaskPending(container, channel = "default") {
  return !!hmbVideoPickerPaintFirstJobs(container, false)?.get(clean(channel) || "default");
}

export function hmbCancelVideoPickerPaintFirstTask(container, channel = "default") {
  const resolvedChannel = clean(channel) || "default";
  const job = hmbVideoPickerPaintFirstJobs(container, false)?.get(resolvedChannel);
  return hmbSettleVideoPickerPaintFirstTask(container, resolvedChannel, job, false);
}

// Paint local feedback before any normalization, host publication, media load,
// or full-view morph. Two animation frames guarantee a compositor boundary;
// the bounded timer keeps interactions reliable in a background/minimized tab.
// A repeated task on the same channel updates the pending work without moving
// the original deadline, so rapid selection changes coalesce instead of lagging.
export function hmbScheduleVideoPickerPaintFirstTask(
  container,
  channel,
  task,
  fallbackMs = HMB_PICKER_PAINT_FIRST_FALLBACK_MS,
) {
  if (!container || typeof task !== "function") return 0;
  const resolvedChannel = clean(channel) || "default";
  const jobs = hmbVideoPickerPaintFirstJobs(container, true);
  const pending = jobs.get(resolvedChannel);
  if (pending && !pending.settled) {
    pending.task = task;
    pending.token = ++hmbVideoPickerPaintFirstSequence;
    return pending.token;
  }
  const job = {
    token: ++hmbVideoPickerPaintFirstSequence,
    task,
    settled: false,
    firstFrame: null,
    secondFrame: null,
    fallbackTimer: null,
  };
  jobs.set(resolvedChannel, job);
  const run = () => hmbSettleVideoPickerPaintFirstTask(container, resolvedChannel, job, true);
  if (typeof setTimeout === "function") {
    job.fallbackTimer = setTimeout(run, Math.max(0, Number(fallbackMs) || 0));
  }
  if (typeof requestAnimationFrame === "function") {
    job.firstFrame = requestAnimationFrame(() => {
      if (job.settled || hmbVideoPickerPaintFirstJobs(container, false)?.get(resolvedChannel) !== job) return;
      job.secondFrame = requestAnimationFrame(run);
    });
  } else if (job.fallbackTimer == null) {
    run();
  }
  return job.token;
}

function hmbPickerEventPath(event) {
  try {
    const path = event?.composedPath?.();
    if (Array.isArray(path) && path.length) return path;
  } catch (_error) {}
  const path = [];
  let current = event?.target || null;
  while (current && path.length < 48) {
    path.push(current);
    current = hmbPickerComposedParent(current);
  }
  return path;
}

// The purple React Flow title bar remains entirely host-owned.  VideoPicker's
// compact/full switch is scoped to the fixed internal red header: its blank
// brand surface toggles, while every actual control and the widget body remain
// ordinary interactive/no-op double-click targets.
export function hmbVideoPickerInternalHeaderDoubleClickTarget(container, event) {
  if (!container || event?.type !== "dblclick" || Number(event?.button || 0) !== 0) return null;
  const rawTarget = event?.target || null;
  const target = rawTarget?.nodeType === 3 ? rawTarget.parentElement : rawTarget;
  if (!target || !container.contains?.(target)) return null;
  const header = target.closest?.(".top[data-picker-toggle-surface='header']") || null;
  if (!header || !container.contains?.(header)) return null;
  try {
    const interactive = target.closest?.(HMB_PICKER_INTERNAL_HEADER_INTERACTIVE_SELECTOR) || null;
    if (interactive && header.contains?.(interactive)) return null;
  } catch (_error) { return null; }
  return header;
}

export function hmbInstallVideoPickerInternalHeaderToggle(container, cleanupList, onToggle) {
  if (!container?.addEventListener || !Array.isArray(cleanupList) || typeof onToggle !== "function") {
    return false;
  }
  const captureInternalHeaderDoubleClick = (event) => {
    if (!hmbVideoPickerInternalHeaderDoubleClickTarget(container, event)) return;
    event.preventDefault?.();
    event.stopImmediatePropagation?.();
    event.stopPropagation?.();
    onToggle(event);
  };
  container.addEventListener("dblclick", captureInternalHeaderDoubleClick, true);
  cleanupList.push(() => {
    container.removeEventListener?.("dblclick", captureInternalHeaderDoubleClick, true);
  });
  return true;
}

const hmbHandledVideoAssetSelectionEvents = new WeakSet();

function hmbClaimVideoAssetSelectionEvent(event) {
  if (!event || (typeof event !== "object" && typeof event !== "function")) return false;
  if (hmbHandledVideoAssetSelectionEvents.has(event)) return false;
  hmbHandledVideoAssetSelectionEvents.add(event);
  return true;
}

export function hmbInstallVideoAssetRootDelegation(container, handlers = {}, cleanupList = []) {
  if (!container?.addEventListener || !Array.isArray(cleanupList)) return false;
  const delegatedClick = (event) => {
    const target = event?.target;
    if (!target || !container.contains?.(target)) return;
    const play = target.closest?.("[data-play-video-uid]");
    if (play && container.contains?.(play)) {
      handlers.play?.(event, play);
      return;
    }
    const remove = target.closest?.("[data-delete-video-uid]");
    if (remove && container.contains?.(remove)) {
      handlers.remove?.(event, remove);
      return;
    }
    const select = target.closest?.("[data-toggle-video-uid]");
    if (
      select
      && container.contains?.(select)
      && hmbClaimVideoAssetSelectionEvent(event)
    ) handlers.select?.(event, select);
  };
  const delegatedKeydown = (event) => {
    if (!["Enter", " "].includes(event?.key)) return;
    const select = event?.target?.closest?.("[data-toggle-video-uid]");
    if (!select || !container.contains?.(select) || event?.repeat === true) return;
    // A native button emits its own trusted click for Enter/Space. Handling the
    // keydown as well toggles selected -> deselected -> selected in one user
    // action. Non-button role surfaces still need the keyboard delegate.
    if (clean(select.tagName).toUpperCase() === "BUTTON") return;
    event.preventDefault?.();
    if (hmbClaimVideoAssetSelectionEvent(event)) handlers.select?.(event, select);
  };
  container.addEventListener("click", delegatedClick);
  container.addEventListener("keydown", delegatedKeydown);
  cleanupList.push(() => {
    container.removeEventListener?.("click", delegatedClick);
    container.removeEventListener?.("keydown", delegatedKeydown);
  });
  return true;
}

export function hmbOpenVideoPickerFileInput(container, workspaceUuidValue) {
  const workspaceUuid = hmbUuid(workspaceUuidValue);
  const input = container?.querySelector?.("#import-video-asset") || null;
  if (!workspaceUuid || !input?.click || container.__hmbVideoImportDialogPending === true) return false;
  const token = `${workspaceUuid}:${Date.now()}:${Math.random().toString(16).slice(2, 8)}`;
  container.__hmbVideoImportDialogPending = true;
  container.__hmbVideoImportDialogToken = token;
  container.__hmbPendingImportWorkspaceUuid = workspaceUuid;
  try { input.value = ""; } catch (_error) {}
  try {
    input.click();
  } catch (_error) {
    delete container.__hmbVideoImportDialogPending;
    delete container.__hmbVideoImportDialogToken;
    delete container.__hmbPendingImportWorkspaceUuid;
    return false;
  }
  // File dialogs are modal in the desktop host. This timer runs only after the
  // dialog closes and makes Cancel retryable without permitting double-open.
  setTimeout(() => {
    if (clean(container.__hmbVideoImportDialogToken) !== token) return;
    delete container.__hmbVideoImportDialogPending;
    delete container.__hmbVideoImportDialogToken;
    delete container.__hmbPendingImportWorkspaceUuid;
  }, 750);
  return true;
}

export function hmbConsumeVideoPickerFileInputTarget(container, fallbackWorkspaceUuid = "") {
  const workspaceUuid = hmbUuid(container?.__hmbPendingImportWorkspaceUuid)
    || hmbUuid(fallbackWorkspaceUuid);
  if (container) {
    delete container.__hmbVideoImportDialogPending;
    delete container.__hmbVideoImportDialogToken;
    delete container.__hmbPendingImportWorkspaceUuid;
  }
  return workspaceUuid;
}

export function hmbEnforceVideoPickerLoadSurfaces(
  container,
  expanded = false,
  activeWorkspaceUuid = "",
) {
  const buttons = Array.from(container?.querySelectorAll?.("#import-video-button") || []);
  const keepButton = expanded
    ? (buttons.find((button) => button.closest?.("[data-video-assets-toolbar]")) || buttons[0] || null)
    : null;
  for (const button of buttons) {
    if (button !== keepButton) button.remove?.();
  }
  if (keepButton) {
    keepButton.setAttribute?.("data-picker-shot-load", hmbUuid(activeWorkspaceUuid));
  }
  const inputs = Array.from(container?.querySelectorAll?.("#import-video-asset") || []);
  const keepInput = inputs[0] || null;
  for (const input of inputs.slice(1)) input.remove?.();
  return {
    visibleLoadButtonCount: keepButton ? 1 : 0,
    sharedInputCount: keepInput ? 1 : 0,
  };
}

export function hmbSyncVideoPickerPlayButtonState(
  container,
  activeUid = "",
  playing = false,
  tr = TEXT.en,
) {
  const resolvedActiveUid = clean(activeUid);
  const copy = tr && typeof tr === "object" ? tr : TEXT.en;
  let activeCount = 0;
  for (const button of container?.querySelectorAll?.("[data-play-video-uid]") || []) {
    const uid = clean(button.getAttribute?.("data-play-video-uid"));
    const active = !!playing && !!resolvedActiveUid && uid === resolvedActiveUid;
    const title = clean(button.getAttribute?.("data-video-title"));
    const actionLabel = active ? (copy.pauseVideo || "Pause") : (copy.playVideo || "Play");
    button.textContent = active ? "Ⅱ" : "▶";
    button.setAttribute?.("aria-pressed", active ? "true" : "false");
    button.setAttribute?.(
      "aria-label",
      `${title ? `${title}: ` : ""}${actionLabel}`,
    );
    button.closest?.(".video-asset-thumb,.compact-shot-thumb")
      ?.classList?.toggle?.("is-playing", active);
    if (active) activeCount += 1;
  }
  return activeCount;
}

function hmbVideoPickerRequestedPlaybackUid(container) {
  return clean(container?.__hmbVideoPickerRequestedPlaybackUid);
}

function hmbSetVideoPickerPlaybackRequest(container, uidValue = "", requested = false) {
  if (!container) return "";
  const uid = requested ? clean(uidValue) : "";
  if (uid) container.__hmbVideoPickerRequestedPlaybackUid = uid;
  else delete container.__hmbVideoPickerRequestedPlaybackUid;
  return uid;
}

export function hmbPauseVideoPickerMedia(container) {
  hmbSetVideoPickerPlaybackRequest(container);
  let paused = 0;
  for (const media of container?.querySelectorAll?.("video") || []) {
    if (!media.paused && !media.ended) paused += 1;
    media.pause?.();
  }
  hmbSyncVideoPickerPlayButtonState(container);
  return paused;
}

export function hmbInstallVideoPickerShotWorkspaceDelegation(container, handlers = {}, cleanupList = []) {
  if (!container?.addEventListener || !Array.isArray(cleanupList)) return false;
  const inside = (element) => !!element && container.contains?.(element);
  const delegatedClick = (event) => {
    const target = event?.target;
    if (!inside(target)) return;
    const add = target.closest?.("[data-picker-shot-add]");
    if (inside(add)) return handlers.add?.(event, add);
    const load = target.closest?.("[data-picker-shot-load]");
    if (inside(load)) return handlers.load?.(event, load);
    const activate = target.closest?.("[data-picker-shot-activate]");
    if (inside(activate)) return handlers.activate?.(event, activate);
    const rename = target.closest?.("[data-picker-shot-rename]");
    if (inside(rename)) return handlers.rename?.(event, rename);
    const remove = target.closest?.("[data-picker-shot-delete]");
    if (inside(remove)) return handlers.remove?.(event, remove);
    const interactive = target.closest?.("button,input,select,textarea,a,[contenteditable='true'],[contenteditable='']");
    const row = target.closest?.("[data-picker-shot-row]");
    if (!interactive && inside(row)) return handlers.activate?.(event, row);
  };
  const delegatedChange = (event) => {
    const binding = event?.target?.closest?.("[data-picker-shot-bind]");
    if (inside(binding)) handlers.bind?.(event, binding);
  };
  const delegatedKeydown = (event) => {
    const input = event?.target?.closest?.("[data-picker-shot-rename-input]");
    if (inside(input)) handlers.renameKeydown?.(event, input);
  };
  const delegatedFocusout = (event) => {
    const input = event?.target?.closest?.("[data-picker-shot-rename-input]");
    if (inside(input)) handlers.renameBlur?.(event, input);
  };
  container.addEventListener("click", delegatedClick);
  container.addEventListener("change", delegatedChange);
  container.addEventListener("keydown", delegatedKeydown);
  container.addEventListener("focusout", delegatedFocusout);
  cleanupList.push(() => {
    container.removeEventListener?.("click", delegatedClick);
    container.removeEventListener?.("change", delegatedChange);
    container.removeEventListener?.("keydown", delegatedKeydown);
    container.removeEventListener?.("focusout", delegatedFocusout);
  });
  return true;
}

export function hmbSetVideoPickerCanvasMotion(container, active) {
  const root = container?.querySelector?.(".hmbvp");
  if (!root) return false;
  root.setAttribute?.("data-canvas-motion", active ? "true" : "false");
  for (const video of root.querySelectorAll?.("video") || []) {
    if (active) {
      video.__hmbPickerSuspendProbe?.();
      if (!video.__hmbPickerMotionPreload) {
        video.__hmbPickerMotionPreload = clean(video.getAttribute?.("preload") || "metadata");
      }
      if (!Object.prototype.hasOwnProperty.call(video, "__hmbPickerMotionWasPlaying")) {
        video.__hmbPickerMotionWasPlaying = !video.paused && !video.ended;
      }
      video.pause?.();
      video.setAttribute?.("preload", "none");
    } else {
      const preload = clean(video.__hmbPickerMotionPreload || "none");
      video.setAttribute?.("preload", preload);
      delete video.__hmbPickerMotionPreload;
      const resume = video.__hmbPickerMotionWasPlaying === true;
      delete video.__hmbPickerMotionWasPlaying;
      const resumeProbe = video.__hmbPickerResumeProbe;
      delete video.__hmbPickerResumeProbe;
      if (typeof resumeProbe === "function") resumeProbe();
      if (resume) {
        const playResult = video.play?.();
        playResult?.catch?.(() => {});
      }
    }
  }
  return true;
}

export function hmbInstallVideoPickerCanvasMotionDelegation(container, cleanupList) {
  // Canvas wheel/pointer delegation was a VideoPicker-only optimization. It
  // registered listeners on the entire React Flow surface and could therefore
  // interfere with host panning and viewport lifecycle. Media is now managed
  // only by controls inside the widget.
  void container;
  void cleanupList;
  return false;
}

export function hmbNormalizePickerHostAncestors(container) {
  // Host/adaptive ancestors are owned exclusively by Griptape.
  void container;
  return 0;
}

function hmbReleaseLegacyOuterNodeOverrides(container) {
  void container;
  return null;
}

function hmbPickerElementScaleY(element) {
  if (!element) return 1;
  try {
    const rect = element.getBoundingClientRect?.();
    const cssHeight = Number(element.offsetHeight || 0);
    const visualHeight = Number(rect?.height || 0);
    if (cssHeight > 0 && visualHeight > 0) {
      const scale = visualHeight / cssHeight;
      if (Number.isFinite(scale) && scale > 0.05 && scale < 20) return scale;
    }
  } catch (_error) {}
  return 1;
}

function hmbPickerCssHeight(element, fallback = 0) {
  if (!element) return Math.max(0, Number(fallback) || 0);
  try {
    const value = Number(element.offsetHeight || 0);
    if (Number.isFinite(value) && value > 0) return value;
  } catch (_error) {}
  try {
    const styleHeight = parseFloat(element.style?.height || "");
    if (Number.isFinite(styleHeight) && styleHeight > 0) return styleHeight;
  } catch (_error) {}
  try {
    const rect = element.getBoundingClientRect?.();
    const visualHeight = Number(rect?.height || 0);
    const scale = hmbPickerElementScaleY(element);
    if (Number.isFinite(visualHeight) && visualHeight > 0) return visualHeight / Math.max(0.05, scale);
  } catch (_error) {}
  return Math.max(0, Number(fallback) || 0);
}

function hmbPickerComputedNumber(element, property, fallback = 0) {
  try {
    const style = element && window.getComputedStyle ? window.getComputedStyle(element) : null;
    const value = style ? parseFloat(style[property] || "") : NaN;
    if (Number.isFinite(value)) return value;
  } catch (_error) {}
  return Number(fallback) || 0;
}

function hmbPickerIsVerticallyStacked(parent) {
  try {
    const style = parent && window.getComputedStyle ? window.getComputedStyle(parent) : null;
    const display = String(style?.display || "").toLowerCase();
    const direction = String(style?.flexDirection || "").toLowerCase();
    if (display.includes("flex")) return !direction.startsWith("row");
    if (display.includes("grid")) {
      const columns = String(style?.gridTemplateColumns || "").trim();
      return !columns || columns === "none" || columns.split(/\s+/).length <= 1;
    }
  } catch (_error) {}
  return true;
}

function hmbPickerPreviousSiblingHeight(parent, current) {
  if (!parent || !current || !hmbPickerIsVerticallyStacked(parent)) return 0;
  let total = 0;
  try {
    for (let sibling = parent.firstElementChild; sibling && sibling !== current; sibling = sibling.nextElementSibling) {
      if (
        sibling.getAttribute?.("data-hmb-maya-picker-bridge") === "true"
        || sibling.getAttribute?.("aria-hidden") === "true"
      ) {
        continue;
      }
      const style = window.getComputedStyle ? window.getComputedStyle(sibling) : null;
      const display = String(style?.display || "").toLowerCase();
      const position = String(style?.position || "").toLowerCase();
      if (display === "none" || position === "absolute" || position === "fixed") continue;
      total += hmbPickerCssHeight(sibling, 0);
      total += parseFloat(style?.marginTop || "0") || 0;
      total += parseFloat(style?.marginBottom || "0") || 0;
    }
  } catch (_error) {}
  return Math.max(0, total);
}

export function hmbPickerNaturalTopInset(container, shell) {
  if (!container || !shell) return 0;
  let total = 0;
  let current = container;
  for (let depth = 0; current && current !== shell && depth < 12; depth += 1) {
    const parent = current.parentElement;
    if (!parent) break;
    total += hmbPickerPreviousSiblingHeight(parent, current);
    total += hmbPickerComputedNumber(parent, "paddingTop", 0);
    total += hmbPickerComputedNumber(parent, "borderTopWidth", 0);
    current = parent;
  }
  return current === shell ? Math.max(0, Math.ceil(total)) : 0;
}

function hmbPickerSectionRequiredHeight(section, fallback = 96) {
  if (!section) return Math.max(0, Number(fallback) || 0);
  let value = 0;
  try {
    const inlineHeight = parseFloat(section.style?.height || "");
    if (Number.isFinite(inlineHeight) && inlineHeight > 0) value = inlineHeight;
  } catch (_error) {}
  if (!(value > 0)) value = hmbPickerCssHeight(section, fallback);
  const minimum = hmbPickerComputedNumber(section, "minHeight", fallback);
  return Math.max(Number(fallback) || 0, minimum || 0, value || 0);
}

function hmbPickerRightStackRequiredHeight(container) {
  const stack = container?.querySelector?.(".right-stack");
  if (!stack) return 0;
  const sections = Array.from(stack.querySelectorAll?.(".side-section") || []);
  if (!sections.length) return 0;
  const heights = sections.map((section) => {
    if (section.classList?.contains("video-assets-section")) {
      return Math.max(240, hmbPickerComputedNumber(section, "minHeight", 240));
    }
    return hmbPickerSectionRequiredHeight(section, 96);
  });
  let display = "";
  let gap = 8;
  try {
    const style = window.getComputedStyle ? window.getComputedStyle(stack) : null;
    display = String(style?.display || "").toLowerCase();
    gap = parseFloat(style?.rowGap || style?.gap || "8") || 8;
  } catch (_error) {}
  if (display === "grid") return Math.max(...heights);
  return heights.reduce((sum, value) => sum + value, 0) + gap * Math.max(0, heights.length - 1);
}

function hmbPickerViewportPanelRequiredHeight(container) {
  const panel = container?.querySelector?.(".viewport-panel");
  if (!panel) return 0;
  const fixed = [
    [".snapshot-toolbar", 42],
    [".generate-playblast-toolbar", 42],
    [".playblast-settings-toolbar", 88],
    [".panel-title.viewport-title", 34],
    [".video-seekbar", 28],
    [".video-controls", 44],
    [".frame-info-strip", 28],
    [".panel-resize-handle", 10],
  ].reduce((sum, entry) => sum + hmbPickerCssHeight(panel.querySelector?.(entry[0]), entry[1]), 0);
  const borders = hmbPickerComputedNumber(panel, "borderTopWidth", 1) + hmbPickerComputedNumber(panel, "borderBottomWidth", 1);
  const explicitHeight = parseFloat(panel.style?.height || "");
  return Math.max(
    Number.isFinite(explicitHeight) ? explicitHeight : 0,
    Math.ceil(fixed + HMB_PICKER_VIEWPORT_STAGE_MIN_HEIGHT + borders),
  );
}

function hmbPickerOutlinerPanelRequiredHeight(container) {
  const panels = Array.from(container?.querySelectorAll?.(".main-grid > .panel") || []);
  const panel = panels.find((item) => !item.classList?.contains("viewport-panel"));
  if (!panel) return 0;
  const fixed = [
    [".panel-title", 34],
    [".outliner-palette", 82],
    [".outliner-toolbar", 45],
    [".column-head", 28],
  ].reduce((sum, entry) => sum + hmbPickerCssHeight(panel.querySelector?.(entry[0]), entry[1]), 0);
  const borders = hmbPickerComputedNumber(panel, "borderTopWidth", 1) + hmbPickerComputedNumber(panel, "borderBottomWidth", 1);
  return Math.ceil(fixed + HMB_PICKER_OUTLINER_BODY_MIN_HEIGHT + borders);
}

function hmbPickerCenterStackRequiredHeight(container) {
  const stack = container?.querySelector?.(".center-stack");
  if (!stack) return hmbPickerViewportPanelRequiredHeight(container);
  const viewportHeight = hmbPickerViewportPanelRequiredHeight(container);
  const activity = stack.querySelector?.(".activity-section");
  const activityHeight = activity
    ? Math.max(150, hmbPickerComputedNumber(activity, "minHeight", 150))
    : 0;
  let gap = 8;
  try {
    const style = window.getComputedStyle ? window.getComputedStyle(stack) : null;
    gap = parseFloat(style?.rowGap || style?.gap || "8") || 8;
  } catch (_error) {}
  return viewportHeight + activityHeight + (activityHeight > 0 ? gap : 0);
}

function hmbPickerMainGridRequiredHeight(container) {
  const grid = container?.querySelector?.(".main-grid");
  if (!grid) return HMB_PICKER_CONTENT_FALLBACK_HEIGHT;
  const leftHeight = hmbPickerOutlinerPanelRequiredHeight(container);
  const centerHeight = hmbPickerCenterStackRequiredHeight(container);
  const rightHeight = hmbPickerRightStackRequiredHeight(container);
  let gridGap = 8;
  let gridPadding = 16;
  let rightDisplay = "flex";
  try {
    const gridStyle = window.getComputedStyle ? window.getComputedStyle(grid) : null;
    gridGap = parseFloat(gridStyle?.rowGap || gridStyle?.gap || "8") || 8;
    gridPadding = (parseFloat(gridStyle?.paddingTop || "0") || 0) + (parseFloat(gridStyle?.paddingBottom || "0") || 0);
    const rightStack = container.querySelector?.(".right-stack");
    const rightStyle = rightStack && window.getComputedStyle ? window.getComputedStyle(rightStack) : null;
    rightDisplay = String(rightStyle?.display || "flex").toLowerCase();
  } catch (_error) {}
  const firstRowHeight = Math.max(leftHeight, centerHeight);
  const contentHeight = rightDisplay === "grid"
    ? firstRowHeight + gridGap + rightHeight
    : Math.max(firstRowHeight, rightHeight);
  return Math.ceil(gridPadding + contentHeight);
}

function hmbPickerInnerRequiredHeight(container) {
  if (!container) return HMB_PICKER_CONTENT_FALLBACK_HEIGHT;
  const headerHeight = hmbPickerCssHeight(container.querySelector?.(".app-header"), 68);
  const sceneLoadHeight = hmbPickerCssHeight(container.querySelector?.(".scene-load-bar"), 42);
  const mainHeight = hmbPickerMainGridRequiredHeight(container);
  const picker = container.querySelector?.(".hmbvp");
  const borders = hmbPickerComputedNumber(picker, "borderTopWidth", 1) + hmbPickerComputedNumber(picker, "borderBottomWidth", 1);
  return Math.max(
    HMB_PICKER_CONTENT_FALLBACK_HEIGHT,
    Math.ceil(headerHeight + sceneLoadHeight + mainHeight + borders),
  );
}

function hmbSetPickerStyleIfChanged(element, property, value, priority = "") {
  if (!element?.style) return false;
  const nextValue = String(value == null ? "" : value);
  try {
    const currentValue = element.style.getPropertyValue?.(property) || "";
    const currentPriority = element.style.getPropertyPriority?.(property) || "";
    if (currentValue === nextValue && currentPriority === priority) return false;
    element.style.setProperty(property, nextValue, priority);
    return true;
  } catch (_error) {
    return false;
  }
}

function hmbApplyPickerHostSizing(container, requiredInnerHeight = null) {
  if (!container || !container.style) return HMB_PICKER_CONTENT_FALLBACK_HEIGHT;
  const minimumRequired = Math.max(
    HMB_PICKER_CONTENT_FALLBACK_HEIGHT,
    Math.ceil(Number(requiredInnerHeight) || hmbPickerInnerRequiredHeight(container)),
  );
  // The custom widget owns only its content box. React Flow, its node shell,
  // adaptive parameter rows and the workspace canvas are never read or styled.
  const required = minimumRequired;
  const applyMinimum = (element) => {
    if (!element || !element.style) return;
    try {
      if (element.dataset?.hmbPickerHeightPropagation === "1") {
        for (const property of ["height", "min-height", "max-height", "flex", "overflow"]) {
          element.style.removeProperty(property);
        }
        delete element.dataset.hmbPickerHeightPropagation;
      }
      hmbSetPickerStyleIfChanged(element, "min-height", `${required}px`);
      hmbSetPickerStyleIfChanged(element, "max-height", "none");
      hmbSetPickerStyleIfChanged(element, "box-sizing", "border-box");
    } catch (_error) {}
  };
  try {
    if (container.style.width !== "100%") container.style.width = "100%";
    hmbSetPickerStyleIfChanged(container, "min-width", "0px");
    if (container.style.maxWidth !== "none") container.style.maxWidth = "none";
    if (container.style.overflow !== "visible") container.style.overflow = "visible";
    applyMinimum(container);
    container.classList?.remove("nodrag");
    container.classList?.remove("nowheel");
    const clip = container.querySelector?.(".hmbvp-clip");
    if (clip && clip.style) {
      hmbSetPickerStyleIfChanged(clip, "width", "100%");
      hmbSetPickerStyleIfChanged(clip, "height", `${required}px`);
      hmbSetPickerStyleIfChanged(clip, "min-height", `${required}px`);
      hmbSetPickerStyleIfChanged(clip, "max-width", "none");
      hmbSetPickerStyleIfChanged(clip, "max-height", "none");
      hmbSetPickerStyleIfChanged(clip, "overflow", "visible");
      hmbSetPickerStyleIfChanged(clip, "box-sizing", "border-box");
    }
    const picker = container.querySelector?.(".hmbvp");
    if (picker && picker.style) {
      hmbSetPickerStyleIfChanged(picker, "width", "100%");
      hmbSetPickerStyleIfChanged(picker, "height", `${required}px`);
      hmbSetPickerStyleIfChanged(picker, "min-height", `${required}px`);
      hmbSetPickerStyleIfChanged(picker, "max-width", "none");
      hmbSetPickerStyleIfChanged(picker, "max-height", "none");
      hmbSetPickerStyleIfChanged(picker, "resize", "none");
      hmbSetPickerStyleIfChanged(picker, "overflow", "hidden");
      hmbSetPickerStyleIfChanged(picker, "box-sizing", "border-box");
      if (!picker.style.paddingLeft) hmbSetPickerStyleIfChanged(picker, "padding-left", "var(--safe-x)");
      if (!picker.style.paddingRight) hmbSetPickerStyleIfChanged(picker, "padding-right", "var(--safe-x)");
    }
  } catch (_error) {}
  return required;
}

const HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES = [
  "width", "height", "min-width", "min-height", "max-width", "max-height",
  "overflow", "box-sizing",
];

// Compact mode is an application-owned loader, not a resizable full
// dashboard.  Attribute-scoped CSS also covers controls inserted later by
// React Flow, while the capture guard prevents a pointer start from reaching
// an already-mounted NodeResizer.  Existing inline styles/attributes are never
// rewritten and are therefore restored exactly on expand/delete.
export function hmbSetVideoPickerNativeResizeLocked(container, locked) {
  // React Flow's native resize controls are host-owned. Compact mode no longer
  // hides or intercepts them outside the widget boundary.
  void container;
  void locked;
  return false;
}

export function hmbAdoptVideoPickerFixedTop(container) {
  if (!container) return null;
  const retained = container.__hmbVideoPickerFixedTop || null;
  const incoming = container.querySelector?.(".top[data-picker-toggle-surface='header']") || null;
  if (!retained && incoming) {
    container.__hmbVideoPickerFixedTop = incoming;
    return incoming;
  }
  if (!retained) return null;
  if (incoming && incoming !== retained) incoming.replaceWith?.(retained);
  else if (!incoming) {
    const picker = container.querySelector?.(".hmbvp") || null;
    if (picker) picker.insertBefore?.(retained, picker.firstChild || null);
  }
  return retained;
}

export function hmbCaptureVideoPickerExpandedGeometry(container) {
  const targets = [
    container,
    container.querySelector?.(".hmbvp-clip"),
    container.querySelector?.(".hmbvp"),
  ].filter((element, index, all) => element?.style && all.indexOf(element) === index);
  const entries = targets.map((element) => {
    const properties = {};
    for (const property of HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES) {
      properties[property] = {
        value: clean(element.style.getPropertyValue?.(property) || ""),
        priority: clean(element.style.getPropertyPriority?.(property) || ""),
      };
    }
    return { element, properties };
  });
  return {
    shell: null,
    entries,
    compactHeight: undefined,
  };
}

export function hmbCaptureVideoPickerCompactHostGeometry(container) {
  if (!container?.style) return null;
  // This is the pre-expanded host baseline. Compact sizing itself never writes
  // these nodes; the snapshot is replayed exactly once when a full dashboard
  // returns to compact mode, undoing the min-height declarations that the
  // established expanded F781 layout intentionally owns.
  const targets = [container, container.querySelector?.(".hmbvp-clip"), container.querySelector?.(".hmbvp")]
    .filter((element, index, all) => element?.style && all.indexOf(element) === index);
  return targets.map((element) => {
    const properties = {};
    for (const property of HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES) {
      properties[property] = {
        value: clean(element.style.getPropertyValue?.(property) || ""),
        priority: clean(element.style.getPropertyPriority?.(property) || ""),
      };
    }
    return { element, properties };
  });
}

export function hmbRestoreVideoPickerCompactHostGeometry(snapshot) {
  if (!Array.isArray(snapshot)) return false;
  for (const entry of snapshot) {
    if (!entry?.element?.style) continue;
    for (const property of HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES) {
      const saved = entry.properties?.[property] || { value: "", priority: "" };
      if (saved.value) entry.element.style.setProperty?.(property, saved.value, saved.priority || "");
      else entry.element.style.removeProperty?.(property);
    }
  }
  return true;
}

export function hmbRestoreVideoPickerExpandedGeometry(container, snapshot, options = {}) {
  if (!container || !snapshot) return false;
  const shellOnly = options?.shellOnly === true;
  if (shellOnly) return false;
  const entries = Array.isArray(snapshot.entries) && snapshot.entries.length
    ? snapshot.entries
    : [];
  for (const entry of entries) {
    if (!entry?.element?.style) continue;
    for (const property of HMB_VIDEO_PICKER_GEOMETRY_PROPERTIES) {
      const saved = entry.properties?.[property] || { value: "", priority: "" };
      if (saved.value) entry.element.style.setProperty?.(property, saved.value, saved.priority || "");
      else entry.element.style.removeProperty?.(property);
    }
  }
  return true;
}

// The embedding React Flow host can expose its useUpdateNodeInternals callback
// on props or the exact node/container.  The bubbling event is the fallback
// bridge for hosts that keep the hook inside their React boundary.
export function hmbRequestVideoPickerNodeInternalsUpdate(container, props = null) {
  void container;
  void props;
  return false;
}

export function hmbVideoPickerNodeInternalsSignature(
  container,
  stateValue = undefined,
  expandedOverride = null,
) {
  if (!container) return "";
  const expanded = typeof expandedOverride === "boolean"
    ? expandedOverride
    : container?.__hmbVideoPickerExpanded === true;
  const state = stateValue === undefined
    ? normalize(container?.__hmbAuthoritativePickerState || {})
    : normalize(stateValue);
  const contentHeight = expanded
    ? Math.max(HMB_PICKER_CONTENT_FALLBACK_HEIGHT, hmbPickerInnerRequiredHeight(container))
    : hmbVideoPickerCompactMeasurementHeightFromNormalizedState(state);
  return [
    expanded ? "expanded" : "compact",
    contentHeight,
    "widget-only",
  ].join("::");
}

export function hmbCancelVideoPickerNodeInternalsUpdate(container) {
  container?.removeAttribute?.("data-hmb-video-picker-node-internals-pending");
  return false;
}

// Compatibility export retained for older test/import surfaces. Node internals
// are host-owned and VideoPicker never schedules a host geometry publication.
export function hmbScheduleVideoPickerNodeInternalsUpdate(
  container,
  props = null,
  options = {},
) {
  void props;
  void options;
  container?.removeAttribute?.("data-hmb-video-picker-node-internals-pending");
  return false;
}

export function hmbDetachVideoPickerDom(container) {
  if (!container) return [];
  const nodes = Array.from(container.childNodes || container.children || []);
  for (const node of nodes) {
    try { container.removeChild?.(node); } catch (_error) { node.remove?.(); }
  }
  return nodes;
}

export function hmbRestoreVideoPickerDom(container, nodes) {
  if (!container || !Array.isArray(nodes)) return false;
  hmbDetachVideoPickerDom(container);
  for (const node of nodes) container.appendChild?.(node);
  return true;
}

// Compact content participates in Griptape's adaptive parameter-row
// measurement; it must never size the enclosing React Flow node directly.
// v0.6.36 wrote the compact content height (158px for one empty Shot) into the
// outer node's height/min-height/max-height.  On a cold reload Griptape saw a
// node shorter than its native title and parameter chrome, moved all three
// Picker parameters into "Collapsed (3)", and therefore never mounted the
// visible widget that could recover it.  Release that legacy triple before the
// live compact frame is measured.  A hidden host-measurement clone may perform
// only the invalid-height repair; it never releases a valid expanded geometry.
export function hmbReleaseVideoPickerCompactOuterGeometry(container, options = {}) {
  void container;
  void options;
  return false;
}

export function hmbApplyVideoPickerCompactHostSizing(container, stateValue = undefined) {
  if (
    !container?.style
    || container.__hmbVideoPickerExpanded === true
    || hmbVideoPickerIsHostMeasurementClone(container)
  ) return 0;
  const picker = container.querySelector?.(".hmbvp");
  const clip = container.querySelector?.(".hmbvp-clip");
  if (clean(picker?.getAttribute?.("data-picker-view")) !== "compact") return 0;
  const resetCompactBox = (element) => {
    if (!element?.style) return;
    hmbSetPickerStyleIfChanged(element, "height", "auto");
    hmbSetPickerStyleIfChanged(element, "min-height", "0px");
    hmbSetPickerStyleIfChanged(element, "max-height", "none");
    hmbSetPickerStyleIfChanged(element, "overflow", "visible");
    hmbSetPickerStyleIfChanged(element, "box-sizing", "border-box");
  };
  // Editor 0.122 observes these adaptive ancestors to derive stackHeight. Its hidden measurement copy
  // now reports the same dynamic height, so releasing stale fixed 996px wrappers
  // is safe and prevents a black tail below the real compact content.
  resetCompactBox(container);
  resetCompactBox(clip);
  resetCompactBox(picker);
  if (clip?.style) hmbSetPickerStyleIfChanged(clip, "overflow", "hidden");
  if (picker?.style) hmbSetPickerStyleIfChanged(picker, "overflow", "hidden");
  // Asset add/delete changes a row between the 86px empty form and the 180px
  // populated form.  During that same frame the host can still expose its old
  // clipped offsetHeight, so prefer the authoritative state model whenever the
  // caller has it. DOM measurement remains a fallback for compatibility.
  const modelHeight = stateValue && typeof stateValue === "object"
    ? hmbVideoPickerCompactMeasurementHeightFromNormalizedState(stateValue)
    : 0;
  // State is authoritative for live widget updates. Avoid forced layout reads
  // in that hot path; DOM measurement remains a legacy/fallback-only branch.
  const layoutHeight = modelHeight > 0 ? 0 : Math.max(
    Number(picker?.offsetHeight || 0),
    Number(picker?.scrollHeight || 0),
  );
  const visualHeight = modelHeight > 0 ? 0 : Number(picker?.getBoundingClientRect?.()?.height || 0);
  const measuredVisible = modelHeight > 0
    ? modelHeight
    : layoutHeight > 0
      ? layoutHeight
      : visualHeight / Math.max(0.05, hmbPickerElementScaleY(picker));
  const measured = Math.ceil(measuredVisible > 0
    ? measuredVisible
    : HMB_VIDEO_PICKER_COMPACT_BOOTSTRAP_HEIGHT);
  const measuredPixels = `${measured}px`;
  // Keep the exact state-derived height inside the authored widget only.
  for (const element of [clip, picker]) {
    if (!element?.style) continue;
    hmbSetPickerStyleIfChanged(element, "height", measuredPixels);
    hmbSetPickerStyleIfChanged(element, "min-height", measuredPixels);
    hmbSetPickerStyleIfChanged(element, "max-height", measuredPixels);
  }
  container.dataset && (container.dataset.hmbVideoPickerCompactContentHeight = String(measured));
  // Repair only a v0.6.36 158px shell. Stable native node geometry (current
  // expanded 1200px or the native compact contract) remains authoritative and
  // is never released by the live compact widget.
  return measured;
}

export function hmbInstallVideoPickerCompactHostSizing(
  container,
  cleanupList = [],
  props = null,
  initialStateValue = undefined,
) {
  if (!container) return () => {};
  let firstFrame = 0;
  let disposed = false;
  let latestStateValue = initialStateValue;
  const useAnimationFrame = typeof requestAnimationFrame === "function";
  const frame = useAnimationFrame ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
  const cancel = useAnimationFrame && typeof cancelAnimationFrame === "function"
    ? cancelAnimationFrame
    : (handle) => clearTimeout(handle);
  const cancelPending = () => {
    if (firstFrame) cancel(firstFrame);
    firstFrame = 0;
  };
  const schedule = (nextStateValue = undefined) => {
    if (disposed || container.__hmbVideoPickerExpanded === true) return;
    if (nextStateValue !== undefined) latestStateValue = nextStateValue;
    cancelPending();
    container.setAttribute?.("data-hmb-video-picker-compact-sizing-pending", "true");
    firstFrame = frame(() => {
      firstFrame = 0;
      if (
        disposed
        || container.__hmbVideoPickerExpanded === true
        || hmbVideoPickerIsHostMeasurementClone(container)
      ) return;
      hmbApplyVideoPickerCompactHostSizing(container, latestStateValue);
      container.removeAttribute?.("data-hmb-video-picker-compact-sizing-pending");
    });
  };
  container.__hmbScheduleVideoPickerCompactHostSizing = schedule;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    cancelPending();
    container.removeAttribute?.("data-hmb-video-picker-compact-sizing-pending");
    if (container.__hmbScheduleVideoPickerCompactHostSizing === schedule) {
      delete container.__hmbScheduleVideoPickerCompactHostSizing;
    }
  };
  if (Array.isArray(cleanupList)) cleanupList.push(cleanup);
  schedule();
  return schedule;
}

function hmbApplyPickerInitialNodeSizeOnce(container) {
  void container;
}

function hmbPickerNodeVerticalMetrics(container, shell) {
  let topOffset = 0;
  let bottomInset = 8;
  try {
    const shellRect = shell?.getBoundingClientRect?.();
    const containerRect = container?.getBoundingClientRect?.();
    const scale = hmbPickerElementScaleY(shell) || 1;
    let measuredTopOffset = 0;
    if (shellRect && containerRect) {
      measuredTopOffset = Math.max(0, (containerRect.top - shellRect.top) / Math.max(0.05, scale));
    }
    const naturalTopOffset = hmbPickerNaturalTopInset(container, shell);
    // Flex/grid hosts can push a fixed-size custom widget to the bottom of a
    // resized node. That visual gap must not be treated as required chrome or
    // the picker can never grow back into it.
    topOffset = naturalTopOffset > 0
      ? (measuredTopOffset > 0 ? Math.min(measuredTopOffset, naturalTopOffset) : naturalTopOffset)
      : measuredTopOffset;
    const style = shell && window.getComputedStyle ? window.getComputedStyle(shell) : null;
    if (style) {
      bottomInset += (parseFloat(style.paddingBottom) || 0) + (parseFloat(style.borderBottomWidth) || 0);
    }
  } catch (_error) {}
  return { topOffset, bottomInset };
}

export function hmbPickerNodeShellHeight(shell) {
  if (!shell) return 0;
  try {
    const value = Number(shell.offsetHeight || 0);
    if (Number.isFinite(value) && value > 0) return Math.round(value);
  } catch (_error) {}
  try {
    const rect = shell.getBoundingClientRect?.();
    const scale = hmbPickerElementScaleY(shell) || 1;
    if (rect && rect.height > 0) return Math.round(rect.height / Math.max(0.05, scale));
  } catch (_error) {}
  return 0;
}

export function hmbPickerAvailableHeightToShell(element, shell) {
  if (!element || !shell) return 0;
  const shellHeight = hmbPickerNodeShellHeight(shell);
  if (!(shellHeight > 0)) return 0;
  let topOffset = 0;
  try {
    const shellRect = shell.getBoundingClientRect?.();
    const elementRect = element.getBoundingClientRect?.();
    const scale = hmbPickerElementScaleY(shell) || 1;
    let measuredTopOffset = 0;
    if (shellRect && elementRect) {
      measuredTopOffset = Math.max(
        0,
        (Number(elementRect.top || 0) - Number(shellRect.top || 0)) / Math.max(0.05, scale),
      );
    }
    const naturalTopOffset = hmbPickerNaturalTopInset(element, shell);
    topOffset = naturalTopOffset > 0
      ? (measuredTopOffset > 0 ? Math.min(measuredTopOffset, naturalTopOffset) : naturalTopOffset)
      : measuredTopOffset;
  } catch (_error) {
    topOffset = hmbPickerNaturalTopInset(element, shell);
  }
  let bottomInset = 0;
  try {
    const style = window.getComputedStyle ? window.getComputedStyle(shell) : null;
    bottomInset = Math.max(
      0,
      (parseFloat(style?.paddingBottom || "0") || 0)
      + (parseFloat(style?.borderBottomWidth || "0") || 0),
    );
  } catch (_error) {}
  return Math.max(1, Math.floor(shellHeight - topOffset - bottomInset));
}

function hmbPickerParameterLayoutRow(container, parameterName) {
  if (!container) return null;
  const selector = `[data-parameter-name="${parameterName}"]`;
  let parameterRow = null;
  try {
    parameterRow = container.closest?.(selector) || null;
  } catch (_error) {}
  if (!parameterRow) {
    let current = container.parentElement || null;
    for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
      if (String(current.getAttribute?.("data-parameter-name") || "") === parameterName) {
        parameterRow = current;
        break;
      }
    }
  }
  const layoutRow = parameterRow?.parentElement || null;
  return layoutRow?.style ? layoutRow : null;
}

export function hmbStretchPickerAdaptiveStack(container, layoutRow, preferredShell = null) {
  void layoutRow;
  void preferredShell;
  return hmbApplyPickerHostSizing(container);
}

export function hmbApplyPickerCommandRowReclaim(container) {
  void container;
  return 0;
}

function hmbPickerDominoContainerDelta(startSize, startRequiredSize, requiredDelta) {
  const size = Math.max(0, Math.round(Number(startSize) || 0));
  const required = Math.max(0, Math.round(Number(startRequiredSize) || 0));
  const delta = Math.round(Number(requiredDelta) || 0);
  const startingGap = size - required;
  if (delta > 0) return Math.max(0, delta - Math.max(0, startingGap));
  if (delta < 0) {
    if (startingGap > 1) return 0;
    return -Math.max(0, -delta - Math.max(0, -startingGap));
  }
  return 0;
}

function hmbPickerDominoOuterHeight(startNodeHeight, startRequiredHeight, nextRequiredHeight) {
  const startNode = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(startNodeHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const startRequired = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(startRequiredHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const nextRequired = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(nextRequiredHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const sizeDelta = hmbPickerDominoContainerDelta(startNode, startRequired, nextRequired - startRequired);
  return Math.max(HMB_MIN_NODE_HEIGHT, Math.min(6000, startNode + sizeDelta));
}

function hmbApplyPickerOuterNodeHeight(container, height) {
  void container;
  void height;
  return null;
}

function hmbApplyPickerDominoResizeFrame(container, startNodeHeight, startRequiredHeight) {
  const innerRequired = hmbPickerInnerRequiredHeight(container);
  hmbApplyPickerHostSizing(container, innerRequired);
  void startNodeHeight;
  void startRequiredHeight;
  return {
    innerHeight: innerRequired,
    nodeHeight: 0,
    requiredHeight: innerRequired,
  };
}

function hmbFitPickerHostWithinNode(
  container,
  preferredShell = null,
  requiredInnerHeight = null,
  preferredNodeHeight = 0,
) {
  void preferredShell;
  void preferredNodeHeight;
  return hmbApplyPickerHostSizing(container, requiredInnerHeight);
}

function hmbEnsurePickerNodeFits(container, preferredShell = null, measuredInnerHeight = null) {
  const innerRequired = Math.max(
    HMB_PICKER_CONTENT_FALLBACK_HEIGHT,
    Math.ceil(Number(measuredInnerHeight) || hmbPickerInnerRequiredHeight(container)),
  );
  hmbApplyPickerHostSizing(container, innerRequired);
  void preferredShell;
  return container;
}

function hmbPickerFitMeasurementSignature(container, shell, measuredInnerHeight = null) {
  const dimension = (element, axis) => {
    if (!element) return 0;
    const offsetValue = axis === "width" ? element.offsetWidth : element.offsetHeight;
    if (Number(offsetValue || 0) > 0) return Math.round(Number(offsetValue));
    try {
      const rect = element.getBoundingClientRect?.();
      return Math.round(Number(rect?.[axis] || 0));
    } catch (_error) {
      return 0;
    }
  };
  const innerHeight = Math.max(
    HMB_PICKER_CONTENT_FALLBACK_HEIGHT,
    Math.ceil(Number(measuredInnerHeight) || hmbPickerInnerRequiredHeight(container)),
  );
  const rightStack = container?.querySelector?.(".right-stack");
  const centerStack = container?.querySelector?.(".center-stack");
  return [
    innerHeight,
    dimension(container, "width"),
    dimension(container, "height"),
    dimension(rightStack, "height"),
    dimension(centerStack, "height"),
    dimension(shell, "width"),
    hmbPickerNodeShellHeight(shell),
  ].join(":");
}

export function hmbAlignPickerOuterBottom(container, preferredShell = null, allowShrink = true) {
  void container;
  void preferredShell;
  void allowShrink;
  return { changed: false, height: 0, delta: 0 };
}

function nodeDepthMap(nodes) {
  const byPath = new Map(nodes.map((node) => [clean(node.full_path), node]));
  const memo = new Map();
  const depth = (path) => {
    if (memo.has(path)) return memo.get(path);
    const parent = clean(byPath.get(path)?.parent_path);
    const value = parent && byPath.has(parent) ? depth(parent) + 1 : 0;
    memo.set(path, value);
    return value;
  };
  nodes.forEach((node) => depth(clean(node.full_path)));
  return memo;
}

function filteredVisibleNodes(state) {
  const nodes = Array.isArray(state?.outliner_nodes) ? state.outliner_nodes : [];
  const byPath = new Map(nodes.map((node) => [clean(node.full_path), node]));
  const query = clean(state.outliner_search).toLowerCase();
  const expanded = new Set(state.outliner_expanded);
  if (query) {
    const keep = new Set();
    nodes.forEach((node) => {
      const path = clean(node.full_path);
      const haystack = `${clean(node.name)} ${path} ${clean(node.namespace)}`.toLowerCase();
      if (!haystack.includes(query)) return;
      keep.add(path);
      let parent = clean(node.parent_path);
      while (parent) {
        keep.add(parent);
        parent = clean(byPath.get(parent)?.parent_path);
      }
    });
    return nodes.filter((node) => keep.has(clean(node.full_path)));
  }
  return nodes.filter((node) => {
    let parent = clean(node.parent_path);
    while (parent) {
      if (!expanded.has(parent)) return false;
      parent = clean(byPath.get(parent)?.parent_path);
    }
    return true;
  });
}

export function hmbPickerOutlinerWindow(state, scrollTop = 0, viewportHeight = 0, options = {}) {
  const visible = filteredVisibleNodes(state);
  const rowHeight = Math.max(1, Number(options.rowHeight || HMB_PICKER_OUTLINER_ROW_HEIGHT));
  const maximumRows = Math.max(24, Number(options.maximumRows || HMB_PICKER_OUTLINER_WINDOW_ROWS));
  const overscanRows = Math.max(2, Number(options.overscanRows || HMB_PICKER_OUTLINER_OVERSCAN_ROWS));
  const viewportRows = Math.max(1, Math.ceil(Math.max(0, Number(viewportHeight || 0)) / rowHeight));
  const renderedRows = Math.min(
    maximumRows,
    Math.max(24, viewportRows + (overscanRows * 2)),
  );
  if (visible.length <= renderedRows) {
    return {
      nodes: visible,
      total: visible.length,
      start: 0,
      end: visible.length,
      topSpacer: 0,
      bottomSpacer: 0,
      rowHeight,
      virtualized: false,
    };
  }
  let start = Math.max(0, Math.floor(Math.max(0, Number(scrollTop || 0)) / rowHeight) - overscanRows);
  start = Math.min(start, Math.max(0, visible.length - renderedRows));
  const forcePath = clean(options.forcePath);
  if (forcePath) {
    const forceIndex = visible.findIndex((node) => clean(node?.full_path) === forcePath);
    if (forceIndex >= 0 && (forceIndex < start || forceIndex >= start + renderedRows)) {
      start = Math.max(0, Math.min(
        visible.length - renderedRows,
        forceIndex - Math.floor(renderedRows / 2),
      ));
    }
  }
  const end = Math.min(visible.length, start + renderedRows);
  return {
    nodes: visible.slice(start, end),
    total: visible.length,
    start,
    end,
    topSpacer: start * rowHeight,
    bottomSpacer: Math.max(0, (visible.length - end) * rowHeight),
    rowHeight,
    virtualized: true,
  };
}

function outlinerHtml(state, bindings, tr, locked = false, options = {}) {
  if (!Array.isArray(state?.outliner_nodes) || !state.outliner_nodes.length) {
    return `<div class="empty-pane"><b>${escapeHtml(tr.noPreviewTitle)}</b><span>${escapeHtml(tr.noPreviewBody)}</span></div>`;
  }
  const depthMap = nodeDepthMap(state.outliner_nodes);
  const expanded = new Set(state.outliner_expanded);
  const assignedByPath = new Map(bindings.map((item) => [clean(item.full_dag_path), clean(item.color)]));
  const visibilitySlot = 1;
  const selectedVisibility = state.slot_visibility.find(
    (item) => Number(item?.video_slot || 0) === visibilitySlot,
  );
  const hiddenPaths = new Set(Array.isArray(selectedVisibility?.hidden_paths) ? selectedVisibility.hidden_paths.map(clean) : []);
  const windowed = hmbPickerOutlinerWindow(
    state,
    options.scrollTop,
    options.viewportHeight,
    { forcePath: options.forcePath },
  );
  const spacer = (edge, height) => height > 0
    ? `<div class="outliner-virtual-spacer" data-outliner-spacer="${edge}" style="height:${Math.round(height)}px;flex:0 0 ${Math.round(height)}px" aria-hidden="true"></div>`
    : "";
  return `<div class="outliner-list" role="tree" aria-label="${escapeHtml(tr.outliner)}" data-outliner-total="${windowed.total}" data-outliner-start="${windowed.start}" data-outliner-end="${windowed.end}" data-outliner-virtualized="${windowed.virtualized ? "true" : "false"}">${spacer("top", windowed.topSpacer)}${windowed.nodes.map((node, localIndex) => {
    const visibleIndex = windowed.start + localIndex;
    const path = clean(node.full_path);
    const name = clean(node.name) || path.split("|").pop();
    const hasChildren = Number(node.child_count || 0) > 0;
    const selected = path === state.selected_outliner_path;
    const assignedColor = assignedByPath.get(path) || "";
    const outputVisible = !hiddenPaths.has(path);
    const indent = Number(depthMap.get(path) || 0) * 17;
    const rowTabIndex = selected || (!clean(state.selected_outliner_path) && visibleIndex === 0) ? 0 : -1;
    const toggleLabel = expanded.has(path) ? tr.collapseNode : tr.expandNode;
    const visibilityLabel = outputVisible ? tr.outputOn : tr.outputOff;
    return `<div class="outliner-row ${selected ? "selected" : ""} ${outputVisible ? "" : "output-off"}" data-group-path="${escapeHtml(path)}" title="${escapeHtml(path)}" role="treeitem" tabindex="${rowTabIndex}" aria-level="${Number(depthMap.get(path) || 0) + 1}" aria-posinset="${visibleIndex + 1}" aria-setsize="${windowed.total}" aria-selected="${selected ? "true" : "false"}" ${hasChildren ? `aria-expanded="${expanded.has(path) ? "true" : "false"}"` : ""}>
      <button type="button" class="tree-toggle ${hasChildren ? "" : "leaf"}" data-toggle-path="${escapeHtml(path)}" style="margin-left:${indent}px" aria-label="${escapeHtml(hasChildren ? toggleLabel : name)}" ${hasChildren ? "" : "disabled"}>${hasChildren ? (expanded.has(path) ? "▾" : "▸") : ""}</button>
      <span class="node-icon">${node.node_kind === "mesh" ? "◆" : "◇"}</span>
      <span class="group-name">${escapeHtml(name)}</span>
      ${node.referenced ? `<span class="ref-tag">${escapeHtml(tr.reference)}</span>` : ""}
      ${assignedColor ? `<span class="assigned-chip" style="${hmbPickerColorStyle(assignedColor, state.marker_catalog)}" title="${escapeHtml(assignedColor)}"></span>` : ""}
      <button type="button" class="eye-toggle ${outputVisible ? "on" : "off"}" data-visibility-path="${escapeHtml(path)}" title="${escapeHtml(visibilityLabel)}" aria-label="${escapeHtml(`${name}: ${visibilityLabel}`)}" aria-pressed="${outputVisible ? "true" : "false"}" aria-disabled="${locked ? "true" : "false"}" ${locked ? "disabled" : ""}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg></button>
    </div>`;
  }).join("")}${spacer("bottom", windowed.bottomSpacer)}</div>`;
}

function cameraControlHtml(state, tr, locked) {
  const cameras = state.cameras.filter((camera) => !camera.default_camera || camera.renderable || camera.registered);
  const usable = cameras.length ? cameras : state.cameras;
  if (!usable.length) return `<div class="camera-fixed disabled">${escapeHtml(tr.noCamera)}</div>`;
  if (usable.length === 1) {
    const camera = usable[0];
    return `<div class="camera-fixed"><b>${escapeHtml(clean(camera.name) || clean(camera.full_path))}</b><em>${escapeHtml(tr.fixed)}</em></div>`;
  }
  const selected = usable.find((camera) => clean(camera.full_path) === state.selected_camera) || usable[0];
  return `<details class="camera-dropdown" ${locked ? "data-locked=\"1\"" : ""}>
    <summary><b>${escapeHtml(clean(selected?.name) || clean(selected?.full_path) || tr.selectCamera)}</b><i>▾</i></summary>
    <div class="camera-menu">${usable.map((camera) => {
      const path = clean(camera.full_path);
      const active = path === clean(selected?.full_path);
      return `<button type="button" data-camera-path="${escapeHtml(path)}" class="${active ? "active" : ""}" ${locked ? "disabled" : ""}>
        <b>${escapeHtml(clean(camera.name) || path)}</b>
        <span>${camera.registered ? escapeHtml(tr.registered) : camera.renderable ? escapeHtml(tr.renderable) : escapeHtml(tr.cameraLabel)}</span>
      </button>`;
    }).join("")}</div>
  </details>`;
}

function hmbVideoAssetRole(item) {
  const role = clean(item?.generation_role || item?.video_role || item?.media_kind).toLowerCase();
  if (role.includes("motion")) return "Motion Guide";
  if (role.includes("depth")) return "Depth";
  if (role.includes("mask") || role.includes("color_assignment")) return "Mask";
  if (role.includes("original")) return "Original";
  if (role.includes("color")) return "Color";
  return "Video";
}

function hmbVideoAssetTitle(item, catalogIndex) {
  const explicit = clean(item?.display_name || item?.label || item?.name);
  if (explicit) return explicit;
  const path = hmbVideoAssetPath(item).replace(/\\/g, "/");
  return path.split("/").pop() || `${hmbVideoAssetRole(item)} ${catalogIndex + 1}`;
}

function hmbVideoAssetDetails(item) {
  const fps = Math.max(0, Number(item?.output_fps || item?.source_fps || item?.frame_metadata?.fps || 0));
  const frames = Math.max(0, Number(item?.output_frame_count || item?.source_frame_count || item?.frame_metadata?.frame_count || 0));
  const seconds = Math.max(0, Number(item?.output_duration_seconds || item?.source_duration_seconds || item?.frame_metadata?.duration_seconds || (fps > 0 ? frames / fps : 0)));
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  const duration = seconds > 0 ? `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}` : "--:--";
  const width = Math.max(0, Number(item?.output_width || item?.frame_metadata?.width || item?.frame_metadata?.resolution?.width || 0));
  const height = Math.max(0, Number(item?.output_height || item?.frame_metadata?.height || item?.frame_metadata?.resolution?.height || 0));
  return `${duration}${width && height ? ` · ${width}×${height}` : ""}`;
}

export function hmbVideoAssetRowFingerprint(item, catalogIndex, language, _locked = false) {
  return JSON.stringify([
    hmbVideoAssetPath(item),
    hmbVideoAssetTitle(item, catalogIndex),
    hmbVideoAssetRole(item),
    hmbVideoAssetDetails(item),
    clean(language),
  ]);
}

function hmbVideoAssetCardHtml(item, catalogIndex, order, selectionFull, tr, locked, reorderEnabled = false) {
  const uid = hmbVideoAssetUid(item, catalogIndex);
  const selectedAsset = Number(order || 0) > 0;
  const role = hmbVideoAssetRole(item);
  const title = hmbVideoAssetTitle(item, catalogIndex);
  const source = videoSourceUrl(hmbVideoAssetPath(item));
  const fingerprint = hmbVideoAssetRowFingerprint(item, catalogIndex, tr === TEXT.ko ? "ko" : "en", locked);
  const blocked = !selectedAsset && selectionFull;
  const selectionLabel = selectedAsset ? tr.deselectVideoAsset : tr.selectVideoAsset;
  const media = source
    ? `<video class="video-asset-thumb-media" src="${escapeHtml(source)}" preload="none" muted playsinline draggable="false" aria-hidden="true"></video>`
    : `<span class="video-asset-thumb-fallback">VIDEO</span>`;
  return `<article class="video-asset-card${selectedAsset ? " selected" : ""}${blocked ? " selection-blocked" : ""}" data-video-asset-uid="${escapeHtml(uid)}" data-video-uid="${escapeHtml(uid)}" data-row-fingerprint="${escapeHtml(fingerprint)}" ${selectedAsset ? `data-selected-video-uid="${escapeHtml(uid)}" draggable="${locked || !reorderEnabled ? "false" : "true"}` : "draggable=\"false\""} data-selected-video-order="${Number(order || 0)}">
    <div class="video-asset-thumb">
      ${media}
      <span class="video-asset-role">${escapeHtml(role)}</span>
      ${selectedAsset ? `<span class="selected-video-order">${String(Number(order || 0)).padStart(2, "0")}</span>` : ""}
      <button type="button" class="video-asset-play" data-play-video-uid="${escapeHtml(uid)}" data-video-title="${escapeHtml(title)}" aria-label="${escapeHtml(`${title}: ${tr.playVideo}`)}" aria-pressed="false">▶</button>
    </div>
    <button type="button" class="video-asset-delete" data-delete-video-uid="${escapeHtml(uid)}" aria-label="${escapeHtml(`${title}: ${tr.deleteVideoAsset}`)}" ${locked ? "disabled" : ""}>×</button>
    <div class="video-asset-copy" data-toggle-video-uid="${escapeHtml(uid)}" role="button" tabindex="${blocked || locked ? "-1" : "0"}" aria-disabled="${blocked || locked ? "true" : "false"}" aria-label="${escapeHtml(`${title}: ${selectionLabel}`)}">
      <b class="video-asset-title" title="${escapeHtml(title)}">${escapeHtml(title)}</b>
      <div class="video-asset-details">${escapeHtml(hmbVideoAssetDetails(item))}</div>
    </div>
  </article>`;
}

function videoAssetCardsHtml(state, tr, locked) {
  const selected = hmbSelectedVideoAssets(state);
  const orderByUid = new Map(selected.map((item, index) => [clean(item.video_uid), index + 1]));
  const assets = hmbVideoPickerWorkspaceVideos(state, hmbActivePickerWorkspace(state))
    .filter(({ item }) => item && typeof item === "object" && hmbVideoAssetHasMedia(item))
    .sort((left, right) => {
      const leftOrder = Number(orderByUid.get(hmbVideoAssetUid(left.item, left.catalogIndex)) || 0);
      const rightOrder = Number(orderByUid.get(hmbVideoAssetUid(right.item, right.catalogIndex)) || 0);
      if (leftOrder && rightOrder) return leftOrder - rightOrder;
      if (leftOrder) return -1;
      if (rightOrder) return 1;
      return left.catalogIndex - right.catalogIndex;
    });
  if (!assets.length) {
    return `<div class="video-assets-empty">${escapeHtml(tr.emptyVideoHistory)}</div>`;
  }
  const selectionFull = selected.length >= HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS;
  return assets.map(({ item, catalogIndex }) => hmbVideoAssetCardHtml(
    item,
    catalogIndex,
    Number(orderByUid.get(hmbVideoAssetUid(item, catalogIndex)) || 0),
    selectionFull,
    tr,
    locked,
    selected.length > 1,
  )).join("");
}

export function hmbVideoPickerCompactStructureKey(value) {
  const state = normalize(value);
  const videos = (Array.isArray(state.videos) ? state.videos : []).map((item, index) => ({
    uid: hmbVideoAssetUid(item, index),
    path: hmbVideoAssetPath(item),
    title: hmbVideoAssetTitle(item, index),
    role: hmbVideoAssetRole(item),
    owner: clean(item?.picker_shot_uuid),
  }));
  const shots = (Array.isArray(state.shot_selections) ? state.shot_selections : []).map((shot) => ({
    uuid: clean(shot?.shot_uuid), number: Number(shot?.number || 0), name: clean(shot?.name),
  }));
  const pickerShots = (Array.isArray(state.picker_shots) ? state.picker_shots : []).map((shot) => ({
    uuid: clean(shot?.workspace_uuid), number: Number(shot?.number || 0), name: clean(shot?.name),
    custom: !!shot?.custom_name, bound: clean(shot?.bound_shot_uuid),
    assets: hmbPickerWorkspaceAssetUids(shot),
    selected: Array.isArray(shot?.selected_video_uids) ? shot.selected_video_uids.map(clean).filter(Boolean) : [],
  }));
  return JSON.stringify({
    runtime: clean(state.runtime_instance_id),
    language: clean(state.language),
    status: clean(state.status),
    operation: clean(state.operation_kind),
    pid: Number(state.active_process_pid || 0),
    preview: clean(state.preview_video_uid || state.selected_video_uid),
    originalPreview: !!state.original_preview_enabled,
    viewportMode: clean(state.viewport_mode),
    snapshot: clean(state.active_snapshot_uid),
    publisher: clean(state.shot_publisher_instance_uuid),
    channel: clean(state.channel_uuid),
    videos,
    shots,
    pickerShots,
    activePickerShot: clean(state.active_picker_shot_uuid),
  });
}

export function hmbReconcileVideoPickerCards(container, stateValue, tr = TEXT.en, locked = false) {
  const grid = container?.querySelector?.(".video-asset-grid");
  const ownerDocument = grid?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!grid || !ownerDocument?.createElement) return false;
  const state = normalize(stateValue);
  const selected = hmbSelectedVideoAssets(state);
  const orderByUid = new Map(selected.map((item, index) => [clean(item.video_uid), index + 1]));
  const assets = hmbVideoPickerWorkspaceVideos(state, hmbActivePickerWorkspace(state))
    .filter(({ item }) => item && typeof item === "object" && hmbVideoAssetHasMedia(item))
    .sort((left, right) => {
      const leftOrder = Number(orderByUid.get(hmbVideoAssetUid(left.item, left.catalogIndex)) || 0);
      const rightOrder = Number(orderByUid.get(hmbVideoAssetUid(right.item, right.catalogIndex)) || 0);
      if (leftOrder && rightOrder) return leftOrder - rightOrder;
      if (leftOrder) return -1;
      if (rightOrder) return 1;
      return left.catalogIndex - right.catalogIndex;
    });
  const existingCards = new Map(Array.from(grid.querySelectorAll?.("[data-video-uid]") || []).map(
    (card) => [clean(card.getAttribute?.("data-video-uid")), card],
  ));
  if (!assets.length) {
    existingCards.forEach((card) => card.remove?.());
    let empty = grid.querySelector?.(".video-assets-empty");
    if (!empty) {
      empty = ownerDocument.createElement("div");
      empty.className = "video-assets-empty";
      grid.appendChild?.(empty);
    }
    empty.textContent = tr.emptyVideoHistory;
    const count = container.querySelector?.(".video-selected-count");
    if (count) count.textContent = `0/${HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS}`;
    return true;
  }
  grid.querySelector?.(".video-assets-empty")?.remove?.();
  const retained = new Set();
  const selectionFull = selected.length >= HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS;
  assets.forEach(({ item, catalogIndex }, desiredIndex) => {
    const uid = hmbVideoAssetUid(item, catalogIndex);
    const fingerprint = hmbVideoAssetRowFingerprint(item, catalogIndex, state.language, locked);
    let card = existingCards.get(uid) || null;
    if (!card || clean(card.getAttribute?.("data-row-fingerprint")) !== fingerprint) {
      const template = ownerDocument.createElement("template");
      template.innerHTML = hmbVideoAssetCardHtml(
        item,
        catalogIndex,
        Number(orderByUid.get(uid) || 0),
        selectionFull,
        tr,
        locked,
        selected.length > 1,
      );
      const replacement = template.content?.firstElementChild || template.firstElementChild || null;
      if (!replacement) return;
      replacement.setAttribute?.("data-row-fingerprint", fingerprint);
      hmbMarkPickerDynamicControls(replacement);
      if (card?.parentElement === grid) grid.replaceChild?.(replacement, card);
      else grid.appendChild?.(replacement);
      card = replacement;
      container.__hmbPickerRegionalParseCount = Number(container.__hmbPickerRegionalParseCount || 0) + 1;
    }
    retained.add(uid);
    const atIndex = grid.children?.[desiredIndex] || null;
    if (atIndex !== card) grid.insertBefore?.(card, atIndex);
  });
  existingCards.forEach((card, uid) => { if (!retained.has(uid)) card.remove?.(); });
  hmbApplySelectedVideoAssetOrderToDomNormalized(container, state, tr, locked);
  return true;
}

export function hmbPatchVideoPickerShotSelector(container, stateValue, locked = false) {
  const state = normalize(stateValue);
  const activeWorkspace = hmbActivePickerWorkspace(state);
  const shots = state.shot_publisher_instance_uuid && state.channel_uuid ? state.shot_selections : [];
  const selectors = Array.from(container?.querySelectorAll?.("[data-picker-shot-bind]") || []);
  const fallback = container?.querySelector?.("#shot-selector");
  if (!selectors.length && fallback) selectors.push(fallback);
  let patched = false;
  for (const selector of selectors) {
    const ownerDocument = selector?.ownerDocument || (typeof document !== "undefined" ? document : null);
    if (!ownerDocument?.createElement) continue;
    const requestedWorkspaceUuid = hmbUuid(selector.getAttribute?.("data-picker-shot-bind"));
    const workspace = state.picker_shots.find((row) => row.workspace_uuid === requestedWorkspaceUuid)
      || activeWorkspace;
    if (!workspace) continue;
    const usedByOtherWorkspace = new Set((state.picker_shots || [])
      .filter((row) => row.workspace_uuid !== workspace.workspace_uuid)
      .map((row) => clean(row.bound_shot_uuid)).filter(Boolean));
    const desired = [{ value: "", text: "Only", disabled: false }, ...shots.map((shot) => ({
      value: clean(shot.shot_uuid),
      text: `${String(shot.number).padStart(2, "0")} · ${shot.name}`,
      disabled: usedByOtherWorkspace.has(clean(shot.shot_uuid)),
    }))];
    const existing = new Map(Array.from(selector.options || []).map((option) => [clean(option.value), option]));
    desired.forEach((row, index) => {
      let option = existing.get(row.value) || null;
      if (!option) {
        option = ownerDocument.createElement("option");
        option.value = row.value;
      }
      if (option.textContent !== row.text) option.textContent = row.text;
      option.disabled = !!row.disabled;
      const atIndex = selector.children?.[index] || null;
      if (atIndex !== option) selector.insertBefore?.(option, atIndex);
      existing.delete(row.value);
    });
    existing.forEach((option) => option.remove?.());
    selector.value = clean(workspace.bound_shot_uuid);
    selector.disabled = !!locked || workspace.workspace_uuid !== activeWorkspace?.workspace_uuid;
    selector.setAttribute?.("data-picker-shot-bind", workspace.workspace_uuid);
    selector.setAttribute?.(
      "data-picker-shot-active-bind",
      workspace.workspace_uuid === activeWorkspace?.workspace_uuid ? "true" : "false",
    );
    patched = true;
  }
  const conflict = container?.querySelector?.("#shot-selector-conflict");
  if (conflict) conflict.hidden = true;
  return patched;
}

function hmbVideoPickerRemoteOptionsHtml(state, workspace) {
  const usedByOther = new Set(state.picker_shots
    .filter((row) => row.workspace_uuid !== workspace?.workspace_uuid)
    .map((row) => row.bound_shot_uuid).filter(Boolean));
  return state.shot_publisher_instance_uuid && state.channel_uuid
    ? state.shot_selections.map((shot) => `<option value="${escapeHtml(shot.shot_uuid)}" ${shot.shot_uuid === workspace?.bound_shot_uuid ? "selected" : ""} ${usedByOther.has(shot.shot_uuid) ? "disabled" : ""}>${String(shot.number).padStart(2, "0")} · ${escapeHtml(shot.name)}</option>`).join("")
    : "";
}

function hmbVideoPickerWorkspaceVideos(state, row) {
  const catalog = Array.isArray(state?.videos) ? state.videos : [];
  const byUid = new Map(catalog.map((item, catalogIndex) => [
    hmbVideoAssetUid(item, catalogIndex),
    { item, catalogIndex },
  ]));
  const selected = Array.from(new Set(
    (Array.isArray(row?.selected_video_uids) ? row.selected_video_uids : []).map(clean).filter(Boolean),
  )).slice(0, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
  const selectedOrder = new Map(selected.map((uid, index) => [uid, index + 1]));
  return hmbPickerWorkspaceAssetUids(row).map((uid, assetIndex) => {
    const record = byUid.get(uid);
    return record ? {
      uid,
      order: Number(selectedOrder.get(uid) || 0),
      assetSlot: assetIndex + 1,
      ...record,
    } : null;
  }).filter(Boolean).sort((left, right) => {
    // Compact and expanded views read the same generator order. Selected
    // videos lead in selected_video_uids order; unselected history retains its
    // stable Shot-local ownership order behind them.
    if (left.order && right.order) return left.order - right.order;
    if (left.order) return -1;
    if (right.order) return 1;
    return left.assetSlot - right.assetSlot;
  });
}

function hmbVideoPickerCompactSlotFingerprint(state, video, locked = false, slotIndex = 1) {
  if (!video) return "";
  return JSON.stringify([
    video.uid,
    hmbVideoAssetPath(video.item),
    hmbVideoAssetTitle(video.item, video.catalogIndex),
    clean(state?.language),
    Number(video.order || 0),
    Number(slotIndex || 0),
    !!locked,
  ]);
}

function hmbVideoPickerCompactVideoHtml(state, row, video, tr, locked = false, slotIndex = 1) {
  if (!video) return "";
  const slot = Math.max(1, Math.min(HMB_PICKER_MAX_ASSETS_PER_SHOT, Math.floor(Number(slotIndex || 1))));
  const fingerprint = hmbVideoPickerCompactSlotFingerprint(state, video, locked, slot);
  const title = hmbVideoAssetTitle(video.item, video.catalogIndex);
  const selectedAsset = Number(video.order || 0) > 0;
  const selectionLabel = selectedAsset ? tr.deselectVideoAsset : tr.selectVideoAsset;
  return `<article class="compact-shot-slot compact-shot-asset${selectedAsset ? " selected" : ""}" data-compact-asset-key="${escapeHtml(`${row.workspace_uuid}:video:${video.uid}`)}" data-compact-video-fingerprint="${escapeHtml(fingerprint)}" data-picker-shot-slot="${slot}" data-video-uid="${escapeHtml(video.uid)}" data-picker-shot-video-owner="${escapeHtml(row.workspace_uuid)}" data-selected-video-order="${Number(video.order || 0)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(`${row.name} video ${slot}: ${title}`)}">
      <div class="compact-shot-thumb"><span class="compact-shot-placeholder" aria-hidden="true"><i>VIDEO</i></span><button type="button" class="compact-video-play" data-play-video-uid="${escapeHtml(video.uid)}" data-video-title="${escapeHtml(title)}" aria-label="${escapeHtml(`${title}: ${tr.playVideo || "Play"}`)}" aria-pressed="false">▶</button><small class="compact-slot-number">${String(slot).padStart(2, "0")}</small><button type="button" class="compact-video-delete" data-delete-video-uid="${escapeHtml(video.uid)}" aria-label="${escapeHtml(`${title}: ${tr.deleteVideoAsset}`)}" ${locked ? "disabled" : ""}>×</button></div>
      <button type="button" class="compact-video-select-label" data-toggle-video-uid="${escapeHtml(video.uid)}" aria-pressed="${selectedAsset ? "true" : "false"}" aria-label="${escapeHtml(`${title}: ${selectionLabel}`)}" ${locked ? "disabled" : ""}>${escapeHtml(title)}</button>
    </article>`;
}

function hmbVideoPickerCompactVideosHtml(state, row, tr, locked = false) {
  const videos = hmbVideoPickerWorkspaceVideos(state, row);
  if (!videos.length) return `<span class="compact-shot-empty">${escapeHtml(tr.emptyVideoHistory || "No videos")}</span>`;
  return videos.map((video, index) => (
    hmbVideoPickerCompactVideoHtml(state, row, video, tr, locked, index + 1)
  )).join("");
}

export function hmbVideoPickerCompactSharedPlayer(container, state, uidValue, card) {
  const uid = clean(uidValue);
  const targetCard = card || Array.from(container?.querySelectorAll?.("[data-video-uid]") || [])
    .find((candidate) => clean(candidate.getAttribute?.("data-video-uid")) === uid) || null;
  const thumb = targetCard?.querySelector?.(".compact-shot-thumb") || null;
  const item = (Array.isArray(state?.videos) ? state.videos : [])
    .find((candidate, index) => hmbVideoAssetUid(candidate, index) === uid);
  const source = videoSourceUrl(hmbVideoAssetPath(item));
  const ownerDocument = thumb?.ownerDocument || container?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  if (!uid || !thumb || !source || !ownerDocument?.createElement) return null;
  let player = container.__hmbCompactSharedVideoPlayer || null;
  if (!player) {
    player = ownerDocument.createElement("video");
    player.className = "video-asset-thumb-media compact-shared-video-player";
    player.setAttribute?.("preload", "metadata");
    player.setAttribute?.("playsinline", "");
    player.playsInline = true;
    container.__hmbCompactSharedVideoPlayer = player;
  }
  const previousCard = player.closest?.("[data-video-uid]") || null;
  if (previousCard && previousCard !== targetCard) {
    player.pause?.();
    hmbSyncVideoPickerPlayButtonState(container);
  }
  if (player.parentElement !== thumb) thumb.appendChild?.(player);
  if (clean(player.getAttribute?.("src")) !== source) {
    player.pause?.();
    player.setAttribute?.("src", source);
    player.load?.();
  }
  player.setAttribute?.("data-video-uid", uid);
  return player;
}

export function hmbReleaseVideoPickerCompactSharedPlayer(container) {
  const player = container?.__hmbCompactSharedVideoPlayer || null;
  if (!player) return false;
  hmbSetVideoPickerPlaybackRequest(container);
  try { player.pause?.(); } catch (_error) {}
  try {
    player.removeAttribute?.("src");
    player.load?.();
    player.remove?.();
  } catch (_error) {}
  hmbSyncVideoPickerPlayButtonState(container);
  delete container.__hmbCompactSharedVideoPlayer;
  return true;
}

function hmbVideoPickerCompactShotPanelHtml(state, row, tr, locked = false) {
  const palette = hmbPickerShotPalette(row.number);
  const active = row.workspace_uuid === clean(state.active_picker_shot_uuid);
  const assetCount = hmbPickerWorkspaceAssetUids(row).length;
  const selectedCount = Math.min(row.selected_video_uids.length, HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS);
  return `<article class="compact-shot-row ${active ? "active" : ""} ${assetCount ? "" : "empty"}" data-picker-shot-row="${escapeHtml(row.workspace_uuid)}" data-shot-number="${row.number}" data-picker-shot-layout="compact" aria-current="${active ? "true" : "false"}" style="--local-shot-accent:${palette.accent};--local-shot-deep:${palette.deep};--shot-accent:${palette.accent};--shot-rgb:${palette.rgb.join(",")}">
      <header class="compact-shot-head"><button type="button" class="picker-shot-number" data-picker-shot-activate="${escapeHtml(row.workspace_uuid)}" aria-label="${escapeHtml(row.name)}" aria-pressed="${active ? "true" : "false"}" ${locked ? "disabled" : ""}>${String(row.number).padStart(2, "0")}</button><b class="picker-shot-name-label" data-picker-shot-name>${escapeHtml(row.name)}</b><span class="compact-shot-status">VIDEOS ${assetCount}/10 · USE ${selectedCount}</span><em class="picker-shot-video-count">${assetCount}/${HMB_PICKER_MAX_ASSETS_PER_SHOT}</em><button type="button" class="picker-shot-rename compact-shot-rename" data-picker-shot-rename="${escapeHtml(row.workspace_uuid)}" aria-label="${escapeHtml(`Rename ${row.name}`)}" ${locked ? "disabled" : ""}>✎</button><button type="button" class="compact-shot-load import-video-button" data-picker-shot-load="${escapeHtml(row.workspace_uuid)}" ${locked || assetCount >= HMB_PICKER_MAX_ASSETS_PER_SHOT ? "disabled" : ""}>${escapeHtml(tr.load || tr.importVideoAsset || "LOAD")}</button></header>
      <div class="compact-shot-assets ${assetCount ? "" : "empty"}" data-compact-shot-assets="${escapeHtml(row.workspace_uuid)}">${hmbVideoPickerCompactVideosHtml(state, row, tr, locked)}</div>
    </article>`;
}

function hmbVideoPickerExpandedShotButtonHtml(state, row, _tr, locked = false) {
  const palette = hmbPickerShotPalette(row.number);
  const active = row.workspace_uuid === clean(state.active_picker_shot_uuid);
  return `<article class="picker-shot-tab ${active ? "active" : ""}" data-picker-shot-row="${escapeHtml(row.workspace_uuid)}" data-picker-shot-layout="expanded" style="--local-shot-accent:${palette.accent};--local-shot-deep:${palette.deep}"><button type="button" class="picker-shot-activate" data-picker-shot-activate="${escapeHtml(row.workspace_uuid)}" aria-label="${escapeHtml(row.name)}" aria-pressed="${active ? "true" : "false"}" ${locked ? "disabled" : ""}><span class="picker-shot-number">${String(row.number).padStart(2, "0")}</span></button></article>`;
}

function hmbVideoPickerShotTabsHtml(stateValue, tr, locked = false, mode = "compact") {
  const state = normalize(stateValue);
  return state.picker_shots.map((row) => mode === "expanded"
    ? hmbVideoPickerExpandedShotButtonHtml(state, row, tr, locked)
    : hmbVideoPickerCompactShotPanelHtml(state, row, tr, locked)).join("");
}

function hmbVideoPickerShotActionMarkup(stateValue, tr, locked = false, mode = "compact") {
  void stateValue;
  void tr;
  void locked;
  void mode;
  return "";
}

export function hmbRenderVideoPickerShotWorkspace(stateValue, tr = TEXT.ko, locked = false, mode = "compact") {
  const state = normalize(stateValue);
  const layout = mode === "expanded" ? "expanded" : "compact";
  return {
    tabs: `<div class="picker-shot-tabs${layout === "compact" ? " library-compact-summary video-picker-compact-summary" : ""}" data-picker-shot-tabs data-picker-shot-layout="${layout}">${hmbVideoPickerShotTabsHtml(state, tr, locked, layout)}</div>`,
    actions: hmbVideoPickerShotActionMarkup(state, tr, locked, layout),
  };
}

export function hmbPatchVideoPickerShotWorkspace(
  container,
  stateValue,
  tr = TEXT.ko,
  locked = false,
  loadLocked = undefined,
) {
  const state = normalize(stateValue);
  const resolvedLoadLocked = loadLocked == null
    ? pickerButtonAvailability(
      state,
      clean(state.scene_draft_path || state.scene_request_path || state.scene_path),
    ).operationBusy
    : !!loadLocked;
  const tabs = container?.querySelector?.("[data-picker-shot-tabs]");
  const mode = clean(tabs?.getAttribute?.("data-picker-shot-layout")) === "expanded" ? "expanded" : "compact";
  const ownerDocument = tabs?.ownerDocument || container?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (tabs && ownerDocument?.createElement) {
    const existing = new Map(Array.from(tabs.querySelectorAll?.("[data-picker-shot-row]") || [])
      .map((row) => [clean(row.getAttribute?.("data-picker-shot-row")), row]));
    const retained = new Set();
    state.picker_shots.forEach((shot, desiredIndex) => {
      const workspaceUuid = clean(shot.workspace_uuid);
      const palette = hmbPickerShotPalette(shot.number);
      const active = workspaceUuid === state.active_picker_shot_uuid;
      let row = existing.get(workspaceUuid) || null;
      if (!row) {
        const template = ownerDocument.createElement("template");
        template.innerHTML = mode === "expanded"
          ? hmbVideoPickerExpandedShotButtonHtml(state, shot, tr, locked)
          : hmbVideoPickerCompactShotPanelHtml(state, shot, tr, locked);
        row = template.content?.firstElementChild || template.firstElementChild || null;
        if (!row) return;
        tabs.appendChild?.(row);
        container.__hmbPickerRegionalParseCount = Number(container.__hmbPickerRegionalParseCount || 0) + 1;
      }
      retained.add(workspaceUuid);
      row.classList?.toggle?.("active", active);
      row.style?.setProperty?.("--local-shot-accent", palette.accent);
      row.style?.setProperty?.("--local-shot-deep", palette.deep);
      row.style?.setProperty?.("--shot-accent", palette.accent);
      row.style?.setProperty?.("--shot-rgb", palette.rgb.join(","));
      row.setAttribute?.("aria-current", active ? "true" : "false");
      const activate = row.querySelector?.("[data-picker-shot-activate]");
      activate?.setAttribute?.("data-picker-shot-activate", workspaceUuid);
      activate?.setAttribute?.("aria-pressed", active ? "true" : "false");
      // Page buttons are optimistic and generation-keyed. A prior page echo
      // may still be in flight, but that must not impose a 1.5s click delay.
      if (activate) activate.disabled = resolvedLoadLocked;
      const number = row.querySelector?.(".picker-shot-number");
      if (number) number.textContent = String(shot.number).padStart(2, "0");
      if (mode === "expanded") {
        const atIndex = tabs.children?.[desiredIndex] || null;
        if (atIndex !== row) tabs.insertBefore?.(row, atIndex);
        return;
      }
      const activeRenameInput = row.querySelector?.("[data-picker-shot-rename-input]");
      const name = row.querySelector?.("[data-picker-shot-name]");
      if (!activeRenameInput && name && name.textContent !== shot.name) name.textContent = shot.name;
      const assetCount = hmbPickerWorkspaceAssetUids(shot).length;
      row.classList?.toggle?.("empty", assetCount === 0);
      const selectedCount = Math.min(
        Array.isArray(shot.selected_video_uids) ? shot.selected_video_uids.length : 0,
        HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS,
      );
      const status = row.querySelector?.(".compact-shot-status");
      if (status) status.textContent = `VIDEOS ${assetCount}/10 · USE ${selectedCount}`;
      const count = row.querySelector?.(".picker-shot-video-count");
      if (count) count.textContent = `${assetCount}/${HMB_PICKER_MAX_ASSETS_PER_SHOT}`;
      const rename = row.querySelector?.("[data-picker-shot-rename]");
      rename?.setAttribute?.("data-picker-shot-rename", workspaceUuid);
      rename?.setAttribute?.("aria-label", `Rename ${shot.name}`);
      if (rename) rename.disabled = locked || !!activeRenameInput;
      const remove = row.querySelector?.("[data-picker-shot-delete]");
      remove?.setAttribute?.("data-picker-shot-delete", workspaceUuid);
      remove?.setAttribute?.("aria-label", `Delete ${shot.name}`);
      if (remove) remove.disabled = true;
      const desiredVideos = hmbVideoPickerWorkspaceVideos(state, shot);
      const compactAssets = row.querySelector?.("[data-compact-shot-assets]");
      if (compactAssets && ownerDocument?.createElement) {
        const existingCards = new Map(Array.from(
          compactAssets.querySelectorAll?.("[data-compact-asset-key]") || [],
        ).map((card) => [clean(card.getAttribute?.("data-video-uid")), card]));
        const retainedCards = new Set();
        if (desiredVideos.length) compactAssets.querySelector?.(".compact-shot-empty")?.remove?.();
        desiredVideos.forEach((video, videoIndex) => {
          const slot = videoIndex + 1;
          const desiredFingerprint = hmbVideoPickerCompactSlotFingerprint(state, video, locked, slot);
          let card = existingCards.get(video.uid) || null;
          if (!card || clean(card.getAttribute?.("data-compact-video-fingerprint")) !== desiredFingerprint) {
            const template = ownerDocument.createElement("template");
            template.innerHTML = hmbVideoPickerCompactVideoHtml(state, shot, video, tr, locked, slot);
            const replacement = template.content?.firstElementChild || template.firstElementChild || null;
            if (!replacement) return;
            if (card?.parentElement === compactAssets) compactAssets.replaceChild?.(replacement, card);
            else compactAssets.appendChild?.(replacement);
            card = replacement;
            container.__hmbPickerRegionalParseCount = Number(container.__hmbPickerRegionalParseCount || 0) + 1;
          }
          retainedCards.add(video.uid);
          const atIndex = compactAssets.children?.[videoIndex] || null;
          if (atIndex !== card) compactAssets.insertBefore?.(card, atIndex);
        });
        existingCards.forEach((card, uid) => { if (!retainedCards.has(uid)) card.remove?.(); });
        if (!desiredVideos.length && !compactAssets.querySelector?.(".compact-shot-empty")) {
          const empty = ownerDocument.createElement("span");
          empty.className = "compact-shot-empty";
          empty.textContent = tr.emptyVideoHistory || "No videos";
          compactAssets.appendChild?.(empty);
        }
        compactAssets.classList?.toggle?.("empty", !desiredVideos.length);
      }
      const atIndex = tabs.children?.[desiredIndex] || null;
      if (atIndex !== row) tabs.insertBefore?.(row, atIndex);
    });
    existing.forEach((row, workspaceUuid) => {
      if (!retained.has(workspaceUuid)) row.remove?.();
    });
  }
  const active = hmbActivePickerWorkspace(state);
  const activeControls = container?.querySelector?.("[data-picker-active-shot-controls]");
  if (activeControls && active) {
    activeControls.setAttribute?.("data-picker-active-shot-controls", active.workspace_uuid);
    const activeInput = activeControls.querySelector?.("[data-picker-shot-rename-input]");
    const activeName = activeControls.querySelector?.("[data-picker-shot-name]");
    if (!activeInput && activeName) activeName.textContent = active.name;
    const activeRename = activeControls.querySelector?.("[data-picker-shot-rename]");
    activeRename?.setAttribute?.("data-picker-shot-rename", active.workspace_uuid);
    if (activeRename) activeRename.disabled = locked || !!activeInput;
    const activeDelete = activeControls.querySelector?.("[data-picker-shot-delete]");
    activeDelete?.setAttribute?.("data-picker-shot-delete", active.workspace_uuid);
    if (activeDelete) activeDelete.disabled = true;
  }
  const expandedActiveName = container?.querySelector?.("[data-video-assets-toolbar] [data-picker-shot-name]");
  if (expandedActiveName && active && expandedActiveName.textContent !== active.name) {
    expandedActiveName.textContent = active.name;
  }
  const add = container?.querySelector?.("[data-picker-shot-add]");
  if (add) add.disabled = true;
  for (const load of container?.querySelectorAll?.("#import-video-button,[data-picker-shot-load]") || []) {
    const owner = hmbUuid(load.getAttribute?.("data-picker-shot-load"));
    const targetShot = owner
      ? state.picker_shots.find((row) => row.workspace_uuid === owner)
      : active;
    const targetCount = hmbPickerWorkspaceAssetUids(targetShot).length;
    load.disabled = resolvedLoadLocked
      || !targetShot
      || targetCount >= HMB_PICKER_MAX_ASSETS_PER_SHOT;
  }
  return !!tabs;
}

export function hmbVideoPickerPreviewDescriptor(stateValue, container = null) {
  const state = normalize(stateValue);
  const video = previewVideo(state);
  const uid = clean(video?.video_uid || state.preview_video_uid || state.selected_video_uid);
  const cardPath = clean(video?.video_url || video?.project_video_path || video?.video_path);
  const forceCard = !!uid && clean(container?.__hmbForceVideoPreviewUid) === uid;
  const path = clean(
    (forceCard ? cardPath : "")
    || (state.original_preview_enabled ? state.original_video_url : "")
    || (state.original_preview_enabled ? state.original_video_path : "")
    || cardPath,
  );
  const snapshots = hmbSnapshotHistory(state);
  const descriptorSnapshot = snapshots.find(
    (item) => clean(item.snapshot_uid) === clean(state.active_snapshot_uid),
  ) || (clean(state.viewport_mode).toLowerCase() === "snapshot" ? snapshots.at(-1) : null) || null;
  const snapshotUrl = clean(state.viewport_mode).toLowerCase() === "snapshot"
    ? hmbSnapshotMediaUrl(descriptorSnapshot) : "";
  return snapshotUrl
    ? { kind: "snapshot", uid: clean(descriptorSnapshot?.snapshot_uid), url: snapshotUrl, videoUid: uid }
    : path
      ? { kind: "video", uid, url: videoSourceUrl(path), videoUid: uid }
      : { kind: "empty", uid: "", url: "", videoUid: uid };
}

export function hmbPatchVideoPickerPreviewDom(container, stateValue, tr = TEXT.en, options = {}) {
  const stage = container?.querySelector?.(".compact-preview") || container?.querySelector?.(".viewport-stage");
  const ownerDocument = stage?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!stage || !ownerDocument?.createElement) return null;
  const descriptor = hmbVideoPickerPreviewDescriptor(stateValue, container);
  const status = stage.querySelector?.("#picker-preview-load-status");
  let video = stage.querySelector?.("#picker-video");
  let snapshot = stage.querySelector?.("#picker-snapshot-image");
  let empty = stage.querySelector?.(".viewport-empty");
  if (descriptor.kind === "video") {
    if (snapshot) snapshot.hidden = true;
    if (empty) empty.hidden = true;
    if (!video) {
      video = ownerDocument.createElement("video");
      video.id = "picker-video";
      video.className = "preview-video";
      video.setAttribute?.("playsinline", "");
      video.setAttribute?.("preload", "metadata");
      stage.insertBefore?.(video, status || stage.firstChild || null);
    }
    video.hidden = false;
    if (clean(video.getAttribute?.("src")) !== descriptor.url) {
      video.pause?.();
      video.setAttribute?.("src", descriptor.url);
      try { video.src = descriptor.url; } catch (_error) {}
      video.load?.();
    }
    if (options.autoplay === true) {
      const playResult = video.play?.();
      if (playResult && typeof playResult.catch === "function") {
        playResult.catch((error) => options.onPlaybackError?.(error));
      }
    }
  } else if (descriptor.kind === "snapshot") {
    video?.pause?.();
    if (video) video.hidden = true;
    if (empty) empty.hidden = true;
    if (!snapshot) {
      snapshot = ownerDocument.createElement("img");
      snapshot.id = "picker-snapshot-image";
      snapshot.className = "preview-image";
      snapshot.alt = "Colored snapshot";
      stage.insertBefore?.(snapshot, status || stage.firstChild || null);
    }
    snapshot.hidden = false;
    if (clean(snapshot.getAttribute?.("src")) !== descriptor.url) snapshot.setAttribute?.("src", descriptor.url);
  } else {
    video?.pause?.();
    if (video) video.hidden = true;
    if (snapshot) snapshot.hidden = true;
    if (!empty) {
      empty = ownerDocument.createElement("div");
      empty.className = "viewport-empty";
      const title = ownerDocument.createElement("b");
      const body = ownerDocument.createElement("span");
      empty.appendChild?.(title);
      empty.appendChild?.(body);
      stage.insertBefore?.(empty, status || stage.firstChild || null);
    }
    empty.hidden = false;
    const title = empty.querySelector?.("b");
    const body = empty.querySelector?.("span");
    if (title) title.textContent = tr.noPreviewTitle;
    if (body) body.textContent = tr.noPreviewBody;
  }
  const isPlaying = descriptor.kind === "video" && !!video && !video.paused && !video.ended;
  for (const button of container.querySelectorAll?.("[data-play-video-uid]") || []) {
    const active = descriptor.kind === "video"
      && clean(button.getAttribute?.("data-play-video-uid")) === descriptor.videoUid
      && isPlaying;
    button.setAttribute?.("aria-pressed", active ? "true" : "false");
    button.closest?.(".video-asset-thumb")?.classList?.toggle?.("is-playing", active);
  }
  const viewportLabel = container.querySelector?.(".viewport-title small");
  if (viewportLabel) viewportLabel.textContent = `(${descriptor.kind === "snapshot" ? (tr.snapshot || "Snapshot") : (tr.preview || "Video")})`;
  return descriptor.kind === "video" ? video : descriptor.kind === "snapshot" ? snapshot : empty;
}

export function hmbVideoPickerMediaFrameContext(stateValue) {
  const state = normalize(stateValue);
  const video = previewVideo(state);
  const selected = hmbSelectedVideoAssets(state);
  const previewUid = clean(video?.video_uid || state.preview_video_uid || state.selected_video_uid);
  const previewOrder = selected.findIndex((item) => clean(item.video_uid) === previewUid) + 1;
  const slot = previewOrder > 0
    ? previewOrder
    : clamp(state.selected_video_slot || 1, 1, Math.max(1, selected.length));
  const metadata = selectedFrameMetadata(state, video, slot);
  const rawStart = Number(metadata.start_frame);
  const start = Number.isFinite(rawStart) ? Math.round(rawStart) : 0;
  const rawEnd = Number(metadata.end_frame);
  const end = Number.isFinite(rawEnd) && rawEnd >= start ? Math.round(rawEnd) : start;
  const fps = Math.max(0.000001, Number(metadata.fps || state.source_fps || video?.source_fps || 24));
  const hasRange = Number(metadata.frame_count || 0) > 0 && end >= start;
  return { state, video, previewUid, slot, metadata, start, end, fps, hasRange };
}

export function hmbCreateVideoPickerMediaController(container, options = {}) {
  if (!container || typeof container.querySelector !== "function") {
    return {
      refresh() { return null; },
      seek() { return false; },
      pause() { return false; },
      togglePlayback() { return false; },
      currentVideo() { return null; },
      context() { return hmbVideoPickerMediaFrameContext({}); },
      cleanup() {},
    };
  }
  const initialState = typeof options.currentState === "function" ? options.currentState() : options.state;
  let liveState = normalize(initialState);
  let boundVideo = null;
  let boundListeners = [];
  let disposed = false;

  const text = () => {
    if (typeof options.text === "function") return options.text(liveState) || TEXT.en;
    return TEXT[liveState.language] || TEXT.ko;
  };
  const context = () => hmbVideoPickerMediaFrameContext(liveState);
  const descriptor = () => hmbVideoPickerPreviewDescriptor(liveState, container);
  const currentVideo = () => container.querySelector?.("#picker-video") || null;
  const removeBoundListeners = () => {
    if (boundVideo) {
      boundListeners.forEach(([eventName, handler]) => {
        boundVideo.removeEventListener?.(eventName, handler);
      });
    }
    boundListeners = [];
    boundVideo = null;
  };
  const requestedFrame = (frameContext = context()) => Math.round(clamp(
    Number(container.__hmbViewportFrame ?? frameContext.state.current_frame ?? frameContext.start),
    frameContext.start,
    frameContext.end,
  ));
  const updateFrameUi = (explicitFrame = null) => {
    const frameContext = context();
    const media = currentVideo();
    const mediaFrame = media && descriptor().kind === "video"
      ? frameContext.start + (Number(media.currentTime || 0) * frameContext.fps)
      : requestedFrame(frameContext);
    const frame = Math.round(clamp(
      explicitFrame != null && Number.isFinite(Number(explicitFrame)) ? Number(explicitFrame) : mediaFrame,
      frameContext.start,
      frameContext.end,
    ));
    container.__hmbViewportFrame = frame;
    const seek = container.querySelector?.("#video-seek");
    const frameInput = container.querySelector?.("#video-frame-number");
    if (seek) seek.value = String(frame);
    if (frameInput && frameInput.ownerDocument?.activeElement !== frameInput) frameInput.value = String(frame);
    const frameInfo = container.querySelector?.("#frame-info-frame");
    const timeInfo = container.querySelector?.("#frame-info-time");
    if (frameInfo) frameInfo.textContent = `${frame} / ${frameContext.end}`;
    if (timeInfo) timeInfo.textContent = formatFrameTimecode(frame, frameContext.start, frameContext.fps);
    return frame;
  };
  const updatePlayUi = () => {
    const media = currentVideo();
    const preview = descriptor();
    const requested = preview.kind === "video"
      && !!preview.videoUid
      && hmbVideoPickerRequestedPlaybackUid(container) === preview.videoUid;
    const playing = preview.kind === "video"
      && !!media
      && !media.hidden
      && (requested || (!media.paused && !media.ended));
    const tr = text();
    const playToggle = container.querySelector?.("#video-play-toggle");
    if (playToggle) {
      playToggle.textContent = playing ? "Ⅱ" : "▶";
      playToggle.title = playing ? (tr.pauseVideo || "Pause") : (tr.playVideo || "Play");
      playToggle.setAttribute?.("aria-label", playToggle.title);
      playToggle.setAttribute?.("aria-pressed", playing ? "true" : "false");
    }
    hmbSyncVideoPickerPlayButtonState(container, preview.videoUid, playing, tr);
    return playing;
  };
  const bindCurrentVideo = () => {
    const media = currentVideo();
    if (media === boundVideo) return media;
    removeBoundListeners();
    if (!media || disposed) return media;
    boundVideo = media;
    // Natural completion must restore every card and transport control to ▶.
    media.loop = false;
    const listen = (eventName, handler) => {
      media.addEventListener?.(eventName, handler);
      boundListeners.push([eventName, handler]);
    };
    listen("loadedmetadata", () => {
      if (media !== currentVideo()) return;
      const frameContext = context();
      const frame = requestedFrame(frameContext);
      media.currentTime = Math.max(0, (frame - frameContext.start) / frameContext.fps);
      updateFrameUi(frame);
      updatePlayUi();
    });
    for (const eventName of ["timeupdate", "seeked"]) listen(eventName, () => updateFrameUi());
    listen("play", () => {
      const preview = descriptor();
      hmbSetVideoPickerPlaybackRequest(container, preview.videoUid, preview.kind === "video");
      updatePlayUi();
    });
    for (const eventName of ["pause", "ended"]) listen(eventName, () => {
      hmbSetVideoPickerPlaybackRequest(container);
      updatePlayUi();
    });
    return media;
  };
  const refresh = (stateValue = undefined) => {
    if (disposed) return null;
    const previousContext = context();
    const previousDescriptor = descriptor();
    if (stateValue !== undefined) liveState = normalize(stateValue);
    else if (typeof options.currentState === "function") liveState = normalize(options.currentState());
    const frameContext = context();
    const nextDescriptor = descriptor();
    const requestedUid = hmbVideoPickerRequestedPlaybackUid(container);
    if (requestedUid && requestedUid !== clean(nextDescriptor.videoUid)) {
      hmbSetVideoPickerPlaybackRequest(container);
    }
    const previewIdentityChanged = (
      previousContext.previewUid !== frameContext.previewUid
      || previousDescriptor.kind !== nextDescriptor.kind
      || previousDescriptor.url !== nextDescriptor.url
    );
    if (previewIdentityChanged) {
      container.__hmbViewportFrame = Math.round(clamp(
        Number(frameContext.state.current_frame ?? frameContext.start),
        frameContext.start,
        frameContext.end,
      ));
    }
    const media = bindCurrentVideo();
    const usableVideo = nextDescriptor.kind === "video"
      && !!media
      && !media.hidden
      && !!clean(media.getAttribute?.("src") || media.src);
    const seek = container.querySelector?.("#video-seek");
    const frameInput = container.querySelector?.("#video-frame-number");
    for (const control of [seek, frameInput]) {
      if (!control) continue;
      control.min = String(frameContext.start);
      control.max = String(frameContext.end);
      control.disabled = !usableVideo || !frameContext.hasRange;
      control.setAttribute?.("aria-disabled", control.disabled ? "true" : "false");
    }
    const playToggle = container.querySelector?.("#video-play-toggle");
    if (playToggle) {
      playToggle.disabled = !usableVideo;
      playToggle.setAttribute?.("aria-disabled", playToggle.disabled ? "true" : "false");
    }
    const snapshotCount = hmbSnapshotHistory(frameContext.state).length;
    for (const selector of ["#snapshot-prev", "#snapshot-next"]) {
      const button = container.querySelector?.(selector);
      if (button) button.disabled = snapshotCount < 1;
    }
    const fpsInfo = container.querySelector?.("#frame-info-fps");
    const rangeInfo = container.querySelector?.("#frame-info-range");
    if (fpsInfo) fpsInfo.textContent = Number.isInteger(frameContext.fps)
      ? String(frameContext.fps)
      : frameContext.fps.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
    if (rangeInfo) rangeInfo.textContent = `${frameContext.start}–${frameContext.end}`;
    updateFrameUi(previewIdentityChanged ? requestedFrame(frameContext) : null);
    updatePlayUi();
    return frameContext;
  };
  const seek = (requested) => {
    const frameContext = context();
    const media = bindCurrentVideo();
    if (!media || descriptor().kind !== "video" || !frameContext.hasRange) return false;
    const frame = Math.round(clamp(Number(requested), frameContext.start, frameContext.end));
    container.__hmbViewportFrame = frame;
    media.currentTime = Math.max(0, (frame - frameContext.start) / frameContext.fps);
    updateFrameUi(frame);
    return true;
  };
  const pause = () => {
    const media = currentVideo();
    if (!media) return false;
    hmbSetVideoPickerPlaybackRequest(container);
    media.pause?.();
    updatePlayUi();
    return true;
  };
  const togglePlayback = () => {
    const media = bindCurrentVideo();
    const preview = descriptor();
    if (!media || preview.kind !== "video" || media.hidden) return false;
    const requested = hmbVideoPickerRequestedPlaybackUid(container) === clean(preview.videoUid);
    if (requested || (!media.paused && !media.ended)) {
      hmbSetVideoPickerPlaybackRequest(container);
      media.pause?.();
      updatePlayUi();
      return true;
    }
    hmbSetVideoPickerPlaybackRequest(container, preview.videoUid, true);
    updatePlayUi();
    const playResult = media.play?.();
    if (playResult && typeof playResult.catch === "function") {
      playResult.catch((error) => {
        hmbSetVideoPickerPlaybackRequest(container);
        updatePlayUi();
        options.onPlaybackError?.(error, "Viewport playback");
      });
    }
    return true;
  };
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    hmbSetVideoPickerPlaybackRequest(container);
    removeBoundListeners();
  };
  refresh(liveState);
  return { refresh, seek, pause, togglePlayback, currentVideo, context, cleanup };
}


export function hmbInstallPickerInteractionIsolation(container, cleanupList) {
  if (!container || typeof container.querySelectorAll !== "function" || !Array.isArray(cleanupList)) return;
  const clip = container.querySelector?.(".hmbvp-clip");
  const picker = container.querySelector?.(".hmbvp");
  // The clip keeps `nodrag` so a drag over the widget pans Griptape instead of
  // relocating the node. Broad `nopan` / `nowheel` guards must not survive a
  // remount: open-hand background areas should use Griptape's native
  // grab-to-pan and wheel-to-zoom behavior.
  container.classList?.remove("nodrag", "nopan", "nowheel");
  clip?.classList?.remove("nopan", "nowheel");
  clip?.classList?.add("nodrag");
  picker?.classList?.remove("nodrag", "nopan", "nowheel");
  [
    ".outliner-scroll",
    ".camera-menu",
    ".snapshot-toolbar",
    ".right-stack",
    ".side-section > .section-body",
    ".video-assets-body",
    ".activity-body"
  ].forEach((selector) => {
    container.querySelectorAll(selector).forEach((element) => {
      element?.classList?.remove("nopan", "nowheel");
    });
  });
  const interactionSelectors = [
    "input",
    "textarea",
    "select",
    "button",
    "label",
    "summary",
    "[role='button']",
    "[contenteditable='true']",
    "[data-group-path]",
    "[data-video-uid]",
    "[data-resize-panel]",
    "[data-resize-section]"
  ];
  const interactionSelector = interactionSelectors.join(",");
  // Classes preserve React Flow's native nodrag/nopan/nowheel contract, while
  // four delegated listeners replace four listeners on every row/control.
  // This keeps a 1,000-row Outliner at O(1) event-listener installation cost.
  container.querySelectorAll(interactionSelector).forEach((element) => {
    element.classList?.add("nodrag", "nopan", "nowheel");
  });
  const stopDelegatedInteraction = (event) => {
    let interaction = null;
    try { interaction = event?.target?.closest?.(interactionSelector) || null; } catch (_error) {}
    if (!interaction) return;
    if (typeof container.contains === "function" && !container.contains(interaction)) return;
    event.stopPropagation?.();
  };
  const delegatedEvents = ["pointerdown", "mousedown", "click", "dblclick"];
  delegatedEvents.forEach((eventName) => {
    container.addEventListener?.(eventName, stopDelegatedInteraction);
  });
  const stopNodeDeleteShortcut = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  container.addEventListener?.("keydown", stopNodeDeleteShortcut);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
  }
  cleanupList.push(() => {
    delegatedEvents.forEach((eventName) => {
      container.removeEventListener?.(eventName, stopDelegatedInteraction);
    });
    container.removeEventListener?.("keydown", stopNodeDeleteShortcut);
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
    }
  });
}


function hmbMorphNodeKey(node) {
  if (!node || node.nodeType !== 1) return "";
  const id = clean(node.getAttribute?.("id"));
  if (id) return `id:${id}`;
  for (const name of [
    "data-group-path",
    "data-camera-path",
    "data-video-uid",
    "data-play-video-uid",
    "data-color",
    "data-outliner-spacer",
    "data-section-key",
    "data-resize-panel",
    "data-resize-section",
  ]) {
    const value = clean(node.getAttribute?.(name));
    if (value) return `${name}:${value}`;
  }
  return "";
}

function hmbMorphNodesCompatible(current, desired) {
  if (!current || !desired || current.nodeType !== desired.nodeType) return false;
  if (current.nodeType !== 1) return true;
  if (String(current.tagName || "") !== String(desired.tagName || "")) return false;
  const currentKey = hmbMorphNodeKey(current);
  const desiredKey = hmbMorphNodeKey(desired);
  return !currentKey && !desiredKey ? true : currentKey === desiredKey;
}

export function hmbSyncPickerElementAttributes(current, desired) {
  const desiredNames = new Set(Array.from(desired.attributes || []).map((attribute) => attribute.name));
  for (const attribute of Array.from(current.attributes || [])) {
    if (!desiredNames.has(attribute.name)) current.removeAttribute?.(attribute.name);
  }
  for (const attribute of Array.from(desired.attributes || [])) {
    if (clean(current.getAttribute?.("id")) === "picker-video" && attribute.name === "src") {
      const currentSource = clean(current.getAttribute?.("src"));
      const desiredSource = clean(attribute.value);
      if (currentSource && currentSource !== desiredSource) {
        current.__hmbPendingPickerVideoSource = desiredSource;
        delete current.__hmbPendingPickerVideoOwner;
        continue;
      }
      // A rapid A -> B -> A selection can leave B in this expando while the
      // retained video already shows A. Matching desired/current source owns
      // the cancellation and must prevent the stale B probe from re-staging.
      delete current.__hmbPendingPickerVideoSource;
      delete current.__hmbPendingPickerVideoOwner;
    }
    if (current.getAttribute?.(attribute.name) !== attribute.value) {
      current.setAttribute?.(attribute.name, attribute.value);
    }
  }

  const tagName = String(current.tagName || "").toLowerCase();
  const inputType = clean(current.getAttribute?.("type")).toLowerCase();
  const focused = document?.activeElement === current;
  const textEditing = focused && (
    tagName === "textarea"
    || tagName === "select"
    || (tagName === "input" && inputType !== "checkbox" && inputType !== "radio" && inputType !== "file")
  );
  if ("disabled" in current) current.disabled = !!desired.disabled;
  if ("checked" in current) current.checked = !!desired.checked;
  if ("selected" in current) current.selected = !!desired.selected;
  if ("value" in current && inputType !== "file" && !textEditing) {
    try { current.value = desired.value; } catch (_error) {}
  }
}

function hmbMorphPickerNode(current, desired) {
  if (!hmbMorphNodesCompatible(current, desired)) return desired.cloneNode(true);
  if (current.nodeType === 3 || current.nodeType === 8) {
    if (current.nodeValue !== desired.nodeValue) current.nodeValue = desired.nodeValue;
    return current;
  }
  hmbSyncPickerElementAttributes(current, desired);
  hmbMorphPickerChildren(current, desired);
  return current;
}

function hmbMorphPickerChildren(currentParent, desiredParent) {
  const desiredChildren = Array.from(desiredParent.childNodes || []);
  for (let index = 0; index < desiredChildren.length; index += 1) {
    const desired = desiredChildren[index];
    let current = currentParent.childNodes?.[index] || null;
    if (!hmbMorphNodesCompatible(current, desired)) {
      const desiredKey = hmbMorphNodeKey(desired);
      if (desiredKey) {
        current = Array.from(currentParent.childNodes || [])
          .slice(index + 1)
          .find((candidate) => hmbMorphNodesCompatible(candidate, desired)) || null;
      } else {
        current = null;
      }
      if (current) {
        currentParent.insertBefore(current, currentParent.childNodes?.[index] || null);
      } else {
        currentParent.insertBefore(desired.cloneNode(true), currentParent.childNodes?.[index] || null);
        current = currentParent.childNodes?.[index] || null;
      }
    }
    const morphed = hmbMorphPickerNode(current, desired);
    if (morphed !== current) currentParent.replaceChild(morphed, current);
  }
  while ((currentParent.childNodes?.length || 0) > desiredChildren.length) {
    currentParent.removeChild(currentParent.lastChild);
  }
}

function hmbMarkPickerDynamicControls(root) {
  if (!root?.querySelectorAll) return;
  for (const element of root.querySelectorAll(
    "button, input, select, textarea, [role='button'], [role='treeitem']",
  )) {
    element.classList?.add?.("nodrag", "nopan", "nowheel");
  }
}

export function hmbRenderPickerOutlinerLocal(container, state, tr, locked = false, options = {}) {
  const scroll = container?.querySelector?.(".outliner-scroll");
  const ownerDocument = scroll?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!scroll || !ownerDocument?.createElement) return false;
  const activeElement = ownerDocument.activeElement;
  const activePath = scroll.contains?.(activeElement)
    ? clean(activeElement?.closest?.("[data-group-path]")?.getAttribute?.("data-group-path"))
    : "";
  const restoreFocusPath = clean(options.focusPath || activePath);
  const scrollTop = Number(scroll.scrollTop || 0);
  const scrollLeft = Number(scroll.scrollLeft || 0);
  const template = ownerDocument.createElement("template");
  template.innerHTML = outlinerHtml(state, selectedBindings(state, 1), tr, locked, {
    scrollTop,
    viewportHeight: Number(scroll.clientHeight || 0),
    forcePath: clean(options.forcePath || restoreFocusPath),
  });
  if (!template.content) return false;
  hmbMorphPickerChildren(scroll, template.content);
  scroll.scrollTop = scrollTop;
  scroll.scrollLeft = scrollLeft;
  hmbMarkPickerDynamicControls(scroll);
  if (restoreFocusPath) {
    Array.from(scroll.querySelectorAll?.("[data-group-path]") || [])
      .find((row) => clean(row.getAttribute?.("data-group-path")) === restoreFocusPath)
      ?.focus?.({ preventScroll: true });
  }
  return true;
}

export function hmbApplyPickerPaletteSelectionToDom(container, state, locked = false) {
  const selectedPath = clean(state?.selected_outliner_path);
  for (const button of container?.querySelectorAll?.("[data-color]") || []) {
    const active = clean(button.getAttribute?.("data-color")) === clean(state?.selected_color);
    if (active) button.classList?.add?.("active");
    else button.classList?.remove?.("active");
    button.disabled = locked || !selectedPath;
  }
}

export function hmbApplyPickerCameraSelectionToDom(container, state) {
  const selectedPath = clean(state?.selected_camera);
  let selectedButton = null;
  for (const button of container?.querySelectorAll?.("[data-camera-path]") || []) {
    const active = clean(button.getAttribute?.("data-camera-path")) === selectedPath;
    if (active) {
      button.classList?.add?.("active");
      selectedButton = button;
    } else {
      button.classList?.remove?.("active");
    }
  }
  const selectedCamera = (Array.isArray(state?.cameras) ? state.cameras : [])
    .find((camera) => clean(camera?.full_path) === selectedPath);
  const label = clean(selectedButton?.querySelector?.("b")?.textContent)
    || clean(selectedCamera?.name)
    || clean(selectedCamera?.full_path);
  const summary = container?.querySelector?.(".camera-dropdown summary b");
  if (summary && label) summary.textContent = label;
  const details = container?.querySelector?.(".camera-dropdown");
  if (details && "open" in details) details.open = false;
  return !!selectedButton;
}

export function hmbApplyPickerResolutionToDom(container, width, height) {
  const select = container?.querySelector?.("#playblast-resolution");
  if (!select) return false;
  const requested = `${Math.max(1, Number(width || 0))}x${Math.max(1, Number(height || 0))}`;
  const matched = Array.from(select.options || []).some((option) => option.value === requested);
  if (!matched) return false;
  select.value = requested;
  return true;
}

export function hmbSetPickerVisibilityBusy(container, busy) {
  for (const button of container?.querySelectorAll?.("[data-visibility-path]") || []) {
    button.disabled = !!busy;
    button.setAttribute?.("aria-disabled", busy ? "true" : "false");
  }
}

export function hmbApplySnapshotNavigationFeedback(container, snapshot, tr, frameStart, fps) {
  const snapshotUrl = hmbSnapshotMediaUrl(snapshot);
  const frame = Number(snapshot?.frame || frameStart || 0);
  const image = container?.querySelector?.("#picker-snapshot-image");
  const title = container?.querySelector?.(".viewport-title small");
  if (title) title.textContent = `(${clean(tr?.snapshot) || "Snapshot"})`;
  if (image && snapshotUrl) {
    image.setAttribute?.("src", snapshotUrl);
    try { image.src = snapshotUrl; } catch (_error) {}
    const frameInput = container?.querySelector?.("#video-frame-number");
    const seek = container?.querySelector?.("#video-seek");
    const frameInfo = container?.querySelector?.("#frame-info-frame");
    const timeInfo = container?.querySelector?.("#frame-info-time");
    if (frameInput) frameInput.value = String(Math.round(frame));
    if (seek) seek.value = String(Math.round(frame));
    if (frameInfo) {
      const end = Math.round(Number(frameInput?.max || seek?.max || frame));
      frameInfo.textContent = `${Math.round(frame)} / ${end}`;
    }
    if (timeInfo) timeInfo.textContent = formatFrameTimecode(frame, frameStart, fps);
    return true;
  }
  const panel = container?.querySelector?.(".viewport-panel");
  panel?.classList?.add?.("is-switching");
  panel?.setAttribute?.("aria-busy", "true");
  return false;
}

export function hmbClearPickerPreviewLoadFailure(container) {
  const status = container?.querySelector?.("#picker-preview-load-status");
  if (!status) return false;
  status.hidden = true;
  status.setAttribute?.("hidden", "");
  status.removeAttribute?.("data-preview-load-failed");
  const message = status.querySelector?.("[data-preview-load-message]");
  if (message) message.textContent = "";
  return true;
}

export function hmbShowPickerPreviewLoadFailure(container, messageText) {
  const status = container?.querySelector?.("#picker-preview-load-status");
  if (!status) return false;
  const message = status.querySelector?.("[data-preview-load-message]");
  const retry = status.querySelector?.("#retry-picker-preview-load");
  if (message) {
    message.textContent = clean(messageText)
      || "The selected video could not be loaded. The previous preview is still shown.";
  }
  if (retry) retry.disabled = false;
  status.setAttribute?.("role", "alert");
  status.setAttribute?.("aria-live", "assertive");
  status.setAttribute?.("data-preview-load-failed", "true");
  status.removeAttribute?.("hidden");
  status.hidden = false;
  return true;
}

export function hmbStagePickerViewportVideoSource(
  video,
  cleanupList,
  onReady = () => {},
  onFailure = () => {},
) {
  const desiredSource = clean(video?.__hmbPendingPickerVideoSource);
  if (!video || !desiredSource) return false;
  const retryAfterMotion = () => hmbStagePickerViewportVideoSource(
    video,
    cleanupList,
    onReady,
    onFailure,
  );
  if (video.closest?.(".hmbvp")?.getAttribute?.("data-canvas-motion") === "true") {
    video.__hmbPickerResumeProbe = retryAfterMotion;
    if (Array.isArray(cleanupList)) {
      cleanupList.push(() => {
        if (video.__hmbPickerResumeProbe === retryAfterMotion) delete video.__hmbPickerResumeProbe;
      });
    }
    return true;
  }
  if (desiredSource === clean(video.getAttribute?.("src"))) {
    if (clean(video.__hmbPendingPickerVideoSource) === desiredSource) {
      delete video.__hmbPendingPickerVideoSource;
      delete video.__hmbPendingPickerVideoOwner;
    }
    return false;
  }
  const ownerToken = {};
  video.__hmbPendingPickerVideoOwner = ownerToken;
  const ownerDocument = video.ownerDocument || (typeof document !== "undefined" ? document : null);
  const probe = ownerDocument?.createElement?.("video");
  let disposed = false;
  let fallbackTimer = null;
  const removeProbeListeners = () => {
    probe?.removeEventListener?.("loadeddata", applySource);
    probe?.removeEventListener?.("canplay", applySource);
    probe?.removeEventListener?.("error", abandonSource);
  };
  const releaseProbeSource = () => {
    try {
      probe?.removeAttribute?.("src");
      probe?.load?.();
    } catch (_error) {}
  };
  const ownsPendingSource = () => (
    clean(video.__hmbPendingPickerVideoSource) === desiredSource
    && video.__hmbPendingPickerVideoOwner === ownerToken
  );
  const clearOwnedPendingSource = () => {
    if (ownsPendingSource()) {
      delete video.__hmbPendingPickerVideoSource;
      delete video.__hmbPendingPickerVideoOwner;
      return true;
    }
    return false;
  };
  const clearOwnedProbeHooks = () => {
    if (video.__hmbPickerSuspendProbe === suspendProbe) delete video.__hmbPickerSuspendProbe;
    if (video.__hmbPickerResumeProbe === retryAfterMotion) delete video.__hmbPickerResumeProbe;
  };
  const suspendProbe = () => {
    if (disposed) return;
    disposed = true;
    removeProbeListeners();
    if (fallbackTimer) clearTimeout(fallbackTimer);
    fallbackTimer = null;
    if (video.__hmbPendingPickerVideoOwner === ownerToken) {
      // Keep the desired source queued, but release the decoder and owner.
      delete video.__hmbPendingPickerVideoOwner;
      video.__hmbPickerResumeProbe = retryAfterMotion;
    }
    if (video.__hmbPickerSuspendProbe === suspendProbe) delete video.__hmbPickerSuspendProbe;
    releaseProbeSource();
  };
  video.__hmbPickerSuspendProbe = suspendProbe;
  const applySource = () => {
    if (disposed) return;
    removeProbeListeners();
    if (fallbackTimer) clearTimeout(fallbackTimer);
    fallbackTimer = null;
    if (!ownsPendingSource()) {
      releaseProbeSource();
      return;
    }
    video.pause?.();
    video.setAttribute?.("src", desiredSource);
    try { video.src = desiredSource; } catch (_error) {}
    clearOwnedPendingSource();
    clearOwnedProbeHooks();
    video.load?.();
    releaseProbeSource();
    onReady();
  };
  const abandonSource = () => {
    if (disposed) return;
    removeProbeListeners();
    if (fallbackTimer) clearTimeout(fallbackTimer);
    fallbackTimer = null;
    const owned = clearOwnedPendingSource();
    clearOwnedProbeHooks();
    releaseProbeSource();
    if (owned) onFailure();
  };
  if (!probe) {
    abandonSource();
    return true;
  }
  probe.preload = "auto";
  probe.muted = true;
  probe.addEventListener?.("loadeddata", applySource, { once: true });
  probe.addEventListener?.("canplay", applySource, { once: true });
  probe.addEventListener?.("error", abandonSource, { once: true });
  try { probe.src = desiredSource; } catch (_error) { abandonSource(); return true; }
  // A slow or broken replacement must never blank a valid retained frame.
  // The next authoritative render may retry, but this attempt keeps current src.
  fallbackTimer = setTimeout(abandonSource, HMB_PICKER_VIDEO_PRELOAD_TIMEOUT_MS);
  if (Array.isArray(cleanupList)) {
    cleanupList.push(() => {
      disposed = true;
      removeProbeListeners();
      if (fallbackTimer) clearTimeout(fallbackTimer);
      fallbackTimer = null;
      clearOwnedPendingSource();
      clearOwnedProbeHooks();
      releaseProbeSource();
    });
  }
  return true;
}

const HMB_PICKER_PRESERVED_SCROLL_SELECTORS = [
  ".main-grid",
  ".outliner-scroll",
  ".right-stack",
  ".side-section > .section-body",
  ".activity-body",
  "#activity-log-view",
  ".camera-menu",
];

function hmbPickerScrollNearEnd(element) {
  if (!element) return true;
  const scrollHeight = Number(element.scrollHeight || 0);
  const clientHeight = Number(element.clientHeight || 0);
  const scrollTop = Number(element.scrollTop || 0);
  return scrollHeight - clientHeight - scrollTop <= 4;
}

function hmbFindPickerElementByMorphKey(container, key) {
  if (!container || !key) return null;
  return Array.from(container.querySelectorAll?.("*") || [])
    .find((element) => hmbMorphNodeKey(element) === key) || null;
}

function hmbCapturePickerViewState(container) {
  const scroll = [];
  const seen = new Set();
  HMB_PICKER_PRESERVED_SCROLL_SELECTORS.forEach((selector) => {
    Array.from(container?.querySelectorAll?.(selector) || []).forEach((element, index) => {
      if (seen.has(element)) return;
      seen.add(element);
      scroll.push({
        element,
        selector,
        index,
        key: hmbMorphNodeKey(element),
        top: Number(element.scrollTop || 0),
        left: Number(element.scrollLeft || 0),
        followEnd: hmbPickerScrollNearEnd(element),
      });
    });
  });

  const allDetails = Array.from(container?.querySelectorAll?.("details") || []);
  const openDetails = allDetails.filter((element) => element.open).map((element) => ({
    element,
    index: allDetails.indexOf(element),
    key: hmbMorphNodeKey(element),
  }));
  const activeElement = typeof document !== "undefined" ? document.activeElement : null;
  let focus = null;
  if (activeElement && container?.contains?.(activeElement)) {
    focus = {
      element: activeElement,
      key: hmbMorphNodeKey(activeElement),
      selectionStart: Number.isFinite(Number(activeElement.selectionStart)) ? Number(activeElement.selectionStart) : null,
      selectionEnd: Number.isFinite(Number(activeElement.selectionEnd)) ? Number(activeElement.selectionEnd) : null,
      selectionDirection: clean(activeElement.selectionDirection),
    };
  }
  return { scroll, openDetails, focus };
}

function hmbResolvePickerViewElement(container, snapshot) {
  if (!snapshot) return null;
  if (snapshot.element && container?.contains?.(snapshot.element)) return snapshot.element;
  if (snapshot.key) {
    const keyed = hmbFindPickerElementByMorphKey(container, snapshot.key);
    if (keyed) return keyed;
  }
  if (snapshot.selector) {
    return Array.from(container?.querySelectorAll?.(snapshot.selector) || [])[snapshot.index || 0] || null;
  }
  return null;
}

function hmbRestorePickerViewState(container, snapshot) {
  if (!container || !snapshot) return;
  for (const detailsState of snapshot.openDetails || []) {
    const details = hmbResolvePickerViewElement(container, {
      ...detailsState,
      selector: "details",
    });
    if (details) details.open = true;
  }

  const focusState = snapshot.focus;
  const focusTarget = hmbResolvePickerViewElement(container, focusState);
  if (focusTarget && typeof focusTarget.focus === "function") {
    try { focusTarget.focus({ preventScroll: true }); } catch (_error) {
      try { focusTarget.focus(); } catch (_focusError) {}
    }
    if (
      focusState.selectionStart !== null
      && focusState.selectionEnd !== null
      && typeof focusTarget.setSelectionRange === "function"
    ) {
      try {
        const length = String(focusTarget.value == null ? "" : focusTarget.value).length;
        focusTarget.setSelectionRange(
          Math.min(length, focusState.selectionStart),
          Math.min(length, focusState.selectionEnd),
          focusState.selectionDirection || undefined,
        );
      } catch (_error) {}
    }
  }

  for (const scrollState of snapshot.scroll || []) {
    const element = hmbResolvePickerViewElement(container, scrollState);
    if (!element) continue;
    element.scrollLeft = scrollState.left;
    element.scrollTop = scrollState.followEnd ? element.scrollHeight : scrollState.top;
  }
}

function hmbRenderPickerActivityLog(logView, state, tr) {
  if (!logView) return;
  const followEnd = hmbPickerScrollNearEnd(logView);
  const scrollTop = Number(logView.scrollTop || 0);
  const scrollLeft = Number(logView.scrollLeft || 0);
  logView.innerHTML = hmbActivityLogHtml(state, tr);
  logView.scrollTop = followEnd ? logView.scrollHeight : scrollTop;
  logView.scrollLeft = scrollLeft;
}

function hmbAppendImmediateActivityLogRow(logView, level, message) {
  if (!logView) return;
  const entry = {
    time: currentLogTime(),
    level: hmbNormalizeActivityLevel(level),
    message: hmbSummarizeActivityMessage(message),
  };
  if (!entry.message) return;
  logView.querySelector?.(".activity-log-empty")?.remove?.();
  logView.insertAdjacentHTML?.("beforeend", hmbActivityLogRowHtml(entry));
  const rows = Array.from(logView.querySelectorAll?.(".activity-log-row") || []);
  rows.slice(0, Math.max(0, rows.length - HMB_ACTIVITY_LOG_MAX_ROWS)).forEach((row) => row.remove?.());
  logView.scrollTop = logView.scrollHeight;
}

export function hmbRenderPickerMarkup(container, markup) {
  if (!container) return "none";
  const text = String(markup || "");
  container.__hmbPickerFullParseCount = Number(container.__hmbPickerFullParseCount || 0) + 1;
  if (!container.firstChild || !document?.createElement) {
    container.innerHTML = text;
    return "mount";
  }
  const template = document.createElement("template");
  template.innerHTML = text;
  const fragment = template.content;
  if (!fragment) {
    container.innerHTML = text;
    return "mount";
  }
  hmbMorphPickerChildren(container, fragment);
  return "morph";
}

export function hmbVideoPickerIsHostMeasurementClone(container) {
  if (!container) return false;
  let current = container;
  for (let index = 0; current && index < 48; index += 1) {
    const classList = current.classList;
    const exactHostMeasurementWrapper = !!(
      classList?.contains?.("absolute")
      && classList?.contains?.("left-0")
      && classList?.contains?.("right-0")
      && classList?.contains?.("pointer-events-none")
    );
    const explicitMeasurementMarker = [
      "data-hmb-host-measurement",
      "data-host-measurement",
      "data-measurement",
      "data-measurement-copy",
      "data-measurement-clone",
      "data-hidden-measurement",
    ].some((name) => {
      try {
        if (!current.hasAttribute?.(name)) return false;
        const value = String(current.getAttribute?.(name) || "").trim().toLowerCase();
        return !["false", "0", "off", "no"].includes(value);
      } catch (_error) {
        return false;
      }
    });
    let hidden = current.hidden === true || current.hasAttribute?.("hidden") === true;
    try {
      const ariaHidden = String(current.getAttribute?.("aria-hidden") || "").trim().toLowerCase();
      const inlineVisibility = String(current.style?.visibility || "").trim().toLowerCase();
      const inlineDisplay = String(current.style?.display || "").trim().toLowerCase();
      hidden = hidden
        || ariaHidden === "true"
        || ["hidden", "collapse"].includes(inlineVisibility)
        || inlineDisplay === "none";
    } catch (_error) {}
    if (!hidden) {
      try {
        const ownerView = current.ownerDocument?.defaultView
          || (typeof window !== "undefined" ? window : null);
        const computed = ownerView?.getComputedStyle?.(current);
        const computedVisibility = String(computed?.visibility || "").trim().toLowerCase();
        const computedDisplay = String(computed?.display || "").trim().toLowerCase();
        hidden = ["hidden", "collapse"].includes(computedVisibility) || computedDisplay === "none";
      } catch (_error) {}
    }
    // A host measurement marker is authoritative. Generic hidden state alone
    // is not: a legitimate live node can be temporarily hidden in an inactive
    // tab/offscreen branch. Require the known inert measurement wrapper when
    // visibility/hidden/aria-hidden is the only evidence.
    if (explicitMeasurementMarker || (exactHostMeasurementWrapper && hidden)) return true;
    current = hmbPickerComposedParent(current);
  }
  return false;
}

// Griptape can keep the raw-widget controller alive while replacing the
// parameter row's children after a mode/height reconciliation.  A controller
// update is not guaranteed after that replacement, so update-time recovery
// alone can leave the visible VideoPicker completely empty.  Watch only this
// widget container and rebuild on the next settled frame when its authored
// root has actually disappeared.  Intentional compact/full DOM swaps finish
// synchronously and therefore still have a root by the time this guard runs.
export function hmbInstallVideoPickerMountedRootGuard(
  container,
  cleanupList = [],
  recoverMountedRoot = null,
) {
  if (!container) return { schedule() {}, inspect() { return false; }, cleanup() {} };
  let disposed = false;
  let recoveryFrame = 0;
  let recovering = false;
  let lifecycleObserver = null;
  const useAnimationFrame = typeof requestAnimationFrame === "function";
  const frame = useAnimationFrame
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 0);
  const cancelFrame = useAnimationFrame && typeof cancelAnimationFrame === "function"
    ? cancelAnimationFrame
    : (handle) => clearTimeout(handle);
  const hasMountedRoot = () => Boolean(
    container.querySelector?.(".hmbvp")
    && container.querySelector?.(".hmbvp-clip"),
  );
  const inspect = () => {
    recoveryFrame = 0;
    if (
      disposed
      || recovering
      || container.__hmbVideoPickerDeleted === true
      || hmbVideoPickerIsHostMeasurementClone(container)
      || hasMountedRoot()
    ) return false;
    if (container.__hmbVideoPickerViewTransition === true) {
      schedule();
      return false;
    }
    if (typeof recoverMountedRoot !== "function") return false;
    recovering = true;
    try {
      return recoverMountedRoot() === true;
    } finally {
      recovering = false;
    }
  };
  const schedule = () => {
    if (disposed || recoveryFrame) return;
    recoveryFrame = frame(inspect);
  };
  const ownerDocument = container.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  const Observer = ownerDocument?.defaultView?.MutationObserver
    || (typeof MutationObserver === "function" ? MutationObserver : null);
  if (Observer) {
    try {
      lifecycleObserver = new Observer(schedule);
      lifecycleObserver.observe?.(container, { childList: true });
    } catch (_error) {
      lifecycleObserver?.disconnect?.();
      lifecycleObserver = null;
    }
  }
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    if (recoveryFrame) cancelFrame(recoveryFrame);
    recoveryFrame = 0;
    lifecycleObserver?.disconnect?.();
    lifecycleObserver = null;
    if (container.__hmbVideoPickerMountedRootGuardSchedule === schedule) {
      delete container.__hmbVideoPickerMountedRootGuardSchedule;
    }
  };
  container.__hmbVideoPickerMountedRootGuardSchedule = schedule;
  if (Array.isArray(cleanupList)) cleanupList.push(cleanup);
  return { schedule, inspect, cleanup };
}

function hmbVideoPickerCompactMeasurementHeightFromNormalizedState(state) {
  const rows = (Array.isArray(state.picker_shots) ? state.picker_shots : [])
    .slice(0, HMB_SHOT_ROUTING_MAX_SHOTS);
  const effectiveRows = rows.length ? rows : [{ video_asset_uids: [] }];
  const shotHeight = effectiveRows.reduce((total, row) => (
    total + (hmbPickerWorkspaceAssetUids(row).length
      ? HMB_VIDEO_PICKER_COMPACT_FIXED_SHOT_HEIGHT
      : HMB_VIDEO_PICKER_COMPACT_EMPTY_SHOT_HEIGHT)
  ), 0);
  return HMB_VIDEO_PICKER_COMPACT_MEASUREMENT_BASE_HEIGHT
    + shotHeight
    + (HMB_VIDEO_PICKER_COMPACT_SHOT_GAP * Math.max(0, effectiveRows.length - 1));
}

export function hmbVideoPickerCompactMeasurementHeight(value) {
  return hmbVideoPickerCompactMeasurementHeightFromNormalizedState(normalize(value));
}

export function hmbSyncVideoPickerHostMeasurement(container, value, expanded = false) {
  void container;
  void value;
  void expanded;
  return 0;
}

export function hmbMountVideoPickerHostMeasurement(container, props = {}, options = {}) {
  if (!container) return null;
  container.__hmbVideoPickerDeleted = false;
  container.setAttribute?.("data-hmb-video-picker-host-measurement", "true");
  let placeholder = container.querySelector?.("[data-hmb-video-picker-measurement-box]") || null;
  if (!placeholder) {
    const doc = container.ownerDocument || (typeof document !== "undefined" ? document : null);
    placeholder = doc?.createElement?.("div") || null;
    if (placeholder) {
      placeholder.setAttribute?.("data-hmb-video-picker-measurement-box", "true");
      placeholder.setAttribute?.("aria-hidden", "true");
      placeholder.style?.setProperty?.("display", "block");
      placeholder.style?.setProperty?.("width", "100%");
      placeholder.style?.setProperty?.("pointer-events", "none");
      container.replaceChildren?.(placeholder);
    }
  }
  let latestProps = props || {};
  let disposed = false;
  let lifecycleObserver = null;
  let promotionFrame = 0;
  const frame = typeof requestAnimationFrame === "function"
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 0);
  const cancelFrame = typeof cancelAnimationFrame === "function"
    ? cancelAnimationFrame
    : (handle) => clearTimeout(handle);
  const applyMeasurement = (nextProps = latestProps, forcedExpanded = null) => {
    if (nextProps && typeof nextProps === "object") latestProps = nextProps;
    if (!placeholder?.style) return HMB_VIDEO_PICKER_COMPACT_BOOTSTRAP_HEIGHT;
    const registeredViewMode = hmbVideoPickerStoredViewMode(container);
    const expanded = typeof forcedExpanded === "boolean"
      ? forcedExpanded
      : registeredViewMode === true;
    const measurementHeight = expanded
      ? HMB_VIDEO_PICKER_EXPANDED_MEASUREMENT_HEIGHT
      : hmbVideoPickerCompactMeasurementHeight(hmbPickerStateFromProps(latestProps));
    const pixels = `${measurementHeight}px`;
    hmbSetPickerStyleIfChanged(placeholder, "height", pixels);
    hmbSetPickerStyleIfChanged(placeholder, "min-height", pixels);
    hmbSetPickerStyleIfChanged(placeholder, "max-height", pixels);
    hmbSetPickerStyleIfChanged(placeholder, "overflow", "hidden");
    hmbSetPickerStyleIfChanged(placeholder, "box-sizing", "border-box");
    placeholder.setAttribute?.("data-hmb-video-picker-measurement-height", String(measurementHeight));
    return measurementHeight;
  };
  applyMeasurement(props || {});
  const promoteLive = typeof options?.promoteLive === "function"
    ? options.promoteLive
    : (nextProps) => HMBVideoPickerLibraryWidget(container, nextProps || {});
  const promoteIfVisible = () => {
    promotionFrame = 0;
    if (disposed || hmbVideoPickerIsHostMeasurementClone(container)) return false;
    const promotedProps = latestProps || {};
    cleanup();
    promoteLive(promotedProps);
    return true;
  };
  const schedulePromotionCheck = () => {
    if (disposed || promotionFrame) return;
    promotionFrame = frame(promoteIfVisible);
  };
  const ownerDocument = container.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  const Observer = ownerDocument?.defaultView?.MutationObserver
    || (typeof MutationObserver === "function" ? MutationObserver : null);
  if (Observer) {
    try {
      lifecycleObserver = new Observer(schedulePromotionCheck);
      // Observe only the widget container. Never subscribe to React Flow node,
      // pane, viewport or canvas mutations.
      lifecycleObserver.observe?.(container, {
        attributes: true,
        childList: true,
        attributeFilter: ["class", "hidden", "style"],
      });
    } catch (_error) {
      lifecycleObserver?.disconnect?.();
      lifecycleObserver = null;
    }
  }
  // Host 0.122 can re-use the initially hidden contentRef as the visible row
  // without invoking the widget factory a second time. Check the settled
  // mount even when that transition does not mutate an observed attribute.
  schedulePromotionCheck();
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    if (promotionFrame) cancelFrame(promotionFrame);
    promotionFrame = 0;
    lifecycleObserver?.disconnect?.();
    lifecycleObserver = null;
    if (container.__hmbVideoPickerCleanup === cleanup) delete container.__hmbVideoPickerCleanup;
    if (container.__hmbVideoPickerCleanupProxy === cleanup) delete container.__hmbVideoPickerCleanupProxy;
    delete container.__hmbVideoPickerControllerUpdate;
    container.removeAttribute?.("data-hmb-video-picker-host-measurement");
  };
  container.__hmbVideoPickerCleanup = cleanup;
  container.__hmbVideoPickerCleanupProxy = cleanup;
  container.__hmbVideoPickerControllerUpdate = (nextProps) => {
    applyMeasurement(nextProps || {});
    schedulePromotionCheck();
  };
  return container.__hmbVideoPickerControllerProxy || {
    cleanup,
    update(nextProps) { applyMeasurement(nextProps || {}); },
  };
}

export default function HMBVideoPickerLibraryWidget(container, props) {
  if (!container) {
    return {
      cleanup() {},
      update() {},
    };
  }
  if (!container.__hmbVideoPickerControllerProxy) {
    container.__hmbVideoPickerControllerProxy = {
      cleanup() { container.__hmbVideoPickerCleanupProxy?.(); },
      update(nextProps) { container.__hmbVideoPickerControllerUpdate?.(nextProps || {}); },
    };
  }
  const initialIdentityState = hmbPickerStateFromProps(props || {});
  container.__hmbVideoPickerRuntimeInstanceId = clean(initialIdentityState.runtime_instance_id);
  // Editor 0.122 renders a second, visibility:hidden copy of every parameter
  // row solely for ResizeObserver measurement.  Mounting the live picker in
  // that copy used to shrink the shared React Flow shell before contentRef had
  // a height; the adaptive allocator then hid all three authored rows and
  // unmounted the real widget behind "Collapsed (3)".  Keep this copy inert and
  // measurable so only the visible row may own node geometry and listeners.
  if (hmbVideoPickerIsHostMeasurementClone(container)) {
    return hmbMountVideoPickerHostMeasurement(container, props || {});
  }
  // A new factory mount is live.  Host deletion flips this before running any
  // cleanup so late promise/timer callbacks cannot publish into a removed
  // node.
  container.__hmbVideoPickerDeleted = false;
  if (typeof container.__hmbVideoPickerExpanded !== "boolean") {
    const storedViewMode = hmbVideoPickerStoredViewMode(container);
    hmbRememberVideoPickerViewMode(container, storedViewMode === true);
  } else {
    hmbRememberVideoPickerViewMode(container, container.__hmbVideoPickerExpanded === true);
  }
  const pickerExpanded = container.__hmbVideoPickerExpanded === true;
  // v0.6.36 keeps one live root across compact/full transitions. Drop any
  // detached-DOM cache left by an older controller; normal keyed morphing now
  // owns every transition and preserves the fixed header/root identity.
  delete container.__hmbVideoPickerExpandedCache;
  delete container.__hmbVideoPickerRestoringExpandedDom;
  const retainedViewportVideo = container.querySelector?.("#picker-video") || null;
  const retainedViewportSource = clean(retainedViewportVideo?.getAttribute?.("src"));
  if (typeof container.__hmbVideoPickerCleanupProxy !== "function") {
    container.__hmbVideoPickerCleanupProxy = () => {
      const recoverCompactUnmount = (
        container.__hmbVideoPickerExpanded !== true
        && container.__hmbVideoPickerViewTransition !== true
      );
      void recoverCompactUnmount;
      const currentCleanup = container.__hmbVideoPickerCleanup;
      if (typeof currentCleanup === "function") currentCleanup();
      container.__hmbVideoPickerDeleted = true;
      hmbCancelVideoPickerNodeInternalsUpdate(container);
      hmbClearPendingPickerStateEcho(container);
      delete container.__hmbPendingPickerState;
      delete container.__hmbAuthoritativePickerState;
      delete container.__hmbPickerStatePublicationPredecessors;
      delete container.__hmbFailedPickerStatePublications;
      delete container.__hmbLastPickerStateRollback;
      delete container.__hmbLatestPickerStatePublicationIdentity;
      delete container.__hmbVisiblePickerStatePublicationError;
      const ackTimer = container.__hmbReadAckTimer;
      if (ackTimer) {
        try { clearTimeout(ackTimer); } catch (_error) {}
        delete container.__hmbReadAckTimer;
      }
      const originalAckTimer = container.__hmbOriginalAckTimer;
      if (originalAckTimer) {
        try { clearTimeout(originalAckTimer); } catch (_error) {}
        delete container.__hmbOriginalAckTimer;
      }
      delete container.__hmbViewportFrame;
      delete container.__hmbAutoplayVideoUid;
      delete container.__hmbForceVideoPreviewUid;
      delete container.__hmbPendingImportWorkspaceUuid;
      delete container.__hmbReadCommandPending;
      delete container.__hmbReadActionId;
      delete container.__hmbOriginalCommandPending;
      delete container.__hmbOriginalActionId;
      delete container.__hmbOriginalRequestedEnabled;
      delete container.__hmbOutlinerSearchDraft;
      delete container.__hmbMayaSceneDraftPath;
      delete container.__hmbMayaSceneDraftRuntimeInstanceId;
      delete container.__hmbNativePickerDeadlineMs;
      delete container.__hmbNativePickerPreviousPath;
      delete container.__hmbPickerOperationSubmissionPending;
      delete container.__hmbPickerOperationActionId;
      delete container.__hmbPickerOperationAction;
      hmbReleasePickerWorkspacePublication(
        container,
        Number(container.__hmbPickerWorkspacePublicationGeneration || 0),
      );
      delete container.__hmbPickerWorkspacePublicationGeneration;
      delete container.__hmbVideoPickerExpanded;
      delete container.__hmbVideoPickerExpandedCache;
      delete container.__hmbVideoPickerExpandedGeometry;
      delete container.__hmbVideoPickerExpandedViewState;
      delete container.__hmbVideoPickerCompactHostGeometry;
      delete container.__hmbVideoPickerCompactOuterGeometry;
      delete container.__hmbVideoPickerRestoringExpandedDom;
      delete container.__hmbVideoPickerFixedTop;
      delete container.__hmbVideoPickerControllerUpdate;
      if (container.__hmbPickerOperationGuardTimer) {
        try { clearTimeout(container.__hmbPickerOperationGuardTimer); } catch (_error) {}
        delete container.__hmbPickerOperationGuardTimer;
      }
      hmbInvalidateNativeMayaPickerCache(container);
    };
  }
  const previousCleanup = container.__hmbVideoPickerCleanup;
  if (typeof previousCleanup === "function") previousCleanup();
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  const engineState = normalize(props?.value ?? props?.parameterValue ?? props?.defaultValue);
  let pendingState = container.__hmbPendingPickerState && typeof container.__hmbPendingPickerState === "object"
    ? normalize(container.__hmbPendingPickerState)
    : null;
  if (
    pendingState
    && clean(pendingState.runtime_instance_id) !== clean(engineState.runtime_instance_id)
  ) {
    delete container.__hmbPendingPickerState;
    pendingState = null;
  }
  const engineRevision = Number(engineState.state_revision || 0);
  const pendingRevision = Number(pendingState?.state_revision || 0);
  const enginePublished = Number(engineState.state_published_at_ms || 0);
  const pendingPublished = Number(pendingState?.state_published_at_ms || 0);
  const pendingActionId = clean(pendingState?.pending_action_id);
  const engineAckActionId = clean(engineState.backend_ack_action_id);
  const localReadActionId = clean(container.__hmbReadActionId);
  const localOriginalActionId = clean(container.__hmbOriginalActionId);
  const engineAcknowledgesPending = !!pendingActionId && engineAckActionId === pendingActionId;
  const engineAcknowledgesLocalRead = !!localReadActionId && engineAckActionId === localReadActionId;
  const engineAcknowledgesLocalOriginal = !!localOriginalActionId && engineAckActionId === localOriginalActionId;
  const localPickerOperationActionId = clean(container.__hmbPickerOperationActionId);
  if (
    engineState.state_writer === "python"
    && localPickerOperationActionId
    && engineAckActionId === localPickerOperationActionId
  ) {
    delete container.__hmbPickerOperationSubmissionPending;
    delete container.__hmbPickerOperationActionId;
    delete container.__hmbPickerOperationAction;
    if (container.__hmbPickerOperationGuardTimer) {
      try { clearTimeout(container.__hmbPickerOperationGuardTimer); } catch (_error) {}
      delete container.__hmbPickerOperationGuardTimer;
    }
  }
  const engineIsNewer = engineState.state_writer === "python"
    ? engineAcknowledgesPending
      || engineRevision >= pendingRevision
      || enginePublished > pendingPublished
    : engineRevision > pendingRevision || enginePublished > pendingPublished;
  if (pendingState && engineIsNewer) {
    delete container.__hmbPendingPickerState;
  }
  const engineStatusKey = clean(engineState.status).toUpperCase();
  const engineStageKey = clean(engineState.scene_stage).toUpperCase();
  if (
    engineState.state_writer === "python"
    && engineAcknowledgesLocalRead
  ) {
    container.__hmbReadCommandPending = false;
    container.__hmbReadActionId = "";
    if (container.__hmbReadAckTimer) {
      try { clearTimeout(container.__hmbReadAckTimer); } catch (_error) {}
      delete container.__hmbReadAckTimer;
    }
  }
  if (
    engineState.state_writer === "python"
    && engineAcknowledgesLocalOriginal
  ) {
    container.__hmbOriginalCommandPending = false;
    if (container.__hmbOriginalAckTimer) {
      try { clearTimeout(container.__hmbOriginalAckTimer); } catch (_error) {}
      delete container.__hmbOriginalAckTimer;
    }
    const engineOriginalTerminal = (
      ["FAILED", "CANCELLED"].includes(engineStatusKey)
      || ["FAILED", "LOAD_FAILED", "CANCELLED", "STALE_RESULT_DISCARDED"].includes(engineStageKey)
      || (
        ["OUTLINER_READY", "VIDEO_READY"].includes(engineStatusKey)
        && ["OUTLINER_READY", "VIDEO_READY"].includes(engineStageKey)
        && clean(engineState.operation_kind) !== "render_original_preview"
        && Number(engineState.active_process_pid || 0) <= 0
      )
    );
    if (engineOriginalTerminal) {
      container.__hmbOriginalActionId = "";
      delete container.__hmbOriginalRequestedEnabled;
    }
  }
  let state = pendingState && !engineIsNewer ? pendingState : engineState;
  // During a compact/full swap, publishing the hidden measurement before the
  // live DOM and shell geometry agree lets React's adaptive allocator replace
  // the visible row in the middle of our mount.  The transition commits one
  // measurement after its final geometry instead.
  if (container.__hmbVideoPickerViewTransition !== true) {
    hmbSyncVideoPickerHostMeasurement(container, state, pickerExpanded);
  }
  const localSearchDraft = container.__hmbOutlinerSearchDraft;
  if (
    localSearchDraft
    && Number(localSearchDraft.expiresAtMs || 0) > Date.now()
  ) {
    state.outliner_search = clean(localSearchDraft.value);
  } else if (localSearchDraft) {
    delete container.__hmbOutlinerSearchDraft;
  }
  state.ui_theme = "P";
  const originalPreviewChecked = !!state.original_enabled;
  const maskChecked = !!state.mask_enabled;
  const depthChecked = !!state.depth_enabled;
  const motionGuideChecked = !!state.motion_guide_enabled;
  const paletteGroups = hmbPickerPaletteGroups(state.marker_catalog);
  const actorOptions = paletteGroups.actor;
  const ghostOptions = paletteGroups.ghost;
  const objectOptions = paletteGroups.object;
  hmbPrepareMayaSceneDraftRuntime(
    container,
    clean(engineState.runtime_instance_id || state.runtime_instance_id),
  );
  container.__hmbAuthoritativePickerState = normalize(state);
  let resizeObserver = null;
  let activeCleanup = [];
  let disposed = false;
  let recoverMissingMountedPicker = () => false;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    activeCleanup.forEach((fn) => { try { fn(); } catch (_error) {} });
    activeCleanup = [];
    if (resizeObserver) {
      try { resizeObserver.disconnect(); } catch (_error) {}
      resizeObserver = null;
    }
    container.removeAttribute?.("data-hmb-video-picker-compact-sizing-pending");
    container.removeAttribute?.("data-hmb-node-delete-protected");
    if (container.__hmbVideoPickerCleanup === cleanup) delete container.__hmbVideoPickerCleanup;
  };
  container.__hmbVideoPickerCleanup = cleanup;
  hmbInstallVideoPickerMountedRootGuard(
    container,
    activeCleanup,
    () => recoverMissingMountedPicker(props || {}),
  );
  concealNativeMayaPicker(container);
  const mayaSceneDraftPath = hmbResolveMayaSceneDraftPath(container, state);
  const buttonAvailability = pickerButtonAvailability(
    state,
    mayaSceneDraftPath,
    !!container.__hmbReadCommandPending,
    !!container.__hmbOriginalCommandPending,
  );
  // Backend work is durable state. The short local transport-submission guard
  // is applied dynamically after every morph so event closures never retain a
  // stale `locked=true` after rejection or ACK timeout recovery.
  const runningOperation = buttonAvailability.operationBusy;
  const stopReady = buttonAvailability.stopEnabled;
  const selectedAssets = hmbSelectedVideoAssets(state);
  const snapshotHistory = hmbSnapshotHistory(state);
  const video = previewVideo(state);
  const previewUid = clean(video?.video_uid || state.preview_video_uid || state.selected_video_uid);
  const previewOrder = selectedAssets.findIndex((item) => clean(item.video_uid) === previewUid) + 1;
  const selectedSlot = previewOrder > 0
    ? previewOrder
    : clamp(state.selected_video_slot || 1, 1, Math.max(1, selectedAssets.length));
  // Initial markup may reflect the mount-time operation state, but no event
  // closure may retain it. Every post-mount interaction consults
  // pickerLocalInteractionLocked() against the current regional state.
  const initialLocked = runningOperation;
  const bindings = selectedBindings(state, 1);
  const frameMetadata = selectedFrameMetadata(state, video, selectedSlot);
  const selectedNode = state.outliner_nodes.find((item) => clean(item.full_path) === state.selected_outliner_path) || null;
  const tr = TEXT[state.language] || TEXT.ko;
  const uiTheme = "P";
  const activePickerWorkspace = hmbActivePickerWorkspace(state);
  const shotPalette = hmbPickerShotPalette(activePickerWorkspace?.number || 1);
  const shotPaletteStyle = hmbPickerShotPaletteStyle(shotPalette.number);
  const rightSectionHeights = hmbNormalizeRightSectionHeights(state.right_section_heights);
  const rawFrameStart = Number(frameMetadata.start_frame);
  const rawFrameEnd = Number(frameMetadata.end_frame);
  const frameStart = Number.isFinite(rawFrameStart) ? Math.round(rawFrameStart) : 0;
  const frameEnd = Number.isFinite(rawFrameEnd) ? Math.round(rawFrameEnd) : frameStart;
  const hasFrameRange = frameMetadata.frame_count > 0
    && Number.isFinite(rawFrameStart)
    && Number.isFinite(rawFrameEnd)
    && rawFrameEnd >= rawFrameStart;
  const frameStartText = hasFrameRange
    ? frameStart.toLocaleString(undefined, { maximumFractionDigits: 0, useGrouping: false })
    : "—";
  const frameEndText = hasFrameRange
    ? frameEnd.toLocaleString(undefined, { maximumFractionDigits: 0, useGrouping: false })
    : "—";
  const sourceFps = Number(frameMetadata.fps);
  const fpsText = Number.isFinite(sourceFps) && sourceFps > 0
    ? sourceFps.toLocaleString(undefined, { maximumFractionDigits: 6, useGrouping: false })
    : "—";
  const viewportMode = clean(state.viewport_mode).toLowerCase() === "snapshot"
    ? "snapshot"
    : "video";
  if (viewportMode === "snapshot") {
    retainedViewportVideo?.pause?.();
    delete container.__hmbAutoplayVideoUid;
    delete container.__hmbForceVideoPreviewUid;
  }
  const forceVideoPreview = viewportMode === "video"
    && clean(container.__hmbForceVideoPreviewUid) === previewUid;
  const cardVideoPath = clean(
    video?.video_url
    || video?.project_video_path
    || video?.video_path,
  );
  const selectedVideoPath = clean(
    (forceVideoPreview ? cardVideoPath : "")
    || (state.original_preview_enabled ? state.original_video_url : "")
    || (state.original_preview_enabled ? state.original_video_path : "")
    || cardVideoPath,
  );
  const selectedVideoUrl = videoSourceUrl(selectedVideoPath);
  const selectedSnapshot = snapshotHistory.find(
    (item) => clean(item.snapshot_uid) === clean(state.active_snapshot_uid),
  ) || (viewportMode === "snapshot" ? snapshotHistory.at(-1) : null) || null;
  const snapshotForViewport = viewportMode === "snapshot"
    && !!hmbSnapshotMediaUrl(selectedSnapshot);
  const initialViewportFrame = clamp(
    Number(
      snapshotForViewport
        ? selectedSnapshot.frame
        : (container.__hmbViewportFrame ?? state.current_frame ?? frameStart),
    ),
    frameStart,
    frameEnd,
  );
  const initialTimecode = formatFrameTimecode(initialViewportFrame, frameStart, sourceFps);
  const frameInfoFps = Number.isInteger(sourceFps) ? String(sourceFps) : sourceFps.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  const viewportMediaHtml = snapshotForViewport
    ? `<img id="picker-snapshot-image" class="preview-image" src="${escapeHtml(hmbSnapshotMediaUrl(selectedSnapshot))}" alt="Colored snapshot"/>`
    : selectedVideoUrl
      ? `<video id="picker-video" class="preview-video" src="${escapeHtml(selectedVideoUrl)}" preload="metadata" playsinline></video>`
      : `<div class="viewport-empty"><div class="camera-frame"></div><b>${escapeHtml(tr.noPreviewTitle)}</b><span>${escapeHtml(tr.noPreviewBody)}</span></div>`;
  const viewportModeLabel = snapshotForViewport ? (tr.snapshot || "Snapshot") : (tr.preview || "Video");
  const snapshotDeleteEnabled = !runningOperation && !!selectedSnapshot;
  const activityRows = hmbActivityLogRowsForDisplay(state);
  const priorOutlinerScroll = container.querySelector?.(".outliner-scroll");
  const priorOutlinerFocusPath = priorOutlinerScroll?.contains?.(priorOutlinerScroll.ownerDocument?.activeElement)
    ? clean(priorOutlinerScroll.ownerDocument?.activeElement?.closest?.("[data-group-path]")?.getAttribute?.("data-group-path"))
    : "";
  const outlinerRenderOptions = {
    scrollTop: Number(priorOutlinerScroll?.scrollTop || 0),
    viewportHeight: Number(priorOutlinerScroll?.clientHeight || 0),
    forcePath: priorOutlinerFocusPath,
  };
  const activityLogMarkup = hmbActivityLogHtml(state, tr);
  const videoAssetMarkup = videoAssetCardsHtml(state, tr, initialLocked);
  const pickerShotWorkspaceMarkup = hmbRenderVideoPickerShotWorkspace(
    state,
    tr,
    initialLocked,
    pickerExpanded ? "expanded" : "compact",
  );
  const fixedTopActiveShot = hmbActivePickerWorkspace(state);
  const fixedTopSelectedCount = Math.min(
    Array.isArray(fixedTopActiveShot?.selected_video_uids)
      ? fixedTopActiveShot.selected_video_uids.length
      : 0,
    HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS,
  );
  const fixedTopAssetCount = hmbPickerWorkspaceAssetUids(fixedTopActiveShot).length;
  const elapsedSeconds = runningOperation && Number(state.operation_started_at_ms || 0) > 0
    ? Math.max(0, (Date.now() - Number(state.operation_started_at_ms)) / 1000)
    : Number(state.last_operation_seconds || 0);
  const elapsedText = `${Math.floor(elapsedSeconds / 60).toString().padStart(2, "0")}:${Math.floor(elapsedSeconds % 60).toString().padStart(2, "0")}`;
  const sharedImportInputMarkup = `
          <input type="file" id="import-video-asset" data-picker-shared-import-input accept=".mp4,video/mp4" multiple hidden/>`;
  const fixedTopPaintMarkup = `<style>
      .hmbvp>.app-header.top[data-picker-toggle-surface="header"]{--hmb-primary-top:#F472B6;--hmb-primary-bottom:#BE185D;--hmb-primary-line:#F3A8CE;--hmb-focus:#22D3EE;--hmb-accent:#22D3EE;--hmb-glow:rgba(168,85,247,.16);--selection-rgb:244,114,182;--selection-deep-rgb:190,24,93;--selection-text:#F8C6DF;--selection-soft:#F3A8CE;--selection-strong:#FFE4F2;background:linear-gradient(90deg,rgba(72,35,101,.44),rgba(14,23,38,.92) 44%,rgba(6,9,18,.96))!important;background-color:#060912!important;border-bottom-color:rgba(148,163,184,.19)!important;box-shadow:none!important;filter:none!important;backdrop-filter:none!important;transition:none!important}
      .hmbvp>.app-header.top[data-picker-toggle-surface="header"] *{transition:none!important}.hmbvp>.app-header.top[data-picker-toggle-surface="header"] button{box-shadow:none!important}.hmbvp>.app-header.top[data-picker-toggle-surface="header"] .brand-mark{border-color:rgba(34,211,238,.70)!important;background:rgba(8,145,178,.12)!important;color:#22D3EE!important;box-shadow:none!important}
      .hmbvp>.app-header.top[data-picker-toggle-surface="header"][data-picker-view-transition-pending="true"]{cursor:progress!important}
      .hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"]>.picker-shot-tab.active{border-color:color-mix(in srgb,var(--local-shot-accent) 48%,#263449)!important;box-shadow:none!important}.hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"] .picker-shot-activate[aria-pressed="true"]{outline:2px solid var(--local-shot-accent)!important;outline-offset:-3px;border-radius:6px;box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--local-shot-accent) 38%,transparent)!important}
      .hmbvp.hmbvp-compact .compact-shot-row.active{border-color:rgba(var(--shot-rgb),.38)!important;box-shadow:none!important}.hmbvp.hmbvp-compact .compact-shot-row.active .compact-shot-head>.picker-shot-number{outline:2px solid var(--shot-accent)!important;outline-offset:2px;border-radius:4px;box-shadow:none!important}
    </style>`;
  const fixedTopMarkup = `${fixedTopPaintMarkup}<header class="app-header top" data-picker-toggle-surface="header" aria-label="HMB VideoPicker">
        <div class="brand"><span class="brand-mark"></span><span>HMBVideoPickerLibrary</span></div>
        <div class="header-actions" data-no-picker-toggle>
          <span class="picker-active-shot-controls" data-picker-active-shot-controls="${escapeHtml(fixedTopActiveShot?.workspace_uuid || "")}"><b data-picker-shot-name>${escapeHtml(fixedTopActiveShot?.name || "Shot 1")}</b><button type="button" class="picker-shot-rename" data-picker-shot-rename="${escapeHtml(fixedTopActiveShot?.workspace_uuid || "")}" aria-label="Rename ${escapeHtml(fixedTopActiveShot?.name || "Shot 1")}" ${initialLocked ? "disabled" : ""}>✎</button></span>
          ${sharedImportInputMarkup}
          <button type="button" class="language-button" id="language-toggle">${escapeHtml(tr.language)}</button>
        </div>
      </header>`;
  const compactPickerMarkup = `
    <style>
      .hmbvp-clip{width:100%;min-width:0;min-height:0;overflow:hidden;background:#090c16;box-sizing:border-box;display:flex;flex-direction:column}
      .hmbvp{--hmb-deep:#090c16;position:relative;width:100%;min-width:0;min-height:0;padding:0;display:flex;flex-direction:column;background:#0b1020;color:#dbe4ec;border:1px solid rgba(148,163,184,.22);border-radius:10px;overflow:hidden;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px}
      .hmbvp *{box-sizing:border-box;min-width:0}.hmbvp button,.hmbvp select{font:inherit;color:inherit}.app-header{position:relative;z-index:30;height:58px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 13px;background:linear-gradient(90deg,rgba(72,35,101,.44),rgba(14,23,38,.9) 44%);border-bottom:1px solid rgba(148,163,184,.22);user-select:none}.brand{display:flex;align-items:center;gap:12px;min-width:0;flex:1;font-size:15px;font-weight:850}.brand-mark{width:35px;height:35px;flex:0 0 35px;display:grid;place-items:center;border:1px solid var(--hmb-primary-line);border-radius:8px;background:rgba(var(--selection-rgb),.12)}.brand-mark:after{content:"VP";font-size:9px;font-weight:950}.header-actions{display:flex;align-items:center;gap:7px}.header-actions button,.header-actions select{height:31px;padding:0 9px;border:1px solid rgba(var(--selection-rgb),.42);border-radius:7px;background:#080d17;color:#eef2f7}.add-picker-shot-button{border-color:var(--hmb-primary-line)!important;background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom))!important;color:#fff!important;font-weight:850}.shot-selector-wrap{display:flex;align-items:center;gap:5px}.shot-selector-label{font-size:9px;font-weight:900;letter-spacing:.12em;color:#8ea0b5}.shot-selector{min-width:132px;max-width:220px}.shot-selector-conflict{display:none}.compact-current-videos{margin:8px;padding:8px;min-height:0;flex:1 1 auto;display:flex;flex-direction:column;border:1px solid rgba(16,185,129,.58);border-radius:8px;background:linear-gradient(90deg,rgba(4,120,87,.22),rgba(6,78,59,.08));box-shadow:inset 0 0 0 1px rgba(52,211,153,.06)}
      .picker-shot-tabs{display:flex;align-items:stretch;gap:6px;overflow-x:auto;padding:0 0 7px}.picker-shot-tab{display:grid;grid-template-columns:30px minmax(72px,1fr) 34px 24px 26px 26px;align-items:center;gap:4px;flex:1 1 190px;min-width:190px;max-width:300px;height:36px;padding:3px;border:1px solid color-mix(in srgb,var(--local-shot-accent) 48%,#263449);border-radius:7px;background:color-mix(in srgb,var(--local-shot-deep) 16%,#0d1423)}.picker-shot-tab.active{border-color:var(--local-shot-accent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--local-shot-accent) 38%,transparent)}.picker-shot-activate,.picker-shot-rename,.picker-shot-delete{height:28px;border:1px solid color-mix(in srgb,var(--local-shot-accent) 42%,#334155);border-radius:5px;background:#101827;color:#fff;cursor:pointer}.picker-shot-number{font-size:9px;font-weight:950}.picker-shot-name-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;font-weight:800;color:#eef2f7}.picker-shot-binding-chip{height:20px;display:grid;place-items:center;border-left:3px solid var(--remote-shot-accent,#64748b);border-radius:4px;background:#111827;color:#aeb9c1;font-size:7px;font-weight:900}.picker-shot-video-count{font-size:8px;text-align:center;color:#a7f3d0}.picker-shot-actions{min-height:48px;display:flex;align-items:center;gap:9px;margin-bottom:7px}.picker-shot-actions .spacer{flex:1}.picker-shot-actions .shot-selector{background:#0b1320;border:1px solid rgba(var(--selection-rgb),.58);border-radius:6px;color:var(--selection-strong)}
      .compact-current-videos-title{color:#a7f3d0;font-size:11px;font-weight:900;letter-spacing:.08em}.video-selected-count{font-size:9px;color:#a7f3d0;font-variant-numeric:tabular-nums}.import-video-button{height:27px;padding:0 12px;border:1px solid #34d399;border-radius:6px;background:linear-gradient(180deg,#047857,#065f46);color:#ecfdf5;font-weight:850;cursor:pointer}.import-video-button:disabled{opacity:.45;cursor:not-allowed}.import-video-icon{display:none}
      .video-assets-body{overflow-x:auto;overflow-y:hidden;contain:layout paint}.video-asset-grid{display:flex;align-items:stretch;gap:8px;min-height:94px}.video-assets-empty{flex:1 1 100%;min-height:92px;display:grid;place-items:center;border:1px dashed rgba(52,211,153,.30);border-radius:7px;color:#86a99c}.video-asset-card{position:relative;display:grid;grid-template-columns:112px 92px;flex:0 0 204px;min-height:88px;border:1px solid #263449;border-radius:7px;background:#0d1423;overflow:hidden}.video-asset-card.selected{border-color:#34d399;box-shadow:inset 0 0 0 1px rgba(52,211,153,.35),0 0 12px rgba(16,185,129,.18)}.video-asset-card.selection-blocked{opacity:.58}.video-asset-thumb{position:relative;min-height:86px;background:#050812;overflow:hidden}.video-asset-thumb-media{width:100%;height:100%;display:block;object-fit:cover;background:#050812}.video-asset-thumb-fallback{height:100%;display:grid;place-items:center;color:#64748b;font-size:10px}.video-asset-role{position:absolute;left:4px;bottom:4px;max-width:70px;padding:2px 4px;border-radius:3px;background:rgba(0,0,0,.72);font-size:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.selected-video-order{position:absolute;left:4px;top:4px;padding:2px 5px;border-radius:4px;background:#047857;color:#fff;font-size:8px;font-weight:900}.video-asset-play{position:absolute;inset:0;width:100%;height:100%;border:0;background:transparent;color:transparent;cursor:pointer}.video-asset-play:focus-visible{outline:2px solid #34d399;outline-offset:-2px}.video-asset-copy{display:flex;flex-direction:column;justify-content:center;gap:4px;padding:8px;cursor:pointer}.video-asset-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e4ebf4;font-size:10px}.video-asset-details{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#7f8da0;font-size:8px}.video-asset-delete{display:none}.video-order-hint{margin-top:5px;color:#86a99c;font-size:8px;text-align:right}.section-resize-handle{display:none}
      @media (max-width:760px){.app-header{height:auto;min-height:58px;flex-wrap:wrap;padding:7px}.header-actions{width:100%}.shot-selector-wrap{flex:1}.shot-selector{width:100%;max-width:none}.compact-current-videos{margin:6px}}
      @media (prefers-reduced-motion:reduce){.hmbvp *{animation:none!important;transition:none!important}}
      .hmbvp .brand{font-size:15px;font-weight:800;letter-spacing:.01em;font-style:normal;line-height:normal}
      .hmbvp .shot-selector{flex:0 1 210px;width:210px;min-width:120px;max-width:210px;height:44px;font-size:13px;font-weight:800;font-style:normal;line-height:normal}
      .hmbvp.hmbvp-compact{box-sizing:border-box}.hmbvp.hmbvp-compact .compact-current-videos{margin:0;padding:0;min-height:0;flex:0 0 auto;display:flex;flex-direction:column;border:0;border-radius:0;background:#060912;box-shadow:none;overflow:visible}
      .hmbvp.hmbvp-compact .video-picker-compact-summary[data-picker-shot-layout="compact"]{position:relative;width:100%;display:flex!important;flex-direction:column!important;flex-wrap:nowrap!important;align-items:stretch!important;gap:6px;padding:6px;overflow:hidden!important;border:0;background:#060912;cursor:default}
      .hmbvp.hmbvp-compact .compact-shot-row{position:relative;display:flex;flex:0 0 auto;flex-direction:column;align-items:stretch;gap:6px;width:100%;min-width:0;max-width:none;height:180px;padding:6px;border:1px solid rgba(var(--shot-rgb),.38);border-radius:7px;background:linear-gradient(90deg,rgba(var(--shot-rgb),.17),rgba(8,13,23,.86))!important;color:#d9e6f3;box-shadow:none!important;overflow:hidden}.hmbvp.hmbvp-compact .compact-shot-row.empty{height:86px;min-height:86px}
      .hmbvp.hmbvp-compact .compact-shot-row.active{border-color:rgba(var(--shot-rgb),.38);box-shadow:none}
      .hmbvp.hmbvp-compact .compact-shot-head{height:28px;flex:0 0 28px;display:grid;grid-template-columns:34px minmax(90px,auto) minmax(120px,1fr) auto 28px minmax(64px,auto);align-items:center;gap:8px;padding:0 4px;cursor:pointer}.hmbvp.hmbvp-compact .compact-shot-head>.picker-shot-number{width:26px;height:22px;padding:0;display:grid;place-items:center;border:0;background:transparent;color:var(--shot-accent);font-size:9px;font-weight:950;cursor:pointer}.hmbvp.hmbvp-compact .compact-shot-head b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.hmbvp.hmbvp-compact .compact-shot-head span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8ea3b8;font-size:7px}.hmbvp.hmbvp-compact .compact-shot-head em{color:var(--shot-accent);font-size:8px;font-style:normal;text-align:center}.hmbvp.hmbvp-compact .compact-shot-head .compact-shot-rename{width:28px;min-width:28px;height:28px;padding:0;border-color:rgba(var(--shot-rgb),.52);background:rgba(var(--shot-rgb),.12);color:var(--shot-accent);font-size:12px}.hmbvp.hmbvp-compact .compact-shot-head .compact-shot-load{min-width:64px;height:28px;margin:0;padding:0 8px;border-color:rgba(var(--shot-rgb),.58);background:linear-gradient(180deg,rgba(var(--shot-rgb),.30),rgba(var(--shot-rgb),.14));color:#fff;box-shadow:none;font-size:8px}
      .hmbvp.hmbvp-compact .compact-shot-assets{height:132px;flex:0 0 132px;min-width:0;display:flex;align-items:stretch;gap:8px;padding:7px;overflow-x:auto;overflow-y:hidden;scrollbar-gutter:stable;border-top:1px solid rgba(var(--shot-rgb),.18)}.hmbvp.hmbvp-compact .compact-shot-assets.empty{height:38px;flex-basis:38px;display:grid;place-items:center;overflow:hidden}.hmbvp.hmbvp-compact .compact-shot-empty{color:#688096;font-size:8px}
      .hmbvp.hmbvp-compact .compact-shot-slot{position:relative;flex:0 0 120px;width:120px;height:118px;display:grid;grid-template-rows:81px minmax(0,1fr);gap:4px;padding:6px;border:1px solid rgba(var(--shot-rgb),.28);border-radius:8px;background:rgba(5,9,16,.82);color:#74879a;overflow:hidden}.hmbvp.hmbvp-compact .compact-shot-slot.selected{border-color:var(--shot-accent);box-shadow:inset 0 0 0 1px rgba(var(--shot-rgb),.22);color:var(--shot-accent)}.hmbvp.hmbvp-compact .compact-shot-thumb{position:relative;width:106px;height:81px;display:grid;place-items:center;overflow:hidden;border-radius:6px;background:#050910}.hmbvp.hmbvp-compact .compact-shot-placeholder{width:100%;height:100%;display:grid;place-items:center;background:linear-gradient(135deg,rgba(var(--shot-rgb),.17),rgba(15,23,42,.84));color:rgba(var(--shot-rgb),.82)}.hmbvp.hmbvp-compact .compact-shot-placeholder i{font-size:8px;font-style:normal;font-weight:900;letter-spacing:.08em}.hmbvp.hmbvp-compact .compact-shot-thumb>.video-asset-thumb-media{position:absolute;inset:0;z-index:1;width:100%;height:100%;display:block;object-fit:cover;background:#050910}.hmbvp.hmbvp-compact .compact-video-play{position:absolute;left:50%;top:50%;z-index:3;width:28px;height:28px;display:grid;place-items:center;transform:translate(-50%,-50%);padding:0;border:1px solid rgba(255,255,255,.34);border-radius:50%;background:rgba(5,8,18,.76);color:#fff;font-size:10px;cursor:pointer}.hmbvp.hmbvp-compact .compact-video-play[aria-pressed="true"]{border-color:var(--shot-accent);box-shadow:0 0 10px rgba(var(--shot-rgb),.34)}.hmbvp.hmbvp-compact .compact-shot-thumb>small{position:absolute;top:3px;left:3px;z-index:2;min-width:22px;padding:2px 3px;border-radius:3px;background:rgba(0,0,0,.76);color:var(--shot-accent);font-size:7px;font-weight:950;text-align:center}.hmbvp.hmbvp-compact .compact-shot-slot>b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#cbd8e5;font-size:7px;text-align:left}.hmbvp.hmbvp-compact .compact-shot-thumb>.selected-video-order{position:absolute;top:3px;right:3px;bottom:auto;left:auto;z-index:2;min-width:0;padding:2px 4px;border-radius:3px;background:var(--local-shot-deep);color:#fff;font-size:7px;font-style:normal;font-weight:950}
      .hmbvp.hmbvp-compact .compact-video-delete{position:absolute;top:3px;right:3px;z-index:4;width:22px;height:20px;padding:0;border:1px solid rgba(251,113,133,.62);border-radius:4px;background:rgba(136,19,55,.92);color:#fff1f3;font-size:12px;font-weight:900;line-height:18px;cursor:pointer}.hmbvp.hmbvp-compact .compact-video-delete:disabled{opacity:.42;cursor:not-allowed}.hmbvp.hmbvp-compact .compact-video-select-label{width:100%;height:19px;padding:0 2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:0;background:transparent;color:#cbd8e5;font-size:7px;font-weight:800;text-align:left;cursor:pointer}.hmbvp.hmbvp-compact .compact-video-select-label[aria-pressed="true"]{color:var(--shot-accent)}.hmbvp.hmbvp-compact .compact-video-select-label:focus-visible{outline:1px solid var(--shot-accent);outline-offset:0}.hmbvp.hmbvp-compact .compact-video-select-label:disabled{opacity:.45;cursor:not-allowed}
      .hmbvp .app-header .picker-active-shot-controls{display:flex;align-items:center;gap:5px;min-width:0;max-width:190px}.hmbvp .app-header .picker-active-shot-controls>b{max-width:112px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--selection-text);font-size:10px}.hmbvp .app-header .picker-active-shot-controls .picker-shot-rename,.hmbvp .app-header .picker-active-shot-controls .picker-shot-delete{width:29px;min-width:29px;height:29px;padding:0}.hmbvp .app-header .import-video-button{height:29px;margin:0;padding:0 10px}
      .hmbvp.hmbvp-compact>.app-header .picker-active-shot-controls,.hmbvp.hmbvp-compact>.app-header #import-video-button,.hmbvp.hmbvp-compact>.app-header .add-picker-shot-button{display:none!important}
    </style>
    <div class="hmbvp-clip nodrag"><div class="hmbvp hmbvp-compact" data-picker-view="compact" data-theme="${uiTheme}" data-shot-number="${shotPalette.number}" data-state-revision="${Number(state.state_revision || 0)}" data-canvas-motion="false" style="${shotPaletteStyle}">
      ${fixedTopMarkup}
      <section class="compact-current-videos" data-compact-current-videos aria-label="HMBVideoPickerLibrary Shots">${pickerShotWorkspaceMarkup.tabs}</section>
    </div></div>`;
  const pickerMarkup = pickerExpanded ? `
    <style>
      .hmbvp-clip{width:100%;height:100%;min-width:0;min-height:0;max-width:none;max-height:none;overflow:hidden;background:#050812;box-sizing:border-box;display:flex;flex-direction:column;flex:1 1 auto}
      .hmbvp{--safe-x:16px;position:relative;width:100%;height:100%;min-width:0;min-height:960px;max-width:none;max-height:none;padding-left:var(--safe-x);padding-right:var(--safe-x);display:flex;flex-direction:column;flex:1 1 auto;background:#101820;color:#dbe4ec;border:1px solid rgba(148,163,184,.2);border-radius:11px;box-shadow:0 0 34px rgba(14,165,233,.12);overflow:hidden;resize:none;container-type:inline-size;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px}
      .hmbvp *{box-sizing:border-box;min-width:0}.hmbvp button,.hmbvp select,.hmbvp input,.hmbvp textarea{font:inherit;pointer-events:auto}.hmbvp button{color:inherit}.hmbvp .nodrag{touch-action:auto}.app-header{position:relative;z-index:30}.header-actions{position:relative;z-index:31}
      .setting-select{width:100%;height:27px;padding:0 8px;border:1px solid #2c3b46;border-radius:2px;background:#202d36;color:#d7dfe4;cursor:pointer;outline:0}.setting-select:disabled{opacity:.5;cursor:not-allowed}
      .hmbvp button,.hmbvp input,.hmbvp select{transition:border-color 80ms ease,color 80ms ease}
      .hmbvp .side-section,.hmbvp .viewport-panel{transition-property:background-color,border-color,opacity;transition-duration:140ms;transition-timing-function:ease}.viewport-panel.is-switching .viewport-stage{opacity:.78}.viewport-panel.is-switching .viewport-title small:after{content:" …"}
      .preview-load-status{position:absolute;z-index:8;left:12px;right:12px;bottom:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 11px;border:1px solid rgba(251,113,133,.72);border-radius:7px;background:rgba(64,14,26,.94);color:#ffe4e8;font-size:10px;line-height:1.35;box-shadow:0 8px 22px rgba(0,0,0,.36)}.preview-load-status[hidden]{display:none}.preview-load-status span{flex:1}.preview-load-status button{height:27px;flex:0 0 auto;padding:0 10px;border:1px solid rgba(255,255,255,.3);border-radius:5px;background:#71283a;color:#fff;cursor:pointer;font-weight:800}
      @media (prefers-reduced-motion:reduce){.hmbvp *{animation:none!important;transition:none!important}}
      .generate-playblast-toolbar{position:relative;z-index:22;min-height:42px;flex:0 0 42px;display:flex;align-items:center;padding:6px 10px;border-bottom:1px solid #2a353e;background:#151f27}.generate-playblast-toolbar .generate-button{height:29px;min-height:29px;line-height:27px}.playblast-settings-toolbar{position:relative;z-index:21;min-height:88px;flex:0 0 88px;display:block;padding:7px 10px;border-bottom:1px solid #2a353e;background:#151f27;overflow:hidden}.playblast-settings-toolbar .settings-grid-inline{width:100%;height:66px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:29px 29px;gap:8px 4px}.settings-grid-inline .settings-primary-item{grid-row:1;display:grid;grid-template-columns:max-content minmax(0,1fr);align-items:center;gap:8px;min-width:0}.settings-grid-inline .settings-primary-label{padding-left:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.settings-grid-inline .setting-value,.settings-grid-inline .setting-select{height:27px}.settings-grid-inline .settings-compact-row{grid-column:1/-1;grid-row:2;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px}.settings-grid-inline .settings-compact-item{height:27px;padding:0 5px}
      .snapshot-toolbar{position:relative;z-index:23;min-height:42px;display:grid;grid-template-columns:minmax(96px,4fr) max-content minmax(145px,6fr);align-items:center;gap:7px;padding:6px 10px;border-bottom:1px solid #2a353e;background:#151f27}.snapshot-toolbar>button,.video-controls button{height:29px;padding:0 11px;border:1px solid #344550;border-radius:3px;background:#1a2833;color:#e4ebef;cursor:pointer}.snapshot-toolbar>button{min-width:0;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:27px}.snapshot-toolbar #create-snapshot{width:auto;min-width:0;background:#1c3c62;border-color:#2c5b8d}.snapshot-toolbar #delete-snapshot{width:max-content;min-width:124px;background:#4d2328;border-color:#774047}.snapshot-toolbar .output-camera-inline{width:100%;height:29px;min-width:0;min-height:29px;margin-left:0;display:grid;grid-template-columns:max-content minmax(0,1fr);align-items:center;overflow:hidden}.snapshot-toolbar .output-camera-label{white-space:nowrap;line-height:29px}.snapshot-toolbar .camera-fixed,.snapshot-toolbar .camera-dropdown{width:100%;height:29px;min-width:0;min-height:29px;max-height:29px;align-self:center;overflow:hidden}.snapshot-toolbar>button:disabled,.video-controls button:disabled{opacity:.4;cursor:not-allowed}.preview-video{display:block;width:100%;height:100%;object-fit:contain;background:#10161b}.video-seekbar{height:28px;flex:0 0 28px;display:flex;align-items:center;padding:4px 12px;background:#111a21;border-top:1px solid #2b363e}.video-seekbar input{width:100%;height:18px;margin:0;accent-color:#4c8fd7;cursor:pointer}.video-seekbar input:disabled{opacity:.35;cursor:not-allowed}.video-controls{height:44px;flex:0 0 44px;display:flex;align-items:center;justify-content:center;gap:6px;padding:6px 10px;background:#111a21}.video-controls .transport-button{width:38px;padding:0;font-weight:800}.frame-number-label{display:flex;align-items:center;gap:6px;margin-left:6px;color:#cbd5dc;font-size:10px}.frame-number-label input{width:92px;height:29px;padding:0 7px;border:1px solid #344550;border-radius:3px;background:#0d151c;color:#fff;font-variant-numeric:tabular-nums}.frame-info-strip{height:28px;flex:0 0 28px;display:flex;align-items:center;justify-content:center;gap:16px;padding:0 10px;border-top:1px solid #26323b;background:#0d151c;color:#7f8e99;font-size:9px;font-weight:800;white-space:nowrap}.frame-info-strip b{margin-left:4px;color:#e5edf2;font-variant-numeric:tabular-nums}
      .app-header{height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 16px;background:linear-gradient(180deg,#121c25,#101820);border-bottom:1px solid #26313a}
      .brand{display:flex;align-items:center;gap:10px;min-width:0;flex:1 1 auto;font-size:19px;font-weight:700;color:#f3f6f8;white-space:nowrap;overflow:hidden}.brand>span:last-child{overflow:hidden;text-overflow:ellipsis}.brand-mark{width:30px;height:30px;flex:0 0 30px;border:2px solid #dfe7ed;transform:rotate(30deg);display:grid;place-items:center}.brand-mark:after{content:"H";transform:rotate(-30deg);font-size:13px}.header-actions{display:flex;align-items:center;justify-content:flex-end;flex:0 0 auto;gap:7px}.header-actions button,.header-actions select{height:30px;border:1px solid #33414d;background:#18232d;border-radius:3px;padding:0 10px;cursor:pointer;color:inherit}.shot-selector-wrap{display:flex;align-items:center;gap:6px}.shot-selector-label{font-size:10px;font-weight:800;letter-spacing:.12em;color:#8296a7}.shot-selector{min-width:150px;max-width:260px}.shot-selector-conflict{color:#fda4af;font-size:10px;font-weight:700}.header-actions .read-button{background:#1c3c62;border-color:#2c5b8d}.header-actions .stop-button{background:#4d2328;border-color:#774047}.header-actions .language-button{min-width:58px}.header-actions button:disabled,.header-actions select:disabled{opacity:.4;cursor:not-allowed}
      .scene-load-bar{height:36px;flex:0 0 36px;display:grid;grid-template-columns:auto minmax(120px,1fr) auto auto max-content max-content max-content max-content;align-items:center;gap:6px;padding:3px 10px;background:#111a22;border-bottom:1px solid #293640}.scene-load-label{font-size:10px;font-weight:800;color:#aebbc4}.scene-path-input{height:25px;min-width:0;padding:0 9px;border:1px solid #33424e;border-radius:3px;background:#0d151c;color:#e2e8ed}.scene-path-input:focus{outline:0;border-color:#5797d1}.scene-load-bar button{height:25px;padding:0 10px;border:1px solid #3b4b57;border-radius:3px;background:#1a2833;color:#e1e8ed;cursor:pointer}.scene-load-bar .load-scene-button{background:#285b91;border-color:#346ba4;font-weight:800}.scene-load-bar button:disabled,.scene-path-input:disabled{opacity:.4;cursor:not-allowed}
      .main-grid{display:grid;grid-template-columns:minmax(230px,24%) minmax(420px,1fr) minmax(285px,26%);align-items:stretch;gap:8px;padding:8px;flex:1;min-height:0;overflow:auto;background:#0e161d}
      .center-stack{min-width:0;min-height:0;display:flex;flex-direction:column;gap:8px;overflow:hidden}.center-stack>.viewport-panel{flex:3 1 0}.center-stack>.activity-section{flex:1 1 0;min-height:150px}
      .panel{min-width:0;min-height:0;background:#151f27;border:1px solid #2c3740;border-radius:10px;display:flex;flex-direction:column;overflow:hidden}.panel-title{height:34px;display:flex;align-items:center;padding:0 10px;border-bottom:1px solid #2b3740;background:#18232b;font-weight:700;color:#edf2f5}.panel-title.viewport-title{justify-content:center;text-align:center}.panel-title small{margin-left:5px;color:#aeb9c1;font-weight:500}.panel-title .grow{flex:1}
      .panel-resize-handle{position:relative;flex:0 0 10px;min-height:10px;height:10px;border-top:1px solid #2c3740;cursor:ns-resize;background:linear-gradient(90deg,transparent,rgba(148,163,184,.16),transparent);touch-action:none;user-select:none}.panel-resize-handle:before{content:"";position:absolute;left:50%;top:3px;width:44px;height:3px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.48)}.panel-resize-handle:hover:before{background:#fff}
      .outliner-palette{padding:8px;border-bottom:1px solid #29343d;background:#111a21}.outliner-toolbar{display:flex;gap:6px;padding:8px;border-bottom:1px solid #29343d}.search-input{width:100%;height:29px;background:#101820;border:1px solid #2b3944;color:#dce5eb;padding:0 9px;border-radius:3px}.column-head{height:28px;display:flex;align-items:center;padding:0 8px;border-bottom:1px solid #2b353d;color:#b7c1c9;font-size:11px}.outliner-scroll{flex:1;min-height:0;overflow:auto;padding:3px}.outliner-list{display:flex;flex-direction:column}.outliner-virtual-spacer{width:1px;pointer-events:none}.outliner-row{display:flex;align-items:center;height:29px;min-height:29px;box-sizing:border-box;padding-right:5px;color:#d2d9df;border-radius:2px;cursor:pointer}.outliner-row:hover{background:#1c2a35}.outliner-row.selected{background:#25517e}.outliner-row.output-off{opacity:.48}.tree-toggle{width:19px;height:25px;border:0;background:transparent;padding:0;color:#a8b4bd;cursor:pointer}.tree-toggle.leaf{cursor:default}.eye-toggle{width:25px;height:25px;display:grid;place-items:center;border:0;background:transparent;padding:4px;cursor:pointer}.eye-toggle svg{width:17px;height:17px;fill:none;stroke:#68d26d;stroke-width:1.8}.eye-toggle.on svg circle{fill:#68d26d;stroke:none}.eye-toggle.off svg{stroke:#dd5c60}.node-icon{font-size:9px;color:#bcc6ce;margin-right:5px}.group-name{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ref-tag{font-size:9px;border:1px solid #5c6b76;border-radius:3px;padding:1px 4px;margin-right:5px;color:#adb8c0}.assigned-chip{width:14px;height:14px;border:1px solid rgba(255,255,255,.4);border-radius:2px;margin-right:6px}
      .viewport-panel{background:#131c23}.output-scope-inline{position:relative;z-index:20;min-height:38px;display:flex;align-items:center;justify-content:flex-start;gap:12px;padding:4px 10px;border-bottom:1px solid #2a353e;background:#151f27;white-space:nowrap;overflow:visible}.output-scope-title{font-size:10px;font-weight:800;color:#d7dfe5;flex:0 0 auto;text-align:center}.output-scope-options{display:flex;align-items:center;justify-content:flex-start;gap:14px;min-width:max-content}.output-scope-option{display:flex;align-items:center;gap:5px;font-size:10px;color:#d7dfe5;cursor:pointer}.output-scope-option input{margin:0;accent-color:#4c8fd7}.output-scope-option span{white-space:nowrap}.output-camera-inline{display:flex;align-items:center;gap:7px;margin-left:auto;flex:0 0 auto}.output-camera-label{font-size:10px;font-weight:800;color:#d7dfe5}.camera-fixed,.camera-dropdown{position:relative;min-width:200px}.camera-fixed{height:28px;display:flex;align-items:center;gap:7px;padding:0 9px;background:#111a21;border:1px solid #33414c;border-radius:3px}.camera-fixed b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.camera-fixed em{font-size:9px;color:#79aee4;font-style:normal}.camera-fixed.disabled{opacity:.5}.camera-dropdown summary{list-style:none;height:29px;display:flex;align-items:center;gap:7px;padding:0 9px;background:#111a21;border:1px solid #33414c;border-radius:3px;cursor:pointer}.camera-dropdown summary::-webkit-details-marker{display:none}.camera-dropdown summary b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.camera-menu{position:absolute;z-index:60;left:0;right:0;top:32px;max-height:240px;overflow:auto;background:#17232c;border:1px solid #3b4a56;box-shadow:0 8px 18px rgba(0,0,0,.5);padding:4px}.camera-menu button{width:100%;display:flex;justify-content:space-between;align-items:center;border:0;background:transparent;padding:8px;text-align:left;cursor:pointer}.camera-menu button:hover,.camera-menu button.active{background:#24415e}.camera-menu button span{font-size:9px;color:#9dacb6}.viewport-stage{position:relative;flex:1;min-height:0;background:radial-gradient(circle at 50% 44%,#5a5a59 0,#373b3d 36%,#20282d 80%);display:flex;align-items:center;justify-content:center;overflow:hidden}.preview-image{width:100%;height:100%;object-fit:contain;background:#232a2e}.viewport-empty{position:relative;width:82%;height:76%;border:1px solid #3fa578;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#b5c0c8;text-align:center;gap:7px;background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(0,0,0,.08))}.viewport-empty .camera-frame{position:absolute;inset:5% 6%;border:1px solid rgba(65,173,124,.8)}.viewport-empty b,.viewport-empty span{position:relative;z-index:2}.viewport-empty span{max-width:420px;color:#93a0aa}.preview-nav{height:42px;flex:0 0 42px;border-top:1px solid #2b363e;background:#111a21;display:grid;grid-template-columns:38px minmax(0,1fr) 38px;align-items:center;gap:8px;padding:6px 10px}.preview-nav button{height:28px;border:1px solid #303e49;background:#1b2730;border-radius:3px;cursor:pointer;font-weight:800}.preview-nav button:disabled{opacity:.35;cursor:not-allowed}.preview-frame-label{min-width:0;text-align:center;color:#aeb9c1;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .right-stack{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:hidden;background:transparent}.side-section{position:relative;flex:0 0 auto;min-height:96px;background:#151f27;border:1px solid #2c3740;border-radius:10px;display:flex;flex-direction:column;overflow:hidden}.playblast-settings-section{min-height:150px}.video-assets-section{min-height:240px;flex:1 1 0}.section-head{height:34px;flex:0 0 34px;display:flex;align-items:center;padding:0 10px;border-bottom:1px solid #2c3740;background:#18232b;font-weight:700}.section-head .grow{flex:1}.section-head .section-tools{margin-left:auto;display:flex;align-items:center;gap:5px}.video-selected-count{margin-left:auto;color:#aeb9c1;font-size:10px;font-variant-numeric:tabular-nums}.import-video-button{height:24px;margin-left:8px;padding:0 8px;border:1px solid #35434e;border-radius:6px;background:#111a21;color:#dce5eb;cursor:pointer;font-size:9px}.activity-section{min-height:150px}.activity-section .section-head{justify-content:flex-start}.activity-clear{height:23px;border:1px solid #35434e;background:#111a21;color:#c7d0d7;border-radius:7px;padding:0 8px;cursor:pointer;font-size:9px}.activity-elapsed{min-width:74px;text-align:right;font-size:9px;color:#aeb9c1;font-variant-numeric:tabular-nums}.activity-body{flex:1;min-width:0;min-height:0;overflow:hidden;padding:0;background:#0e161d;contain:layout paint}.activity-log-view{display:block;width:100%;height:100%;min-width:0;min-height:0;max-width:100%;margin:0;padding:6px 8px;overflow-x:auto;overflow-y:auto;scrollbar-gutter:stable both-edges;color:#cbd5dc;background:transparent;font:10px/1.5 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;user-select:text;-webkit-user-select:text;pointer-events:auto}.activity-log-row{display:grid;grid-template-columns:68px 58px max-content;align-items:center;width:max-content;min-width:100%;height:18px;min-height:18px;max-height:18px;overflow:visible;white-space:nowrap;color:#cbd5dc}.activity-log-time{overflow:hidden;color:#7f8e99;font-variant-numeric:tabular-nums}.activity-log-level{overflow:hidden;font-weight:800}.activity-log-message{display:block;min-width:max-content;max-width:none;overflow:visible;text-overflow:clip;white-space:nowrap}.activity-log-row[data-level="ERROR"]{color:#fb7185}.activity-log-row[data-level="ERROR"] .activity-log-time{color:#fb7185}.activity-log-row[data-level="WARNING"]{color:#fbbf24}.activity-log-row[data-level="WARNING"] .activity-log-time{color:#d6a51d}.activity-log-row[data-level="SUCCESS"]{color:#4ade80}.activity-log-row[data-level="SUCCESS"] .activity-log-time{color:#3bbd6b}.activity-log-empty{padding:4px 0;color:#7f8e99;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.section-resize-handle{position:relative;left:auto;right:auto;bottom:auto;flex:0 0 10px;min-height:10px;height:10px;border-top:1px solid #2c3740;cursor:ns-resize;background:linear-gradient(90deg,transparent,rgba(148,163,184,.16),transparent);touch-action:none}.section-resize-handle:before{content:"";position:absolute;left:50%;top:3px;width:44px;height:3px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.48)}.section-resize-handle:hover:before{background:#fff}.section-body{padding:9px}.side-section>.section-body{flex:1;min-height:0;overflow:auto;padding-bottom:9px}.palette-head{display:flex;flex-direction:column;align-items:stretch;gap:7px;min-width:0}.palette-group{display:grid;grid-template-columns:minmax(82px,92px) minmax(0,1fr);align-items:center;gap:6px;min-width:0}.palette-label{height:26px;min-width:0;display:flex;align-items:center;padding:0 7px;background:#26343f;border:1px solid #364652;border-radius:7px;color:#d5dde3;white-space:nowrap;font-size:10px}.palette-grid{display:flex;gap:4px;flex-wrap:wrap;min-width:0}.palette-button{width:20px;height:20px;border:2px solid transparent;border-radius:3px;cursor:pointer;padding:0}.palette-button.active{border-color:#f4f7f9;box-shadow:0 0 0 1px #111}.video-assets-body{flex:1;min-height:0;overflow:auto;padding:8px}.video-asset-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:8px}.video-assets-empty{grid-column:1/-1;min-height:130px;display:grid;place-items:center;padding:16px;border:1px dashed #35434e;border-radius:8px;color:#8998a3;text-align:center}.video-asset-card{position:relative;overflow:hidden;border:1px solid var(--hmb-line-soft,#344550);border-radius:9px;background:linear-gradient(145deg,rgba(255,255,255,.025),rgba(255,255,255,.006)),var(--hmb-field,#101820);transition:border-color 100ms ease,box-shadow 100ms ease}.video-asset-card[draggable="true"]{cursor:grab}.video-asset-card.dragging{opacity:.5;transform:scale(.985)}.video-asset-card.drop-target{border-color:rgb(var(--selection-rgb));box-shadow:0 0 0 1px rgba(var(--selection-rgb),.35)}.video-asset-card.selected{border-color:rgb(var(--selection-rgb));background:linear-gradient(145deg,rgba(var(--selection-rgb),.12),var(--selection-card));box-shadow:0 0 0 1px rgba(var(--selection-rgb),.16),0 0 18px rgba(var(--selection-rgb),.12)}.video-asset-thumb{position:relative;aspect-ratio:16/9;overflow:hidden;background:#080d14}.video-asset-thumb-media{width:100%;height:100%;object-fit:cover;pointer-events:none}.video-asset-thumb-fallback{position:absolute;inset:0;display:grid;place-items:center;color:#667684;font-size:10px;font-weight:800}.video-asset-role,.selected-video-order{position:absolute;top:7px;padding:3px 6px;border-radius:5px;background:rgba(5,8,18,.82);color:#fff;font-size:9px;font-weight:800}.video-asset-role{left:7px}.selected-video-order{right:7px;color:var(--selection-strong)}.video-asset-play{position:absolute;left:50%;top:50%;width:38px;height:38px;transform:translate(-50%,-50%);display:grid;place-items:center;border:1px solid rgba(255,255,255,.30);border-radius:50%;background:rgba(5,8,18,.76);color:#fff;cursor:pointer}.video-asset-delete{position:absolute;right:7px;bottom:7px;width:26px;height:26px;border:1px solid rgba(251,113,133,.45);border-radius:6px;background:rgba(76,5,25,.80);color:#ffe4e8;cursor:pointer}.video-asset-copy{padding:8px}.video-asset-copy>b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:#edf2f5}.video-asset-footer{display:flex;align-items:center;gap:6px;margin-top:6px}.video-asset-footer>span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8f9da7;font-size:9px}.video-asset-footer button,.video-order-actions button{height:25px;padding:0 7px;border:1px solid #35434e;border-radius:6px;background:#111a21;color:#dce5eb;cursor:pointer;font-size:9px}.video-order-actions{display:flex;justify-content:flex-end;gap:4px;margin-top:5px}.video-order-hint{flex:0 0 auto;padding:5px 8px;border-top:1px solid #2c3740;color:#7f8e99;font-size:9px;text-align:center}
      .radio-list{display:flex;flex-direction:column;gap:9px}.radio-row{display:grid;grid-template-columns:18px 1fr;align-items:start;cursor:pointer}.radio-row input{margin-top:3px;accent-color:#4c8fd7}.radio-row b{display:block;font-size:11px}.radio-row span{display:block;font-size:9px;color:#8f9ca6;margin-top:2px}.settings-action{position:sticky;top:0;z-index:4;padding:0 0 8px;background:linear-gradient(180deg,var(--hmb-panel-top,#151f27) 82%,rgba(21,31,39,0));}.settings-action .setting-checks{margin-top:7px}.settings-grid{display:grid;grid-template-columns:78px minmax(0,1fr);gap:7px 8px;align-items:center;font-size:10px}.setting-value{height:27px;display:flex;align-items:center;padding:0 8px;background:#202d36;border:1px solid #2c3b46;color:#d7dfe4;border-radius:2px}.setting-value.split{justify-content:space-between}.settings-compact-row{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,.72fr) minmax(0,1.28fr) minmax(0,1fr);gap:5px;min-width:0}.settings-compact-item{height:27px;min-width:0;display:flex;align-items:center;justify-content:space-between;gap:4px;padding:0 6px;background:#202d36;border:1px solid #2c3b46;color:#d7dfe4;border-radius:2px;white-space:nowrap;overflow:hidden}.settings-compact-item b{flex:0 0 auto;font-size:8px;color:#8f9ca6}.settings-compact-item span{min-width:0;overflow:hidden;text-overflow:ellipsis}.setting-checks{display:flex;gap:12px;margin-top:0;font-size:9px;color:#aab6bf}.setting-checks label{display:flex;align-items:center;gap:5px}.setting-checks input{accent-color:#4c8fd7}.generate-button{width:100%;height:34px;margin:0;border:1px solid #346ba4;background:#285b91;color:#fff;font-weight:700;cursor:pointer}.generate-button:disabled,.palette-button:disabled{opacity:.4;cursor:not-allowed}
      .empty-pane{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;color:#8998a3;text-align:center;padding:20px}.empty-pane b{color:#c9d2d8}
      .video-asset-grid{grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}
      .video-asset-thumb{cursor:pointer;outline:0}.video-asset-thumb:focus-visible{box-shadow:inset 0 0 0 2px var(--hmb-focus),inset 0 0 18px var(--hmb-glow)}.video-asset-thumb.is-playing .video-asset-play{border-color:var(--hmb-focus);background:rgba(5,8,18,.88);box-shadow:0 0 14px var(--hmb-glow)}.video-asset-play{z-index:3;pointer-events:none;font-size:15px;font-weight:900}.video-asset-delete{top:7px;right:7px;bottom:auto;z-index:5}.selected-video-order{top:auto;right:7px;bottom:7px}.video-asset-copy{display:grid;gap:3px;padding:7px 8px 8px}.video-asset-title{display:block;width:100%;min-width:0;padding:0;border:0;background:transparent;color:#edf2f5;font:inherit;font-size:11px;font-weight:800;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.video-asset-title:not(:disabled):hover{color:var(--selection-strong)}.video-asset-title:disabled{opacity:.48;cursor:not-allowed}.video-asset-details{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8f9da7;font-size:9px}.import-video-button{display:inline-flex;align-items:center;justify-content:center;gap:5px;font-weight:800}.import-video-icon{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
      .video-asset-card.selected{border-width:2px;border-color:rgb(var(--selection-rgb));box-shadow:0 0 0 2px rgba(var(--selection-rgb),.82),0 0 28px rgba(var(--selection-rgb),.62),inset 0 0 16px rgba(var(--selection-rgb),.12)}.video-asset-copy{min-height:52px;cursor:pointer;outline:0}.video-asset-copy:not([aria-disabled="true"]):hover{background:rgba(var(--selection-rgb),.12)}.video-asset-copy:focus-visible{background:rgba(var(--selection-rgb),.14);box-shadow:inset 0 0 0 2px var(--hmb-focus)}.video-asset-copy[aria-disabled="true"]{cursor:not-allowed;opacity:.48}.video-asset-title,.video-asset-details{pointer-events:none}.video-asset-title{cursor:inherit}
      .video-asset-thumb{cursor:inherit}.video-asset-play{pointer-events:auto}.video-asset-role,.selected-video-order{pointer-events:none}
      .hmbvp .video-asset-play,.hmbvp.hmbvp-compact .compact-video-play{touch-action:manipulation;user-select:none;transition:none}.hmbvp.hmbvp-compact .compact-video-play{width:34px;height:34px;font-size:11px}
      @container(max-width:1250px){.main-grid{grid-template-columns:280px minmax(420px,1fr)}.right-stack{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1fr);overflow:visible}}
      @container(max-width:930px){.hmbvp{--safe-x:12px}}
      @container(max-width:620px){.hmbvp{--safe-x:6px}}

      .original-preview-toggle,.mask-playblast-toggle,.depth-playblast-toggle,.motion-guide-toggle{height:25px;display:inline-flex;align-items:center;gap:5px;padding:0 8px;border:1px solid #344550;border-radius:3px;background:#101820;color:#dce5eb;font-size:10px;font-weight:700;white-space:nowrap;cursor:pointer}
      .original-preview-toggle input,.mask-playblast-toggle input,.depth-playblast-toggle input,.motion-guide-toggle input{margin:0;accent-color:#4c8fd7}
      .original-preview-toggle:has(input:disabled),.mask-playblast-toggle:has(input:disabled),.depth-playblast-toggle:has(input:disabled),.motion-guide-toggle:has(input:disabled){opacity:.4;cursor:not-allowed}

      /* Shared UI theme follower. Color-only overrides preserve the original layout and behavior. */
      .hmbvp[data-theme="P"]{--hmb-shell:#090c16;--hmb-deep:#060912;--hmb-work:#070b13;--hmb-panel-top:#101523;--hmb-panel-bottom:#090e18;--hmb-head-top:#2b173e;--hmb-head-mid:#171329;--hmb-head-bottom:#0e1422;--hmb-line:rgba(148,163,184,.20);--hmb-line-soft:rgba(148,163,184,.14);--hmb-field:#070c15;--hmb-hover:rgba(34,211,238,.09);--hmb-selected:linear-gradient(90deg,rgba(190,24,93,.30),rgba(88,28,135,.24));--hmb-primary-top:rgba(190,24,93,.68);--hmb-primary-bottom:rgba(88,28,135,.58);--hmb-primary-line:rgba(244,114,182,.72);--hmb-secondary:#a855f7;--hmb-focus:#22d3ee;--hmb-accent:#22d3ee;--hmb-accent-2:#f472b6;--hmb-text:#e6edf7;--hmb-muted:#8fa3b8;--hmb-glow:rgba(168,85,247,.16);--selection-rgb:244,114,182;--selection-deep-rgb:190,24,93;--selection-secondary-rgb:217,70,239;--selection-text:#f8c6df;--selection-soft:#f3a8ce;--selection-strong:#ffe4f2;--selection-card:rgba(61,23,49,.60)}
      .hmbvp[data-theme="T"]{--hmb-shell:#091525;--hmb-deep:#050a12;--hmb-work:#07111d;--hmb-panel-top:#0c1b2e;--hmb-panel-bottom:#07111d;--hmb-head-top:#153a63;--hmb-head-mid:#0f2947;--hmb-head-bottom:#081827;--hmb-line:rgba(96,165,250,.25);--hmb-line-soft:rgba(96,165,250,.15);--hmb-field:#07111d;--hmb-hover:rgba(56,189,248,.13);--hmb-selected:linear-gradient(90deg,rgba(37,99,235,.48),rgba(14,116,144,.28));--hmb-primary-top:#2563eb;--hmb-primary-bottom:#174ea6;--hmb-primary-line:#60a5fa;--hmb-secondary:#38bdf8;--hmb-focus:#38bdf8;--hmb-accent:#38bdf8;--hmb-accent-2:#60a5fa;--hmb-text:#e7f3ff;--hmb-muted:#89a5c2;--hmb-glow:rgba(37,99,235,.20);--selection-rgb:56,189,248;--selection-deep-rgb:3,105,161;--selection-secondary-rgb:37,99,235;--selection-text:#bae6fd;--selection-soft:#7dd3fc;--selection-strong:#e0f2fe;--selection-card:rgba(12,48,78,.62)}
      .hmbvp[data-theme]{background:radial-gradient(circle at 50% -12%,var(--hmb-glow),transparent 40%),linear-gradient(180deg,var(--hmb-shell),#070b12);color:#fff;border-color:var(--hmb-line);box-shadow:0 12px 34px rgba(0,0,0,.28),inset 0 0 0 1px rgba(255,255,255,.025)}
      .hmbvp[data-theme] .app-header{background:linear-gradient(180deg,var(--hmb-head-top) 0%,var(--hmb-head-mid) 42%,var(--hmb-head-bottom) 100%);border-bottom-color:var(--hmb-line)}
      .hmbvp[data-theme] .main-grid{background:radial-gradient(circle at 52% 0%,var(--hmb-glow),transparent 38%),linear-gradient(180deg,var(--hmb-work),#070b12)}
      .hmbvp[data-theme] .panel,.hmbvp[data-theme] .side-section,.hmbvp[data-theme] .viewport-panel{background:linear-gradient(180deg,var(--hmb-panel-top),var(--hmb-panel-bottom));border-color:var(--hmb-line);box-shadow:0 9px 24px rgba(0,0,0,.16)}
      .hmbvp[data-theme] .panel-title,.hmbvp[data-theme] .section-head,.hmbvp[data-theme] .output-scope-inline,.hmbvp[data-theme] .preview-nav{background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.012)),linear-gradient(180deg,var(--hmb-head-mid),var(--hmb-head-bottom));border-color:var(--hmb-line)}
      .hmbvp[data-theme] .brand,.hmbvp[data-theme] .brand-mark:after,.hmbvp[data-theme] .output-scope-title,.hmbvp[data-theme] .output-scope-option,.hmbvp[data-theme] .panel-title,.hmbvp[data-theme] .panel-title small,.hmbvp[data-theme] .section-head,.hmbvp[data-theme] .column-head,.hmbvp[data-theme] .outliner-row,.hmbvp[data-theme] .tree-toggle,.hmbvp[data-theme] .node-icon,.hmbvp[data-theme] .group-name,.hmbvp[data-theme] .ref-tag,.hmbvp[data-theme] .camera-fixed,.hmbvp[data-theme] .camera-fixed span,.hmbvp[data-theme] .camera-fixed b,.hmbvp[data-theme] .camera-fixed em,.hmbvp[data-theme] .camera-dropdown summary,.hmbvp[data-theme] .camera-dropdown summary span,.hmbvp[data-theme] .camera-dropdown summary b,.hmbvp[data-theme] .camera-menu button,.hmbvp[data-theme] .camera-menu button span,.hmbvp[data-theme] .viewport-empty,.hmbvp[data-theme] .viewport-empty span,.hmbvp[data-theme] .preview-frame-label,.hmbvp[data-theme] .palette-label,.hmbvp[data-theme] .radio-row,.hmbvp[data-theme] .radio-row span,.hmbvp[data-theme] .settings-grid,.hmbvp[data-theme] .setting-value,.hmbvp[data-theme] .setting-checks,.hmbvp[data-theme] .empty-pane,.hmbvp[data-theme] .empty-pane b{color:#fff}
      .hmbvp[data-theme] .panel-title small,.hmbvp[data-theme] .column-head,.hmbvp[data-theme] .camera-fixed span,.hmbvp[data-theme] .camera-dropdown summary span,.hmbvp[data-theme] .camera-menu button span,.hmbvp[data-theme] .preview-frame-label,.hmbvp[data-theme] .radio-row span,.hmbvp[data-theme] .setting-checks{opacity:.72}
      .hmbvp[data-theme] .brand-mark{border-color:rgba(255,255,255,.88)}
      .hmbvp[data-theme] .step{color:rgba(255,255,255,.72)}
      .hmbvp[data-theme] .header-actions button,.hmbvp[data-theme] .activity-clear,.hmbvp[data-theme] .import-video-button,.hmbvp[data-theme] .search-input,.hmbvp[data-theme] .camera-fixed,.hmbvp[data-theme] .camera-dropdown summary,.hmbvp[data-theme] .palette-label,.hmbvp[data-theme] .setting-value,.hmbvp[data-theme] .preview-nav button{background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.008)),var(--hmb-field);border-color:var(--hmb-line-soft);color:#fff}
      .hmbvp[data-theme] .header-actions .read-button,.hmbvp[data-theme] .generate-button,.hmbvp[data-theme] .import-video-button{background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom));border-color:var(--hmb-primary-line);color:#fff}
      .hmbvp[data-theme] .header-actions .stop-button{background:linear-gradient(180deg,#71353c,#492329);border-color:#8d5058;color:#fff}
      .hmbvp[data-theme] .snapshot-toolbar #create-snapshot{background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom));border-color:var(--hmb-primary-line);color:#fff}
      .hmbvp[data-theme] .snapshot-toolbar #delete-snapshot{background:linear-gradient(180deg,#71353c,#492329);border-color:#8d5058;color:#fff}
      .hmbvp[data-theme] .search-input::placeholder{color:rgba(255,255,255,.52)}
      .hmbvp[data-theme] .search-input:focus{border-color:var(--hmb-focus);box-shadow:0 0 0 1px var(--hmb-focus),0 0 16px var(--hmb-glow)}
      .hmbvp[data-theme] .outliner-palette,.hmbvp[data-theme] .outliner-toolbar,.hmbvp[data-theme] .column-head{border-color:var(--hmb-line-soft)}
      .hmbvp[data-theme] .outliner-row:hover{background:var(--hmb-hover)}
      .hmbvp[data-theme] .outliner-row.selected{background:var(--hmb-selected)}
      .hmbvp[data-theme] .viewport-stage{background:radial-gradient(circle at 50% 34%,rgba(255,255,255,.16),rgba(255,255,255,.04) 30%,transparent 48%),linear-gradient(180deg,var(--hmb-panel-top),var(--hmb-panel-bottom))}
      .hmbvp[data-theme] .viewport-empty{border-color:var(--hmb-focus);background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.01))}
      .hmbvp[data-theme] .viewport-empty .camera-frame{border-color:rgba(255,255,255,.36)}
      .hmbvp[data-theme] .camera-menu{background:linear-gradient(180deg,var(--hmb-panel-top),var(--hmb-panel-bottom));border-color:var(--hmb-line);box-shadow:0 8px 18px rgba(0,0,0,.5)}
      .hmbvp[data-theme] .camera-menu button:hover,.hmbvp[data-theme] .camera-menu button.active{background:var(--hmb-hover)}
      .hmbvp[data-theme] .palette-button.active{border-color:#fff;box-shadow:0 0 0 1px rgba(0,0,0,.65)}
      .hmbvp[data-theme] .radio-row input,.hmbvp[data-theme] .setting-checks input{accent-color:var(--hmb-accent)}
      .hmbvp .app-header{border-radius:10px 10px 0 0}

      /* ImageAsset-aligned visual language. These late overrides are deliberately
         paint-only: control identity, geometry, state, and interaction stay intact. */
      .hmbvp[data-theme]{background:radial-gradient(circle at 8% -10%,var(--hmb-glow),transparent 34%),linear-gradient(180deg,var(--hmb-shell),var(--hmb-deep));color:var(--hmb-text);border-color:var(--hmb-line);box-shadow:0 18px 44px rgba(0,0,0,.34),inset 0 0 0 1px rgba(255,255,255,.025)}
      .hmbvp[data-theme] .app-header{background:radial-gradient(circle at 8% -45%,var(--hmb-glow),transparent 52%),linear-gradient(90deg,var(--hmb-head-top),var(--hmb-head-mid) 42%,var(--hmb-head-bottom));border-bottom-color:var(--hmb-line);box-shadow:inset 0 -1px 0 rgba(255,255,255,.018)}
      .hmbvp[data-theme] .main-grid{background:radial-gradient(circle at 8% -8%,var(--hmb-glow),transparent 35%),linear-gradient(180deg,var(--hmb-work),var(--hmb-deep))}
      .hmbvp[data-theme] .panel,.hmbvp[data-theme] .side-section,.hmbvp[data-theme] .viewport-panel{background:linear-gradient(145deg,var(--hmb-panel-top),var(--hmb-panel-bottom));border-color:var(--hmb-line);box-shadow:0 10px 26px rgba(0,0,0,.20),inset 0 1px 0 rgba(255,255,255,.018)}
      .hmbvp[data-theme] .panel-title,.hmbvp[data-theme] .section-head,.hmbvp[data-theme] .output-scope-inline,.hmbvp[data-theme] .preview-nav{background:linear-gradient(180deg,rgba(255,255,255,.038),rgba(255,255,255,.008)),var(--hmb-panel-top);border-color:var(--hmb-line-soft)}
      .hmbvp[data-theme] .brand{color:var(--hmb-text);font-size:15px;font-weight:800;letter-spacing:.01em}
      .hmbvp[data-theme] .brand-mark{border-width:1px;border-style:solid;border-radius:8px;transform:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.025)}
      .hmbvp[data-theme] .brand-mark:after{content:"VP";transform:none;font-size:9px;font-weight:950;letter-spacing:.04em}
      .hmbvp[data-theme] .brand-mark{border-color:var(--hmb-primary-line);background:rgba(var(--selection-rgb),.12);color:var(--hmb-accent);box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 13px var(--hmb-glow)}
      .hmbvp[data-theme] .shot-selector{border-color:rgba(var(--selection-rgb),.58);background:linear-gradient(180deg,rgba(var(--selection-rgb),.18),rgba(var(--selection-deep-rgb),.14)),var(--hmb-field);color:var(--selection-strong);box-shadow:0 0 12px var(--hmb-glow)}
      .hmbvp[data-theme] .shot-selector:focus{border-color:var(--hmb-focus);box-shadow:0 0 0 1px var(--hmb-focus),0 0 15px var(--hmb-glow)}
      .hmbvp[data-theme] .panel-title,.hmbvp[data-theme] .section-head{color:var(--hmb-text);font-weight:800;letter-spacing:.025em}
      .hmbvp[data-theme] .panel-title small,.hmbvp[data-theme] .column-head,.hmbvp[data-theme] .camera-fixed span,.hmbvp[data-theme] .camera-dropdown summary span,.hmbvp[data-theme] .camera-menu button span,.hmbvp[data-theme] .preview-frame-label,.hmbvp[data-theme] .radio-row span,.hmbvp[data-theme] .setting-checks,.hmbvp[data-theme] .scene-load-label,.hmbvp[data-theme] .frame-number-label,.hmbvp[data-theme] .video-selected-count,.hmbvp[data-theme] .video-order-hint{color:var(--hmb-muted)}
      .hmbvp[data-theme] .scene-load-bar,.hmbvp[data-theme] .snapshot-toolbar,.hmbvp[data-theme] .generate-playblast-toolbar,.hmbvp[data-theme] .playblast-settings-toolbar,.hmbvp[data-theme] .video-seekbar,.hmbvp[data-theme] .video-controls,.hmbvp[data-theme] .frame-info-strip{background:linear-gradient(180deg,rgba(255,255,255,.022),rgba(255,255,255,.004)),var(--hmb-field);border-color:var(--hmb-line-soft)}
      .hmbvp[data-theme] .activity-body{background:var(--hmb-deep)}
      .hmbvp[data-theme] .activity-log-view{color:var(--hmb-text)}
      .hmbvp[data-theme] .scene-path-input,.hmbvp[data-theme] .scene-load-bar button,.hmbvp[data-theme] .original-preview-toggle,.hmbvp[data-theme] .mask-playblast-toggle,.hmbvp[data-theme] .depth-playblast-toggle,.hmbvp[data-theme] .motion-guide-toggle,.hmbvp[data-theme] .setting-select,.hmbvp[data-theme] .video-controls button,.hmbvp[data-theme] .frame-number-label input,.hmbvp[data-theme] .snapshot-toolbar>button,.hmbvp[data-theme] .header-actions button,.hmbvp[data-theme] .activity-clear,.hmbvp[data-theme] .import-video-button,.hmbvp[data-theme] .search-input,.hmbvp[data-theme] .camera-fixed,.hmbvp[data-theme] .camera-dropdown summary,.hmbvp[data-theme] .palette-label,.hmbvp[data-theme] .setting-value,.hmbvp[data-theme] .preview-nav button,.hmbvp[data-theme] .video-asset-footer button,.hmbvp[data-theme] .video-order-actions button{border-color:var(--hmb-line-soft);border-radius:7px;background:linear-gradient(180deg,rgba(255,255,255,.032),rgba(255,255,255,.006)),var(--hmb-field);color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.018)}
      .hmbvp[data-theme] button{letter-spacing:.01em}
      .hmbvp[data-theme] .scene-load-bar .load-scene-button,.hmbvp[data-theme] .snapshot-toolbar #create-snapshot,.hmbvp[data-theme] .generate-button,.hmbvp[data-theme] .import-video-button{border-color:var(--hmb-primary-line);border-radius:7px;background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom));color:#fff;box-shadow:0 0 14px var(--hmb-glow),inset 0 1px 0 rgba(255,255,255,.10)}
      .hmbvp[data-theme] .header-actions .stop-button,.hmbvp[data-theme] .snapshot-toolbar #delete-snapshot,.hmbvp[data-theme] .video-asset-delete{border-color:rgba(251,113,133,.50);background:linear-gradient(180deg,rgba(159,18,57,.74),rgba(76,5,25,.84));color:#ffe4e8;box-shadow:inset 0 1px 0 rgba(255,255,255,.07)}
      .hmbvp[data-theme] .scene-path-input:focus,.hmbvp[data-theme] .setting-select:focus,.hmbvp[data-theme] .frame-number-label input:focus,.hmbvp[data-theme] .search-input:focus,.hmbvp[data-theme] .camera-dropdown summary:focus-visible,.hmbvp[data-theme] button:focus-visible{outline:0;border-color:var(--hmb-focus);box-shadow:0 0 0 1px var(--hmb-focus),0 0 14px var(--hmb-glow)}
      .hmbvp[data-theme] .scene-load-bar button:not(:disabled):hover,.hmbvp[data-theme] .generate-playblast-toolbar .generate-button:not(:disabled):hover,.hmbvp[data-theme] .video-controls button:not(:disabled):hover,.hmbvp[data-theme] .snapshot-toolbar>button:not(:disabled):hover,.hmbvp[data-theme] .header-actions button:not(:disabled):hover,.hmbvp[data-theme] .preview-nav button:not(:disabled):hover,.hmbvp[data-theme] .activity-clear:not(:disabled):hover,.hmbvp[data-theme] .import-video-button:not(:disabled):hover,.hmbvp[data-theme] .video-asset-footer button:not(:disabled):hover,.hmbvp[data-theme] .video-order-actions button:not(:disabled):hover{border-color:var(--hmb-focus);color:#fff;box-shadow:0 0 12px var(--hmb-glow)}
      .hmbvp[data-theme] .outliner-row.selected{background:var(--hmb-selected);box-shadow:inset 2px 0 0 var(--hmb-accent-2),0 0 12px var(--hmb-glow)}
      .hmbvp[data-theme] .outliner-row:hover{background:var(--hmb-hover)}
      .hmbvp[data-theme] .video-seekbar input,.hmbvp[data-theme] .output-scope-option input,.hmbvp[data-theme] .original-preview-toggle input,.hmbvp[data-theme] .mask-playblast-toggle input,.hmbvp[data-theme] .depth-playblast-toggle input,.hmbvp[data-theme] .motion-guide-toggle input,.hmbvp[data-theme] .radio-row input,.hmbvp[data-theme] .setting-checks input{accent-color:var(--hmb-accent)}
      .hmbvp[data-theme] .viewport-empty{border-color:var(--hmb-focus);box-shadow:inset 0 0 0 1px rgba(255,255,255,.018),0 0 18px var(--hmb-glow)}
      .hmbvp[data-theme] .viewport-empty .camera-frame{border-color:color-mix(in srgb,var(--hmb-focus) 58%,transparent)}
      .hmbvp[data-theme] .panel-resize-handle,.hmbvp[data-theme] .section-resize-handle{border-color:var(--hmb-line-soft);background:linear-gradient(90deg,transparent,var(--hmb-line-soft),transparent)}
      .hmbvp[data-theme] .panel-resize-handle:before,.hmbvp[data-theme] .section-resize-handle:before{background:var(--hmb-muted);opacity:.48}
      .hmbvp[data-theme] .video-assets-section>.section-resize-handle{border-top-color:transparent;background:transparent}.hmbvp[data-theme] .video-assets-section>.section-resize-handle:before{display:none}
      .hmbvp .brand{font-size:15px;font-weight:800;letter-spacing:.01em;font-style:normal;line-height:normal}
      .hmbvp .shot-selector{flex:0 1 210px;width:210px;min-width:120px;max-width:210px;height:44px;font-size:13px;font-weight:800;font-style:normal;line-height:normal}
      .hmbvp .add-picker-shot-button{border-color:var(--hmb-primary-line);background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom));color:#fff;font-weight:850}.hmbvp .picker-shot-tabs{display:flex;align-items:stretch;gap:6px;overflow-x:auto;padding:6px 8px;border-bottom:1px solid #2c3740}.hmbvp .picker-shot-tab{display:grid;grid-template-columns:30px minmax(72px,1fr) 34px 24px 26px 26px;align-items:center;gap:4px;flex:1 1 190px;min-width:190px;max-width:300px;height:36px;padding:3px;border:1px solid color-mix(in srgb,var(--local-shot-accent) 48%,#263449);border-radius:7px;background:color-mix(in srgb,var(--local-shot-deep) 16%,#0d1423)}.hmbvp .picker-shot-tab.active{border-color:var(--local-shot-accent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--local-shot-accent) 38%,transparent)}.hmbvp .picker-shot-activate,.hmbvp .picker-shot-rename,.hmbvp .picker-shot-delete{height:28px;border:1px solid color-mix(in srgb,var(--local-shot-accent) 42%,#334155);border-radius:5px;background:#101827;color:#fff;cursor:pointer}.hmbvp .picker-shot-number{font-size:9px;font-weight:950}.hmbvp .picker-shot-name-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;font-weight:800;color:#eef2f7}.hmbvp .picker-shot-binding-chip{height:20px;display:grid;place-items:center;border-left:3px solid var(--remote-shot-accent,#64748b);border-radius:4px;background:#111827;color:#aeb9c1;font-size:7px;font-weight:900}.hmbvp .picker-shot-video-count{font-size:8px;text-align:center;color:var(--selection-soft)}.hmbvp .picker-shot-name-input{height:24px;width:100%;border:1px solid var(--local-shot-accent);border-radius:5px;background:#060b13;color:#f8fafc;padding:0 6px;outline:none}.hmbvp .picker-shot-actions{min-height:52px;display:flex;align-items:center;gap:8px;padding:4px 8px;border-bottom:1px solid #2c3740;background:#18232b}.hmbvp .picker-shot-actions .spacer{flex:1}.hmbvp .picker-shot-actions .compact-current-videos-title{font-size:10px;color:var(--selection-text);white-space:nowrap}
      .hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"]{display:flex;flex-wrap:wrap;align-items:center;align-content:center;gap:6px;overflow:hidden;padding:6px 8px}
      .hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"]>.picker-shot-tab{display:block;flex:0 0 44px;width:44px;min-width:44px;max-width:44px;height:44px;padding:0;border-radius:7px;overflow:hidden}
      .hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"] .picker-shot-activate{width:44px;height:44px;padding:0;border:0;background:transparent;color:var(--local-shot-accent);font-size:13px;font-weight:800;font-variant-numeric:tabular-nums}
      .hmbvp .picker-shot-tabs[data-picker-shot-layout="expanded"] .picker-shot-number{font-size:13px;font-weight:800}
      .hmbvp .picker-active-shot-controls{display:flex;align-items:center;gap:6px;max-width:220px}.hmbvp .picker-active-shot-controls>b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmbvp .picker-active-shot-controls .picker-shot-rename,.hmbvp .picker-active-shot-controls .picker-shot-delete{width:28px;min-width:28px;padding:0}
      .hmbvp .video-assets-toolbar{height:42px;flex:0 0 42px;display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--hmb-line-soft,#2c3740);background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,.004)),var(--hmb-field,#18232b)}.hmbvp .video-assets-active-shot{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--selection-text);font-size:10px}.hmbvp .video-assets-toolbar .video-selected-count{margin-left:auto}.hmbvp .video-assets-toolbar .import-video-button{height:30px;margin:0;padding:0 12px}
      </style>
    <div class="hmbvp-clip nodrag"><div class="hmbvp" data-picker-view="expanded" data-theme="${uiTheme}" data-shot-number="${shotPalette.number}" data-state-revision="${Number(state.state_revision || 0)}" data-canvas-motion="false" style="${shotPaletteStyle}">
      ${fixedTopMarkup}
      <div class="scene-load-bar">
        <span class="scene-load-label">MAYA SCENE</span>
        <input type="text" class="scene-path-input nodrag" id="maya-scene-path" value="${escapeHtml(mayaSceneDraftPath)}" placeholder="${escapeHtml(tr.scenePath)}" ${runningOperation ? "disabled" : ""}/>
        <button type="button" id="browse-maya-scene" ${runningOperation ? "disabled" : ""}>${escapeHtml(tr.browse)}</button>
        <button type="button" class="load-scene-button read-button" id="read-scene" ${!buttonAvailability.readEnabled ? "disabled" : ""}>${escapeHtml(tr.read)}</button>
        <label class="original-preview-toggle"><input type="checkbox" id="original-preview-toggle" ${originalPreviewChecked ? "checked" : ""} ${runningOperation ? "disabled" : ""}/><span>${escapeHtml(tr.originalPreview || "Original Playblast")}</span></label>
        <label class="mask-playblast-toggle"><input type="checkbox" id="mask-playblast-toggle" ${maskChecked ? "checked" : ""} ${runningOperation ? "disabled" : ""}/><span>${escapeHtml(tr.mask || "Mask")}</span></label>
        <label class="depth-playblast-toggle"><input type="checkbox" id="depth-playblast-toggle" ${depthChecked ? "checked" : ""} ${runningOperation ? "disabled" : ""}/><span>${escapeHtml(tr.depth || "Depth")}</span></label>
        <label class="motion-guide-toggle"><input type="checkbox" id="motion-guide-toggle" ${motionGuideChecked ? "checked" : ""} ${runningOperation ? "disabled" : ""}/><span>${escapeHtml(tr.motionGuide || "Motion Guide")}</span></label>
      </div>
      <main class="main-grid">
        <section class="panel outliner-panel">
          <div class="panel-title">${escapeHtml(tr.outliner)} <small>(${escapeHtml(tr.filteredPolygon)})</small></div>
          <div class="outliner-palette">
            <div class="palette-head">
              <div class="palette-group"><div class="palette-label">${escapeHtml(tr.presetActor)}</div><div class="palette-grid" data-palette-kind="actor">${actorOptions.map((name) => `<button type="button" class="palette-button ${state.selected_color === name ? "active" : ""}" data-color="${escapeHtml(name)}" title="${escapeHtml(name)}" aria-label="${escapeHtml(`${tr.presetActor}: ${name}`)}" style="${hmbPickerColorStyle(name, state.marker_catalog)}" ${initialLocked || !selectedNode ? "disabled" : ""}></button>`).join("")}</div></div>
              <div class="palette-group"><div class="palette-label" title="${escapeHtml(tr.presetGhostScope)}">${escapeHtml(tr.presetGhost)}</div><div class="palette-grid" data-palette-kind="ghost" data-palette-scope="actor-background">${ghostOptions.map((name) => `<button type="button" class="palette-button ${state.selected_color === name ? "active" : ""}" data-color="${escapeHtml(name)}" title="${escapeHtml(`${name} · ${tr.presetGhostScope}`)}" aria-label="${escapeHtml(`${tr.presetGhost}: ${name}. ${tr.presetGhostScope}`)}" style="${hmbPickerColorStyle(name, state.marker_catalog)}" ${initialLocked || !selectedNode ? "disabled" : ""}></button>`).join("")}</div></div>
              <div class="palette-group"><div class="palette-label">${escapeHtml(tr.presetObject)}</div><div class="palette-grid" data-palette-kind="object">${objectOptions.map((name) => `<button type="button" class="palette-button ${state.selected_color === name ? "active" : ""}" data-color="${escapeHtml(name)}" title="${escapeHtml(name)}" aria-label="${escapeHtml(`${tr.presetObject}: ${name}`)}" style="${hmbPickerColorStyle(name, state.marker_catalog)}" ${initialLocked || !selectedNode ? "disabled" : ""}></button>`).join("")}</div></div>
            </div>
          </div>
          <div class="outliner-toolbar"><input id="outliner-search" class="search-input" value="${escapeHtml(state.outliner_search)}" placeholder="${escapeHtml(tr.search)}" aria-label="${escapeHtml(tr.search)}"/></div>
          <div class="column-head"><span>${escapeHtml(tr.name)}</span></div>
          <div class="outliner-scroll">${outlinerHtml(state, bindings, tr, initialLocked, outlinerRenderOptions)}</div>
        </section>
        <div class="center-stack">
        <section class="panel viewport-panel" style="${hmbFlexPanelHeightStyle(state.viewport_panel_height, HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT)}">
          <div class="snapshot-toolbar"><button type="button" id="create-snapshot" ${!buttonAvailability.snapshotEnabled ? "disabled" : ""}>${escapeHtml(tr.snapshot || "Snapshot")}</button><button type="button" id="delete-snapshot" ${!snapshotDeleteEnabled ? "disabled" : ""}>${escapeHtml(tr.deleteSnapshot || "Delete Snapshot")}</button><div class="output-camera-inline"><span class="output-camera-label">${escapeHtml(tr.cameraPrefix)} :</span>${cameraControlHtml(state, tr, runningOperation)}</div></div>
          <div class="generate-playblast-toolbar" role="group" aria-label="${escapeHtml(tr.generate)}"><button type="button" class="generate-button" id="run-video" aria-label="${escapeHtml(tr.generate)}" ${!buttonAvailability.playblastEnabled ? "disabled" : ""}>▶&nbsp; ${escapeHtml(tr.generate)}</button></div>
          <div class="playblast-settings-toolbar">
            <div class="settings-grid settings-grid-inline">
              <label class="settings-primary-item"><span class="settings-primary-label">${escapeHtml(tr.resolution)}</span><select id="playblast-resolution" class="setting-select" ${runningOperation ? "disabled" : ""}>${HMB_PLAYBLAST_RESOLUTIONS.map((item) => `<option value="${item.value}" ${item.width === Number(state.output_width) && item.height === Number(state.output_height) ? "selected" : ""}>${item.label}</option>`).join("")}</select></label>
              <div class="settings-primary-item"><span class="settings-primary-label">${escapeHtml(tr.frameRange)}</span><span class="setting-value split"><b>${escapeHtml(frameStartText)}</b><span>–</span><b>${escapeHtml(frameEndText)}</b></span></div>
              <div class="settings-compact-row"><span class="settings-compact-item" title="${escapeHtml(`${tr.fps}: ${fpsText}`)}"><b>${escapeHtml(tr.fps)}</b><span>${escapeHtml(fpsText)}</span></span><span class="settings-compact-item" title="${escapeHtml(`${tr.format}: MPEG-4 / H.264`)}"><b>${escapeHtml(tr.format)}</b><span>H.264</span></span><span class="settings-compact-item" title="${escapeHtml(`${tr.mayaVersion}: ${state.maya_version ? `Maya ${state.maya_version}` : tr.autoDetect}`)}"><b>${escapeHtml(tr.mayaVersion)}</b><span>${escapeHtml(state.maya_version || tr.autoDetect)}</span></span></div>
            </div>
          </div>
          <div class="panel-title viewport-title">${escapeHtml(tr.viewport)} <small>(${escapeHtml(viewportModeLabel)})</small></div>
          <div class="viewport-stage">${viewportMediaHtml}<div id="picker-preview-load-status" class="preview-load-status" role="alert" aria-live="assertive" hidden><span data-preview-load-message></span><button type="button" id="retry-picker-preview-load">${escapeHtml(tr.retryPreview || "Retry")}</button></div></div>
          <div class="video-seekbar"><input type="range" id="video-seek" min="${frameStart}" max="${frameEnd}" step="1" value="${Math.round(initialViewportFrame)}" aria-label="Video timeline" ${!selectedVideoUrl || snapshotForViewport || !hasFrameRange ? "disabled" : ""}/></div>
          <div class="video-controls"><button type="button" class="transport-button" id="snapshot-prev" title="${escapeHtml(tr.previousSnapshot || "Previous snapshot")}" aria-label="${escapeHtml(tr.previousSnapshot || "Previous snapshot")}" ${snapshotHistory.length ? "" : "disabled"}>◀</button><button type="button" class="transport-button" id="video-play-toggle" title="${escapeHtml(tr.playVideo || "Play")}" aria-label="${escapeHtml(tr.playVideo || "Play")}" ${selectedVideoUrl ? "" : "disabled"}>▶</button><button type="button" class="transport-button" id="snapshot-next" title="${escapeHtml(tr.nextSnapshot || "Next snapshot")}" aria-label="${escapeHtml(tr.nextSnapshot || "Next snapshot")}" ${snapshotHistory.length ? "" : "disabled"}>▶</button><label class="frame-number-label">${escapeHtml(tr.frameLabel)} <input type="number" id="video-frame-number" min="${frameStart}" max="${frameEnd}" step="1" value="${Math.round(initialViewportFrame)}" aria-label="${escapeHtml(tr.frameLabel)}" ${!hasFrameRange || snapshotForViewport ? "disabled" : ""}/></label></div>
          <div class="frame-info-strip"><span>FRAME <b id="frame-info-frame">${Math.round(initialViewportFrame)} / ${frameEnd}</b></span><span>TIME <b id="frame-info-time">${escapeHtml(initialTimecode)}</b></span><span>FPS <b id="frame-info-fps">${escapeHtml(frameInfoFps || "—")}</b></span><span>RANGE <b id="frame-info-range">${frameStart}–${frameEnd}</b></span></div>
          <div class="panel-resize-handle nodrag" data-resize-panel="viewport" title="${escapeHtml(tr.resizeSection)}"></div>
        </section>
          <section class="side-section activity-section preview-activity-section" data-section-key="log"><div class="section-head"><span class="grow">${escapeHtml(tr.activityLog)}</span><div class="section-tools"><span class="activity-elapsed" id="activity-elapsed" data-start-ms="${Number(state.operation_started_at_ms || 0)}">${escapeHtml(tr.elapsed)} ${elapsedText}</span><button type="button" class="activity-clear" id="clear-activity-log" ${activityRows.length ? "" : "disabled"}>${escapeHtml(tr.clearLog)}</button></div></div><div class="activity-body" id="activity-log-body"><div id="activity-log-view" class="activity-log-view" role="log" aria-live="polite" aria-label="${escapeHtml(tr.activityLog)}">${activityLogMarkup}</div></div></section>
        </div>
        <aside class="right-stack">
          <section class="side-section video-assets-section" data-section-key="color" style="${hmbSectionHeightStyle(rightSectionHeights, "color")}">
            ${pickerShotWorkspaceMarkup.tabs}
            <div class="video-assets-toolbar" data-video-assets-toolbar>
              <b class="video-assets-active-shot" data-picker-shot-name>${escapeHtml(fixedTopActiveShot?.name || "Shot 1")}</b>
              <span class="video-selected-count">${fixedTopSelectedCount}/${HMB_PICKER_MAX_REPRESENTATIVE_VIDEOS}</span>
              <button type="button" class="import-video-button" id="import-video-button" data-picker-shot-load="${escapeHtml(fixedTopActiveShot?.workspace_uuid || "")}" ${initialLocked || fixedTopAssetCount >= HMB_PICKER_MAX_ASSETS_PER_SHOT ? "disabled" : ""}><svg class="import-video-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m16 16 4 4"></path></svg><span>${escapeHtml(tr.load || tr.importVideoAsset || "LOAD")}</span></button>
            </div>
            <div class="video-assets-body"><div class="video-asset-grid">${videoAssetMarkup}</div></div>
            <div class="video-order-hint">${escapeHtml(tr.dragVideoOrder)}</div>
            <div class="section-resize-handle nodrag" data-resize-section="color" title="${escapeHtml(tr.resizeSection)}"></div>
          </section>
        </aside>
      </main>
    </div></div>` : compactPickerMarkup;
  const pickerViewState = hmbCapturePickerViewState(container);
  const pickerRenderMode = hmbRenderPickerMarkup(
    container,
    hmbScopeWidgetStyleMarkup(pickerMarkup, ".hmbvp"),
  );
  hmbAdoptVideoPickerFixedTop(container);
  hmbEnforceVideoPickerLoadSurfaces(
    container,
    pickerExpanded,
    fixedTopActiveShot?.workspace_uuid || "",
  );
  // Give the first paint a complete, top-anchored picker frame. The full node
  // fit runs after the host has finished mounting its native parameter rows.
  concealNativeMayaPicker(container);
  if (pickerExpanded) {
    hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
  } else {
    // Fit the first visible frame immediately.  The hidden host measurement
    // copy already owns the adaptive row allocation; the two settled RAFs
    // below only reconcile late font/media layout and never touch that row.
    hmbApplyVideoPickerCompactHostSizing(container, state);
    hmbInstallVideoPickerCompactHostSizing(container, activeCleanup, props || {}, state);
  }
  // Node internals publish is deferred to the single settled scheduler below;
  // never expose the pre-fit mount frame to the host allocator.
  const replacementViewportVideo = container.querySelector("#picker-video");
  if (
    retainedViewportVideo
    && replacementViewportVideo
    && replacementViewportVideo !== retainedViewportVideo
    && retainedViewportSource
    && retainedViewportSource === clean(replacementViewportVideo.getAttribute("src"))
  ) {
    replacementViewportVideo.replaceWith(retainedViewportVideo);
  }

  hmbRestorePickerViewState(container, pickerViewState);

  const settleRequestedPreviewSwitch = () => {
    const viewportPanel = container.querySelector(".viewport-panel");
    viewportPanel?.classList?.remove?.("is-switching");
    viewportPanel?.removeAttribute?.("aria-busy");
  };
  const markRequestedPreviewSwitchBusy = () => {
    const viewportPanel = container.querySelector(".viewport-panel");
    viewportPanel?.classList?.add?.("is-switching");
    viewportPanel?.setAttribute?.("aria-busy", "true");
  };
  const reportPlaybackFailure = (error, context = "Video playback") => {
    settleRequestedPreviewSwitch();
    delete container.__hmbAutoplayVideoUid;
    hmbShowPickerPreviewLoadFailure(container, tr.previewPlayFailed || tr.previewLoadFailed);
    const details = clean(error?.message || error);
    hmbAppendImmediateActivityLogRow(
      container.querySelector("#activity-log-view"),
      "ERROR",
      `${context} failed${details ? `: ${details}` : "."}`,
    );
    try { console.error("[HMBVideoPickerLibrary] playback failed", error); } catch (_consoleError) {}
  };
  const startRequestedPreview = () => {
    if (
      !Object.prototype.hasOwnProperty.call(container, "__hmbAutoplayVideoUid")
      || clean(container.__hmbAutoplayVideoUid) !== previewUid
    ) return;
    const autoplayVideo = container.querySelector("#picker-video");
    delete container.__hmbAutoplayVideoUid;
    const startPreview = () => {
      const playResult = autoplayVideo?.play?.();
      if (playResult && typeof playResult.catch === "function") {
        playResult.catch((error) => reportPlaybackFailure(error, "Requested preview playback"));
      }
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(startPreview);
    else startPreview();
  };
  const completeRequestedPreviewSwitch = () => {
    settleRequestedPreviewSwitch();
    hmbClearPickerPreviewLoadFailure(container);
    startRequestedPreview();
  };
  const failRequestedPreviewSwitch = () => {
    settleRequestedPreviewSwitch();
    if (clean(container.__hmbAutoplayVideoUid) === previewUid) {
      delete container.__hmbAutoplayVideoUid;
    }
    hmbShowPickerPreviewLoadFailure(container, tr.previewLoadFailed);
  };
  const stageRequestedPreviewSource = (restoreDesiredSource = false) => {
    const stagedVideo = container.querySelector("#picker-video");
    if (
      restoreDesiredSource
      && stagedVideo
      && selectedVideoUrl
      && clean(stagedVideo.getAttribute?.("src")) !== clean(selectedVideoUrl)
    ) {
      stagedVideo.__hmbPendingPickerVideoSource = selectedVideoUrl;
      delete stagedVideo.__hmbPendingPickerVideoOwner;
    }
    if (clean(stagedVideo?.__hmbPendingPickerVideoSource)) {
      markRequestedPreviewSwitchBusy();
    }
    const stagedViewportSource = hmbStagePickerViewportVideoSource(
      stagedVideo,
      activeCleanup,
      completeRequestedPreviewSwitch,
      failRequestedPreviewSwitch,
    );
    if (!stagedViewportSource) completeRequestedPreviewSwitch();
    return stagedViewportSource;
  };
  stageRequestedPreviewSource();
  const retryPreviewLoad = container.querySelector("#retry-picker-preview-load");
  const retryRequestedPreviewLoad = (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (!selectedVideoUrl || !previewUid) return;
    retryPreviewLoad.disabled = true;
    hmbClearPickerPreviewLoadFailure(container);
    container.__hmbAutoplayVideoUid = previewUid;
    container.__hmbForceVideoPreviewUid = previewUid;
    stageRequestedPreviewSource(true);
  };
  if (retryPreviewLoad) {
    retryPreviewLoad.addEventListener?.("click", retryRequestedPreviewLoad);
    activeCleanup.push(() => {
      retryPreviewLoad.removeEventListener?.("click", retryRequestedPreviewLoad);
    });
  }

  const activityLogView = container.querySelector("#activity-log-view");
  if (activityLogView && pickerRenderMode === "mount") {
    const scrollToLatest = () => { activityLogView.scrollTop = activityLogView.scrollHeight; };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(scrollToLatest);
    else scrollToLatest();
  }
  const elapsedElement = container.querySelector("#activity-elapsed");
  if (elapsedElement && runningOperation && Number(state.operation_started_at_ms || 0) > 0) {
    const startedAt = Number(state.operation_started_at_ms);
    const updateElapsed = () => {
      const seconds = Math.max(0, (Date.now() - startedAt) / 1000);
      const label = `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
      elapsedElement.textContent = `${tr.elapsed} ${label}`;
    };
    updateElapsed();
    const elapsedTimer = window.setInterval(updateElapsed, 1000);
    activeCleanup.push(() => window.clearInterval(elapsedTimer));
  }

  const applyImmediateCommandUi = (next) => {
    const readButton = container.querySelector("#read-scene");
    const stopButton = container.querySelector("#stop-read");
    const playblastButton = container.querySelector("#run-video");
    const snapshotButton = container.querySelector("#create-snapshot");
    const deleteSnapshotButton = container.querySelector("#delete-snapshot");
    const originalPreviewToggle = container.querySelector("#original-preview-toggle");
    const maskPlayblastToggle = container.querySelector("#mask-playblast-toggle");
    const depthPlayblastToggle = container.querySelector("#depth-playblast-toggle");
    const motionGuideToggle = container.querySelector("#motion-guide-toggle");
    const draftInput = container.querySelector("#maya-scene-path");
    const browseButton = container.querySelector("#browse-maya-scene");
    const resolutionSelect = container.querySelector("#playblast-resolution");
    const shotSelector = container.querySelector("#shot-selector");
    const submissionPending = !!container.__hmbPickerOperationSubmissionPending;
    const submissionAction = clean(container.__hmbPickerOperationAction);
    const draftPath = clean(draftInput?.value || next?.scene_draft_path || next?.scene_request_path || next?.scene_path);
    const availability = pickerButtonAvailability(
      next,
      draftPath,
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    hmbApplyPickerCommandAvailabilityToDom(container, availability);
    for (const [button, action] of [
      [playblastButton, "run_video"],
      [snapshotButton, "render_snapshot"],
      [deleteSnapshotButton, "delete_snapshot"],
    ]) {
      if (!button) continue;
      if (submissionPending && submissionAction === action) button.setAttribute("aria-busy", "true");
      else button.removeAttribute("aria-busy");
    }
    if (originalPreviewToggle) {
      originalPreviewToggle.checked = !!next?.original_enabled;
      originalPreviewToggle.disabled = submissionPending || availability.operationBusy;
    }
    if (maskPlayblastToggle) {
      maskPlayblastToggle.checked = next?.mask_enabled !== false;
      maskPlayblastToggle.disabled = submissionPending || availability.operationBusy;
    }
    if (depthPlayblastToggle) {
      depthPlayblastToggle.checked = !!next?.depth_enabled;
      depthPlayblastToggle.disabled = submissionPending || availability.operationBusy;
    }
    if (motionGuideToggle) {
      motionGuideToggle.checked = !!next?.motion_guide_enabled;
      motionGuideToggle.disabled = submissionPending || availability.operationBusy;
    }
    if (draftInput) draftInput.disabled = submissionPending || availability.operationBusy;
    if (browseButton) browseButton.disabled = submissionPending || availability.operationBusy;
    if (resolutionSelect) resolutionSelect.disabled = submissionPending || availability.operationBusy;
    if (shotSelector) shotSelector.disabled = submissionPending || availability.operationBusy;
    for (const control of container.querySelectorAll?.("[data-camera-path]") || []) {
      control.disabled = submissionPending || availability.operationBusy;
    }
    hmbApplyPickerPaletteSelectionToDom(
      container,
      next,
      submissionPending || availability.operationBusy,
    );
    hmbApplyPickerCommandGuardToDom(container, submissionPending, submissionAction);
    hmbSetPickerVisibilityBusy(
      container,
      availability.operationBusy || !!container.__hmbPickerOperationSubmissionPending,
    );
    hmbRenderPickerActivityLog(container.querySelector("#activity-log-view"), next, tr);
  };
  applyImmediateCommandUi(state);

  const reportTransportError = (error) => {
    const message = clean(error?.message || error) || "Widget state delivery failed.";
    hmbAppendImmediateActivityLogRow(container.querySelector("#activity-log-view"), "ERROR", message);
    try { console.error("[HMBVideoPickerLibrary]", message, error); } catch (_consoleError) {}
    return message;
  };

  const commit = (next, options = {}) => {
    if (container.__hmbVideoPickerDeleted === true) {
      return { state: normalize(next), delivered: false, deliveryPromise: null };
    }
    // Any newer synchronous action (delete, Shot switch, command setting, etc.)
    // is built from currentWidgetState(), which already includes this draft.
    // It therefore supersedes the queued publication and must cancel that job
    // before committing, otherwise the older timer could replay stale media.
    if (container.__hmbPickerPaintFirstState) {
      hmbCancelVideoPickerPaintFirstTask(container, "state-publication");
      delete container.__hmbPickerPaintFirstState;
      container.removeAttribute?.("data-hmb-picker-state-publication-pending");
    }
    const previousPendingState = (
      container.__hmbPendingPickerState
      && typeof container.__hmbPendingPickerState === "object"
    ) ? normalize(container.__hmbPendingPickerState) : null;
    const previousAuthoritativeState = (
      container.__hmbAuthoritativePickerState
      && typeof container.__hmbAuthoritativePickerState === "object"
    ) ? normalize(container.__hmbAuthoritativePickerState) : null;
    const previous = normalize(container.__hmbPendingPickerState || state);
    const normalized = normalize(hmbStateWithNotificationsLogged(next, previous));
    normalized.pending_action = "";
    normalized.pending_action_id = "";
    normalized.state_revision = Math.max(
      Number(state.state_revision || 0),
      Number(container.__hmbPendingPickerState?.state_revision || 0),
    ) + 1;
    normalized.frontend_seen_revision = Number(state.state_revision || 0);
    normalized.state_writer = "widget";
    normalized.state_published_at_ms = Date.now();
    if (!(container.__hmbPickerStatePublicationPredecessors instanceof Map)) {
      container.__hmbPickerStatePublicationPredecessors = new Map();
    }
    const normalizedIdentity = hmbPickerStatePublicationIdentity(normalized);
    container.__hmbLatestPickerStatePublicationIdentity = normalizedIdentity;
    delete container.__hmbVisiblePickerStatePublicationError;
    container.__hmbPickerStatePublicationPredecessors.set(
      normalizedIdentity,
      previousPendingState || previousAuthoritativeState || null,
    );
    if (container.__hmbPickerStatePublicationPredecessors.size > 32) {
      const oldestIdentity = container.__hmbPickerStatePublicationPredecessors.keys().next().value;
      container.__hmbPickerStatePublicationPredecessors.delete(oldestIdentity);
      container.__hmbFailedPickerStatePublications?.delete?.(oldestIdentity);
    }
    container.__hmbAuthoritativePickerState = normalize(normalized);
    container.__hmbPendingPickerState = normalize(normalized);
    applyImmediateCommandUi(normalized);
    hmbApplyPickerShotFeedbackNormalized(
      container,
      normalized,
      tr,
      pickerWorkspaceInteractionLocked(normalized),
    );
    const rollbackFailedCommit = () => {
      const rolledBack = hmbRollbackFailedPickerStatePublication(
        container,
        normalized,
        previousPendingState,
        previousAuthoritativeState,
      );
      if (rolledBack) {
        const rollbackState = previousPendingState || previousAuthoritativeState || state;
        const resolvedRollbackState = hmbPickerStateRollbackFallback(container, normalized);
        const visiblePublicationError = container.__hmbVisiblePickerStatePublicationError;
        applyImmediateCommandUi(resolvedRollbackState || rollbackState);
        if (resolvedRollbackState) {
          hmbApplyPickerShotFeedbackNormalized(
            container,
            resolvedRollbackState,
            tr,
            pickerLocalInteractionLocked(resolvedRollbackState),
          );
        } else {
          hmbApplyPickerShotFeedbackNormalized(
            container,
            rollbackState,
            tr,
            pickerLocalInteractionLocked(rollbackState),
          );
        }
        if (
          visiblePublicationError
          && visiblePublicationError.publication_identity
            === container.__hmbLatestPickerStatePublicationIdentity
        ) {
          hmbAppendImmediateActivityLogRow(
            container.querySelector("#activity-log-view"),
            "ERROR",
            visiblePublicationError.message,
          );
        }
      }
      return (
        rolledBack
        && container.__hmbLatestPickerStatePublicationIdentity === normalizedIdentity
        && container.__hmbLastPickerStateRollback?.visible_error_owned === true
      );
    };
    const reportFailedCommitError = (error) => {
      const message = reportTransportError(error);
      container.__hmbVisiblePickerStatePublicationError = {
        publication_identity: normalizedIdentity,
        message,
      };
    };
    let delivered = false;
    let deliveryPromise = null;
    try {
      if (!props || typeof props.onChange !== "function") {
        throw new Error("The Griptape state widget did not provide props.onChange.");
      }
      if (options && options.suppressMatchingEcho === true) {
        hmbRememberPendingPickerStateEcho(container, normalized, props);
      } else {
        // Structural/view changes rely on the normal morph to refresh dependent
        // controls. They must also invalidate any older disposable echo.
        hmbClearPendingPickerStateEcho(container);
      }
      if (
        Number(options?.workspacePublicationGeneration || 0) > 0
        && Number(options.workspacePublicationGeneration)
          === Number(container.__hmbPickerWorkspacePublicationGeneration || 0)
        && container.__hmbPickerWorkspacePublicationPending === true
      ) {
        container.__hmbPickerWorkspacePublicationEchoValue = hmbPickerStateEchoValue(normalized);
      }
      const publication = hmbDeliverPickerStateIfMounted(
        container,
        props.onChange,
        JSON.parse(JSON.stringify(normalized)),
      );
      if (!publication.delivered) return { state: normalized, delivered: false, deliveryPromise: null };
      const deliveryResult = publication.result;
      delivered = publication.delivered;
      if (deliveryResult && typeof deliveryResult.then === "function") {
        deliveryPromise = Promise.resolve(deliveryResult)
          .then(() => ({ ok: true, error: null }))
          .catch((error) => {
            // A late rejection must not report against a newer optimistic
            // publication. Only the exact failed state can own rollback and
            // therefore the visible transport error.
            if (rollbackFailedCommit()) reportFailedCommitError(error);
            return { ok: false, error };
          });
      }
    } catch (error) {
      if (rollbackFailedCommit()) reportFailedCommitError(error);
    }
    return { state: normalized, delivered, deliveryPromise };
  };
  const currentWidgetState = () => {
    const current = normalize(
      container.__hmbPickerPaintFirstState
      || container.__hmbPendingPickerState
      || state,
    );
    const draft = container.__hmbOutlinerSearchDraft;
    if (draft && Number(draft.expiresAtMs || 0) > Date.now()) {
      current.outliner_search = clean(draft.value);
    }
    return current;
  };
  const pickerLocalInteractionLocked = (candidateState = null) => {
    const latest = candidateState && typeof candidateState === "object"
      ? candidateState
      : currentWidgetState();
    const latestAvailability = pickerButtonAvailability(
      latest,
      clean(latest.scene_request_path || latest.scene_path),
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    return (
      !!container.__hmbPickerOperationSubmissionPending
      || latestAvailability.operationBusy
    );
  };
  const togglePickerView = () => {
    if (
      disposed
      || hmbVideoPickerPaintFirstTaskPending(container, "view-transition")
    ) return false;
    const currentlyExpanded = container.__hmbVideoPickerExpanded === true;
    const targetExpanded = !currentlyExpanded;
    const header = container.querySelector?.(".top[data-picker-toggle-surface='header']") || null;
    const root = container.querySelector?.(".hmbvp") || null;
    container.setAttribute?.("data-hmb-video-picker-view-transition-pending", "true");
    header?.setAttribute?.("data-picker-view-transition-pending", "true");
    root?.setAttribute?.("aria-busy", "true");
    root?.setAttribute?.("data-picker-view-transition-target", targetExpanded ? "expanded" : "compact");
    const clearPickerViewTransitionFeedback = () => {
      container.removeAttribute?.("data-hmb-video-picker-view-transition-pending");
      const liveHeader = container.querySelector?.(".top[data-picker-toggle-surface='header']") || header;
      const liveRoot = container.querySelector?.(".hmbvp") || root;
      liveHeader?.removeAttribute?.("data-picker-view-transition-pending");
      liveRoot?.removeAttribute?.("aria-busy");
      liveRoot?.removeAttribute?.("data-picker-view-transition-target");
    };
    hmbScheduleVideoPickerPaintFirstTask(container, "view-transition", () => {
      if (disposed || container.__hmbVideoPickerDeleted === true) {
        clearPickerViewTransitionFeedback();
        return;
      }
      const liveProps = {
        ...((props && typeof props === "object") ? props : {}),
        value: currentWidgetState(),
      };
      container.__hmbVideoPickerViewTransition = true;
      try {
        if (!targetExpanded) {
          container.__hmbVideoPickerExpandedViewState = hmbCapturePickerViewState(container);
          for (const videoElement of container.querySelectorAll?.("video") || []) videoElement.pause?.();
          // Keep the authored root/header mounted. Cleanup releases listeners;
          // the next factory call morphs only the mode-specific descendants.
          hmbRememberVideoPickerViewMode(container, false);
          cleanup();
          HMBVideoPickerLibraryWidget(container, liveProps);
          return;
        }

        const expandedViewState = container.__hmbVideoPickerExpandedViewState || null;
        hmbRememberVideoPickerViewMode(container, true);
        cleanup();
        HMBVideoPickerLibraryWidget(container, liveProps);
        hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
        hmbRestorePickerViewState(container, expandedViewState);
      } finally {
        delete container.__hmbVideoPickerViewTransition;
        clearPickerViewTransitionFeedback();
      }
    });
    return true;
  };
  const commandBridge = () => {
    const registry = typeof globalThis !== "undefined"
      ? globalThis.__hmbVideoPickerCommandBridgeRegistryV1
      : null;
    const runtimeInstanceId = clean(currentWidgetState().runtime_instance_id);
    return registry instanceof Map && runtimeInstanceId
      ? registry.get(runtimeInstanceId) || null
      : null;
  };
  const releaseVisibilityOperationGuard = (actionId) => {
    const ownedActionId = clean(actionId);
    if (!ownedActionId || clean(container.__hmbPickerOperationActionId) !== ownedActionId) return false;
    hmbClearPickerCommandSubmission(container, ownedActionId);
    if (container.__hmbPickerOperationGuardTimer) {
      try { clearTimeout(container.__hmbPickerOperationGuardTimer); } catch (_error) {}
      delete container.__hmbPickerOperationGuardTimer;
    }
    const latest = currentWidgetState();
    const latestAvailability = pickerButtonAvailability(
      latest,
      clean(latest.scene_request_path || latest.scene_path),
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    applyImmediateCommandUi(latest);
    hmbSetPickerVisibilityBusy(container, latestAvailability.operationBusy);
    return true;
  };
  const reserveVisibilityOperationGuard = (actionId, action = "") => {
    const ownedActionId = clean(actionId);
    if (!ownedActionId) return false;
    if (!hmbClaimPickerCommandSubmission(container, action, ownedActionId)) return false;
    if (container.__hmbPickerOperationGuardTimer) {
      try { clearTimeout(container.__hmbPickerOperationGuardTimer); } catch (_error) {}
    }
    applyImmediateCommandUi(currentWidgetState());
    hmbSetPickerVisibilityBusy(container, true);
    container.__hmbPickerOperationGuardTimer = setTimeout(() => {
      if (!releaseVisibilityOperationGuard(ownedActionId)) return;
      appendImmediateLogLine(
        "ERROR",
        `${clean(action) || "Picker command"} timed out before Python acknowledgement (${HMB_PICKER_COMMAND_ACK_TIMEOUT_MS / 1000} seconds). Controls were restored for retry.`,
      );
    }, HMB_PICKER_COMMAND_ACK_TIMEOUT_MS);
    return true;
  };
  const dispatchCommand = (action, payload = {}, actionId = "", options = {}) => {
    if (container.__hmbVideoPickerDeleted === true) {
      return { command: null, delivered: false, deliveryPromise: null };
    }
    const liveState = currentWidgetState();
    const resolvedActionId = clean(actionId)
      || `${clean(action) || "command"}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const commandPayload = hmbPickerCommandPayload(liveState, payload);
    const command = {
      schema: "hmb-picker-command",
      version: 1,
      runtime_instance_id: clean(liveState.runtime_instance_id),
      action: clean(action),
      action_id: resolvedActionId,
      issued_at_ms: Date.now(),
      payload: commandPayload,
    };
    const reserveVisibility = options?.reserveVisibility === true;
    // Reserve before bridge.dispatch(): a local bridge may synchronously ack
    // and remount this widget before dispatch returns. Installing the guard
    // afterwards would miss that ack and leave visibility locked for 20s.
    if (reserveVisibility && !reserveVisibilityOperationGuard(resolvedActionId, action)) {
      return { command: null, delivered: false, deliveryPromise: null, duplicate: true };
    }
    let delivered = false;
    let deliveryPromise = null;
    try {
      const bridge = commandBridge();
      if (!bridge || typeof bridge.dispatch !== "function") {
        throw new Error("The independent HMB_PICKER_COMMAND bridge is not mounted.");
      }
      const deliveryResult = bridge.dispatch(command);
      delivered = true;
      if (deliveryResult && typeof deliveryResult.then === "function") {
        deliveryPromise = Promise.resolve(deliveryResult)
          .then(() => ({ ok: true, error: null }))
          .catch((error) => {
            if (reserveVisibility) releaseVisibilityOperationGuard(resolvedActionId) && reportTransportError(error);
            else reportTransportError(error);
            return { ok: false, error };
          });
      }
    } catch (error) {
      if (reserveVisibility) releaseVisibilityOperationGuard(resolvedActionId) && reportTransportError(error);
      else reportTransportError(error);
    }
    return { command, delivered, deliveryPromise };
  };
  const scheduleReadAckTimeout = (actionId) => {
    if (container.__hmbReadAckTimer) {
      try { clearTimeout(container.__hmbReadAckTimer); } catch (_error) {}
    }
    container.__hmbReadAckTimer = setTimeout(() => {
      delete container.__hmbReadAckTimer;
      const latest = currentWidgetState();
      if (clean(latest.backend_ack_action_id) === actionId) return;
      if (clean(container.__hmbReadActionId) !== actionId) return;
      container.__hmbReadCommandPending = false;
      container.__hmbReadActionId = "";
      const failed = normalize({
        ...latest,
        message: "Python did not acknowledge READ within 20 seconds. Retry after reloading the library.",
      });
      reportTransportError("READ transport timed out before Python acknowledgement (20 seconds).");
      applyImmediateCommandUi(failed);
    }, 20000);
  };
  const scheduleOriginalAckTimeout = (actionId, previousEnabled) => {
    if (container.__hmbOriginalAckTimer) {
      try { clearTimeout(container.__hmbOriginalAckTimer); } catch (_error) {}
    }
    container.__hmbOriginalAckTimer = setTimeout(() => {
      delete container.__hmbOriginalAckTimer;
      const latest = currentWidgetState();
      if (clean(latest.backend_ack_action_id) === actionId) return;
      if (clean(container.__hmbOriginalActionId) !== actionId) return;
      container.__hmbOriginalCommandPending = false;
      container.__hmbOriginalActionId = "";
      delete container.__hmbOriginalRequestedEnabled;
      const toggle = container.querySelector("#original-preview-toggle");
      if (toggle) {
        toggle.checked = !!previousEnabled;
        toggle.disabled = false;
      }
      const failed = normalize({
        ...latest,
        original_preview_enabled: !!previousEnabled,
        message: "Python did not acknowledge the Original Playblast request within 20 seconds.",
      });
      reportTransportError("Original Playblast transport timed out before Python acknowledgement (20 seconds).");
      applyImmediateCommandUi(failed);
    }, 20000);
  };

  const on = (element, eventName, handler, options = undefined) => {
    if (!element) return;
    element.addEventListener(eventName, handler, options);
    activeCleanup.push(() => element.removeEventListener(eventName, handler, options));
  };

  hmbInstallPickerInteractionIsolation(container, activeCleanup);
  hmbInstallVideoPickerInternalHeaderToggle(container, activeCleanup, togglePickerView);

  let mediaController = null;
  const pickerWorkspaceInteractionLocked = (candidateState = null) => (
    pickerLocalInteractionLocked(candidateState)
    || container.__hmbPickerWorkspacePublicationPending === true
  );
  const pickerStateWithLiveWorkspaceDraft = () => {
    const liveState = currentWidgetState();
    const sceneInput = container.querySelector?.("#maya-scene-path");
    const sceneDraftPath = sceneInput
      ? clean(sceneInput.value).replace(/^["']|["']$/g, "")
      : clean(liveState.scene_draft_path);
    const currentFrame = Number.isFinite(Number(container.__hmbViewportFrame))
      ? Number(container.__hmbViewportFrame)
      : Number(liveState.current_frame || 0);
    return normalize({ ...liveState, scene_draft_path: sceneDraftPath, current_frame: currentFrame });
  };
  const patchPickerWorkspaceExperience = (nextStateValue) => {
    const nextState = normalize(nextStateValue);
    hmbSyncVideoPickerHostMeasurement(container, nextState, pickerExpanded);
    const nextTr = TEXT[nextState.language] || TEXT.ko;
    const locked = pickerWorkspaceInteractionLocked(nextState);
    const immediateMediaLocked = pickerLocalInteractionLocked(nextState);
    container.__hmbViewportFrame = Number(nextState.current_frame || 0);
    hmbPatchVideoPickerShotWorkspace(
      container,
      nextState,
      nextTr,
      locked,
      pickerLocalInteractionLocked(nextState),
    );
    hmbApplyPickerShotFeedbackNormalized(container, nextState, nextTr, locked);
    hmbReconcileVideoPickerCards(container, nextState, nextTr, immediateMediaLocked);
    hmbPatchVideoPickerPreviewDom(container, nextState, nextTr);
    const sceneInput = container.querySelector?.("#maya-scene-path");
    if (sceneInput) sceneInput.value = clean(nextState.scene_draft_path);
    mediaController?.refresh?.(nextState);
    if (!pickerExpanded) {
      // Apply the state-derived height in the same transaction so a populated
      // row never spends a frame clipped to the former empty-row height (or
      // vice versa), then coalesce the host-internals notification next frame.
      hmbApplyVideoPickerCompactHostSizing(container, nextState);
      container.__hmbScheduleVideoPickerCompactHostSizing?.(nextState);
    } else {
      schedulePickerFit(false);
    }
    return nextState;
  };
  const publishPickerWorkspaceMutation = (nextStateValue) => {
    const optimisticState = normalize(nextStateValue);
    const generation = hmbBeginPickerWorkspacePublication(container, optimisticState, () => {
      patchPickerWorkspaceExperience(currentWidgetState());
    });
    const nextState = patchPickerWorkspaceExperience(optimisticState);
    const publication = commit(nextState, {
      suppressMatchingEcho: true,
      workspacePublicationGeneration: generation,
    });
    if (!publication?.delivered) {
      if (hmbReleasePickerWorkspacePublication(container, generation)) {
        patchPickerWorkspaceExperience(currentWidgetState());
      }
    } else if (publication.deliveryPromise?.then) {
      publication.deliveryPromise.then((result) => {
        if (result?.ok !== false) return;
        if (hmbReleasePickerWorkspacePublication(container, generation)) {
          patchPickerWorkspaceExperience(currentWidgetState());
        }
      });
    }
    return publication;
  };
  const schedulePickerStatePublicationAfterPaint = (
    nextState,
    options = {},
    deferredVisualUpdate = null,
  ) => {
    container.__hmbPickerPaintFirstState = nextState;
    container.setAttribute?.("data-hmb-picker-state-publication-pending", "true");
    return hmbScheduleVideoPickerPaintFirstTask(container, "state-publication", () => {
      const finalState = container.__hmbPickerPaintFirstState || nextState;
      delete container.__hmbPickerPaintFirstState;
      container.removeAttribute?.("data-hmb-picker-state-publication-pending");
      try {
        deferredVisualUpdate?.(finalState);
      } finally {
        if (options.workspacePublication === true) publishPickerWorkspaceMutation(finalState);
        else commit(finalState, options.commitOptions || { suppressMatchingEcho: true });
      }
    });
  };
  const finishPickerShotRename = (input, save) => {
    if (!input || input.__hmbPickerRenameSettled) return;
    input.__hmbPickerRenameSettled = true;
    const workspaceUuid = hmbUuid(input.getAttribute?.("data-picker-shot-rename-input"));
    const liveState = pickerStateWithLiveWorkspaceDraft();
    const shot = liveState.picker_shots.find((row) => row.workspace_uuid === workspaceUuid);
    const ownerDocument = input.ownerDocument || container.ownerDocument
      || (typeof document !== "undefined" ? document : null);
    if (!shot || !ownerDocument?.createElement) return;
    const requestedName = clean(input.value).slice(0, 128);
    const label = ownerDocument.createElement("b");
    label.className = "picker-shot-name-label";
    label.setAttribute("data-picker-shot-name", "");
    label.textContent = save && requestedName ? requestedName : shot.name;
    input.replaceWith?.(label);
    if (save && requestedName && requestedName !== shot.name && !pickerWorkspaceInteractionLocked(liveState)) {
      publishPickerWorkspaceMutation(hmbRenameLocalPickerShot(liveState, workspaceUuid, requestedName));
    } else {
      hmbPatchVideoPickerShotWorkspace(
        container,
        liveState,
        TEXT[liveState.language] || TEXT.ko,
        pickerWorkspaceInteractionLocked(liveState),
        pickerLocalInteractionLocked(liveState),
      );
    }
  };
  hmbInstallVideoPickerShotWorkspaceDelegation(container, {
    add: (event) => {
      event?.preventDefault?.(); event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerWorkspaceInteractionLocked(liveState) || liveState.picker_shots.length >= HMB_SHOT_ROUTING_MAX_SHOTS) return;
      hmbPauseVideoPickerMedia(container);
      publishPickerWorkspaceMutation(hmbAddLocalPickerShot(liveState));
    },
    load: (event, button) => {
      event?.preventDefault?.(); event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerLocalInteractionLocked(liveState)) return;
      const workspaceUuid = hmbUuid(button.getAttribute?.("data-picker-shot-load"));
      const targetShot = liveState.picker_shots.find((row) => row.workspace_uuid === workspaceUuid);
      if (!targetShot || hmbPickerWorkspaceAssetUids(targetShot).length >= HMB_PICKER_MAX_ASSETS_PER_SHOT) return;
      hmbPauseVideoPickerMedia(container);
      if (workspaceUuid !== liveState.active_picker_shot_uuid) {
        publishPickerWorkspaceMutation(hmbSwitchLocalPickerShot(liveState, workspaceUuid));
      }
      const result = dispatchCommand("browse_video_asset", {
        select_if_capacity: true,
        picker_shot_uuid: workspaceUuid,
      });
      if (!result.delivered && !result.duplicate) {
        hmbOpenVideoPickerFileInput(container, workspaceUuid);
      }
    },
    activate: (event, button) => {
      event?.preventDefault?.(); event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerLocalInteractionLocked(liveState)) return;
      const workspaceUuid = hmbUuid(
        button.getAttribute?.("data-picker-shot-activate")
        || button.getAttribute?.("data-picker-shot-row"),
      );
      if (!workspaceUuid || workspaceUuid === liveState.active_picker_shot_uuid) return;
      hmbPauseVideoPickerMedia(container);
      delete container.__hmbAutoplayVideoUid;
      delete container.__hmbForceVideoPreviewUid;
      publishPickerWorkspaceMutation(hmbSwitchLocalPickerShot(liveState, workspaceUuid));
    },
    rename: (event, button) => {
      event?.preventDefault?.(); event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerWorkspaceInteractionLocked(liveState)) return;
      const workspaceUuid = hmbUuid(button.getAttribute?.("data-picker-shot-rename"));
      const shot = liveState.picker_shots.find((row) => row.workspace_uuid === workspaceUuid);
      const row = button.closest?.("[data-picker-shot-row]")
        || button.closest?.("[data-picker-active-shot-controls]");
      const label = row?.querySelector?.("[data-picker-shot-name]");
      const ownerDocument = label?.ownerDocument || container.ownerDocument
        || (typeof document !== "undefined" ? document : null);
      if (!shot || !label || !ownerDocument?.createElement) return;
      const input = ownerDocument.createElement("input");
      input.type = "text";
      input.className = "picker-shot-name-input nodrag";
      input.maxLength = 128;
      input.value = shot.name;
      input.setAttribute("data-picker-shot-rename-input", workspaceUuid);
      input.setAttribute("aria-label", `Rename ${shot.name}`);
      label.replaceWith?.(input);
      button.disabled = true;
      try { input.focus?.({ preventScroll: true }); } catch (_error) { input.focus?.(); }
      input.select?.();
    },
    renameKeydown: (event, input) => {
      event?.stopPropagation?.();
      if (event?.isComposing || Number(event?.keyCode) === 229) return;
      if (event?.key === "Enter") { event.preventDefault?.(); finishPickerShotRename(input, true); }
      else if (event?.key === "Escape") { event.preventDefault?.(); finishPickerShotRename(input, false); }
    },
    renameBlur: (_event, input) => finishPickerShotRename(input, true),
    remove: (event, button) => {
      event?.preventDefault?.(); event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerWorkspaceInteractionLocked(liveState) || liveState.picker_shots.length <= 1) return;
      const workspaceUuid = hmbUuid(button.getAttribute?.("data-picker-shot-delete"));
      if (!workspaceUuid) return;
      hmbPauseVideoPickerMedia(container);
      publishPickerWorkspaceMutation(hmbDeleteLocalPickerShot(liveState, workspaceUuid));
    },
    bind: (event, selector) => {
      event?.stopPropagation?.();
      const liveState = pickerStateWithLiveWorkspaceDraft();
      if (pickerWorkspaceInteractionLocked(liveState)) {
        hmbPatchVideoPickerShotSelector(container, liveState, true);
        return;
      }
      const requested = hmbUuid(selector.value);
      const previousBinding = clean(hmbActivePickerWorkspace(liveState)?.bound_shot_uuid);
      const nextState = hmbBindActivePickerShot(liveState, requested);
      const acceptedBinding = clean(hmbActivePickerWorkspace(nextState)?.bound_shot_uuid);
      if (acceptedBinding !== requested) {
        hmbPatchVideoPickerShotSelector(container, liveState, false);
        const conflict = container.querySelector?.("#shot-selector-conflict");
        if (conflict) { conflict.hidden = false; conflict.textContent = "Already bound to another local Shot"; }
        return;
      }
      if (acceptedBinding !== previousBinding) publishPickerWorkspaceMutation(nextState);
      else hmbPatchVideoPickerShotSelector(container, liveState, false);
    },
  }, activeCleanup);

  const patchInitialPickerShotWorkspace = () => {
    const liveState = currentWidgetState();
    hmbPatchVideoPickerShotWorkspace(
      container,
      liveState,
      TEXT[liveState.language] || TEXT.ko,
      pickerWorkspaceInteractionLocked(liveState),
      pickerLocalInteractionLocked(liveState),
    );
  };
  if (typeof window !== "undefined") {
    // Discovery is a notification only. The corresponding process-global
    // catalog event is intentionally not observed by this widget.
    try {
      window.dispatchEvent(new CustomEvent(HMB_SHOT_DISCOVER_EVENT, {
        detail: { schema: "hmb-shot-routing-discover", version: 1, participant_kind: "video_picker" },
      }));
    } catch (_error) {}
  }
  patchInitialPickerShotWorkspace();

  recoverMissingMountedPicker = (nextProps = {}) => {
    if (
      container.__hmbVideoPickerDeleted === true
      || container.__hmbVideoPickerViewTransition === true
    ) return false;
    const mountedRoot = container.querySelector?.(".hmbvp") || null;
    const mountedBody = container.querySelector?.(".hmbvp-clip") || null;
    if (mountedRoot && mountedBody) return false;

    // Griptape 0.122 can retain the widget controller while replacing the
    // visible parameter-row children during a value/size reconciliation.  A
    // regional patch cannot repair a root that React has already removed, so
    // remount the same view from the newest authoritative props.  Expanded
    // recovery deliberately discards a stale transition cache; the fixed top
    // is adopted into the fresh full dashboard by the normal factory path.
    hmbRememberVideoPickerViewMode(container, pickerExpanded);
    delete container.__hmbVideoPickerRestoringExpandedDom;
    if (pickerExpanded) delete container.__hmbVideoPickerExpandedCache;
    container.__hmbVideoPickerRootRecoveryCount = Number(
      container.__hmbVideoPickerRootRecoveryCount || 0,
    ) + 1;
    HMBVideoPickerLibraryWidget(container, nextProps || {});
    return true;
  };

  const patchMountedPicker = (nextProps = {}) => {
    if (recoverMissingMountedPicker(nextProps || {})) return true;
    const nextState = normalize(nextProps?.value ?? nextProps?.parameterValue ?? nextProps?.defaultValue);
    const nextTr = TEXT[nextState.language] || TEXT.ko;
    props = nextProps || {};
    state = nextState;
    container.__hmbAuthoritativePickerState = normalize(nextState);
    if (
      nextState.state_writer === "python"
      && container.__hmbPickerWorkspacePublicationPending !== true
    ) delete container.__hmbPendingPickerState;
    // A host echo may arrive between local feedback and the second-frame
    // publication. Keep the visible draft authoritative for media/order only
    // during that bounded window so the card cannot flash back and reselect.
    const visibleState = container.__hmbPickerPaintFirstState
      ? normalize(container.__hmbPickerPaintFirstState)
      : nextState;
    const nextLocked = pickerWorkspaceInteractionLocked(nextState);
    const immediateMediaLocked = pickerLocalInteractionLocked(nextState);
    hmbPatchVideoPickerShotWorkspace(
      container,
      visibleState,
      nextTr,
      nextLocked,
      pickerLocalInteractionLocked(nextState),
    );
    hmbApplyPickerShotFeedbackNormalized(container, visibleState, nextTr, nextLocked);
    hmbReconcileVideoPickerCards(container, visibleState, nextTr, immediateMediaLocked);
    hmbPatchVideoPickerPreviewDom(container, visibleState, nextTr);
    applyImmediateCommandUi(nextState);
    const root = container.querySelector?.(".hmbvp");
    root?.setAttribute?.("data-state-revision", String(Number(nextState.state_revision || 0)));
    root?.setAttribute?.("data-picker-update-mode", "regional");
    const languageButton = container.querySelector?.("#language-toggle");
    if (languageButton) languageButton.textContent = nextTr.language;
    const pathInput = container.querySelector?.("#maya-scene-path");
    if (pathInput && pathInput.ownerDocument?.activeElement !== pathInput) {
      pathInput.value = hmbResolveMayaSceneDraftPath(container, nextState);
    }
    const resolution = container.querySelector?.("#playblast-resolution");
    if (resolution) resolution.value = `${Number(nextState.output_width)}x${Number(nextState.output_height)}`;
    const nextVideo = previewVideo(visibleState);
    const nextSelected = hmbSelectedVideoAssets(visibleState);
    const nextPreviewUid = clean(nextVideo?.video_uid || visibleState.preview_video_uid || visibleState.selected_video_uid);
    const nextOrder = nextSelected.findIndex((item) => clean(item.video_uid) === nextPreviewUid) + 1;
    const nextSlot = nextOrder > 0 ? nextOrder : clamp(visibleState.selected_video_slot || 1, 1, Math.max(1, nextSelected.length));
    const nextMetadata = selectedFrameMetadata(visibleState, nextVideo, nextSlot);
    const nextStart = Number.isFinite(Number(nextMetadata.start_frame)) ? Math.round(Number(nextMetadata.start_frame)) : 0;
    const nextEnd = Number.isFinite(Number(nextMetadata.end_frame)) ? Math.round(Number(nextMetadata.end_frame)) : nextStart;
    const nextFrame = Math.round(clamp(Number(container.__hmbViewportFrame ?? visibleState.current_frame ?? nextStart), nextStart, nextEnd));
    const nextFps = Math.max(0.000001, Number(nextMetadata.fps || visibleState.source_fps || 24));
    const seek = container.querySelector?.("#video-seek");
    const frameInput = container.querySelector?.("#video-frame-number");
    for (const control of [seek, frameInput]) {
      if (!control) continue;
      control.min = String(nextStart);
      control.max = String(nextEnd);
      if (control.ownerDocument?.activeElement !== control) control.value = String(nextFrame);
    }
    const frameInfo = container.querySelector?.("#frame-info-frame");
    const timeInfo = container.querySelector?.("#frame-info-time");
    if (frameInfo) frameInfo.textContent = `${nextFrame} / ${nextEnd}`;
    if (timeInfo) timeInfo.textContent = formatFrameTimecode(nextFrame, nextStart, nextFps);
    mediaController?.refresh(visibleState);
    if (pickerExpanded) {
      const outlinerKey = JSON.stringify([
        nextState.outliner_nodes,
        nextState.outliner_expanded,
        nextState.outliner_search,
        nextState.selected_outliner_path,
        nextState.slot_visibility,
        nextState.slot_assignments,
        nextState.marker_catalog_version,
        nextLocked,
        nextState.language,
      ]);
      if (container.__hmbPickerOutlinerPatchKey !== outlinerKey) {
        hmbRenderPickerOutlinerLocal(container, nextState, nextTr, nextLocked);
        container.__hmbPickerOutlinerPatchKey = outlinerKey;
      }
      hmbApplyPickerCameraSelectionToDom(container, nextState);
      hmbApplyPickerPaletteSelectionToDom(container, nextState, nextLocked);
    } else {
      hmbApplyVideoPickerCompactHostSizing(container, visibleState);
      container.__hmbScheduleVideoPickerCompactHostSizing?.(visibleState);
    }
    if (pickerExpanded) schedulePickerFit(false);
    container.__hmbPickerRegionalUpdateCount = Number(container.__hmbPickerRegionalUpdateCount || 0) + 1;
    return true;
  };

  if (!pickerExpanded) {
    const playCompactVideo = (event, button) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      const uid = clean(button?.getAttribute?.("data-play-video-uid"));
      if (!uid) return;
      const card = button.closest?.("[data-video-uid]") || null;
      const ownerWorkspaceUuid = hmbUuid(
        card?.getAttribute?.("data-picker-shot-video-owner")
        || card?.closest?.("[data-picker-shot-row]")?.getAttribute?.("data-picker-shot-row"),
      );
      let liveState = pickerStateWithLiveWorkspaceDraft();
      const switchingWorkspace = !!ownerWorkspaceUuid
        && ownerWorkspaceUuid !== liveState.active_picker_shot_uuid;
      if (switchingWorkspace) {
        hmbPauseVideoPickerMedia(container);
        liveState = hmbSwitchLocalPickerShot(liveState, ownerWorkspaceUuid);
      }
      const player = hmbVideoPickerCompactSharedPlayer(container, liveState, uid, card);
      if (!player) return;
      const requested = hmbVideoPickerRequestedPlaybackUid(container) === uid;
      if (
        clean(player.getAttribute?.("data-video-uid")) === uid
        && (requested || (!player.paused && !player.ended))
      ) {
        hmbSetVideoPickerPlaybackRequest(container);
        player.pause?.();
        hmbSyncVideoPickerPlayButtonState(container, "", false, tr);
        return;
      }
      const livePreviewUid = clean(liveState.preview_video_uid || liveState.selected_video_uid);
      hmbSyncVideoPickerPlayButtonState(container, uid, true, tr);
      container.__hmbAutoplayVideoUid = uid;
      container.__hmbForceVideoPreviewUid = uid;
      const nextState = livePreviewUid === uid
        ? { ...liveState, viewport_mode: "video" }
        : { ...hmbPreviewVideoAsset(liveState, uid), viewport_mode: "video" };
      hmbSetVideoPickerPlaybackRequest(container, uid, true);
      const playResult = player.play?.();
      if (playResult && typeof playResult.catch === "function") {
        playResult.catch((error) => {
          hmbSetVideoPickerPlaybackRequest(container);
          hmbSyncVideoPickerPlayButtonState(container, "", false, tr);
          reportPlaybackFailure(error, "Video-card playback");
        });
      }
      delete container.__hmbAutoplayVideoUid;
      if (switchingWorkspace) {
        publishPickerWorkspaceMutation(nextState);
      } else if (livePreviewUid !== uid || clean(liveState.viewport_mode).toLowerCase() !== "video") {
        commit(nextState, { suppressMatchingEcho: true });
      }
    };
    const selectCompactVideo = (event, selectionSurface) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      if (
        pickerLocalInteractionLocked()
        || selectionSurface?.getAttribute?.("aria-disabled") === "true"
        || container.__hmbSuppressVideoSelectionClick
      ) return;
      const uid = clean(selectionSurface?.getAttribute?.("data-toggle-video-uid"));
      if (!uid) return;
      const card = selectionSurface.closest?.("[data-video-uid]") || null;
      const ownerWorkspaceUuid = hmbUuid(
        card?.getAttribute?.("data-picker-shot-video-owner")
        || card?.closest?.("[data-picker-shot-row]")?.getAttribute?.("data-picker-shot-row"),
      );
      let liveState = currentWidgetState();
      const switchingWorkspace = !!ownerWorkspaceUuid
        && ownerWorkspaceUuid !== liveState.active_picker_shot_uuid;
      if (switchingWorkspace) {
        hmbPauseVideoPickerMedia(container);
        liveState = hmbSwitchLocalPickerShot(liveState, ownerWorkspaceUuid);
      }
      const wasSelected = hmbSelectedVideoAssets(liveState).some((item) => clean(item.video_uid) === uid);
      const nextState = hmbToggleVideoAssetSelection(liveState, uid);
      const nextSelected = hmbSelectedVideoAssets(nextState);
      const isSelected = nextSelected.some((item) => clean(item.video_uid) === uid);
      hmbApplySelectedVideoAssetOrderToDom(container, nextState, tr, pickerLocalInteractionLocked(nextState));
      const loggedState = appendActivityLog(
        nextState,
        wasSelected && !isSelected ? "INFO" : "SUCCESS",
        isSelected
          ? `Video selected as @video${nextSelected.findIndex((item) => clean(item.video_uid) === uid) + 1}.`
          : "Video removed from the active @video order; its history asset remains available.",
      );
      schedulePickerStatePublicationAfterPaint(
        loggedState,
        {
          workspacePublication: switchingWorkspace,
          commitOptions: { suppressMatchingEcho: true },
        },
        (paintedState) => hmbPatchVideoPickerPreviewDom(container, paintedState, tr),
      );
    };
    const deleteCompactVideo = (event, button) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      if (pickerLocalInteractionLocked()) return;
      const uid = clean(button?.getAttribute?.("data-delete-video-uid"));
      if (!uid) return;
      const liveState = currentWidgetState();
      const target = (Array.isArray(liveState.videos) ? liveState.videos : [])
        .find((item, index) => hmbVideoAssetUid(item, index) === uid);
      const sharedPlayer = container.__hmbCompactSharedVideoPlayer || null;
      if (clean(sharedPlayer?.getAttribute?.("data-video-uid")) === uid) {
        hmbReleaseVideoPickerCompactSharedPlayer(container);
      }
      const nextState = appendActivityLog(
        hmbDeleteVideoAsset(liveState, uid),
        "SUCCESS",
        `${hmbVideoAssetTitle(target || {}, 0)} removed from history. The media file was not deleted.`,
      );
      patchPickerWorkspaceExperience(nextState);
      commit(nextState, { suppressMatchingEcho: true });
      dispatchCommand("delete_video_asset", { video_uid: uid });
    };
    hmbInstallVideoAssetRootDelegation(
      container,
      { play: playCompactVideo, select: selectCompactVideo, remove: deleteCompactVideo },
      activeCleanup,
    );
    activeCleanup.push(() => hmbReleaseVideoPickerCompactSharedPlayer(container));
    const syncCompactPlaybackState = (event) => {
      const media = event?.target;
      if (!media?.classList?.contains?.("video-asset-thumb-media")) return;
      const uid = clean(media.getAttribute?.("data-video-uid"));
      const playing = event.type === "play" && !media.paused && !media.ended;
      hmbSetVideoPickerPlaybackRequest(container, uid, playing);
      hmbSyncVideoPickerPlayButtonState(container, uid, playing, tr);
    };
    on(container, "play", syncCompactPlaybackState, true);
    on(container, "pause", syncCompactPlaybackState, true);
    on(container, "ended", syncCompactPlaybackState, true);
    activeCleanup.push(hmbInstallVideoAssetDragReorder(container, {
      locked: () => pickerLocalInteractionLocked(),
      currentState: currentWidgetState,
      commitState: (nextState, details) => {
        const loggedState = appendActivityLog(
          nextState,
          "SUCCESS",
          `Video order changed by drag-and-drop; ${details.sourceUid} is now @video${details.targetIndex + 1}.`,
        );
        schedulePickerStatePublicationAfterPaint(loggedState);
      },
    }));
    on(container.querySelector("#import-video-asset"), "change", (event) => {
      const files = Array.from(event.target?.files || []);
      const sources = files.map((file) => ({
        source_path: clean(file.path || file.webkitRelativePath),
        label: clean(file.name),
      })).filter((item) => item.source_path);
      const pickerShotUuid = hmbConsumeVideoPickerFileInputTarget(
        container,
        currentWidgetState().active_picker_shot_uuid,
      );
      if (sources.length) {
        dispatchCommand("import_video_assets", {
          sources,
          select_if_capacity: true,
          picker_shot_uuid: pickerShotUuid,
        });
      }
      event.target.value = "";
    });
    on(container.querySelector("#language-toggle"), "click", (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      const liveState = currentWidgetState();
      const nextLanguage = liveState.language === "ko" ? "en" : "ko";
      const nextState = normalize({ ...liveState, language: nextLanguage });
      const languageButton = container.querySelector("#language-toggle");
      if (languageButton) languageButton.textContent = (TEXT[nextLanguage] || TEXT.ko).language;
      dispatchCommand("set_language", { language: nextLanguage });
      commit(nextState, { suppressMatchingEcho: true });
    });
    on(container.querySelector("#stop-read"), "click", (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      const liveState = currentWidgetState();
      const processPid = Math.max(0, Number(liveState.active_process_pid || 0));
      const action = processPid > 0 ? "stop_read" : "cancel_pending";
      dispatchCommand(action, {
        target_action_id: clean(liveState.backend_ack_action_id),
        active_process_pid: processPid,
      });
    });
    container.__hmbVideoPickerControllerUpdate = (nextProps) => {
      const workspaceEchoMatches = hmbPickerWorkspacePublicationMatchesEcho(
        container,
        hmbPickerStateFromProps(nextProps || {}),
      );
      if (hmbConsumePendingPickerStateEcho(container, nextProps || {})) {
        if (workspaceEchoMatches) {
          hmbReleasePickerWorkspacePublication(
            container,
            Number(container.__hmbPickerWorkspacePublicationGeneration || 0),
          );
        }
        patchMountedPicker(nextProps || {});
        return;
      }
      hmbClearPendingPickerStateEcho(container);
      patchMountedPicker(nextProps || {});
    };
    return container.__hmbVideoPickerControllerProxy;
  }

  const frameNumberInput = container.querySelector("#video-frame-number");
  const videoSeekInput = container.querySelector("#video-seek");
  const playToggleButton = container.querySelector("#video-play-toggle");
  mediaController = hmbCreateVideoPickerMediaController(container, {
    currentState: currentWidgetState,
    text: (liveState) => TEXT[liveState.language] || TEXT.ko,
    onPlaybackError: (error, context) => reportPlaybackFailure(error, context),
  });
  activeCleanup.push(() => mediaController?.cleanup());
  const showAdjacentSnapshot = (direction) => {
    const liveState = currentWidgetState();
    const frameContext = mediaController.context();
    const liveTr = TEXT[liveState.language] || TEXT.ko;
    const liveHistory = hmbSnapshotHistory(liveState);
    if (!liveHistory.length) return;
    const activeUid = clean(liveState.active_snapshot_uid);
    const activeIndex = liveHistory.findIndex(
      (item) => clean(item.snapshot_uid) === activeUid,
    );
    const step = Number(direction) < 0 ? -1 : 1;
    const targetIndex = activeIndex < 0
      ? (step < 0 ? liveHistory.length - 1 : 0)
      : (activeIndex + step + liveHistory.length) % liveHistory.length;
    const target = liveHistory[targetIndex];
    if (!target) return;
    mediaController.pause();
    delete container.__hmbAutoplayVideoUid;
    delete container.__hmbForceVideoPreviewUid;
    container.__hmbViewportFrame = Number(target.frame || frameContext.start);
    const next = {
      ...liveState,
      viewport_mode: "snapshot",
      active_snapshot_uid: clean(target.snapshot_uid),
      snapshot_active: true,
      snapshot_frame: Number(target.frame || 0),
      snapshot_video_slot: Number(target.render_video_slot || target.video_slot || 1),
      snapshot_data_uri: "",
      snapshot_path: clean(target.path),
      snapshot_url: clean(target.url),
      snapshot_sha256: clean(target.sha256),
    };
    const snapshotUpdated = hmbApplySnapshotNavigationFeedback(
      container,
      target,
      liveTr,
      frameContext.start,
      frameContext.fps,
    );
    commit(next, { suppressMatchingEcho: snapshotUpdated });
  };
  on(container.querySelector("#snapshot-prev"), "click", () => showAdjacentSnapshot(-1));
  on(container.querySelector("#snapshot-next"), "click", () => showAdjacentSnapshot(1));
  on(playToggleButton, "click", () => {
    const liveState = currentWidgetState();
    if (clean(liveState.viewport_mode).toLowerCase() !== "video") {
      const nextState = { ...liveState, viewport_mode: "video", snapshot_active: false };
      if (hmbVideoPickerPreviewDescriptor(nextState, container).kind !== "video") return;
      delete container.__hmbForceVideoPreviewUid;
      hmbPatchVideoPickerPreviewDom(container, nextState, TEXT[nextState.language] || TEXT.ko);
      mediaController.refresh(nextState);
      mediaController.togglePlayback();
      commit(nextState, { suppressMatchingEcho: true });
      return;
    }
    mediaController.togglePlayback();
  });
  on(videoSeekInput, "input", (event) => {
    mediaController.seek(event.target.value);
  });
  on(frameNumberInput, "change", (event) => {
    mediaController.pause();
    mediaController.seek(event.target.value);
  });

  const appendImmediateLogLine = (level, message) => {
    hmbAppendImmediateActivityLogRow(container.querySelector("#activity-log-view"), level, message);
  };

  const applyColor = (color) => {
    if (!color || pickerLocalInteractionLocked()) return;
    const liveState = currentWidgetState();
    const liveSelectedNode = liveState.outliner_nodes.find(
      (item) => clean(item.full_path) === clean(liveState.selected_outliner_path),
    ) || null;
    if (!liveSelectedNode) return;
    const liveSlot = 1;
    const current = selectedBindings(liveState, liveSlot);
    const selectedIdentity = hmbPickerBindingIdentity({
      maya_uuid: liveSelectedNode.maya_uuid,
      full_dag_path: liveSelectedNode.full_path,
    });
    const duplicateColor = current.find((item) => (
      clean(item.color) === color
      && hmbPickerBindingIdentity(item) !== selectedIdentity
    ));
    if (duplicateColor && !hmbPickerMarkerAllowsRepeat(color, liveState.marker_catalog)) {
      const duplicateState = {
        ...liveState,
        selected_color: color,
        message: `Color ${color} is already used by ${duplicateColor.group_name} in the current cut.`,
      };
      hmbApplyPickerPaletteSelectionToDom(
        container,
        duplicateState,
        pickerLocalInteractionLocked(duplicateState),
      );
      commit(duplicateState, { suppressMatchingEcho: true });
      return;
    }
    const existingIndex = current.findIndex((item) => (
      hmbPickerBindingIdentity(item) === selectedIdentity
    ));
    const nextBinding = {
      group_name: clean(liveSelectedNode.name),
      full_dag_path: clean(liveSelectedNode.full_path),
      maya_uuid: clean(liveSelectedNode.maya_uuid),
      reference_node: clean(liveSelectedNode.reference_node),
      reference_file: clean(liveSelectedNode.reference_file),
      proxy_manager: clean(liveSelectedNode.proxy_manager),
      proxy_tag: clean(liveSelectedNode.proxy_tag),
      color,
      enabled: true,
      video_slot: liveSlot,
      picker_order: existingIndex >= 0 ? current[existingIndex].picker_order : current.length + 1,
    };
    const withoutSelectedObject = current.filter((item) => (
      hmbPickerBindingIdentity(item) !== selectedIdentity
    ));
    if (existingIndex >= 0) {
      withoutSelectedObject.splice(
        Math.min(existingIndex, withoutSelectedObject.length),
        0,
        nextBinding,
      );
    } else {
      withoutSelectedObject.push(nextBinding);
    }
    const next = setSlotBindings(
      { ...liveState },
      liveSlot,
      withoutSelectedObject,
    );
    next.selected_color = color;
    next.status = "READY";
    next.message = `${clean(liveSelectedNode.name)} → ${color} ${existingIndex >= 0 ? "updated" : "added"} for the current cut.`;
    const interactionLocked = pickerLocalInteractionLocked(next);
    const outlinerUpdated = hmbRenderPickerOutlinerLocal(container, next, tr, interactionLocked);
    hmbApplyPickerPaletteSelectionToDom(container, next, interactionLocked);
    commit(next, { suppressMatchingEcho: outlinerUpdated });
  };

  const scenePathInput = container.querySelector("#maya-scene-path");
  const updateSceneDraftUi = () => {
    const draftPath = clean(scenePathInput?.value).replace(/^["']|["']$/g, "");
    container.__hmbMayaSceneDraftPath = draftPath;
    const availability = pickerButtonAvailability(
      currentWidgetState(),
      draftPath,
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    const readButton = container.querySelector("#read-scene");
    const stopButton = container.querySelector("#stop-read");
    const playblastButton = container.querySelector("#run-video");
    if (readButton) readButton.disabled = !availability.readEnabled;
    if (stopButton) stopButton.disabled = !availability.stopEnabled;
    if (playblastButton) playblastButton.disabled = !availability.playblastEnabled;
    return draftPath;
  };
  const publishSceneDraft = () => {
    const draftPath = updateSceneDraftUi();
    const liveState = currentWidgetState();
    if (mayaScenePathKey(draftPath) === mayaScenePathKey(liveState.scene_draft_path)) return;
    commit({ ...liveState, scene_draft_path: draftPath }, { suppressMatchingEcho: true });
  };
  on(scenePathInput, "input", updateSceneDraftUi);
  on(scenePathInput, "change", publishSceneDraft);
  on(scenePathInput, "blur", publishSceneDraft);
  const nativeRefreshTimers = new Set();
  const syncNativeMayaPath = ({ exactNativeTarget = false, explicitBrowseResult = false } = {}) => {
    const browseSessionActive = hmbNativeMayaBrowseSessionActive(container);
    if (!exactNativeTarget && !explicitBrowseResult && !browseSessionActive) return false;
    concealNativeMayaPicker(container);
    const nativePath = hmbNativeMayaScenePath(container);
    if (!nativePath) return false;
    if (
      browseSessionActive
      && !explicitBrowseResult
      && mayaScenePathKey(nativePath) === mayaScenePathKey(container.__hmbNativePickerPreviousPath)
    ) {
      return false;
    }
    if (scenePathInput) scenePathInput.value = nativePath;
    container.__hmbMayaSceneDraftPath = nativePath;
    publishSceneDraft();
    return true;
  };
  const scheduleNativeMayaPathSync = (event = null) => {
    if (event?.target && container.contains?.(event.target)) return;
    const exactNativeTarget = hmbIsExactNativeMayaPickerTarget(container, event?.target);
    if (!exactNativeTarget && !hmbNativeMayaBrowseSessionActive(container)) return;
    const browseSessionActive = hmbNativeMayaBrowseSessionActive(container);
    const browseActionId = clean(container.__hmbNativePickerBrowseActionId);
    const focusReturnedFromBrowse = event?.type === "focus" && browseSessionActive;
    for (const timer of nativeRefreshTimers) window.clearTimeout(timer);
    nativeRefreshTimers.clear();
    hmbInvalidateNativeMayaPickerCache(container);
    for (const delay of [0, 500]) {
      const timer = window.setTimeout(() => {
        nativeRefreshTimers.delete(timer);
        if (delay > 0) hmbInvalidateNativeMayaPickerCache(container);
        const changed = syncNativeMayaPath({ exactNativeTarget });
        if (changed && hmbNativeMayaBrowseSessionActive(container)) {
          const selectedPath = hmbNativeMayaScenePath(container);
          stopNativeSelectionPolling(true, browseActionId);
          for (const pendingTimer of nativeRefreshTimers) window.clearTimeout(pendingTimer);
          nativeRefreshTimers.clear();
          if (selectedPath) appendImmediateLogLine("SUCCESS", `Maya scene selected: ${selectedPath}`);
          return;
        }
        if (focusReturnedFromBrowse && delay > 0 && hmbNativeMayaBrowseSessionActive(container)) {
          stopNativeSelectionPolling(true, browseActionId);
          appendImmediateLogLine("INFO", "Maya scene browse closed without changing the current path.");
        }
      }, delay);
      nativeRefreshTimers.add(timer);
    }
  };
  let nativeSelectionPollTimer = null;
  const stopNativeSelectionPolling = (clearSession = false, actionId = "") => {
    const ownerActionId = clean(actionId);
    if (ownerActionId && !hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)) return false;
    if (nativeSelectionPollTimer != null) {
      window.clearTimeout(nativeSelectionPollTimer);
      nativeSelectionPollTimer = null;
    }
    if (clearSession) {
      hmbClearNativeMayaBrowseSession(container, ownerActionId);
    }
    return true;
  };
  const beginNativeSelectionPolling = (previousPath, actionId, preserveDeadline = false) => {
    stopNativeSelectionPolling(false);
    const ownerActionId = clean(actionId);
    const retainedDeadline = Number(container.__hmbNativePickerDeadlineMs || 0);
    const deadlineMs = preserveDeadline && retainedDeadline > 0
      ? retainedDeadline
      : Date.now()
        + HMB_PICKER_BROWSE_POLL_DELAYS_MS.reduce((total, delay) => total + delay, 0)
        + 1000;
    if (!hmbClaimNativeMayaBrowseSession(container, ownerActionId, previousPath, deadlineMs)) return false;
    let attempt = 0;
    const checkSelectionResult = () => {
      if (!hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)) return;
      if (Date.now() >= Number(container.__hmbNativePickerDeadlineMs || 0)) {
        stopNativeSelectionPolling(true, ownerActionId);
        return;
      }
      const selectedPath = hmbNativeMayaScenePath(container);
      const pathBeforeBrowse = hmbNormalizeMayaScenePath(container.__hmbNativePickerPreviousPath);
      if (!selectedPath || mayaScenePathKey(selectedPath) === mayaScenePathKey(pathBeforeBrowse)) return;
      syncNativeMayaPath({ explicitBrowseResult: true });
      stopNativeSelectionPolling(true, ownerActionId);
      appendImmediateLogLine("SUCCESS", `Maya scene selected: ${selectedPath}`);
    };
    const scheduleNextCheck = () => {
      if (!hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)) return;
      if (!hmbNativeMayaBrowseSessionActive(container)) return;
      if (attempt >= HMB_PICKER_BROWSE_POLL_DELAYS_MS.length) {
        stopNativeSelectionPolling(true, ownerActionId);
        return;
      }
      const delay = HMB_PICKER_BROWSE_POLL_DELAYS_MS[attempt];
      attempt += 1;
      nativeSelectionPollTimer = window.setTimeout(() => {
        nativeSelectionPollTimer = null;
        if (!hmbNativeMayaBrowseSessionOwnedBy(container, ownerActionId)) return;
        const selectedBefore = hmbNativeMayaScenePath(container);
        checkSelectionResult();
        if (!hmbNativeMayaBrowseSessionActive(container)) return;
        if (
          selectedBefore
          && mayaScenePathKey(selectedBefore)
            !== mayaScenePathKey(container.__hmbNativePickerPreviousPath)
        ) return;
        scheduleNextCheck();
      }, delay);
    };
    scheduleNextCheck();
    return true;
  };
  on(container.querySelector("#browse-maya-scene"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const actionId = `browse-maya-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    beginNativeSelectionPolling(hmbNativeMayaScenePath(container), actionId);
    const result = dispatchCommand("browse_maya_scene", {
      scene_path: clean(currentLocal.scene_draft_path || currentLocal.scene_request_path || currentLocal.scene_path),
    }, actionId);
    if (!result.delivered) {
      if (stopNativeSelectionPolling(true, actionId)) {
        appendImmediateLogLine("ERROR", "The native Maya scene browser command could not be delivered to HMB_PICKER_COMMAND.");
      }
    } else {
      appendImmediateLogLine("INFO", "Opening the native Maya .ma/.mb scene browser.");
      if (result.deliveryPromise) {
        result.deliveryPromise.then((outcome) => {
          if (outcome?.ok) return;
          if (stopNativeSelectionPolling(true, actionId)) {
            appendImmediateLogLine("ERROR", "The native Maya scene browser transport was rejected; background checks were stopped.");
          }
        });
      }
    }
  });
  const nodeRoot = videoPickerNodeRoot(container);
  on(nodeRoot, "change", scheduleNativeMayaPathSync);
  on(nodeRoot, "input", scheduleNativeMayaPathSync);
  if (typeof window !== "undefined") {
    on(window, "focus", scheduleNativeMayaPathSync);
  }
  activeCleanup.push(() => {
    stopNativeSelectionPolling(false);
    for (const timer of nativeRefreshTimers) window.clearTimeout(timer);
    nativeRefreshTimers.clear();
  });
  if (Number(container.__hmbNativePickerDeadlineMs || 0) > Date.now()) {
    beginNativeSelectionPolling(
      container.__hmbNativePickerPreviousPath,
      clean(container.__hmbNativePickerBrowseActionId) || `browse-resume-${Date.now()}`,
      true,
    );
  }

  on(container.querySelector("#language-toggle"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const nextLanguage = currentLocal.language === "ko" ? "en" : "ko";
    const result = dispatchCommand("set_language", { language: nextLanguage });
    if (!result.delivered) {
      appendImmediateLogLine("ERROR", "Language command could not be delivered to HMB_PICKER_COMMAND.");
    }
  });
  const submitSceneRead = (requestedPath, sourceLabel = "READ") => {
    const currentLocal = currentWidgetState();
    const liveScenePath = clean(
      requestedPath
      || container.__hmbMayaSceneDraftPath
      || currentLocal.scene_draft_path
      || currentLocal.scene_request_path
      || currentLocal.scene_path,
    ).replace(/^["']|["']$/g, "");
    const currentAvailability = pickerButtonAvailability(
      currentLocal,
      liveScenePath,
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    if (!isMayaScenePath(liveScenePath)) {
      appendImmediateLogLine("ERROR", `${sourceLabel} requires a Maya .mb or .ma absolute path.`);
      return false;
    }
    if (!currentAvailability.readEnabled) {
      appendImmediateLogLine(
        "WARNING",
        currentLocal.maya_available
          ? "READ is already pending, running, or complete for this scene."
          : "READ is disabled because no Maya mayabatch executable is available.",
      );
      return false;
    }
    const actionId = `read-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    container.__hmbReadCommandPending = true;
    container.__hmbReadActionId = actionId;
    const pendingDisplay = appendActivityLog({
      ...currentLocal,
      scene_draft_path: liveScenePath,
      scene_request_path: liveScenePath,
      message: "READ command is waiting for Python acknowledgement. Other controls remain available.",
    }, "INFO", `${sourceLabel}: ${liveScenePath}`);
    applyImmediateCommandUi(pendingDisplay);
    const result = dispatchCommand("read_scene", {
      scene_path: liveScenePath,
      output_width: Number(currentLocal.output_width || 1280),
      output_height: Number(currentLocal.output_height || 720),
    }, actionId);
    if (!result.delivered) {
      container.__hmbReadCommandPending = false;
      container.__hmbReadActionId = "";
      applyImmediateCommandUi({
        ...currentLocal,
        message: "READ was not submitted because HMB_PICKER_COMMAND is unavailable.",
      });
      return false;
    }
    appendImmediateLogLine("INFO", "READ request submitted through HMB_PICKER_COMMAND. Waiting for Python acknowledgement.");
    scheduleReadAckTimeout(actionId);
    if (result.deliveryPromise) {
      result.deliveryPromise.then((outcome) => {
        if (outcome?.ok) return;
        const latest = currentWidgetState();
        if (clean(latest.backend_ack_action_id) === actionId) return;
        if (clean(container.__hmbReadActionId) !== actionId) return;
        container.__hmbReadCommandPending = false;
        container.__hmbReadActionId = "";
        applyImmediateCommandUi({
          ...latest,
          message: "READ transport was rejected before Python could acknowledge it.",
        });
      });
    }
    return true;
  };
  on(container.querySelector("#read-scene"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    submitSceneRead("", "READ");
  });
  on(container.querySelector("#original-preview-toggle"), "change", (event) => {
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const originalEnabled = !!event?.target?.checked;
    const message = originalEnabled
      ? "Original selected. It will run only when Generate Playblast is pressed."
      : "Original deselected. The next Generate Playblast will omit it.";
    const next = appendActivityLog({
      ...currentLocal,
      original_enabled: originalEnabled,
      message,
    }, "INFO", message);
    commit(next, { suppressMatchingEcho: true });
  });
  on(container.querySelector("#mask-playblast-toggle"), "change", (event) => {
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const maskEnabled = !!event?.target?.checked;
    const message = maskEnabled
      ? "Mask selected. It will run only when Generate Playblast is pressed."
      : "Mask deselected. The next Generate Playblast will omit it.";
    const next = appendActivityLog({
      ...currentLocal,
      mask_enabled: maskEnabled,
      message,
    }, "INFO", message);
    commit(next, { suppressMatchingEcho: true });
  });
  on(container.querySelector("#depth-playblast-toggle"), "change", (event) => {
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const depthEnabled = !!event?.target?.checked;
    const message = depthEnabled
      ? "Depth selected. It will run only when Generate Playblast is pressed."
      : "Depth deselected. The next Generate Playblast will omit it.";
    const next = appendActivityLog({
      ...currentLocal,
      depth_enabled: depthEnabled,
      message,
    }, "INFO", message);
    commit(next, { suppressMatchingEcho: true });
  });
  on(container.querySelector("#motion-guide-toggle"), "change", (event) => {
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const motionGuideEnabled = !!event?.target?.checked;
    const message = motionGuideEnabled
      ? "Motion Guide selected. It will run only when Generate Playblast is pressed."
      : "Motion Guide deselected. The next Generate Playblast will omit it.";
    const next = appendActivityLog({
      ...currentLocal,
      motion_guide_enabled: motionGuideEnabled,
      message,
    }, "INFO", message);
    commit(next, { suppressMatchingEcho: true });
  });
  on(container.querySelector("#stop-read"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const localReadPending = !!container.__hmbReadCommandPending;
    const localOriginalPending = !!container.__hmbOriginalCommandPending;
    const localPending = localReadPending || localOriginalPending;
    const processPid = Math.max(0, Number(currentLocal.active_process_pid || 0));
    const activeNow = localPending
      || ["READING_SCENE", "RUNNING", "GENERATING_VIDEO", "GENERATING_ORIGINAL", "SNAPSHOT_RENDERING", "CANCELLING"].includes(clean(currentLocal.status).toUpperCase())
      || ["read_scene", "render_original_preview", "run_video", "render_snapshot"].includes(clean(currentLocal.operation_kind));
    if (!activeNow) {
      appendImmediateLogLine("INFO", "STOP ignored because no active or pending operation is visible.");
      return;
    }
    const actionId = `stop-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const action = processPid > 0 ? "stop_read" : "cancel_pending";
    const activeOperationKind = clean(currentLocal.operation_kind);
    const targetOriginal = (
      localOriginalPending
      || activeOperationKind === "render_original_preview"
      || clean(currentLocal.status).toUpperCase() === "GENERATING_ORIGINAL"
      || clean(currentLocal.scene_stage).toUpperCase() === "ORIGINAL_RENDERING"
    );
    const readActionId = clean(container.__hmbReadActionId);
    const originalActionId = clean(container.__hmbOriginalActionId);
    const targetActionId = clean(
      (targetOriginal ? originalActionId : readActionId)
      || (targetOriginal ? readActionId : originalActionId)
      || currentLocal.backend_ack_action_id,
    );
    const result = dispatchCommand(action, {
      target_action_id: targetActionId,
      active_process_pid: processPid,
    }, actionId);
    if (!result.delivered) {
      appendImmediateLogLine("ERROR", "STOP could not be delivered to HMB_PICKER_COMMAND.");
      return;
    }
    const clearStoppedLocalPending = () => {
      if (targetActionId && targetActionId === readActionId) {
        container.__hmbReadCommandPending = false;
        container.__hmbReadActionId = "";
        if (container.__hmbReadAckTimer) {
          try { clearTimeout(container.__hmbReadAckTimer); } catch (_error) {}
          delete container.__hmbReadAckTimer;
        }
      }
      if (targetActionId && targetActionId === originalActionId) {
        container.__hmbOriginalCommandPending = false;
        container.__hmbOriginalActionId = "";
        delete container.__hmbOriginalRequestedEnabled;
        if (container.__hmbOriginalAckTimer) {
          try { clearTimeout(container.__hmbOriginalAckTimer); } catch (_error) {}
          delete container.__hmbOriginalAckTimer;
        }
      }
    };
    if (result.deliveryPromise) {
      result.deliveryPromise.then((outcome) => {
        if (outcome?.ok) {
          clearStoppedLocalPending();
          return;
        }
        appendImmediateLogLine("ERROR", "STOP transport was rejected; the pending guard remains active.");
      });
    } else {
      clearStoppedLocalPending();
    }
    if (processPid > 0) {
      appendImmediateLogLine("WARNING", `STOP requested termination of PID ${processPid}.`);
      applyImmediateCommandUi({ ...currentLocal, message: `Stopping active process PID ${processPid}.` });
    } else {
      appendImmediateLogLine("WARNING", "Pending operation cancelled before an external process PID existed.");
      applyImmediateCommandUi({ ...currentLocal, message: "Pending operation cancelled before Maya or FFmpeg started." });
    }
  });
  on(container.querySelector("#create-snapshot"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const currentAvailability = pickerButtonAvailability(
      currentLocal,
      clean(currentLocal.scene_request_path || currentLocal.scene_path),
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    if (!currentAvailability.snapshotEnabled) {
      appendImmediateLogLine(
        "WARNING",
        "SNAPSHOT requires a completed READ, a paused viewport frame, a camera, and valid output timing.",
      );
      return;
    }
    viewportVideo?.pause?.();
    const liveSlot = 1;
    const frame = clamp(
      Number(frameNumberInput?.value || container.__hmbViewportFrame || currentLocal.current_frame),
      Number(currentLocal.start_frame || 0),
      Number(currentLocal.end_frame || currentLocal.start_frame || 0),
    );
    const result = dispatchCommand("render_snapshot", {
      scene_path: clean(currentLocal.scene_request_path || currentLocal.scene_path),
      selected_video_slot: liveSlot,
      video_uid: clean(currentLocal.preview_video_uid || currentLocal.selected_video_uid),
      snapshot_frame: frame,
      output_width: Number(currentLocal.output_width || 1280),
      output_height: Number(currentLocal.output_height || 720),
    }, "", { reserveVisibility: true });
    if (result.duplicate) return;
    if (!result.delivered) {
      appendImmediateLogLine("ERROR", "SNAPSHOT could not be delivered to HMB_PICKER_COMMAND.");
    } else {
      appendImmediateLogLine("INFO", `Current-cut snapshot requested at Maya frame ${frame}.`);
    }
  });
  on(container.querySelector("#delete-snapshot"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const activeSnapshot = hmbSnapshotHistory(currentLocal).find(
      (item) => clean(item.snapshot_uid) === clean(currentLocal.active_snapshot_uid),
    ) || null;
    if (!activeSnapshot) {
      appendImmediateLogLine("WARNING", "No active snapshot is available to delete.");
      return;
    }
    const liveSlot = Number(activeSnapshot.render_video_slot || activeSnapshot.video_slot || 1);
    const result = dispatchCommand("delete_snapshot", {
      scene_path: clean(currentLocal.scene_request_path || currentLocal.scene_path),
      selected_video_slot: liveSlot,
      snapshot_uid: clean(activeSnapshot.snapshot_uid),
    }, "", HMB_PICKER_GUARDED_COMMAND_OPTIONS);
    if (result.duplicate) return;
    if (!result.delivered) appendImmediateLogLine("ERROR", "Snapshot delete command could not be delivered.");
  });
  on(container.querySelector("#run-video"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const liveDraftPath = clean(
      container.__hmbMayaSceneDraftPath
      || container.querySelector("#maya-scene-path")?.value
      || currentLocal.scene_draft_path
      || currentLocal.scene_request_path
      || currentLocal.scene_path,
    );
    const currentAvailability = pickerButtonAvailability(
      currentLocal,
      liveDraftPath,
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    if (!currentAvailability.playblastEnabled) {
      appendImmediateLogLine(
        "WARNING",
        "PLAYBLAST requires a completed READ snapshot, a camera, and a valid output frame range.",
      );
      return;
    }
    const originalEnabled = !!currentLocal.original_enabled;
    const maskEnabled = !!currentLocal.mask_enabled;
    const depthEnabled = !!currentLocal.depth_enabled;
    const motionGuideEnabled = !!currentLocal.motion_guide_enabled;
    const selectedOutputs = [
      ["Original", originalEnabled],
      ["Mask", maskEnabled],
      ["Depth", depthEnabled],
      ["Motion Guide", motionGuideEnabled],
    ].filter(([, enabled]) => enabled).map(([label]) => label);
    if (!selectedOutputs.length) {
      appendImmediateLogLine(
        "WARNING",
        "Select at least one output: Original, Mask, Depth, or Motion Guide.",
      );
      return;
    }
    const liveSlot = 1;
    const result = dispatchCommand("run_video", {
      scene_path: clean(currentLocal.scene_request_path || currentLocal.scene_path),
      selected_video_slot: liveSlot,
      output_width: Number(currentLocal.output_width || 1280),
      output_height: Number(currentLocal.output_height || 720),
      include_original: originalEnabled,
      include_mask: maskEnabled,
      include_depth: depthEnabled,
      include_motion_guide: motionGuideEnabled,
      authoring_state: {
        state_revision: Number(currentLocal.state_revision || 0),
        selected_camera: clean(currentLocal.selected_camera || currentLocal.camera),
        slot_assignments: Array.isArray(currentLocal.slot_assignments)
          ? currentLocal.slot_assignments
          : [],
        slot_visibility: Array.isArray(currentLocal.slot_visibility)
          ? currentLocal.slot_visibility
          : [],
        original_enabled: originalEnabled,
        mask_enabled: maskEnabled,
        depth_enabled: depthEnabled,
        motion_guide_enabled: motionGuideEnabled,
        output_width: Number(currentLocal.output_width || 1280),
        output_height: Number(currentLocal.output_height || 720),
      },
    }, "", { reserveVisibility: true });
    if (result.duplicate) return;
    if (!result.delivered) {
      appendImmediateLogLine("ERROR", "PLAYBLAST could not be delivered to HMB_PICKER_COMMAND.");
    } else {
      appendImmediateLogLine(
        "INFO",
        `Generate requested for new history assets: ${selectedOutputs.join(", ")}. Existing assets will be preserved.`,
      );
    }
  });
  on(container.querySelector("#playblast-resolution"), "change", (event) => {
    const selected = HMB_PLAYBLAST_RESOLUTIONS.find(
      (item) => item.value === clean(event?.target?.value),
    ) || HMB_PLAYBLAST_RESOLUTIONS[0];
    const liveState = currentWidgetState();
    const next = appendActivityLog({
      ...liveState,
      output_width: selected.width,
      output_height: selected.height,
      message: `Playblast resolution set to ${selected.label}.`,
    }, "INFO", `Playblast resolution set to ${selected.label}.`);
    hmbApplyPickerResolutionToDom(container, selected.width, selected.height);
    commit(next);
  });
  on(container.querySelector("#clear-activity-log"), "click", () => {
    commit({
      ...currentWidgetState(),
      activity_log: [],
      activity_log_text: "",
      activity_log_text_user_edited: true,
      activity_log_cleared: true,
      message: "",
    });
  });
  const outlinerSearchInput = container.querySelector("#outliner-search");
  let outlinerSearchPublishTimer = null;
  let outlinerSearchRenderTimer = null;
  const renderOutlinerSearchDraft = (resetScroll = false) => {
    if (outlinerSearchRenderTimer) clearTimeout(outlinerSearchRenderTimer);
    outlinerSearchRenderTimer = null;
    const draft = container.__hmbOutlinerSearchDraft;
    if (!draft) return false;
    const scroll = container.querySelector(".outliner-scroll");
    if (resetScroll && scroll) scroll.scrollTop = 0;
    const localState = { ...currentWidgetState(), outliner_search: clean(draft.value) };
    return hmbRenderPickerOutlinerLocal(
      container,
      localState,
      tr,
      pickerLocalInteractionLocked(localState),
    );
  };
  const scheduleOutlinerSearchRender = () => {
    if (outlinerSearchRenderTimer) clearTimeout(outlinerSearchRenderTimer);
    outlinerSearchRenderTimer = setTimeout(
      () => renderOutlinerSearchDraft(true),
      HMB_PICKER_OUTLINER_SEARCH_RENDER_DELAY_MS,
    );
  };
  const publishOutlinerSearchDraft = () => {
    if (outlinerSearchPublishTimer) clearTimeout(outlinerSearchPublishTimer);
    outlinerSearchPublishTimer = null;
    const draft = container.__hmbOutlinerSearchDraft;
    if (!draft) return;
    renderOutlinerSearchDraft(true);
    const value = clean(draft.value);
    delete container.__hmbOutlinerSearchDraft;
    commit(
      { ...currentWidgetState(), outliner_search: value },
      { suppressMatchingEcho: true },
    );
  };
  const scheduleOutlinerSearchPublish = () => {
    if (outlinerSearchPublishTimer) clearTimeout(outlinerSearchPublishTimer);
    const dueAtMs = Number(container.__hmbOutlinerSearchDraft?.dueAtMs || Date.now());
    outlinerSearchPublishTimer = setTimeout(
      publishOutlinerSearchDraft,
      Math.max(0, dueAtMs - Date.now()),
    );
  };
  on(outlinerSearchInput, "input", (event) => {
    const value = clean(event?.target?.value);
    container.__hmbOutlinerSearchDraft = {
      value,
      dueAtMs: Date.now() + 180,
      expiresAtMs: Date.now() + 3000,
    };
    scheduleOutlinerSearchRender();
    scheduleOutlinerSearchPublish();
  });
  on(outlinerSearchInput, "change", publishOutlinerSearchDraft);
  on(outlinerSearchInput, "blur", publishOutlinerSearchDraft);
  on(outlinerSearchInput, "keydown", (event) => {
    if (event.key === "Enter") publishOutlinerSearchDraft();
  });
  if (container.__hmbOutlinerSearchDraft) scheduleOutlinerSearchPublish();
  activeCleanup.push(() => {
    if (outlinerSearchPublishTimer) clearTimeout(outlinerSearchPublishTimer);
    outlinerSearchPublishTimer = null;
    if (outlinerSearchRenderTimer) clearTimeout(outlinerSearchRenderTimer);
    outlinerSearchRenderTimer = null;
  });

  const outlinerScroll = container.querySelector(".outliner-scroll");
  let outlinerVirtualScrollFrame = 0;
  const renderVirtualOutlinerWindow = () => {
    outlinerVirtualScrollFrame = 0;
    if (!outlinerScroll) return;
    const liveState = currentWidgetState();
    const desired = hmbPickerOutlinerWindow(
      liveState,
      Number(outlinerScroll.scrollTop || 0),
      Number(outlinerScroll.clientHeight || 0),
    );
    const list = outlinerScroll.querySelector?.(".outliner-list");
    if (
      list
      && Number(list.getAttribute?.("data-outliner-start") || 0) === desired.start
      && Number(list.getAttribute?.("data-outliner-end") || 0) === desired.end
    ) return;
    hmbRenderPickerOutlinerLocal(
      container,
      liveState,
      tr,
      pickerLocalInteractionLocked(liveState),
    );
  };
  on(outlinerScroll, "scroll", () => {
    if (outlinerVirtualScrollFrame) return;
    const raf = typeof requestAnimationFrame === "function"
      ? requestAnimationFrame
      : (callback) => setTimeout(callback, 0);
    outlinerVirtualScrollFrame = raf(renderVirtualOutlinerWindow);
  }, { passive: true });
  activeCleanup.push(() => {
    if (!outlinerVirtualScrollFrame) return;
    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(outlinerVirtualScrollFrame);
    else clearTimeout(outlinerVirtualScrollFrame);
    outlinerVirtualScrollFrame = 0;
  });
  const selectOutlinerPath = (path) => {
    const liveState = currentWidgetState();
    const node = liveState.outliner_nodes.find((item) => clean(item.full_path) === clean(path));
    if (!node) return;
    const next = {
      ...liveState,
      selected_outliner_path: clean(path),
      selected_outliner_name: clean(node.name),
      selected_outliner_uuid: clean(node.maya_uuid),
    };
    const interactionLocked = pickerLocalInteractionLocked(next);
    const outlinerUpdated = hmbRenderPickerOutlinerLocal(container, next, tr, interactionLocked);
    hmbApplyPickerPaletteSelectionToDom(container, next, interactionLocked);
    commit(next, { suppressMatchingEcho: outlinerUpdated });
  };
  const toggleOutlinerPath = (path) => {
    const liveState = currentWidgetState();
    const expanded = new Set(liveState.outliner_expanded);
    if (expanded.has(path)) expanded.delete(path); else expanded.add(path);
    const next = { ...liveState, outliner_expanded: Array.from(expanded) };
    const outlinerUpdated = hmbRenderPickerOutlinerLocal(
      container,
      next,
      tr,
      pickerLocalInteractionLocked(next),
    );
    commit(next, { suppressMatchingEcho: outlinerUpdated });
  };
  const toggleOutlinerVisibility = (path) => {
    const liveState = currentWidgetState();
    const availability = pickerButtonAvailability(
      liveState,
      clean(liveState.scene_request_path || liveState.scene_path),
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    if (availability.operationBusy || container.__hmbPickerOperationSubmissionPending) {
      hmbSetPickerVisibilityBusy(container, true);
      appendImmediateLogLine("WARNING", "Visibility is locked until the active Maya operation finishes.");
      return;
    }
    const liveSlot = 1;
    const currentEntry = liveState.slot_visibility.find((item) => Number(item?.video_slot || 0) === liveSlot);
    const hiddenPaths = new Set(Array.isArray(currentEntry?.hidden_paths) ? currentEntry.hidden_paths.map(clean) : []);
    if (hiddenPaths.has(path)) hiddenPaths.delete(path); else hiddenPaths.add(path);
    const next = {
      ...liveState,
      slot_visibility: [
        { video_slot: 1, hidden_paths: Array.from(hiddenPaths) },
        ...liveState.slot_visibility.filter((item) => Number(item?.video_slot || 0) !== 1),
      ],
      message: `${path} visibility ${hiddenPaths.has(path) ? "OFF" : "ON"} for the current cut.`,
    };
    const outlinerUpdated = hmbRenderPickerOutlinerLocal(
      container,
      next,
      tr,
      pickerLocalInteractionLocked(next),
    );
    commit(next, { suppressMatchingEcho: outlinerUpdated });
  };
  on(outlinerScroll, "pointerdown", (event) => event.stopPropagation?.());
  on(outlinerScroll, "click", (event) => {
    event.stopPropagation?.();
    const visibility = event.target?.closest?.("[data-visibility-path]");
    if (visibility) {
      event.preventDefault?.();
      toggleOutlinerVisibility(clean(visibility.getAttribute?.("data-visibility-path")));
      return;
    }
    const toggle = event.target?.closest?.("[data-toggle-path]");
    if (toggle) {
      event.preventDefault?.();
      toggleOutlinerPath(clean(toggle.getAttribute?.("data-toggle-path")));
      return;
    }
    const row = event.target?.closest?.("[data-group-path]");
    if (row) selectOutlinerPath(clean(row.getAttribute?.("data-group-path")));
  });
  on(outlinerScroll, "keydown", (event) => {
    const row = event.target?.closest?.("[data-group-path]");
    if (!row || event.target !== row) return;
    if (["Enter", " "].includes(event.key)) {
      event.preventDefault();
      event.stopPropagation();
      selectOutlinerPath(clean(row.getAttribute?.("data-group-path")));
      return;
    }
    if (["ArrowUp", "ArrowDown"].includes(event.key)) {
      const liveState = currentWidgetState();
      const visibleNodes = filteredVisibleNodes(liveState);
      const path = clean(row.getAttribute?.("data-group-path"));
      const currentIndex = visibleNodes.findIndex((item) => clean(item?.full_path) === path);
      const nextIndex = Math.max(0, Math.min(
        visibleNodes.length - 1,
        currentIndex + (event.key === "ArrowUp" ? -1 : 1),
      ));
      const targetPath = clean(visibleNodes[nextIndex]?.full_path);
      if (!targetPath || targetPath === path) return;
      event.preventDefault();
      let target = Array.from(outlinerScroll.querySelectorAll?.("[data-group-path]") || [])
        .find((item) => clean(item.getAttribute?.("data-group-path")) === targetPath);
      if (!target) {
        const viewportRows = Math.max(1, Math.floor(
          Number(outlinerScroll.clientHeight || HMB_PICKER_OUTLINER_ROW_HEIGHT)
            / HMB_PICKER_OUTLINER_ROW_HEIGHT,
        ));
        outlinerScroll.scrollTop = Math.max(
          0,
          (nextIndex - Math.floor(viewportRows / 2)) * HMB_PICKER_OUTLINER_ROW_HEIGHT,
        );
        hmbRenderPickerOutlinerLocal(
          container,
          liveState,
          tr,
          pickerLocalInteractionLocked(liveState),
          { forcePath: targetPath, focusPath: targetPath },
        );
        target = Array.from(outlinerScroll.querySelectorAll?.("[data-group-path]") || [])
          .find((item) => clean(item.getAttribute?.("data-group-path")) === targetPath);
      }
      for (const item of outlinerScroll.querySelectorAll?.("[data-group-path]") || []) {
        item.setAttribute("tabindex", item === target ? "0" : "-1");
      }
      target?.focus?.({ preventScroll: true });
      return;
    }
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const path = clean(row.getAttribute?.("data-group-path"));
    const liveState = currentWidgetState();
    const node = liveState.outliner_nodes.find((item) => clean(item.full_path) === path);
    if (!node) return;
    const expanded = new Set(liveState.outliner_expanded);
    if (event.key === "ArrowRight" && Number(node.child_count || 0) > 0 && !expanded.has(path)) {
      event.preventDefault();
      toggleOutlinerPath(path);
    } else if (event.key === "ArrowLeft" && expanded.has(path)) {
      event.preventDefault();
      toggleOutlinerPath(path);
    } else if (event.key === "ArrowLeft" && clean(node.parent_path)) {
      event.preventDefault();
      const parentPath = clean(node.parent_path);
      let parentRow = Array.from(outlinerScroll.querySelectorAll?.("[data-group-path]") || [])
        .find((item) => clean(item.getAttribute?.("data-group-path")) === parentPath);
      if (!parentRow) {
        const visibleNodes = filteredVisibleNodes(liveState);
        const parentIndex = visibleNodes.findIndex((item) => clean(item?.full_path) === parentPath);
        if (parentIndex >= 0) {
          outlinerScroll.scrollTop = Math.max(0, parentIndex * HMB_PICKER_OUTLINER_ROW_HEIGHT);
          hmbRenderPickerOutlinerLocal(
            container,
            liveState,
            tr,
            pickerLocalInteractionLocked(liveState),
            { forcePath: parentPath, focusPath: parentPath },
          );
          parentRow = Array.from(outlinerScroll.querySelectorAll?.("[data-group-path]") || [])
            .find((item) => clean(item.getAttribute?.("data-group-path")) === parentPath);
        }
      }
      parentRow?.focus?.({ preventScroll: true });
    }
  });
  container.querySelectorAll("[data-camera-path]").forEach((button) => {
    on(button, "click", () => {
      const next = { ...currentWidgetState(), selected_camera: clean(button.getAttribute("data-camera-path")) };
      hmbApplyPickerCameraSelectionToDom(container, next);
      commit(next);
    });
  });
  container.querySelectorAll("[data-color]").forEach((button) => {
    on(button, "click", () => {
      const color = clean(button.getAttribute("data-color"));
      const liveState = currentWidgetState();
      const liveSelectedNode = liveState.outliner_nodes.find(
        (item) => clean(item.full_path) === clean(liveState.selected_outliner_path),
      );
      if (liveSelectedNode) applyColor(color);
      else {
        const next = { ...liveState, selected_color: color };
        hmbApplyPickerPaletteSelectionToDom(
          container,
          next,
          pickerLocalInteractionLocked(next),
        );
        commit(next, { suppressMatchingEcho: true });
      }
    });
  });
  on(container.querySelector("#import-video-asset"), "change", (event) => {
    const files = Array.from(event.target?.files || []);
    const pickerShotUuid = hmbConsumeVideoPickerFileInputTarget(
      container,
      currentWidgetState().active_picker_shot_uuid,
    );
    if (!files.length) {
      event.target.value = "";
      return;
    }
    const sources = files.map((file) => ({
      source_path: clean(file.path || file.webkitRelativePath),
      label: clean(file.name),
    })).filter((item) => item.source_path);
    if (sources.length !== files.length) {
      appendImmediateLogLine(
        "WARNING",
        `${files.length - sources.length} selected MP4 file(s) did not expose a local path and were skipped.`,
      );
    }
    if (!sources.length) {
      appendImmediateLogLine("ERROR", "The selected MP4 files did not expose local paths; no second file browser was opened.");
      event.target.value = "";
      return;
    }
    const result = dispatchCommand("import_video_assets", {
        sources,
        select_if_capacity: true,
        picker_shot_uuid: pickerShotUuid,
      });
    appendImmediateLogLine(
      result.delivered ? "INFO" : "ERROR",
      result.delivered
        ? `Batch import requested for ${sources.length} MP4 file(s).`
        : "The MP4 import request could not be delivered.",
    );
    event.target.value = "";
  });
  const playInPreview = (event, button) => {
    event.preventDefault?.();
    event.stopPropagation?.();
    const uid = clean(button?.getAttribute?.("data-play-video-uid"));
    if (!uid) return;
    const liveState = currentWidgetState();
    const livePreviewUid = clean(liveState.preview_video_uid || liveState.selected_video_uid);
    const previewPlayer = container.querySelector("#picker-video");
    const alreadyForced = clean(container.__hmbForceVideoPreviewUid) === uid;
    const requested = hmbVideoPickerRequestedPlaybackUid(container) === uid;
    if (
      previewPlayer
      && livePreviewUid === uid
      && alreadyForced
      && (requested || (!previewPlayer.paused && !previewPlayer.ended))
    ) {
      hmbSetVideoPickerPlaybackRequest(container);
      previewPlayer.pause?.();
      hmbPatchVideoPickerPreviewDom(container, liveState, tr);
      mediaController.refresh(liveState);
      return;
    }
    container.__hmbAutoplayVideoUid = uid;
    container.__hmbForceVideoPreviewUid = uid;
    hmbSetVideoPickerPlaybackRequest(container, uid, true);
    hmbSyncVideoPickerPlayButtonState(container, uid, true, tr);
    const nextState = livePreviewUid === uid
      ? { ...liveState, viewport_mode: "video" }
      : { ...hmbPreviewVideoAsset(liveState, uid), viewport_mode: "video" };
    hmbPatchVideoPickerPreviewDom(container, nextState, tr, {
      autoplay: true,
      onPlaybackError: (error) => {
        hmbSetVideoPickerPlaybackRequest(container);
        hmbSyncVideoPickerPlayButtonState(container, "", false, tr);
        reportPlaybackFailure(error, "Video-card playback");
      },
    });
    mediaController.refresh(nextState);
    delete container.__hmbAutoplayVideoUid;
    if (livePreviewUid !== uid || clean(liveState.viewport_mode).toLowerCase() !== "video") {
      commit(nextState, { suppressMatchingEcho: true });
    }
  };
  const toggleVideoSelection = (event, selectionSurface) => {
    event.preventDefault?.();
    event.stopPropagation?.();
    if (
      pickerLocalInteractionLocked()
      || selectionSurface?.getAttribute?.("aria-disabled") === "true"
      || container.__hmbSuppressVideoSelectionClick
    ) return;
    const uid = clean(selectionSurface?.getAttribute?.("data-toggle-video-uid"));
    if (!uid) return;
    const liveState = currentWidgetState();
    const wasSelected = hmbSelectedVideoAssets(liveState).some((item) => clean(item.video_uid) === uid);
    const nextState = hmbToggleVideoAssetSelection(liveState, uid);
    const nextSelected = hmbSelectedVideoAssets(nextState);
    const isSelected = nextSelected.some((item) => clean(item.video_uid) === uid);
    hmbApplySelectedVideoAssetOrderToDom(container, nextState, tr, pickerLocalInteractionLocked(nextState));
    const loggedState = appendActivityLog(
      nextState,
      wasSelected && !isSelected ? "INFO" : "SUCCESS",
      isSelected
        ? `Video selected as @video${nextSelected.findIndex((item) => clean(item.video_uid) === uid) + 1}.`
        : "Video removed from the active @video order; its history asset remains available.",
    );
    schedulePickerStatePublicationAfterPaint(
      loggedState,
      { commitOptions: { suppressMatchingEcho: true } },
      (paintedState) => {
        hmbPatchVideoPickerPreviewDom(container, paintedState, tr);
        mediaController.refresh(paintedState);
      },
    );
  };
  const deleteVideoAsset = (event, button) => {
    event.preventDefault?.();
    event.stopPropagation?.();
    if (pickerLocalInteractionLocked()) return;
    const uid = clean(button?.getAttribute?.("data-delete-video-uid"));
    if (!uid) return;
    const liveState = currentWidgetState();
    const target = (Array.isArray(liveState.videos) ? liveState.videos : [])
      .find((item, index) => hmbVideoAssetUid(item, index) === uid);
    if (
      clean(liveState.preview_video_uid || liveState.selected_video_uid) === uid
      || clean(container.__hmbForceVideoPreviewUid) === uid
    ) {
      container.querySelector("#picker-video")?.pause?.();
      delete container.__hmbForceVideoPreviewUid;
      delete container.__hmbAutoplayVideoUid;
    }
    const result = dispatchCommand("delete_video_asset", { video_uid: uid });
    if (result.delivered) {
      appendImmediateLogLine("INFO", `${hmbVideoAssetTitle(target || {}, 0)} removal requested. The media file will be preserved.`);
      return;
    }
    commit(appendActivityLog(
      hmbDeleteVideoAsset(liveState, uid),
      "SUCCESS",
      `${hmbVideoAssetTitle(target || {}, 0)} removed from history. The media file was not deleted.`,
    ));
  };
  hmbInstallVideoAssetRootDelegation(
    container,
    { play: playInPreview, select: toggleVideoSelection, remove: deleteVideoAsset },
    activeCleanup,
  );
  activeCleanup.push(hmbInstallVideoAssetDragReorder(container, {
    locked: () => pickerLocalInteractionLocked(),
    currentState: currentWidgetState,
    commitState: (nextState, details) => {
      const loggedState = appendActivityLog(
        nextState,
        "SUCCESS",
        `Video order changed by drag-and-drop; ${details.sourceUid} is now @video${details.targetIndex + 1}.`,
      );
      schedulePickerStatePublicationAfterPaint(loggedState);
    },
  }));
  container.querySelectorAll("[data-resize-section]").forEach((handle) => {
    on(handle, "pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const key = clean(handle.getAttribute("data-resize-section"));
      const section = handle.closest(".side-section");
      if (!key || !section) return;
      const startY = Number(event.clientY || 0);
      const sectionRect = section.getBoundingClientRect?.();
      const offsetHeight = Number(section.offsetHeight || 0);
      const rectHeight = Number(sectionRect?.height || 0);
      const startHeight = offsetHeight > 0 ? offsetHeight : (rectHeight > 0 ? rectHeight : 120);
      const renderScale = offsetHeight > 0 && rectHeight > 0 ? rectHeight / offsetHeight : 1;
      const safeScale = Number.isFinite(renderScale) && renderScale > 0.05 ? renderScale : 1;
      let latestHeight = startHeight;
      try { handle.setPointerCapture?.(event.pointerId); } catch (_error) {}
      const move = (moveEvent) => {
        moveEvent.preventDefault();
        const screenDelta = Number(moveEvent.clientY || startY) - startY;
        latestHeight = clamp(Math.round(startHeight + screenDelta / safeScale), 96, 900);
        section.style.height = `${latestHeight}px`;
        section.style.flexBasis = `${latestHeight}px`;
        hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
      };
      const end = (endEvent) => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", end, true);
        window.removeEventListener("pointercancel", end, true);
        try { handle.releasePointerCapture?.(endEvent?.pointerId ?? event.pointerId); } catch (_error) {}
        const currentLocal = normalize(container.__hmbPendingPickerState || state);
        const heights = hmbNormalizeRightSectionHeights(currentLocal.right_section_heights);
        heights[key] = latestHeight;
        commit({
          ...currentLocal,
          right_section_heights: heights,
        }, { suppressMatchingEcho: true });
        schedulePickerFit();
      };
      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", end, true);
      window.addEventListener("pointercancel", end, true);
      activeCleanup.push(() => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", end, true);
        window.removeEventListener("pointercancel", end, true);
      });
    });
  });

  container.querySelectorAll("[data-resize-panel]").forEach((handle) => {
    on(handle, "pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const key = clean(handle.getAttribute("data-resize-panel"));
      const panel = handle.closest(".panel");
      const stateField = "viewport_panel_height";
      const minimum = HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT;
      if (!panel || key !== "viewport") return;
      const startY = Number(event.clientY || 0);
      const panelRect = panel.getBoundingClientRect?.();
      const offsetHeight = Number(panel.offsetHeight || 0);
      const rectHeight = Number(panelRect?.height || 0);
      const startHeight = Math.max(
        minimum,
        offsetHeight > 0 ? offsetHeight : (rectHeight > 0 ? rectHeight : minimum),
      );
      const renderScale = offsetHeight > 0 && rectHeight > 0 ? rectHeight / offsetHeight : 1;
      const safeScale = Number.isFinite(renderScale) && renderScale > 0.05 ? renderScale : 1;
      let latestHeight = startHeight;
      try { handle.setPointerCapture?.(event.pointerId); } catch (_error) {}

      const move = (moveEvent) => {
        moveEvent.preventDefault();
        const screenDelta = Number(moveEvent.clientY || startY) - startY;
        latestHeight = clamp(
          Math.round(startHeight + screenDelta / safeScale),
          minimum,
          6000,
        );
        panel.style.height = `${latestHeight}px`;
        panel.style.flex = `0 0 ${latestHeight}px`;
        hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
      };

      const end = (endEvent) => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", end, true);
        window.removeEventListener("pointercancel", end, true);
        try { handle.releasePointerCapture?.(endEvent?.pointerId ?? event.pointerId); } catch (_error) {}
        const liveState = currentWidgetState();
        commit({
          ...liveState,
          [stateField]: latestHeight,
        }, { suppressMatchingEcho: true });
        schedulePickerFit();
      };

      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", end, true);
      window.addEventListener("pointercancel", end, true);
      activeCleanup.push(() => {
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", end, true);
        window.removeEventListener("pointercancel", end, true);
      });
    });
  });

  let resizeFrame = 0;
  const schedulePickerFit = (settle = false) => {
    if (resizeFrame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(resizeFrame);
    const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (fn) => setTimeout(fn, 0);
    const apply = () => {
      resizeFrame = 0;
      if (disposed) return;
      if (
        !container.querySelector?.(".hmbvp")
        || !container.querySelector?.(".hmbvp-clip")
      ) {
        container.__hmbVideoPickerMountedRootGuardSchedule?.();
        return;
      }
      if (!pickerExpanded) {
        const fittedState = currentWidgetState();
        hmbApplyVideoPickerCompactHostSizing(container, fittedState);
        container.removeAttribute?.("data-hmb-video-picker-compact-sizing-pending");
        return;
      }
      const measuredInnerHeight = hmbPickerInnerRequiredHeight(container);
      const beforeSignature = hmbPickerFitMeasurementSignature(
        container,
        null,
        measuredInnerHeight,
      );
      if (beforeSignature === container.__hmbPickerFitSignature) return;
      hmbApplyPickerHostSizing(container, measuredInnerHeight);
      container.__hmbPickerFitSignature = hmbPickerFitMeasurementSignature(
        container,
        null,
      );
    };
    resizeFrame = raf(() => {
      if (settle) resizeFrame = raf(apply);
      else apply();
    });
  };

  if (pickerExpanded) {
    hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
    container.__hmbPickerFitSignature = hmbPickerFitMeasurementSignature(
      container,
      null,
    );
  } else {
    delete container.__hmbPickerFitSignature;
  }
  activeCleanup.push(() => {
    if (resizeFrame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(resizeFrame);
    resizeFrame = 0;
  });
  schedulePickerFit(true);
  container.__hmbVideoPickerControllerUpdate = (nextProps) => {
    const workspaceEchoMatches = hmbPickerWorkspacePublicationMatchesEcho(
      container,
      hmbPickerStateFromProps(nextProps || {}),
    );
    if (hmbConsumePendingPickerStateEcho(container, nextProps || {})) {
      if (workspaceEchoMatches) {
        hmbReleasePickerWorkspacePublication(
          container,
          Number(container.__hmbPickerWorkspacePublicationGeneration || 0),
        );
      }
      patchMountedPicker(nextProps || {});
      return;
    }
    hmbClearPendingPickerStateEcho(container);
    patchMountedPicker(nextProps || {});
  };
  return container.__hmbVideoPickerControllerProxy;
}
