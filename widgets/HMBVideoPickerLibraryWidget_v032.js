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
const HMB_PICKER_CONTENT_FALLBACK_HEIGHT = 960;
const HMB_PICKER_VIEWPORT_STAGE_MIN_HEIGHT = 360;
const HMB_PICKER_OUTLINER_BODY_MIN_HEIGHT = 300;
const HMB_PICKER_OUTLINER_PANEL_MIN_HEIGHT = 480;
const HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT = 520;
const HMB_PLAYBLAST_RESOLUTIONS = [
  { value: "1280x720", width: 1280, height: 720, label: "1280 × 720" },
  { value: "1920x1080", width: 1920, height: 1080, label: "1920 × 1080" },
];
const HMB_UI_THEME_STORAGE_KEY = "hmb_gp_production_ui_theme";
const HMB_UI_THEME_EVENT = "hmb-gp-production-theme-change";
const HMB_RIGHT_SECTION_DEFAULT_HEIGHTS = { settings: 285, color: 628, log: 208 };
const HMB_ACTIVITY_LOG_MAX_ROWS = 80;
const HMB_ACTIVITY_LOG_MESSAGE_MAX_CHARS = 260;
const HMB_PICKER_MAX_SELECTED_VIDEOS = 10;
const HMB_PICKER_MAX_SNAPSHOTS = 10;

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

export function hmbScopeWidgetStyleMarkup(markup, rootSelector) {
  return String(markup || "").replace(/<style>([\s\S]*?)<\/style>/g, (_match, css) => (
    `<style>${hmbScopeWidgetCss(css, rootSelector)}</style>`
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

function hmbNormalizeUiTheme(value) {
  return String(value || "").toUpperCase() === "T" ? "T" : "P";
}

function hmbReadSharedUiTheme(fallback = "P") {
  try {
    if (typeof window !== "undefined") {
      const memoryTheme = hmbNormalizeUiTheme(window.__hmbGpProductionUiTheme);
      if (window.__hmbGpProductionUiTheme === "P" || window.__hmbGpProductionUiTheme === "T") return memoryTheme;
      if (window.sessionStorage) {
        const storedTheme = window.sessionStorage.getItem(HMB_UI_THEME_STORAGE_KEY);
        if (storedTheme === "P" || storedTheme === "T") {
          window.__hmbGpProductionUiTheme = storedTheme;
          return storedTheme;
        }
      }
    }
  } catch (_error) {}
  return hmbNormalizeUiTheme(fallback);
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
    presetObject: "Preset Object",
    playblastSettings: "PLAYBLAST SETTINGS",
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
    cutVideoHistory: "CURRENT CUT VIDEOS",
    selectedVideos: "Selected",
    selectVideoAsset: "Select",
    deselectVideoAsset: "Deselect",
    previewLarge: "Large Preview",
    deleteVideoAsset: "Delete from history",
    importVideoAsset: "Load",
    emptyVideoHistory: "Generate a playblast to add a video for this cut.",
    dragVideoOrder: "Drag selected cards to change @video order.",
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
    presetObject: "프리셋 오브젝트",
    target: "대상",
    color: "컬러",
    playblastSettings: "플레이블라스트 설정",
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
    cutVideoHistory: "현재 컷 생성 히스토리",
    selectedVideos: "선택",
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

function clean(value) {
  return String(value == null ? "" : value).trim();
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

function isMayaScenePath(value) {
  return /\.(ma|mb)$/i.test(clean(value).replace(/^["']|["']$/g, ""));
}

function videoPickerNodeRoot(container) {
  let current = container?.parentElement || null;
  let fallback = null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    try {
      if (current.matches?.(".react-flow__node")) return current;
      const nativeSceneElements = current.querySelectorAll?.(
        '[data-parameter-name="MAYA_SCENE"], [data-parameter="MAYA_SCENE"], [data-parameter-key="MAYA_SCENE"], '
        + 'input[name="MAYA_SCENE"], textarea[name="MAYA_SCENE"], input[aria-label*="MAYA_SCENE" i], '
        + 'textarea[aria-label*="MAYA_SCENE" i], input[placeholder*=".mb" i], input[placeholder*=".ma" i]',
      );
      if (Array.from(nativeSceneElements || []).some((element) => !container.contains?.(element))) return current;
      if (!fallback && (
        current.hasAttribute?.("data-node-id")
        || current.hasAttribute?.("data-nodeid")
        || current.hasAttribute?.("data-id")
      )) {
        fallback = current;
      }
    } catch (_error) {}
  }
  return fallback || container?.parentElement || container || null;
}

function hmbPickerBranchContainsVideoOutputs(branch) {
  if (!branch?.querySelector) return false;
  try {
    return Boolean(branch.querySelector(
      '[data-parameter-name="PICKER_OUT"], '
      + '[data-parameter-name="VIDEO_OUT"], '
      + '.react-flow__handle[data-handleid="PICKER_OUT"], '
      + '.react-flow__handle[data-handleid="VIDEO_OUT"]',
    ));
  } catch (_error) {
    return false;
  }
}

function mayaPathFromElement(element) {
  if (!element) return "";
  const values = [
    element.value,
    element.getAttribute?.("value"),
    element.getAttribute?.("title"),
    element.getAttribute?.("data-value"),
    element.getAttribute?.("data-path"),
  ];
  for (const value of values) {
    const text = clean(value).replace(/^["']|["']$/g, "");
    if (isMayaScenePath(text) && !/[\\/]fakepath[\\/]/i.test(text)) return text;
  }
  const text = clean(element.textContent);
  const match = text.length <= 4096
    ? text.match(/(?:file:\/\/\/)?(?:[A-Za-z]:[\\/]|\\\\|\/)[^\r\n<>"']+?\.(?:mb|ma)(?=$|[\s"'])/i)
    : null;
  return match ? clean(match[0]) : "";
}

function nativeMayaPickerElements(container) {
  const root = videoPickerNodeRoot(container);
  if (!root?.querySelectorAll) return [];
  const selectors = [
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
  for (const selector of selectors) {
    for (const element of root.querySelectorAll(selector)) {
      if (container.contains?.(element) || seen.has(element)) continue;
      seen.add(element);
      elements.push(element);
    }
  }
  return elements;
}

function nativeMayaPickerHosts(container) {
  const root = videoPickerNodeRoot(container);
  if (!root?.querySelectorAll) return [];
  const hosts = [];
  const seen = new Set();
  const addHost = (host) => {
    if (!host || host === root || container.contains?.(host) || host.contains?.(container) || seen.has(host)) return;
    seen.add(host);
    hosts.push(host);
  };
  const selectors = [
    '[data-parameter-name="MAYA_SCENE"]',
    '[data-parameter="MAYA_SCENE"]',
    '[data-parameter-key="MAYA_SCENE"]',
    '[data-parameter-id*="MAYA_SCENE" i]',
    '[aria-label*="MAYA_SCENE" i]',
  ];
  for (const selector of selectors) {
    for (const host of root.querySelectorAll(selector)) addHost(host);
  }
  for (const element of nativeMayaPickerElements(container)) {
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
  for (const label of root.querySelectorAll("label, span, div")) {
    if (container.contains?.(label)) continue;
    const text = clean(label.textContent);
    if (text.length > 80 || !/^MAYA[\s_-]*SCENE\b/i.test(text)) continue;
    let candidate = label;
    for (let depth = 0; candidate && candidate !== root && depth < 5; depth += 1, candidate = candidate.parentElement) {
      if (candidate.querySelector?.('input, textarea, button, [role="button"]')) {
        addHost(candidate);
        break;
      }
    }
  }
  return hosts;
}

function nativeMayaScenePath(container) {
  for (const element of nativeMayaPickerElements(container)) {
    const candidate = mayaPathFromElement(element);
    if (candidate) return candidate;
  }
  for (const host of nativeMayaPickerHosts(container)) {
    const direct = mayaPathFromElement(host);
    if (direct) return direct;
    for (const element of host.querySelectorAll?.("input, textarea, [title], [data-value], [data-path], span, div") || []) {
      const candidate = mayaPathFromElement(element);
      if (candidate) return candidate;
    }
  }
  return "";
}

export function hmbCollapseNativeMayaLayoutRows(container) {
  const shell = findReactFlowNode(container);
  if (!shell) return 0;
  let collapsed = 0;
  for (const host of nativeMayaPickerHosts(container)) {
    let parameterBranch = host;
    try {
      parameterBranch = host.closest?.(
        '[data-parameter-name="MAYA_SCENE"], [data-parameter="MAYA_SCENE"], '
        + '[data-parameter-key="MAYA_SCENE"], [data-parameter-id*="MAYA_SCENE" i]',
      ) || host;
    } catch (_error) {}
    // Griptape v119 nests the native parameter inside one or more layout
    // wrappers. Walk to the largest MAYA_SCENE-only branch, but stop before
    // the common ancestor that also owns the visible Picker widget.
    while (
      parameterBranch?.parentElement
      && parameterBranch.parentElement !== shell
      && !parameterBranch.parentElement.contains?.(container)
      && !hmbPickerIsOuterCanvasOrNode(parameterBranch.parentElement)
      && !hmbPickerBranchContainsVideoOutputs(parameterBranch.parentElement)
    ) {
      parameterBranch = parameterBranch.parentElement;
    }
    if (
      !parameterBranch?.style
      || parameterBranch === shell
      || parameterBranch.contains?.(container)
      || hmbPickerIsOuterCanvasOrNode(parameterBranch)
    ) {
      continue;
    }
    parameterBranch.dataset.hmbMayaPickerLayoutCollapsed = "1";
    parameterBranch.style.setProperty("height", "0px", "important");
    parameterBranch.style.setProperty("min-height", "0px", "important");
    parameterBranch.style.setProperty("max-height", "0px", "important");
    parameterBranch.style.setProperty("flex", "0 0 0px", "important");
    parameterBranch.style.setProperty("margin", "0", "important");
    parameterBranch.style.setProperty("padding", "0", "important");
    parameterBranch.style.setProperty("border", "0", "important");
    parameterBranch.style.setProperty("overflow", "hidden", "important");
    collapsed += 1;
  }
  return collapsed;
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
  hmbCollapseNativeMayaLayoutRows(container);
  for (const host of nativeMayaPickerHosts(container)) {
    host.setAttribute("data-hmb-maya-picker-bridge", "true");
    host.setAttribute("aria-hidden", "true");
    host.style.setProperty("position", "absolute", "important");
    host.style.setProperty("left", "-100000px", "important");
    host.style.setProperty("top", "0", "important");
    host.style.setProperty("width", "1px", "important");
    host.style.setProperty("height", "1px", "important");
    host.style.setProperty("min-width", "0", "important");
    host.style.setProperty("min-height", "0", "important");
    host.style.setProperty("overflow", "hidden", "important");
    host.style.setProperty("opacity", "0", "important");
    host.style.setProperty("pointer-events", "none", "important");
    host.style.setProperty("clip-path", "inset(50%)", "important");
  }
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
  const match = text.match(/(?:file:\/\/\/)?(?:[A-Za-z]:[\\/]|\\\\|\/)[^\r\n<>"']+?\.(?:mb|ma)(?=$|[\s"'])/i);
  return match ? clean(match[0]) : "";
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
  const dataUri = clean(item?.data_uri || item?.snapshot_data_uri);
  const identity = [
    clean(item?.path || item?.snapshot_path),
    clean(item?.video_uid),
    Number(item?.render_video_slot || item?.video_slot || 1),
    Number(item?.frame || item?.snapshot_frame || 0),
    Number(item?.created_at_ms || item?.created_at || 0),
    dataUri.length,
    dataUri.slice(-32),
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
      && clean(item.data_uri || item.snapshot_data_uri).startsWith("data:image/")
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
      return next;
    });
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
  const uniqueOrder = Array.from(new Set((Array.isArray(orderedUids) ? orderedUids : []).map(clean).filter(Boolean)))
    .slice(0, HMB_PICKER_MAX_SELECTED_VIDEOS);
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
  if (!byUid.has(previewUid)) previewUid = uniqueOrder[0] || clean(videos[0]?.video_uid);
  const preview = byUid.get(previewUid) || null;
  const previewOrder = Number(orderByUid.get(previewUid) || 0);
  const selectedSlot = previewOrder > 0
    ? previewOrder
    : clamp(Number(state?.selected_video_slot || 1), 1, Math.max(1, uniqueOrder.length));
  return {
    ...state,
    videos,
    video_library_version: 1,
    max_selected_videos: HMB_PICKER_MAX_SELECTED_VIDEOS,
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
  if (index >= 0) ordered.splice(index, 1);
  else if (ordered.length < HMB_PICKER_MAX_SELECTED_VIDEOS) ordered.push(targetUid);
  return hmbApplyVideoAssetSelection(state, ordered, targetUid);
}

export function hmbMoveSelectedVideoAsset(state, uid, targetIndex) {
  const targetUid = clean(uid);
  const ordered = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  const currentIndex = ordered.indexOf(targetUid);
  if (currentIndex < 0 || !ordered.length) return { ...state };
  const destination = clamp(Math.floor(Number(targetIndex || 0)), 0, ordered.length - 1);
  ordered.splice(currentIndex, 1);
  ordered.splice(destination, 0, targetUid);
  return hmbApplyVideoAssetSelection(state, ordered, targetUid);
}

export function hmbApplySelectedVideoAssetOrderToDom(container, state) {
  const grid = container?.querySelector?.(".video-asset-grid");
  if (!grid || typeof grid.querySelectorAll !== "function" || typeof grid.appendChild !== "function") return [];
  const cards = Array.from(grid.querySelectorAll("[data-video-uid]") || []);
  if (!cards.length) return [];
  const selectedUids = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  const selectedOrder = new Map(selectedUids.map((uid, index) => [uid, index + 1]));
  const cardByUid = new Map(cards.map((card) => [clean(card.getAttribute?.("data-video-uid")), card]));
  const orderedCards = [
    ...selectedUids.map((uid) => cardByUid.get(uid)).filter(Boolean),
    ...cards.filter((card) => !selectedOrder.has(clean(card.getAttribute?.("data-video-uid")))),
  ];
  orderedCards.forEach((card) => grid.appendChild(card));
  for (const card of cards) {
    const uid = clean(card.getAttribute?.("data-video-uid"));
    const order = Number(selectedOrder.get(uid) || 0);
    card.setAttribute?.("data-selected-video-order", String(order));
    const badge = card.querySelector?.(".selected-video-order");
    if (badge && order > 0) badge.textContent = `@video${order}`;
  }
  return selectedUids;
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
  const locked = options.locked === true;
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
    if (
      !session
      || !targetUid
      || targetUid === clean(session.sourceUid)
      || !card?.hasAttribute?.("data-selected-video-uid")
    ) {
      clearCandidate();
      return false;
    }
    const selected = hmbSelectedVideoAssets(currentState());
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
  if (locked && retainedSession) {
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
      locked
      || !card
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
    container.__hmbVideoDragSession = {
      sourceUid,
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
  const exists = source.some((item, index) => hmbVideoAssetUid(item, index) === targetUid);
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
  const nextState = { ...state, videos: remaining };
  const ordered = hmbSelectedVideoAssets(nextState).map((item) => clean(item.video_uid));
  const requestedPreview = clean(state?.preview_video_uid || state?.selected_video_uid) === targetUid
    ? (ordered[0] || clean(remaining[0]?.video_uid))
    : clean(state?.preview_video_uid || state?.selected_video_uid);
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
    max_selected_videos: HMB_PICKER_MAX_SELECTED_VIDEOS,
    pending_action: "",
    pending_action_id: "",
    backend_ack_action_id: "",
    runtime_instance_id: "",
    node_width: 0,
    node_height: 0,
    outliner_panel_height: 0,
    viewport_panel_height: 0,
    right_section_heights: { ...HMB_RIGHT_SECTION_DEFAULT_HEIGHTS },
    ui_layout_version: 5,
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
    language: "en",
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
      const bindings = Array.isArray(entry.bindings)
        ? entry.bindings.map((binding, index) => normalizeBinding(binding, slot, index + 1)).filter(Boolean)
        : [];
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
  state.ui_layout_version = 5;
  state.ui_theme = hmbNormalizeUiTheme(state.ui_theme);
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
  state.snapshot_data_uri = clean(state.snapshot_data_uri).startsWith("data:image/")
    ? clean(state.snapshot_data_uri)
    : "";
  state.snapshot_path = clean(state.snapshot_path);
  const snapshotByUid = new Map();
  const rawSnapshots = Array.isArray(state.snapshots) ? state.snapshots : [];
  rawSnapshots.forEach((raw, snapshotIndex) => {
    if (!raw || typeof raw !== "object") return;
    const dataUri = clean(raw?.data_uri || raw?.snapshot_data_uri);
    if (!dataUri.startsWith("data:image/")) return;
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
      data_uri: dataUri,
      path: clean(raw?.path || raw?.snapshot_path),
      created_at_ms: Math.max(0, Number(raw?.created_at_ms || raw?.created_at || 0)),
    });
  });
  if (state.snapshot_active && state.snapshot_video_slot && state.snapshot_data_uri) {
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
        data_uri: state.snapshot_data_uri,
        path: state.snapshot_path,
      }, rawSnapshots.length);
    snapshotByUid.set(snapshotUid, {
      snapshot_uid: snapshotUid,
      video_uid: clean(matchingSnapshot?.video_uid || state.preview_video_uid || state.selected_video_uid),
      render_video_slot: state.snapshot_video_slot,
      video_slot: state.snapshot_video_slot,
      frame: state.snapshot_frame,
      data_uri: state.snapshot_data_uri,
      path: state.snapshot_path,
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
    state.snapshot_data_uri = clean(activeSnapshot.data_uri);
    state.snapshot_path = clean(activeSnapshot.path);
  } else {
    state.snapshot_active = false;
    state.active_snapshot_uid = "";
    state.snapshot_video_slot = 0;
    state.snapshot_data_uri = "";
    state.snapshot_path = "";
    viewportMode = "video";
  }
  state.viewport_mode = viewportMode;
  state.native_read_ready = !!state.native_read_ready;
  state.native_read_mode = clean(state.native_read_mode);
  state.native_source_version = clean(state.native_source_version);
  state.native_metadata = state.native_metadata && typeof state.native_metadata === "object" ? { ...state.native_metadata } : {};
  state.outliner_search = clean(state.outliner_search);
  state.language = clean(state.language).toLowerCase() === "ko" ? "ko" : "en";
  state.outliner_nodes = Array.isArray(state.outliner_nodes) ? state.outliner_nodes.filter((item) => item && typeof item === "object") : [];
  state.outliner_expanded = Array.isArray(state.outliner_expanded) ? state.outliner_expanded.map(clean).filter(Boolean) : [];
  state.cameras = Array.isArray(state.cameras) ? state.cameras.filter((item) => item && typeof item === "object") : [];
  state.videos = Array.isArray(state.videos)
    ? state.videos.map((item, index) => normalizeVideo(item, index)).filter(Boolean)
    : [];
  const selectedVideoUids = hmbSelectedVideoAssets(state).map((item) => clean(item.video_uid));
  Object.assign(
    state,
    hmbApplyVideoAssetSelection(
      state,
      selectedVideoUids,
      clean(state.preview_video_uid || state.selected_video_uid),
    ),
  );
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

export function hmbClearPendingPickerStateEcho(container) {
  if (!container) return;
  if (container.__hmbPendingPickerStateEchoTimer) {
    try { clearTimeout(container.__hmbPendingPickerStateEchoTimer); } catch (_error) {}
  }
  delete container.__hmbPendingPickerStateEchoes;
  delete container.__hmbPendingPickerStateEchoTimer;
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
  }, 1500);
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
    ? item.bindings.map((binding, index) => normalizeBinding(binding, slot, index + 1)).filter(Boolean)
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
  const operationBusy = !terminalFailure && (
    stopping
    || !!localReadPending
    || !!localOriginalPending
    || ["READING_SCENE", "RUNNING", "GENERATING_VIDEO", "GENERATING_ORIGINAL", "SNAPSHOT_RENDERING"].includes(status)
    || ["MAYA_READING", "PYTHON_COMMAND_RECEIVED", "ORIGINAL_RENDERING", "SNAPSHOT_RENDERING"].includes(sceneStage)
    || ["read_scene", "render_original_preview", "run_video", "render_snapshot"].includes(operationKind)
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
      && clean(state.snapshot_data_uri).startsWith("data:image/")
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

function setSlotBindings(state, slot, bindings) {
  return {
    ...state,
    slot_assignments: Array.from({ length: state.active_slot_count }, (_, index) => {
      const currentSlot = index + 1;
      return {
        video_slot: currentSlot,
        bindings: (currentSlot === slot ? bindings : selectedBindings(state, currentSlot))
          .map((binding, row) => ({ ...normalizeBinding(binding, currentSlot, row + 1), video_slot: currentSlot, picker_order: row + 1 }))
          .filter(Boolean),
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

function findReactFlowNode(container) {
  let current = container ? container.parentElement : null;
  for (let index = 0; current && index < 10; index += 1) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) return null;
    current = current.parentElement;
  }
  return null;
}

function hmbPickerNodeIsSelected(root) {
  if (!root) return false;
  if (root.classList?.contains("selected")) return true;
  if (String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true") return true;
  if (String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true") return true;
  return Boolean(root.querySelector?.(
    ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
  ));
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
  if (!hmbPickerNodeIsSelected(findReactFlowNode(container) || videoPickerNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function hmbPickerIsOuterCanvasOrNode(el) {
  if (!el || el === document.body || el === document.documentElement) return true;
  const className = String(el.className || "").toLowerCase();
  const testId = String(el.getAttribute?.("data-testid") || "").toLowerCase();
  const role = String(el.getAttribute?.("role") || "").toLowerCase();
  return Boolean(
    className.includes("react-flow__node") ||
    className.includes("react-flow__pane") ||
    className.includes("react-flow__viewport") ||
    className.includes("react-flow__renderer") ||
    className.includes("react-flow__selection") ||
    testId === "node" ||
    testId.includes("react-flow") ||
    role === "application"
  );
}

function hmbPickerLocalHostAncestors(container) {
  const result = [];
  let current = container ? container.parentElement : null;
  for (let index = 0; current && index < 12; index += 1) {
    if (hmbPickerIsOuterCanvasOrNode(current)) break;
    result.push(current);
    current = current.parentElement;
  }
  return result;
}

export function hmbNormalizePickerHostAncestors(container) {
  hmbPickerLocalHostAncestors(container).forEach((element) => {
    if (!element?.style) return;
    try {
      const pickerHeightPropagation = element.dataset?.hmbPickerHeightPropagation === "1";
      // Do not assign height, flex, overflow, or width here. These wrappers
      // belong to Griptape's adaptive parameter-row layout. Only remove the
      // intrinsic-width floor so the picker can shrink inside its own row.
      if (element.style.width === "100%") element.style.removeProperty("width");
      if (element.style.maxWidth === "none") element.style.removeProperty("max-width");
      if (!pickerHeightPropagation) {
        if (element.style.height === "auto") element.style.removeProperty("height");
        if (element.style.minHeight === "0px" || element.style.minHeight === "0") {
          element.style.removeProperty("min-height");
        }
        if (element.style.maxHeight === "none") element.style.removeProperty("max-height");
        if (element.style.overflow === "visible") element.style.removeProperty("overflow");
        if (element.style.flex === "1 1 auto") element.style.removeProperty("flex");
        if (element.style.alignSelf === "stretch") element.style.removeProperty("align-self");
      }
      element.style.minWidth = "0";
      element.style.boxSizing = "border-box";
    } catch (_error) {}
  });
}

function hmbReleaseLegacyOuterNodeOverrides(container) {
  const shell = findReactFlowNode(container);
  if (!shell?.style || !shell.dataset) return shell;
  const legacyOverride = (
    shell.dataset.hmbVideoPickerInitialSizeApplied === "1"
    || shell.dataset.hmbPickerBootstrapRecovered === "1"
  );
  if (!legacyOverride) return shell;
  try {
    // Keep the current width/height as the user's visible node size, but release
    // the min/max/overflow locks left by v022 so Griptape can own subsequent
    // native resize and adaptive-row calculations.
    shell.style.removeProperty("min-width");
    shell.style.removeProperty("min-height");
    shell.style.removeProperty("max-width");
    shell.style.removeProperty("max-height");
    shell.style.removeProperty("overflow");
    shell.style.removeProperty("box-sizing");
    delete shell.dataset.hmbVideoPickerInitialSizeApplied;
    delete shell.dataset.hmbPickerBootstrapRecovered;
  } catch (_error) {}
  return shell;
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
  // Match HMBPromptLibrary: the dashboard owns one exact content frame and the
  // React Flow node grows only when that frame plus native rows require it.
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
    hmbPickerLocalHostAncestors(container).forEach(applyMinimum);
    const clip = container.querySelector?.(".hmbvp-clip");
    if (clip && clip.style) {
      hmbSetPickerStyleIfChanged(clip, "width", "100%");
      if (clip.style.height !== `${required}px`) clip.style.height = `${required}px`;
      hmbSetPickerStyleIfChanged(clip, "min-height", `${required}px`);
      hmbSetPickerStyleIfChanged(clip, "max-width", "none");
      hmbSetPickerStyleIfChanged(clip, "max-height", "none");
      hmbSetPickerStyleIfChanged(clip, "overflow", "visible");
      hmbSetPickerStyleIfChanged(clip, "box-sizing", "border-box");
    }
    const picker = container.querySelector?.(".hmbvp");
    if (picker && picker.style) {
      hmbSetPickerStyleIfChanged(picker, "width", "100%");
      if (picker.style.height !== `${required}px`) picker.style.height = `${required}px`;
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

function hmbApplyPickerInitialNodeSizeOnce(container) {
  const shell = findReactFlowNode(container);
  if (!shell || !shell.style) return;
  if (shell.dataset && shell.dataset.hmbVideoPickerInitialSizeApplied === "1") return;
  try {
    const rect = shell.getBoundingClientRect ? shell.getBoundingClientRect() : null;
    const currentWidth = rect && rect.width ? rect.width : 0;
    const currentHeight = rect && rect.height ? rect.height : 0;
    // Python/manifest metadata owns the 1400x1200 new-node default. This is
    // only a zero-layout fallback: a smaller non-zero shell may be a restored
    // user resize and must not be enlarged during a widget remount.
    const needsWidth = !currentWidth || currentWidth <= 1;
    const needsHeight = !currentHeight || currentHeight <= 1;
    if (needsWidth) shell.style.width = `${HMB_DEFAULT_NODE_WIDTH}px`;
    if (needsHeight) shell.style.height = `${HMB_DEFAULT_NODE_HEIGHT}px`;
    shell.style.minWidth = `${HMB_MIN_NODE_WIDTH}px`;
    shell.style.minHeight = `${HMB_MIN_NODE_HEIGHT}px`;
    shell.style.maxHeight = "none";
    shell.style.overflow = "visible";
    shell.style.boxSizing = "border-box";
    if (shell.dataset) shell.dataset.hmbVideoPickerInitialSizeApplied = "1";
  } catch (_error) {}
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

function hmbRequiredPickerNodeHeight(container, preferredShell = null) {
  const shell = preferredShell || findReactFlowNode(container);
  if (!shell || !container) return HMB_MIN_NODE_HEIGHT;
  const innerRequired = hmbPickerInnerRequiredHeight(container);
  let topOffset = 0;
  let bottomInset = 8;
  try {
    const shellRect = shell.getBoundingClientRect?.();
    const containerRect = container.getBoundingClientRect?.();
    const scale = hmbPickerElementScaleY(shell) || 1;
    if (shellRect && containerRect) {
      topOffset = Math.max(0, (containerRect.top - shellRect.top) / Math.max(0.05, scale));
    }
    const style = window.getComputedStyle ? window.getComputedStyle(shell) : null;
    if (style) {
      bottomInset += (parseFloat(style.paddingBottom) || 0) + (parseFloat(style.borderBottomWidth) || 0);
    }
  } catch (_error) {}
  return Math.max(HMB_MIN_NODE_HEIGHT, Math.ceil(topOffset + innerRequired + bottomInset));
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
  const shell = findReactFlowNode(container);
  const reclaim = Number(shell?.__hmbPickerCommandRowReclaim || 0);
  if (!(reclaim > 0)) return 0;
  const layoutRow = hmbPickerParameterLayoutRow(container, "HMB_PICKER_STATE");
  if (!layoutRow?.style) return 0;

  // The command bridge owns its own zero-height collapse. Clear the former
  // adaptive-stack overrides so the visible picker can retain its natural
  // content height without a flex/height feedback loop.
  for (const property of [
    "position", "top", "left", "right", "bottom", "width", "margin",
    "height", "min-height", "max-height", "flex", "overflow",
  ]) {
    layoutRow.style.removeProperty(property);
  }
  delete layoutRow.dataset.hmbPickerHeightPropagation;

  const stack = layoutRow.parentElement;
  const trailingSpacer = Array.from(stack?.children || []).find(
    (element) => String(element.getAttribute?.("aria-hidden") || "").toLowerCase() === "true",
  );
  if (trailingSpacer?.style) {
    trailingSpacer.style.setProperty("height", "0px", "important");
    trailingSpacer.style.setProperty("min-height", "0px", "important");
    trailingSpacer.style.setProperty("flex", "0 0 0px", "important");
    trailingSpacer.style.setProperty("overflow", "hidden", "important");
  }
  return 1;
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
  const shell = findReactFlowNode(container);
  if (!shell || !shell.style) return null;
  const nextHeight = Math.max(
    HMB_MIN_NODE_HEIGHT,
    Math.min(6000, Math.round(Number(height) || HMB_DEFAULT_NODE_HEIGHT)),
  );
  try {
    shell.style.height = `${nextHeight}px`;
    shell.style.minHeight = `${HMB_MIN_NODE_HEIGHT}px`;
    shell.style.maxHeight = "none";
    shell.style.overflow = "visible";
    shell.style.boxSizing = "border-box";
  } catch (_error) {}
  return { shell, height: nextHeight };
}

function hmbApplyPickerDominoResizeFrame(container, startNodeHeight, startRequiredHeight) {
  const innerRequired = hmbPickerInnerRequiredHeight(container);
  hmbApplyPickerHostSizing(container, innerRequired);
  const shell = findReactFlowNode(container);
  const nextRequiredHeight = hmbRequiredPickerNodeHeight(container, shell);
  const nextNodeHeight = hmbPickerDominoOuterHeight(
    startNodeHeight,
    startRequiredHeight,
    nextRequiredHeight,
  );
  const applied = hmbApplyPickerOuterNodeHeight(container, nextNodeHeight);
  try {
    const liveShell = applied?.shell || shell;
    if (liveShell?.style) liveShell.style.minHeight = `${nextRequiredHeight}px`;
  } catch (_error) {}
  return {
    innerHeight: innerRequired,
    nodeHeight: nextNodeHeight,
    requiredHeight: nextRequiredHeight,
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
  const shell = preferredShell || hmbReleaseLegacyOuterNodeOverrides(container);
  hmbApplyPickerCommandRowReclaim(container);
  const innerRequired = Math.max(
    HMB_PICKER_CONTENT_FALLBACK_HEIGHT,
    Math.ceil(Number(measuredInnerHeight) || hmbPickerInnerRequiredHeight(container)),
  );
  hmbApplyPickerHostSizing(container, innerRequired);
  if (!shell || !shell.style) return shell;
  try {
    const requiredHeight = hmbRequiredPickerNodeHeight(container, shell);
    hmbSetPickerStyleIfChanged(shell, "min-width", `${HMB_MIN_NODE_WIDTH}px`);
    hmbSetPickerStyleIfChanged(shell, "min-height", `${requiredHeight}px`);
    hmbSetPickerStyleIfChanged(shell, "max-width", "none");
    hmbSetPickerStyleIfChanged(shell, "max-height", "none");
    hmbSetPickerStyleIfChanged(shell, "overflow", "visible");
    hmbSetPickerStyleIfChanged(shell, "box-sizing", "border-box");
    const rect = shell.getBoundingClientRect?.();
    const width = Number(shell.offsetWidth || rect?.width || 0);
    const height = Number(shell.offsetHeight || 0)
      || Number(rect?.height || 0) / Math.max(0.05, hmbPickerElementScaleY(shell));
    if (width > 0 && width < HMB_MIN_NODE_WIDTH) {
      hmbSetPickerStyleIfChanged(shell, "width", `${HMB_MIN_NODE_WIDTH}px`);
    }
    if (height > 0 && height < requiredHeight) {
      hmbSetPickerStyleIfChanged(shell, "height", `${requiredHeight}px`);
    }
  } catch (_error) {}
  return shell;
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
  const shell = preferredShell || findReactFlowNode(container);
  const picker = container?.querySelector?.(".hmbvp");
  if (!shell?.style || !picker) return { changed: false, height: 0, delta: 0 };
  try {
    const shellRect = shell.getBoundingClientRect?.();
    const pickerRect = picker.getBoundingClientRect?.();
    const scale = hmbPickerElementScaleY(shell) || 1;
    if (!shellRect || !pickerRect || !(scale > 0)) {
      return { changed: false, height: hmbPickerNodeShellHeight(shell), delta: 0 };
    }
    const delta = (Number(pickerRect.bottom || 0) - Number(shellRect.bottom || 0))
      / Math.max(0.05, scale);
    const currentHeight = hmbPickerNodeShellHeight(shell);
    if (!(currentHeight > 0) || Math.abs(delta) <= 2 || (delta < 0 && !allowShrink)) {
      return { changed: false, height: currentHeight, delta };
    }
    // Move only the React Flow node's bottom edge. The Picker panels keep
    // their measured size, so the status bar is neither stretched nor clipped.
    const targetHeight = Math.max(
      HMB_MIN_NODE_HEIGHT,
      Math.min(6000, Math.ceil(currentHeight + delta + 1)),
    );
    if (Math.abs(targetHeight - currentHeight) <= 1) {
      return { changed: false, height: currentHeight, delta };
    }
    shell.style.height = `${targetHeight}px`;
    shell.style.minHeight = `${targetHeight}px`;
    shell.style.maxHeight = "none";
    shell.style.overflow = "visible";
    shell.style.boxSizing = "border-box";
    return { changed: true, height: targetHeight, delta };
  } catch (_error) {
    return { changed: false, height: hmbPickerNodeShellHeight(shell), delta: 0 };
  }
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
  const nodes = state.outliner_nodes;
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

function outlinerHtml(state, bindings, tr) {
  if (!state.outliner_nodes.length) {
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
  const visible = filteredVisibleNodes(state);
  return `<div class="outliner-list" role="tree" aria-label="${escapeHtml(tr.outliner)}">${visible.map((node, visibleIndex) => {
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
    return `<div class="outliner-row ${selected ? "selected" : ""} ${outputVisible ? "" : "output-off"}" data-group-path="${escapeHtml(path)}" title="${escapeHtml(path)}" role="treeitem" tabindex="${rowTabIndex}" aria-level="${Number(depthMap.get(path) || 0) + 1}" aria-selected="${selected ? "true" : "false"}" ${hasChildren ? `aria-expanded="${expanded.has(path) ? "true" : "false"}"` : ""}>
      <button type="button" class="tree-toggle ${hasChildren ? "" : "leaf"}" data-toggle-path="${escapeHtml(path)}" style="margin-left:${indent}px" aria-label="${escapeHtml(hasChildren ? toggleLabel : name)}" ${hasChildren ? "" : "disabled"}>${hasChildren ? (expanded.has(path) ? "▾" : "▸") : ""}</button>
      <span class="node-icon">${node.node_kind === "mesh" ? "◆" : "◇"}</span>
      <span class="group-name">${escapeHtml(name)}</span>
      ${node.referenced ? `<span class="ref-tag">${escapeHtml(tr.reference)}</span>` : ""}
      ${assignedColor ? `<span class="assigned-chip" style="${hmbPickerColorStyle(assignedColor, state.marker_catalog)}" title="${escapeHtml(assignedColor)}"></span>` : ""}
      <button type="button" class="eye-toggle ${outputVisible ? "on" : "off"}" data-visibility-path="${escapeHtml(path)}" title="${escapeHtml(visibilityLabel)}" aria-label="${escapeHtml(`${name}: ${visibilityLabel}`)}" aria-pressed="${outputVisible ? "true" : "false"}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"></path><circle cx="12" cy="12" r="3"></circle></svg></button>
    </div>`;
  }).join("")}</div>`;
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

function videoAssetCardsHtml(state, tr, locked) {
  const selected = hmbSelectedVideoAssets(state);
  const orderByUid = new Map(selected.map((item, index) => [clean(item.video_uid), index + 1]));
  const assets = (Array.isArray(state?.videos) ? state.videos : [])
    .map((item, catalogIndex) => ({ item, catalogIndex }))
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
  const selectionFull = selected.length >= HMB_PICKER_MAX_SELECTED_VIDEOS;
  return assets.map(({ item, catalogIndex }) => {
    const uid = hmbVideoAssetUid(item, catalogIndex);
    const order = Number(orderByUid.get(uid) || 0);
    const selectedAsset = order > 0;
    const role = hmbVideoAssetRole(item);
    const title = hmbVideoAssetTitle(item, catalogIndex);
    const source = videoSourceUrl(hmbVideoAssetPath(item));
    const blocked = !selectedAsset && selectionFull;
    const selectionLabel = selectedAsset ? tr.deselectVideoAsset : tr.selectVideoAsset;
    const media = source
      ? `<video class="video-asset-thumb-media" src="${escapeHtml(source)}" preload="metadata" muted playsinline draggable="false" aria-hidden="true"></video>`
      : `<span class="video-asset-thumb-fallback">VIDEO</span>`;
    return `<article class="video-asset-card${selectedAsset ? " selected" : ""}${blocked ? " selection-blocked" : ""}" data-video-asset-uid="${escapeHtml(uid)}" data-video-uid="${escapeHtml(uid)}" ${selectedAsset ? `data-selected-video-uid="${escapeHtml(uid)}"` : ""} data-selected-video-order="${order}" ${selectedAsset && !locked ? "draggable=\"true\"" : ""}>
      <div class="video-asset-thumb">
        ${media}
        <span class="video-asset-role">${escapeHtml(role)}</span>
        ${selectedAsset ? `<span class="selected-video-order">@video${order}</span>` : ""}
        <button type="button" class="video-asset-play" data-play-video-uid="${escapeHtml(uid)}" data-video-title="${escapeHtml(title)}" aria-label="${escapeHtml(`${title}: ${tr.playVideo}`)}" aria-pressed="false" ${locked ? "disabled" : ""}>▶</button>
      </div>
      <button type="button" class="video-asset-delete" data-delete-video-uid="${escapeHtml(uid)}" aria-label="${escapeHtml(`${title}: ${tr.deleteVideoAsset}`)}" ${locked ? "disabled" : ""}>×</button>
      <div class="video-asset-copy" data-toggle-video-uid="${escapeHtml(uid)}" role="button" tabindex="${blocked || locked ? "-1" : "0"}" aria-disabled="${blocked || locked ? "true" : "false"}" aria-label="${escapeHtml(`${title}: ${selectionLabel}`)}">
        <b class="video-asset-title" title="${escapeHtml(title)}">${escapeHtml(title)}</b>
        <div class="video-asset-details">${escapeHtml(hmbVideoAssetDetails(item))}</div>
      </div>
    </article>`;
  }).join("");
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
  const isolated = new Set();
  const stopControlPropagation = (event) => event?.stopPropagation?.();
  const isolatePointer = (element) => {
    if (!element || isolated.has(element)) return;
    isolated.add(element);
    // Keep native controls local, including wheel-bearing inputs and text
    // editors. Unlike the old broad panel guards, this leaves their surrounding
    // empty space available for canvas pan and zoom.
    element.classList?.add("nodrag", "nopan", "nowheel");
    ["pointerdown", "mousedown", "click", "dblclick"].forEach((eventName) => {
      element.addEventListener?.(eventName, stopControlPropagation);
    });
    cleanupList.push(() => {
      ["pointerdown", "mousedown", "click", "dblclick"].forEach((eventName) => {
        element.removeEventListener?.(eventName, stopControlPropagation);
      });
    });
  };
  interactionSelectors.forEach((selector) => {
    container.querySelectorAll(selector).forEach(isolatePointer);
  });
  const stopNodeDeleteShortcut = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  const stopInteriorNodeSelection = (event) => event.stopPropagation();
  container.addEventListener?.("keydown", stopNodeDeleteShortcut);
  container.addEventListener?.("pointerdown", stopInteriorNodeSelection);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
  }
  cleanupList.push(() => {
    container.removeEventListener?.("keydown", stopNodeDeleteShortcut);
    container.removeEventListener?.("pointerdown", stopInteriorNodeSelection);
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

function hmbSyncPickerElementAttributes(current, desired) {
  const desiredNames = new Set(Array.from(desired.attributes || []).map((attribute) => attribute.name));
  for (const attribute of Array.from(current.attributes || [])) {
    if (!desiredNames.has(attribute.name)) current.removeAttribute?.(attribute.name);
  }
  for (const attribute of Array.from(desired.attributes || [])) {
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

export default function HMBVideoPickerLibraryWidget(container, props) {
  if (!container) {
    return {
      cleanup() {},
      update() {},
    };
  }
  const retainedViewportVideo = container.querySelector?.("#picker-video") || null;
  const retainedViewportSource = clean(retainedViewportVideo?.getAttribute?.("src"));
  if (typeof container.__hmbVideoPickerCleanupProxy !== "function") {
    container.__hmbVideoPickerCleanupProxy = () => {
      const currentCleanup = container.__hmbVideoPickerCleanup;
      if (typeof currentCleanup === "function") currentCleanup();
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
      delete container.__hmbReadCommandPending;
      delete container.__hmbReadActionId;
      delete container.__hmbOriginalCommandPending;
      delete container.__hmbOriginalActionId;
      delete container.__hmbOriginalRequestedEnabled;
    };
  }
  const previousCleanup = container.__hmbVideoPickerCleanup;
  if (typeof previousCleanup === "function") previousCleanup();
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  const engineState = normalize(props?.value ?? props?.parameterValue ?? props?.defaultValue);
  const pendingState = container.__hmbPendingPickerState && typeof container.__hmbPendingPickerState === "object"
    ? normalize(container.__hmbPendingPickerState)
    : null;
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
  const state = pendingState && !engineIsNewer ? pendingState : engineState;
  // A newly mounted picker follows the established workflow palette, but it
  // does not publish or otherwise claim ownership of that palette.
  state.ui_theme = hmbReadSharedUiTheme(state.ui_theme);
  const originalPreviewChecked = !!state.original_enabled;
  const maskChecked = !!state.mask_enabled;
  const depthChecked = !!state.depth_enabled;
  const motionGuideChecked = !!state.motion_guide_enabled;
  const markerOptions = Array.isArray(state.marker_catalog?.options) && state.marker_catalog.options.length === 14
    ? state.marker_catalog.options
    : FALLBACK_MARKER_OPTIONS;
  const actorOptions = markerOptions.slice(0, 7);
  const objectOptions = markerOptions.slice(7, 14);
  container.__hmbAuthoritativePickerState = normalize(state);
  let resizeObserver = null;
  let activeCleanup = [];
  let disposed = false;
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    activeCleanup.forEach((fn) => { try { fn(); } catch (_error) {} });
    activeCleanup = [];
    if (resizeObserver) {
      try { resizeObserver.disconnect(); } catch (_error) {}
      resizeObserver = null;
    }
    container.removeAttribute?.("data-hmb-node-delete-protected");
    if (container.__hmbVideoPickerCleanup === cleanup) delete container.__hmbVideoPickerCleanup;
  };
  container.__hmbVideoPickerCleanup = cleanup;
  const nativeScenePath = nativeMayaScenePath(container);
  if (nativeScenePath) container.__hmbMayaSceneDraftPath = nativeScenePath;
  hmbApplyPickerInitialNodeSizeOnce(container);
  concealNativeMayaPicker(container);
  const effectiveMayaScenePath = clean(state.scene_request_path || state.scene_path);
  const mayaSceneDraftPath = clean(container.__hmbMayaSceneDraftPath || state.scene_draft_path || effectiveMayaScenePath);
  const buttonAvailability = pickerButtonAvailability(
    state,
    mayaSceneDraftPath,
    !!container.__hmbReadCommandPending,
    !!container.__hmbOriginalCommandPending,
  );
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
  const locked = runningOperation;
  const bindings = selectedBindings(state, 1);
  const frameMetadata = selectedFrameMetadata(state, video, selectedSlot);
  const selectedNode = state.outliner_nodes.find((item) => clean(item.full_path) === state.selected_outliner_path) || null;
  const tr = TEXT[state.language] || TEXT.en;
  const uiTheme = hmbReadSharedUiTheme(state.ui_theme);
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
    && clean(selectedSnapshot?.data_uri).startsWith("data:image/");
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
    ? `<img id="picker-snapshot-image" class="preview-image" src="${escapeHtml(selectedSnapshot.data_uri)}" alt="Colored snapshot"/>`
    : selectedVideoUrl
      ? `<video id="picker-video" class="preview-video" src="${escapeHtml(selectedVideoUrl)}" preload="metadata" playsinline></video>`
      : `<div class="viewport-empty"><div class="camera-frame"></div><b>${escapeHtml(tr.noPreviewTitle)}</b><span>${escapeHtml(tr.noPreviewBody)}</span></div>`;
  const viewportModeLabel = snapshotForViewport ? (tr.snapshot || "Snapshot") : (tr.preview || "Video");
  const snapshotDeleteEnabled = !runningOperation && !!selectedSnapshot;
  const activityRows = hmbActivityLogRowsForDisplay(state);
  const activityLogMarkup = hmbActivityLogHtml(state, tr);
  const videoAssetMarkup = videoAssetCardsHtml(state, tr, locked);
  const elapsedSeconds = runningOperation && Number(state.operation_started_at_ms || 0) > 0
    ? Math.max(0, (Date.now() - Number(state.operation_started_at_ms)) / 1000)
    : Number(state.last_operation_seconds || 0);
  const elapsedText = `${Math.floor(elapsedSeconds / 60).toString().padStart(2, "0")}:${Math.floor(elapsedSeconds % 60).toString().padStart(2, "0")}`;
  const pickerMarkup = `
    <style>
      .hmbvp-clip{width:100%;height:100%;min-width:0;min-height:0;max-width:none;max-height:none;overflow:hidden;background:#050812;box-sizing:border-box;display:flex;flex-direction:column;flex:1 1 auto}
      .hmbvp{--safe-x:16px;position:relative;width:100%;height:100%;min-width:0;min-height:960px;max-width:none;max-height:none;padding-left:var(--safe-x);padding-right:var(--safe-x);display:flex;flex-direction:column;flex:1 1 auto;background:#101820;color:#dbe4ec;border:1px solid rgba(148,163,184,.2);border-radius:11px;box-shadow:0 0 34px rgba(14,165,233,.12);overflow:hidden;resize:none;container-type:inline-size;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px}
      .hmbvp *{box-sizing:border-box;min-width:0}.hmbvp button,.hmbvp select,.hmbvp input,.hmbvp textarea{font:inherit;pointer-events:auto}.hmbvp button{color:inherit}.hmbvp .nodrag{touch-action:auto}.app-header{position:relative;z-index:30}.header-actions{position:relative;z-index:31}
      .settings-grid>span:nth-child(2){display:none}.settings-grid>.setting-select{grid-row:1;grid-column:2}.setting-select{width:100%;height:27px;padding:0 8px;border:1px solid #2c3b46;border-radius:2px;background:#202d36;color:#d7dfe4;cursor:pointer;outline:0}.setting-select:disabled{opacity:.5;cursor:not-allowed}
      .hmbvp button,.hmbvp input,.hmbvp select{transition:border-color 80ms ease,color 80ms ease}
      .hmbvp .side-section,.hmbvp .viewport-panel{transition-property:background-color,border-color,opacity;transition-duration:140ms;transition-timing-function:ease}
      @media (prefers-reduced-motion:reduce){.hmbvp *{animation:none!important;transition:none!important}}
      .snapshot-toolbar{position:relative;z-index:20;min-height:42px;display:grid;grid-template-columns:minmax(96px,4fr) max-content minmax(145px,6fr);align-items:center;gap:7px;padding:6px 10px;border-bottom:1px solid #2a353e;background:#151f27}.snapshot-toolbar>button,.video-controls button{height:29px;padding:0 11px;border:1px solid #344550;border-radius:3px;background:#1a2833;color:#e4ebef;cursor:pointer}.snapshot-toolbar>button{min-width:0;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:27px}.snapshot-toolbar #create-snapshot{width:auto;min-width:0;background:#1c3c62;border-color:#2c5b8d}.snapshot-toolbar #delete-snapshot{width:max-content;min-width:124px;background:#4d2328;border-color:#774047}.snapshot-toolbar .output-camera-inline{width:100%;height:29px;min-width:0;min-height:29px;margin-left:0;display:grid;grid-template-columns:max-content minmax(0,1fr);align-items:center;overflow:hidden}.snapshot-toolbar .output-camera-label{white-space:nowrap;line-height:29px}.snapshot-toolbar .camera-fixed,.snapshot-toolbar .camera-dropdown{width:100%;height:29px;min-width:0;min-height:29px;max-height:29px;align-self:center;overflow:hidden}.snapshot-toolbar>button:disabled,.video-controls button:disabled{opacity:.4;cursor:not-allowed}.preview-video{display:block;width:100%;height:100%;object-fit:contain;background:#10161b}.video-seekbar{height:28px;flex:0 0 28px;display:flex;align-items:center;padding:4px 12px;background:#111a21;border-top:1px solid #2b363e}.video-seekbar input{width:100%;height:18px;margin:0;accent-color:#4c8fd7;cursor:pointer}.video-seekbar input:disabled{opacity:.35;cursor:not-allowed}.video-controls{height:44px;flex:0 0 44px;display:flex;align-items:center;justify-content:center;gap:6px;padding:6px 10px;background:#111a21}.video-controls .transport-button{width:38px;padding:0;font-weight:800}.frame-number-label{display:flex;align-items:center;gap:6px;margin-left:6px;color:#cbd5dc;font-size:10px}.frame-number-label input{width:92px;height:29px;padding:0 7px;border:1px solid #344550;border-radius:3px;background:#0d151c;color:#fff;font-variant-numeric:tabular-nums}.frame-info-strip{height:28px;flex:0 0 28px;display:flex;align-items:center;justify-content:center;gap:16px;padding:0 10px;border-top:1px solid #26323b;background:#0d151c;color:#7f8e99;font-size:9px;font-weight:800;white-space:nowrap}.frame-info-strip b{margin-left:4px;color:#e5edf2;font-variant-numeric:tabular-nums}
      .app-header{height:68px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 16px;background:linear-gradient(180deg,#121c25,#101820);border-bottom:1px solid #26313a}
      .brand{display:flex;align-items:center;gap:10px;min-width:0;flex:1 1 auto;font-size:19px;font-weight:700;color:#f3f6f8;white-space:nowrap;overflow:hidden}.brand>span:last-child{overflow:hidden;text-overflow:ellipsis}.brand-mark{width:30px;height:30px;flex:0 0 30px;border:2px solid #dfe7ed;transform:rotate(30deg);display:grid;place-items:center}.brand-mark:after{content:"H";transform:rotate(-30deg);font-size:13px}.header-actions{display:flex;align-items:center;justify-content:flex-end;flex:0 0 auto;gap:7px}.header-actions button{height:30px;border:1px solid #33414d;background:#18232d;border-radius:3px;padding:0 10px;cursor:pointer}.header-actions .read-button{background:#1c3c62;border-color:#2c5b8d}.header-actions .stop-button{background:#4d2328;border-color:#774047}.header-actions .language-button{min-width:58px}.header-actions button:disabled{opacity:.4;cursor:not-allowed}
      .scene-load-bar{height:36px;flex:0 0 36px;display:grid;grid-template-columns:auto minmax(120px,1fr) auto auto max-content max-content max-content max-content;align-items:center;gap:6px;padding:3px 10px;background:#111a22;border-bottom:1px solid #293640}.scene-load-label{font-size:10px;font-weight:800;color:#aebbc4}.scene-path-input{height:25px;min-width:0;padding:0 9px;border:1px solid #33424e;border-radius:3px;background:#0d151c;color:#e2e8ed}.scene-path-input:focus{outline:0;border-color:#5797d1}.scene-load-bar button{height:25px;padding:0 10px;border:1px solid #3b4b57;border-radius:3px;background:#1a2833;color:#e1e8ed;cursor:pointer}.scene-load-bar .load-scene-button{background:#285b91;border-color:#346ba4;font-weight:800}.scene-load-bar button:disabled,.scene-path-input:disabled{opacity:.4;cursor:not-allowed}
      .main-grid{display:grid;grid-template-columns:minmax(230px,24%) minmax(420px,1fr) minmax(285px,26%);align-items:stretch;gap:8px;padding:8px;flex:1;min-height:0;overflow:auto;background:#0e161d}
      .center-stack{min-width:0;min-height:0;display:flex;flex-direction:column;gap:8px;overflow:hidden}.center-stack>.viewport-panel{flex:3 1 0}.center-stack>.activity-section{flex:1 1 0;min-height:150px}
      .panel{min-width:0;min-height:0;background:#151f27;border:1px solid #2c3740;border-radius:10px;display:flex;flex-direction:column;overflow:hidden}.panel-title{height:34px;display:flex;align-items:center;padding:0 10px;border-bottom:1px solid #2b3740;background:#18232b;font-weight:700;color:#edf2f5}.panel-title.viewport-title{justify-content:center;text-align:center}.panel-title small{margin-left:5px;color:#aeb9c1;font-weight:500}.panel-title .grow{flex:1}
      .panel-resize-handle{position:relative;flex:0 0 10px;min-height:10px;height:10px;border-top:1px solid #2c3740;cursor:ns-resize;background:linear-gradient(90deg,transparent,rgba(148,163,184,.16),transparent);touch-action:none;user-select:none}.panel-resize-handle:before{content:"";position:absolute;left:50%;top:3px;width:44px;height:3px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.48)}.panel-resize-handle:hover:before{background:#fff}
      .outliner-palette{padding:8px;border-bottom:1px solid #29343d;background:#111a21}.outliner-toolbar{display:flex;gap:6px;padding:8px;border-bottom:1px solid #29343d}.search-input{width:100%;height:29px;background:#101820;border:1px solid #2b3944;color:#dce5eb;padding:0 9px;border-radius:3px}.column-head{height:28px;display:flex;align-items:center;padding:0 8px;border-bottom:1px solid #2b353d;color:#b7c1c9;font-size:11px}.outliner-scroll{flex:1;min-height:0;overflow:auto;padding:3px}.outliner-list{display:flex;flex-direction:column}.outliner-row{display:flex;align-items:center;min-height:29px;padding-right:5px;color:#d2d9df;border-radius:2px;cursor:pointer}.outliner-row:hover{background:#1c2a35}.outliner-row.selected{background:#25517e}.outliner-row.output-off{opacity:.48}.tree-toggle{width:19px;height:25px;border:0;background:transparent;padding:0;color:#a8b4bd;cursor:pointer}.tree-toggle.leaf{cursor:default}.eye-toggle{width:25px;height:25px;display:grid;place-items:center;border:0;background:transparent;padding:4px;cursor:pointer}.eye-toggle svg{width:17px;height:17px;fill:none;stroke:#68d26d;stroke-width:1.8}.eye-toggle.on svg circle{fill:#68d26d;stroke:none}.eye-toggle.off svg{stroke:#dd5c60}.node-icon{font-size:9px;color:#bcc6ce;margin-right:5px}.group-name{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.ref-tag{font-size:9px;border:1px solid #5c6b76;border-radius:3px;padding:1px 4px;margin-right:5px;color:#adb8c0}.assigned-chip{width:14px;height:14px;border:1px solid rgba(255,255,255,.4);border-radius:2px;margin-right:6px}
      .viewport-panel{background:#131c23}.output-scope-inline{position:relative;z-index:20;min-height:38px;display:flex;align-items:center;justify-content:flex-start;gap:12px;padding:4px 10px;border-bottom:1px solid #2a353e;background:#151f27;white-space:nowrap;overflow:visible}.output-scope-title{font-size:10px;font-weight:800;color:#d7dfe5;flex:0 0 auto;text-align:center}.output-scope-options{display:flex;align-items:center;justify-content:flex-start;gap:14px;min-width:max-content}.output-scope-option{display:flex;align-items:center;gap:5px;font-size:10px;color:#d7dfe5;cursor:pointer}.output-scope-option input{margin:0;accent-color:#4c8fd7}.output-scope-option span{white-space:nowrap}.output-camera-inline{display:flex;align-items:center;gap:7px;margin-left:auto;flex:0 0 auto}.output-camera-label{font-size:10px;font-weight:800;color:#d7dfe5}.camera-fixed,.camera-dropdown{position:relative;min-width:200px}.camera-fixed{height:28px;display:flex;align-items:center;gap:7px;padding:0 9px;background:#111a21;border:1px solid #33414c;border-radius:3px}.camera-fixed b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.camera-fixed em{font-size:9px;color:#79aee4;font-style:normal}.camera-fixed.disabled{opacity:.5}.camera-dropdown summary{list-style:none;height:29px;display:flex;align-items:center;gap:7px;padding:0 9px;background:#111a21;border:1px solid #33414c;border-radius:3px;cursor:pointer}.camera-dropdown summary::-webkit-details-marker{display:none}.camera-dropdown summary b{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.camera-menu{position:absolute;z-index:60;left:0;right:0;top:32px;max-height:240px;overflow:auto;background:#17232c;border:1px solid #3b4a56;box-shadow:0 8px 18px rgba(0,0,0,.5);padding:4px}.camera-menu button{width:100%;display:flex;justify-content:space-between;align-items:center;border:0;background:transparent;padding:8px;text-align:left;cursor:pointer}.camera-menu button:hover,.camera-menu button.active{background:#24415e}.camera-menu button span{font-size:9px;color:#9dacb6}.viewport-stage{position:relative;flex:1;min-height:0;background:radial-gradient(circle at 50% 44%,#5a5a59 0,#373b3d 36%,#20282d 80%);display:flex;align-items:center;justify-content:center;overflow:hidden}.preview-image{width:100%;height:100%;object-fit:contain;background:#232a2e}.viewport-empty{position:relative;width:82%;height:76%;border:1px solid #3fa578;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#b5c0c8;text-align:center;gap:7px;background:linear-gradient(180deg,rgba(255,255,255,.03),rgba(0,0,0,.08))}.viewport-empty .camera-frame{position:absolute;inset:5% 6%;border:1px solid rgba(65,173,124,.8)}.viewport-empty b,.viewport-empty span{position:relative;z-index:2}.viewport-empty span{max-width:420px;color:#93a0aa}.preview-nav{height:42px;flex:0 0 42px;border-top:1px solid #2b363e;background:#111a21;display:grid;grid-template-columns:38px minmax(0,1fr) 38px;align-items:center;gap:8px;padding:6px 10px}.preview-nav button{height:28px;border:1px solid #303e49;background:#1b2730;border-radius:3px;cursor:pointer;font-weight:800}.preview-nav button:disabled{opacity:.35;cursor:not-allowed}.preview-frame-label{min-width:0;text-align:center;color:#aeb9c1;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .right-stack{display:flex;flex-direction:column;gap:8px;min-height:0;overflow:hidden;background:transparent}.side-section{position:relative;flex:0 0 auto;min-height:96px;background:#151f27;border:1px solid #2c3740;border-radius:10px;display:flex;flex-direction:column;overflow:hidden}.playblast-settings-section{min-height:150px}.video-assets-section{min-height:240px;flex:1 1 0}.section-head{height:34px;flex:0 0 34px;display:flex;align-items:center;padding:0 10px;border-bottom:1px solid #2c3740;background:#18232b;font-weight:700}.section-head .grow{flex:1}.section-head .section-tools{margin-left:auto;display:flex;align-items:center;gap:5px}.video-selected-count{margin-left:auto;color:#aeb9c1;font-size:10px;font-variant-numeric:tabular-nums}.import-video-button{height:24px;margin-left:8px;padding:0 8px;border:1px solid #35434e;border-radius:6px;background:#111a21;color:#dce5eb;cursor:pointer;font-size:9px}.activity-section{min-height:150px}.activity-section .section-head{justify-content:flex-start}.activity-clear{height:23px;border:1px solid #35434e;background:#111a21;color:#c7d0d7;border-radius:7px;padding:0 8px;cursor:pointer;font-size:9px}.activity-elapsed{min-width:74px;text-align:right;font-size:9px;color:#aeb9c1;font-variant-numeric:tabular-nums}.activity-body{flex:1;min-width:0;min-height:0;overflow:hidden;padding:0;background:#0e161d;contain:layout paint}.activity-log-view{display:block;width:100%;height:100%;min-width:0;min-height:0;max-width:100%;margin:0;padding:6px 8px;overflow-x:auto;overflow-y:auto;scrollbar-gutter:stable both-edges;color:#cbd5dc;background:transparent;font:10px/1.5 ui-monospace,SFMono-Regular,Consolas,"Liberation Mono",monospace;user-select:text;-webkit-user-select:text;pointer-events:auto}.activity-log-row{display:grid;grid-template-columns:68px 58px max-content;align-items:center;width:max-content;min-width:100%;height:18px;min-height:18px;max-height:18px;overflow:visible;white-space:nowrap;color:#cbd5dc}.activity-log-time{overflow:hidden;color:#7f8e99;font-variant-numeric:tabular-nums}.activity-log-level{overflow:hidden;font-weight:800}.activity-log-message{display:block;min-width:max-content;max-width:none;overflow:visible;text-overflow:clip;white-space:nowrap}.activity-log-row[data-level="ERROR"]{color:#fb7185}.activity-log-row[data-level="ERROR"] .activity-log-time{color:#fb7185}.activity-log-row[data-level="WARNING"]{color:#fbbf24}.activity-log-row[data-level="WARNING"] .activity-log-time{color:#d6a51d}.activity-log-row[data-level="SUCCESS"]{color:#4ade80}.activity-log-row[data-level="SUCCESS"] .activity-log-time{color:#3bbd6b}.activity-log-empty{padding:4px 0;color:#7f8e99;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.section-resize-handle{position:relative;left:auto;right:auto;bottom:auto;flex:0 0 10px;min-height:10px;height:10px;border-top:1px solid #2c3740;cursor:ns-resize;background:linear-gradient(90deg,transparent,rgba(148,163,184,.16),transparent);touch-action:none}.section-resize-handle:before{content:"";position:absolute;left:50%;top:3px;width:44px;height:3px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.48)}.section-resize-handle:hover:before{background:#fff}.section-body{padding:9px}.side-section>.section-body{flex:1;min-height:0;overflow:auto;padding-bottom:9px}.palette-head{display:flex;flex-direction:column;align-items:stretch;gap:7px;min-width:0}.palette-group{display:grid;grid-template-columns:minmax(82px,92px) minmax(0,1fr);align-items:center;gap:6px;min-width:0}.palette-label{height:26px;min-width:0;display:flex;align-items:center;padding:0 7px;background:#26343f;border:1px solid #364652;border-radius:7px;color:#d5dde3;white-space:nowrap;font-size:10px}.palette-grid{display:flex;gap:4px;flex-wrap:wrap;min-width:0}.palette-button{width:20px;height:20px;border:2px solid transparent;border-radius:3px;cursor:pointer;padding:0}.palette-button.active{border-color:#f4f7f9;box-shadow:0 0 0 1px #111}.video-assets-body{flex:1;min-height:0;overflow:auto;padding:8px}.video-asset-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:8px}.video-assets-empty{grid-column:1/-1;min-height:130px;display:grid;place-items:center;padding:16px;border:1px dashed #35434e;border-radius:8px;color:#8998a3;text-align:center}.video-asset-card{position:relative;overflow:hidden;border:1px solid var(--hmb-line-soft,#344550);border-radius:9px;background:linear-gradient(145deg,rgba(255,255,255,.025),rgba(255,255,255,.006)),var(--hmb-field,#101820);transition:border-color 100ms ease,box-shadow 100ms ease}.video-asset-card[draggable="true"]{cursor:grab}.video-asset-card.dragging{opacity:.5;transform:scale(.985)}.video-asset-card.drop-target{border-color:rgb(var(--selection-rgb));box-shadow:0 0 0 1px rgba(var(--selection-rgb),.35)}.video-asset-card.selected{border-color:rgb(var(--selection-rgb));background:linear-gradient(145deg,rgba(var(--selection-rgb),.12),var(--selection-card));box-shadow:0 0 0 1px rgba(var(--selection-rgb),.16),0 0 18px rgba(var(--selection-rgb),.12)}.video-asset-thumb{position:relative;aspect-ratio:16/9;overflow:hidden;background:#080d14}.video-asset-thumb-media{width:100%;height:100%;object-fit:cover;pointer-events:none}.video-asset-thumb-fallback{position:absolute;inset:0;display:grid;place-items:center;color:#667684;font-size:10px;font-weight:800}.video-asset-role,.selected-video-order{position:absolute;top:7px;padding:3px 6px;border-radius:5px;background:rgba(5,8,18,.82);color:#fff;font-size:9px;font-weight:800}.video-asset-role{left:7px}.selected-video-order{right:7px;color:var(--selection-strong)}.video-asset-play{position:absolute;left:50%;top:50%;width:38px;height:38px;transform:translate(-50%,-50%);display:grid;place-items:center;border:1px solid rgba(255,255,255,.30);border-radius:50%;background:rgba(5,8,18,.76);color:#fff;cursor:pointer}.video-asset-delete{position:absolute;right:7px;bottom:7px;width:26px;height:26px;border:1px solid rgba(251,113,133,.45);border-radius:6px;background:rgba(76,5,25,.80);color:#ffe4e8;cursor:pointer}.video-asset-copy{padding:8px}.video-asset-copy>b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:#edf2f5}.video-asset-footer{display:flex;align-items:center;gap:6px;margin-top:6px}.video-asset-footer>span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8f9da7;font-size:9px}.video-asset-footer button,.video-order-actions button{height:25px;padding:0 7px;border:1px solid #35434e;border-radius:6px;background:#111a21;color:#dce5eb;cursor:pointer;font-size:9px}.video-order-actions{display:flex;justify-content:flex-end;gap:4px;margin-top:5px}.video-order-hint{flex:0 0 auto;padding:5px 8px;border-top:1px solid #2c3740;color:#7f8e99;font-size:9px;text-align:center}
      .radio-list{display:flex;flex-direction:column;gap:9px}.radio-row{display:grid;grid-template-columns:18px 1fr;align-items:start;cursor:pointer}.radio-row input{margin-top:3px;accent-color:#4c8fd7}.radio-row b{display:block;font-size:11px}.radio-row span{display:block;font-size:9px;color:#8f9ca6;margin-top:2px}.settings-action{position:sticky;top:0;z-index:4;padding:0 0 8px;background:linear-gradient(180deg,var(--hmb-panel-top,#151f27) 82%,rgba(21,31,39,0));}.settings-action .setting-checks{margin-top:7px}.settings-grid{display:grid;grid-template-columns:78px 1fr;gap:7px 8px;align-items:center;font-size:10px}.setting-value{height:27px;display:flex;align-items:center;padding:0 8px;background:#202d36;border:1px solid #2c3b46;color:#d7dfe4;border-radius:2px}.setting-value.split{justify-content:space-between}.setting-checks{display:flex;gap:12px;margin-top:0;font-size:9px;color:#aab6bf}.setting-checks label{display:flex;align-items:center;gap:5px}.setting-checks input{accent-color:#4c8fd7}.generate-button{width:100%;height:34px;margin:0;border:1px solid #346ba4;background:#285b91;color:#fff;font-weight:700;cursor:pointer}.generate-button:disabled,.palette-button:disabled{opacity:.4;cursor:not-allowed}
      .empty-pane{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;color:#8998a3;text-align:center;padding:20px}.empty-pane b{color:#c9d2d8}
      .video-asset-grid{grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}
      .video-asset-thumb{cursor:pointer;outline:0}.video-asset-thumb:focus-visible{box-shadow:inset 0 0 0 2px var(--hmb-focus),inset 0 0 18px var(--hmb-glow)}.video-asset-thumb.is-playing .video-asset-play{border-color:var(--hmb-focus);background:rgba(5,8,18,.88);box-shadow:0 0 14px var(--hmb-glow)}.video-asset-play{z-index:3;pointer-events:none;font-size:15px;font-weight:900}.video-asset-delete{top:7px;right:7px;bottom:auto;z-index:5}.selected-video-order{top:auto;right:7px;bottom:7px}.video-asset-copy{display:grid;gap:3px;padding:7px 8px 8px}.video-asset-title{display:block;width:100%;min-width:0;padding:0;border:0;background:transparent;color:#edf2f5;font:inherit;font-size:11px;font-weight:800;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.video-asset-title:not(:disabled):hover{color:var(--selection-strong)}.video-asset-title:disabled{opacity:.48;cursor:not-allowed}.video-asset-details{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8f9da7;font-size:9px}.import-video-button{display:inline-flex;align-items:center;justify-content:center;gap:5px;font-weight:800}.import-video-icon{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
      .video-asset-card.selected{border-width:2px;border-color:rgb(var(--selection-rgb));box-shadow:0 0 0 2px rgba(var(--selection-rgb),.82),0 0 28px rgba(var(--selection-rgb),.62),inset 0 0 16px rgba(var(--selection-rgb),.12)}.video-asset-copy{min-height:52px;cursor:pointer;outline:0}.video-asset-copy:not([aria-disabled="true"]):hover{background:rgba(var(--selection-rgb),.12)}.video-asset-copy:focus-visible{background:rgba(var(--selection-rgb),.14);box-shadow:inset 0 0 0 2px var(--hmb-focus)}.video-asset-copy[aria-disabled="true"]{cursor:not-allowed;opacity:.48}.video-asset-title,.video-asset-details{pointer-events:none}.video-asset-title{cursor:inherit}
      .video-asset-thumb{cursor:inherit}.video-asset-play{pointer-events:auto}.video-asset-role,.selected-video-order{pointer-events:none}
      @container(max-width:1250px){.main-grid{grid-template-columns:280px minmax(420px,1fr)}.right-stack{grid-column:1/-1;display:grid;grid-template-columns:minmax(240px,.7fr) minmax(0,1.3fr);overflow:visible}}
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
      .hmbvp[data-theme="P"] .brand-mark{border-color:rgba(34,211,238,.70);background:rgba(8,145,178,.12);color:#22d3ee;box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 13px rgba(34,211,238,.10)}
      .hmbvp[data-theme="T"] .brand-mark{border-color:rgba(56,189,248,.70);background:rgba(37,99,235,.16);color:#38bdf8;box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 13px rgba(56,189,248,.11)}
      .hmbvp[data-theme] .panel-title,.hmbvp[data-theme] .section-head{color:var(--hmb-text);font-weight:800;letter-spacing:.025em}
      .hmbvp[data-theme] .panel-title small,.hmbvp[data-theme] .column-head,.hmbvp[data-theme] .camera-fixed span,.hmbvp[data-theme] .camera-dropdown summary span,.hmbvp[data-theme] .camera-menu button span,.hmbvp[data-theme] .preview-frame-label,.hmbvp[data-theme] .radio-row span,.hmbvp[data-theme] .setting-checks,.hmbvp[data-theme] .scene-load-label,.hmbvp[data-theme] .frame-number-label,.hmbvp[data-theme] .video-selected-count,.hmbvp[data-theme] .video-order-hint{color:var(--hmb-muted)}
      .hmbvp[data-theme] .scene-load-bar,.hmbvp[data-theme] .snapshot-toolbar,.hmbvp[data-theme] .video-seekbar,.hmbvp[data-theme] .video-controls,.hmbvp[data-theme] .frame-info-strip{background:linear-gradient(180deg,rgba(255,255,255,.022),rgba(255,255,255,.004)),var(--hmb-field);border-color:var(--hmb-line-soft)}
      .hmbvp[data-theme] .activity-body{background:var(--hmb-deep)}
      .hmbvp[data-theme] .activity-log-view{color:var(--hmb-text)}
      .hmbvp[data-theme] .scene-path-input,.hmbvp[data-theme] .scene-load-bar button,.hmbvp[data-theme] .original-preview-toggle,.hmbvp[data-theme] .mask-playblast-toggle,.hmbvp[data-theme] .depth-playblast-toggle,.hmbvp[data-theme] .motion-guide-toggle,.hmbvp[data-theme] .setting-select,.hmbvp[data-theme] .video-controls button,.hmbvp[data-theme] .frame-number-label input,.hmbvp[data-theme] .snapshot-toolbar>button,.hmbvp[data-theme] .header-actions button,.hmbvp[data-theme] .activity-clear,.hmbvp[data-theme] .import-video-button,.hmbvp[data-theme] .search-input,.hmbvp[data-theme] .camera-fixed,.hmbvp[data-theme] .camera-dropdown summary,.hmbvp[data-theme] .palette-label,.hmbvp[data-theme] .setting-value,.hmbvp[data-theme] .preview-nav button,.hmbvp[data-theme] .video-asset-footer button,.hmbvp[data-theme] .video-order-actions button{border-color:var(--hmb-line-soft);border-radius:7px;background:linear-gradient(180deg,rgba(255,255,255,.032),rgba(255,255,255,.006)),var(--hmb-field);color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.018)}
      .hmbvp[data-theme] button{letter-spacing:.01em}
      .hmbvp[data-theme] .scene-load-bar .load-scene-button,.hmbvp[data-theme] .snapshot-toolbar #create-snapshot,.hmbvp[data-theme] .generate-button,.hmbvp[data-theme] .import-video-button{border-color:var(--hmb-primary-line);border-radius:7px;background:linear-gradient(180deg,var(--hmb-primary-top),var(--hmb-primary-bottom));color:#fff;box-shadow:0 0 14px var(--hmb-glow),inset 0 1px 0 rgba(255,255,255,.10)}
      .hmbvp[data-theme] .header-actions .stop-button,.hmbvp[data-theme] .snapshot-toolbar #delete-snapshot,.hmbvp[data-theme] .video-asset-delete{border-color:rgba(251,113,133,.50);background:linear-gradient(180deg,rgba(159,18,57,.74),rgba(76,5,25,.84));color:#ffe4e8;box-shadow:inset 0 1px 0 rgba(255,255,255,.07)}
      .hmbvp[data-theme] .scene-path-input:focus,.hmbvp[data-theme] .setting-select:focus,.hmbvp[data-theme] .frame-number-label input:focus,.hmbvp[data-theme] .search-input:focus,.hmbvp[data-theme] .camera-dropdown summary:focus-visible,.hmbvp[data-theme] button:focus-visible{outline:0;border-color:var(--hmb-focus);box-shadow:0 0 0 1px var(--hmb-focus),0 0 14px var(--hmb-glow)}
      .hmbvp[data-theme] .scene-load-bar button:not(:disabled):hover,.hmbvp[data-theme] .video-controls button:not(:disabled):hover,.hmbvp[data-theme] .snapshot-toolbar>button:not(:disabled):hover,.hmbvp[data-theme] .header-actions button:not(:disabled):hover,.hmbvp[data-theme] .preview-nav button:not(:disabled):hover,.hmbvp[data-theme] .activity-clear:not(:disabled):hover,.hmbvp[data-theme] .import-video-button:not(:disabled):hover,.hmbvp[data-theme] .video-asset-footer button:not(:disabled):hover,.hmbvp[data-theme] .video-order-actions button:not(:disabled):hover{border-color:var(--hmb-focus);color:#fff;box-shadow:0 0 12px var(--hmb-glow)}
      .hmbvp[data-theme] .outliner-row.selected{background:var(--hmb-selected);box-shadow:inset 2px 0 0 var(--hmb-accent-2),0 0 12px var(--hmb-glow)}
      .hmbvp[data-theme] .outliner-row:hover{background:var(--hmb-hover)}
      .hmbvp[data-theme] .video-seekbar input,.hmbvp[data-theme] .output-scope-option input,.hmbvp[data-theme] .original-preview-toggle input,.hmbvp[data-theme] .mask-playblast-toggle input,.hmbvp[data-theme] .depth-playblast-toggle input,.hmbvp[data-theme] .motion-guide-toggle input,.hmbvp[data-theme] .radio-row input,.hmbvp[data-theme] .setting-checks input{accent-color:var(--hmb-accent)}
      .hmbvp[data-theme] .viewport-empty{border-color:var(--hmb-focus);box-shadow:inset 0 0 0 1px rgba(255,255,255,.018),0 0 18px var(--hmb-glow)}
      .hmbvp[data-theme] .viewport-empty .camera-frame{border-color:color-mix(in srgb,var(--hmb-focus) 58%,transparent)}
      .hmbvp[data-theme] .panel-resize-handle,.hmbvp[data-theme] .section-resize-handle{border-color:var(--hmb-line-soft);background:linear-gradient(90deg,transparent,var(--hmb-line-soft),transparent)}
      .hmbvp[data-theme] .panel-resize-handle:before,.hmbvp[data-theme] .section-resize-handle:before{background:var(--hmb-muted);opacity:.48}
      .hmbvp[data-theme] .video-assets-section>.section-resize-handle{border-top-color:transparent;background:transparent}.hmbvp[data-theme] .video-assets-section>.section-resize-handle:before{display:none}
      </style>
    <div class="hmbvp-clip nodrag"><div class="hmbvp" data-theme="${uiTheme}" data-state-revision="${Number(state.state_revision || 0)}">
      <header class="app-header">
        <div class="brand"><span class="brand-mark"></span><span>HMBVideoPickerLibrary</span></div>
        <div class="header-actions">
          <button type="button" class="language-button" id="language-toggle">${escapeHtml(tr.language)}</button>
          <button type="button" class="stop-button" id="stop-read" ${!stopReady ? "disabled" : ""}>${escapeHtml(tr.stop)}</button>
        </div>
      </header>
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
              <div class="palette-group"><div class="palette-label">${escapeHtml(tr.presetActor)}</div><div class="palette-grid" data-palette-kind="actor">${actorOptions.map((name) => `<button type="button" class="palette-button ${state.selected_color === name ? "active" : ""}" data-color="${escapeHtml(name)}" title="${escapeHtml(name)}" aria-label="${escapeHtml(`${tr.presetActor}: ${name}`)}" style="${hmbPickerColorStyle(name, state.marker_catalog)}" ${locked || !selectedNode ? "disabled" : ""}></button>`).join("")}</div></div>
              <div class="palette-group"><div class="palette-label">${escapeHtml(tr.presetObject)}</div><div class="palette-grid" data-palette-kind="object">${objectOptions.map((name) => `<button type="button" class="palette-button ${state.selected_color === name ? "active" : ""}" data-color="${escapeHtml(name)}" title="${escapeHtml(name)}" aria-label="${escapeHtml(`${tr.presetObject}: ${name}`)}" style="${hmbPickerColorStyle(name, state.marker_catalog)}" ${locked || !selectedNode ? "disabled" : ""}></button>`).join("")}</div></div>
            </div>
          </div>
          <div class="outliner-toolbar"><input id="outliner-search" class="search-input" value="${escapeHtml(state.outliner_search)}" placeholder="${escapeHtml(tr.search)}" aria-label="${escapeHtml(tr.search)}"/></div>
          <div class="column-head"><span>${escapeHtml(tr.name)}</span></div>
          <div class="outliner-scroll">${outlinerHtml(state, bindings, tr)}</div>
        </section>
        <div class="center-stack">
        <section class="panel viewport-panel" style="${hmbFlexPanelHeightStyle(state.viewport_panel_height, HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT)}">
          <div class="snapshot-toolbar"><button type="button" id="create-snapshot" ${!buttonAvailability.snapshotEnabled ? "disabled" : ""}>${escapeHtml(tr.snapshot || "Snapshot")}</button><button type="button" id="delete-snapshot" ${!snapshotDeleteEnabled ? "disabled" : ""}>${escapeHtml(tr.deleteSnapshot || "Delete Snapshot")}</button><div class="output-camera-inline"><span class="output-camera-label">${escapeHtml(tr.cameraPrefix)} :</span>${cameraControlHtml(state, tr, runningOperation)}</div></div>
          <div class="panel-title viewport-title">${escapeHtml(tr.viewport)} <small>(${escapeHtml(viewportModeLabel)})</small></div>
          <div class="viewport-stage">${viewportMediaHtml}</div>
          <div class="video-seekbar"><input type="range" id="video-seek" min="${frameStart}" max="${frameEnd}" step="1" value="${Math.round(initialViewportFrame)}" aria-label="Video timeline" ${!selectedVideoUrl || snapshotForViewport || !hasFrameRange ? "disabled" : ""}/></div>
          <div class="video-controls"><button type="button" class="transport-button" id="snapshot-prev" title="${escapeHtml(tr.previousSnapshot || "Previous snapshot")}" aria-label="${escapeHtml(tr.previousSnapshot || "Previous snapshot")}" ${snapshotHistory.length ? "" : "disabled"}>◀</button><button type="button" class="transport-button" id="video-play-toggle" title="${escapeHtml(tr.playVideo || "Play")}" aria-label="${escapeHtml(tr.playVideo || "Play")}" ${selectedVideoUrl ? "" : "disabled"}>▶</button><button type="button" class="transport-button" id="snapshot-next" title="${escapeHtml(tr.nextSnapshot || "Next snapshot")}" aria-label="${escapeHtml(tr.nextSnapshot || "Next snapshot")}" ${snapshotHistory.length ? "" : "disabled"}>▶</button><label class="frame-number-label">${escapeHtml(tr.frameLabel)} <input type="number" id="video-frame-number" min="${frameStart}" max="${frameEnd}" step="1" value="${Math.round(initialViewportFrame)}" aria-label="${escapeHtml(tr.frameLabel)}" ${!hasFrameRange || snapshotForViewport ? "disabled" : ""}/></label></div>
          <div class="frame-info-strip"><span>FRAME <b id="frame-info-frame">${Math.round(initialViewportFrame)} / ${frameEnd}</b></span><span>TIME <b id="frame-info-time">${escapeHtml(initialTimecode)}</b></span><span>FPS <b>${escapeHtml(frameInfoFps || "—")}</b></span><span>RANGE <b>${frameStart}–${frameEnd}</b></span></div>
          <div class="panel-resize-handle nodrag" data-resize-panel="viewport" title="${escapeHtml(tr.resizeSection)}"></div>
        </section>
          <section class="side-section activity-section preview-activity-section" data-section-key="log"><div class="section-head"><span class="grow">${escapeHtml(tr.activityLog)}</span><div class="section-tools"><span class="activity-elapsed" id="activity-elapsed" data-start-ms="${Number(state.operation_started_at_ms || 0)}">${escapeHtml(tr.elapsed)} ${elapsedText}</span><button type="button" class="activity-clear" id="clear-activity-log" ${activityRows.length ? "" : "disabled"}>${escapeHtml(tr.clearLog)}</button></div></div><div class="activity-body" id="activity-log-body"><div id="activity-log-view" class="activity-log-view" role="log" aria-live="polite" aria-label="${escapeHtml(tr.activityLog)}">${activityLogMarkup}</div></div></section>
        </div>
        <aside class="right-stack">
          <section class="side-section playblast-settings-section" data-section-key="settings" style="${hmbSectionHeightStyle(rightSectionHeights, "settings")}"><div class="section-head">${escapeHtml(tr.playblastSettings)}</div><div class="section-body">
            <div class="settings-action"><button type="button" class="generate-button" id="run-video" ${!buttonAvailability.playblastEnabled ? "disabled" : ""}>▶&nbsp; ${escapeHtml(tr.generate)}</button></div>
            <div class="settings-grid">
              <span>${escapeHtml(tr.resolution)}</span><span class="setting-value">${Number(state.output_width || 1280)} × ${Number(state.output_height || 720)}</span>
              <span>${escapeHtml(tr.frameRange)}</span><span class="setting-value split"><b>${escapeHtml(frameStartText)}</b><span>–</span><b>${escapeHtml(frameEndText)}</b></span>
              <select id="playblast-resolution" class="setting-select" ${runningOperation ? "disabled" : ""}>${HMB_PLAYBLAST_RESOLUTIONS.map((item) => `<option value="${item.value}" ${item.width === Number(state.output_width) && item.height === Number(state.output_height) ? "selected" : ""}>${item.label}</option>`).join("")}</select>
              <span>${escapeHtml(tr.fps)}</span><span class="setting-value">${escapeHtml(fpsText)}</span>
              <span>${escapeHtml(tr.format)}</span><span class="setting-value">MPEG-4 / H.264</span>
              <span>${escapeHtml(tr.mayaVersion)}</span><span class="setting-value">${escapeHtml(state.maya_version ? `Maya ${state.maya_version}` : tr.autoDetect)}</span>
            </div>
          </div><div class="section-resize-handle nodrag" data-resize-section="settings" title="${escapeHtml(tr.resizeSection)}"></div></section>
          <section class="side-section video-assets-section" data-section-key="color" style="${hmbSectionHeightStyle(rightSectionHeights, "color")}">
            <div class="section-head"><span class="grow">${escapeHtml(tr.cutVideoHistory)}</span><span class="video-selected-count">${selectedAssets.length}/${HMB_PICKER_MAX_SELECTED_VIDEOS}</span><input type="file" id="import-video-asset" accept="video/mp4,video/*" hidden/><button type="button" class="import-video-button" id="import-video-button" ${locked ? "disabled" : ""}><svg class="import-video-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m16 16 4 4"></path></svg><span>${escapeHtml(tr.importVideoAsset)}</span></button></div>
            <div class="video-assets-body"><div class="video-asset-grid">${videoAssetMarkup}</div></div>
            <div class="video-order-hint">${escapeHtml(tr.dragVideoOrder)}</div>
            <div class="section-resize-handle nodrag" data-resize-section="color" title="${escapeHtml(tr.resizeSection)}"></div>
          </section>
        </aside>
      </main>
    </div></div>`;
  const pickerViewState = hmbCapturePickerViewState(container);
  const pickerRenderMode = hmbRenderPickerMarkup(
    container,
    hmbScopeWidgetStyleMarkup(pickerMarkup, ".hmbvp"),
  );
  // Give the first paint a complete, top-anchored picker frame. The full node
  // fit runs after the host has finished mounting its native parameter rows.
  concealNativeMayaPicker(container);
  hmbApplyPickerHostSizing(container, hmbPickerInnerRequiredHeight(container));
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

  if (
    Object.prototype.hasOwnProperty.call(container, "__hmbAutoplayVideoUid")
    && clean(container.__hmbAutoplayVideoUid) === previewUid
  ) {
    const autoplayVideo = container.querySelector("#picker-video");
    delete container.__hmbAutoplayVideoUid;
    const startPreview = () => {
      const playResult = autoplayVideo?.play?.();
      if (playResult && typeof playResult.catch === "function") playResult.catch(() => {});
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(startPreview);
    else startPreview();
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
    const draftPath = clean(draftInput?.value || next?.scene_draft_path || next?.scene_request_path || next?.scene_path);
    const availability = pickerButtonAvailability(
      next,
      draftPath,
      !!container.__hmbReadCommandPending,
      !!container.__hmbOriginalCommandPending,
    );
    if (readButton) readButton.disabled = !availability.readEnabled;
    if (stopButton) stopButton.disabled = !availability.stopEnabled;
    if (playblastButton) playblastButton.disabled = !availability.playblastEnabled;
    if (snapshotButton) snapshotButton.disabled = !availability.snapshotEnabled;
    if (deleteSnapshotButton) deleteSnapshotButton.disabled = !availability.snapshotDeleteEnabled;
    if (originalPreviewToggle) {
      originalPreviewToggle.checked = !!next?.original_enabled;
      originalPreviewToggle.disabled = availability.operationBusy;
    }
    if (maskPlayblastToggle) {
      maskPlayblastToggle.checked = next?.mask_enabled !== false;
      maskPlayblastToggle.disabled = availability.operationBusy;
    }
    if (depthPlayblastToggle) {
      depthPlayblastToggle.checked = !!next?.depth_enabled;
      depthPlayblastToggle.disabled = availability.operationBusy;
    }
    if (motionGuideToggle) {
      motionGuideToggle.checked = !!next?.motion_guide_enabled;
      motionGuideToggle.disabled = availability.operationBusy;
    }
    if (draftInput) draftInput.disabled = availability.operationBusy;
    if (browseButton) browseButton.disabled = availability.operationBusy;
    hmbRenderPickerActivityLog(container.querySelector("#activity-log-view"), next, tr);
  };

  const reportTransportError = (error) => {
    const message = clean(error?.message || error) || "Widget state delivery failed.";
    hmbAppendImmediateActivityLogRow(container.querySelector("#activity-log-view"), "ERROR", message);
    try { console.error("[HMBVideoPickerLibrary]", message, error); } catch (_consoleError) {}
    return message;
  };

  const commit = (next, options = {}) => {
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
    container.__hmbAuthoritativePickerState = normalize(normalized);
    container.__hmbPendingPickerState = normalize(normalized);
    applyImmediateCommandUi(normalized);
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
      const deliveryResult = props.onChange(JSON.parse(JSON.stringify(normalized)));
      delivered = true;
      if (deliveryResult && typeof deliveryResult.then === "function") {
        deliveryPromise = Promise.resolve(deliveryResult)
          .then(() => ({ ok: true, error: null }))
          .catch((error) => {
            hmbClearPendingPickerStateEcho(container);
            reportTransportError(error);
            return { ok: false, error };
          });
      }
    } catch (error) {
      hmbClearPendingPickerStateEcho(container);
      reportTransportError(error);
    }
    return { state: normalized, delivered, deliveryPromise };
  };
  const currentWidgetState = () => normalize(container.__hmbPendingPickerState || state);
  const commandBridge = () => {
    const shell = findReactFlowNode(container) || videoPickerNodeRoot(container);
    return shell?.__hmbPickerCommandBridge || null;
  };
  const dispatchCommand = (action, payload = {}, actionId = "") => {
    const liveState = currentWidgetState();
    const resolvedActionId = clean(actionId)
      || `${clean(action) || "command"}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const command = {
      schema: "hmb-picker-command",
      version: 1,
      runtime_instance_id: clean(liveState.runtime_instance_id),
      action: clean(action),
      action_id: resolvedActionId,
      issued_at_ms: Date.now(),
      payload: payload && typeof payload === "object" ? JSON.parse(JSON.stringify(payload)) : {},
    };
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
            reportTransportError(error);
            return { ok: false, error };
          });
      }
    } catch (error) {
      reportTransportError(error);
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

  const viewportVideo = container.querySelector("#picker-video");
  const frameNumberInput = container.querySelector("#video-frame-number");
  const videoSeekInput = container.querySelector("#video-seek");
  const playToggleButton = container.querySelector("#video-play-toggle");
  const frameInfoFrame = container.querySelector("#frame-info-frame");
  const frameInfoTime = container.querySelector("#frame-info-time");
  const mediaFps = Math.max(0.000001, Number(frameMetadata.fps || state.source_fps || video?.source_fps || 24));
  const frameFromVideo = () => {
    if (!viewportVideo) return initialViewportFrame;
    return Math.round(clamp(frameStart + (Number(viewportVideo.currentTime || 0) * mediaFps), frameStart, frameEnd));
  };
  const updateFrameNumber = () => {
    const frame = frameFromVideo();
    container.__hmbViewportFrame = frame;
    if (frameNumberInput) {
      frameNumberInput.value = Math.round(frame).toString();
    }
    if (videoSeekInput) videoSeekInput.value = Math.round(frame).toString();
    if (frameInfoFrame) frameInfoFrame.textContent = `${Math.round(frame)} / ${frameEnd}`;
    if (frameInfoTime) frameInfoTime.textContent = formatFrameTimecode(frame, frameStart, mediaFps);
  };
  const updatePlayToggle = () => {
    const playing = !!viewportVideo && !viewportVideo.paused && !viewportVideo.ended;
    if (playToggleButton) {
      playToggleButton.textContent = playing ? "Ⅱ" : "▶";
      playToggleButton.title = playing ? (tr.pauseVideo || "Pause") : (tr.playVideo || "Play");
      playToggleButton.setAttribute("aria-label", playToggleButton.title);
      playToggleButton.setAttribute("aria-pressed", playing ? "true" : "false");
    }
    container.querySelectorAll("[data-play-video-uid]").forEach((button) => {
      const uid = clean(button.getAttribute("data-play-video-uid"));
      const active = playing && forceVideoPreview && uid === previewUid;
      const thumb = button.closest(".video-asset-thumb");
      const title = clean(button.getAttribute("data-video-title"));
      thumb?.classList?.toggle("is-playing", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.setAttribute(
        "aria-label",
        `${title ? `${title}: ` : ""}${active ? tr.pauseVideo : tr.playVideo}`,
      );
      button.textContent = active ? "Ⅱ" : "▶";
    });
  };
  if (viewportVideo) {
    viewportVideo.loop = true;
    on(viewportVideo, "loadedmetadata", () => {
      const targetFrame = clamp(
        Number(container.__hmbViewportFrame ?? state.current_frame ?? frameStart),
        frameStart,
        frameEnd,
      );
      viewportVideo.currentTime = Math.max(0, (targetFrame - frameStart) / mediaFps);
      updateFrameNumber();
      updatePlayToggle();
    });
    on(viewportVideo, "timeupdate", updateFrameNumber);
    on(viewportVideo, "seeked", updateFrameNumber);
    on(viewportVideo, "play", updatePlayToggle);
    on(viewportVideo, "pause", updatePlayToggle);
    on(viewportVideo, "ended", updatePlayToggle);
  }
  updatePlayToggle();
  const seekToFrame = (requestedFrame) => {
    const frame = Math.round(clamp(Number(requestedFrame), frameStart, frameEnd));
    container.__hmbViewportFrame = frame;
    if (frameNumberInput) frameNumberInput.value = frame.toString();
    if (videoSeekInput) videoSeekInput.value = frame.toString();
    if (frameInfoFrame) frameInfoFrame.textContent = `${frame} / ${frameEnd}`;
    if (frameInfoTime) frameInfoTime.textContent = formatFrameTimecode(frame, frameStart, mediaFps);
    if (viewportVideo) viewportVideo.currentTime = Math.max(0, (frame - frameStart) / mediaFps);
  };
  const showAdjacentSnapshot = (direction) => {
    const liveState = currentWidgetState();
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
    viewportVideo?.pause?.();
    delete container.__hmbAutoplayVideoUid;
    delete container.__hmbForceVideoPreviewUid;
    container.__hmbViewportFrame = Number(target.frame || frameStart);
    commit({
      ...liveState,
      viewport_mode: "snapshot",
      active_snapshot_uid: clean(target.snapshot_uid),
      snapshot_active: true,
      snapshot_frame: Number(target.frame || 0),
      snapshot_video_slot: Number(target.render_video_slot || target.video_slot || 1),
      snapshot_data_uri: clean(target.data_uri),
      snapshot_path: clean(target.path),
    });
  };
  on(container.querySelector("#snapshot-prev"), "click", () => showAdjacentSnapshot(-1));
  on(container.querySelector("#snapshot-next"), "click", () => showAdjacentSnapshot(1));
  on(playToggleButton, "click", () => {
    if (!viewportVideo) {
      if (!selectedVideoUrl) return;
      const liveState = currentWidgetState();
      const livePreviewUid = clean(liveState.preview_video_uid || liveState.selected_video_uid);
      delete container.__hmbForceVideoPreviewUid;
      container.__hmbAutoplayVideoUid = livePreviewUid;
      commit({ ...liveState, viewport_mode: "video" });
      return;
    }
    if (!viewportVideo.paused && !viewportVideo.ended) {
      viewportVideo.pause();
      return;
    }
    const playResult = viewportVideo.play?.();
    if (playResult && typeof playResult.catch === "function") playResult.catch(() => {});
  });
  on(videoSeekInput, "input", (event) => {
    seekToFrame(event.target.value);
  });
  on(frameNumberInput, "change", (event) => {
    viewportVideo?.pause?.();
    seekToFrame(event.target.value);
  });

  const appendImmediateLogLine = (level, message) => {
    hmbAppendImmediateActivityLogRow(container.querySelector("#activity-log-view"), level, message);
  };

  const applySharedUiTheme = (value) => {
    const root = container.querySelector(".hmbvp");
    if (root) root.setAttribute("data-theme", hmbNormalizeUiTheme(value));
  };
  const sharedThemeHandler = (event) => {
    const eventTheme = event && event.detail ? event.detail.theme : "";
    const theme = hmbNormalizeUiTheme(eventTheme || hmbReadSharedUiTheme());
    applySharedUiTheme(theme);
    // Shared-theme reception is paint-only. Do not turn another widget's
    // explicit P/T choice into a VideoPicker backend state transaction.
    state.ui_theme = theme;
    if (container.__hmbAuthoritativePickerState) {
      container.__hmbAuthoritativePickerState.ui_theme = theme;
    }
  };
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener(HMB_UI_THEME_EVENT, sharedThemeHandler);
    activeCleanup.push(() => {
      window.removeEventListener(HMB_UI_THEME_EVENT, sharedThemeHandler);
    });
  }

  const applyColor = (color) => {
    if (!selectedNode || !color || locked) return;
    const liveState = currentWidgetState();
    const liveSlot = 1;
    const current = selectedBindings(liveState, liveSlot);
    const duplicateColor = current.find((item) => clean(item.color) === color && clean(item.full_dag_path) !== clean(selectedNode.full_path));
    if (duplicateColor && !hmbPickerMarkerAllowsRepeat(color, liveState.marker_catalog)) {
      commit({ ...liveState, selected_color: color, message: `Color ${color} is already used by ${duplicateColor.group_name} in the current cut.` });
      return;
    }
    const existingIndex = current.findIndex((item) => clean(item.full_dag_path) === clean(selectedNode.full_path));
    const nextBinding = {
      group_name: clean(selectedNode.name),
      full_dag_path: clean(selectedNode.full_path),
      maya_uuid: clean(selectedNode.maya_uuid),
      reference_node: clean(selectedNode.reference_node),
      reference_file: clean(selectedNode.reference_file),
      proxy_manager: clean(selectedNode.proxy_manager),
      proxy_tag: clean(selectedNode.proxy_tag),
      color,
      enabled: true,
      video_slot: liveSlot,
      picker_order: existingIndex >= 0 ? current[existingIndex].picker_order : current.length + 1,
    };
    if (existingIndex >= 0) current[existingIndex] = nextBinding;
    else current.push(nextBinding);
    const next = setSlotBindings({ ...liveState }, liveSlot, current);
    next.selected_color = color;
    next.status = "READY";
    next.message = `${clean(selectedNode.name)} → ${color} ${existingIndex >= 0 ? "updated" : "added"} for the current cut.`;
    commit(next);
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
  const syncNativeMayaPath = () => {
    concealNativeMayaPicker(container);
    const nativePath = nativeMayaScenePath(container);
    if (!nativePath) return false;
    if (scenePathInput) scenePathInput.value = nativePath;
    container.__hmbMayaSceneDraftPath = nativePath;
    publishSceneDraft();
    return true;
  };
  const scheduleNativeMayaPathSync = () => {
    for (const timer of nativeRefreshTimers) window.clearTimeout(timer);
    nativeRefreshTimers.clear();
    for (const delay of [0, 120, 400, 1000]) {
      const timer = window.setTimeout(() => {
        nativeRefreshTimers.delete(timer);
        syncNativeMayaPath();
      }, delay);
      nativeRefreshTimers.add(timer);
    }
  };
  let nativeSelectionPollTimer = null;
  const stopNativeSelectionPolling = (clearSession = false) => {
    if (nativeSelectionPollTimer != null) {
      window.clearInterval(nativeSelectionPollTimer);
      nativeSelectionPollTimer = null;
    }
    if (clearSession) {
      delete container.__hmbNativePickerPreviousPath;
      delete container.__hmbNativePickerDeadlineMs;
    }
  };
  const beginNativeSelectionPolling = (previousPath, preserveDeadline = false) => {
    stopNativeSelectionPolling(false);
    container.__hmbNativePickerPreviousPath = clean(previousPath);
    if (!preserveDeadline || !Number(container.__hmbNativePickerDeadlineMs || 0)) {
      container.__hmbNativePickerDeadlineMs = Date.now() + 120000;
    }
    const checkSelectionResult = () => {
      if (Date.now() >= Number(container.__hmbNativePickerDeadlineMs || 0)) {
        stopNativeSelectionPolling(true);
        return;
      }
      const selectedPath = nativeMayaScenePath(container);
      const pathBeforeBrowse = clean(container.__hmbNativePickerPreviousPath);
      if (!selectedPath || selectedPath === pathBeforeBrowse) return;
      stopNativeSelectionPolling(true);
      syncNativeMayaPath();
      appendImmediateLogLine("SUCCESS", `Maya scene selected: ${selectedPath}`);
    };
    nativeSelectionPollTimer = window.setInterval(checkSelectionResult, 200);
    checkSelectionResult();
  };
  on(container.querySelector("#browse-maya-scene"), "click", (event) => {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    const currentLocal = currentWidgetState();
    const actionId = `browse-maya-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const result = dispatchCommand("browse_maya_scene", {
      scene_path: clean(currentLocal.scene_draft_path || currentLocal.scene_request_path || currentLocal.scene_path),
    }, actionId);
    if (!result.delivered) {
      appendImmediateLogLine("ERROR", "The native Maya scene browser command could not be delivered to HMB_PICKER_COMMAND.");
    } else {
      appendImmediateLogLine("INFO", "Opening the native Maya .ma/.mb scene browser.");
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
    beginNativeSelectionPolling(container.__hmbNativePickerPreviousPath, true);
  }
  syncNativeMayaPath();

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
    });
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
    });
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
    });
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
  on(container.querySelector("#outliner-search"), "input", (event) => commit({ ...currentWidgetState(), outliner_search: clean(event.target.value) }));
  container.querySelectorAll("[data-group-path]").forEach((row) => {
    const selectRow = () => {
      const path = clean(row.getAttribute("data-group-path"));
      const liveState = currentWidgetState();
      const node = liveState.outliner_nodes.find((item) => clean(item.full_path) === path);
      if (!node) return;
      commit({ ...liveState, selected_outliner_path: path, selected_outliner_name: clean(node.name), selected_outliner_uuid: clean(node.maya_uuid) });
    };
    on(row, "click", (event) => {
      if (event.target.closest("[data-toggle-path], [data-visibility-path]")) return;
      selectRow();
    });
    on(row, "keydown", (event) => {
      if (event.target !== row) return;
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        event.stopPropagation();
        selectRow();
        return;
      }
      if (["ArrowUp", "ArrowDown"].includes(event.key)) {
        const rows = Array.from(container.querySelectorAll("[data-group-path]"));
        const currentIndex = rows.indexOf(row);
        const nextIndex = Math.max(0, Math.min(rows.length - 1, currentIndex + (event.key === "ArrowUp" ? -1 : 1)));
        const target = rows[nextIndex];
        if (!target || target === row) return;
        event.preventDefault();
        rows.forEach((item) => item.setAttribute("tabindex", item === target ? "0" : "-1"));
        target.focus?.();
        return;
      }
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      const path = clean(row.getAttribute("data-group-path"));
      const liveState = currentWidgetState();
      const node = liveState.outliner_nodes.find((item) => clean(item.full_path) === path);
      if (!node) return;
      const expanded = new Set(liveState.outliner_expanded);
      if (event.key === "ArrowRight" && Number(node.child_count || 0) > 0 && !expanded.has(path)) {
        expanded.add(path);
      } else if (event.key === "ArrowLeft" && expanded.has(path)) {
        expanded.delete(path);
      } else if (event.key === "ArrowLeft" && clean(node.parent_path)) {
        event.preventDefault();
        Array.from(container.querySelectorAll("[data-group-path]"))
          .find((item) => clean(item.getAttribute("data-group-path")) === clean(node.parent_path))
          ?.focus?.();
        return;
      } else {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      commit({ ...liveState, outliner_expanded: Array.from(expanded) });
    });
  });
  container.querySelectorAll("[data-toggle-path]").forEach((button) => {
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const path = clean(button.getAttribute("data-toggle-path"));
      const liveState = currentWidgetState();
      const expanded = new Set(liveState.outliner_expanded);
      if (expanded.has(path)) expanded.delete(path); else expanded.add(path);
      commit({ ...liveState, outliner_expanded: Array.from(expanded) });
    });
  });
  container.querySelectorAll("[data-visibility-path]").forEach((button) => {
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const path = clean(button.getAttribute("data-visibility-path"));
      const liveState = currentWidgetState();
      const liveSlot = 1;
      const currentEntry = liveState.slot_visibility.find((item) => Number(item?.video_slot || 0) === liveSlot);
      const hiddenPaths = new Set(Array.isArray(currentEntry?.hidden_paths) ? currentEntry.hidden_paths.map(clean) : []);
      if (hiddenPaths.has(path)) hiddenPaths.delete(path); else hiddenPaths.add(path);
      const slotVisibility = [
        { video_slot: 1, hidden_paths: Array.from(hiddenPaths) },
        ...liveState.slot_visibility.filter((item) => Number(item?.video_slot || 0) !== 1),
      ];
      button.classList.toggle("on", !hiddenPaths.has(path));
      button.classList.toggle("off", hiddenPaths.has(path));
      button.setAttribute("aria-pressed", hiddenPaths.has(path) ? "false" : "true");
      button.closest(".outliner-row")?.classList.toggle("output-off", hiddenPaths.has(path));
      commit({
        ...liveState,
        slot_visibility: slotVisibility,
        message: `${path} visibility ${hiddenPaths.has(path) ? "OFF" : "ON"} for the current cut.`,
      });
    });
  });
  container.querySelectorAll("[data-camera-path]").forEach((button) => {
    on(button, "click", () => commit({ ...currentWidgetState(), selected_camera: clean(button.getAttribute("data-camera-path")) }));
  });
  container.querySelectorAll("[data-color]").forEach((button) => {
    on(button, "click", () => {
      const color = clean(button.getAttribute("data-color"));
      if (selectedNode) applyColor(color);
      else commit({ ...currentWidgetState(), selected_color: color });
    });
  });
  on(container.querySelector("#import-video-button"), "click", () => {
    const result = dispatchCommand("browse_video_asset", { select_if_capacity: true });
    if (result.delivered) {
      appendImmediateLogLine("INFO", "Opening the MP4 browser for the current-cut video history.");
      return;
    }
    container.querySelector("#import-video-asset")?.click?.();
  });
  on(container.querySelector("#import-video-asset"), "change", (event) => {
    const file = event.target?.files?.[0];
    if (!file) return;
    const sourcePath = clean(file.path || file.webkitRelativePath);
    if (!sourcePath) {
      appendImmediateLogLine("ERROR", "The selected MP4 did not expose a local file path. Use the native MP4 browser button.");
      event.target.value = "";
      return;
    }
    const result = dispatchCommand("import_video_asset", {
      source_path: sourcePath,
      label: clean(file.name),
      select_if_capacity: true,
    });
    appendImmediateLogLine(
      result.delivered ? "INFO" : "ERROR",
      result.delivered
        ? `Import requested: ${clean(file.name) || sourcePath}.`
        : "The MP4 import request could not be delivered.",
    );
    event.target.value = "";
  });
  container.querySelectorAll("[data-play-video-uid]").forEach((button) => {
    const playInPreview = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (locked) return;
      const uid = clean(button.getAttribute("data-play-video-uid"));
      if (!uid) return;
      const liveState = currentWidgetState();
      const livePreviewUid = clean(liveState.preview_video_uid || liveState.selected_video_uid);
      const previewPlayer = container.querySelector("#picker-video");
      if (
        previewPlayer
        && livePreviewUid === uid
        && clean(container.__hmbForceVideoPreviewUid) === uid
      ) {
        if (!previewPlayer.paused && !previewPlayer.ended) {
          previewPlayer.pause?.();
        } else {
          const playResult = previewPlayer.play?.();
          if (playResult && typeof playResult.catch === "function") playResult.catch(() => {});
        }
        return;
      }
      container.__hmbAutoplayVideoUid = uid;
      container.__hmbForceVideoPreviewUid = uid;
      commit({ ...hmbPreviewVideoAsset(liveState, uid), viewport_mode: "video" });
    };
    on(button, "click", playInPreview);
  });
  container.querySelectorAll("[data-toggle-video-uid]").forEach((selectionSurface) => {
    const toggleSelection = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (
        locked
        || selectionSurface.getAttribute("aria-disabled") === "true"
        || container.__hmbSuppressVideoSelectionClick
      ) return;
      const uid = clean(selectionSurface.getAttribute("data-toggle-video-uid"));
      const liveState = currentWidgetState();
      const wasSelected = hmbSelectedVideoAssets(liveState).some((item) => clean(item.video_uid) === uid);
      const nextState = hmbToggleVideoAssetSelection(liveState, uid);
      const isSelected = hmbSelectedVideoAssets(nextState).some((item) => clean(item.video_uid) === uid);
      const level = wasSelected && !isSelected ? "INFO" : "SUCCESS";
      commit(appendActivityLog(
        nextState,
        level,
        isSelected
          ? `Video selected as @video${hmbSelectedVideoAssets(nextState).findIndex((item) => clean(item.video_uid) === uid) + 1}.`
          : "Video removed from the active @video order; its history asset remains available.",
      ));
    };
    on(selectionSurface, "click", toggleSelection);
    on(selectionSurface, "keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      toggleSelection(event);
    });
  });
  container.querySelectorAll("[data-delete-video-uid]").forEach((button) => {
    on(button, "click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const uid = clean(button.getAttribute("data-delete-video-uid"));
      const liveState = currentWidgetState();
      const target = (Array.isArray(liveState.videos) ? liveState.videos : [])
        .find((item, index) => hmbVideoAssetUid(item, index) === uid);
      // Stop media before removing its backing catalog record. In particular,
      // a playing main preview must not survive until the asynchronous Python
      // echo when its selected UID is being deleted; normalization will select
      // the next available preview in that authoritative response.
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
        appendImmediateLogLine(
          "INFO",
          `${hmbVideoAssetTitle(target || {}, 0)} removal requested. The media file will be preserved.`,
        );
        return;
      }
      let nextState = hmbDeleteVideoAsset(liveState, uid);
      nextState = appendActivityLog(
        nextState,
        "SUCCESS",
        `${hmbVideoAssetTitle(target || {}, 0)} removed from history. The media file was not deleted.`,
      );
      commit(nextState);
    });
  });
  activeCleanup.push(hmbInstallVideoAssetDragReorder(container, {
    locked,
    currentState: currentWidgetState,
    commitState: (nextState, details) => {
      commit(appendActivityLog(
        nextState,
        "SUCCESS",
        `Video order changed by drag-and-drop; ${details.sourceUid} is now @video${details.targetIndex + 1}.`,
      ));
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
      const resizeShell = findReactFlowNode(container);
      const startNodeHeight = hmbPickerNodeShellHeight(resizeShell);
      const startRequiredHeight = hmbRequiredPickerNodeHeight(container, resizeShell);
      let latestHeight = startHeight;
      try { handle.setPointerCapture?.(event.pointerId); } catch (_error) {}
      const move = (moveEvent) => {
        moveEvent.preventDefault();
        const screenDelta = Number(moveEvent.clientY || startY) - startY;
        latestHeight = clamp(Math.round(startHeight + screenDelta / safeScale), 96, 900);
        section.style.height = `${latestHeight}px`;
        section.style.flexBasis = `${latestHeight}px`;
        hmbApplyPickerDominoResizeFrame(container, startNodeHeight, startRequiredHeight);
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
      const resizeShell = findReactFlowNode(container);
      const startNodeHeight = hmbPickerNodeShellHeight(resizeShell);
      const startRequiredHeight = hmbRequiredPickerNodeHeight(container, resizeShell);
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
        hmbApplyPickerDominoResizeFrame(container, startNodeHeight, startRequiredHeight);
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

  const shellForResizeSync = findReactFlowNode(container);
  let resizeFrame = 0;
  let resizeApplying = false;
  let pointerInteractionActive = false;
  let nativeNodeResizeActive = false;
  const schedulePickerFit = (settle = false) => {
    if (resizeFrame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(resizeFrame);
    const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (fn) => setTimeout(fn, 0);
    const apply = () => {
      resizeFrame = 0;
      if (disposed || resizeApplying || pointerInteractionActive) return;
      const liveShell = shellForResizeSync || findReactFlowNode(container);
      const measuredInnerHeight = hmbPickerInnerRequiredHeight(container);
      const beforeSignature = hmbPickerFitMeasurementSignature(
        container,
        liveShell,
        measuredInnerHeight,
      );
      if (beforeSignature === container.__hmbPickerFitSignature) return;
      resizeApplying = true;
      try {
        concealNativeMayaPicker(container);
        hmbEnsurePickerNodeFits(container, shellForResizeSync || findReactFlowNode(container));
        container.__hmbPickerFitSignature = hmbPickerFitMeasurementSignature(
          container,
          liveShell,
        );
      } finally {
        resizeApplying = false;
      }
    };
    resizeFrame = raf(() => {
      if (settle) resizeFrame = raf(apply);
      else apply();
    });
  };

  hmbEnsurePickerNodeFits(container, shellForResizeSync);
  container.__hmbPickerFitSignature = hmbPickerFitMeasurementSignature(
    container,
    shellForResizeSync,
  );
  try {
    const ResizeObserverClass = window?.ResizeObserver;
    if (typeof ResizeObserverClass === "function") {
      resizeObserver = new ResizeObserverClass(() => schedulePickerFit(false));
      try { resizeObserver.observe(container); } catch (_error) {}
      const rightStackForResizeSync = container.querySelector?.(".right-stack");
      if (rightStackForResizeSync) {
        try { resizeObserver.observe(rightStackForResizeSync); } catch (_error) {}
      }
      const centerStackForResizeSync = container.querySelector?.(".center-stack");
      if (centerStackForResizeSync) {
        try { resizeObserver.observe(centerStackForResizeSync); } catch (_error) {}
      }
    }
  } catch (_error) {}

  const pauseFitDuringPointer = (event) => {
    const target = event?.target;
    let nativeResizeControl = false;
    let localResizeControl = false;
    try {
      nativeResizeControl = !!target?.closest?.(
        ".react-flow__resize-control,.react-flow__node-resizer,[class*='resize-control'],[class*='node-resizer']",
      );
      localResizeControl = !!target?.closest?.("[data-resize-panel],[data-resize-section]");
    } catch (_error) {}
    if (target && (localResizeControl || nativeResizeControl)) {
      pointerInteractionActive = true;
      if (nativeResizeControl) {
        nativeNodeResizeActive = true;
        try {
          const shell = shellForResizeSync || findReactFlowNode(container);
          if (shell?.style) shell.style.minHeight = `${HMB_MIN_NODE_HEIGHT}px`;
        } catch (_error) {}
      }
    }
  };
  const settleAfterPointer = () => {
    if (!pointerInteractionActive && !nativeNodeResizeActive) return;
    pointerInteractionActive = false;
    const wasNativeNodeResize = nativeNodeResizeActive;
    if (wasNativeNodeResize) {
      nativeNodeResizeActive = false;
    }
    schedulePickerFit(true);
  };
  window.addEventListener("pointerdown", pauseFitDuringPointer, true);
  window.addEventListener("pointerup", settleAfterPointer, true);
  window.addEventListener("pointercancel", settleAfterPointer, true);
  window.addEventListener("mouseup", settleAfterPointer, true);
  activeCleanup.push(() => {
    window.removeEventListener("pointerdown", pauseFitDuringPointer, true);
    window.removeEventListener("pointerup", settleAfterPointer, true);
    window.removeEventListener("pointercancel", settleAfterPointer, true);
    window.removeEventListener("mouseup", settleAfterPointer, true);
    if (resizeFrame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(resizeFrame);
    resizeFrame = 0;
  });
  schedulePickerFit(true);

  return {
    cleanup: container.__hmbVideoPickerCleanupProxy,
    update(nextProps) {
      if (hmbConsumePendingPickerStateEcho(container, nextProps || {})) {
        props = nextProps || {};
        return;
      }
      hmbClearPendingPickerStateEcho(container);
      HMBVideoPickerLibraryWidget(container, nextProps || {});
    },
  };
}
