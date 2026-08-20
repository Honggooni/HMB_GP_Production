const MAX_IMAGES = 50;
const MAX_SHOT_IMAGES = 30;
const MAX_VIDEOS = 10;
const MAX_SHOTS = 5;
const MAX_COLOR_PICKS = 3;
const MAX_IDENTIFIER_CHARS = 256;
const MAX_DESCRIPTION_CHARS = 6000;
const MAX_VIDEO_VFX_CHARS = 20000;
const MAX_KEEP_OUT_CHARS = 4000;
const MAX_FRAME_RANGES_PER_BINDING = 100;
const MAX_MANUAL_FRAME_NUMBER = 9999;
const MAX_SOURCE_SYNC_REVISION = Number.MAX_SAFE_INTEGER;
const UI_EDIT_REVISION_KEY = "ui_edit_revision";
let ACTOR_COLOR_PICK_CHOICES = [];
let OBJECT_COLOR_PICK_CHOICES = [];
let COLOR_PICK_CHOICES = [];
let ACTOR_COLOR_PICK_SOURCE_TYPES = new Set();
let OBJECT_COLOR_PICK_SOURCE_TYPES = new Set();
const HMB_DEFAULT_NODE_WIDTH = 1800;
const HMB_MIN_NODE_WIDTH = 760;
const HMB_HEADER_LAYOUT_VERSION = 2;
const HMB_LEGACY_IMAGE_SOURCES_DEFAULT_HEIGHT = 542;
const HMB_GROUP_START_HEIGHTS = Object.freeze({
  // Match VideoPicker's 68px header without changing the established
  // 1800x1193 outer startup size. Only the fresh/default image editor absorbs
  // the 10px delta; persisted user group heights remain authoritative.
  imageSources: 514,
  imageText: 200,
  videoSources: 200,
  videoText: 150,
});
const HMB_GROUP_MIN_HEIGHTS = Object.freeze({
  // Keep the outer 1193px minimum while reserving the VideoPicker header chrome.
  imageSources: 514,
  imageText: 200,
  videoSources: 200,
  videoText: 150,
});
const HMB_GROUP_DEFAULT_HEIGHTS = HMB_GROUP_START_HEIGHTS;
const HMB_START_LAYOUT_CHROME_HEIGHT = 129;
// Native compatibility/dependency ports are hidden one-pixel host rows.
const HMB_NATIVE_ASSET_INPUT_ROW_HEIGHT = 0;
const HMB_DEFAULT_NODE_HEIGHT =
  Object.values(HMB_GROUP_START_HEIGHTS).reduce((total, height) => total + height, 0) +
  HMB_START_LAYOUT_CHROME_HEIGHT +
  HMB_NATIVE_ASSET_INPUT_ROW_HEIGHT;
const HMB_MIN_NODE_HEIGHT = HMB_DEFAULT_NODE_HEIGHT;
const HMB_RESIZE_MODE = "stacked_outer_1000";
const HMB_GROUP_MAX_HEIGHT = 6000;
const HMB_GROUP_KEYS = Object.keys(HMB_GROUP_MIN_HEIGHTS);
const HMB_KEEP_OUT_MIN_HEIGHT = 34;
const HMB_KEEP_OUT_DEFAULT_HEIGHT = 34;
const HMB_KEEP_OUT_MAX_HEIGHT = 1200;


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

let IMAGE_SOURCE_TYPES = [];
let IMAGE_SCOPES = [];
let IMAGE_SCOPES_BY_SOURCE_TYPE = {};

const VIDEO_SOURCE_TYPES = [
  "Role Required / Select Video Type",
  "Ignore / Unused",
  "Maya Preview / Playblast",
  "Unified Shot-Control Video",
  "Motion Reference",
  "Camera / Layout Reference",
  "Depth / Spatial Reference",
  "Motion Guide / Retargeting Reference",
  "FX Reference",
  "Timing / Edit Reference",
  "Lighting / Look Reference",
  "Simulation Reference",
  "Mask / Control Reference",
  "Custom",
];

const VIDEO_CONTROL_ROLES = [
  "",
  "Primary Unified Shot Control",
  "Timing Only",
  "Local Motion Detail Only",
  "Secondary Motion Only",
  "Spatial Alignment Verification Only",
  "Derived Motion Decoding Only",
  "FX Behavior Only",
  "Lighting / Look Only",
  "Local Composition Check Only",
  "Mask / Guide Only",
  "Context Only",
  "Custom Role",
];

const VIDEO_ROLE_COMPATIBILITY = {
  "Maya Preview / Playblast": ["Local Motion Detail Only", "Secondary Motion Only", "Spatial Alignment Verification Only", "Timing Only", "Mask / Guide Only", "Context Only"],
  "Unified Shot-Control Video": ["Primary Unified Shot Control"],
  "Motion Reference": ["Local Motion Detail Only", "Secondary Motion Only", "Context Only"],
  "Camera / Layout Reference": ["Spatial Alignment Verification Only", "Local Composition Check Only", "Context Only"],
  "Depth / Spatial Reference": ["Spatial Alignment Verification Only", "Mask / Guide Only", "Context Only"],
  "Motion Guide / Retargeting Reference": ["Derived Motion Decoding Only"],
  "FX Reference": ["FX Behavior Only", "Timing Only", "Context Only"],
  "Timing / Edit Reference": ["Timing Only", "Context Only"],
  "Lighting / Look Reference": ["Lighting / Look Only", "Context Only"],
  "Simulation Reference": ["Secondary Motion Only", "FX Behavior Only", "Context Only"],
  "Mask / Control Reference": ["Mask / Guide Only", "Context Only"],
  "Custom": ["Custom Role", "Context Only"],
};

const TEXT_FIELDS = [
  ["PROJECT_STYLE_LOOK", "PROJECT STYLE / LOOK CONTEXT ONLY", "approved project look, render quality, style continuity, production-level visual target", "image"],
  ["SCENE_CONTEXT", "SCENE CONTEXT ONLY", "place, time, atmosphere, story situation, relationship, narrative context", "image"],
  ["EMOTION_INTENT", "EMOTION / INTENT", "emotion, performance intent, mood, relationship, tension, tone, narrative purpose", "image"],
  ["VIDEO_VFX", "VIDEO VFX", "shot-specific VFX generation notes, FX timing, FX placement, visibility states, occlusion behavior, and fallback-only instructions", "video"],
  ["PRESERVED_TEXT", "EXACT TEXT / PROPER NOUNS", "one item per line: [Proper Noun], [Dialogue], [Lip-sync Speech], [Lyrics], [Chant], or [On-screen Text] followed by the exact original text", "image"],
];

const MANUAL_VIDEO_CONTEXT_VERSION = 1;
const MANUAL_VIDEO_CONTEXT_TEXT_FIELDS = Object.freeze(
  TEXT_FIELDS.map(([key]) => key).filter((key) => key !== "PRESERVED_TEXT"),
);
const MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS = Object.freeze([
  "color_picks",
  "binding_scopes",
  "binding_custom_scopes",
  "binding_video_slots",
  "marker_video",
  "preview_marker",
  "picker_auto_video",
  "picker_auto_color",
  "picker_auto_source",
  "frame_range_enabled",
  "frame_range_color_index",
  "frame_range_bindings",
  "frame_range_binding",
  "frame_range_selected_index",
]);

const HMB_UI_KO = {
  image_source_binding: "이미지 소스 연결",
  image_text_context: "이미지 텍스트 설명",
  scene_level_notes: "장면 단위 메모",
  video_source_binding: "비디오 소스 연결",
  video_vfx: "비디오 VFX",
  name: "이름",
  main_type: "주요 유형",
  target: "대상",
  sub_type: "세부 유형",
  color_pick: "컬러 픽",
  video_color_pick: "비디오 / 컬러 픽",
  keep_out: "제외 항목",
  custom_main_type: "사용자 지정 주요 유형 입력",
  custom_scope: "사용자 지정 범위 입력",
  custom_video_type: "사용자 지정 비디오 유형 입력",
  custom_video_role: "사용자 지정 비디오 세부 유형 입력",
  blank_target: "— 빈칸 / 대상 없음 —",
  blank_subtype: "— 빈칸 / 세부 유형 없음 —",
  blank_control_role: "— 빈칸 / 제어 역할 선택 —",
  keep_out_placeholder: "최종 출력에서 제외할 더미 FX, 타이밍 가이드 영역, 마커 전용 가이드 영역, 프리뷰 아티팩트, 프록시 이펙트 및 기타 금지 요소",
  video_marker_source: "비디오 마커 소스",
  resize_group: "위아래로 드래그하여 중앙 그룹 크기 조절",
  resize_keep_out: "위아래로 드래그하여 제외 항목 창 크기 조절",
  move_image_up: "이미지를 위로 이동",
  move_image_down: "이미지를 아래로 이동",
  drag_image_row: "\uC774\uBBF8\uC9C0 \uC18C\uC2A4 \uD589\uC744 \uB4DC\uB798\uADF8\uD558\uC5EC \uC21C\uC11C \uBCC0\uACBD",
  delete_image_row: "\uC774\uBBF8\uC9C0 \uC18C\uC2A4 \uD589 \uC0AD\uC81C",
  delete_video_row: "비디오 소스 행 삭제",
  add_image_row: "이미지 소스 행 추가",
  add_image_row_asset_locked: "이미지 어셋 라이브러리 연결 중에는 이미지 행을 추가할 수 없습니다",
  add_video_row: "비디오 소스 행 추가",
  add_color_pick: "컬러 픽 추가",
  remove_color_pick: "컬러 픽 삭제",
  use_frame_range: "Range",
  frame_range_disabled: "연결 없이도 Range를 편집할 수 있으며 소스 연결 시 자동으로 활성화됩니다.",
  frame_in: "인",
  frame_out: "아웃",
  delete_range: "선택 구간 삭제",
};

const HMB_OPTION_KO = {
  "Role Required / Select Source Type": "소스 유형 선택 (선택 사항)",
  "Ignore / Unused": "무시 / 사용 안 함",
  "Character Appearance": "캐릭터 외형",
  "Partial Character Detail": "캐릭터 부분 세부",
  "Prop / Accessory": "소품 / 액세서리",
  "Costume / Clothing": "의상 / 복장",
  "Environment / Background": "환경 / 배경",
  "Sky / Exterior Background": "하늘 / 외부 배경",
  "Set / Structure": "세트 / 구조물",
  "Foreground / Ground": "전경 / 지면",
  "Color / Look Reference": "색감 / 룩 참조",
  "Color + Look + Lighting Mood Reference": "색감 + 룩 + 조명 분위기 참조",
  "Lighting / Atmosphere Reference": "조명 / 분위기 참조",
  "Scale / Composition Reference": "크기 / 구도 참조",
  "Custom": "사용자 지정",
  "Scene / Environment": "장면 / 환경",
  "Camera / Composition": "카메라 / 구도",
  "Global Look": "전체 룩",
  "Current shot": "현재 샷",
  "None": "없음",
  "Full body / full appearance": "전신 / 전체 외형",
  "Full outfit / complete costume": "전체 의상 / 완전한 복장",
  "Head / face only": "머리 / 얼굴만",
  "Eye / expression detail": "눈 / 표정 세부",
  "Eyes / iris / pupil detail": "눈 / 홍채 / 동공 세부",
  "Hand / foot / body part detail": "손 / 발 / 신체 부위 세부",
  "Hair / fur detail": "머리카락 / 털 세부",
  "Costume detail": "의상 세부",
  "Handheld prop": "손에 드는 소품",
  "Attached accessory": "부착 액세서리",
  "Interactive scene prop": "상호작용 씬 소품",
  "Independent scene prop": "독립 씬 소품",
  "Main background": "메인 배경",
  "Set geometry / structure only": "세트 지오메트리 / 구조물만",
  "Sky / exterior area": "하늘 / 외부 영역",
  "Ground / floor": "지면 / 바닥",
  "Foreground element": "전경 요소",
  "Color mood only": "색감 분위기만",
  "Lighting mood only": "조명 분위기만",
  "Render look only": "렌더 룩만",
  "All color + look + lighting functions": "색감 + 룩 + 조명 전체",
  "Scale only": "크기만",
  "Scale + composition": "크기 + 구도",
  "Composition only": "구도만",
  "Custom scope": "사용자 지정 범위",
  "Role Required / Select Video Type": "비디오 유형 선택 (선택 사항)",
  "Maya Preview / Playblast": "Maya 프리뷰 / 플레이블라스트",
  "Unified Shot-Control Video": "통합 샷 제어 비디오",
  "Motion Reference": "모션 참조",
  "Camera / Layout Reference": "카메라 / 레이아웃 참조",
  "Depth / Spatial Reference": "깊이 / 공간 참조",
  "Motion Guide / Retargeting Reference": "모션 가이드 / 리타게팅 참조",
  "FX Reference": "FX 참조",
  "Timing / Edit Reference": "타이밍 / 편집 참조",
  "Lighting / Look Reference": "조명 / 룩 참조",
  "Simulation Reference": "시뮬레이션 참조",
  "Mask / Control Reference": "마스크 / 제어 참조",
  "Primary Unified Shot Control": "기본 통합 샷 제어",
  "Timing Only": "타이밍만",
  "Local Motion Detail Only": "지정 모션 세부",
  "Secondary Motion Only": "유기적 모션 세부",
  "Spatial Alignment Verification Only": "공간 정렬 검증만",
  "Derived Motion Decoding Only": "파생 모션 디코딩만",
  "FX Behavior Only": "FX 동작만",
  "Lighting / Look Only": "조명 / 룩만",
  "Local Composition Check Only": "부분 구도 확인만",
  "Mask / Guide Only": "마스크 / 가이드만",
  "Context Only": "맥락 참조만",
  "Custom Role": "사용자 지정 역할",
  "Red": "빨강",
  "Yellow": "노랑",
  "Green": "초록",
  "Blue": "파랑",
  "Purple": "보라",
  "Orange": "주황",
  "Pink": "분홍",
  "Sky Blue": "하늘색",
  "Mint": "민트",
  "Beige": "베이지",
  "Direction Checker": "방향 체커",
  "Sky Grid": "하늘 그리드",
  "Floor Grid": "바닥 그리드",
  "Position Pattern": "위치 패턴",
};

const HMB_TEXT_KO = {
  PROJECT_STYLE_LOOK: ["프로젝트 스타일 / 룩 설명만", "승인된 프로젝트 룩, 렌더 품질, 스타일 연속성, 프로덕션 수준의 시각 목표"],
  SCENE_CONTEXT: ["장면 설명만", "장소, 시간, 분위기, 이야기 상황, 관계, 서사적 맥락"],
  EMOTION_INTENT: ["감정 / 의도", "감정, 연기 의도, 분위기, 관계, 긴장감, 톤, 서사 목적"],
  VIDEO_VFX: ["비디오 VFX", "샷별 VFX 생성 메모, FX 타이밍, 위치, 가시성, 가림 동작 및 소스 누락 시 대체 지시"],
  PRESERVED_TEXT: ["원문 유지 항목", "한 줄에 하나씩 입력: [Proper Noun], [Dialogue], [Lip-sync Speech], [Lyrics], [Chant], [On-screen Text] 뒤에 원문을 정확히 입력"],
};

function uiLanguage(state) {
  const value = clean(state && state.ui && state.ui.language).toLowerCase();
  return value === "en" ? "en" : "ko";
}

function uiText(state, key, english) {
  return uiLanguage(state) === "ko" ? (HMB_UI_KO[key] || english || key) : (english || key);
}

function optionLabel(value, state) {
  const text = String(value == null ? "" : value);
  if (uiLanguage(state) !== "ko") {
    if (text === "Role Required / Select Source Type") return "Select Source Type (Optional)";
    if (text === "Role Required / Select Video Type") return "Select Video Type (Optional)";
    return text;
  }
  const imageMatch = text.match(/^image\s+(\d+)$/i);
  if (imageMatch) return `이미지 ${imageMatch[1]}`;
  return HMB_OPTION_KO[text] || text;
}

function localizedTextField(key, label, placeholder, state) {
  if (uiLanguage(state) !== "ko") return [label, placeholder];
  return HMB_TEXT_KO[key] || [label, placeholder];
}

function defaultImage(slot) {
  return {
    slot,
    token: `@image${slot}`,
    name: `IMAGE_${String(slot).padStart(2, "0")}`,
    present: false,
    label: "",
    asset_id: "",
    asset_path: "",
    asset_library_id: "",
    asset_source_uid: "",
    asset_project_uid: "",
    asset_selection_order: 0,
    asset_source_type_candidate: "",
    asset_scope_candidate: "",
    asset_color_pick_candidates: [],
    asset_default_target: "",
    asset_managed: false,
    asset_verified: false,
    asset_source_kind: "",
    source_type: "Role Required / Select Source Type",
    custom_source_type: "",
    owner: "",
    legacy_relationship_targets: [],
    scope: "",
    binding_scopes: [""],
    binding_custom_scopes: [""],
    binding_video_slots: [1],
    color_picks: [""],
    marker_video: 1,
    preview_marker: "",
    picker_auto_color: "",
    picker_auto_video: 0,
    picker_auto_source: "",
    frame_range_enabled: false,
    frame_range_color_index: 0,
    frame_range_bindings: {},
    frame_range_binding: null,
    frame_range_selected_index: -1,
    manual: true,
  };
}

// A source row needs an identity that survives local reorder/renumber without
// leaking an implementation key into the persisted prompt payload.  Symbols
// are copied by the normalizers below, but JSON.stringify intentionally omits
// them.
const HMB_PROMPT_SOURCE_IDENTITY = Symbol("hmbPromptSourceIdentity");
let hmbPromptSourceIdentitySequence = 0;

function hmbPromptSourceIdentityHash(value) {
  let hash = 0x811c9dc5;
  for (const char of String(value || "")) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(36);
}

function hmbPromptNaturalSourceIdentity(source, kind) {
  if (!source || typeof source !== "object") return "";
  const authority = kind === "image"
    ? clean(source.asset_source_uid)
      || [clean(source.asset_library_id), clean(source.asset_id)].filter(Boolean).join("\u001f")
      || clean(source.asset_path)
    : clean(source.video_uid || source.source_uid);
  return authority ? `${kind}-authority-${hmbPromptSourceIdentityHash(authority)}` : "";
}

function hmbPromptCarrySourceIdentity(source, target, kind) {
  if (!target || typeof target !== "object") return target;
  let identity = source && typeof source === "object"
    ? source[HMB_PROMPT_SOURCE_IDENTITY]
    : "";
  if (!identity) identity = hmbPromptNaturalSourceIdentity(source, kind);
  if (!identity) {
    hmbPromptSourceIdentitySequence += 1;
    identity = `${kind}-${hmbPromptSourceIdentitySequence}`;
  }
  try {
    Object.defineProperty(target, HMB_PROMPT_SOURCE_IDENTITY, {
      configurable: true,
      enumerable: false,
      writable: false,
      value: identity,
    });
  } catch (_error) {}
  return target;
}

export function hmbPromptSourceIdentity(item, kind = "source") {
  if (!item || typeof item !== "object") return `${kind}-missing`;
  if (!item[HMB_PROMPT_SOURCE_IDENTITY]) hmbPromptCarrySourceIdentity(item, item, kind);
  return String(item[HMB_PROMPT_SOURCE_IDENTITY] || `${kind}-missing`);
}

function hmbPromptStableSerializable(value) {
  if (Array.isArray(value)) return value.map(hmbPromptStableSerializable);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [
    key,
    hmbPromptStableSerializable(value[key]),
  ]));
}

function hmbPromptManualSourceFingerprint(item, kind, coarse = false) {
  if (!item || typeof item !== "object") return "";
  if (coarse) {
    const keys = kind === "image" ? [
      "label", "present", "asset_id", "asset_path", "asset_library_id",
      "source_type", "custom_source_type", "scope", "owner", "manual",
    ] : [
      "label", "present", "video_uid", "source_uid", "source_type",
      "custom_source_type", "control_role", "custom_control_role", "manual",
    ];
    return JSON.stringify(keys.map((key) => hmbPromptStableSerializable(item[key])));
  }
  // Slot/order fields are presentation coordinates. Excluding them lets a
  // JSON-round-tripped reorder follow the source rather than its old row.
  const positional = new Set([
    "slot", "token", "name", "selection_order", "asset_selection_order",
    "order_key", "frame_range_selected_index",
  ]);
  const semantic = {};
  Object.keys(item).sort().forEach((key) => {
    if (!positional.has(key)) semantic[key] = hmbPromptStableSerializable(item[key]);
  });
  return JSON.stringify(semantic);
}

function hmbPromptReconcileSourceRows(previousRows, nextRows, kind) {
  const previous = Array.isArray(previousRows) ? previousRows : [];
  const next = Array.isArray(nextRows) ? nextRows : [];
  const unused = new Set(previous.map((_item, index) => index));
  let reconciled = 0;
  const candidates = (predicate) => Array.from(unused).filter((index) => predicate(previous[index]));
  const choose = (matches, nextItem, nextIndex) => {
    if (!matches.length) return -1;
    const sameSlot = matches.find((index) => Number(previous[index]?.slot) === Number(nextItem?.slot));
    if (sameSlot != null) return sameSlot;
    if (matches.length === 1) return matches[0];
    return matches.includes(nextIndex) ? nextIndex : matches[0];
  };

  next.forEach((nextItem, nextIndex) => {
    if (!nextItem || typeof nextItem !== "object") return;
    // Authority-backed rows already derive the same deterministic identity
    // after deserialization and must never borrow a manual row's identity.
    if (hmbPromptNaturalSourceIdentity(nextItem, kind)) return;
    const exact = hmbPromptManualSourceFingerprint(nextItem, kind, false);
    let match = choose(candidates((item) => (
      !hmbPromptNaturalSourceIdentity(item, kind)
      && hmbPromptManualSourceFingerprint(item, kind, false) === exact
    )), nextItem, nextIndex);
    if (match < 0) {
      const coarse = hmbPromptManualSourceFingerprint(nextItem, kind, true);
      match = choose(candidates((item) => (
        !hmbPromptNaturalSourceIdentity(item, kind)
        && hmbPromptManualSourceFingerprint(item, kind, true) === coarse
      )), nextItem, nextIndex);
    }
    if (match < 0) {
      match = choose(candidates((item) => (
        !hmbPromptNaturalSourceIdentity(item, kind)
        && Number(item?.slot) === Number(nextItem?.slot)
      )), nextItem, nextIndex);
    }
    if (match < 0 && unused.has(nextIndex)) match = nextIndex;
    if (match < 0) return;
    hmbPromptCarrySourceIdentity(previous[match], nextItem, kind);
    unused.delete(match);
    reconciled += 1;
  });
  return reconciled;
}

// Reattach non-serializable row identities when a host sends a canonical JSON
// echo. The persisted/public payload remains unchanged, while keyed DOM rows,
// focus, selection and IME ownership survive unrelated authoritative updates.
export function hmbReconcilePromptSourceIdentities(previousState, nextState) {
  if (!nextState || typeof nextState !== "object") return 0;
  return hmbPromptReconcileSourceRows(previousState?.images, nextState.images, "image")
    + hmbPromptReconcileSourceRows(previousState?.videos, nextState.videos, "video");
}

const PICKER_AUTO_DEPTH_FIELDS = Object.freeze([
  "label",
  "present",
  "source_type",
  "custom_source_type",
  "control_role",
  "custom_control_role",
  "picker_auto_label",
]);

function pickerAutoDepthFieldValue(field, value) {
  if (field !== "present") return clean(value);
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) && value !== 0;
  return ["1", "true", "yes", "on"].includes(clean(value).toLowerCase());
}

function normalizePickerAutoDepth(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const rawFields = value.fields;
  if (!rawFields || typeof rawFields !== "object" || Array.isArray(rawFields)) return {};
  const fields = {};
  PICKER_AUTO_DEPTH_FIELDS.forEach((field) => {
    const entry = rawFields[field];
    if (
      !entry
      || typeof entry !== "object"
      || Array.isArray(entry)
      || !Object.prototype.hasOwnProperty.call(entry, "assigned")
      || !Object.prototype.hasOwnProperty.call(entry, "previous")
    ) return;
    fields[field] = {
      assigned: pickerAutoDepthFieldValue(field, entry.assigned),
      previous: pickerAutoDepthFieldValue(field, entry.previous),
    };
  });
  if (!Object.keys(fields).length) return {};
  return {
    pair_run_id: clean(value.pair_run_id),
    fields,
  };
}

function normalizePickerAutoMotionGuide(value) {
  const normalized = normalizePickerAutoDepth(value);
  if (!Object.keys(normalized).length) return {};
  return {
    bundle_run_id: clean(value.bundle_run_id || value.pair_run_id),
    fields: normalized.fields,
  };
}

function normalizePickerMotionGuideSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const profile = clean(value.profile);
  if (profile !== "hmb_target_neutral_motion_guide_v5") return {};
  const count = (field) => Math.max(0, Math.floor(Number(value[field]) || 0));
  const allowedGroups = new Set(["brow", "eyelid", "mouth", "jaw"]);
  return {
    profile,
    semantic_face: Boolean(value.semantic_face),
    target_count: count("target_count"),
    channel_count: count("channel_count"),
    driver_count: count("driver_count"),
    landmark_count: count("landmark_count"),
    rasterized_sample_count: count("rasterized_sample_count"),
    hidden_or_occluded_sample_count: count("hidden_or_occluded_sample_count"),
    semantic_groups: uniqueList(
      (Array.isArray(value.semantic_groups) ? value.semantic_groups : [])
        .map(clean)
        .filter((group) => allowedGroups.has(group)),
    ).sort(),
    final_blendshape_values_in_sidecar: Boolean(
      value.final_blendshape_values_in_sidecar,
    ),
    raw_curve_geometry_rendered: false,
  };
}

function normalizePickerCompanionSourceSlot(item) {
  if (!item || typeof item !== "object") return -1;
  let value = item.picker_companion_source_slot;
  if (value == null || value === "") value = item.source_video_slot;
  if (value == null || value === "") value = item.companion_of_video_slot;
  const match = clean(value).match(/^(?:@?video)?\s*(-?\d+)$/i);
  const slot = Number(match ? match[1] : value);
  return Number.isInteger(slot) && slot >= 0 && slot <= MAX_VIDEOS ? slot : -1;
}

function defaultVideo(slot) {
  return {
    slot,
    token: `@video${slot}`,
    name: `VIDEO_${String(slot).padStart(2, "0")}`,
    video_uid: "",
    source_uid: "",
    selection_order: 0,
    order_key: "",
    picker_managed: false,
    present: false,
    label: "",
    source_type: "Role Required / Select Video Type",
    custom_source_type: "",
    control_role: "",
    custom_control_role: "",
    keep_out: "",
    picker_auto_label: "",
    picker_auto_depth: {},
    picker_auto_motion_guide: {},
    picker_motion_guide_summary: {},
    picker_companion_kind: "",
    picker_companion_source_slot: -1,
    picker_companion_source_uid: "",
    picker_companion_validated: false,
    manual: slot === 1,
  };
}

function defaultUi() {
  return {
    group_heights: {},
    textarea_heights: {},
    resize_mode: HMB_RESIZE_MODE,
    header_layout_version: HMB_HEADER_LAYOUT_VERSION,
    language: "ko",
  };
}

function defaultState() {
  return normalizeState({
    schema: "prompt-library-state",
    mode: "prompt_only_role_dashboard",
    source_sync_revision: 0,
    [UI_EDIT_REVISION_KEY]: 0,
    shot: {
      shot_uuid: "",
      channel_uuid: "",
      name: "Only",
      number: 1,
      selected_source_uids: [],
    },
    images: [defaultImage(1), defaultImage(2), defaultImage(3), defaultImage(4)],
    videos: [defaultVideo(1)],
    text: Object.fromEntries(TEXT_FIELDS.map(([key]) => [key, ""])),
    source_intent_fallbacks: [],
    ui: defaultUi(),
    picker: {
      enabled: false,
      awaiting_data: false,
      run_id: "",
      selection_id: "",
      selected_video_count: 0,
      ordered_video_uids: [],
      order_managed: false,
      dormant_video_rows: [],
      dormant_manual_rows: [],
      manual_video_context: {},
      slot_suppressions: {},
      scene: "",
      video_path: "",
      camera: "",
      markers: [],
      frame_metadata: [],
      contract_errors: [],
      matched_images: 0,
      shot_catalog: [],
      shot_routing: {},
    },
    image_asset: {
      enabled: false,
      project_id: "",
      project_uid: "",
      project_root: "",
      selection_id: "",
      selected_assets: 0,
      ordered_source_uids: [],
      order_managed: false,
      dormant_manual_rows: [],
      dormant_asset_rows: [],
      shot_catalog: [],
      shot_routing: {},
    },
  });
}

function parseValue(value) {
  if (!value) return defaultState();
  if (typeof value === "object") return normalizeState(value);
  if (typeof value === "string") {
    try { return normalizeState(JSON.parse(value)); } catch (_e) { return defaultState(); }
  }
  return defaultState();
}

function clean(value) {
  return String(value || "").trim();
}

function normalizeSourceSyncRevision(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(MAX_SOURCE_SYNC_REVISION, Math.floor(parsed)));
}

function normalizeUiEditRevision(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(MAX_SOURCE_SYNC_REVISION, Math.floor(parsed)));
}

const SOURCE_PARSE_DIAGNOSTIC_KIND = "parse_diagnostic";
const SOURCE_PARSE_DIAGNOSTIC_REASON = "invalid JSON connected input";
const SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE = "invalid_json";
const LEGACY_NON_JSON_REASON = "readable non-JSON connected input";
const LEGACY_MACHINE_PREFIX_CHARS = 4096;
const SOURCE_MACHINE_SIGNATURES = Object.freeze({
  PICKER_IN: Object.freeze({
    schema: "hmb-prompt-library-picker-binding",
    mode: "maya",
  }),
  IMAGE_ASSET_IN: Object.freeze({
    schema: "hmb-image-asset-library-binding",
    mode: "image_asset",
  }),
});

function hmbUtf8Bytes(value) {
  const text = String(value == null ? "" : value);
  if (typeof TextEncoder === "function") return new TextEncoder().encode(text);
  // The widget host normally provides TextEncoder. This portable fallback is
  // kept for retained-mode test/host isolates and deliberately replaces lone
  // UTF-16 surrogates exactly as the standard UTF-8 encoder does.
  const bytes = [];
  for (let index = 0; index < text.length; index += 1) {
    let point = text.charCodeAt(index);
    if (point >= 0xd800 && point <= 0xdbff) {
      const low = text.charCodeAt(index + 1);
      if (low >= 0xdc00 && low <= 0xdfff) {
        point = 0x10000 + ((point - 0xd800) << 10) + (low - 0xdc00);
        index += 1;
      } else point = 0xfffd;
    } else if (point >= 0xdc00 && point <= 0xdfff) point = 0xfffd;
    if (point <= 0x7f) bytes.push(point);
    else if (point <= 0x7ff) {
      bytes.push(0xc0 | (point >>> 6), 0x80 | (point & 0x3f));
    } else if (point <= 0xffff) {
      bytes.push(
        0xe0 | (point >>> 12),
        0x80 | ((point >>> 6) & 0x3f),
        0x80 | (point & 0x3f),
      );
    } else {
      bytes.push(
        0xf0 | (point >>> 18),
        0x80 | ((point >>> 12) & 0x3f),
        0x80 | ((point >>> 6) & 0x3f),
        0x80 | (point & 0x3f),
      );
    }
  }
  return Uint8Array.from(bytes);
}

function hmbRotateRight32(value, count) {
  return (value >>> count) | (value << (32 - count));
}

// Synchronous SHA-256 is required here because normalizeState is synchronous
// and legacy workflow state must migrate identically in browser and backend.
function hmbSha256Hex(value) {
  const input = hmbUtf8Bytes(value);
  const bitLength = input.length * 8;
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(input);
  bytes[input.length] = 0x80;
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  const view = new DataView(bytes.buffer);
  view.setUint32(paddedLength - 8, high >>> 0, false);
  view.setUint32(paddedLength - 4, low, false);
  const constants = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  const hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];
  const words = new Uint32Array(64);
  for (let offset = 0; offset < bytes.length; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + (index * 4), false);
    }
    for (let index = 16; index < 64; index += 1) {
      const a = words[index - 15];
      const b = words[index - 2];
      const sigma0 = hmbRotateRight32(a, 7) ^ hmbRotateRight32(a, 18) ^ (a >>> 3);
      const sigma1 = hmbRotateRight32(b, 17) ^ hmbRotateRight32(b, 19) ^ (b >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const sum1 = hmbRotateRight32(e, 6) ^ hmbRotateRight32(e, 11) ^ hmbRotateRight32(e, 25);
      const choice = (e & f) ^ ((~e) & g);
      const temporary1 = (h + sum1 + choice + constants[index] + words[index]) >>> 0;
      const sum0 = hmbRotateRight32(a, 2) ^ hmbRotateRight32(a, 13) ^ hmbRotateRight32(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temporary2 = (sum0 + majority) >>> 0;
      h = g; g = f; f = e; e = (d + temporary1) >>> 0;
      d = c; c = b; b = a; a = (temporary1 + temporary2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  return hash.map((word) => word.toString(16).padStart(8, "0")).join("");
}

function hmbJsonErrorOffset(text) {
  let firstInvalidEscape = -1;
  let inString = false;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    if (!inString) {
      if (code === 0x22) inString = true;
      continue;
    }
    if (code === 0x22) {
      inString = false;
      continue;
    }
    if (code !== 0x5c) continue;
    const escape = text[index + 1] || "";
    if ('"\\/bfnrt'.includes(escape)) {
      index += 1;
      continue;
    }
    if (escape === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(index + 2, index + 6))) {
      index += 5;
      continue;
    }
    firstInvalidEscape = Array.from(text.slice(0, index)).length;
    break;
  }
  try {
    JSON.parse(text);
    return -1;
  } catch (error) {
    const message = String(error && error.message || "");
    const match = message.match(/(?:position|at position)\s+(\d+)/i)
      || message.match(/at line\s+(\d+)\s+column\s+(\d+)/i);
    if (!match) return firstInvalidEscape;
    if (match.length === 2) {
      const utf16Offset = Math.max(0, Number(match[1]) || 0);
      const engineOffset = Array.from(text.slice(0, utf16Offset)).length;
      return firstInvalidEscape >= 0 && firstInvalidEscape <= engineOffset
        ? firstInvalidEscape
        : engineOffset;
    }
    const line = Math.max(1, Number(match[1]) || 1);
    const column = Math.max(1, Number(match[2]) || 1);
    const lines = text.split("\n");
    let offset = 0;
    for (let index = 0; index < line - 1 && index < lines.length; index += 1) {
      offset += lines[index].length + 1;
    }
    const engineOffset = Array.from(text.slice(0, offset + column - 1)).length;
    return firstInvalidEscape >= 0 && firstInvalidEscape <= engineOffset
      ? firstInvalidEscape
      : engineOffset;
  }
}

function hmbLegacyMachineRaw(source, reason, text) {
  const signature = SOURCE_MACHINE_SIGNATURES[source];
  if (!signature || reason !== LEGACY_NON_JSON_REASON) return false;
  const prefix = text.slice(0, LEGACY_MACHINE_PREFIX_CHARS);
  if (!prefix.startsWith("{")) return false;
  const quoted = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[,{])\\s*"schema"\\s*:\\s*"${quoted(signature.schema)}"`).test(prefix)
    && new RegExp(`(?:^|[,{])\\s*"mode"\\s*:\\s*"${quoted(signature.mode)}"`).test(prefix);
}

function hmbPythonInteger(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") {
    return Number.isFinite(value) && Number.isSafeInteger(Math.trunc(value))
      ? Math.trunc(value)
      : null;
  }
  if (typeof value === "string" && /^[+-]?\d+$/.test(value.trim())) {
    const parsed = Number(value.trim());
    return Number.isSafeInteger(parsed) ? parsed : null;
  }
  return null;
}

function hmbParseDiagnosticFromRaw(source, text, suppliedErrorOffset = null) {
  const normalizedOffset = hmbPythonInteger(suppliedErrorOffset);
  return {
    kind: SOURCE_PARSE_DIAGNOSTIC_KIND,
    source,
    reason: SOURCE_PARSE_DIAGNOSTIC_REASON,
    error_code: SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE,
    byte_length: hmbUtf8Bytes(text).length,
    sha256: hmbSha256Hex(text),
    error_offset: Math.max(
      -1,
      normalizedOffset == null ? hmbJsonErrorOffset(text) : normalizedOffset,
    ),
  };
}

function hmbNormalizeParseDiagnostic(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (raw.kind !== SOURCE_PARSE_DIAGNOSTIC_KIND) return null;
  const source = clean(raw.source);
  if (!SOURCE_MACHINE_SIGNATURES[source]) return null;
  const byteLength = hmbPythonInteger(raw.byte_length);
  const errorOffset = hmbPythonInteger(raw.error_offset);
  const sha256 = clean(raw.sha256).toLowerCase();
  if (
    clean(raw.error_code) !== SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE
    || byteLength == null
    || !/^[0-9a-f]{64}$/.test(sha256)
    || errorOffset == null
  ) return null;
  return {
    kind: SOURCE_PARSE_DIAGNOSTIC_KIND,
    source,
    reason: SOURCE_PARSE_DIAGNOSTIC_REASON,
    error_code: SOURCE_PARSE_DIAGNOSTIC_ERROR_CODE,
    byte_length: Math.max(0, byteLength),
    sha256,
    error_offset: Math.max(-1, errorOffset),
  };
}

function hmbReadableOriginal(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  const canonicalize = (item, ancestors) => {
    if (item == null || typeof item !== "object") return item;
    if (ancestors.has(item)) throw new TypeError("circular value");
    ancestors.add(item);
    let result;
    if (Array.isArray(item)) {
      result = item.map((child) => canonicalize(child, ancestors));
    } else {
      result = {};
      Object.keys(item).sort().forEach((key) => {
        result[key] = canonicalize(item[key], ancestors);
      });
    }
    ancestors.delete(item);
    return result;
  };
  try {
    const encoded = JSON.stringify(canonicalize(value, new Set()));
    return typeof encoded === "string" ? encoded : "";
  } catch (_error) {
    try { return String(value).trim(); } catch (_ignored) { return ""; }
  }
}

function normalizeSourceIntentFallbacks(value) {
  const source = Array.isArray(value) ? value : (value == null ? [] : [value]);
  const out = [];
  const seen = new Set();
  const diagnosticIndexes = new Map();
  source.forEach((raw) => {
    const existingDiagnostic = hmbNormalizeParseDiagnostic(raw);
    const rawSource = raw && typeof raw === "object" && !Array.isArray(raw)
      ? clean(raw.source) || "CONNECTED_SOURCE"
      : "CONNECTED_SOURCE";
    const rawReason = raw && typeof raw === "object" && !Array.isArray(raw)
      ? clean(raw.reason) || "readable unstructured input"
      : "readable unstructured input";
    const rawText = raw && typeof raw === "object" && !Array.isArray(raw)
      ? hmbReadableOriginal(raw.text)
      : hmbReadableOriginal(raw);
    let diagnostic = existingDiagnostic;
    if (!diagnostic && raw && typeof raw === "object" && !Array.isArray(raw)
      && raw.kind === SOURCE_PARSE_DIAGNOSTIC_KIND) {
      diagnostic = rawText && hmbLegacyMachineRaw(
        rawSource,
        LEGACY_NON_JSON_REASON,
        rawText,
      )
        ? hmbParseDiagnosticFromRaw(rawSource, rawText, raw.error_offset)
        : null;
    }
    if (!diagnostic && rawText && hmbLegacyMachineRaw(rawSource, rawReason, rawText)) {
      diagnostic = hmbParseDiagnosticFromRaw(rawSource, rawText);
    }
    if (diagnostic) {
      if (diagnosticIndexes.has(diagnostic.source)) {
        out[diagnosticIndexes.get(diagnostic.source)] = diagnostic;
      } else {
        diagnosticIndexes.set(diagnostic.source, out.length);
        out.push(diagnostic);
      }
      return;
    }
    const entry = raw && typeof raw === "object" && !Array.isArray(raw)
      ? {
        source: rawSource,
        reason: rawReason,
        text: rawText,
      }
      : {
        source: "CONNECTED_SOURCE",
        reason: "readable unstructured input",
        text: rawText,
      };
    if (!entry.text || !entry.text.trim()) return;
    const signature = `${entry.source}\u0000${entry.reason}\u0000${entry.text}`;
    if (seen.has(signature)) return;
    seen.add(signature);
    out.push(entry);
  });
  return out;
}

function isKnownColorPick(value) {
  const color = clean(value);
  return Boolean(color) && (
    COLOR_PICK_CHOICES.length === 0
    || COLOR_PICK_CHOICES.includes(color)
  );
}

function applyImageTaxonomy(input) {
  const taxonomy = input && typeof input.image_taxonomy === "object"
    ? input.image_taxonomy
    : {};
  const firstImage = input && Array.isArray(input.images) && input.images[0]
    && typeof input.images[0] === "object"
    ? input.images[0]
    : {};
  const uniqueStrings = (value) => Array.isArray(value)
    ? [...new Set(value.map((item) => String(item == null ? "" : item)).filter((item, index) => item || index === 0))]
    : [];

  const sourceTypes = uniqueStrings(
    taxonomy.source_type_choices || firstImage.source_type_choices,
  );
  const scopes = uniqueStrings(taxonomy.scope_choices || firstImage.scope_choices);
  if (sourceTypes.length) IMAGE_SOURCE_TYPES = sourceTypes;
  if (scopes.length) IMAGE_SCOPES = scopes;

  const rawMap = taxonomy.scope_choices_by_source_type;
  if (rawMap && typeof rawMap === "object" && !Array.isArray(rawMap)) {
    const mapped = {};
    Object.entries(rawMap).forEach(([key, values]) => {
      const choices = uniqueStrings(values);
      if (choices.length) mapped[String(key)] = choices;
    });
    if (Object.keys(mapped).length) IMAGE_SCOPES_BY_SOURCE_TYPE = mapped;
  }

  const actorColors = uniqueStrings(taxonomy.actor_color_pick_choices);
  const objectColors = uniqueStrings(taxonomy.object_color_pick_choices);
  const actorTypes = uniqueStrings(taxonomy.actor_color_pick_source_types);
  const objectTypes = uniqueStrings(taxonomy.object_color_pick_source_types);
  if (actorColors.length) ACTOR_COLOR_PICK_CHOICES = actorColors;
  if (objectColors.length) OBJECT_COLOR_PICK_CHOICES = objectColors;
  if (actorTypes.length) ACTOR_COLOR_PICK_SOURCE_TYPES = new Set(actorTypes);
  if (objectTypes.length) OBJECT_COLOR_PICK_SOURCE_TYPES = new Set(objectTypes);
  COLOR_PICK_CHOICES = [...new Set([
    ...ACTOR_COLOR_PICK_CHOICES,
    ...OBJECT_COLOR_PICK_CHOICES,
  ])];

  return {
    source_type_choices: [...IMAGE_SOURCE_TYPES],
    scope_choices: [...IMAGE_SCOPES],
    scope_choices_by_source_type: Object.fromEntries(
      Object.entries(IMAGE_SCOPES_BY_SOURCE_TYPE).map(([key, values]) => [key, [...values]]),
    ),
    actor_color_pick_choices: [...ACTOR_COLOR_PICK_CHOICES],
    object_color_pick_choices: [...OBJECT_COLOR_PICK_CHOICES],
    actor_color_pick_source_types: [...ACTOR_COLOR_PICK_SOURCE_TYPES],
    object_color_pick_source_types: [...OBJECT_COLOR_PICK_SOURCE_TYPES],
  };
}

export function colorPickChoicesForSourceType(sourceType) {
  const value = clean(sourceType);
  if (ACTOR_COLOR_PICK_SOURCE_TYPES.has(value)) return [...ACTOR_COLOR_PICK_CHOICES];
  if (OBJECT_COLOR_PICK_SOURCE_TYPES.has(value)) return [...OBJECT_COLOR_PICK_CHOICES];
  if (value === "Custom") return [...COLOR_PICK_CHOICES];
  return [];
}

const VIDEO_ROLE_ALIASES = {
  "Strongest Unified Shot-Control": "Primary Unified Shot Control",
  "Motion Only": "Local Motion Detail Only",
  "Camera / Layout / Depth Only": "Spatial Alignment Verification Only",
  "Composition Reference Only": "Local Composition Check Only",
};

function canonicalVideoRole(value) {
  const role = clean(value);
  return VIDEO_ROLE_ALIASES[role] || role;
}

export function applyVideoRoleDefaultForSourceType(item) {
  if (!item || typeof item !== "object") return "";
  const currentRole = canonicalVideoRole(item.control_role);
  const sourceType = clean(item.source_type);
  const defaultRole = sourceType === "FX Reference"
    ? "FX Behavior Only"
    : sourceType === "Timing / Edit Reference"
      ? "Timing Only"
      : "";
  if (!defaultRole) {
    item.control_role = currentRole;
    return currentRole;
  }
  item.control_role = defaultRole;
  return defaultRole;
}

function primaryVideoTypeChoices(_current) {
  return [...VIDEO_SOURCE_TYPES];
}

function mergeUniqueNotes(...values) {
  const parts = [];
  values.forEach((value) => {
    const cleaned = clean(value);
    if (!cleaned) return;
    cleaned.split(/\r?\n/).forEach((line) => {
      const note = clean(line);
      if (note && !parts.includes(note)) parts.push(note);
    });
  });
  return parts.join("\n");
}


function normalizeColorPicks(value) {
  let raw = [];
  if (Array.isArray(value)) {
    raw = value.slice(0, MAX_COLOR_PICKS).map((item) => item && typeof item === "object" ? (item.color || item.value || item.name || "") : item);
  } else if (typeof value === "string") {
    raw = value.split(/[,+/]/).slice(0, MAX_COLOR_PICKS);
  }
  const out = raw.map((item) => {
    const color = clean(item);
    // The predefined palette is a convenience, not an authority boundary.
    // Preserve readable custom markers across every state round trip.
    return color;
  });
  if (!out.length) out.push("");
  return out.slice(0, MAX_COLOR_PICKS);
}

function normalizeBindingScopes(value, fallbackScope, count) {
  let raw = [];
  if (Array.isArray(value)) raw = value.slice(0, MAX_COLOR_PICKS);
  else if (typeof value === "string" && clean(value)) raw = [value];
  const fallback = clean(fallbackScope);
  const targetCount = Math.max(1, Math.min(MAX_COLOR_PICKS, Number(count) || raw.length || 1));
  if (!raw.length && fallback) raw = [fallback];
  const out = raw.slice(0, targetCount).map((item) => clean(item));
  while (out.length < targetCount) out.push("");
  return out.slice(0, MAX_COLOR_PICKS);
}


function normalizeParallelTextList(value, count, maxCount) {
  let raw = [];
  if (Array.isArray(value)) raw = value.slice(0, maxCount);
  else if (typeof value === "string" && clean(value)) raw = [value];
  const targetCount = Math.max(1, Math.min(maxCount, Number(count) || raw.length || 1));
  const out = raw.slice(0, targetCount).map((item) => clean(item));
  while (out.length < targetCount) out.push("");
  return out.slice(0, maxCount);
}

function normalizeBindingVideoSlots(value, fallback, count, videoCount) {
  let raw = [];
  if (Array.isArray(value)) raw = value.slice(0, MAX_COLOR_PICKS);
  else if (value != null && value !== "") raw = [value];
  const targetCount = Math.max(1, Math.min(MAX_COLOR_PICKS, Number(count) || raw.length || 1));
  const fallbackSlot = normalizeMarkerVideo(fallback, videoCount);
  const out = raw.slice(0, targetCount).map((item) => normalizeMarkerVideo(item, videoCount));
  while (out.length < targetCount) out.push(out.length ? out[out.length - 1] : fallbackSlot);
  return out.slice(0, MAX_COLOR_PICKS);
}

function videoSlotNumber(value, videoCount = MAX_VIDEOS) {
  const match = clean(value).match(/(?:@?video)?\s*(\d+)/i);
  return normalizeMarkerVideo(match ? match[1] : value, videoCount);
}

function frameBindingKey(videoSlot, colorPick) {
  return `@video${videoSlotNumber(videoSlot, MAX_VIDEOS)}::${clean(colorPick)}`;
}

export function normalizeFrameRanges(value) {
  const source = Array.isArray(value) ? value.slice(0, MAX_FRAME_RANGES_PER_BINDING) : [];
  const ranges = source.map((raw) => {
    if (!raw || typeof raw !== "object") return null;
    const start = Math.round(Number(raw.start));
    const end = Math.round(Number(raw.end));
    return Number.isFinite(start) && Number.isFinite(end) ? { start, end } : null;
  }).filter(Boolean).sort((a, b) => a.start - b.start || a.end - b.end);
  const merged = [];
  ranges.forEach((current) => {
    const previous = merged[merged.length - 1];
    if (current.start > current.end) {
      merged.push({ ...current });
    } else if (previous && previous.start <= previous.end && current.start <= previous.end + 1) {
      previous.end = Math.max(previous.end, current.end);
    } else {
      merged.push({ ...current });
    }
  });
  return merged.slice(0, MAX_FRAME_RANGES_PER_BINDING);
}

function normalizeFrameDomainEndpoint(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const frame = Math.round(Number(value));
  if (!Number.isFinite(frame)) return null;
  return Math.max(0, Math.min(MAX_MANUAL_FRAME_NUMBER, frame));
}

export function normalizeFrameRangeBindings(value, legacyBinding = null) {
  const out = {};
  const candidates = [];
  if (legacyBinding && typeof legacyBinding === "object") candidates.push(["", legacyBinding]);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    candidates.push(...Object.entries(value));
  }
  candidates.forEach(([rawKey, raw]) => {
    if (!raw || typeof raw !== "object") return;
    const keyParts = String(rawKey || "").split("::");
    const slot = videoSlotNumber(raw.video_slot || raw.video || keyParts[0], MAX_VIDEOS);
    const color = clean(raw.color_pick || raw.color || keyParts[1]);
    const key = frameBindingKey(slot, color);
    const previous = out[key] && typeof out[key] === "object" ? out[key] : {};
    const hasEnabled = Object.prototype.hasOwnProperty.call(raw, "enabled");
    const hasStart = Object.prototype.hasOwnProperty.call(raw, "start_frame")
      || Object.prototype.hasOwnProperty.call(raw, "manual_start_frame");
    const hasEnd = Object.prototype.hasOwnProperty.call(raw, "end_frame")
      || Object.prototype.hasOwnProperty.call(raw, "manual_end_frame");
    out[key] = {
      video_slot: `@video${slot}`,
      color_pick: color,
      enabled: hasEnabled
        ? Boolean(raw.enabled)
        : Object.prototype.hasOwnProperty.call(previous, "enabled")
          ? Boolean(previous.enabled)
          : true,
      origin: clean(raw.origin) || "manual",
      ranges: normalizeFrameRanges(raw.ranges),
      start_frame: hasStart
        ? normalizeFrameDomainEndpoint(
          Object.prototype.hasOwnProperty.call(raw, "start_frame")
            ? raw.start_frame
            : raw.manual_start_frame,
        )
        : normalizeFrameDomainEndpoint(previous.start_frame),
      end_frame: hasEnd
        ? normalizeFrameDomainEndpoint(
          Object.prototype.hasOwnProperty.call(raw, "end_frame")
            ? raw.end_frame
            : raw.manual_end_frame,
        )
        : normalizeFrameDomainEndpoint(previous.end_frame),
    };
  });
  return out;
}

function normalizeFrameMetadata(value) {
  const bySlot = new Map();
  (Array.isArray(value) ? value : []).forEach((raw) => {
    if (!raw || typeof raw !== "object") return;
    const slot = videoSlotNumber(raw.video_slot || raw.video, MAX_VIDEOS);
    const fps = Number(raw.fps || 0);
    const startFrame = Math.round(Number(raw.start_frame));
    const endFrame = Math.round(Number(raw.end_frame));
    const frameCount = Math.round(Number(raw.frame_count || 0));
    const resolution = raw.resolution && typeof raw.resolution === "object"
      ? raw.resolution
      : {};
    const width = Math.max(0, Math.round(Number(raw.width || resolution.width || 0)));
    const height = Math.max(0, Math.round(Number(raw.height || resolution.height || 0)));
    const rangeCount = endFrame >= startFrame ? endFrame - startFrame + 1 : 0;
    const conflict = Boolean(raw.conflict)
      || (frameCount > 0 && rangeCount > 0 && frameCount !== rangeCount);
    const structurallyValid = Number.isFinite(fps) && fps > 0
      && Number.isFinite(startFrame)
      && Number.isFinite(endFrame)
      && endFrame >= startFrame
      && Number.isFinite(frameCount)
      && frameCount > 0;
    const colors = Array.from(new Set(
      (Array.isArray(raw.available_color_picks) ? raw.available_color_picks : [])
        .map(clean)
        .filter((color) => isKnownColorPick(color)),
    ));
    bySlot.set(slot, {
      video_slot: `@video${slot}`,
      video_uid: clean(raw.video_uid || raw.source_uid),
      source_uid: clean(raw.video_uid || raw.source_uid),
      selection_order: Math.max(0, Math.floor(Number(raw.selection_order) || 0)),
      order_key: clean(raw.order_key || raw.video_uid || raw.source_uid),
      fps: Number.isFinite(fps) ? fps : 0,
      start_frame: Number.isFinite(startFrame) ? startFrame : 0,
      end_frame: Number.isFinite(endFrame) ? endFrame : -1,
      frame_count: Number.isFinite(frameCount) ? frameCount : 0,
      duration_seconds: Math.max(0, Number(raw.duration_seconds || 0)),
      timebase: clean(raw.timebase),
      width,
      height,
      resolution: { width, height },
      available_color_picks: colors,
      origin: clean(raw.origin),
      conflict,
      valid: raw.valid !== false && structurallyValid && !conflict,
      warnings: (
        (Array.isArray(raw.warnings) ? raw.warnings : []).map(clean).filter(Boolean).length
          ? (Array.isArray(raw.warnings) ? raw.warnings : []).map(clean).filter(Boolean)
          : conflict
            ? [`Frame count ${frameCount} does not match display range ${startFrame}–${endFrame} (${rangeCount} frames).`]
            : []
      ),
    });
  });
  return Array.from(bySlot.values()).sort((a, b) => videoSlotNumber(a.video_slot) - videoSlotNumber(b.video_slot));
}

function currentFrameRangeSelection(item) {
  const picks = normalizeColorPicks(item && item.color_picks);
  let colorIndex = Math.max(0, Math.min(picks.length - 1, Math.floor(Number(item && item.frame_range_color_index) || 0)));
  if (!clean(picks[colorIndex])) {
    const firstNonEmpty = picks.findIndex((color) => clean(color));
    if (firstNonEmpty >= 0) colorIndex = firstNonEmpty;
  }
  const color = clean(picks[colorIndex]);
  const videoSlots = normalizeBindingVideoSlots(
    item && item.binding_video_slots,
    item && item.marker_video,
    picks.length,
    MAX_VIDEOS,
  );
  const slot = videoSlots[colorIndex];
  const bindings = normalizeFrameRangeBindings(item && item.frame_range_bindings, item && item.frame_range_binding);
  const key = frameBindingKey(slot, color);
  return {
    colorIndex,
    color,
    slot,
    key,
    bindings,
    binding: bindings[key] || (
      item && item.frame_range_enabled
        ? {
          video_slot: `@video${slot}`,
          color_pick: color,
          enabled: true,
          origin: "manual",
          ranges: [],
          start_frame: null,
          end_frame: null,
        }
        : null
    ),
  };
}

function syncCurrentFrameRangeBinding(item) {
  if (!item || typeof item !== "object") return item;
  const selection = currentFrameRangeSelection(item);
  item.frame_range_color_index = selection.colorIndex;
  item.frame_range_bindings = selection.bindings;
  item.frame_range_binding = selection.binding ? { ...selection.binding } : null;
  return item;
}

function frameMetadataForSlot(state, slot) {
  return normalizeFrameMetadata(state && state.picker && state.picker.frame_metadata)
    .find((item) => videoSlotNumber(item.video_slot) === Number(slot)) || null;
}

export function frameRangeUiStatus(state, item) {
  const korean = uiLanguage(state) === "ko";
  const selection = currentFrameRangeSelection(item || {});
  const pickerMetadata = frameMetadataForSlot(state, selection.slot);
  const picker = state && state.picker && typeof state.picker === "object" ? state.picker : {};
  const video = (state && Array.isArray(state.videos) ? state.videos : [])
    .find((entry) => Number(entry && entry.slot) === selection.slot && isActiveVideo(entry));
  const pickerReady = Boolean(picker.enabled && !picker.awaiting_data);
  const manualStart = normalizeFrameDomainEndpoint(selection.binding && selection.binding.start_frame);
  const manualEnd = normalizeFrameDomainEndpoint(selection.binding && selection.binding.end_frame);
  const manualDomainComplete = manualStart !== null && manualEnd !== null && manualEnd >= manualStart;
  const manualDomainInvalid = manualStart !== null && manualEnd !== null && manualEnd < manualStart;
  // Picker frame endpoints are informational only. They may be exposed as a
  // suggestion, but never populate, replace, lock, or bound the user's
  // canonical manual Range domain.
  const suggestedStart = pickerReady && pickerMetadata && pickerMetadata.valid
    && !pickerMetadata.conflict
    ? normalizeFrameDomainEndpoint(pickerMetadata.start_frame)
    : null;
  const suggestedEnd = pickerReady && pickerMetadata && pickerMetadata.valid
    && !pickerMetadata.conflict
    ? normalizeFrameDomainEndpoint(pickerMetadata.end_frame)
    : null;
  const suggestedDomain = suggestedStart !== null
    && suggestedEnd !== null
    && suggestedEnd >= suggestedStart
    ? { start_frame: suggestedStart, end_frame: suggestedEnd }
    : null;
  const metadata = manualDomainComplete
    ? {
      video_slot: `@video${selection.slot}`,
      fps: 0,
      start_frame: manualStart,
      end_frame: manualEnd,
      frame_count: manualEnd - manualStart + 1,
      duration_seconds: 0,
      timebase: "",
      available_color_picks: selection.color ? [selection.color] : [],
      origin: "manual",
      conflict: false,
      valid: true,
      warnings: [],
    }
    : null;
  let reason = "";
  if (!video) reason = `@video${selection.slot} is not an active video source.`;
  // An empty Picker marker catalog means marker authority is unknown.  In
  // that case a blank Color Pick deliberately authors a video-wide manual
  // Range; keep the blank state for backend projection.  A nonempty catalog
  // remains an explicit marker allow-list and still requires a Color Pick.
  else if (
    !selection.color
    && pickerReady
    && pickerMetadata
    && pickerMetadata.available_color_picks.length > 0
  ) reason = "Select a Color Pick.";
  else if (
    pickerReady
    && pickerMetadata
    && pickerMetadata.available_color_picks.length > 0
    && !pickerMetadata.available_color_picks.includes(selection.color)
  ) {
    reason = `${selection.color} is not available in @video${selection.slot} Picker metadata.`;
  }
  // Missing media/color metadata makes this address dormant; it does not lock
  // editing.  Execution validation can surface the reason without destroying
  // or disabling user-authored intent.
  const canEnable = true;
  const ranges = normalizeFrameRanges(selection.binding && selection.binding.ranges);
  let status = item && item.frame_range_enabled
    ? (korean ? "범위 선택 (선택 사항)" : "SELECT RANGE · OPTIONAL")
    : (korean ? "전체 샷 · 범위 끔" : "FULL SHOT · RANGE OFF");
  if (item && item.frame_range_enabled && reason) {
    status = korean ? "주소 대기 · 편집 가능" : "DORMANT ADDRESS · EDITABLE";
  }
  else if (item && item.frame_range_enabled && !metadata) {
    status = manualDomainInvalid
      ? (korean ? "범위 값 확인 (선택 사항)" : "CHECK OPTIONAL RANGE")
      : (korean ? "시작 / 끝 입력 (선택 사항)" : "SET START / END · OPTIONAL");
  }
  else if (item && item.frame_range_enabled && ranges.length) {
    const outside = ranges.some((range) => range.start < metadata.start_frame || range.end > metadata.end_frame || range.start > range.end);
    status = outside
      ? (korean ? "선택 범위 무시됨" : "OPTIONAL RANGE IGNORED")
      : (korean ? `${ranges.length}개 범위` : `${ranges.length} RANGE${ranges.length === 1 ? "" : "S"}`);
    if (outside) reason = `Optional range is outside Frames ${metadata.start_frame}–${metadata.end_frame} and will be ignored.`;
  }
  return {
    ...selection,
    metadata,
    pickerMetadata,
    canEnable,
    reason,
    status,
    ranges,
    domainStart: manualStart,
    domainEnd: manualEnd,
    domainReadonly: false,
    domainComplete: Boolean(metadata),
    domainInvalid: manualDomainInvalid,
    suggestedDomain,
  };
}

function legacyRelationshipTargets(item) {
  const preservedValue = item && item.legacy_relationship_targets;
  const preserved = Array.isArray(preservedValue)
    ? preservedValue
    : (typeof preservedValue === "string" && clean(preservedValue) ? [preservedValue] : []);
  const rawValue = item && (item.interaction_targets || item.interaction_target || item.interactionTarget);
  const raw = Array.isArray(rawValue) ? rawValue : (typeof rawValue === "string" && clean(rawValue) ? [rawValue] : []);
  const customValue = item && item.interaction_custom_targets;
  const customs = Array.isArray(customValue) ? customValue : (typeof customValue === "string" && clean(customValue) ? [customValue] : []);
  const out = uniqueList(preserved.map(clean).filter(Boolean));
  raw.forEach((value, index) => {
    const target = clean(clean(value) === "Custom" ? customs[index] : value);
    if (target && !out.includes(target)) out.push(target);
  });
  return out;
}

function migrateTargetAuthority(item, scopes) {
  let owner = clean(item && item.owner);
  if (owner === "Custom") owner = clean(item && (item.custom_owner || item.custom_target));
  const relationshipScopes = ["Handheld prop", "Attached accessory", "Interactive scene prop"];
  if (!owner && (scopes || []).some((scope) => relationshipScopes.includes(clean(scope)))) {
    const legacyTargets = legacyRelationshipTargets(item);
    if (legacyTargets.length === 1) owner = legacyTargets[0];
  }
  return owner;
}

function normalizeImageBindingFields(item, videoCount = MAX_VIDEOS) {
  if (!item || typeof item !== "object") return item;
  const picks = normalizeColorPicks(item.color_picks);
  const rawScopes = item.binding_scopes != null ? item.binding_scopes : (item.sub_types != null ? item.sub_types : item.subtypes);
  let scopes = normalizeBindingScopes(rawScopes, item.scope, picks.length);
  const count = Math.max(1, Math.min(MAX_COLOR_PICKS, Math.max(picks.length, scopes.length)));
  while (picks.length < count) picks.push("");
  while (scopes.length < count) scopes.push("");
  let customScopes = normalizeParallelTextList(item.binding_custom_scopes, count, MAX_COLOR_PICKS);
  const registeredSubtype = verifiedRegisteredSubtype(item);
  // Sub Type is image-level authority. Color/video bindings remain independent,
  // but they must not carry hidden per-binding subtype overrides.
  const firstAuthoredScopeIndex = scopes.findIndex((scope) => Boolean(clean(scope)));
  const primaryScopeIndex = !registeredSubtype
    && !clean(scopes[0])
    && !clean(item.scope)
    && firstAuthoredScopeIndex >= 0
    ? firstAuthoredScopeIndex
    : 0;
  const primaryScope = registeredSubtype
    || clean(scopes[primaryScopeIndex])
    || clean(item.scope);
  const primaryCustomScope = !registeredSubtype && primaryScope === "Custom scope"
    ? clean(customScopes[primaryScopeIndex] || customScopes.find((scope) => Boolean(clean(scope))) || "")
    : "";
  scopes = Array.from({ length: count }, () => primaryScope);
  customScopes = Array.from({ length: count }, () => primaryCustomScope);
  const legacySlots = normalizeBindingVideoSlots(item.binding_video_slots, item.marker_video || item.color_video || item.video_slot || 1, count, MAX_VIDEOS);
  item.color_picks = picks.slice(0, count);
  item.binding_scopes = scopes.slice(0, count);
  item.binding_custom_scopes = customScopes.slice(0, count);
  item.binding_video_slots = legacySlots.slice(0, count);
  item.marker_video = item.binding_video_slots[0];
  item.scope = item.binding_scopes[0] || "";
  item.frame_range_enabled = Boolean(item.frame_range_enabled);
  item.frame_range_color_index = Math.max(0, Math.min(
    count - 1,
    Math.floor(Number(item.frame_range_color_index) || 0),
  ));
  item.frame_range_bindings = normalizeFrameRangeBindings(item.frame_range_bindings, item.frame_range_binding);
  item.frame_range_selected_index = Number.isFinite(Number(item.frame_range_selected_index))
    ? Math.max(-1, Math.floor(Number(item.frame_range_selected_index)))
    : -1;
  syncCurrentFrameRangeBinding(item);
  return item;
}

function rawBindingEntries(item, videoCount = MAX_VIDEOS) {
  const copy = normalizeImageBindingFields({
    ...(item || {}),
    color_picks: Array.isArray(item && item.color_picks) ? [...item.color_picks] : item && item.color_picks,
    binding_scopes: Array.isArray(item && item.binding_scopes) ? [...item.binding_scopes] : item && item.binding_scopes,
    binding_custom_scopes: Array.isArray(item && item.binding_custom_scopes) ? [...item.binding_custom_scopes] : item && item.binding_custom_scopes,
    binding_video_slots: Array.isArray(item && item.binding_video_slots) ? [...item.binding_video_slots] : item && item.binding_video_slots,
  }, videoCount);
  return copy.binding_scopes.map((scopeChoice, index) => {
    const customScope = clean(copy.binding_custom_scopes[index]);
    return {
      index,
      scopeChoice: clean(scopeChoice),
      customScope,
      scope: clean(scopeChoice) === "Custom scope"
        ? (customScope || (verifiedRegisteredSubtype(copy) === "Custom scope" ? "Custom scope" : ""))
        : clean(scopeChoice),
      color: clean(copy.color_picks[index]),
      videoSlot: normalizeMarkerVideo(copy.binding_video_slots[index], videoCount),
    };
  });
}

function normalizeMarkerVideo(value, videoCount) {
  const max = Math.max(1, Math.min(MAX_VIDEOS, Number(videoCount) || 1));
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.min(max, Math.round(parsed)));
}

function videoSlotCount(state) {
  const count = state && Array.isArray(state.videos) ? state.videos.length : 1;
  return Math.max(1, Math.min(MAX_VIDEOS, Number(count) || 1));
}

function activeVideoSlotChoices(state) {
  const videos = state && Array.isArray(state.videos) ? state.videos : [];
  const out = [];
  videos.forEach((item, index) => {
    const slot = String(Number(item && item.slot) || index + 1);
    if (isActiveVideo(item) && !out.includes(slot)) out.push(slot);
  });
  return out;
}

export function hmbImagePickerEnabled(state) {
  const videos = state && Array.isArray(state.videos) ? state.videos : [];
  return videos.some(isActiveVideo);
}

export function hmbImagePickerActionAvailability(state, item) {
  const enabled = hmbImagePickerEnabled(state);
  const pickCount = normalizeColorPicks(item && item.color_picks).length;
  return {
    enabled,
    canAdd: pickCount < MAX_COLOR_PICKS,
    canRemove: pickCount > 1,
  };
}

function editableVideoSlotChoices() {
  return Array.from({ length: MAX_VIDEOS }, (_item, index) => String(index + 1));
}

function resetImagesBoundToInactiveVideos(images, videos) {
  // Inactive-slot bindings are dormant, not disposable. Keep their exact
  // address so they can resume if that independent source returns.
  (images || []).forEach((item) => {
    if (!item || typeof item !== "object") return;
    normalizeImageBindingFields(item, MAX_VIDEOS);
  });
  return { images, changed: false };
}

function normalizePickerSlotSuppressions(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out = {};
  Object.entries(value).forEach(([rawSlot, rawPayloadId]) => {
    const slot = Number(rawSlot);
    const payloadId = clean(rawPayloadId);
    if (Number.isInteger(slot) && slot >= 1 && slot <= MAX_VIDEOS && payloadId) {
      out[String(slot)] = payloadId;
    }
  });
  return out;
}

export function hmbSuppressPickerVideoSlot(state, rawSlot) {
  if (!state || typeof state !== "object") return false;
  const slot = Number(rawSlot);
  if (!Number.isInteger(slot) || slot < 1 || slot > MAX_VIDEOS) return false;
  const picker = state.picker && typeof state.picker === "object" ? state.picker : {};
  const payloadId = clean(picker.run_id);
  if (!payloadId) return false;
  picker.slot_suppressions = normalizePickerSlotSuppressions(picker.slot_suppressions);
  picker.slot_suppressions[String(slot)] = payloadId;
  state.picker = picker;
  return true;
}

export function hmbReleasePickerVideoSlotSuppression(state, rawSlot) {
  if (!state || typeof state !== "object") return false;
  const slot = Number(rawSlot);
  if (!Number.isInteger(slot) || slot < 1 || slot > MAX_VIDEOS) return false;
  const picker = state.picker && typeof state.picker === "object" ? state.picker : {};
  const suppressions = normalizePickerSlotSuppressions(picker.slot_suppressions);
  const key = String(slot);
  if (!Object.prototype.hasOwnProperty.call(suppressions, key)) return false;
  delete suppressions[key];
  picker.slot_suppressions = suppressions;
  state.picker = picker;
  return true;
}

function enforceColorPickUniquenessByVideo(images, videoCount) {
  // Selectors exclude colors already used by the selected video. Preserve any
  // legacy duplicate state so validation can report it instead of deleting it.
  (images || []).forEach((item) => {
    if (!item) return;
    normalizeImageBindingFields(item, MAX_VIDEOS);
    item.color_picks = item.color_picks.map((color) => {
      const value = clean(color);
      return value;
    });
    normalizeImageBindingFields(item, MAX_VIDEOS);
  });
  return images;
}

function resetImageVideoBindingToPrimary(item, videoCount = MAX_VIDEOS) {
  if (!item || typeof item !== "object") return item;
  // Compatibility hook: a temporarily unavailable video must not erase or
  // redirect a user-authored binding.
  normalizeImageBindingFields(item, MAX_VIDEOS);
  return item;
}

function resetImageBindingsMatchingVideo(item, shouldReset, videoCount = MAX_VIDEOS) {
  if (!item || typeof item !== "object") return false;
  // Compatibility hook retained for older controller call sites. Bindings to
  // hidden/removed slots remain dormant and can become active again later.
  normalizeImageBindingFields(item, MAX_VIDEOS);
  return false;
}

function resetImagesBoundToVideoSlot(state, removedSlot) {
  // Preserve dormant user intent when a video is hidden, renamed, ignored, or
  // removed. UI availability follows active slots; stored addresses do not.
  (state && Array.isArray(state.images) ? state.images : []).forEach((item) => {
    if (!item || typeof item !== "object") return;
    normalizeImageBindingFields(item, MAX_VIDEOS);
  });
  enforceColorPickUniquenessByVideo(state && state.images, MAX_VIDEOS);
}

function migrateImage(item, slot) {
  const out = defaultImage(slot);
  if (!item || typeof item !== "object") return hmbPromptCarrySourceIdentity(null, out, "image");
  out.label = clean(item.label || item.name_override || item.description);
  out.present = Boolean(item.present) || Boolean(out.label);
  out.asset_id = clean(item.asset_id);
  out.asset_path = clean(item.asset_path);
  out.asset_library_id = clean(item.asset_library_id);
  out.asset_source_uid = clean(item.asset_source_uid || item.source_uid);
  out.asset_project_uid = clean(item.asset_project_uid);
  out.asset_selection_order = Math.max(
    0,
    Math.floor(Number(item.asset_selection_order || item.selection_order) || 0),
  );
  out.asset_source_type_candidate = clean(item.asset_source_type_candidate);
  out.asset_scope_candidate = clean(item.asset_scope_candidate);
  out.asset_color_pick_candidates = Array.isArray(item.asset_color_pick_candidates)
    ? item.asset_color_pick_candidates.map(clean).filter(Boolean)
    : [];
  out.asset_default_target = clean(item.asset_default_target);
  out.asset_managed = Boolean(item.asset_managed);
  out.asset_source_kind = ["project", "user"].includes(clean(item.asset_source_kind).toLowerCase())
    ? clean(item.asset_source_kind).toLowerCase()
    : "";
  out.asset_verified = Boolean(item.asset_verified && out.asset_source_kind === "project");
  out.source_type = clean(item.source_type) || out.source_type;
  out.custom_source_type = clean(item.custom_source_type || item.custom_main_type);
  out.scope = clean(item.scope);
  out.color_picks = normalizeColorPicks(item.color_picks || item.colorPick || item.color_pick || item.color || item.preview_color);
  out.binding_custom_scopes = normalizeParallelTextList(item.binding_custom_scopes || item.custom_scopes, out.color_picks.length, MAX_COLOR_PICKS);
  const legacyVideoSlots = normalizeBindingVideoSlots(item.binding_video_slots, item.marker_video || item.color_video || item.video_slot || item.video_number || item.video_pick, out.color_picks.length, MAX_VIDEOS);
  out.binding_video_slots = legacyVideoSlots;
  out.marker_video = legacyVideoSlots[0];
  const rawBindingScopes = item.binding_scopes != null ? item.binding_scopes : (item.sub_types != null ? item.sub_types : item.subtypes);
  const migrationScopes = normalizeBindingScopes(rawBindingScopes, out.scope, out.color_picks.length);
  const migrationPrimaryScope = verifiedRegisteredSubtype(out)
    || clean(migrationScopes[0])
    || clean(out.scope)
    || clean(migrationScopes.find((scope) => Boolean(clean(scope))) || "");
  out.owner = migrateTargetAuthority(item, [migrationPrimaryScope]);
  out.legacy_relationship_targets = legacyRelationshipTargets(item);
  out.preview_marker = clean(item.preview_marker || item.target_marker || item.replacement_target);
  out.picker_auto_color = clean(item.picker_auto_color);
  out.picker_auto_video = Number(item.picker_auto_video) || 0;
  out.picker_auto_source = clean(item.picker_auto_source);
  out.frame_range_enabled = Boolean(item.frame_range_enabled);
  out.frame_range_color_index = Math.floor(Number(item.frame_range_color_index) || 0);
  out.frame_range_bindings = normalizeFrameRangeBindings(item.frame_range_bindings, item.frame_range_binding);
  out.frame_range_selected_index = Number.isFinite(Number(item.frame_range_selected_index))
    ? Math.floor(Number(item.frame_range_selected_index))
    : -1;
  out.manual = item.manual !== false;

  const oldRole = clean(item.role);
  if (oldRole && !item.source_type) {
    const m = oldRole.match(/^Subject\s+(\d+)\s+Appearance$/);
    if (m) {
      out.source_type = "Character Appearance";
      out.owner = `Subject ${Number(m[1])}`;
      out.scope = "Full body / full appearance";
    } else if (oldRole === "Environment / Background") {
      out.source_type = "Environment / Background";
      out.owner = "Scene / Environment";
      out.scope = "Main background";
    } else if (oldRole === "Lighting / Atmosphere") {
      out.source_type = "Lighting / Atmosphere Reference";
      out.owner = "Global Look";
      out.scope = "Lighting mood only";
    } else if (oldRole === "Scene Scale / Composition") {
      out.source_type = "Scale / Composition Reference";
      out.owner = "Camera / Composition";
      out.scope = "Composition only";
    } else if (oldRole === "Prop / Set Reference") {
      out.source_type = "Prop / Accessory";
      out.scope = "Custom scope";
    } else if (oldRole === "Color / Look Reference") {
      out.source_type = "Color / Look Reference";
      out.owner = "Global Look";
      out.scope = "Render look only";
    } else if (oldRole === "Ignore / Unused") {
      out.source_type = "Ignore / Unused";
    }
  }
  if (IMAGE_SOURCE_TYPES.length && !IMAGE_SOURCE_TYPES.includes(out.source_type)) {
    const unknownSourceType = out.source_type;
    out.source_type = "Custom";
    out.custom_source_type = uniqueList([unknownSourceType, out.custom_source_type].filter(Boolean)).join(" | ");
  }
  if (subjectNumberFromOwner(out.owner)) out.owner = `image ${subjectNumberFromOwner(out.owner)}`;
  out.binding_scopes = normalizeBindingScopes(rawBindingScopes, out.scope, out.color_picks.length);
  normalizeImageBindingFields(out, MAX_VIDEOS);
  return hmbPromptCarrySourceIdentity(item, out, "image");
}

function migrateVideo(item, slot) {
  const out = defaultVideo(slot);
  if (!item || typeof item !== "object") return hmbPromptCarrySourceIdentity(null, out, "video");
  out.video_uid = clean(item.video_uid || item.source_uid);
  out.source_uid = out.video_uid;
  out.selection_order = Math.max(
    0,
    Math.floor(Number(item.selection_order || item.video_selection_order) || 0),
  );
  out.order_key = clean(item.order_key) || out.video_uid;
  out.picker_managed = Boolean(item.picker_managed || out.video_uid);
  out.label = clean(item.label || item.name_override || item.description);
  out.present = Boolean(item.present) || Boolean(out.label);
  out.source_type = clean(item.source_type) || out.source_type;
  out.custom_source_type = clean(item.custom_source_type || item.custom_video_type);
  out.control_role = canonicalVideoRole(item.control_role);
  out.custom_control_role = clean(item.custom_control_role || item.custom_video_role);
  out.keep_out = mergeUniqueNotes(
    item.keep_out,
    item.keepOut,
    item.exclusion_note,
    item.negative_prompt,
    item.video_marker,
    item.marker,
    item.description,
  );
  out.picker_auto_label = clean(item.picker_auto_label);
  out.picker_auto_depth = normalizePickerAutoDepth(item.picker_auto_depth);
  out.picker_auto_motion_guide = normalizePickerAutoMotionGuide(
    item.picker_auto_motion_guide,
  );
  out.picker_motion_guide_summary = normalizePickerMotionGuideSummary(
    item.picker_motion_guide_summary,
  );
  let companionKind = clean(item.picker_companion_kind).toLowerCase();
  if (!["depth", "motion_guide"].includes(companionKind)) {
    const mediaKind = clean(item.media_kind)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    if (mediaKind === "maya_depth_playblast" || Object.keys(out.picker_auto_depth).length) {
      companionKind = "depth";
    } else if (
      mediaKind === "maya_motion_guide"
      || Object.keys(out.picker_auto_motion_guide).length
    ) {
      companionKind = "motion_guide";
    }
  }
  out.picker_companion_kind = ["depth", "motion_guide"].includes(companionKind)
    ? companionKind
    : "";
  out.picker_companion_source_slot = normalizePickerCompanionSourceSlot(item);
  out.picker_companion_source_uid = clean(
    item.picker_companion_source_uid
    || item.source_video_uid
    || item.companion_of_video_uid
    || item.companion_video_uid,
  );
  out.picker_companion_validated = Boolean(
    item.picker_companion_validated
    || Object.keys(out.picker_auto_depth).length
    || Object.keys(out.picker_auto_motion_guide).length,
  );
  out.manual = Boolean(item.manual) || slot === 1;

  const oldRole = clean(item.role);
  if (oldRole && !item.source_type) {
    if (oldRole === "Maya Preview / Strongest Unified Shot-Control Source") {
      out.source_type = "Maya Preview / Playblast";
      out.control_role = "";
    } else if (oldRole === "Motion / Timing Reference") {
      out.source_type = "Motion Reference";
      out.control_role = "Local Motion Detail Only";
    } else if (oldRole === "Camera / Layout / Depth Reference") {
      out.source_type = "Camera / Layout Reference";
      out.control_role = "Spatial Alignment Verification Only";
    } else if (oldRole === "Performance Reference") {
      out.source_type = "Motion Reference";
      out.control_role = "Local Motion Detail Only";
    } else if (oldRole === "Reference Video Only") {
      out.source_type = "Custom";
      out.control_role = "Context Only";
    } else if (oldRole === "Ignore / Unused") {
      out.source_type = "Ignore / Unused";
    }
  }
  if (!VIDEO_SOURCE_TYPES.includes(out.source_type)) {
    const unknownSourceType = out.source_type;
    out.source_type = "Custom";
    out.custom_source_type = uniqueList([unknownSourceType, out.custom_source_type].filter(Boolean)).join(" | ");
  }
  if (!VIDEO_CONTROL_ROLES.includes(out.control_role)) {
    const unknownControlRole = out.control_role;
    out.control_role = "Custom Role";
    out.custom_control_role = uniqueList([unknownControlRole, out.custom_control_role].filter(Boolean)).join(" | ");
  }
  // Keep the factual Maya preview type but remove the stale combined
  // authority. Primary is valid only for an explicit Unified type.
  if (
    out.source_type === "Maya Preview / Playblast"
    && out.control_role === "Primary Unified Shot Control"
  ) {
    out.control_role = "";
    out.custom_control_role = "";
  }
  return hmbPromptCarrySourceIdentity(item, out, "video");
}

function hasVideoMeaning(item) {
  if (!item) return false;
  return Boolean(item.present) || Boolean(clean(item.video_uid || item.source_uid)) || Boolean(clean(item.label)) || Boolean(clean(item.keep_out)) || Boolean(clean(item.control_role)) || Boolean(clean(item.custom_source_type)) || Boolean(clean(item.custom_control_role)) || clean(item.source_type) !== "Role Required / Select Video Type";
}

function hasImageMeaning(item) {
  if (!item) return false;
  return Boolean(
    item.present
    || clean(item.label)
    || clean(item.asset_id)
    || clean(item.asset_path)
    || clean(item.asset_source_uid)
    || clean(item.asset_library_id)
    || item.asset_managed
    || item.asset_verified
    || !["", "Role Required / Select Source Type"].includes(clean(item.source_type))
    || clean(item.custom_source_type)
    || clean(item.owner)
    || (item.legacy_relationship_targets || []).some((value) => clean(value))
    || (item.binding_scopes || []).some((value) => clean(value))
    || (item.binding_custom_scopes || []).some((value) => clean(value))
    || (item.color_picks || []).some((value) => clean(value))
    || clean(item.preview_marker)
    || item.frame_range_enabled
  );
}

function normalizeRows(rows, kind, maxCount) {
  const source = Array.isArray(rows) ? rows.slice(0, maxCount) : [];
  const migrated = source.map((item, idx) => kind === "image" ? migrateImage(item, idx + 1) : migrateVideo(item, idx + 1));
  if (!migrated.length) {
    if (kind === "image") migrated.push(defaultImage(1), defaultImage(2), defaultImage(3), defaultImage(4));
    else migrated.push(defaultVideo(1));
  }

  if (kind === "video") {
    let lastVisible = 0;
    migrated.forEach((item, idx) => {
      if (idx === 0 || item.manual || hasVideoMeaning(item)) lastVisible = idx;
    });
    const visibleCount = Math.max(1, Math.min(maxCount, lastVisible + 1));
    const out = [];
    for (let i = 1; i <= visibleCount; i += 1) {
      const row = migrateVideo(migrated[i - 1] || {}, i);
      row.slot = i;
      row.token = `@video${i}`;
      row.name = `VIDEO_${String(i).padStart(2, "0")}`;
      row.present = hasVideoMeaning(row);
      row.manual = row.manual || i === 1;
      out.push(row);
    }
    return out;
  }

  // Image rows are user-managed. New nodes start with four rows, X deletes any
  // selected row and promotes the following rows, and + adds rows up to
  // MAX_IMAGES. Field edits never create another image row automatically.
  const visibleCount = Math.max(1, Math.min(maxCount, migrated.length));
  const out = [];
  for (let i = 1; i <= visibleCount; i += 1) {
    const row = migrateImage(migrated[i - 1] || {}, i);
    row.slot = i;
    row.token = `@image${i}`;
    row.name = `IMAGE_${String(i).padStart(2, "0")}`;
    row.present = hasImageMeaning(row);
    row.manual = true;
    out.push(row);
  }
  return out;
}

function normalizeDormantVideoRows(value, managed) {
  if (!Array.isArray(value)) return [];
  const rows = [];
  const seenUids = new Set();
  value.forEach((raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return;
    const row = migrateVideo(raw, rows.length + 1);
    const uid = clean(row.video_uid || row.source_uid);
    if (managed) {
      if (!uid || seenUids.has(uid)) return;
      seenUids.add(uid);
      row.video_uid = uid;
      row.source_uid = uid;
      row.picker_managed = true;
    } else {
      if (uid || row.picker_managed) return;
      row.picker_managed = false;
      row.selection_order = 0;
      row.order_key = "";
    }
    row.slot = 0;
    row.token = "";
    row.name = "";
    rows.push(row);
  });
  return rows;
}

function isActiveImage(item) {
  return hasImageMeaning(item) && item.source_type !== "Ignore / Unused";
}

function isActiveImageForState(item, state) {
  const connectionOwned = Boolean(state?.image_asset?.enabled);
  return isActiveImage(item) && (!connectionOwned || Boolean(item?.asset_managed));
}

function normalizeDormantImageRows(value, assetRows = false) {
  if (!Array.isArray(value)) return [];
  const limit = assetRows ? MAX_IMAGES * 4 : MAX_IMAGES;
  return value.slice(0, limit).flatMap((raw, index) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const row = migrateImage(raw, index + 1);
    row.manual = true;
    if (assetRows) {
      if (!clean(row.asset_source_uid || row.asset_library_id)) return [];
      row.asset_managed = true;
    } else {
      row.asset_managed = false;
      row.asset_verified = false;
      row.asset_source_kind = "";
      row.asset_selection_order = 0;
    }
    return [row];
  });
}

function isActiveVideo(item) {
  return hasVideoMeaning(item) && item.source_type !== "Ignore / Unused";
}

function enforceSingleActiveVideoUnified(videos) {
  // Legacy normalization hook. Picker-authored rows already carry explicit
  // roles; manual rows must never be rewritten merely because of slot order.
  return videos;
}

function normalizeUi(input) {
  const source = input && typeof input === "object" ? input : {};
  const compatible = clean(source.resize_mode) === HMB_RESIZE_MODE;
  const rawHeights = compatible && source.group_heights && typeof source.group_heights === "object" ? source.group_heights : {};
  const headerLayoutVersion = Math.max(0, Math.floor(Number(source.header_layout_version) || 0));
  const legacyDefaultLayout = compatible
    && headerLayoutVersion < HMB_HEADER_LAYOUT_VERSION
    && Math.round(Number(rawHeights.imageSources)) === HMB_LEGACY_IMAGE_SOURCES_DEFAULT_HEIGHT
    && ["imageText", "videoSources", "videoText"].every((key) => (
      rawHeights[key] == null
      || Math.round(Number(rawHeights[key])) === HMB_GROUP_START_HEIGHTS[key]
    ));
  const group_heights = {};
  Object.keys(HMB_GROUP_MIN_HEIGHTS).forEach((key) => {
    const value = key === "imageSources" && legacyDefaultLayout
      ? HMB_GROUP_START_HEIGHTS.imageSources
      : Number(rawHeights[key]);
    const minHeight = HMB_GROUP_MIN_HEIGHTS[key];
    if (Number.isFinite(value) && value >= minHeight && value <= HMB_GROUP_MAX_HEIGHT) {
      group_heights[key] = Math.round(value);
    }
  });

  const rawTextareaHeights = compatible && source.textarea_heights && typeof source.textarea_heights === "object" ? source.textarea_heights : {};
  const textarea_heights = {};
  Object.entries(rawTextareaHeights).forEach(([key, rawValue]) => {
    if (!/^video:(?:10|[1-9]):keep_out$/.test(clean(key))) return;
    const value = Number(rawValue);
    if (Number.isFinite(value) && value >= HMB_KEEP_OUT_MIN_HEIGHT && value <= HMB_KEEP_OUT_MAX_HEIGHT) {
      textarea_heights[key] = Math.round(value);
    }
  });

  const language = clean(source.language).toLowerCase() === "en" ? "en" : "ko";
  return {
    group_heights,
    textarea_heights,
    resize_mode: HMB_RESIZE_MODE,
    header_layout_version: HMB_HEADER_LAYOUT_VERSION,
    language,
  };
}

function boundedClean(value, maxChars = MAX_IDENTIFIER_CHARS) {
  return clean(value).slice(0, Math.max(0, Number(maxChars) || 0));
}

function normalizeManualVideoContextFrameRanges(value) {
  const bounded = (Array.isArray(value) ? value : [])
    .slice(0, MAX_FRAME_RANGES_PER_BINDING)
    .flatMap((raw) => {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
      const start = normalizeFrameDomainEndpoint(raw.start);
      const end = normalizeFrameDomainEndpoint(raw.end);
      return start === null || end === null ? [] : [{ start, end }];
    });
  return normalizeFrameRanges(bounded);
}

function normalizeManualVideoContextSelectedRange(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return -1;
  return Math.max(
    -1,
    Math.min(MAX_FRAME_RANGES_PER_BINDING - 1, Math.floor(parsed)),
  );
}

function manualVideoContextFrameBindingInput(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const out = {
    video_slot: boundedClean(value.video_slot || value.video),
    color_pick: boundedClean(value.color_pick || value.color),
    origin: boundedClean(value.origin) || "manual",
    ranges: normalizeManualVideoContextFrameRanges(value.ranges),
  };
  if (Object.prototype.hasOwnProperty.call(value, "enabled")) {
    out.enabled = Boolean(value.enabled);
  }
  if (
    Object.prototype.hasOwnProperty.call(value, "start_frame")
    || Object.prototype.hasOwnProperty.call(value, "manual_start_frame")
  ) {
    out.start_frame = normalizeFrameDomainEndpoint(
      Object.prototype.hasOwnProperty.call(value, "start_frame")
        ? value.start_frame
        : value.manual_start_frame,
    );
  }
  if (
    Object.prototype.hasOwnProperty.call(value, "end_frame")
    || Object.prototype.hasOwnProperty.call(value, "manual_end_frame")
  ) {
    out.end_frame = normalizeFrameDomainEndpoint(
      Object.prototype.hasOwnProperty.call(value, "end_frame")
        ? value.end_frame
        : value.manual_end_frame,
    );
  }
  return out;
}

function normalizeManualVideoContextFrameBindings(value, legacyBinding = null) {
  const limited = {};
  if (value && typeof value === "object" && !Array.isArray(value)) {
    let inspected = 0;
    for (const rawKey in value) {
      if (!Object.prototype.hasOwnProperty.call(value, rawKey)) continue;
      if (inspected >= MAX_COLOR_PICKS) break;
      inspected += 1;
      const binding = manualVideoContextFrameBindingInput(value[rawKey]);
      if (!binding) continue;
      limited[boundedClean(rawKey, (MAX_IDENTIFIER_CHARS * 2) + 32)] = binding;
    }
  }
  const normalized = normalizeFrameRangeBindings(
    limited,
    manualVideoContextFrameBindingInput(legacyBinding),
  );
  const out = {};
  for (const [key, binding] of Object.entries(normalized)) {
    if (Object.keys(out).length >= MAX_COLOR_PICKS) break;
    out[key] = {
      video_slot: boundedClean(binding.video_slot),
      color_pick: boundedClean(binding.color_pick),
      enabled: Boolean(binding.enabled),
      origin: boundedClean(binding.origin) || "manual",
      ranges: normalizeManualVideoContextFrameRanges(binding.ranges),
      start_frame: normalizeFrameDomainEndpoint(binding.start_frame),
      end_frame: normalizeFrameDomainEndpoint(binding.end_frame),
    };
  }
  return out;
}

function normalizeManualVideoContextImageFields(value, index) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const colorPicks = normalizeColorPicks(source.color_picks)
    .map((item) => boundedClean(item));
  const bindingScopes = normalizeBindingScopes(source.binding_scopes, "", colorPicks.length)
    .map((item) => boundedClean(item));
  const bindingCustomScopes = normalizeParallelTextList(
    source.binding_custom_scopes,
    colorPicks.length,
    MAX_COLOR_PICKS,
  ).map((item) => boundedClean(item));
  const bindingVideoSlots = normalizeBindingVideoSlots(
    source.binding_video_slots,
    source.marker_video,
    colorPicks.length,
    MAX_VIDEOS,
  );
  const boundedBindings = normalizeManualVideoContextFrameBindings(
    source.frame_range_bindings,
    source.frame_range_binding,
  );
  const normalizedItem = migrateImage({
    color_picks: colorPicks,
    binding_scopes: bindingScopes,
    binding_custom_scopes: bindingCustomScopes,
    binding_video_slots: bindingVideoSlots,
    marker_video: normalizeMarkerVideo(source.marker_video, MAX_VIDEOS),
    preview_marker: boundedClean(source.preview_marker),
    picker_auto_video: Math.max(
      0,
      Math.min(MAX_VIDEOS, Math.floor(Number(source.picker_auto_video) || 0)),
    ),
    picker_auto_color: boundedClean(source.picker_auto_color),
    picker_auto_source: boundedClean(source.picker_auto_source),
    frame_range_enabled: Boolean(source.frame_range_enabled),
    frame_range_color_index: Math.max(
      0,
      Math.min(MAX_COLOR_PICKS - 1, Math.floor(Number(source.frame_range_color_index) || 0)),
    ),
    frame_range_bindings: boundedBindings,
    frame_range_binding: null,
    frame_range_selected_index: normalizeManualVideoContextSelectedRange(
      source.frame_range_selected_index,
    ),
  }, index + 1);
  const normalizedBindings = normalizeManualVideoContextFrameBindings(
    normalizedItem.frame_range_bindings,
  );
  const normalizedCurrentBinding = Object.values(
    normalizeManualVideoContextFrameBindings({}, normalizedItem.frame_range_binding),
  )[0] || null;
  const fields = {
    color_picks: normalizedItem.color_picks.map((item) => boundedClean(item)).slice(0, MAX_COLOR_PICKS),
    binding_scopes: normalizedItem.binding_scopes.map((item) => boundedClean(item)).slice(0, MAX_COLOR_PICKS),
    binding_custom_scopes: normalizedItem.binding_custom_scopes.map((item) => boundedClean(item)).slice(0, MAX_COLOR_PICKS),
    binding_video_slots: normalizedItem.binding_video_slots.slice(0, MAX_COLOR_PICKS),
    marker_video: normalizeMarkerVideo(normalizedItem.marker_video, MAX_VIDEOS),
    preview_marker: boundedClean(normalizedItem.preview_marker),
    picker_auto_video: Math.max(
      0,
      Math.min(MAX_VIDEOS, Math.floor(Number(normalizedItem.picker_auto_video) || 0)),
    ),
    picker_auto_color: boundedClean(normalizedItem.picker_auto_color),
    picker_auto_source: boundedClean(normalizedItem.picker_auto_source),
    frame_range_enabled: Boolean(normalizedItem.frame_range_enabled),
    frame_range_color_index: Math.max(
      0,
      Math.min(MAX_COLOR_PICKS - 1, Math.floor(Number(normalizedItem.frame_range_color_index) || 0)),
    ),
    frame_range_bindings: normalizedBindings,
    frame_range_binding: normalizedCurrentBinding,
    frame_range_selected_index: normalizeManualVideoContextSelectedRange(
      normalizedItem.frame_range_selected_index,
    ),
  };
  return Object.fromEntries(
    MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS.map((field) => [field, fields[field]]),
  );
}

function normalizeManualVideoContextSnapshot(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const textSource = source.text && typeof source.text === "object" && !Array.isArray(source.text)
    ? source.text
    : {};
  const text = Object.fromEntries(MANUAL_VIDEO_CONTEXT_TEXT_FIELDS.map((key) => [
    key,
    boundedClean(
      textSource[key],
      key === "VIDEO_VFX" ? MAX_VIDEO_VFX_CHARS : MAX_DESCRIPTION_CHARS,
    ),
  ]));
  const images = [];
  const rawImages = Array.isArray(source.images) ? source.images.slice(0, MAX_IMAGES) : [];
  rawImages.forEach((raw, fallbackIndex) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return;
    const parsedIndex = Number(raw.index);
    const index = Number.isInteger(parsedIndex)
      ? Math.max(0, Math.min(MAX_IMAGES - 1, parsedIndex))
      : fallbackIndex;
    images.push({
      identity: boundedClean(raw.identity) || `slot:${index + 1}`,
      index,
      fields: normalizeManualVideoContextImageFields(raw.fields, index),
    });
  });
  const textareaHeights = normalizeUi({
    resize_mode: HMB_RESIZE_MODE,
    textarea_heights: source.textarea_heights && typeof source.textarea_heights === "object"
      ? source.textarea_heights
      : {},
  }).textarea_heights;
  return { text, images, textarea_heights: textareaHeights };
}

function normalizeManualVideoContext(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  if (
    value.version !== MANUAL_VIDEO_CONTEXT_VERSION
    || !value.before
    || typeof value.before !== "object"
    || Array.isArray(value.before)
    || !value.after
    || typeof value.after !== "object"
    || Array.isArray(value.after)
  ) return {};
  return {
    version: MANUAL_VIDEO_CONTEXT_VERSION,
    before: normalizeManualVideoContextSnapshot(value.before),
    after: normalizeManualVideoContextSnapshot(value.after),
  };
}

function hmbTextareaKey(kind, indexOrKey, field) {
  return `${String(kind || "text")}:${String(indexOrKey || "0")}:${String(field || "value")}`;
}

function hmbIsKeepOutTextareaKey(key) {
  return /^video:(?:10|[1-9]):keep_out$/.test(clean(key));
}

function hmbTextareaHeight(state, key) {
  if (!hmbIsKeepOutTextareaKey(key)) return null;
  const source = state && state.ui && state.ui.textarea_heights ? state.ui.textarea_heights : {};
  const stored = Number(source[key]);
  const value = Number.isFinite(stored) ? stored : HMB_KEEP_OUT_DEFAULT_HEIGHT;
  return Math.max(HMB_KEEP_OUT_MIN_HEIGHT, Math.min(HMB_KEEP_OUT_MAX_HEIGHT, Math.round(value)));
}

function hmbTextareaHeightStyle(state, key) {
  const height = hmbTextareaHeight(state, key);
  if (!Number.isFinite(height)) return "";
  return `style="height:${height}px;min-height:${height}px;max-height:${height}px"`;
}

function hmbTextareaAttrs(state, key) {
  return `data-textarea-key="${escapeHtml(key)}" ${hmbTextareaHeightStyle(state, key)}`;
}

function groupHeightStyle(state, key) {
  const heights = state && state.ui && state.ui.group_heights ? state.ui.group_heights : {};
  const stored = Number(heights[key]);
  const fallback = Number(HMB_GROUP_DEFAULT_HEIGHTS[key]);
  const value = Number.isFinite(stored) ? stored : fallback;
  const minHeight = HMB_GROUP_MIN_HEIGHTS[key] || 120;
  const height = Math.max(minHeight, Math.min(HMB_GROUP_MAX_HEIGHT, Math.round(value || minHeight)));
  return `style="flex:0 0 ${height}px;flex-basis:${height}px;min-height:${minHeight}px"`;
}

function migrateText(input) {
  const textInput = input && typeof input === "object" ? input : {};
  const out = Object.fromEntries(TEXT_FIELDS.map(([key]) => [key, clean(textInput[key])]));
  const legacyParts = [];
  const addPart = (label, value) => {
    const v = clean(value);
    if (!v) return;
    const line = label ? `${label}: ${v}` : v;
    if (!legacyParts.includes(line)) legacyParts.push(line);
  };
  addPart("", textInput.VIDEO_VFX);
  addPart("Shot VFX note", textInput.FX_ADDITIONAL_INSTRUCTION);
  const missing = clean(textInput.FALLBACK_MISSING_FUNCTION);
  const instruction = clean(textInput.FALLBACK_INSTRUCTION);
  if (missing || instruction) {
    const fallback = [missing ? `Missing function = ${missing}` : "", instruction ? `Instruction = ${instruction}` : ""].filter(Boolean).join(" / ");
    addPart("Fallback only if source is missing", fallback);
  }
  if (legacyParts.length) out.VIDEO_VFX = legacyParts.join("\n");
  return out;
}

function normalizeShotSelection(value) {
  const source = value && typeof value === "object" ? value : {};
  const shotUuid = clean(source.shot_uuid).slice(0, 128);
  const channelUuid = clean(source.channel_uuid).slice(0, 128);
  const bound = Boolean(shotUuid && channelUuid);
  const number = bound
    ? Math.max(1, Math.min(MAX_SHOTS, Math.floor(Number(source.number) || 1)))
    : 1;
  return {
    shot_uuid: bound ? shotUuid : "",
    channel_uuid: bound ? channelUuid : "",
    name: bound ? (clean(source.name).slice(0, 128) || `Shot ${number}`) : "Only",
    number,
    selected_source_uids: bound ? uniqueList(
      Array.isArray(source.selected_source_uids)
        ? source.selected_source_uids.map(clean).filter(Boolean)
        : [],
    ).slice(0, MAX_SHOT_IMAGES) : [],
  };
}

function normalizeShotCatalog(value) {
  const source = Array.isArray(value) ? value : [];
  const result = [];
  const uuids = new Set();
  const numbers = new Set();
  source.forEach((raw) => {
    if (!raw || typeof raw !== "object" || result.length >= MAX_SHOTS) return;
    const shot = normalizeShotSelection(raw);
    if (!shot.shot_uuid || uuids.has(shot.shot_uuid) || numbers.has(shot.number)) return;
    uuids.add(shot.shot_uuid);
    numbers.add(shot.number);
    result.push(shot);
  });
  return result.sort((left, right) => left.number - right.number || left.shot_uuid.localeCompare(right.shot_uuid));
}

function normalizeShotRouting(value) {
  const source = value && typeof value === "object" ? value : {};
  const result = {
    publisher_instance_uuid: clean(source.publisher_instance_uuid),
    channel_uuid: clean(source.channel_uuid),
    generation: normalizeSourceSyncRevision(source.generation),
    metadata_sha256: clean(source.metadata_sha256),
    media_sha256: clean(source.media_sha256),
    media_count: Math.max(0, Math.floor(Number(source.media_count) || 0)),
    media_order_sha256: clean(source.media_order_sha256),
  };
  return Object.values(result).some(Boolean) ? result : {};
}

function normalizeShotCatalogRouting(value) {
  const source = value && typeof value === "object" ? value : {};
  const result = {
    publisher_instance_uuid: clean(source.publisher_instance_uuid),
    channel_uuid: clean(source.channel_uuid),
    generation: normalizeSourceSyncRevision(source.generation),
    metadata_sha256: clean(source.metadata_sha256),
  };
  return Object.values(result).some(Boolean) ? result : {};
}

export function hmbApplyRemoteShotCatalog(state, detail) {
  if (!state || typeof state !== "object" || !detail || typeof detail !== "object") {
    return { changed: false, state };
  }
  if (
    detail.schema !== "hmb-shot-routing-ui-catalog"
    || detail.version !== 1
    || detail.publisher_kind !== "image_asset"
  ) return { changed: false, state };
  const detailKeys = Object.keys(detail).sort().join(",");
  if (detailKeys !== [
    "channel_uuid",
    "generation",
    "publisher_instance_uuid",
    "publisher_kind",
    "schema",
    "shots",
    "version",
  ].sort().join(",")) return { changed: false, state };
  const channelUuid = clean(detail.channel_uuid);
  const publisherUuid = clean(detail.publisher_instance_uuid);
  if (
    !channelUuid
    || channelUuid.length > 128
    || !publisherUuid
    || publisherUuid.length > 128
    || !Array.isArray(detail.shots)
  ) {
    return { changed: false, state };
  }
  if (
    !Number.isSafeInteger(detail.generation)
    || detail.generation < 0
    || detail.shots.length < 1
    || detail.shots.length > MAX_SHOTS
    || detail.shots.some((item) => (
      !item
      || typeof item !== "object"
      || Object.keys(item).sort().join(",") !== ["name", "number", "revision", "shot_uuid"].join(",")
      || !clean(item.shot_uuid)
      || !clean(item.name)
      || clean(item.name).length > 128
      || !Number.isSafeInteger(item.number)
      || item.number < 1
      || item.number > MAX_SHOTS
      || !Number.isSafeInteger(item.revision)
      || item.revision < 0
    ))
  ) return { changed: false, state };
  const detailShotUuids = detail.shots.map((item) => clean(item.shot_uuid));
  const detailShotNumbers = detail.shots.map((item) => item.number);
  if (
    new Set(detailShotUuids).size !== detailShotUuids.length
    || new Set(detailShotNumbers).size !== detailShotNumbers.length
  ) return { changed: false, state };
  const currentShot = normalizeShotSelection(state.shot);
  const currentRouting = normalizeShotCatalogRouting(
    state?.image_asset?.shot_catalog_routing,
  );
  // Window events are process-global and carry no flow identity. They may
  // refresh an already backend-verified subscription, but they must never
  // create durable Shot identity for a blank Prompt. The Python graph helper
  // performs same-flow publisher discovery and adopts Shot 1 authoritatively.
  if (
    !currentShot.channel_uuid
    || !currentShot.shot_uuid
    || !currentRouting.publisher_instance_uuid
  ) return { changed: false, state };
  if (currentShot.channel_uuid !== channelUuid) {
    return { changed: false, state };
  }
  if (currentRouting.publisher_instance_uuid !== publisherUuid) {
    return { changed: false, state };
  }
  if (detail.generation !== currentRouting.generation) {
    return { changed: false, state };
  }
  const previousCatalog = normalizeShotCatalog(state?.image_asset?.shot_catalog);
  const publishedIdentity = detail.shots.map((item) => (
    `${clean(item.shot_uuid)}\u0000${item.number}\u0000${clean(item.name)}`
  ));
  const verifiedIdentity = previousCatalog.map((item) => (
    `${item.shot_uuid}\u0000${item.number}\u0000${item.name}`
  ));
  if (JSON.stringify(publishedIdentity) !== JSON.stringify(verifiedIdentity)) {
    return { changed: false, state };
  }
  // The browser catalog is discovery/paint notification only. Backend props
  // already contain the same-flow validated catalog and remain the sole
  // durable authority, so this event never emits another state transaction.
  return { changed: false, state };
}

export function normalizeState(input) {
  const imageTaxonomy = applyImageTaxonomy(input || {});
  const videos = normalizeRows(input && input.videos, "video", MAX_VIDEOS);

  // Legacy states may still contain old global video-control text.
  // That function now belongs to the fourth video field, Keep Out. Preserve it on
  // @video1 instead of emitting it as VIDEO VFX.
  const legacyTextInput = input && typeof input.text === "object" ? input.text : {};
  const legacyKeepOut = mergeUniqueNotes(legacyTextInput.VIDEO_CONTEXT, legacyTextInput.VIDEO_MARKER, legacyTextInput.VIDEO_DESCRIPTION);
  if (legacyKeepOut && videos.length) {
    videos[0].keep_out = mergeUniqueNotes(videos[0].keep_out, legacyKeepOut);
  }

  enforceSingleActiveVideoUnified(videos);
  const imageReset = resetImagesBoundToInactiveVideos(normalizeRows(input && input.images, "image", MAX_IMAGES), videos);
  const images = enforceColorPickUniquenessByVideo(imageReset.images, videos.length);
  const imageAssetConnected = Boolean(input?.image_asset?.enabled);
  const activeImageCount = images.filter(
    (item) => isActiveImage(item) && (!imageAssetConnected || Boolean(item?.asset_managed)),
  ).length;
  const activeVideoCount = videos.filter(isActiveVideo).length;
  const textInput = input && typeof input.text === "object" ? input.text : {};
  const text = migrateText(textInput);
  const pickerInput = input && typeof input.picker === "object" ? input.picker : {};
  const pickerMarkers = Array.isArray(pickerInput.markers) ? pickerInput.markers.filter((item) => item && typeof item === "object") : [];
  const picker = {
    enabled: Boolean(pickerInput.enabled),
    awaiting_data: Boolean(pickerInput.awaiting_data),
    run_id: clean(pickerInput.run_id),
    selection_id: clean(pickerInput.selection_id),
    selected_video_count: Math.max(
      0,
      Math.min(MAX_VIDEOS, Math.floor(Number(pickerInput.selected_video_count) || 0)),
    ),
    ordered_video_uids: uniqueList(
      (Array.isArray(pickerInput.ordered_video_uids)
        ? pickerInput.ordered_video_uids
        : [])
        .map(clean)
        .filter(Boolean),
    ).slice(0, MAX_VIDEOS),
    order_managed: Boolean(pickerInput.order_managed),
    dormant_video_rows: normalizeDormantVideoRows(
      pickerInput.dormant_video_rows,
      true,
    ),
    dormant_manual_rows: normalizeDormantVideoRows(
      pickerInput.dormant_manual_rows,
      false,
    ),
    manual_video_context: normalizeManualVideoContext(pickerInput.manual_video_context),
    slot_suppressions: normalizePickerSlotSuppressions(pickerInput.slot_suppressions),
    scene: clean(pickerInput.scene),
    video_path: clean(pickerInput.video_path),
    camera: clean(pickerInput.camera),
    markers: pickerMarkers,
    frame_metadata: normalizeFrameMetadata(pickerInput.frame_metadata),
    contract_errors: (Array.isArray(pickerInput.contract_errors)
      ? pickerInput.contract_errors
      : []).map(clean).filter(Boolean),
    matched_images: Number(pickerInput.matched_images) || 0,
    shot_catalog: normalizeShotCatalog(pickerInput.shot_catalog),
    shot_routing: normalizeShotRouting(pickerInput.shot_routing),
  };
  const imageAssetInput = input && typeof input.image_asset === "object"
    ? input.image_asset
    : {};
  const imageAsset = {
    enabled: Boolean(imageAssetInput.enabled),
    project_id: clean(imageAssetInput.project_id),
    project_uid: clean(imageAssetInput.project_uid),
    project_root: clean(imageAssetInput.project_root),
    selection_id: clean(imageAssetInput.selection_id),
    selected_assets: Math.max(0, Math.floor(Number(imageAssetInput.selected_assets) || 0)),
    verified_assets: Math.max(0, Math.floor(Number(imageAssetInput.verified_assets) || 0)),
    imported_images: Math.max(0, Math.floor(Number(imageAssetInput.imported_images) || 0)),
    ordered_source_uids: uniqueList(
      Array.isArray(imageAssetInput.ordered_source_uids)
        ? imageAssetInput.ordered_source_uids
        : [],
    ).slice(0, MAX_IMAGES),
    order_managed: Boolean(imageAssetInput.order_managed),
    dormant_manual_rows: normalizeDormantImageRows(
      imageAssetInput.dormant_manual_rows,
      false,
    ),
    dormant_asset_rows: normalizeDormantImageRows(
      imageAssetInput.dormant_asset_rows,
      true,
    ),
    shot_catalog: normalizeShotCatalog(imageAssetInput.shot_catalog),
    shot_catalog_routing: normalizeShotCatalogRouting(
      imageAssetInput.shot_catalog_routing,
    ),
    shot_routing: normalizeShotRouting(imageAssetInput.shot_routing),
  };
  return {
    schema: "prompt-library-state",
    mode: "prompt_only_role_dashboard",
    source_sync_revision: normalizeSourceSyncRevision(input?.source_sync_revision),
    [UI_EDIT_REVISION_KEY]: normalizeUiEditRevision(input?.[UI_EDIT_REVISION_KEY]),
    image_taxonomy: imageTaxonomy,
    shot: normalizeShotSelection(input && input.shot),
    images,
    videos,
    text,
    source_intent_fallbacks: normalizeSourceIntentFallbacks(
      input && input.source_intent_fallbacks,
    ),
    ui: normalizeUi(input && input.ui),
    picker,
    image_asset: imageAsset,
    status: {
      active_images: activeImageCount,
      active_videos: activeVideoCount,
      visible_image_slots: images.length,
      visible_video_slots: videos.length,
      max_images: MAX_IMAGES,
      max_videos: MAX_VIDEOS,
    },
  };
}

function emit(props, state, container = null) {
  return hmbEmitLocalPromptState(container, props, state);
}

export function hmbEmitPromptState(container, props, state) {
  return emit(props, state, container);
}

function hmbClearImmediateStateCommit(container) {
  if (!container) return false;
  const timer = container.__hmbPromptLibraryCommitTimer;
  try { if (timer) clearTimeout(timer); } catch (_e) {}
  try { container.__hmbPromptLibraryCommitTimer = null; } catch (_e) {}
  const pending = Boolean(container.__hmbPromptLibraryCommitPending);
  try { container.__hmbPromptLibraryCommitPending = false; } catch (_e) {}
  return pending;
}

export function hmbScheduleImmediateStateCommit(container, props, state) {
  if (!container) return;
  // Any newly edited draft supersedes an exact-payload transport retry that
  // may still be waiting from the preceding publication.
  hmbInvalidatePromptPublication(container);
  hmbCaptureTextEditingState(container);
  const active = typeof document !== "undefined" ? document.activeElement : null;
  if (active && container.contains?.(active)) {
    hmbRememberPromptDirtyTextControl(container, active, state);
  }
  hmbClearImmediateStateCommit(container);
  container.__hmbPromptLibraryCommitPending = true;
  const timer = setTimeout(() => {
    if (container.__hmbPromptLibraryCommitTimer !== timer) return;
    container.__hmbPromptLibraryCommitTimer = null;
    if (hmbShouldDeferPromptTextCommit(container)) {
      // A composing IME value is not final. Keep one trailing commit armed;
      // ordinary focus is intentionally not a blocker because users can run a
      // downstream node without blurring the current Prompt field first.
      hmbScheduleImmediateStateCommit(container, props, state);
      return;
    }
    container.__hmbPromptLibraryCommitPending = false;
    hmbCaptureUiBeforeStateEmit(container, state);
    // Register the exact local value before calling the host. A synchronous
    // props echo can then be consumed without replacing the focused control.
    hmbEmitLocalPromptState(container, props, state);
  }, 260);
  container.__hmbPromptLibraryCommitTimer = timer;
}

export function hmbFlushImmediateStateCommit(container, props, state) {
  if (!hmbClearImmediateStateCommit(container)) return false;
  hmbCaptureUiBeforeStateEmit(container, state);
  hmbEmitLocalPromptState(container, props, state);
  return true;
}

function hmbIsEditableTextControl(element) {
  if (!element || typeof element.matches !== "function") return false;
  return element.matches('textarea, input:not([type]), input[type="text"], input[type="search"]');
}


export function hmbShouldDeferPromptTextCommit(container) {
  return Boolean(container && container.__hmbPromptLibraryCompositionActive);
}

export function hmbReleasePromptCompositionLatch(container) {
  if (!container) return false;
  const wasActive = Boolean(container.__hmbPromptLibraryCompositionActive);
  try { container.__hmbPromptLibraryCompositionActive = false; } catch (_e) {}
  return wasActive;
}

function hmbTextControlIdentity(element) {
  if (!hmbIsEditableTextControl(element)) return "";
  const textKey = element.getAttribute("data-text-key");
  if (textKey) return `text:${textKey}`;
  const row = element.closest(".source-row");
  const kind = row ? (row.getAttribute("data-kind") || "") : "";
  const index = row ? (row.getAttribute("data-index") || "") : "";
  const arrayField = element.getAttribute("data-custom-array") || "";
  const arrayIndex = element.getAttribute("data-custom-index") || "";
  const field = element.getAttribute("data-field") || "";
  const frameDomain = element.getAttribute("data-frame-domain-number") || "";
  if (kind || field || arrayField || frameDomain) {
    return `row:${kind}:${index}:${field}:${arrayField}:${arrayIndex}:domain:${frameDomain}`;
  }
  return "";
}

function hmbPromptSourceDirtyKey(item, kind) {
  if (!item || typeof item !== "object") return "";
  if (kind === "image") {
    const sourceUid = clean(item.asset_source_uid);
    if (sourceUid) return `asset-source:${sourceUid}`;
    const libraryId = clean(item.asset_library_id);
    if (libraryId) return `asset-library:${libraryId}`;
    return "";
  }
  const sourceUid = clean(item.video_uid || item.source_uid);
  return sourceUid ? `video-source:${sourceUid}` : "";
}

function hmbPromptSourceAuthority(item, kind) {
  if (!item || typeof item !== "object") return "unknown";
  if (hmbPromptSourceDirtyKey(item, kind)) return "managed";
  if (kind === "image" && (item.asset_managed || item.asset_verified)) return "managed";
  if (kind === "video" && item.picker_managed) return "managed";
  return "manual";
}

function hmbPromptDirtyTextEntries(container) {
  const dirty = container && container.__hmbPromptLibraryDirtyText;
  return dirty instanceof Map ? [...dirty.values()] : [];
}

function hmbClearPromptDirtyText(container) {
  if (!container) return;
  try { delete container.__hmbPromptLibraryDirtyText; } catch (_e) {}
}

export function hmbRememberPromptDirtyTextControl(container, element, state) {
  if (!container || !hmbIsEditableTextControl(element)) return false;
  const textKey = clean(element.getAttribute?.("data-text-key"));
  let entry = null;
  if (textKey) {
    entry = {
      kind: "text",
      key: textKey,
      value: String(element.value ?? ""),
    };
  } else {
    const row = element.closest?.(".source-row");
    const sourceKind = clean(row?.getAttribute?.("data-kind"));
    const index = Number(row?.getAttribute?.("data-index"));
    const rows = sourceKind === "image"
      ? state?.images
      : sourceKind === "video"
        ? state?.videos
        : null;
    const source = Array.isArray(rows) && Number.isInteger(index) ? rows[index] : null;
    const field = clean(element.getAttribute?.("data-field"));
    const arrayField = clean(element.getAttribute?.("data-custom-array"));
    if (source && (field || arrayField)) {
      const sourceAuthority = hmbPromptSourceAuthority(source, sourceKind);
      const manualIndex = sourceAuthority === "manual"
        ? rows.slice(0, index + 1).filter((item) => (
            hmbPromptSourceAuthority(item, sourceKind) === "manual"
          )).length - 1
        : -1;
      entry = {
        kind: "source",
        sourceKind,
        sourceKey: hmbPromptSourceDirtyKey(source, sourceKind),
        sourceAuthority,
        manualIndex,
        index,
        slot: Math.max(1, Number(source.slot) || index + 1),
        field,
        arrayField,
        arrayIndex: Math.max(0, Number(element.getAttribute?.("data-custom-index")) || 0),
        replicateArray: sourceKind === "image" && arrayField === "binding_custom_scopes",
        value: String(element.value ?? ""),
      };
    }
  }
  if (!entry) return false;
  const dirty = container.__hmbPromptLibraryDirtyText instanceof Map
    ? container.__hmbPromptLibraryDirtyText
    : new Map();
  const identity = entry.kind === "text"
    ? `text:${entry.key}`
    : [
        "source",
        entry.sourceKind,
        entry.sourceKey || `slot:${entry.slot}:index:${entry.index}`,
        entry.field,
        entry.arrayField,
        entry.arrayIndex,
      ].join(":");
  dirty.set(identity, entry);
  container.__hmbPromptLibraryDirtyText = dirty;
  return true;
}

function hmbFindPromptDirtySource(state, entry) {
  const rows = entry?.sourceKind === "image" ? state?.images : state?.videos;
  if (!Array.isArray(rows)) return null;
  const authority = clean(entry.sourceAuthority)
    || (entry.sourceKey ? "managed" : "manual");
  if (authority === "managed") {
    if (!entry.sourceKey) return null;
    const active = rows.find((item) => (
      hmbPromptSourceDirtyKey(item, entry.sourceKind) === entry.sourceKey
    ));
    if (active) return active;
    const dormant = entry.sourceKind === "image"
      ? state?.image_asset?.dormant_asset_rows
      : state?.picker?.dormant_video_rows;
    return (Array.isArray(dormant) ? dormant : []).find((item) => (
      hmbPromptSourceDirtyKey(item, entry.sourceKind) === entry.sourceKey
    )) || null;
  }
  if (authority !== "manual") return null;
  const slot = Math.max(1, Number(entry.slot) || Number(entry.index) + 1);
  const sameAuthority = (item) => (
    hmbPromptSourceAuthority(item, entry.sourceKind) === "manual"
  );
  const activeBySlot = rows.find((item) => (
    Number(item?.slot) === slot && sameAuthority(item)
  ));
  if (activeBySlot) return activeBySlot;
  const activeByIndex = rows[Math.max(0, Number(entry.index) || 0)];
  if (sameAuthority(activeByIndex)) return activeByIndex;
  const dormant = entry.sourceKind === "image"
    ? state?.image_asset?.dormant_manual_rows
    : state?.picker?.dormant_manual_rows;
  if (!Array.isArray(dormant)) return null;
  const manualIndex = Math.max(0, Number(entry.manualIndex) || 0);
  const dormantBySlot = entry.sourceKind === "image"
    ? dormant.find((item) => Number(item?.slot) === slot && sameAuthority(item))
    : null;
  if (dormantBySlot) return dormantBySlot;
  const dormantByIndex = dormant[manualIndex];
  return sameAuthority(dormantByIndex) ? dormantByIndex : null;
}

export function hmbMergePromptDirtyTextState(authoritativeValue, dirtyEntries) {
  const next = normalizeState(authoritativeValue);
  const entries = dirtyEntries instanceof Map
    ? [...dirtyEntries.values()]
    : Array.isArray(dirtyEntries)
      ? dirtyEntries
      : [];
  entries.forEach((entry) => {
    if (!entry || typeof entry !== "object") return;
    const value = String(entry.value ?? "");
    if (entry.kind === "text") {
      const key = clean(entry.key);
      if (key && next.text && Object.prototype.hasOwnProperty.call(next.text, key)) {
        next.text[key] = value;
      }
      return;
    }
    if (entry.kind !== "source") return;
    const source = hmbFindPromptDirtySource(next, entry);
    if (!source) return;
    const arrayField = clean(entry.arrayField);
    if (arrayField) {
      if (!Array.isArray(source[arrayField])) return;
      if (entry.replicateArray) {
        source[arrayField] = source[arrayField].map(() => value);
      } else {
        const index = Math.max(0, Number(entry.arrayIndex) || 0);
        if (index < source[arrayField].length) source[arrayField][index] = value;
      }
      return;
    }
    const field = clean(entry.field);
    if (!field || !Object.prototype.hasOwnProperty.call(source, field)) return;
    source[field] = value;
    if (field === "label" && entry.sourceKind === "video") {
      source.picker_auto_label = "";
    }
  });
  return normalizeState(next);
}

function hmbCaptureTextEditingState(container) {
  if (!container) return;
  const active = typeof document !== "undefined" ? document.activeElement : null;
  if (!active || !container.contains(active) || !hmbIsEditableTextControl(active)) {
    hmbClearTextEditingState(container);
    return;
  }
  const key = hmbTextControlIdentity(active);
  if (!key) return;
  let start = null;
  let end = null;
  let direction = "none";
  try {
    start = Number(active.selectionStart);
    end = Number(active.selectionEnd);
    direction = active.selectionDirection || "none";
  } catch (_e) {}
  container.__hmbPromptLibraryTextFocus = {
    key,
    start: Number.isFinite(start) ? start : null,
    end: Number.isFinite(end) ? end : null,
    direction,
    scrollTop: Number(active.scrollTop) || 0,
    scrollLeft: Number(active.scrollLeft) || 0,
  };
}

function hmbClearTextEditingState(container) {
  if (!container) return;
  try { container.__hmbPromptLibraryTextFocus = null; } catch (_e) {}
}

export function hmbRememberPromptTextPointerTarget(container, event) {
  if (!container) return;
  const target = event && event.target;
  try {
    container.__hmbPromptLibraryPointerTextTarget =
      target && container.contains?.(target) && hmbIsEditableTextControl(target)
        ? target
        : null;
  } catch (_e) {
    try { container.__hmbPromptLibraryPointerTextTarget = null; } catch (__e) {}
  }
}

export function hmbPromptBlurStaysInsideEditable(container, event) {
  if (!container) return false;
  const current = event && event.currentTarget;
  const related = event && event.relatedTarget;
  const pending = container.__hmbPromptLibraryPointerTextTarget;
  const isInternalTarget = (target) => Boolean(
    target &&
    target !== current &&
    container.contains?.(target) &&
    hmbIsEditableTextControl(target)
  );
  return isInternalTarget(related) || isInternalTarget(pending);
}

export function hmbFinalizePromptTextBlur(container, event, finalize) {
  if (hmbPromptBlurStaysInsideEditable(container, event)) return false;
  hmbClearImmediateStateCommit(container);
  hmbClearTextEditingState(container);
  if (typeof finalize === "function") finalize();
  return true;
}

function hmbFindTextControlByIdentity(container, key) {
  if (!container || !key) return null;
  const candidates = container.querySelectorAll('textarea, input:not([type]), input[type="text"], input[type="search"]');
  for (const element of candidates) {
    if (hmbTextControlIdentity(element) === key) return element;
  }
  return null;
}

function hmbRestoreTextEditingState(container) {
  if (!container) return;
  const memory = container.__hmbPromptLibraryTextFocus;
  if (!memory || !memory.key) return;
  const target = hmbFindTextControlByIdentity(container, memory.key);
  if (!target || target.disabled) return;
  try { target.focus({ preventScroll: true }); } catch (_e) { try { target.focus(); } catch (__e) {} }
  if (Number.isFinite(memory.start) && Number.isFinite(memory.end) && typeof target.setSelectionRange === "function") {
    const max = String(target.value || "").length;
    try {
      target.setSelectionRange(
        Math.max(0, Math.min(max, memory.start)),
        Math.max(0, Math.min(max, memory.end)),
        memory.direction || "none",
      );
    } catch (_e) {}
  }
  try { target.scrollTop = Number(memory.scrollTop) || 0; } catch (_e) {}
  try { target.scrollLeft = Number(memory.scrollLeft) || 0; } catch (_e) {}
}

function hmbPromptLifecycleFrame(container, callback) {
  const ownedScheduler = container?.__hmbPromptLibraryScheduleFrame;
  if (typeof ownedScheduler === "function") return ownedScheduler(callback);
  const raf = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (fn) => setTimeout(fn, 0);
  try { return raf(callback); } catch (_e) {
    try { return setTimeout(callback, 0); } catch (__e) { return 0; }
  }
}

function hmbRestoreTextEditingStateDeferred(container) {
  hmbPromptLifecycleFrame(container, () => {
    hmbRestoreTextEditingState(container);
    hmbPromptLifecycleFrame(container, () => hmbRestoreTextEditingState(container));
  });
}

const HMB_PROMPT_FOCUSABLE_SELECTOR = "input,textarea,select,button,[tabindex]";
const HMB_PROMPT_STRUCTURAL_FOCUS_CLASSES = [
  "add-image-source",
  "add-video-source",
  "clear-source",
  "add-color-pick",
  "remove-color-pick",
  "move-image-up",
  "move-image-down",
];

function hmbPromptControlFocusDescriptor(container) {
  const active = typeof document !== "undefined" ? document.activeElement : null;
  if (!active || !container?.contains?.(active) || hmbIsEditableTextControl(active)) return null;
  if (active.hasAttribute?.("data-language-toggle")) return { kind: "language" };
  if (active.hasAttribute?.("data-shot-selector")) return { kind: "shot" };
  const structuralAction = HMB_PROMPT_STRUCTURAL_FOCUS_CLASSES.find((className) => (
    active.classList?.contains?.(className)
  ));
  if (structuralAction) {
    const sourceRow = active.closest?.(".source-row");
    return {
      kind: "structure",
      action: structuralAction,
      rowKind: sourceRow?.getAttribute?.("data-kind") || "",
      rowIndex: sourceRow?.getAttribute?.("data-index") || "",
      sourceKey: sourceRow?.getAttribute?.("data-source-key") || "",
    };
  }
  const row = active.closest?.(".source-row[data-kind][data-index]");
  if (row) {
    const controls = [...row.querySelectorAll(HMB_PROMPT_FOCUSABLE_SELECTOR)];
    return {
      kind: "row",
      rowKind: row.getAttribute("data-kind") || "",
      rowIndex: row.getAttribute("data-index") || "",
      sourceKey: row.getAttribute("data-source-key") || "",
      index: Math.max(0, controls.indexOf(active)),
    };
  }
  const group = active.closest?.("[data-group-id]");
  if (group) {
    const controls = [...group.querySelectorAll(HMB_PROMPT_FOCUSABLE_SELECTOR)];
    return {
      kind: "group",
      groupId: group.getAttribute("data-group-id") || "",
      index: Math.max(0, controls.indexOf(active)),
    };
  }
  return null;
}

function hmbCapturePromptControlFocus(container) {
  if (!container) return;
  try { container.__hmbPromptLibraryControlFocus = hmbPromptControlFocusDescriptor(container); }
  catch (_error) { try { container.__hmbPromptLibraryControlFocus = null; } catch (__error) {} }
}

function hmbRestorePromptControlFocus(container) {
  if (!container?.querySelector) return;
  const memory = container.__hmbPromptLibraryControlFocus;
  if (!memory) return;
  let target = null;
  if (memory.kind === "language") {
    target = container.querySelector("[data-language-toggle]");
  } else if (memory.kind === "shot") {
    target = container.querySelector("[data-shot-selector]");
  } else if (memory.kind === "structure") {
    const rows = [...container.querySelectorAll(".source-row[data-kind]")];
    const row = rows.find((element) => (
      (element.getAttribute("data-kind") || "") === memory.rowKind
      && (
        (memory.sourceKey && (element.getAttribute("data-source-key") || "") === memory.sourceKey)
        || (!memory.sourceKey && memory.rowIndex !== ""
          && (element.getAttribute("data-index") || "") === memory.rowIndex)
      )
    ));
    target = row?.querySelector?.(`.${memory.action}`)
      || container.querySelector(`.${memory.action}`);
  } else if (memory.kind === "row") {
    const row = [...container.querySelectorAll(".source-row[data-kind][data-index]")].find((element) => (
      (element.getAttribute("data-kind") || "") === memory.rowKind
      && (
        (memory.sourceKey && (element.getAttribute("data-source-key") || "") === memory.sourceKey)
        || (!memory.sourceKey && (element.getAttribute("data-index") || "") === memory.rowIndex)
      )
    ));
    target = row ? [...row.querySelectorAll(HMB_PROMPT_FOCUSABLE_SELECTOR)][memory.index] || null : null;
  } else if (memory.kind === "group") {
    const group = [...container.querySelectorAll("[data-group-id]")]
      .find((element) => (element.getAttribute("data-group-id") || "") === memory.groupId);
    target = group ? [...group.querySelectorAll(HMB_PROMPT_FOCUSABLE_SELECTOR)][memory.index] || null : null;
  }
  if (!target || target.disabled || target.hidden) return;
  try { target.focus({ preventScroll: true }); } catch (_error) { try { target.focus(); } catch (__error) {} }
}

const HMB_SOURCE_SCROLL_KEYS = ["imageSources", "videoSources"];

function hmbScrollMemory(container) {
  if (!container) return {};
  if (!container.__hmbPromptLibraryScrollMemory || typeof container.__hmbPromptLibraryScrollMemory !== "object") {
    container.__hmbPromptLibraryScrollMemory = { imageSources: 0, videoSources: 0 };
  }
  return container.__hmbPromptLibraryScrollMemory;
}

function hmbScrollDatasetKey(key) {
  return key === "videoSources" ? "hmbVideoSourceScrollTop" : "hmbImageSourceScrollTop";
}

function hmbSourceScrollbox(container, key) {
  try {
    return container ? container.querySelector(`.group-card[data-group-id="${key}"] .source-scrollbox`) : null;
  } catch (_e) {
    return null;
  }
}

function hmbStoreSourceScroll(container, key, value) {
  if (!container || !key) return;
  const top = Math.max(0, Math.round(Number(value) || 0));
  const memory = hmbScrollMemory(container);
  memory[key] = top;
  try { container.dataset[hmbScrollDatasetKey(key)] = String(top); } catch (_e) {}
}

function hmbReadStoredSourceScroll(container, key) {
  const memory = hmbScrollMemory(container);
  const own = Number(memory[key]);
  if (Number.isFinite(own) && own > 0) return own;
  try {
    const data = Number(container && container.dataset ? container.dataset[hmbScrollDatasetKey(key)] : 0);
    if (Number.isFinite(data) && data > 0) return data;
  } catch (_e) {}
  return 0;
}

function hmbCaptureSourceScroll(container) {
  HMB_SOURCE_SCROLL_KEYS.forEach((key) => {
    const box = hmbSourceScrollbox(container, key);
    if (box) hmbStoreSourceScroll(container, key, box.scrollTop || 0);
  });
}

function hmbRestoreSourceScrollNow(container) {
  HMB_SOURCE_SCROLL_KEYS.forEach((key) => {
    const box = hmbSourceScrollbox(container, key);
    if (!box) return;
    const maxTop = Math.max(0, (box.scrollHeight || 0) - (box.clientHeight || 0));
    const target = Math.max(0, Math.min(maxTop, hmbReadStoredSourceScroll(container, key)));
    if (Math.abs((box.scrollTop || 0) - target) > 1) {
      try { box.scrollTop = target; } catch (_e) {}
    }
  });
}

function hmbRestoreSourceScroll(container) {
  if (hmbIsGroupResizeDragging(container)) return;
  hmbRestoreSourceScrollNow(container);
  hmbPromptLifecycleFrame(container, () => {
    if (hmbIsGroupResizeDragging(container)) return;
    hmbRestoreSourceScrollNow(container);
    hmbPromptLifecycleFrame(container, () => {
      if (!hmbIsGroupResizeDragging(container)) hmbRestoreSourceScrollNow(container);
    });
  });
}


export function hmbInstallPromptInteractionIsolation(container, listeners) {
  if (!container || typeof container.querySelectorAll !== "function" || !Array.isArray(listeners)) return;
  const canvasPanRoots = [
    container,
    container.querySelector?.(".hmb-dashboard-clip"),
    container.querySelector?.(".hmb-dashboard"),
  ].filter(Boolean);
  // Keep nodrag on the widget host so an interior gesture cannot move the
  // node itself. Node selection and resize activation belong to the native
  // purple title bar only.
  canvasPanRoots.forEach((element) => element.classList?.remove("nopan", "nowheel"));
  const interactionSelectors = [
    "input",
    "textarea",
    "select",
    "button",
    "label",
    "summary",
    "[role='button']",
    "[contenteditable='true']",
    "[data-resize-group]",
    "[data-resize-textarea]"
  ];
  const isolated = new Set();
  const stopPointerPropagation = (event) => event.stopPropagation();
  const isolatePointer = (element) => {
    if (!element || isolated.has(element)) return;
    isolated.add(element);
    // A concrete control keeps its native pointer and wheel behavior. The
    // surrounding open-hand background remains free for Griptape pan/zoom.
    element.classList?.add("nodrag", "nopan", "nowheel");
    ["pointerdown", "mousedown", "click", "dblclick"].forEach((eventName) => {
      element.addEventListener?.(eventName, stopPointerPropagation);
      listeners.push([element, eventName, stopPointerPropagation]);
    });
  };

  // IMAGE SOURCE BINDING now follows the same Griptape canvas behavior as the
  // rest of the dashboard. Only concrete controls below are isolated.
  const imageSourceBinding = container.querySelector?.(".image-card");
  imageSourceBinding?.classList?.remove("nodrag", "nopan", "nowheel");
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
  listeners.push([container, "keydown", stopNodeDeleteShortcut]);
  listeners.push([container, "pointerdown", stopInteriorNodeSelection]);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
    listeners.push([window, "keydown", stopSelectedNodeDeleteShortcut, true]);
  }
}

function hmbInstallSourceScrollPositionLock(container, listeners) {
  HMB_SOURCE_SCROLL_KEYS.forEach((key) => {
    const box = hmbSourceScrollbox(container, key);
    if (!box) return;
    const save = () => hmbStoreSourceScroll(container, key, box.scrollTop || 0);
    box.addEventListener("scroll", save, { passive: true });
    box.addEventListener("wheel", save, { passive: true });
    box.addEventListener("pointerdown", save);
    box.addEventListener("focusin", save);
    listeners.push([box, "scroll", save]);
    listeners.push([box, "wheel", save]);
    listeners.push([box, "pointerdown", save]);
    listeners.push([box, "focusin", save]);
  });
  hmbRestoreSourceScroll(container);
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function options(list, value, blankLabel, state) {
  return list.map((item) => {
    const text = item === "" ? blankLabel : optionLabel(item, state);
    return `<option value="${escapeHtml(item)}" ${item === value ? "selected" : ""}>${escapeHtml(text)}</option>`;
  }).join("");
}

export function hmbSyncSelectOptions(select, list, value, blankLabel, state) {
  if (!select) return false;
  const desired = (Array.isArray(list) ? list : []).map((item) => ({
    value: String(item == null ? "" : item),
    label: String(item === "" ? blankLabel : optionLabel(item, state)),
  }));
  const current = Array.from(select.options || []);
  const optionsChanged = current.length !== desired.length || desired.some((item, index) => {
    const option = current[index];
    if (!option) return true;
    const label = option.textContent != null ? option.textContent : option.text;
    return String(option.value) !== item.value || String(label == null ? "" : label) !== item.label;
  });
  if (optionsChanged) {
    select.innerHTML = options(
      desired.map((item) => item.value),
      String(value == null ? "" : value),
      blankLabel,
      state,
    );
  }
  const nextValue = String(value == null ? "" : value);
  if (String(select.value == null ? "" : select.value) !== nextValue) {
    select.value = nextValue;
  }
  return optionsChanged;
}


function colorPickChoices(images, rowIndex, pickIndex, videoCount) {
  const row = (images || [])[rowIndex] || {};
  normalizeImageBindingFields(row, MAX_VIDEOS);
  const markerVideo = normalizeMarkerVideo(row.binding_video_slots[pickIndex], MAX_VIDEOS);
  const current = clean(row.color_picks[pickIndex]);
  const used = [];
  (images || []).forEach((image, imageIndex) => {
    if (!isActiveImage(image)) return;
    rawBindingEntries(image, MAX_VIDEOS).forEach((entry) => {
      if (entry.videoSlot !== markerVideo || !entry.color) return;
      if (imageIndex === rowIndex && entry.index === pickIndex) return;
      if (!used.includes(entry.color)) used.push(entry.color);
    });
  });
  const allowed = colorPickChoicesForSourceType(row.source_type);
  const choices = [
    "",
    ...(current && !allowed.includes(current) ? [current] : []),
    ...allowed.filter((item) => item === current || !used.includes(item)),
  ];
  return uniqueList(choices);
}

function colorPickOptions(images, rowIndex, pickIndex, videoCount, state) {
  const row = (images || [])[rowIndex] || {};
  normalizeImageBindingFields(row, MAX_VIDEOS);
  const current = clean(row.color_picks[pickIndex]);
  return options(
    colorPickChoices(images, rowIndex, pickIndex, videoCount),
    current,
    "—",
    state,
  );
}

function verifiedRegisteredSubtype(item) {
  if (
    !item?.asset_verified
    || clean(item?.asset_source_kind).toLowerCase() !== "project"
  ) return "";
  const subtype = clean(item.asset_scope_candidate);
  const choices = Array.isArray(IMAGE_SCOPES_BY_SOURCE_TYPE[clean(item.source_type)])
    ? IMAGE_SCOPES_BY_SOURCE_TYPE[clean(item.source_type)]
    : IMAGE_SCOPES;
  return subtype && choices.includes(subtype) ? subtype : "";
}

function renderSubtypeControls(item, state, locked = false) {
  normalizeImageBindingFields(item, videoSlotCount(state));
  const scope = clean(item.binding_scopes[0]);
  const customInput = `<input class="custom-inline-input ${scope === "Custom scope" ? "" : "is-hidden"}" data-custom-array="binding_custom_scopes" data-custom-index="0" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.binding_custom_scopes[0] || "")}" placeholder="${escapeHtml(uiText(state, "custom_scope", "Custom scope input"))}" aria-hidden="${scope === "Custom scope" ? "false" : "true"}" ${locked ? "disabled" : ""}/>`;
  return `<div class="binding-scope-stack"><div class="binding-scope-entry"><select class="source-select binding-scope-select" data-field="binding_scopes" data-binding-index="0" ${locked ? "disabled" : ""}>${options(imageScopeChoicesForRow(item, scope), scope, uiText(state, "blank_subtype", "— blank / no subtype —"), state)}</select>${customInput}</div></div>`;
}

function frameRangeBarsHtml(ranges, metadata, selectedIndex) {
  if (!metadata || metadata.end_frame < metadata.start_frame) return "";
  const total = Math.max(1, metadata.end_frame - metadata.start_frame + 1);
  return normalizeFrameRanges(ranges).map((range, index) => {
    const left = ((range.start - metadata.start_frame) / total) * 100;
    const width = ((range.end - range.start + 1) / total) * 100;
    return `<span class="frame-range-bar ${index === selectedIndex ? "selected" : ""}" data-frame-range-index="${index}" style="left:${Math.max(0, left)}%;width:${Math.max(0, width)}%" title="${range.start}–${range.end}"><i class="frame-range-handle left" data-frame-range-handle="start"></i><b>${range.start}–${range.end}</b><i class="frame-range-handle right" data-frame-range-handle="end"></i></span>`;
  }).join("");
}

function hmbFrameRangeAriaValueText(ranges, selectedIndex) {
  const normalized = normalizeFrameRanges(ranges);
  const selected = normalized[selectedIndex] || null;
  if (!selected) {
    return "No range selected. Enter creates the first range; Alt+Enter adds another; PageUp and PageDown select ranges.";
  }
  return `Range ${selectedIndex + 1} of ${normalized.length} selected, frames ${selected.start} to ${selected.end}. Alt+Enter adds a range; PageUp and PageDown select ranges.`;
}

export function frameDomainInputValue(value) {
  if (value === null || value === undefined || String(value).trim() === "") return "";
  const frame = Math.round(Number(value));
  if (!Number.isFinite(frame)) return "";
  if (frame < 0) return `-${String(Math.abs(frame)).padStart(3, "0")}`;
  return String(frame).padStart(4, "0");
}

function renderFrameRangeRow(item, index, state) {
  normalizeImageBindingFields(item, videoSlotCount(state));
  const frameStatus = frameRangeUiStatus(state, item);
  const enabled = Boolean(item.frame_range_enabled);
  const editable = enabled;
  const trackEditable = editable && frameStatus.domainComplete;
  const visibleError = enabled && Boolean(frameStatus.reason || frameStatus.domainInvalid);
  const selectedIndex = Math.max(
    -1,
    Math.min(
      frameStatus.ranges.length - 1,
      Number.isFinite(Number(item.frame_range_selected_index))
        ? Number(item.frame_range_selected_index)
        : -1,
    ),
  );
  const metadata = frameStatus.metadata;
  const minimum = metadata ? metadata.start_frame : 0;
  const maximum = metadata ? metadata.end_frame : MAX_MANUAL_FRAME_NUMBER;
  const suggestion = frameStatus.suggestedDomain
    ? ` Picker suggestion: ${frameStatus.suggestedDomain.start_frame}-${frameStatus.suggestedDomain.end_frame}.`
    : "";
  const tooltip = frameStatus.reason
    || (!frameStatus.domainComplete && enabled
      ? `Enter the manual start and end frames.${suggestion}`
      : `${frameStatus.binding?.video_slot || `@video${frameStatus.slot}`} · ${frameStatus.color || "Color Pick"} · Frames ${minimum}-${maximum}`);
  const domainHidden = enabled ? "" : "is-hidden";
  const startDomain = frameDomainInputValue(frameStatus.domainStart);
  const endDomain = frameDomainInputValue(frameStatus.domainEnd);
  const selectedRange = frameStatus.ranges[selectedIndex] || null;
  const ariaNow = selectedRange ? selectedRange.start : minimum;
  const ariaText = hmbFrameRangeAriaValueText(frameStatus.ranges, selectedIndex);
  return `<div class="frame-binding-row ${enabled ? "enabled" : "disabled"} ${visibleError ? "invalid" : ""}" data-frame-binding-row data-index="${index}">
    <label class="frame-range-toggle-wrap" title="${escapeHtml(tooltip)}"><input type="checkbox" class="frame-range-toggle" data-frame-range-toggle data-hmb-base-disabled="0" ${enabled ? "checked" : ""}/><span class="frame-range-toggle-ui"><b>Range</b><em>${enabled ? "ON" : "OFF"}</em></span></label>
    <div class="frame-track-shell" title="${escapeHtml(tooltip)}">
      <input class="frame-domain-number frame-domain-start ${domainHidden}" data-frame-domain-number="start" type="text" inputmode="numeric" pattern="[0-9]{1,4}" maxlength="4" value="${startDomain}" placeholder="0001" aria-label="Range start frame"/>
      <div class="frame-track-stage"><div class="frame-track ${trackEditable ? "editable" : ""}" data-frame-track data-index="${index}" data-frame-min="${minimum}" data-frame-max="${maximum}" tabindex="${trackEditable ? "0" : "-1"}" role="slider" aria-roledescription="multi-range frame editor" aria-label="Frame range editor" aria-valuemin="${minimum}" aria-valuemax="${maximum}" aria-valuenow="${ariaNow}" aria-valuetext="${escapeHtml(ariaText)}" aria-keyshortcuts="Enter Space Alt+Enter PageUp PageDown ArrowLeft ArrowRight Shift+ArrowLeft Shift+ArrowRight Control+ArrowLeft Control+ArrowRight Home End Delete Backspace"><span class="frame-track-grid"></span>${frameRangeBarsHtml(frameStatus.ranges, metadata, selectedIndex)}<em>${escapeHtml(frameStatus.status)}</em></div></div>
      <input class="frame-domain-number frame-domain-end ${domainHidden}" data-frame-domain-number="end" type="text" inputmode="numeric" pattern="[0-9]{1,4}" maxlength="4" value="${endDomain}" placeholder="0100" aria-label="Range end frame"/>
    </div>
  </div>`;
}

export function storeCurrentFrameRanges(item, ranges, selectedIndex = -1) {
  if (!item || typeof item !== "object") return [];
  normalizeImageBindingFields(item, MAX_VIDEOS);
  const selection = currentFrameRangeSelection(item);
  const normalizedRanges = normalizeFrameRanges(ranges);
  const binding = {
    video_slot: `@video${selection.slot}`,
    color_pick: selection.color,
    enabled: true,
    origin: "manual",
    ranges: normalizedRanges,
    start_frame: normalizeFrameDomainEndpoint(selection.binding && selection.binding.start_frame),
    end_frame: normalizeFrameDomainEndpoint(selection.binding && selection.binding.end_frame),
  };
  item.frame_range_bindings = {
    ...selection.bindings,
    [selection.key]: binding,
  };
  item.frame_range_binding = { ...binding };
  item.frame_range_selected_index = normalizedRanges.length
    ? Math.max(0, Math.min(normalizedRanges.length - 1, Math.floor(Number(selectedIndex) || 0)))
    : -1;
  return normalizedRanges;
}

export function storeCurrentFrameDomain(item, startFrame, endFrame) {
  if (!item || typeof item !== "object") return null;
  normalizeImageBindingFields(item, MAX_VIDEOS);
  const selection = currentFrameRangeSelection(item);
  const binding = {
    video_slot: `@video${selection.slot}`,
    color_pick: selection.color,
    enabled: true,
    origin: "manual",
    ranges: normalizeFrameRanges(selection.binding && selection.binding.ranges),
    start_frame: normalizeFrameDomainEndpoint(startFrame),
    end_frame: normalizeFrameDomainEndpoint(endFrame),
  };
  item.frame_range_bindings = {
    ...selection.bindings,
    [selection.key]: binding,
  };
  item.frame_range_binding = { ...binding };
  return { start_frame: binding.start_frame, end_frame: binding.end_frame };
}

export function setFrameRangeEnabled(item, enabled) {
  if (!item || typeof item !== "object") return false;
  normalizeImageBindingFields(item, MAX_VIDEOS);
  item.frame_range_enabled = Boolean(enabled);
  if (!item.frame_range_enabled) item.frame_range_selected_index = -1;
  if (item.frame_range_enabled) {
    const selection = currentFrameRangeSelection(item);
    if (!selection.binding) {
      storeCurrentFrameRanges(item, [], -1);
    } else {
      const binding = { ...selection.binding, enabled: true, origin: "manual" };
      item.frame_range_bindings = {
        ...selection.bindings,
        [selection.key]: binding,
      };
      item.frame_range_binding = { ...binding };
    }
  } else syncCurrentFrameRangeBinding(item);
  return item.frame_range_enabled;
}

function frameFromPointer(event, track, minimum, maximum) {
  const rect = track.getBoundingClientRect();
  const width = Math.max(1, Number(rect.width || 1));
  const ratio = Math.max(0, Math.min(0.999999, (Number(event.clientX || 0) - Number(rect.left || 0)) / width));
  return minimum + Math.floor(ratio * Math.max(1, maximum - minimum + 1));
}

export function updateFrameTrackPreview(track, ranges, metadata, selectedIndex, statusText) {
  if (!track) return;
  const validMetadata = Boolean(metadata && metadata.end_frame >= metadata.start_frame);
  const normalized = validMetadata ? normalizeFrameRanges(ranges) : [];
  const total = validMetadata
    ? Math.max(1, metadata.end_frame - metadata.start_frame + 1)
    : 0;
  const documentRef = track.ownerDocument || (typeof document !== "undefined" ? document : null);
  const status = track.querySelector?.("em");
  const existing = Array.from(track.querySelectorAll?.(".frame-range-bar") || []);
  normalized.forEach((range, index) => {
    let bar = existing[index] || null;
    if (!bar && documentRef && typeof documentRef.createElement === "function") {
      bar = documentRef.createElement("span");
      const leftHandle = documentRef.createElement("i");
      const label = documentRef.createElement("b");
      const rightHandle = documentRef.createElement("i");
      leftHandle.className = "frame-range-handle left";
      leftHandle.setAttribute("data-frame-range-handle", "start");
      rightHandle.className = "frame-range-handle right";
      rightHandle.setAttribute("data-frame-range-handle", "end");
      bar.append(leftHandle, label, rightHandle);
      if (status && status.parentNode === track) track.insertBefore(bar, status);
      else track.appendChild(bar);
    }
    if (!bar) return;
    bar.className = `frame-range-bar ${index === selectedIndex ? "selected" : ""}`.trim();
    bar.setAttribute("data-frame-range-index", String(index));
    bar.setAttribute("title", `${range.start}–${range.end}`);
    const left = total ? ((range.start - metadata.start_frame) / total) * 100 : 0;
    const width = total ? ((range.end - range.start + 1) / total) * 100 : 0;
    bar.style.left = `${Math.max(0, left)}%`;
    bar.style.width = `${Math.max(0, width)}%`;
    const label = bar.querySelector?.("b");
    if (label) label.textContent = `${range.start}–${range.end}`;
  });
  existing.slice(normalized.length).forEach((bar) => bar.remove?.());
  if (status) status.textContent = String(statusText || "");
  if (validMetadata) {
    const selected = normalized[selectedIndex] || null;
    track.setAttribute?.("aria-valuemin", String(metadata.start_frame));
    track.setAttribute?.("aria-valuemax", String(metadata.end_frame));
    track.setAttribute?.("aria-valuenow", String(selected ? selected.start : metadata.start_frame));
    track.setAttribute?.(
      "aria-valuetext",
      hmbFrameRangeAriaValueText(normalized, selectedIndex),
    );
  }
}

function hmbSyncFrameRangeRowDom(row, item, state) {
  if (!row || !item) return null;
  const frameStatus = frameRangeUiStatus(state, item);
  const enabled = Boolean(item.frame_range_enabled);
  const trackEditable = enabled && frameStatus.domainComplete;
  const visibleError = enabled && Boolean(frameStatus.reason || frameStatus.domainInvalid);
  const metadata = frameStatus.metadata;
  const minimum = metadata ? metadata.start_frame : 0;
  const maximum = metadata ? metadata.end_frame : MAX_MANUAL_FRAME_NUMBER;
  const selectedIndex = Math.max(
    -1,
    Math.min(
      frameStatus.ranges.length - 1,
      Number.isFinite(Number(item.frame_range_selected_index))
        ? Number(item.frame_range_selected_index)
        : -1,
    ),
  );
  const suggestion = frameStatus.suggestedDomain
    ? ` Picker suggestion: ${frameStatus.suggestedDomain.start_frame}-${frameStatus.suggestedDomain.end_frame}.`
    : "";
  const tooltip = frameStatus.reason
    || (!frameStatus.domainComplete && enabled
      ? `Enter the manual start and end frames.${suggestion}`
      : `${frameStatus.binding?.video_slot || `@video${frameStatus.slot}`} · ${frameStatus.color || "Color Pick"} · Frames ${minimum}–${maximum}`);

  row.classList?.toggle("enabled", enabled);
  row.classList?.toggle("disabled", !enabled);
  row.classList?.toggle("invalid", visibleError);
  const toggle = row.querySelector?.("[data-frame-range-toggle]");
  if (toggle) {
    toggle.checked = enabled;
    toggle.disabled = false;
    toggle.setAttribute?.("data-hmb-base-disabled", "0");
    toggle.closest?.(".frame-range-toggle-wrap")?.setAttribute("title", tooltip);
  }
  const toggleState = row.querySelector?.(".frame-range-toggle-ui em");
  if (toggleState) toggleState.textContent = enabled ? "ON" : "OFF";

  [
    ["start", frameStatus.domainStart],
    ["end", frameStatus.domainEnd],
  ].forEach(([field, value]) => {
    const input = row.querySelector?.(`[data-frame-domain-number="${field}"]`);
    if (!input) return;
    input.classList?.toggle("is-hidden", !enabled);
    input.value = frameDomainInputValue(value);
    input.readOnly = false;
    input.removeAttribute("readonly");
  });

  const shell = row.querySelector?.(".frame-track-shell");
  if (shell) shell.setAttribute("title", tooltip);
  const track = row.querySelector?.("[data-frame-track]");
  if (track) {
    track.classList?.toggle("editable", trackEditable);
    track.setAttribute("data-frame-min", String(minimum));
    track.setAttribute("data-frame-max", String(maximum));
    track.setAttribute("tabindex", trackEditable ? "0" : "-1");
    updateFrameTrackPreview(track, frameStatus.ranges, metadata, selectedIndex, frameStatus.status);
  }
  return frameStatus;
}

const HMB_PROMPT_LOCAL_ECHO_TTL_MS = 750;
const HMB_PROMPT_LOCAL_ECHO_MAX_CONSUMES = 3;
const HMB_PROMPT_LOCAL_ECHO_QUEUE_LIMIT = 12;
const HMB_PROMPT_TRANSPORT_RETRY_MS = 32;
let hmbPromptPublicationSequence = 0;

export function hmbInvalidatePromptPublication(container) {
  hmbClearPromptTransportRetry(container);
  const publicationToken = ++hmbPromptPublicationSequence;
  if (container) container.__hmbPromptLibraryPublicationOwner = publicationToken;
  return publicationToken;
}

function hmbClearPromptTransportRetry(container) {
  if (!container) return false;
  const timer = container.__hmbPromptLibraryTransportRetryTimer;
  const hadTimer = timer !== null && timer !== undefined;
  try { if (hadTimer) clearTimeout(timer); } catch (_error) {}
  try { container.__hmbPromptLibraryTransportRetryTimer = null; } catch (_error) {}
  return hadTimer;
}

function hmbClearPendingPromptStateEchoes(container) {
  if (!container) return;
  try {
    if (container.__hmbPromptPendingLocalTimer) {
      clearTimeout(container.__hmbPromptPendingLocalTimer);
    }
  } catch (_error) {}
  try {
    delete container.__hmbPromptPendingLocalValues;
    delete container.__hmbPromptSupersededLocalValues;
    delete container.__hmbPromptPendingLocalTimer;
  } catch (_error) {}
}

function hmbPendingPromptEchoIsLive(item, now) {
  if (!item || typeof item.value !== "string") return false;
  const expiresAt = Number(item.expiresAt);
  return !Number.isFinite(expiresAt) || expiresAt > now;
}

function hmbPromptStateRevisionFromSerialized(value) {
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value;
    return normalizeSourceSyncRevision(parsed?.source_sync_revision);
  } catch (_error) {
    return 0;
  }
}

function hmbRememberPromptRevisionState(container, state, disabled, local = false) {
  if (!container) return;
  const uiEditRevision = normalizeUiEditRevision(state?.[UI_EDIT_REVISION_KEY]);
  const sourceSyncRevision = normalizeSourceSyncRevision(state?.source_sync_revision);
  container.__hmbPromptCurrentUiEditRevision = uiEditRevision;
  container.__hmbPromptCurrentSourceSyncRevision = sourceSyncRevision;
  container.__hmbPromptCurrentDisabled = Boolean(disabled);
  container.__hmbPromptCurrentShotCatalogRouting = normalizeShotCatalogRouting(
    state?.image_asset?.shot_catalog_routing,
  );
  if (local) {
    container.__hmbPromptLatestLocalUiEditRevision = Math.max(
      normalizeUiEditRevision(container.__hmbPromptLatestLocalUiEditRevision),
      uiEditRevision,
    );
  }
}

export function hmbPromptShotCatalogRoutingIsStale(currentValue, incomingValue) {
  const current = normalizeShotCatalogRouting(currentValue);
  const incoming = normalizeShotCatalogRouting(incomingValue);
  if (
    !current.publisher_instance_uuid
    || !current.channel_uuid
    || !incoming.publisher_instance_uuid
    || !incoming.channel_uuid
    || current.publisher_instance_uuid !== incoming.publisher_instance_uuid
    || current.channel_uuid !== incoming.channel_uuid
  ) return false;
  if (incoming.generation < current.generation) return true;
  return Boolean(
    incoming.generation === current.generation
    && current.generation > 0
    && current.metadata_sha256
    && incoming.metadata_sha256
    && current.metadata_sha256 !== incoming.metadata_sha256
  );
}

function hmbNextPromptUiEditRevision(container, state) {
  const current = normalizeUiEditRevision(state?.[UI_EDIT_REVISION_KEY]);
  const latestLocal = normalizeUiEditRevision(
    container?.__hmbPromptLatestLocalUiEditRevision,
  );
  return Math.min(MAX_SOURCE_SYNC_REVISION, Math.max(current, latestLocal) + 1);
}

function hmbPromptRevisionDisposition(container, nextProps, incomingState) {
  if (!container || !incomingState) return "unknown";
  if (hmbPromptShotCatalogRoutingIsStale(
    container.__hmbPromptCurrentShotCatalogRouting,
    incomingState?.image_asset?.shot_catalog_routing,
  )) return "stale";
  const hasCurrentSourceRevision = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbPromptCurrentSourceSyncRevision",
  );
  const incomingSourceRevision = normalizeSourceSyncRevision(
    incomingState.source_sync_revision,
  );
  const currentSourceRevision = normalizeSourceSyncRevision(
    container.__hmbPromptCurrentSourceSyncRevision,
  );
  if (hasCurrentSourceRevision && incomingSourceRevision > currentSourceRevision) {
    return "authoritative";
  }
  if (hasCurrentSourceRevision && incomingSourceRevision < currentSourceRevision) {
    return "stale";
  }

  const hasCurrentUiRevision = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbPromptCurrentUiEditRevision",
  );
  const hasLatestLocalUiRevision = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbPromptLatestLocalUiEditRevision",
  );
  if (hasCurrentUiRevision || hasLatestLocalUiRevision) {
    const latestUiRevision = Math.max(
      normalizeUiEditRevision(container.__hmbPromptCurrentUiEditRevision),
      normalizeUiEditRevision(container.__hmbPromptLatestLocalUiEditRevision),
    );
    const incomingUiRevision = normalizeUiEditRevision(
      incomingState[UI_EDIT_REVISION_KEY],
    );
    if (incomingUiRevision < latestUiRevision) return "stale";
    if (incomingUiRevision > latestUiRevision) return "authoritative";
  }

  // Disabled is host-owned, but an old source/UI payload must never roll back
  // live selections just because it carries a newer disabled flag. The caller
  // applies that flag without replacing the serialized state.
  const hasCurrentDisabled = Object.prototype.hasOwnProperty.call(
    container,
    "__hmbPromptCurrentDisabled",
  );
  if (
    hasCurrentDisabled
    && Boolean(nextProps?.disabled) !== Boolean(container.__hmbPromptCurrentDisabled)
  ) return "authoritative";
  return hasCurrentUiRevision || hasLatestLocalUiRevision ? "current" : "unknown";
}

function hmbPromptStateEchoMatches(item, incoming, disabled) {
  return Boolean(
    item
    && incoming === item.value
    && Boolean(disabled) === Boolean(item.disabled)
  );
}

function hmbPromptDirtySnapshot(container) {
  const dirty = container && container.__hmbPromptLibraryDirtyText;
  return dirty instanceof Map
    ? new Map([...dirty.entries()].map(([key, entry]) => [key, { ...entry }]))
    : new Map();
}

function hmbRegisterPendingPromptStateEcho(container, value, disabled, publicationToken) {
  if (!container) return;
  const now = Date.now();
  const pending = {
    value,
    disabled: Boolean(disabled),
    publicationToken,
    sourceSyncRevision: hmbPromptStateRevisionFromSerialized(value),
    expiresAt: now + HMB_PROMPT_LOCAL_ECHO_TTL_MS,
    remainingEchoes: HMB_PROMPT_LOCAL_ECHO_MAX_CONSUMES,
  };
  try {
    const prior = Array.isArray(container.__hmbPromptPendingLocalValues)
      ? container.__hmbPromptPendingLocalValues
      : [];
    const queue = prior.filter((item) => hmbPendingPromptEchoIsLive(item, now));
    const tail = queue[queue.length - 1];
    if (tail && tail.value === pending.value && Boolean(tail.disabled) === pending.disabled) {
      queue[queue.length - 1] = pending;
    } else {
      queue.push(pending);
    }
    container.__hmbPromptPendingLocalValues = queue.slice(-HMB_PROMPT_LOCAL_ECHO_QUEUE_LIMIT);
    if (container.__hmbPromptPendingLocalTimer) {
      clearTimeout(container.__hmbPromptPendingLocalTimer);
    }
    container.__hmbPromptPendingLocalTimer = setTimeout(() => {
      hmbClearPendingPromptStateEchoes(container);
    }, HMB_PROMPT_LOCAL_ECHO_TTL_MS);
  } catch (_error) {}
}

function hmbRemovePendingPromptStateEcho(container, publicationToken) {
  if (!container) return;
  const queue = (Array.isArray(container.__hmbPromptPendingLocalValues)
    ? container.__hmbPromptPendingLocalValues
    : []).filter((item) => item?.publicationToken !== publicationToken);
  try {
    if (container.__hmbPromptPendingLocalTimer) {
      clearTimeout(container.__hmbPromptPendingLocalTimer);
    }
  } catch (_error) {}
  if (!queue.length) {
    hmbClearPendingPromptStateEchoes(container);
    return;
  }
  container.__hmbPromptPendingLocalValues = queue;
  container.__hmbPromptPendingLocalTimer = setTimeout(() => {
    hmbClearPendingPromptStateEchoes(container);
  }, HMB_PROMPT_LOCAL_ECHO_TTL_MS);
}

function hmbRestorePromptDirtySnapshot(container, dirtySnapshot) {
  if (!container) return;
  const restored = dirtySnapshot instanceof Map ? new Map(dirtySnapshot) : new Map();
  const current = container.__hmbPromptLibraryDirtyText;
  if (current instanceof Map) {
    current.forEach((entry, key) => restored.set(key, entry));
  }
  if (restored.size) container.__hmbPromptLibraryDirtyText = restored;
  container.__hmbPromptLibraryCommitPending = true;
}

function hmbSetPromptPublicationStatus(container, message = "", detail = "") {
  const status = container?.querySelector?.("[data-prompt-publication-status]");
  if (!status) return false;
  const text = String(message || "");
  status.textContent = text;
  status.setAttribute?.("data-state", text ? "error" : "idle");
  status.setAttribute?.("title", text ? String(detail?.message || detail || text) : "");
  return true;
}

function hmbReportPromptPublicationFailure(container, error, publicationToken) {
  const message = String(error?.message || error || "Prompt state publication failed");
  if (container) {
    container.__hmbPromptLibraryLastPublishError = {
      message,
      publicationToken,
      at: Date.now(),
    };
  }
  hmbSetPromptPublicationStatus(container, "Save failed · retrying…", error);
  try { console?.error?.("[HMBPromptLibrary] state publication failed", error); } catch (_e) {}
}

function hmbPublishPromptStateValue(
  container,
  props,
  value,
  registerEcho = false,
  retryBudget = 1,
  onFinalFailure = null,
) {
  hmbClearPromptTransportRetry(container);
  const publicationToken = ++hmbPromptPublicationSequence;
  const dirtySnapshot = hmbPromptDirtySnapshot(container);
  if (container) container.__hmbPromptLibraryPublicationOwner = publicationToken;
  hmbClearPromptDirtyText(container);
  if (registerEcho) {
    hmbRegisterPendingPromptStateEcho(
      container,
      value,
      Boolean(props?.disabled),
      publicationToken,
    );
  }
  const fail = (error) => {
    // Even a superseded failure owns its exact echo entry. Removing that token
    // cannot disturb a newer publication and prevents a failed stale payload
    // from being mistaken for a later authoritative host echo.
    if (registerEcho) hmbRemovePendingPromptStateEcho(container, publicationToken);
    if (!container || container.__hmbPromptLibraryPublicationOwner !== publicationToken) {
      return false;
    }
    hmbRestorePromptDirtySnapshot(container, dirtySnapshot);
    hmbReportPromptPublicationFailure(container, error, publicationToken);
    if (retryBudget > 0 && typeof setTimeout === "function") {
      const timer = setTimeout(() => {
        if (container.__hmbPromptLibraryTransportRetryTimer !== timer) return;
        container.__hmbPromptLibraryTransportRetryTimer = null;
        if (container.__hmbPromptLibraryPublicationOwner !== publicationToken) return;
        // This exact retry now owns the pending dirty snapshot. Clear the
        // failure marker before publishing; another failure restores it.
        container.__hmbPromptLibraryCommitPending = false;
        hmbPublishPromptStateValue(
          container,
          props,
          value,
          registerEcho,
          retryBudget - 1,
          onFinalFailure,
        );
      }, HMB_PROMPT_TRANSPORT_RETRY_MS);
      container.__hmbPromptLibraryTransportRetryTimer = timer;
    } else if (typeof onFinalFailure === "function") {
      try { onFinalFailure(error, publicationToken); } catch (_error) {}
    }
    return false;
  };
  const succeed = () => {
    if (container?.__hmbPromptLibraryPublicationOwner === publicationToken) {
      delete container.__hmbPromptLibraryLastPublishError;
      hmbSetPromptPublicationStatus(container, "");
    }
    return true;
  };
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
  return publicationToken;
}

export function hmbEmitLocalPromptState(container, props, state, onFinalFailure = null) {
  const revisionBaseline = {
    currentUiEditRevision: container?.__hmbPromptCurrentUiEditRevision,
    latestLocalUiEditRevision: container?.__hmbPromptLatestLocalUiEditRevision,
    currentSourceSyncRevision: container?.__hmbPromptCurrentSourceSyncRevision,
    currentDisabled: container?.__hmbPromptCurrentDisabled,
  };
  const nextUiEditRevision = hmbNextPromptUiEditRevision(container, state);
  if (state && typeof state === "object") {
    state[UI_EDIT_REVISION_KEY] = nextUiEditRevision;
  }
  const normalized = normalizeState(state);
  normalized[UI_EDIT_REVISION_KEY] = nextUiEditRevision;
  hmbRememberPromptRevisionState(
    container,
    normalized,
    Boolean(props?.disabled),
    true,
  );
  const restoreRejectedRevision = (error, publicationToken) => {
    // A transport rejection is not host authority. Re-admit the exact
    // pre-edit backend revision so its next retained-mode props update can
    // repaint the optimistic control instead of being discarded as stale.
    if (state && typeof state === "object") {
      state[UI_EDIT_REVISION_KEY] = normalizeUiEditRevision(
        revisionBaseline.currentUiEditRevision
          ?? state[UI_EDIT_REVISION_KEY],
      );
    }
    if (container) {
      container.__hmbPromptCurrentUiEditRevision = normalizeUiEditRevision(
        revisionBaseline.currentUiEditRevision,
      );
      container.__hmbPromptLatestLocalUiEditRevision = normalizeUiEditRevision(
        revisionBaseline.latestLocalUiEditRevision,
      );
      container.__hmbPromptCurrentSourceSyncRevision = normalizeSourceSyncRevision(
        revisionBaseline.currentSourceSyncRevision,
      );
      container.__hmbPromptCurrentDisabled = Boolean(
        revisionBaseline.currentDisabled,
      );
    }
    if (typeof onFinalFailure === "function") {
      onFinalFailure(error, publicationToken);
    }
  };
  return hmbPublishPromptStateValue(
    container,
    props,
    JSON.stringify(normalized),
    true,
    1,
    restoreRejectedRevision,
  );
}

// Structural source edits must repaint from their own local state. Griptape
// does not guarantee an immediate props echo when PromptLibrary is used by
// itself, so waiting for a Picker/Asset update makes added rows appear queued.
// Paint first, then register/persist the canonical local echo. A synchronous
// host echo is still consumed, while the user sees the structural result before
// any retained-mode transaction can delay the feedback.
export function hmbCommitLocalPromptStructure(container, props, state, remount, paint = null) {
  hmbClearImmediateStateCommit(container);
  hmbCaptureUiBeforeStateEmit(container, state);
  const rollbackValue = typeof container?.__hmbPromptLastPaintedValue === "string"
    ? container.__hmbPromptLastPaintedValue
    : "";
  const rollbackRevisionState = {
    currentUiEditRevision: container?.__hmbPromptCurrentUiEditRevision,
    latestLocalUiEditRevision: container?.__hmbPromptLatestLocalUiEditRevision,
    currentSourceSyncRevision: container?.__hmbPromptCurrentSourceSyncRevision,
    currentDisabled: container?.__hmbPromptCurrentDisabled,
  };
  let committedState = state;
  if (typeof paint === "function") {
    paint(state);
    try { container.__hmbPromptLastPaintedValue = JSON.stringify(state); } catch (_e) {}
  } else if (typeof remount === "function") committedState = remount() || state;
  else hmbRestoreSourceScroll(container);
  hmbEmitLocalPromptState(container, props, committedState, () => {
    if (!rollbackValue) return;
    const rollbackState = normalizeState(parseValue(rollbackValue));
    // The failed publication never became host authority. Restore the exact
    // pre-edit revision watermarks as well as the visible state; otherwise a
    // legitimate backend echo at the old revision is misclassified as stale
    // and its fresh callback is ignored after rollback.
    rollbackState[UI_EDIT_REVISION_KEY] = normalizeUiEditRevision(
      rollbackRevisionState.currentUiEditRevision
        ?? rollbackState[UI_EDIT_REVISION_KEY],
    );
    if (typeof remount === "function") remount(rollbackState);
    hmbSetPromptPublicationStatus(
      container,
      "Save failed · previous state restored",
      container.__hmbPromptLibraryLastPublishError?.message || "Prompt state publication failed",
    );
    container.__hmbPromptCurrentUiEditRevision = normalizeUiEditRevision(
      rollbackRevisionState.currentUiEditRevision
        ?? rollbackState[UI_EDIT_REVISION_KEY],
    );
    container.__hmbPromptLatestLocalUiEditRevision = normalizeUiEditRevision(
      rollbackRevisionState.latestLocalUiEditRevision
        ?? rollbackState[UI_EDIT_REVISION_KEY],
    );
    container.__hmbPromptCurrentSourceSyncRevision = normalizeSourceSyncRevision(
      rollbackRevisionState.currentSourceSyncRevision
        ?? rollbackState.source_sync_revision,
    );
    container.__hmbPromptCurrentDisabled = Boolean(
      rollbackRevisionState.currentDisabled ?? props?.disabled,
    );
  });
  return committedState;
}

export function hmbConsumePendingPromptStateEcho(container, nextProps) {
  if (!container || !nextProps) return false;
  container.__hmbPromptLastConsumedEchoWasStale = false;
  let incoming = "";
  let incomingState = null;
  try {
    incomingState = normalizeState(parseValue(nextProps.value));
    incoming = JSON.stringify(incomingState);
  } catch (_error) {
    return false;
  }

  // Retained-mode hosts may echo two rapid local edits out of order, and may
  // do so after the short exact-echo queue has expired. The serialized UI edit
  // revision is the durable ordering contract: a lower revision at the same
  // source revision is stale regardless of callback latency. Source revisions
  // and disabled-state changes remain authoritative and must repaint.
  const revisionDisposition = hmbPromptRevisionDisposition(
    container,
    nextProps,
    incomingState,
  );
  if (revisionDisposition === "stale") {
    container.__hmbPromptLastConsumedEchoWasStale = true;
    return true;
  }
  if (revisionDisposition === "authoritative") {
    hmbClearPendingPromptStateEchoes(container);
    return false;
  }

  const pending = Array.isArray(container.__hmbPromptPendingLocalValues)
    ? container.__hmbPromptPendingLocalValues
    : [];
  if (!pending.length) return false;
  const incomingDisabled = Boolean(nextProps.disabled);
  const now = Date.now();
  const livePending = pending.filter((item) => hmbPendingPromptEchoIsLive(item, now));
  const matchIndex = livePending.findIndex((item) => (
    hmbPromptStateEchoMatches(item, incoming, incomingDisabled)
  ));
  if (matchIndex < 0) {
    hmbClearPendingPromptStateEchoes(container);
    return false;
  }
  try {
    // A host may publish the same exact local value more than once. Keep only
    // a short counted allowance. Older queued values may be discarded here:
    // their lower serialized UI revisions identify them after any queue expiry.
    const matched = livePending[matchIndex];
    const configuredRemaining = Number(matched.remainingEchoes);
    const remaining = (Number.isFinite(configuredRemaining)
      ? Math.max(1, Math.trunc(configuredRemaining))
      : 1) - 1;
    const queue = livePending.slice(matchIndex);
    if (remaining > 0) {
      queue[0] = { ...matched, remainingEchoes: remaining };
    } else {
      queue.shift();
    }
    if (queue.length) {
      container.__hmbPromptPendingLocalValues = queue;
    } else {
      hmbClearPendingPromptStateEchoes(container);
    }
  } catch (_error) {}
  return true;
}

export function hmbConsumePendingFrameRangeEcho(container, nextProps) {
  return hmbConsumePendingPromptStateEcho(container, nextProps);
}

export function hmbApplyFrameRangeKeyboard(
  ranges,
  selectedIndex,
  key,
  modifiers = {},
  minimum = 0,
  maximum = MAX_MANUAL_FRAME_NUMBER,
) {
  const min = Math.round(Number(minimum) || 0);
  const max = Math.max(min, Math.round(Number(maximum) || 0));
  const current = normalizeFrameRanges(ranges)
    .map((range) => ({
      start: Math.max(min, Math.min(max, range.start)),
      end: Math.max(min, Math.min(max, range.end)),
    }))
    .filter((range) => range.end >= range.start);
  let selected = Number.isInteger(Number(selectedIndex)) ? Number(selectedIndex) : -1;
  if (selected < 0 || selected >= current.length) selected = current.length ? 0 : -1;
  const normalizedKey = key === "Spacebar" ? " " : String(key || "");
  const handledKeys = new Set([
    "Enter", " ", "Delete", "Backspace", "ArrowLeft", "ArrowRight", "Home", "End",
    "PageUp", "PageDown",
  ]);
  if (!handledKeys.has(normalizedKey)) {
    return { handled: false, changed: false, ranges: current, selectedIndex: selected };
  }
  if (normalizedKey === "Enter" && modifiers.altKey) {
    if (current.length >= MAX_FRAME_RANGES_PER_BINDING) {
      return { handled: true, changed: false, ranges: current, selectedIndex: selected };
    }
    const searchStart = selected >= 0 ? Math.min(max, current[selected].end + 2) : min;
    const span = max - min + 1;
    let frame = null;
    for (let offset = 0; offset < span; offset += 1) {
      const candidate = min + ((searchStart - min + offset) % span);
      const separated = current.every((range) => (
        candidate < range.start - 1 || candidate > range.end + 1
      ));
      if (separated) {
        frame = candidate;
        break;
      }
    }
    if (frame == null) {
      return { handled: true, changed: false, ranges: current, selectedIndex: selected };
    }
    const next = normalizeFrameRanges([...current, { start: frame, end: frame }]);
    const nextSelected = next.findIndex((range) => range.start === frame && range.end === frame);
    return {
      handled: true,
      changed: next.length > current.length,
      ranges: next,
      selectedIndex: nextSelected >= 0 ? nextSelected : selected,
    };
  }
  if (["Enter", " "].includes(normalizedKey)) {
    if (selected >= 0) return { handled: true, changed: false, ranges: current, selectedIndex: selected };
    return {
      handled: true,
      changed: true,
      ranges: [{ start: min, end: min }],
      selectedIndex: 0,
    };
  }
  if (["PageUp", "PageDown"].includes(normalizedKey)) {
    if (!current.length) {
      return { handled: true, changed: false, ranges: current, selectedIndex: -1 };
    }
    const direction = normalizedKey === "PageUp" ? -1 : 1;
    return {
      handled: true,
      changed: false,
      ranges: current,
      selectedIndex: (selected + direction + current.length) % current.length,
    };
  }
  if (selected < 0) {
    return { handled: true, changed: false, ranges: current, selectedIndex: -1 };
  }
  if (["Delete", "Backspace"].includes(normalizedKey)) {
    const next = current.filter((_range, index) => index !== selected);
    return {
      handled: true,
      changed: true,
      ranges: next,
      selectedIndex: next.length ? Math.min(selected, next.length - 1) : -1,
    };
  }

  const next = current.map((range) => ({ ...range }));
  const range = next[selected];
  if (normalizedKey === "Home" || normalizedKey === "End") {
    const length = range.end - range.start;
    const start = normalizedKey === "Home" ? min : Math.max(min, max - length);
    next[selected] = { start, end: Math.min(max, start + length) };
  } else {
    const direction = normalizedKey === "ArrowLeft" ? -1 : 1;
    const amount = modifiers.shiftKey ? 10 : 1;
    if (modifiers.ctrlKey || modifiers.metaKey) {
      range.start = Math.max(min, Math.min(range.end, range.start + direction * amount));
    } else if (modifiers.shiftKey) {
      range.end = Math.min(max, Math.max(range.start, range.end + direction * amount));
    } else {
      const length = range.end - range.start;
      const start = Math.max(min, Math.min(max - length, range.start + direction * amount));
      range.start = start;
      range.end = start + length;
    }
  }
  const changed = JSON.stringify(next) !== JSON.stringify(current);
  return { handled: true, changed, ranges: next, selectedIndex: selected };
}

function hmbInstallFrameRangeInteractions(container, state, props, listeners) {
  const commitFrameState = (row, item) => {
    hmbSyncFrameRangeRowDom(row, item, state);
    hmbCaptureUiBeforeStateEmit(container, state);
    hmbEmitLocalPromptState(container, props, state);
    hmbRestoreSourceScroll(container);
  };
  const itemForElement = (element) => {
    const row = element && element.closest ? element.closest("[data-frame-binding-row]") : null;
    const index = row ? Number(row.getAttribute("data-index")) : -1;
    return { row, index, item: index >= 0 ? state.images[index] : null };
  };

  const changeHandler = (event) => {
    const target = event.target;
    if (!target || !target.closest) return;
    if (target.matches("[data-frame-range-toggle]")) {
      const { row, item } = itemForElement(target);
      if (!item) return;
      setFrameRangeEnabled(item, Boolean(target.checked));
      commitFrameState(row, item);
      return;
    }
    if (target.matches("[data-frame-domain-number]")) {
      const { row, item } = itemForElement(target);
      if (!item) return;
      const status = frameRangeUiStatus(state, item);
      const field = target.getAttribute("data-frame-domain-number");
      const nextValue = normalizeFrameDomainEndpoint(target.value);
      const startFrame = field === "start" ? nextValue : status.domainStart;
      const endFrame = field === "end" ? nextValue : status.domainEnd;
      storeCurrentFrameDomain(item, startFrame, endFrame);
      commitFrameState(row, item);
    }
  };

  const keydownHandler = (event) => {
    const track = event.target && event.target.closest ? event.target.closest("[data-frame-track]") : null;
    if (!track || !container.contains(track)) return;
    const { row, item } = itemForElement(track);
    if (!item) return;
    const status = frameRangeUiStatus(state, item);
    if (!item.frame_range_enabled || !status.metadata) return;
    const result = hmbApplyFrameRangeKeyboard(
      status.ranges,
      Number(item.frame_range_selected_index),
      event.key,
      event,
      status.metadata.start_frame,
      status.metadata.end_frame,
    );
    if (!result.handled) return;
    event.preventDefault();
    event.stopPropagation();
    if (!result.changed && Number(item.frame_range_selected_index) === result.selectedIndex) return;
    storeCurrentFrameRanges(item, result.ranges, result.selectedIndex);
    commitFrameState(row, item);
  };

  const pointerDownHandler = (event) => {
    if (event.button != null && event.button !== 0) return;
    const track = event.target && event.target.closest ? event.target.closest("[data-frame-track]") : null;
    if (!track || !container.contains(track) || !track.classList.contains("editable")) return;
    const { row, item } = itemForElement(track);
    if (!item) return;
    const status = frameRangeUiStatus(state, item);
    if (!item.frame_range_enabled || !status.metadata) return;

    event.preventDefault();
    event.stopPropagation();
    container.__hmbFrameRangeDragCleanup?.();
    const metadata = status.metadata;
    const minimum = metadata.start_frame;
    const maximum = metadata.end_frame;
    const originalRanges = status.ranges.map((range) => ({ ...range }));
    const bar = event.target.closest(".frame-range-bar");
    const handle = event.target.closest("[data-frame-range-handle]");
    const rangeIndex = bar ? Number(bar.getAttribute("data-frame-range-index")) : -1;
    const mode = handle
      ? (handle.getAttribute("data-frame-range-handle") === "start" ? "resize-start" : "resize-end")
      : bar
        ? "move"
        : "create";
    const anchorFrame = frameFromPointer(event, track, minimum, maximum);
    const anchorClientX = Number(event.clientX || 0);
    let previewRanges = originalRanges.map((range) => ({ ...range }));
    let previewSelected = rangeIndex;
    let movedPixels = 0;

    const moveHandler = (moveEvent) => {
      moveEvent.preventDefault();
      movedPixels = Math.max(movedPixels, Math.abs(Number(moveEvent.clientX || 0) - anchorClientX));
      const frame = frameFromPointer(moveEvent, track, minimum, maximum);
      previewRanges = originalRanges.map((range) => ({ ...range }));
      if (mode === "create") {
        previewRanges.push({ start: Math.min(anchorFrame, frame), end: Math.max(anchorFrame, frame) });
        previewSelected = previewRanges.length - 1;
      } else if (previewRanges[rangeIndex]) {
        const original = originalRanges[rangeIndex];
        if (mode === "move") {
          const length = original.end - original.start;
          const requestedStart = original.start + (frame - anchorFrame);
          const nextStart = Math.max(minimum, Math.min(maximum - length, requestedStart));
          previewRanges[rangeIndex] = { start: nextStart, end: nextStart + length };
        } else if (mode === "resize-start") {
          previewRanges[rangeIndex].start = Math.max(minimum, Math.min(original.end, frame));
        } else {
          previewRanges[rangeIndex].end = Math.min(maximum, Math.max(original.start, frame));
        }
      }
      updateFrameTrackPreview(track, previewRanges, metadata, previewSelected, `${previewRanges[previewSelected]?.start || anchorFrame}–${previewRanges[previewSelected]?.end || frame}`);
    };

    const removeDocumentListeners = () => {
      document.removeEventListener("pointermove", moveHandler, true);
      document.removeEventListener("pointerup", upHandler, true);
      document.removeEventListener("pointercancel", cancelHandler, true);
      if (container.__hmbFrameRangeDragCleanup === removeDocumentListeners) {
        delete container.__hmbFrameRangeDragCleanup;
      }
    };
    const cancelHandler = () => {
      removeDocumentListeners();
      updateFrameTrackPreview(track, originalRanges, metadata, Number(item.frame_range_selected_index), status.status);
    };
    const upHandler = (upEvent) => {
      removeDocumentListeners();
      try { track.releasePointerCapture?.(upEvent.pointerId); } catch (_error) {}
      if (mode === "create" && movedPixels < 6) {
        updateFrameTrackPreview(track, originalRanges, metadata, Number(item.frame_range_selected_index), status.status);
        return;
      }
      if (mode !== "create" && movedPixels < 3) {
        if (Number(item.frame_range_selected_index) === rangeIndex) {
          updateFrameTrackPreview(track, originalRanges, metadata, rangeIndex, status.status);
          return;
        }
        item.frame_range_selected_index = rangeIndex;
        storeCurrentFrameRanges(item, originalRanges, rangeIndex);
        commitFrameState(row, item);
        return;
      }
      const normalized = normalizeFrameRanges(previewRanges);
      const targetRange = previewRanges[Math.max(0, previewSelected)];
      const selected = targetRange
        ? normalized.findIndex((range) => range.start <= targetRange.start && range.end >= targetRange.end)
        : -1;
      storeCurrentFrameRanges(item, normalized, Math.max(0, selected));
      commitFrameState(row, item);
    };

    container.__hmbFrameRangeDragCleanup = removeDocumentListeners;
    try { track.setPointerCapture?.(event.pointerId); } catch (_error) {}
    document.addEventListener("pointermove", moveHandler, true);
    document.addEventListener("pointerup", upHandler, true);
    document.addEventListener("pointercancel", cancelHandler, true);
  };

  const bind = (element, eventName, handler) => {
    if (!element) return;
    element.addEventListener(eventName, handler);
    listeners.push([element, eventName, handler]);
  };
  // Bind Range behavior directly on its controls; the surrounding IMAGE
  // SOURCE BINDING background remains available to Griptape canvas gestures.
  container.querySelectorAll(
    "[data-frame-range-toggle], [data-frame-domain-number]",
  ).forEach((element) => bind(element, "change", changeHandler));
  container.querySelectorAll("[data-frame-track]").forEach((track) => {
    bind(track, "keydown", keydownHandler);
    bind(track, "pointerdown", pointerDownHandler);
  });
}

function renderColorPickControls(item, rowIndex, images, state) {
  const count = MAX_VIDEOS;
  normalizeImageBindingFields(item, count);
  const title = escapeHtml(uiText(state, "video_marker_source", "video marker source"));
  return `<div class="video-color-pick-wrap"><div class="color-pick-stack">${item.color_picks.map((pick, pickIndex) => `<div class="color-binding-entry"><select class="source-select image-video-index binding-video-index" data-field="binding_video_slots" data-binding-index="${pickIndex}" title="${title}" aria-label="${title}">${videoNumberOptions(state, item.binding_video_slots[pickIndex])}</select><select class="source-select color-pick-select" data-field="color_picks" data-color-index="${pickIndex}" aria-label="${escapeHtml(uiText(state, "video_color_pick", "Video / Color Pick"))}">${colorPickOptions(images, rowIndex, pickIndex, count, state)}</select></div>`).join("")}</div></div>`;
}

function videoNumberChoices(current) {
  const choices = editableVideoSlotChoices();
  const savedValue = String(normalizeMarkerVideo(current, MAX_VIDEOS));
  return uniqueList(choices.includes(savedValue)
    ? choices
    : [savedValue, ...choices]);
}

function videoNumberOptions(state, current) {
  const savedValue = String(normalizeMarkerVideo(current, MAX_VIDEOS));
  return options(videoNumberChoices(current), savedValue, "1", state);
}

function renderImageActions(item, state, index, imageCount) {
  const pickerActions = hmbImagePickerActionAvailability(state, item);
  const canRemove = pickerActions.canRemove;
  const canAdd = pickerActions.canAdd;
  const orderManaged = Boolean(state?.image_asset?.enabled && state?.image_asset?.order_managed);
  const rowManaged = Boolean(orderManaged && item?.asset_managed);
  const canMoveUp = !orderManaged && index > 0;
  const canMoveDown = !orderManaged && index < Math.max(0, Number(imageCount || 0) - 1);
  const orderTitle = orderManaged
    ? "Order is controlled by HMBImageAssetLibrary"
    : uiText(state, "move_image_up", "Move image up");
  const deleteLabel = rowManaged ? "Deselect this source in HMBImageAssetLibrary" : uiText(state, "delete_image_row", "Delete image source row");
  const downLabel = orderManaged ? "Order is controlled by HMBImageAssetLibrary" : uiText(state, "move_image_down", "Move image down");
  return `<div class="source-actions image-actions"><button class="clear-source" ${rowManaged ? "disabled" : ""} title="${escapeHtml(deleteLabel)}" aria-label="${escapeHtml(deleteLabel)}">X</button><span class="image-order-controls"><button class="move-image-up" ${canMoveUp ? "" : "disabled"} title="${escapeHtml(orderTitle)}" aria-label="${escapeHtml(orderTitle)}">▲</button><button class="move-image-down" ${canMoveDown ? "" : "disabled"} title="${escapeHtml(downLabel)}" aria-label="${escapeHtml(downLabel)}">▼</button></span><button class="remove-color-pick" ${canRemove ? "" : "disabled"} title="${escapeHtml(uiText(state, "remove_color_pick", "Remove Color Pick"))}" aria-label="${escapeHtml(uiText(state, "remove_color_pick", "Remove Color Pick"))}">-</button><button class="add-color-pick" ${canAdd ? "" : "disabled"} title="${escapeHtml(uiText(state, "add_color_pick", "Add Color Pick"))}" aria-label="${escapeHtml(uiText(state, "add_color_pick", "Add Color Pick"))}">+</button></div>`;
}

function remapImageSourceReferences(value, slotMap) {
  const source = String(value == null ? "" : value);
  if (!source || !(slotMap instanceof Map) || !slotMap.size) return source;
  return source.replace(/@image(\d+)(?!\d)/gi, (token, rawSlot) => {
    const slot = Number(rawSlot);
    if (!slotMap.has(slot)) return token;
    const nextSlot = Number(slotMap.get(slot) || 0);
    // Preserve a removed reference without allowing it to bind to a promoted
    // row that later inherits the old slot number.
    return nextSlot > 0 ? `@image${nextSlot}` : `[deselected image source #${slot}]`;
  });
}

function remapImageSourceReferencesInState(state, slotMap) {
  if (!state || !(slotMap instanceof Map) || !slotMap.size) return;
  if (state.text && typeof state.text === "object") {
    Object.keys(state.text).forEach((key) => {
      if (key === "PRESERVED_TEXT") return;
      state.text[key] = remapImageSourceReferences(state.text[key], slotMap);
    });
  }
  (Array.isArray(state.videos) ? state.videos : []).forEach((item) => {
    if (!item || typeof item !== "object") return;
    item.keep_out = remapImageSourceReferences(item.keep_out, slotMap);
  });
}

function renumberImageRows(images) {
  (Array.isArray(images) ? images : []).forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const slot = index + 1;
    item.slot = slot;
    item.token = `@image${slot}`;
    item.name = `IMAGE_${String(slot).padStart(2, "0")}`;
  });
}

export function swapImageRowsWithoutReset(state, firstIndex, secondIndex) {
  if (!state || !Array.isArray(state.images)) return false;
  if (firstIndex < 0 || secondIndex < 0 || firstIndex >= state.images.length || secondIndex >= state.images.length || firstIndex === secondIndex) return false;
  const firstSlot = firstIndex + 1;
  const secondSlot = secondIndex + 1;
  const temporary = state.images[firstIndex];
  state.images[firstIndex] = state.images[secondIndex];
  state.images[secondIndex] = temporary;
  renumberImageRows(state.images);
  remapImageSourceReferencesInState(state, new Map([
    [firstSlot, secondSlot],
    [secondSlot, firstSlot],
  ]));
  return true;
}

export function moveImageRowWithoutReset(state, sourceIndex, targetIndex) {
  if (!state || !Array.isArray(state.images)) return false;
  const count = state.images.length;
  const source = Math.trunc(Number(sourceIndex));
  const target = Math.trunc(Number(targetIndex));
  if (source < 0 || target < 0 || source >= count || target >= count || source === target) return false;
  let current = source;
  const direction = target > source ? 1 : -1;
  while (current !== target) {
    if (!swapImageRowsWithoutReset(state, current, current + direction)) return false;
    current += direction;
  }
  return true;
}

export function removeImageRowAndPromote(state, sourceIndex) {
  if (!state || !Array.isArray(state.images) || !state.images.length) {
    return { changed: false, removedSlot: 0, remaining: 0 };
  }
  const index = Math.trunc(Number(sourceIndex));
  if (index < 0 || index >= state.images.length) {
    return { changed: false, removedSlot: 0, remaining: state.images.length };
  }
  const originalCount = state.images.length;
  const removedSlot = index + 1;
  const removedItem = state.images[index];
  const slotMap = new Map();
  for (let slot = 1; slot <= originalCount; slot += 1) {
    if (slot === removedSlot) slotMap.set(slot, 0);
    else if (slot > removedSlot) slotMap.set(slot, slot - 1);
  }
  if (originalCount === 1) {
    state.images[0] = defaultImage(1);
  } else {
    state.images.splice(index, 1);
    renumberImageRows(state.images);
  }
  if (
    state.picker
    && typeof state.picker === "object"
    && (
      clean(removedItem?.picker_auto_color)
      || Number(removedItem?.picker_auto_video || 0) > 0
      || clean(removedItem?.picker_auto_source)
    )
  ) {
    state.picker.matched_images = Math.max(0, Number(state.picker.matched_images || 0) - 1);
  }
  remapImageSourceReferencesInState(state, slotMap);
  return { changed: true, removedSlot, remaining: state.images.length };
}

function renderVideoActions(state) {
  const pickerLocked = hmbPromptVideoRowsLocked(state);
  const label = pickerLocked
    ? uiText(
      state,
      "delete_video_row_picker_locked",
      "Video rows cannot be deleted while Picker is connected",
    )
    : uiText(state, "delete_video_row", "Delete video source row");
  return `<div class="source-actions"><button class="clear-source" data-picker-locked="${pickerLocked ? "true" : "false"}" ${pickerLocked ? "disabled" : ""} title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">X</button></div>`;
}

export function hmbCanAddPromptImageRow(state, images = state?.images) {
  return !Boolean(state?.image_asset?.enabled) && (images || []).length < MAX_IMAGES;
}

export function hmbPromptVideoRowsLocked(state) {
  return Boolean(state?.picker?.enabled);
}

export function hmbCanAddPromptVideoRow(state, videos = state?.videos) {
  return !hmbPromptVideoRowsLocked(state) && (videos || []).length < MAX_VIDEOS;
}

function renderImageAddRow(images, state) {
  const assetLocked = Boolean(state?.image_asset?.enabled);
  const canAdd = hmbCanAddPromptImageRow(state, images);
  const label = assetLocked
    ? uiText(
      state,
      "add_image_row_asset_locked",
      "Image rows cannot be added while Image Asset Library is connected",
    )
    : uiText(state, "add_image_row", "Add image source row");
  return `<div class="source-row image image-add-row" data-kind="image-add"><div></div><div></div><div></div><div></div><div></div><div></div><div class="source-status"><div class="source-actions"><button class="add-image-source" data-asset-locked="${assetLocked ? "true" : "false"}" ${canAdd ? "" : "disabled"} title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">+</button></div></div></div>`;
}

function renderVideoAddRow(videos, state) {
  const canAdd = hmbCanAddPromptVideoRow(state, videos);
  const label = uiText(state, "add_video_row", "Add video source row");
  return `<div class="source-row video video-add-row" data-kind="video-add"><div></div><div></div><div></div><div></div><div></div><div class="source-status"><div class="source-actions"><button class="add-video-source" ${canAdd ? "" : "disabled"} title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">+</button></div></div></div>`;
}

function subjectNumberFromOwner(owner) {
  const match = clean(owner).match(/^Subject\s+(\d+)$/);
  return match ? Number(match[1]) : null;
}

function uniqueList(items) {
  const out = [];
  items.forEach((item) => {
    if (item == null) return;
    const value = String(item);
    if (!out.includes(value)) out.push(value);
  });
  return out;
}

function imageTargetLabel(item, _index) {
  return clean(item && item.label);
}

function imageTargetChoicesForRow(item, images) {
  const dynamicTargets = (images || []).filter(isActiveImage).map((row, idx) => imageTargetLabel(row, idx)).filter(Boolean);
  const sourceType = clean(item && item.source_type);
  let choices = ["", ...dynamicTargets];
  if (sourceType === "Ignore / Unused") {
    choices = ["", "None"];
  } else if (["Environment / Background", "Sky / Exterior Background", "Set / Structure", "Foreground / Ground"].includes(sourceType)) {
    choices = ["", ...dynamicTargets, "Scene / Environment"];
  } else if (sourceType === "Scale / Composition Reference") {
    choices = ["", ...dynamicTargets, "Camera / Composition"];
  } else if (["Color / Look Reference", "Color + Look + Lighting Mood Reference", "Lighting / Atmosphere Reference"].includes(sourceType)) {
    choices = ["", ...dynamicTargets, "Global Look"];
  } else if (sourceType === "Custom") {
    choices = ["", ...dynamicTargets, "Scene / Environment", "Camera / Composition", "Global Look"];
  }
  const currentTarget = clean(item && item.owner);
  if (currentTarget) choices.push(currentTarget);
  return uniqueList(choices);
}

function targetSelectOptions(item, images, state) {
  return options(
    imageTargetChoicesForRow(item, images),
    clean(item && item.owner),
    uiText(state, "blank_target", "— blank / no target —"),
    state
  );
}

function refreshImageTargetControls(container, state) {
  try {
    const images = state && Array.isArray(state.images) ? state.images : [];
    container.querySelectorAll('.source-row.image').forEach((row) => {
      const index = Number(row.getAttribute('data-index') || -1);
      const item = images[index];
      const select = row.querySelector('select[data-field="owner"]');
      if (!item || !select) return;
      hmbSyncSelectOptions(
        select,
        imageTargetChoicesForRow(item, images),
        clean(item.owner),
        uiText(state, "blank_target", "— blank / no target —"),
        state,
      );
    });
  } catch (_e) {}
}

function imageScopeChoicesForRow(item, currentValue) {
  const sourceType = clean(item && item.source_type);
  const current = clean(currentValue);
  let choices = Array.isArray(IMAGE_SCOPES_BY_SOURCE_TYPE[sourceType])
    ? [...IMAGE_SCOPES_BY_SOURCE_TYPE[sourceType]]
    : [...IMAGE_SCOPES];
  if (!choices.length) choices = [""];
  if (current && !choices.includes(current)) choices.splice(Math.max(1, choices.length - 1), 0, current);
  return uniqueList(choices);
}

function reconcileImageBindingAfterTypeChange(item, images) {
  if (!item) return;
  // A Main Type edit changes interpretation, never authored data. Preserve
  // Target, Sub Type, Color Pick, and dormant slot addresses verbatim.
  normalizeImageBindingFields(item, MAX_VIDEOS);
  item.scope = item.binding_scopes[0] || "";
}

function renderImageCustomPanel(item, state) {
  const visible = item.source_type === "Custom";
  return `<div class="custom-fields-panel image-custom-panel ${visible ? "" : "is-hidden"}" aria-hidden="${visible ? "false" : "true"}"><label><span>${escapeHtml(uiText(state, "main_type", "MAIN TYPE"))}</span><input class="custom-field-input" data-field="custom_source_type" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.custom_source_type || "")}" placeholder="${escapeHtml(uiText(state, "custom_main_type", "Custom main type input"))}"/></label></div>`;
}

function compatibleVideoSourceTypeChoices(item, primaryVideo) {
  return primaryVideoTypeChoices(item && item.source_type);
}

export function compatibleVideoRoleChoices(item, _primaryVideo = false) {
  const sourceType = clean(item?.source_type);
  const compatible = VIDEO_ROLE_COMPATIBILITY[sourceType];
  if (!Array.isArray(compatible)) return [...VIDEO_CONTROL_ROLES];
  const choices = ["", ...compatible];
  const current = canonicalVideoRole(item?.control_role);
  const prohibitedPair = Boolean(
    sourceType === "Maya Preview / Playblast"
    && current === "Primary Unified Shot Control"
  );
  // A saved manual value remains visible until the user changes it.  New
  // choices are constrained by the authoritative main-type compatibility map.
  if (current && !choices.includes(current) && !prohibitedPair) {
    choices.push(current);
  }
  return uniqueList(choices);
}

function renderVideoCustomPanel(item, state) {
  const sourceVisible = item.source_type === "Custom";
  const roleVisible = item.control_role === "Custom Role";
  return `<div class="custom-fields-panel video-custom-panel ${sourceVisible || roleVisible ? "" : "is-hidden"}" aria-hidden="${sourceVisible || roleVisible ? "false" : "true"}"><label class="video-custom-source ${sourceVisible ? "" : "is-hidden"}"><span>${escapeHtml(uiText(state, "main_type", "MAIN TYPE"))}</span><input class="custom-field-input" data-field="custom_source_type" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.custom_source_type || "")}" placeholder="${escapeHtml(uiText(state, "custom_video_type", "Custom video type input"))}"/></label><label class="video-custom-role ${roleVisible ? "" : "is-hidden"}"><span>${escapeHtml(uiText(state, "sub_type", "SUB TYPE"))}</span><input class="custom-field-input" data-field="custom_control_role" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.custom_control_role || "")}" placeholder="${escapeHtml(uiText(state, "custom_video_role", "Custom video role input"))}"/></label></div>`;
}

function hmbSetVisible(element, visible) {
  if (!element) return;
  element.classList?.toggle("is-hidden", !visible);
  element.setAttribute?.("aria-hidden", visible ? "false" : "true");
}

export function hmbImageRowHasExpandedLeftFields(item) {
  return clean(item?.binding_scopes?.[0]) === "Custom scope";
}

function hmbRefreshImageSubtypeControls(row, item, state) {
  if (!row || !item) return;
  normalizeImageBindingFields(item, videoSlotCount(state));
  row.classList?.toggle(
    "image-expanded-left-fields",
    hmbImageRowHasExpandedLeftFields(item),
  );
  row.querySelectorAll?.('select[data-field="binding_scopes"]').forEach((select) => {
    const bindingIndex = Number(select.getAttribute("data-binding-index") || 0);
    const scope = clean(item.binding_scopes[bindingIndex]);
    hmbSyncSelectOptions(
      select,
      imageScopeChoicesForRow(item, scope),
      scope,
      uiText(state, "blank_subtype", "— blank / no subtype —"),
      state,
    );
    const input = select.closest?.(".binding-scope-entry")?.querySelector?.(".custom-inline-input");
    if (input) {
      input.value = clean(item.binding_custom_scopes[bindingIndex]);
      hmbSetVisible(input, scope === "Custom scope");
    }
  });
}

function hmbRefreshImageCustomPanel(row, item) {
  if (!row || !item) return;
  const panel = row.querySelector?.(".image-custom-panel");
  const visible = item.source_type === "Custom";
  hmbSetVisible(panel, visible);
  const input = panel?.querySelector?.('[data-field="custom_source_type"]');
  if (input) input.value = clean(item.custom_source_type);
}

function hmbRefreshVideoDependentControls(row, item, index, state) {
  if (!row || !item) return;
  const primaryVideo = index === 0;
  const typeSelect = row.querySelector?.('select[data-field="source_type"]');
  if (typeSelect) typeSelect.value = clean(item.source_type);
  const roleSelect = row.querySelector?.('select[data-field="control_role"]');
  if (roleSelect) {
    const blankRole = uiText(state, "blank_control_role", "— optional / choose role —");
    hmbSyncSelectOptions(
      roleSelect,
      compatibleVideoRoleChoices(item, primaryVideo),
      item.control_role,
      blankRole,
      state,
    );
  }
  const panel = row.querySelector?.(".video-custom-panel");
  const sourceVisible = item.source_type === "Custom";
  const roleVisible = item.control_role === "Custom Role";
  hmbSetVisible(panel, sourceVisible || roleVisible);
  hmbSetVisible(panel?.querySelector?.(".video-custom-source"), sourceVisible);
  hmbSetVisible(panel?.querySelector?.(".video-custom-role"), roleVisible);
  const sourceInput = panel?.querySelector?.('[data-field="custom_source_type"]');
  const roleInput = panel?.querySelector?.('[data-field="custom_control_role"]');
  if (sourceInput) sourceInput.value = clean(item.custom_source_type);
  if (roleInput) roleInput.value = clean(item.custom_control_role);
  hmbSyncSourceRowActivation(row);
}

function hmbRefreshImageColorControls(container, state) {
  const images = Array.isArray(state && state.images) ? state.images : [];
  const count = MAX_VIDEOS;
  images.forEach((item, rowIndex) => {
    normalizeImageBindingFields(item, count);
    const row = container.querySelector?.(`.source-row.image[data-index="${rowIndex}"]`);
    if (!row) return;
    const sourceType = row.querySelector?.('select[data-field="source_type"]');
    if (sourceType) sourceType.value = clean(item.source_type);
    row.querySelectorAll?.('select[data-field="binding_video_slots"]').forEach((select) => {
      const bindingIndex = Number(select.getAttribute("data-binding-index") || 0);
      const videoSlot = item.binding_video_slots[bindingIndex];
      hmbSyncSelectOptions(
        select,
        videoNumberChoices(videoSlot),
        String(normalizeMarkerVideo(videoSlot, MAX_VIDEOS)),
        "1",
        state,
      );
      select.disabled = false;
      select.setAttribute?.("data-hmb-base-disabled", "0");
    });
    row.querySelectorAll?.('select[data-field="color_picks"]').forEach((select) => {
      const pickIndex = Number(select.getAttribute("data-color-index") || 0);
      const pick = clean(item.color_picks[pickIndex]);
      hmbSyncSelectOptions(
        select,
        colorPickChoices(images, rowIndex, pickIndex, count),
        pick,
        "—",
        state,
      );
      select.disabled = false;
      select.setAttribute?.("data-hmb-base-disabled", "0");
    });
    const pickerActions = hmbImagePickerActionAvailability(state, item);
    const removePick = row.querySelector?.(".remove-color-pick");
    const addPick = row.querySelector?.(".add-color-pick");
    if (removePick) {
      removePick.disabled = !pickerActions.canRemove;
      removePick.setAttribute?.("data-hmb-base-disabled", removePick.disabled ? "1" : "0");
    }
    if (addPick) {
      addPick.disabled = !pickerActions.canAdd;
      addPick.setAttribute?.("data-hmb-base-disabled", addPick.disabled ? "1" : "0");
    }
    hmbRefreshImageSubtypeControls(row, item, state);
    hmbRefreshImageCustomPanel(row, item);
    const frameRow = row.querySelector?.("[data-frame-binding-row]");
    if (frameRow) hmbSyncFrameRangeRowDom(frameRow, item, state);
    hmbSyncSourceRowActivation(row);
  });
}

function hmbRefreshSourceSummaries(container, state) {
  const images = Array.isArray(state && state.images) ? state.images : [];
  const videos = Array.isArray(state && state.videos) ? state.videos : [];
  const activeImages = images.filter((item) => isActiveImageForState(item, state)).length;
  const activeVideos = videos.filter(isActiveVideo).length;
  const imageCount = container.querySelector?.('[data-group-id="imageSources"] h3 b');
  const videoCount = container.querySelector?.('[data-group-id="videoSources"] h3 b');
  if (imageCount) imageCount.textContent = `${activeImages} / ${MAX_IMAGES}`;
  if (videoCount) videoCount.textContent = `${activeVideos} / ${MAX_VIDEOS}`;
}

function hmbSyncSourceSelectDom(container, state, row, kind, index, field) {
  const target = kind === "image" ? state.images : state.videos;
  const item = target && target[index];
  if (!row || !item) return;
  if (kind === "image") {
    const sourceType = row.querySelector?.('select[data-field="source_type"]');
    if (sourceType) sourceType.value = clean(item.source_type);
    if (field === "source_type" || field === "owner") {
      refreshImageTargetControls(container, state);
    }
    if (field === "source_type" || field === "color_picks" || field === "binding_video_slots") {
      hmbRefreshImageColorControls(container, state);
    } else if (field === "binding_scopes") {
      hmbRefreshImageSubtypeControls(row, item, state);
      hmbSyncSourceRowActivation(row);
    }
  } else {
    hmbRefreshVideoDependentControls(row, item, index, state);
    if (field === "source_type") hmbRefreshImageColorControls(container, state);
  }
  hmbRefreshSourceSummaries(container, state);
}

function renderImageRow(item, index, images, state) {
  normalizeImageBindingFields(item, videoSlotCount(state));
  const sourceTypeChoices = IMAGE_SOURCE_TYPES.length
    ? IMAGE_SOURCE_TYPES
    : uniqueList([item.source_type]);
  const orderManaged = Boolean(state?.image_asset?.enabled && state?.image_asset?.order_managed);
  const rowManaged = Boolean(orderManaged && item.asset_managed);
  const verifiedAsset = Boolean(
    rowManaged
    && item.asset_verified
    && clean(item.asset_source_kind).toLowerCase() === "project"
  );
  const dragEnabled = !orderManaged && images.length > 1;
  const identityTitle = verifiedAsset
    ? "Image Name, Asset ID, Main Type, registered Sub Type, and @image order are controlled by HMBImageAssetLibrary; Target remains editable"
    : (rowManaged
      ? "Generator order is controlled by HMBImageAssetLibrary; Name and Prompt fields remain editable"
      : (item.asset_id ? `Asset ID: ${item.asset_id}` : ""));
  const expandedLeftFields = hmbImageRowHasExpandedLeftFields(item);
  return `<div class="source-row image ${item.present ? "active" : "next"} ${rowManaged ? "asset-order-managed" : ""} ${verifiedAsset ? "asset-authority-managed" : ""} ${expandedLeftFields ? "image-expanded-left-fields" : ""}" data-kind="image" data-index="${index}" data-source-key="${escapeHtml(hmbPromptSourceIdentity(item, "image"))}">
    <div class="source-num image-index-cell image-drag-handle nodrag" data-image-drag-handle draggable="${dragEnabled ? "true" : "false"}" role="button" tabindex="${dragEnabled ? "0" : "-1"}" aria-label="${escapeHtml(dragEnabled ? uiText(state, "drag_image_row", "Drag or use arrow keys to reorder image source") : (orderManaged ? "Order is controlled by HMBImageAssetLibrary" : ""))}" title="${escapeHtml(dragEnabled ? uiText(state, "drag_image_row", "Drag to reorder image source") : (orderManaged ? "Order is controlled by HMBImageAssetLibrary" : ""))}">${String(item.slot).padStart(2, "0")}</div>
    <div class="source-label image-name-cell"><input class="source-label-input" data-field="label" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.label)}" placeholder="${escapeHtml(uiText(state, "name", "Name"))}" title="${escapeHtml(identityTitle)}" ${verifiedAsset ? "readonly" : ""}/></div>
    <div class="source-role image-main-type-cell"><select class="source-select" data-field="source_type" ${verifiedAsset ? "disabled" : ""}>${options(sourceTypeChoices, item.source_type, "", state)}</select></div>
    <div class="source-role binding-scope-cell">${renderSubtypeControls(item, state, Boolean(verifiedAsset && verifiedRegisteredSubtype(item)))}</div>
    <div class="source-role image-target-cell"><select class="source-select source-target-select" data-field="owner">${targetSelectOptions(item, images, state)}</select></div>
    <div class="source-role color-pick-cell">${renderColorPickControls(item, index, images, state)}</div>
    <div class="source-status image-actions-cell">${renderImageActions(item, state, index, images.length)}</div>
    ${renderFrameRangeRow(item, index, state)}
    ${renderImageCustomPanel(item, state)}
  </div>`;
}

function renderVideoRow(item, index, images, state) {
  const primaryVideo = index === 0;
  const roleChoices = compatibleVideoRoleChoices(item, primaryVideo);
  const blankRole = uiText(state, "blank_control_role", "— optional / choose role —");
  const keepOutKey = hmbTextareaKey("video", index + 1, "keep_out");
  return `<div class="source-row video ${item.present ? "active" : "next"}" data-kind="video" data-index="${index}" data-source-key="${escapeHtml(hmbPromptSourceIdentity(item, "video"))}">
    <div class="source-num">${String(item.slot).padStart(2, "0")}<br/><b>${escapeHtml(item.token)}</b></div>
    <div class="source-label"><input class="source-label-input" data-field="label" maxlength="${MAX_IDENTIFIER_CHARS}" value="${escapeHtml(item.label)}" placeholder="${escapeHtml(uiText(state, "name", "Name"))}"/></div>
    <div class="source-role"><select class="source-select" data-field="source_type">${options(compatibleVideoSourceTypeChoices(item, primaryVideo), item.source_type, "", state)}</select></div>
    <div class="source-role"><select class="source-select" data-field="control_role">${options(roleChoices, item.control_role, blankRole, state)}</select></div>
    <div class="source-label source-textarea keep-out-field"><div class="keep-out-resize-shell"><textarea class="source-label-input source-note-input" data-field="keep_out" maxlength="${MAX_KEEP_OUT_CHARS}" ${hmbTextareaAttrs(state, keepOutKey)} placeholder="${escapeHtml(uiText(state, "keep_out_placeholder", "Keep Out: dummy FX, timing-guide regions, marker-only guide areas, preview artifacts, proxy effects, and anything not allowed in final output"))}">${escapeHtml(item.keep_out)}</textarea><div class="keep-out-resize-bar nodrag" data-resize-textarea="${escapeHtml(keepOutKey)}" title="${escapeHtml(uiText(state, "resize_keep_out", "Drag down/up to resize this Keep Out field"))}"></div></div></div>
    <div class="source-status">${renderVideoActions(state)}</div>
    ${renderVideoCustomPanel(item, state)}
  </div>`;
}

function textField(key, label, value, placeholder, state) {
  const localized = localizedTextField(key, label, placeholder, state);
  const maxChars = key === "VIDEO_VFX" ? MAX_VIDEO_VFX_CHARS : MAX_DESCRIPTION_CHARS;
  const tag = `<textarea data-text-key="${escapeHtml(key)}" maxlength="${maxChars}" ${hmbTextareaAttrs(state, hmbTextareaKey("text", key, "value"))} rows="2" placeholder="${escapeHtml(localized[1])}">${escapeHtml(value)}</textarea>`;
  return `<label class="text-field"><span>${escapeHtml(localized[0])}</span>${tag}</label>`;
}

export const HMB_JEWEL_NIGHT_SHOT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});

export function hmbPromptShotAccent(state) {
  return HMB_JEWEL_NIGHT_SHOT_PALETTE[hmbPromptPaletteShotNumber(state)];
}

export function hmbPromptPaletteShotNumber(state) {
  const current = normalizeShotSelection(state?.shot);
  if (!current.shot_uuid || !current.channel_uuid) return 1;
  const routing = normalizeShotCatalogRouting(state?.image_asset?.shot_catalog_routing);
  if (
    !routing.publisher_instance_uuid
    || routing.channel_uuid !== current.channel_uuid
    || routing.generation < 1
    || !/^[0-9a-f]{64}$/i.test(routing.metadata_sha256)
  ) return 1;
  const exact = normalizeShotCatalog(state?.image_asset?.shot_catalog).find((item) => (
    item.shot_uuid === current.shot_uuid
    && item.channel_uuid === current.channel_uuid
    && item.number === current.number
  ));
  return exact ? exact.number : 1;
}

export function hmbApplyPromptShotFeedback(container, state) {
  if (!container || !state) return false;
  const selectorPatched = hmbPatchPromptShotSelector(container, state);
  const dashboard = container.querySelector?.(".hmb-dashboard");
  dashboard?.setAttribute?.(
    "data-shot-number",
    String(hmbPromptPaletteShotNumber(state)),
  );
  return Boolean(selectorPatched || dashboard);
}

export const HMB_PROMPT_ONLY_SHOT_VALUE = "__hmb_only__";

export function hmbPromptVerifiedShotCatalog(state) {
  const routing = normalizeShotCatalogRouting(state?.image_asset?.shot_catalog_routing);
  if (
    !routing.publisher_instance_uuid
    || !routing.channel_uuid
    || routing.generation < 1
    || !/^[0-9a-f]{64}$/i.test(routing.metadata_sha256)
  ) return [];
  const catalog = normalizeShotCatalog(state?.image_asset?.shot_catalog).filter((item) => (
    item.channel_uuid === routing.channel_uuid
  ));
  if (!catalog.length) return [];
  if (catalog.some((item, index) => (
    item.number < 1
    || item.number > 5
    || (index > 0 && item.number <= catalog[index - 1].number)
  ))) return [];
  return catalog;
}

export function hmbPromptShotOptions(state) {
  const current = normalizeShotSelection(state?.shot);
  const catalog = hmbPromptVerifiedShotCatalog(state);
  const exact = catalog.find((item) => (
    item.shot_uuid === current.shot_uuid && item.channel_uuid === current.channel_uuid
  ));
  return [
    {
      value: HMB_PROMPT_ONLY_SHOT_VALUE,
      shot_uuid: "",
      channel_uuid: "",
      number: 0,
      name: "Only",
      selected: !exact,
      only: true,
    },
    ...catalog.map((item) => ({
      ...item,
      value: item.shot_uuid,
      selected: item.shot_uuid === exact?.shot_uuid,
      only: false,
    })),
  ];
}

function hmbPromptShotOptionNodes(selector) {
  const direct = Array.from(selector?.options || []);
  return direct.length
    ? direct
    : Array.from(selector?.querySelectorAll?.("option") || []);
}

function hmbPromptShotOptionLabel(item) {
  return item.only
    ? "Only"
    : `${String(item.number).padStart(2, "0")} · ${item.name}`;
}

// Patch only the Shot selector for backend catalog churn.  The select element
// and its change listener remain stable while option nodes are keyed by the
// publisher-owned Shot UUID, so add/rename/delete does not rebuild the topbar
// or disturb an editor elsewhere in the Prompt dashboard.
export function hmbPatchPromptShotSelector(container, state) {
  const selector = container?.querySelector?.("[data-shot-selector]");
  if (!selector) return false;
  const desired = hmbPromptShotOptions(state);
  const existing = new Map(
    hmbPromptShotOptionNodes(selector).map((option) => [clean(option?.value), option]),
  );
  const ownerDocument = selector.ownerDocument
    || container?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  const retained = new Set();
  desired.forEach((item, desiredIndex) => {
    let option = existing.get(item.value) || null;
    if (!option && ownerDocument?.createElement) option = ownerDocument.createElement("option");
    if (!option) return;
    retained.add(item.value);
    option.value = item.value;
    option.textContent = hmbPromptShotOptionLabel(item);
    option.selected = Boolean(item.selected);
    option.setAttribute?.("value", item.value);
    if (item.only) option.removeAttribute?.("data-shot-number");
    else option.setAttribute?.("data-shot-number", String(item.number));
    const ordered = hmbPromptShotOptionNodes(selector);
    const currentAtIndex = ordered[desiredIndex] || null;
    if (currentAtIndex !== option) {
      if (typeof selector.insertBefore === "function") {
        selector.insertBefore(option, currentAtIndex);
      } else if (typeof selector.appendChild === "function") {
        selector.appendChild(option);
      }
    }
  });
  existing.forEach((option, value) => {
    if (!retained.has(value)) option.remove?.();
  });

  const selected = desired.find((item) => item.selected) || desired[0];
  selector.value = selected?.value || HMB_PROMPT_ONLY_SHOT_VALUE;
  const hasRemote = desired.length > 1;
  selector.disabled = !hasRemote || Boolean(state?.disabled);
  if (selector.disabled) selector.setAttribute?.("disabled", "");
  else selector.removeAttribute?.("disabled");

  const shell = selector.closest?.(".shot-selector-shell")
    || container?.querySelector?.(".shot-selector-shell");
  let remoteStatus = shell?.querySelector?.("i") || null;
  if (hasRemote) {
    if (!remoteStatus && ownerDocument?.createElement) {
      remoteStatus = ownerDocument.createElement("i");
      shell?.appendChild?.(remoteStatus);
    }
    if (remoteStatus) remoteStatus.textContent = "REMOTE";
  } else {
    remoteStatus?.remove?.();
  }
  return true;
}

export function hmbPromptNonShotStateFingerprint(stateValue) {
  const normalized = normalizeState(stateValue || {});
  const {
    source_sync_revision: _sourceSyncRevision,
    shot: _shot,
    image_asset: imageAssetValue,
    picker: pickerValue,
    ...rest
  } = normalized;
  const imageAsset = { ...(imageAssetValue || {}) };
  delete imageAsset.shot_catalog;
  delete imageAsset.shot_catalog_routing;
  delete imageAsset.shot_routing;
  const picker = { ...(pickerValue || {}) };
  delete picker.shot_catalog;
  delete picker.shot_routing;
  return JSON.stringify({ ...rest, image_asset: imageAsset, picker });
}

function renderShotSelector(state) {
  const options = hmbPromptShotOptions(state);
  const hasRemote = options.length > 1;
  const remoteStatus = hasRemote ? "<i>REMOTE</i>" : "";
  const markup = options.map((item) => {
    const label = item.only
      ? "Only"
      : `${String(item.number).padStart(2, "0")} · ${item.name}`;
    return `<option value="${escapeHtml(item.value)}"${item.only ? "" : ` data-shot-number="${item.number}"`}${item.selected ? " selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  return `<label class="shot-selector-shell"><span>SHOT</span><select class="shot-selector" data-shot-selector aria-label="Active Shot"${hasRemote && !state.disabled ? "" : " disabled"}>${markup}</select>${remoteStatus}</label>`;
}

function render(state) {
  const paletteShotNumber = hmbPromptPaletteShotNumber(state);
  const images = state.images || [];
  const videos = state.videos || [];
  const groupBFields = TEXT_FIELDS.filter((x) => x[3] === "image").map(([key, label, ph]) => textField(key, label, state.text[key], ph, state)).join("");
  const groupDFields = TEXT_FIELDS.filter((x) => x[3] === "video").map(([key, label, ph]) => textField(key, label, state.text[key], ph, state)).join("");
  const hImageSources = groupHeightStyle(state, "imageSources");
  const hImageText = groupHeightStyle(state, "imageText");
  const hVideoSources = groupHeightStyle(state, "videoSources");
  const hVideoText = groupHeightStyle(state, "videoText");
  return `<style>
    .hmb-dashboard-clip{width:100%;height:100%;min-width:0;min-height:0;max-width:none;max-height:none;overflow:hidden;background:#050812;box-sizing:border-box;display:flex;flex-direction:column;flex:1 1 auto}
    .hmb-dashboard{--bg:#0b0f19;--panel:#0f172a;--muted:#94a3b8;--line:rgba(148,163,184,.18);--pink:#ec4899;--orange:#f97316;--cyan:#06b6d4;--green:#22c55e;--purple:#a855f7;--safe-x:16px;width:100%;height:100%;min-width:0;min-height:0;max-width:none;max-height:none;padding-left:var(--safe-x);padding-right:var(--safe-x);overflow:hidden;display:flex;flex-direction:column;flex:1 1 auto;background:radial-gradient(circle at 15% 0%,rgba(14,165,233,.16),transparent 34%),linear-gradient(180deg,#0b1120,#050812);color:#e2e8f0;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;border:1px solid rgba(148,163,184,.2);border-radius:11px;box-shadow:0 0 34px rgba(14,165,233,.12);box-sizing:border-box;resize:none;container-type:inline-size}
    .hmb-dashboard *{box-sizing:border-box;min-width:0}.topbar{height:58px;flex:0 0 58px;padding:8px 13px;border-bottom:1px solid rgba(148,163,184,.14);background:linear-gradient(90deg,rgba(30,41,59,.92),rgba(15,23,42,.78))}.title{flex:1 1 auto;display:flex;align-items:center;gap:12px;overflow:hidden;color:#f8fafc;font-size:15px;font-weight:850;letter-spacing:.01em;white-space:nowrap;text-overflow:ellipsis}.title>span:last-child{overflow:hidden;text-overflow:ellipsis}.title-mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(244,114,182,.5);border-radius:8px;background:linear-gradient(145deg,rgba(190,24,93,.28),rgba(88,28,135,.22));color:#f9a8d4;font-size:10px;font-weight:950;letter-spacing:.04em;box-shadow:inset 0 0 0 1px rgba(255,255,255,.035),0 0 10px rgba(168,85,247,.13)}.topbar{display:flex;align-items:center;gap:12px}.prompt-publish-status{flex:0 1 230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--hmb-status-error);font-size:9px;font-weight:800;text-align:right}.prompt-publish-status:empty{display:none}.language-select{width:auto;min-width:92px;height:28px;border-radius:7px;border:1px solid rgba(148,163,184,.28);background:#090d16;color:#e2e8f0;padding:3px 7px;font-size:11px;outline:none}.language-select:focus{border-color:rgba(34,211,238,.75)}.layout{display:grid;grid-template-columns:minmax(0,1fr);gap:0;flex:1 1 auto;min-height:0;height:100%;overflow:hidden;padding:8px}.center{min-height:0;border:1px solid var(--line);border-radius:10px;background:linear-gradient(180deg,rgba(15,23,42,.74),rgba(2,6,23,.72));padding:8px;overflow:hidden;scrollbar-gutter:auto;display:flex;flex-direction:column;gap:7px;align-content:stretch}.group-card{margin:0;border:1px solid var(--line);border-radius:10px;background:rgba(2,6,23,.54);overflow:hidden;display:flex;flex-direction:column;min-height:0;max-height:none;flex:0 0 auto}.group-card h3{margin:0;padding:8px 12px;font-size:12px;letter-spacing:.04em;border-bottom:1px solid rgba(148,163,184,.14);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:0 0 auto}.group-card h3 b{font-size:10px;color:#94a3b8;font-weight:600}.group-body{flex:1 1 auto;min-height:0;overflow:hidden}.source-scrollbox{overflow:auto;scrollbar-gutter:stable;overscroll-behavior:contain}.source-scrollbox .source-header{position:sticky;top:0;z-index:5;background:linear-gradient(180deg,rgba(8,13,26,.98),rgba(8,13,26,.94));backdrop-filter:blur(2px)}.source-scrollbox .source-row:last-child{border-bottom:1px solid rgba(148,163,184,.1)}.group-resize-bar{flex:0 0 10px;min-height:10px;border-top:1px solid rgba(148,163,184,.16);background:linear-gradient(90deg,transparent,rgba(148,163,184,.18),transparent);cursor:ns-resize;touch-action:none;user-select:none;position:relative}.group-resize-bar::before{content:"";position:absolute;left:50%;top:3px;width:38px;height:3px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.52)}.group-resize-bar:hover::before{background:#67e8f9}.keep-out-resize-shell{display:flex;flex-direction:column;width:100%;min-height:0}.keep-out-field .source-note-input{height:34px;min-height:34px;max-height:34px;resize:none;border-radius:7px 7px 0 0}.keep-out-resize-bar{height:9px;min-height:9px;border:1px solid rgba(148,163,184,.24);border-top:0;border-radius:0 0 7px 7px;background:linear-gradient(90deg,transparent,rgba(148,163,184,.18),transparent);cursor:ns-resize;touch-action:none;user-select:none;position:relative}.keep-out-resize-bar::before{content:"";position:absolute;left:50%;top:3px;width:28px;height:2px;transform:translateX(-50%);border-radius:99px;background:rgba(148,163,184,.52)}.keep-out-resize-bar:hover::before{background:#67e8f9}.image-card{border-color:rgba(236,72,153,.58)}.image-card h3{color:#fb7185}.imgtext{border-color:rgba(168,85,247,.55)}.imgtext h3{color:#c084fc}.video-card{border-color:rgba(249,115,22,.7)}.video-card h3{color:#fb923c}.vtext{border-color:rgba(59,130,246,.55)}.vtext h3{color:#60a5fa}.source-header,.source-row{display:grid;gap:8px;align-items:start}.image-header,.source-row.image{grid-template-columns:2.75rem minmax(0,.78fr) minmax(0,.95fr) minmax(0,.82fr) minmax(0,.82fr) minmax(0,.92fr) 3.6rem}.video-header,.source-row.video{grid-template-columns:2.75rem minmax(0,.84fr) minmax(0,.95fr) minmax(0,.95fr) minmax(0,1.36fr) 3rem}.source-header{min-height:22px;padding:5px 10px;color:#b6c5d2;font-size:10px;font-weight:800;border-bottom:1px solid rgba(148,163,184,.11)}.source-header span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-row{padding:6px 10px;border-bottom:1px solid rgba(148,163,184,.1)}.source-row:last-child{border-bottom:none}.source-num{font-weight:800;color:#f8fafc;font-size:11px;line-height:1.3;overflow:hidden;text-overflow:ellipsis}.source-num b{font-size:9px;color:#94a3b8}.source-label,.source-role,.text-field{min-width:0}.source-label input,.source-label textarea,.source-select,.source-target-input,.text-field textarea,.text-field input{width:100%;min-width:0;border-radius:7px;border:1px solid rgba(148,163,184,.24);background:#090d16;color:#e2e8f0;padding:8px;font-size:11px;outline:none}.source-label input,.source-label textarea,.text-field textarea,.text-field input,.custom-inline-input,.custom-fields-panel input{caret-color:#67e8f9}.source-label input::selection,.source-label textarea::selection,.text-field textarea::selection,.text-field input::selection,.custom-inline-input::selection,.custom-fields-panel input::selection{background:rgba(34,211,238,.34);color:#f8fafc}.source-label input:focus,.source-label textarea:focus,.source-select:focus,.source-target-input:focus,.text-field textarea:focus,.text-field input:focus{border-color:#22d3ee;box-shadow:0 0 0 1px rgba(34,211,238,.38),inset 0 0 0 1px rgba(34,211,238,.08);background:#07111b}.source-label small,.source-role small{display:block;margin-top:5px;color:#94a3b8;font-size:9px;line-height:1.25;overflow:hidden;text-overflow:ellipsis}.source-label textarea{resize:none;min-height:34px;line-height:1.35}.source-note-input{height:34px;min-height:34px;max-height:34px;resize:none}.source-status{display:flex;gap:6px;align-items:center;justify-content:flex-end}.source-actions{display:flex;gap:4px;align-items:center;justify-content:flex-end}.source-actions.image-actions{display:grid;grid-template-columns:24px 24px;grid-template-rows:28px 28px;gap:4px;align-items:center;justify-content:flex-end}.image-order-controls{display:grid;width:24px;height:28px;grid-template-rows:1fr 1fr;gap:2px}.source-actions.image-actions .image-order-controls button{width:24px;height:13px;min-height:0;padding:0;border-radius:5px;font-size:8px;line-height:1}.binding-scope-stack,.color-pick-stack{display:flex;flex-direction:column;gap:4px}.binding-scope-entry,.color-binding-entry{display:flex;flex-direction:column;gap:4px}.color-binding-entry{display:block}.binding-scope-cell select,.color-pick-cell select{height:30px;padding:5px 6px}.video-color-pick-wrap{display:grid;grid-template-columns:2rem minmax(0,1fr);gap:4px;align-items:start}.video-color-pick-wrap .image-video-index{height:30px;padding:0 2px;text-align:center;text-align-last:center;font-weight:800}.video-color-pick-wrap .image-video-index:disabled{opacity:.55;cursor:not-allowed}.binding-video-index{padding:0 2px!important;text-align:center;text-align-last:center;font-weight:800}.custom-inline-input,.custom-fields-panel input{width:100%;border-radius:7px;border:1px solid rgba(34,211,238,.28);background:#07111b;color:#dbeafe;padding:7px;font-size:10px;outline:none}.custom-inline-input:focus,.custom-fields-panel input:focus{border-color:#22d3ee}.custom-fields-panel{grid-column:2 / 7;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:6px 8px;border:1px solid rgba(34,211,238,.22);border-radius:8px;background:rgba(8,47,73,.12)}.custom-fields-panel label{display:flex;flex-direction:column;gap:4px}.custom-fields-panel span{font-size:9px;font-weight:800;color:#67e8f9}.video-custom-panel{grid-column:2 / 6}.source-row.image-add-row,.source-row.video-add-row{border-bottom:1px solid rgba(148,163,184,.1);padding-top:6px;padding-bottom:6px}.source-actions button{flex:0 0 24px;width:24px;height:28px;border-radius:7px;border:1px solid rgba(148,163,184,.22);background:#0b1220;color:#94a3b8;cursor:pointer;font-weight:800;line-height:1}.source-actions button:hover{border-color:#67e8f9;color:#67e8f9}.source-actions button.clear-source:hover{border-color:#fb7185;color:#fb7185}.source-actions button:disabled{opacity:.35;cursor:not-allowed}.clear-source{}.add-note{margin:10px;border:1px dashed rgba(148,163,184,.25);border-radius:8px;padding:9px;text-align:center;color:#94a3b8;font-size:11px}.notes{margin:0 10px 10px;color:#cbd5e1;font-size:10px;line-height:1.45}.text-grid{display:grid;grid-template-columns:1fr;align-items:stretch;align-content:stretch;gap:7px;padding:7px;height:100%;min-height:0}.imgtext .text-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.vtext .text-grid{grid-template-columns:1fr}.imgtext .group-body,.vtext .group-body{overflow:hidden;min-height:0}.text-field{display:flex;flex-direction:column;min-width:0;min-height:0}.text-field span{display:block;font-size:10px;color:#cbd5e1;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.text-field textarea{resize:none;display:block;flex:1 1 auto;height:100%;min-height:0;max-height:none}.warning{margin:10px 0 0;padding:8px;border:1px solid rgba(249,115,22,.35);border-radius:8px;color:#fed7aa;background:rgba(124,45,18,.16);font-size:10px;line-height:1.4}
    .video-color-pick-wrap{display:block}.color-binding-entry{display:grid;grid-template-columns:2rem minmax(0,1fr);gap:4px;align-items:start}
    .topbar-controls .language-button{min-width:58px;height:28px;padding:0 11px;border:1px solid rgba(148,163,184,.24);border-radius:8px;background:#090d16;color:#e2e8f0;font-size:11px;font-weight:800;cursor:pointer}.topbar-controls .language-button:hover,.topbar-controls .language-button:focus-visible{border-color:var(--hmb-shot-accent);color:var(--hmb-shot-soft);outline:none;box-shadow:0 0 0 1px var(--hmb-shot-accent),0 0 12px var(--hmb-shot-glow)}.shot-selector-shell{flex:0 1 290px;width:290px;max-width:290px;height:30px;display:flex;align-items:center;gap:6px;padding:3px 7px;border:1px solid var(--hmb-shot-line);border-radius:8px;background:linear-gradient(180deg,rgba(var(--hmb-shot-rgb),.24),rgba(15,23,42,.88));box-shadow:0 0 12px var(--hmb-shot-glow)}.shot-selector-shell>span,.shot-selector-shell>i{flex:0 0 auto;color:var(--hmb-shot-soft);font-size:8px;font-style:normal;font-weight:900;letter-spacing:.08em}.shot-selector-shell>i{color:var(--hmb-shot-accent)}.shot-selector{flex:1 1 auto;width:100%;height:22px;padding:0 7px;border:0;border-radius:5px;background:#07101f;color:#dbeafe;font-size:10px;font-weight:800;outline:none}.shot-selector:focus-visible{box-shadow:0 0 0 1px var(--hmb-shot-accent),0 0 10px var(--hmb-shot-glow)}.shot-selector:disabled{opacity:.72}
    .source-row{transition:opacity 120ms ease,box-shadow 120ms ease,background-color 120ms ease}
    .frame-binding-row{grid-column:1/-1;display:grid;grid-template-columns:3.55rem minmax(0,.78fr) minmax(0,.95fr) minmax(0,.82fr) minmax(0,.82fr) minmax(0,.92fr) 3.6rem;gap:8px;align-items:center;min-height:36px;margin-top:-2px}.frame-range-toggle-wrap{grid-column:1;position:relative;display:flex;align-items:center;min-width:0;color:#cbd5e1;font-size:8px;font-weight:800;line-height:1;cursor:pointer}.frame-range-toggle{position:absolute;inset:0;inline-size:100%;block-size:100%;margin:0;opacity:0;pointer-events:auto;cursor:pointer;z-index:2}.frame-range-toggle-ui{width:100%;min-width:52px;height:24px;display:inline-flex;align-items:center;justify-content:space-between;gap:3px;padding:0 5px;border:1px solid rgba(148,163,184,.28);border-radius:7px;background:#090d16;color:#94a3b8;white-space:nowrap;overflow:hidden}.frame-range-toggle:hover+.frame-range-toggle-ui,.frame-range-toggle:focus-visible+.frame-range-toggle-ui{border-color:rgba(34,211,238,.62);color:#cbd5e1;box-shadow:0 0 0 1px rgba(34,211,238,.2)}.frame-range-toggle-ui b,.frame-range-toggle-ui em{font-size:7px;font-style:normal;font-weight:900;letter-spacing:.02em}.frame-range-toggle-ui em{min-width:17px;text-align:center;color:#64748b}.frame-range-toggle:checked+.frame-range-toggle-ui{border-color:rgba(34,211,238,.52);background:rgba(8,145,178,.18);color:#e0f2fe}.frame-range-toggle:checked+.frame-range-toggle-ui em{color:#67e8f9}.frame-range-toggle:disabled+.frame-range-toggle-ui{opacity:.42;cursor:not-allowed}.frame-track-shell{grid-column:2/5;display:grid;grid-template-columns:3.25rem minmax(0,1fr) 3.25rem;align-items:center;gap:5px;min-width:0}.frame-track-stage{position:relative;min-width:0}.frame-domain-number{width:100%;height:26px;border:1px solid rgba(148,163,184,.28);border-radius:7px;background:#090d16;color:#e2e8f0;padding:2px 4px;font-size:9px;font-weight:800;font-variant-numeric:tabular-nums;text-align:center;outline:none}.frame-domain-number:focus{border-color:#22d3ee;box-shadow:0 0 0 1px rgba(34,211,238,.3)}.frame-domain-number[readonly]{border-color:rgba(34,211,238,.25);background:rgba(8,47,73,.18);color:#bae6fd;cursor:default}.frame-domain-number.is-hidden{visibility:hidden;pointer-events:none}.frame-track{position:relative;height:26px;border:1px solid rgba(148,163,184,.26);border-radius:7px;background:#070d17;overflow:hidden;touch-action:none;user-select:none}.frame-track.editable{cursor:crosshair;border-color:rgba(34,211,238,.42)}.frame-track:focus{outline:1px solid #22d3ee;outline-offset:1px}.frame-track-grid{position:absolute;inset:0;background:repeating-linear-gradient(90deg,transparent 0,transparent calc(10% - 1px),rgba(148,163,184,.09) calc(10% - 1px),rgba(148,163,184,.09) 10%)}.frame-track>em{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#718096;font-size:8px;font-style:normal;font-weight:800;letter-spacing:.05em;pointer-events:none}.frame-binding-row.enabled .frame-track>em{justify-content:flex-end;padding-right:7px;color:#fbbf24}.frame-binding-row.invalid .frame-track{border-color:rgba(248,113,113,.65)}.frame-binding-row.invalid .frame-track>em{color:#fca5a5}.frame-range-bar{position:absolute;z-index:2;top:3px;height:18px;min-width:2px;border:1px solid #22d3ee;border-radius:5px;background:linear-gradient(180deg,rgba(34,211,238,.78),rgba(8,145,178,.72));cursor:grab;overflow:visible}.frame-range-bar.selected{border-color:#f8fafc;box-shadow:0 0 0 1px rgba(34,211,238,.85),0 0 8px rgba(34,211,238,.5)}.frame-range-bar>b{display:block;padding:1px 8px;color:#fff;font-size:8px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;pointer-events:none}.frame-range-handle{position:absolute;z-index:3;top:-1px;bottom:-1px;width:7px;background:rgba(255,255,255,.45);cursor:ew-resize}.frame-range-handle.left{left:-1px;border-radius:5px 0 0 5px}.frame-range-handle.right{right:-1px;border-radius:0 5px 5px 0}.frame-binding-row.disabled .frame-track{opacity:.72}.frame-binding-row.disabled .frame-range-bar{filter:saturate(.35)}.frame-custom-scope{grid-column:5;display:flex;flex-direction:column;gap:4px;min-width:0}.frame-custom-scope:empty{min-height:1px}.frame-binding-context{grid-column:6;display:flex;align-items:center;gap:5px;min-width:0;color:#94a3b8;font-size:8px;white-space:nowrap;overflow:hidden}.frame-binding-context b,.frame-binding-context span{overflow:hidden;text-overflow:ellipsis}.frame-binding-context.error{color:#fca5a5}.frame-range-editor{position:absolute;z-index:30;left:50%;top:30px;transform:translateX(-50%);display:flex;align-items:center;gap:5px;padding:5px;border:1px solid rgba(34,211,238,.52);border-radius:7px;background:#07111b;box-shadow:0 8px 18px rgba(0,0,0,.55)}.frame-range-editor label{display:flex;align-items:center;gap:3px;color:#cbd5e1;font-size:8px;font-weight:800}.frame-range-number{width:58px;height:24px;border:1px solid rgba(148,163,184,.28);border-radius:5px;background:#090d16;color:#fff;padding:2px 4px;font-size:9px}.frame-range-delete{width:24px;height:24px;border:1px solid rgba(248,113,113,.45);border-radius:5px;background:#3f1720;color:#fecaca;cursor:pointer}
    .image-drag-handle{padding:5px 4px;border:1px solid transparent;border-radius:7px;cursor:grab;user-select:none;-webkit-user-select:none;touch-action:none}
    .image-drag-handle:hover{border-color:rgba(103,232,249,.5);background:rgba(34,211,238,.08)}
    .image-drag-handle:active{cursor:grabbing}
    .source-row.asset-order-managed .image-drag-handle{cursor:default;color:#f9a8d4;border-color:rgba(236,72,153,.2);background:rgba(131,24,67,.08)}
    .source-row.asset-authority-managed .image-name-cell input[readonly],.source-row.asset-authority-managed .image-main-type-cell select:disabled,.source-row.asset-authority-managed .binding-scope-cell select:disabled{border-color:rgba(236,72,153,.28);background:rgba(46,16,35,.28);color:#fbcfe8;opacity:1;cursor:default}
    .source-row.image-row-dragging{opacity:.42}
    .source-row.image-drop-before{box-shadow:inset 0 3px 0 #67e8f9}
    .source-row.image-drop-after{box-shadow:inset 0 -3px 0 #67e8f9}
    @container (max-width: 1250px){.layout{grid-template-columns:minmax(0,1fr);gap:0;padding:7px}.center{padding:7px;gap:6px}.image-header,.source-row.image{grid-template-columns:2.5rem minmax(0,.7fr) minmax(0,.9fr) minmax(0,.75fr) minmax(0,.75fr) minmax(0,.84fr) 3.6rem}.video-header,.source-row.video{grid-template-columns:2.5rem minmax(0,.76fr) minmax(0,.9fr) minmax(0,.9fr) minmax(0,1.25fr) 3rem}.source-label textarea{min-height:34px}.source-note-input{height:34px;min-height:34px;max-height:34px}}
    @container (max-width: 930px){.hmb-dashboard{--safe-x:12px}.topbar{height:58px;flex-basis:58px;padding:8px 12px}.title{font-size:17px}.layout{grid-template-columns:minmax(0,1fr);gap:0;padding:8px}.source-header{display:none}.source-row.image,.source-row.video{grid-template-columns:2.4rem minmax(0,1fr) minmax(0,1fr);gap:7px}.source-row.image .source-textarea,.source-row.video .source-textarea{grid-column:span 3}.source-status{grid-column:span 3}.custom-fields-panel,.imgtext .text-grid,.vtext .text-grid{grid-template-columns:1fr}.group-card h3{white-space:normal}.notes{display:none}}
    @container (max-width: 620px){.hmb-dashboard{--safe-x:6px}.source-row.image,.source-row.video{grid-template-columns:1fr}.source-num,.source-row.image .source-textarea,.source-row.video .source-textarea,.source-status{display:flex;grid-column:1}.custom-fields-panel{display:grid;grid-column:1}.source-actions button{flex-basis:30px}.source-label small,.source-role small,.add-note,.warning{display:block}.group-card h3{font-size:11px}.source-row{padding:7px}.text-grid{padding:7px}}
    @container (max-width: 1250px){.frame-binding-row{grid-template-columns:3.4rem minmax(0,.7fr) minmax(0,.9fr) minmax(0,.75fr) minmax(0,.75fr) minmax(0,.84fr) 3.6rem}.frame-track-shell{grid-template-columns:3rem minmax(0,1fr) 3rem}}
    @container (max-width: 930px){.frame-binding-row{grid-template-columns:3.4rem repeat(5,minmax(0,1fr)) 3.6rem}.frame-track-shell{grid-column:2/5}}
    @container (max-width: 620px){.frame-binding-row{display:grid!important;grid-template-columns:3.35rem minmax(0,1fr);gap:6px}.frame-range-toggle-wrap{grid-column:1;display:flex!important;justify-content:center}.frame-track-shell{grid-column:2;grid-template-columns:2.65rem minmax(3.5rem,1fr) 2.65rem}.frame-custom-scope,.frame-binding-context,.frame-binding-row>div:last-child{display:none}.frame-range-editor{left:auto;right:0;transform:none}}
    .custom-inline-input.is-hidden,.custom-fields-panel.is-hidden,.custom-fields-panel label.is-hidden{display:none!important}
    /* Compact Range row: reuse the open area below # / NAME / MAIN TYPE / SUB TYPE. */
    .frame-binding-row{grid-column:1/-1;display:grid;grid-template-columns:3.55rem minmax(0,1fr);gap:8px;align-items:center;min-height:28px;margin-top:0}
    .frame-binding-row .frame-range-toggle-wrap{grid-column:1}
    .frame-binding-row .frame-track-shell{grid-column:2}
    @container (min-width:931px){
      .source-row.image>.image-index-cell{grid-column:1;grid-row:1}
      .source-row.image>.image-name-cell{grid-column:2;grid-row:1}
      .source-row.image>.image-main-type-cell{grid-column:3;grid-row:1}
      .source-row.image>.binding-scope-cell{grid-column:4;grid-row:1}
      .source-row.image>.image-target-cell{grid-column:5;grid-row:1}
      .source-row.image>.color-pick-cell{grid-column:6;grid-row:1}
      .source-row.image>.image-actions-cell{grid-column:7;grid-row:1}
      .source-row.image>.frame-binding-row{grid-column:1/5;grid-row:1;align-self:start;margin-top:38px}
      .source-row.image.image-expanded-left-fields>.frame-binding-row{margin-top:72px}
    }
    @container (max-width:1250px) and (min-width:931px){
      .frame-binding-row{grid-template-columns:3.4rem minmax(0,1fr)}
      .frame-track-shell{grid-template-columns:3rem minmax(0,1fr) 3rem}
    }
    @container (max-width:930px){
      .frame-binding-row{grid-column:1/-1;grid-row:auto;grid-template-columns:3.4rem minmax(0,1fr);margin-top:0}
      .frame-track-shell{grid-column:2}
    }
    @container (max-width:620px){
      .frame-binding-row{grid-template-columns:3.35rem minmax(0,1fr)}
      .frame-track-shell{grid-template-columns:2.65rem minmax(3.5rem,1fr) 2.65rem}
    }

    /* VideoPicker header geometry/typography, with Prompt-specific controls. */
    .topbar{position:relative;z-index:30;height:68px;flex:0 0 68px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 16px;border-radius:10px 10px 0 0;user-select:none}
    .title{flex:1 1 auto;gap:10px;min-width:0;font-size:15px;font-weight:800;letter-spacing:.01em}
    .title-mark{flex:0 0 30px;width:30px;height:30px;border-width:1px;border-style:solid;border-radius:8px;background:rgba(var(--hmb-shot-rgb),.12);font-size:9px;font-weight:950;letter-spacing:.04em}
    .topbar-controls{position:relative;z-index:31;display:flex;align-items:center;justify-content:flex-end;flex:0 0 auto;gap:7px;margin-left:auto}
    .topbar-controls .language-button{min-width:58px;height:30px;padding:0 10px;border-radius:3px;font-size:12px}
    .shot-selector-shell{flex:0 0 auto;width:auto;max-width:none;height:auto;display:flex;align-items:center;gap:6px;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}
    .shot-selector-shell>span,.shot-selector-shell>i{color:#8296a7;font-size:10px;font-weight:800;letter-spacing:.12em}
    .shot-selector{min-width:150px;max-width:260px;height:30px;padding:0 10px;border:1px solid #33414d;border-radius:3px;background:#18232d;font-size:12px}
    .hmb-dashboard{--hmb-shot-accent:#F472B6;--hmb-shot-rgb:244,114,182;--hmb-shot-deep:#BE185D;--hmb-shot-soft:#FBCFE8;--hmb-shot-line:rgba(244,114,182,.48);--hmb-shot-glow:rgba(244,114,182,.2);--hmb-bg-top:#0b1020;--hmb-bg-bottom:#060912;--hmb-panel-top:#101523;--hmb-panel-bottom:#080d17;--hmb-head-top:rgba(var(--hmb-shot-rgb),.2);--hmb-head-mid:#17192b;--hmb-head-bottom:#0d1625;--hmb-line:rgba(148,163,184,.19);--hmb-line-strong:var(--hmb-shot-line);--hmb-field:#070c15;--hmb-focus:var(--hmb-shot-accent);--hmb-hover:rgba(var(--hmb-shot-rgb),.055);--hmb-primary-top:var(--hmb-shot-accent);--hmb-primary-bottom:var(--hmb-shot-deep);--hmb-glow:var(--hmb-shot-glow);--hmb-text:#e6edf7;--hmb-muted:#8fa3b8;--hmb-subtle:#667e94;--hmb-utility:var(--hmb-shot-accent);--hmb-selection:var(--hmb-shot-accent);--hmb-group-image:var(--hmb-shot-accent);--hmb-group-context:var(--hmb-shot-soft);--hmb-group-video:var(--hmb-shot-accent);--hmb-group-vfx:var(--hmb-shot-soft);--hmb-status-error:#FB7185;--hmb-status-warning:#FBBF24;--hmb-status-success:#34D399}
    .hmb-dashboard[data-shot-number="2"]{--hmb-shot-accent:#3B82F6;--hmb-shot-rgb:59,130,246;--hmb-shot-deep:#1D4ED8;--hmb-shot-soft:#DBEAFE;--hmb-shot-line:rgba(59,130,246,.5);--hmb-shot-glow:rgba(59,130,246,.2)}
    .hmb-dashboard[data-shot-number="3"]{--hmb-shot-accent:#10B981;--hmb-shot-rgb:16,185,129;--hmb-shot-deep:#047857;--hmb-shot-soft:#D1FAE5;--hmb-shot-line:rgba(16,185,129,.5);--hmb-shot-glow:rgba(16,185,129,.2)}
    .hmb-dashboard[data-shot-number="4"]{--hmb-shot-accent:#8B5CF6;--hmb-shot-rgb:139,92,246;--hmb-shot-deep:#6D28D9;--hmb-shot-soft:#EDE9FE;--hmb-shot-line:rgba(139,92,246,.5);--hmb-shot-glow:rgba(139,92,246,.2)}
    .hmb-dashboard[data-shot-number="5"]{--hmb-shot-accent:#EAB308;--hmb-shot-rgb:234,179,8;--hmb-shot-deep:#A16207;--hmb-shot-soft:#FEF3C7;--hmb-shot-line:rgba(234,179,8,.5);--hmb-shot-glow:rgba(234,179,8,.2)}
    .hmb-dashboard{background:radial-gradient(circle at 8% -10%,var(--hmb-glow),transparent 34%),radial-gradient(circle at 88% 0%,var(--hmb-glow),transparent 30%),linear-gradient(180deg,var(--hmb-bg-top),var(--hmb-bg-bottom));color:var(--hmb-text);border-color:var(--hmb-shot-line);box-shadow:0 12px 36px rgba(0,0,0,.28),0 0 30px var(--hmb-glow)}
    .hmb-dashboard .topbar{background:radial-gradient(circle at 8% -45%,var(--hmb-glow),transparent 52%),linear-gradient(90deg,var(--hmb-head-top),var(--hmb-head-mid) 42%,var(--hmb-head-bottom));border-bottom-color:var(--hmb-line);box-shadow:inset 0 -1px 0 rgba(255,255,255,.018)}
    .hmb-dashboard .center{background:radial-gradient(circle at 50% 0%,var(--hmb-glow),transparent 35%),linear-gradient(180deg,var(--hmb-panel-top),var(--hmb-panel-bottom));border-color:var(--hmb-line);box-shadow:0 9px 24px rgba(0,0,0,.14)}
    .hmb-dashboard .group-card,.hmb-dashboard .custom-fields-panel{background:linear-gradient(145deg,rgba(255,255,255,.026),rgba(255,255,255,.006)),linear-gradient(180deg,var(--hmb-panel-top),var(--hmb-panel-bottom));border-color:var(--hmb-line)}
    .hmb-dashboard .group-card h3,.hmb-dashboard .source-scrollbox .source-header{background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,.005)),linear-gradient(180deg,var(--hmb-head-mid),var(--hmb-head-bottom));border-bottom-color:var(--hmb-line)}
    .hmb-dashboard .title,.hmb-dashboard .group-card h3,.hmb-dashboard .source-num,.hmb-dashboard .text-field span{color:var(--hmb-text)}
    .hmb-dashboard .group-card h3 b,.hmb-dashboard .source-header,.hmb-dashboard .source-num b,.hmb-dashboard .source-label small,.hmb-dashboard .source-role small,.hmb-dashboard .notes,.hmb-dashboard .add-note{color:var(--hmb-muted)}
    .hmb-dashboard .custom-fields-panel span{color:var(--hmb-utility)}
    .hmb-dashboard .language-select,.hmb-dashboard .source-label input,.hmb-dashboard .source-label textarea,.hmb-dashboard .source-select,.hmb-dashboard .source-target-input,.hmb-dashboard .text-field textarea,.hmb-dashboard .text-field input,.hmb-dashboard .custom-inline-input,.hmb-dashboard .custom-fields-panel input,.hmb-dashboard .source-actions button{background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,.004)),var(--hmb-field);border-color:rgba(148,163,184,.2);color:var(--hmb-text)}
    .hmb-dashboard .source-label input::placeholder,.hmb-dashboard .source-label textarea::placeholder,.hmb-dashboard .text-field textarea::placeholder,.hmb-dashboard .text-field input::placeholder,.hmb-dashboard .custom-inline-input::placeholder,.hmb-dashboard .custom-fields-panel input::placeholder{color:rgba(255,255,255,.50)}
    .hmb-dashboard .source-label input:focus,.hmb-dashboard .source-label textarea:focus,.hmb-dashboard .source-select:focus,.hmb-dashboard .source-target-input:focus,.hmb-dashboard .text-field textarea:focus,.hmb-dashboard .text-field input:focus,.hmb-dashboard .custom-inline-input:focus,.hmb-dashboard .custom-fields-panel input:focus,.hmb-dashboard .language-select:focus{border-color:var(--hmb-focus);box-shadow:0 0 0 1px var(--hmb-focus),0 0 18px var(--hmb-glow);background:var(--hmb-field)}
    .hmb-dashboard .language-button{background:linear-gradient(180deg,rgba(255,255,255,.025),rgba(255,255,255,.004)),var(--hmb-field);border-color:rgba(148,163,184,.2);color:var(--hmb-text)}.hmb-dashboard .language-button:hover,.hmb-dashboard .language-button:focus-visible{border-color:var(--hmb-focus);color:var(--hmb-utility);box-shadow:0 0 0 1px var(--hmb-focus),0 0 18px var(--hmb-glow)}
    .hmb-dashboard .shot-selector{border-color:rgba(var(--hmb-shot-rgb),.58);background:linear-gradient(180deg,rgba(var(--hmb-shot-rgb),.18),rgba(var(--hmb-shot-rgb),.14)),var(--hmb-field);color:var(--hmb-shot-soft);box-shadow:0 0 12px var(--hmb-glow)}
    .hmb-dashboard .source-row,.hmb-dashboard .source-scrollbox .source-row:last-child{border-color:rgba(255,255,255,.08)}
    .hmb-dashboard .source-row:hover{background:var(--hmb-hover)}
    .hmb-dashboard .group-resize-bar{border-top-color:var(--hmb-line);background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent)}
    .hmb-dashboard .group-resize-bar::before{background:rgba(255,255,255,.44)}
    .hmb-dashboard .group-resize-bar:hover::before{background:var(--hmb-focus)}
    .hmb-dashboard .keep-out-resize-bar{border-color:rgba(255,255,255,.16);background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent)}
    .hmb-dashboard .keep-out-resize-bar::before{background:rgba(255,255,255,.44)}
    .hmb-dashboard .keep-out-resize-bar:hover::before{background:var(--hmb-focus)}
    .hmb-dashboard .image-card{border-color:var(--hmb-line-strong)}.hmb-dashboard .image-card h3{color:var(--hmb-group-image)}
    .hmb-dashboard .imgtext{border-color:var(--hmb-line-strong)}.hmb-dashboard .imgtext h3{color:var(--hmb-group-context)}
    .hmb-dashboard .video-card{border-color:var(--hmb-line-strong)}.hmb-dashboard .video-card h3{color:var(--hmb-group-video)}
    .hmb-dashboard .vtext{border-color:var(--hmb-line-strong)}.hmb-dashboard .vtext h3{color:var(--hmb-group-vfx)}
    .hmb-dashboard .source-actions button:hover{border-color:var(--hmb-focus);color:var(--hmb-text);box-shadow:0 0 12px var(--hmb-glow)}
    .hmb-dashboard .source-actions button.clear-source:hover{border-color:var(--hmb-selection);color:var(--hmb-text)}
    .hmb-dashboard .warning{color:var(--hmb-status-warning);background:rgba(120,53,15,.1);border-color:rgba(251,191,36,.22)}
    .hmb-dashboard .title-mark{border-color:var(--hmb-shot-line);background:rgba(var(--hmb-shot-rgb),.12);color:var(--hmb-shot-accent);box-shadow:inset 0 0 0 1px rgba(255,255,255,.025),0 0 13px var(--hmb-glow)}
    /* Shared HMB header typography and Shot selector sizing. */
    .hmb-dashboard .title{font-size:15px;font-weight:800;letter-spacing:.01em;line-height:normal}
    .hmb-dashboard .shot-selector{flex:0 1 210px;width:210px;min-width:120px;max-width:210px;height:44px;padding:0 10px;font-size:13px;font-weight:800;line-height:normal}
    @media (prefers-reduced-motion: reduce){.hmb-dashboard,.hmb-dashboard *,.hmb-dashboard *::before,.hmb-dashboard *::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
  </style><div class="hmb-dashboard-clip nodrag"><div class="hmb-dashboard ${state.disabled ? "disabled" : ""}" data-shot-number="${paletteShotNumber}">
    <div class="topbar"><div class="title"><span class="title-mark" aria-hidden="true">PL</span><span>HMBPromptLibrary</span></div><div class="prompt-publish-status" data-prompt-publication-status role="status" aria-live="polite" aria-atomic="true"></div><div class="topbar-controls">${renderShotSelector(state)}<button type="button" class="language-button" data-language-toggle aria-label="Language">${uiLanguage(state) === "ko" ? "한국어" : "EN"}</button></div></div>
    <div class="layout">
      <main class="center">
        <section class="group-card image-card" data-group-id="imageSources" ${hImageSources}><h3>${escapeHtml(uiText(state, "image_source_binding", "IMAGE SOURCE BINDING"))} <b>${state.status.active_images} / ${state.status.max_images}</b></h3><div class="group-body source-scrollbox" data-scroll-id="imageSources"><div class="source-header image-header"><span>#</span><span>${escapeHtml(uiText(state, "name", "NAME"))}</span><span>${escapeHtml(uiText(state, "main_type", "MAIN TYPE"))}</span><span>${escapeHtml(uiText(state, "sub_type", "SUB TYPE"))}</span><span>${escapeHtml(uiText(state, "target", "TARGET"))}</span><span>${escapeHtml(uiText(state, "video_color_pick", "VIDEO / COLOR PICK"))}</span><span></span></div>${images.map((item, idx) => renderImageRow(item, idx, images, state)).join("")}${renderImageAddRow(images, state)}</div><div class="group-resize-bar nodrag" data-resize-group="imageSources" title="${escapeHtml(uiText(state, "resize_group", "Drag down/up to resize this center group"))}"></div></section>
        <section class="group-card imgtext" data-group-id="imageText" ${hImageText}><h3>${escapeHtml(uiText(state, "image_text_context", "IMAGE TEXT CONTEXT"))} <b>${escapeHtml(uiText(state, "scene_level_notes", "scene-level notes"))}</b></h3><div class="group-body"><div class="text-grid">${groupBFields}</div></div><div class="group-resize-bar nodrag" data-resize-group="imageText" title="${escapeHtml(uiText(state, "resize_group", "Drag down/up to resize this center group"))}"></div></section>
        <section class="group-card video-card" data-group-id="videoSources" ${hVideoSources}><h3>${escapeHtml(uiText(state, "video_source_binding", "VIDEO SOURCE BINDING"))} <b>${state.status.active_videos} / ${state.status.max_videos}</b></h3><div class="group-body source-scrollbox" data-scroll-id="videoSources"><div class="source-header video-header"><span>#</span><span>${escapeHtml(uiText(state, "name", "NAME"))}</span><span>${escapeHtml(uiText(state, "main_type", "MAIN TYPE"))}</span><span>${escapeHtml(uiText(state, "sub_type", "SUB TYPE"))}</span><span>${escapeHtml(uiText(state, "keep_out", "KEEP OUT"))}</span><span></span></div>${videos.map((item, idx) => renderVideoRow(item, idx, images, state)).join("")}${renderVideoAddRow(videos, state)}</div><div class="group-resize-bar nodrag" data-resize-group="videoSources" title="${escapeHtml(uiText(state, "resize_group", "Drag down/up to resize this center group"))}"></div></section>
        <section class="group-card vtext" data-group-id="videoText" ${hVideoText}><h3>${escapeHtml(uiText(state, "video_vfx", "VIDEO VFX"))}</h3><div class="group-body"><div class="text-grid">${groupDFields}</div></div><div class="group-resize-bar nodrag" data-resize-group="videoText" title="${escapeHtml(uiText(state, "resize_group", "Drag down/up to resize this center group"))}"></div></section>
      </main>
    </div>
  </div></div>`;
}


function hmbFindSafeReactFlowNode(container) {
  let current = container ? container.parentElement : null;
  const doc = typeof document !== "undefined" ? document : null;
  for (let i = 0; current && i < 10; i += 1) {
    if (doc && (current === doc.body || current === doc.documentElement)) return null;
    const cls = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (cls.includes("react-flow__pane") || cls.includes("react-flow__viewport") || cls.includes("react-flow__renderer")) return null;
    if (cls.includes("react-flow__node") || testId === "node") return current;
    current = current.parentElement;
  }
  return null;
}

export function hmbRequestPromptHostResize(container, shell = null) {
  if (!container) return false;
  const wasPending = Boolean(container.__hmbPromptHostResizeTimer);
  if (container.__hmbPromptHostResizeTimer) {
    clearTimeout(container.__hmbPromptHostResizeTimer);
  }
  container.__hmbPromptHostResizeTimer = setTimeout(() => {
    container.__hmbPromptHostResizeTimer = null;
    try {
      // Force layout before notifying ReactFlow/host listeners. ResizeObserver
      // remains the primary geometry signal; the standard window resize event
      // safely invalidates hosts that cache node bounds outside that observer.
      // A short trailing delay keeps pointer-resize and structural edits from
      // broadcasting one global resize event per animation frame.
      const target = shell || hmbFindSafeReactFlowNode(container);
      if (target) void target.offsetHeight;
      if (typeof window !== "undefined" && typeof window.dispatchEvent === "function" && typeof Event === "function") {
        window.dispatchEvent(new Event("resize"));
      }
    } catch (_e) {}
  }, 80);
  return !wasPending;
}

function hmbPromptNodeIsSelected(root) {
  if (!root) return false;
  if (root.classList?.contains("selected")) return true;
  if (String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true") return true;
  if (String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true") return true;
  return Boolean(root.querySelector?.(
    ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
  ));
}

function hmbPromptDeleteEditingTarget(event) {
  return Boolean(event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbPromptDeleteEditingTarget(event)) return false;
  if (!hmbPromptNodeIsSelected(hmbFindSafeReactFlowNode(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function hmbApplyInitialNodeSizeOnce(container) {
  const shell = hmbFindSafeReactFlowNode(container);
  if (!shell || !shell.style) return;
  if (shell.dataset && shell.dataset.hmbPromptLibraryInitialSizeApplied === "1") return;
  try {
    const rect = shell.getBoundingClientRect ? shell.getBoundingClientRect() : null;
    const currentWidth = rect && rect.width ? rect.width : 0;
    const currentHeight = rect && rect.height ? rect.height : 0;
    // Apply the final required startup size before the widget HTML is mounted.
    // The earlier threshold-based check allowed intermediate engine sizes (for
    // example 1040px) to render first and expand on the next animation frame,
    // which caused the lower edge to visibly jump once during opening.
    const needsWidth = !currentWidth || currentWidth < HMB_DEFAULT_NODE_WIDTH - 1;
    const needsHeight = !currentHeight || currentHeight < HMB_DEFAULT_NODE_HEIGHT - 1;
    if (needsWidth) shell.style.width = `${HMB_DEFAULT_NODE_WIDTH}px`;
    if (needsHeight) shell.style.height = `${HMB_DEFAULT_NODE_HEIGHT}px`;
    shell.style.minWidth = `${HMB_MIN_NODE_WIDTH}px`;
    shell.style.minHeight = `${HMB_MIN_NODE_HEIGHT}px`;
    shell.style.maxHeight = "none";
    shell.style.overflow = "visible";
    shell.style.boxSizing = "border-box";
    if (shell.dataset) shell.dataset.hmbPromptLibraryInitialSizeApplied = "1";
    if (needsWidth || needsHeight) hmbRequestPromptHostResize(container, shell);
  } catch (_e) {}
}

function hmbIsOuterCanvasOrNode(el) {
  if (!el || el === document.body || el === document.documentElement) return true;
  const cls = String(el.className || "").toLowerCase();
  const testId = String(el.getAttribute?.("data-testid") || "").toLowerCase();
  const role = String(el.getAttribute?.("role") || "").toLowerCase();
  return Boolean(
    cls.includes("react-flow__node") ||
    cls.includes("react-flow__pane") ||
    cls.includes("react-flow__viewport") ||
    cls.includes("react-flow__renderer") ||
    cls.includes("react-flow__selection") ||
    cls.includes("canvas") ||
    cls.includes("viewport") ||
    testId === "node" ||
    testId.includes("react-flow") ||
    role === "application"
  );
}

function hmbLocalHostAncestors(container) {
  const out = [];
  let current = container ? container.parentElement : null;
  for (let i = 0; current && i < 5; i += 1) {
    if (hmbIsOuterCanvasOrNode(current)) break;
    out.push(current);
    current = current.parentElement;
  }
  return out;
}

function hmbPromptInnerRequiredHeight(container, state) {
  let groupTotal = 0;
  HMB_GROUP_KEYS.forEach((key) => {
    const minHeight = HMB_GROUP_MIN_HEIGHTS[key] || 120;
    const saved = state && state.ui && state.ui.group_heights ? Number(state.ui.group_heights[key]) : NaN;
    const fallback = Number(HMB_GROUP_DEFAULT_HEIGHTS[key]) || minHeight;
    groupTotal += Math.max(minHeight, Number.isFinite(saved) ? saved : fallback);
  });
  let chrome = 96;
  try {
    const topbar = container?.querySelector?.(".topbar");
    const layout = container?.querySelector?.(".layout");
    const center = container?.querySelector?.(".center");
    const centerStyle = center && window.getComputedStyle ? window.getComputedStyle(center) : null;
    const layoutStyle = layout && window.getComputedStyle ? window.getComputedStyle(layout) : null;
    const gap = centerStyle ? (parseFloat(centerStyle.rowGap || centerStyle.gap) || 0) : 7;
    const centerPadding = centerStyle ? (parseFloat(centerStyle.paddingTop) || 0) + (parseFloat(centerStyle.paddingBottom) || 0) : 16;
    const layoutPadding = layoutStyle ? (parseFloat(layoutStyle.paddingTop) || 0) + (parseFloat(layoutStyle.paddingBottom) || 0) : 16;
    const topbarHeight = topbar ? Number(topbar.offsetHeight || 68) : 68;
    chrome = topbarHeight + layoutPadding + centerPadding + gap * Math.max(0, HMB_GROUP_KEYS.length - 1) + 8;
  } catch (_e) {}
  return Math.max(HMB_DEFAULT_NODE_HEIGHT, Math.round(groupTotal + chrome));
}

function hmbApplyDashboardHostSizing(container, state) {
  if (!container || !container.style) return 0;
  const required = hmbPromptInnerRequiredHeight(container, state);
  const applyMinimum = (element) => {
    if (!element || !element.style) return;
    try {
      element.style.minHeight = `${required}px`;
      element.style.maxHeight = "none";
      element.style.overflow = "visible";
      element.style.boxSizing = "border-box";
    } catch (_e) {}
  };
  try {
    container.style.width = "100%";
    container.style.minWidth = "0";
    container.style.maxWidth = "none";
    applyMinimum(container);
    container.classList.add("nodrag");
    container.classList.remove("nowheel");
    hmbLocalHostAncestors(container).forEach(applyMinimum);
    const clip = container.querySelector(".hmb-dashboard-clip");
    if (clip && clip.style) {
      clip.style.width = "100%";
      clip.style.height = `${required}px`;
      clip.style.minHeight = `${required}px`;
      clip.style.maxHeight = "none";
      clip.style.overflow = "visible";
      clip.style.boxSizing = "border-box";
    }
    const dashboard = container.querySelector(".hmb-dashboard");
    if (dashboard && dashboard.style) {
      dashboard.style.width = "100%";
      dashboard.style.height = `${required}px`;
      dashboard.style.minHeight = `${required}px`;
      dashboard.style.maxHeight = "none";
      dashboard.style.resize = "none";
      dashboard.style.overflow = "hidden";
      dashboard.style.boxSizing = "border-box";
      if (!dashboard.style.paddingLeft) dashboard.style.paddingLeft = "var(--safe-x)";
      if (!dashboard.style.paddingRight) dashboard.style.paddingRight = "var(--safe-x)";
    }
  } catch (_e) {}
  return required;
}

function hmbInstallFluidLayoutSync(container, getState) {
  let observer = null;
  let frame = 0;
  let applying = false;
  let stopped = false;
  const apply = () => {
    if (stopped) return;
    // ResizeObserver can fire several times in one layout turn. One owned
    // frame is enough; replacing it would strand cancelled task records until
    // unmount and recreate the workspace-growth memory pattern.
    if (frame) return;
    frame = hmbPromptLifecycleFrame(container, () => {
      frame = 0;
      if (stopped || applying || hmbIsGroupResizeDragging(container)) return;
      applying = true;
      try {
        hmbCaptureSourceScroll(container);
        const state = typeof getState === "function" ? getState() : null;
        hmbFitGroupHeightsToCenter(container, state);
        hmbRestoreSourceScroll(container);
      } finally {
        hmbPromptLifecycleFrame(container, () => { applying = false; });
      }
    });
  };
  try {
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(apply);
      observer.observe(container);
      const shell = hmbFindSafeReactFlowNode(container);
      if (shell) observer.observe(shell);
    }
  } catch (_e) { observer = null; }
  apply();
  return () => {
    stopped = true;
    try { observer && observer.disconnect(); } catch (_e) {}
    if (frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
    frame = 0;
    applying = false;
  };
}

function hmbCurrentGroupHeight(card) {
  if (!card) return 0;
  // React Flow can scale nodes with CSS transform. getBoundingClientRect() returns
  // the scaled visual size, while flex-basis expects the unscaled CSS size.
  // Prefer offsetHeight to prevent the group from snapping to a smaller/larger
  // value the moment the resize handle is pressed.
  try {
    const value = Number(card.offsetHeight || 0);
    if (Number.isFinite(value) && value > 0) return Math.round(value);
  } catch (_e) {}
  try {
    const rect = card.getBoundingClientRect ? card.getBoundingClientRect() : null;
    if (rect && rect.height && rect.height > 0) return Math.round(rect.height);
  } catch (_e) {}
  return 0;
}

function hmbElementVisualScaleY(el) {
  if (!el) return 1;
  try {
    const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
    const cssHeight = Number(el.offsetHeight || 0);
    const visualHeight = rect && Number(rect.height || 0);
    if (Number.isFinite(cssHeight) && cssHeight > 0 && Number.isFinite(visualHeight) && visualHeight > 0) {
      const scale = visualHeight / cssHeight;
      if (Number.isFinite(scale) && scale > 0.05 && scale < 20) return scale;
    }
  } catch (_e) {}
  return 1;
}

function hmbGroupHeightMemory(container) {
  if (!container) return {};
  if (!container.__hmbPromptLibraryGroupHeightMemory || typeof container.__hmbPromptLibraryGroupHeightMemory !== "object") {
    container.__hmbPromptLibraryGroupHeightMemory = {};
  }
  return container.__hmbPromptLibraryGroupHeightMemory;
}

function hmbGroupDatasetKey(key) {
  return `hmbGroupHeight${String(key || "").replace(/[^a-zA-Z0-9]/g, "")}`;
}

function hmbStoreGroupHeight(container, key, value) {
  if (!container || !key || !(key in HMB_GROUP_MIN_HEIGHTS)) return;
  const minHeight = HMB_GROUP_MIN_HEIGHTS[key] || 120;
  const height = Math.max(minHeight, Math.min(HMB_GROUP_MAX_HEIGHT, Math.round(Number(value) || minHeight)));
  const memory = hmbGroupHeightMemory(container);
  memory[key] = height;
  try { container.dataset[hmbGroupDatasetKey(key)] = String(height); } catch (_e) {}
}

function hmbReadStoredGroupHeight(container, key) {
  if (!container || !key || !(key in HMB_GROUP_MIN_HEIGHTS)) return null;
  const minHeight = HMB_GROUP_MIN_HEIGHTS[key] || 120;
  const memory = hmbGroupHeightMemory(container);
  const value = Number(memory[key]);
  if (Number.isFinite(value) && value >= minHeight && value <= HMB_GROUP_MAX_HEIGHT) return Math.round(value);
  try {
    const data = Number(container.dataset ? container.dataset[hmbGroupDatasetKey(key)] : NaN);
    if (Number.isFinite(data) && data >= minHeight && data <= HMB_GROUP_MAX_HEIGHT) return Math.round(data);
  } catch (_e) {}
  return null;
}

function hmbMergeStoredGroupHeights(container, state) {
  if (!state) return state;
  state.ui = normalizeUi(state.ui);
  HMB_GROUP_KEYS.forEach((key) => {
    const stored = hmbReadStoredGroupHeight(container, key);
    if (Number.isFinite(stored)) state.ui.group_heights[key] = stored;
  });
  return state;
}

function hmbPreserveManualGroupHeights(container, state) {
  if (!container || !state) return;
  state.ui = normalizeUi(state.ui);
  HMB_GROUP_KEYS.forEach((key) => {
    const stored = hmbReadStoredGroupHeight(container, key);
    if (Number.isFinite(stored)) state.ui.group_heights[key] = stored;
  });
}

function hmbApplyExactGroupFlex(card, height) {
  if (!card || !card.style) return;
  const groupId = card.getAttribute ? (card.getAttribute("data-group-id") || "") : "";
  const minHeight = HMB_GROUP_MIN_HEIGHTS[groupId] || 120;
  const finalHeight = Math.max(minHeight, Math.min(HMB_GROUP_MAX_HEIGHT, Math.round(Number(height) || minHeight)));
  try {
    card.style.flex = `0 0 ${finalHeight}px`;
    card.style.flexBasis = `${finalHeight}px`;
    card.style.minHeight = `${minHeight}px`;
    card.style.height = "";
  } catch (_e) {}
}

function hmbNodeShellHeight(shell) {
  if (!shell) return 0;
  try {
    const value = Number(shell.offsetHeight || 0);
    if (Number.isFinite(value) && value > 0) return Math.round(value);
  } catch (_e) {}
  try {
    const rect = shell.getBoundingClientRect ? shell.getBoundingClientRect() : null;
    const scale = hmbElementVisualScaleY(shell) || 1;
    if (rect && rect.height > 0) return Math.round(rect.height / Math.max(0.05, scale));
  } catch (_e) {}
  return 0;
}

function hmbApplyOuterNodeHeight(container, height) {
  const shell = hmbFindSafeReactFlowNode(container);
  if (!shell || !shell.style) return null;
  const nextHeight = Math.max(HMB_MIN_NODE_HEIGHT, Math.min(6000, Math.round(Number(height) || HMB_DEFAULT_NODE_HEIGHT)));
  const previousHeight = hmbNodeShellHeight(shell);
  try {
    shell.style.height = `${nextHeight}px`;
    shell.style.minHeight = `${HMB_MIN_NODE_HEIGHT}px`;
    shell.style.maxHeight = "none";
    shell.style.overflow = "visible";
    shell.style.boxSizing = "border-box";
  } catch (_e) {}
  if (!previousHeight || Math.abs(nextHeight - previousHeight) > 1) {
    hmbRequestPromptHostResize(container, shell);
  }
  return { shell, height: nextHeight };
}

function hmbRequiredOuterNodeHeight(container, state) {
  if (!container) return HMB_DEFAULT_NODE_HEIGHT;
  const innerRequired = hmbPromptInnerRequiredHeight(container, state);
  const shell = hmbFindSafeReactFlowNode(container);
  let topOffset = 0;
  let bottomInset = 8;
  try {
    const shellRect = shell?.getBoundingClientRect?.();
    const containerRect = container.getBoundingClientRect?.();
    const scale = hmbElementVisualScaleY(shell) || 1;
    if (shellRect && containerRect) topOffset = Math.max(0, (containerRect.top - shellRect.top) / Math.max(0.05, scale));
    const style = shell && window.getComputedStyle ? window.getComputedStyle(shell) : null;
    if (style) bottomInset += (parseFloat(style.paddingBottom) || 0) + (parseFloat(style.borderBottomWidth) || 0);
  } catch (_e) {}
  return Math.max(HMB_MIN_NODE_HEIGHT, Math.ceil(topOffset + innerRequired + bottomInset));
}

function hmbDominoContainerDelta(startSize, startRequiredSize, requiredDelta) {
  const size = Math.max(0, Math.round(Number(startSize) || 0));
  const required = Math.max(0, Math.round(Number(startRequiredSize) || 0));
  const delta = Math.round(Number(requiredDelta) || 0);
  const startingGap = size - required;

  if (delta > 0) {
    return Math.max(0, delta - Math.max(0, startingGap));
  }
  if (delta < 0) {
    if (startingGap > 1) return 0;
    return -Math.max(0, -delta - Math.max(0, -startingGap));
  }
  return 0;
}

function hmbDominoOuterHeight(startNodeHeight, startRequiredHeight, nextRequiredHeight) {
  const startNode = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(startNodeHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const startRequired = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(startRequiredHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const nextRequired = Math.max(HMB_MIN_NODE_HEIGHT, Math.round(Number(nextRequiredHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const sizeDelta = hmbDominoContainerDelta(startNode, startRequired, nextRequired - startRequired);
  return Math.max(HMB_MIN_NODE_HEIGHT, Math.min(6000, startNode + sizeDelta));
}

function hmbGroupShrinkMinDelta(startHeight, minHeight, startRequiredHeight, startingSlack) {
  const ownMinimumDelta = Math.round(Number(minHeight) || 0) - Math.round(Number(startHeight) || 0);
  if (Math.max(0, Number(startingSlack) || 0) > 1) return ownMinimumDelta;
  const required = Math.max(HMB_DEFAULT_NODE_HEIGHT, Math.round(Number(startRequiredHeight) || HMB_DEFAULT_NODE_HEIGHT));
  const outerMinimumDelta = Math.min(0, HMB_DEFAULT_NODE_HEIGHT - required);
  return Math.max(ownMinimumDelta, outerMinimumDelta);
}

function hmbApplyDominoGroupFrame(container, state, card, groupId, nextHeight, resizeContext) {
  const minHeight = HMB_GROUP_MIN_HEIGHTS[groupId] || 120;
  const height = Math.max(minHeight, Math.min(HMB_GROUP_MAX_HEIGHT, Math.round(Number(nextHeight) || minHeight)));
  state.ui = normalizeUi(state.ui);
  state.ui.group_heights[groupId] = height;
  hmbStoreGroupHeight(container, groupId, height);
  hmbApplyExactGroupFlex(card, height);
  hmbApplyDashboardHostSizing(container, state);

  const nextRequiredHeight = hmbRequiredOuterNodeHeight(container, state);
  const nextNodeHeight = hmbDominoOuterHeight(
    resizeContext.startNodeHeight,
    resizeContext.startRequiredHeight,
    nextRequiredHeight
  );
  const applied = hmbApplyOuterNodeHeight(container, nextNodeHeight);
  try {
    const shell = applied && applied.shell ? applied.shell : hmbFindSafeReactFlowNode(container);
    if (shell && shell.style) shell.style.minHeight = `${nextRequiredHeight}px`;
  } catch (_e) {}
  return { groupHeight: height, nodeHeight: nextNodeHeight, requiredHeight: nextRequiredHeight };
}

function hmbEnsureOuterNodeFitsGroups(container, state, allowShrink, sizingAlreadyApplied = false) {
  if (!container || !state || hmbIsGroupResizeDragging(container)) return;
  if (container.__hmbEnsuringOuterHeight) return;
  const shell = hmbFindSafeReactFlowNode(container);
  if (!shell) return;
  if (!sizingAlreadyApplied) hmbApplyDashboardHostSizing(container, state);
  const required = hmbRequiredOuterNodeHeight(container, state);
  try { shell.style.minHeight = `${required}px`; shell.style.overflow = "visible"; } catch (_e) {}
  const current = hmbNodeShellHeight(shell);
  const next = allowShrink ? required : Math.max(required, current || 0);
  if (Math.abs(next - current) <= 1) return;
  try {
    container.__hmbEnsuringOuterHeight = true;
    hmbApplyOuterNodeHeight(container, next);
    try { shell.style.minHeight = `${required}px`; } catch (_e) {}
  } finally {
    hmbPromptLifecycleFrame(container, () => {
      try { container.__hmbEnsuringOuterHeight = false; } catch (_e) {}
    });
  }
}

function hmbFitGroupHeightsToCenter(container, state) {
  if (!container || !state || hmbIsGroupResizeDragging(container)) return;
  state.ui = normalizeUi(state.ui);
  const center = container.querySelector ? container.querySelector(".center") : null;
  if (center && center.style) center.style.overflowY = "hidden";
  HMB_GROUP_KEYS.forEach((key) => {
    const minHeight = HMB_GROUP_MIN_HEIGHTS[key] || 120;
    const stored = Number(state.ui.group_heights[key]);
    const fallback = Number(HMB_GROUP_DEFAULT_HEIGHTS[key]) || minHeight;
    const value = Math.max(minHeight, Math.min(HMB_GROUP_MAX_HEIGHT, Math.round(Number.isFinite(stored) ? stored : fallback)));
    state.ui.group_heights[key] = value;
    hmbStoreGroupHeight(container, key, value);
    const card = container.querySelector(`.group-card[data-group-id="${key}"]`);
    if (card) hmbApplyExactGroupFlex(card, value);
  });
  hmbApplyDashboardHostSizing(container, state);
  hmbEnsureOuterNodeFitsGroups(container, state, false, true);
}

function hmbApplyStoredGroupHeightsToDom(container, state) {
  if (!container) return;
  try {
    HMB_GROUP_KEYS.forEach((key) => {
      const card = container.querySelector(`.group-card[data-group-id="${key}"]`);
      if (!card) return;
      const value = state && state.ui && state.ui.group_heights ? Number(state.ui.group_heights[key]) : hmbReadStoredGroupHeight(container, key);
      if (Number.isFinite(value)) hmbApplyExactGroupFlex(card, value);
    });
  } catch (_e) {}
}

function hmbSetGroupResizeDragging(container, value) {
  if (!container) return;
  try { container.__hmbPromptLibraryGroupResizeDragging = Boolean(value); } catch (_e) {}
}

function hmbIsGroupResizeDragging(container) {
  try { return Boolean(container && container.__hmbPromptLibraryGroupResizeDragging); } catch (_e) { return false; }
}

function hmbClearActivePromptResize(container) {
  if (!container) return;
  const cleanup = container.__hmbPromptLibraryResizeCleanup;
  if (typeof cleanup === "function") {
    try { cleanup(); } catch (_error) {}
  }
  delete container.__hmbPromptLibraryResizeCleanup;
  hmbSetGroupResizeDragging(container, false);
  try { document.body?.classList?.remove("hmb-group-resizing"); } catch (_error) {}
}

function hmbInstallGroupResizers(container, state, props, listeners) {
  container.querySelectorAll(".group-resize-bar").forEach((handle) => {
    const groupId = handle.getAttribute("data-resize-group") || "";
    const card = handle.closest(".group-card");
    if (!groupId || !card || !(groupId in HMB_GROUP_MIN_HEIGHTS)) return;

    const pointerDown = (event) => {
      if (props && props.disabled) return;
      event.preventDefault();
      event.stopPropagation();

      hmbClearActivePromptResize(container);

      hmbCaptureSourceScroll(container);
      hmbFitGroupHeightsToCenter(container, state);
      hmbSetGroupResizeDragging(container, true);

      const nodeShell = hmbFindSafeReactFlowNode(container);
      if (!nodeShell || !nodeShell.style) {
        hmbSetGroupResizeDragging(container, false);
        return;
      }

      const minHeight = HMB_GROUP_MIN_HEIGHTS[groupId] || 120;
      const startY = Number(event.clientY) || 0;
      const scaleY = hmbElementVisualScaleY(card) || 1;
      const startHeight = Math.max(minHeight, hmbCurrentGroupHeight(card) || minHeight);
      const startNodeHeight = Math.max(HMB_MIN_NODE_HEIGHT, hmbNodeShellHeight(nodeShell) || hmbRequiredOuterNodeHeight(container, state));
      const startRequiredHeight = hmbRequiredOuterNodeHeight(container, state);
      const startingSlack = Math.max(0, startNodeHeight - startRequiredHeight);
      let lastHeight = startHeight;
      let lastNodeHeight = startNodeHeight;

      state.ui = normalizeUi(state.ui);
      try { document.body && document.body.classList && document.body.classList.add("hmb-group-resizing"); } catch (_e) {}

      const applyResize = (rawDelta) => {
        const minDelta = hmbGroupShrinkMinDelta(startHeight, minHeight, startRequiredHeight, startingSlack);
        const maxDelta = Math.min(HMB_GROUP_MAX_HEIGHT - startHeight, startingSlack + 6000 - startNodeHeight);
        const delta = Math.max(minDelta, Math.min(maxDelta, Math.round(rawDelta)));
        const nextHeight = Math.max(minHeight, Math.round(startHeight + delta));
        if (nextHeight === lastHeight) return;
        const frame = hmbApplyDominoGroupFrame(container, state, card, groupId, nextHeight, {
          startNodeHeight,
          startRequiredHeight,
        });
        lastHeight = frame.groupHeight;
        lastNodeHeight = frame.nodeHeight;
      };

      const move = (moveEvent) => {
        moveEvent.preventDefault();
        moveEvent.stopPropagation();
        const currentY = Number(moveEvent.clientY) || startY;
        const cssDelta = (currentY - startY) / Math.max(0.05, scaleY);
        applyResize(cssDelta);
      };

      const cleanupDrag = () => {
        document.removeEventListener("pointermove", move, true);
        document.removeEventListener("pointerup", up, true);
        document.removeEventListener("pointercancel", up, true);
        try { document.body?.classList?.remove("hmb-group-resizing"); } catch (_e) {}
        if (container.__hmbPromptLibraryResizeCleanup === cleanupDrag) {
          delete container.__hmbPromptLibraryResizeCleanup;
        }
        hmbSetGroupResizeDragging(container, false);
      };

      const up = (upEvent) => {
        upEvent.preventDefault();
        upEvent.stopPropagation();
        try { handle.releasePointerCapture?.(event.pointerId); } catch (_e) {}
        cleanupDrag();

        state.ui = normalizeUi(state.ui);
        state.ui.group_heights[groupId] = lastHeight;
        hmbStoreGroupHeight(container, groupId, lastHeight);
        hmbApplyOuterNodeHeight(container, lastNodeHeight);

        hmbCaptureUiBeforeStateEmit(container, state);
        emit(props, state, container);

        hmbPromptLifecycleFrame(container, () => {
          hmbApplyStoredGroupHeightsToDom(container, state);
          hmbEnsureOuterNodeFitsGroups(container, state, false);
          hmbRestoreSourceScroll(container);
        });
      };

      try { handle.setPointerCapture?.(event.pointerId); } catch (_e) {}
      container.__hmbPromptLibraryResizeCleanup = cleanupDrag;
      document.addEventListener("pointermove", move, true);
      document.addEventListener("pointerup", up, true);
      document.addEventListener("pointercancel", up, true);
    };

    handle.addEventListener("pointerdown", pointerDown);
    listeners.push([handle, "pointerdown", pointerDown]);
  });
}

function hmbCaptureCurrentTextareaHeights(container, state) {
  if (!container || !state) return;
  state.ui = normalizeUi(state.ui);
  try {
    container.querySelectorAll('.source-note-input[data-textarea-key]').forEach((textarea) => {
      const key = clean(textarea.getAttribute("data-textarea-key"));
      if (!hmbIsKeepOutTextareaKey(key)) return;
      const height = Math.max(
        HMB_KEEP_OUT_MIN_HEIGHT,
        Math.min(HMB_KEEP_OUT_MAX_HEIGHT, Math.round(Number(textarea.offsetHeight) || HMB_KEEP_OUT_DEFAULT_HEIGHT))
      );
      state.ui.textarea_heights[key] = height;
    });
  } catch (_e) {}
}

function hmbDirectContentHeight(element) {
  if (!element || !element.children) return 0;
  let total = 0;
  try {
    Array.from(element.children).forEach((child) => {
      total += Math.max(0, Math.round(Number(child.offsetHeight) || 0));
    });
  } catch (_e) {}
  return total;
}

function hmbInstallKeepOutResizers(container, state, props, listeners) {
  container.querySelectorAll(".keep-out-resize-bar").forEach((handle) => {
    const key = clean(handle.getAttribute("data-resize-textarea"));
    const row = handle.closest(".source-row.video");
    const textarea = row ? row.querySelector(`.source-note-input[data-textarea-key="${key}"]`) : null;
    const card = handle.closest('.group-card[data-group-id="videoSources"]');
    if (!hmbIsKeepOutTextareaKey(key) || !row || !textarea || !card) return;

    const pointerDown = (event) => {
      if ((props && props.disabled) || textarea.disabled) return;
      event.preventDefault();
      event.stopPropagation();

      hmbClearActivePromptResize(container);

      hmbCaptureSourceScroll(container);
      hmbFitGroupHeightsToCenter(container, state);
      hmbSetGroupResizeDragging(container, true);

      const nodeShell = hmbFindSafeReactFlowNode(container);
      if (!nodeShell || !nodeShell.style) {
        hmbSetGroupResizeDragging(container, false);
        return;
      }

      state.ui = normalizeUi(state.ui);
      const groupId = "videoSources";
      const groupMinHeight = HMB_GROUP_MIN_HEIGHTS[groupId] || 130;
      const startY = Number(event.clientY) || 0;
      const scaleY = hmbElementVisualScaleY(textarea) || 1;
      const startTextareaHeight = Math.max(
        HMB_KEEP_OUT_MIN_HEIGHT,
        Math.min(HMB_KEEP_OUT_MAX_HEIGHT, Math.round(Number(textarea.offsetHeight) || hmbTextareaHeight(state, key) || HMB_KEEP_OUT_DEFAULT_HEIGHT))
      );
      const startGroupHeight = Math.max(groupMinHeight, hmbCurrentGroupHeight(card) || groupMinHeight);
      const sourceScrollbox = card.querySelector(".source-scrollbox");
      const startGroupViewportHeight = Math.max(0, Math.round(Number(sourceScrollbox && sourceScrollbox.clientHeight) || 0));
      const startGroupContentHeight = Math.max(0, hmbDirectContentHeight(sourceScrollbox));
      const startingInternalSlack = Math.max(0, startGroupViewportHeight - startGroupContentHeight);
      const startNodeHeight = Math.max(HMB_MIN_NODE_HEIGHT, hmbNodeShellHeight(nodeShell) || hmbRequiredOuterNodeHeight(container, state));
      const startRequiredHeight = hmbRequiredOuterNodeHeight(container, state);
      const startingSlack = Math.max(0, startNodeHeight - startRequiredHeight);
      let lastTextareaHeight = startTextareaHeight;
      let lastGroupHeight = startGroupHeight;
      let lastNodeHeight = startNodeHeight;

      try { document.body && document.body.classList && document.body.classList.add("hmb-group-resizing"); } catch (_e) {}

      const applyResize = (rawDelta) => {
        const minDelta = HMB_KEEP_OUT_MIN_HEIGHT - startTextareaHeight;
        const maxDelta = Math.min(
          HMB_KEEP_OUT_MAX_HEIGHT - startTextareaHeight,
          startingInternalSlack + HMB_GROUP_MAX_HEIGHT - startGroupHeight,
          startingInternalSlack + startingSlack + 6000 - startNodeHeight
        );
        const delta = Math.max(minDelta, Math.min(maxDelta, Math.round(rawDelta)));
        const nextTextareaHeight = Math.max(HMB_KEEP_OUT_MIN_HEIGHT, Math.round(startTextareaHeight + delta));
        const groupDelta = hmbDominoContainerDelta(
          startGroupViewportHeight,
          startGroupContentHeight,
          delta
        );
        const nextGroupHeight = Math.max(groupMinHeight, Math.round(startGroupHeight + groupDelta));
        if (nextTextareaHeight === lastTextareaHeight && nextGroupHeight === lastGroupHeight) return;

        try {
          textarea.style.height = `${nextTextareaHeight}px`;
          textarea.style.minHeight = `${nextTextareaHeight}px`;
          textarea.style.maxHeight = `${nextTextareaHeight}px`;
        } catch (_e) {}
        state.ui.textarea_heights[key] = nextTextareaHeight;
        const frame = hmbApplyDominoGroupFrame(container, state, card, groupId, nextGroupHeight, {
          startNodeHeight,
          startRequiredHeight,
        });
        lastTextareaHeight = nextTextareaHeight;
        lastGroupHeight = frame.groupHeight;
        lastNodeHeight = frame.nodeHeight;
      };

      const move = (moveEvent) => {
        moveEvent.preventDefault();
        moveEvent.stopPropagation();
        const currentY = Number(moveEvent.clientY) || startY;
        const cssDelta = (currentY - startY) / Math.max(0.05, scaleY);
        applyResize(cssDelta);
      };

      const cleanupDrag = () => {
        document.removeEventListener("pointermove", move, true);
        document.removeEventListener("pointerup", up, true);
        document.removeEventListener("pointercancel", up, true);
        try { document.body?.classList?.remove("hmb-group-resizing"); } catch (_e) {}
        if (container.__hmbPromptLibraryResizeCleanup === cleanupDrag) {
          delete container.__hmbPromptLibraryResizeCleanup;
        }
        hmbSetGroupResizeDragging(container, false);
      };

      const up = (upEvent) => {
        upEvent.preventDefault();
        upEvent.stopPropagation();
        try { handle.releasePointerCapture?.(event.pointerId); } catch (_e) {}
        cleanupDrag();

        state.ui = normalizeUi(state.ui);
        state.ui.textarea_heights[key] = lastTextareaHeight;
        state.ui.group_heights[groupId] = lastGroupHeight;
        hmbStoreGroupHeight(container, groupId, lastGroupHeight);
        hmbApplyOuterNodeHeight(container, lastNodeHeight);

        hmbCaptureUiBeforeStateEmit(container, state);
        emit(props, state, container);

        hmbPromptLifecycleFrame(container, () => {
          hmbApplyStoredGroupHeightsToDom(container, state);
          hmbEnsureOuterNodeFitsGroups(container, state, false);
          hmbRestoreSourceScroll(container);
        });
      };

      try { handle.setPointerCapture?.(event.pointerId); } catch (_e) {}
      container.__hmbPromptLibraryResizeCleanup = cleanupDrag;
      document.addEventListener("pointermove", move, true);
      document.addEventListener("pointerup", up, true);
      document.addEventListener("pointercancel", up, true);
    };

    handle.addEventListener("pointerdown", pointerDown);
    listeners.push([handle, "pointerdown", pointerDown]);
  });
}

function hmbCaptureUiBeforeStateEmit(container, state) {
  try { hmbCaptureSourceScroll(container); } catch (_e) {}
  try { hmbPreserveManualGroupHeights(container, state); } catch (_e) {}
  try { hmbCaptureCurrentTextareaHeights(container, state); } catch (_e) {}
}

export function hmbImageDropTargetIndex(sourceIndex, hoverIndex, placeAfter, imageCount) {
  const count = Math.max(0, Math.trunc(Number(imageCount) || 0));
  const source = Math.trunc(Number(sourceIndex));
  const hover = Math.trunc(Number(hoverIndex));
  if (count < 1 || source < 0 || source >= count || hover < 0 || hover >= count) return -1;
  const insertionIndex = hover + (placeAfter ? 1 : 0);
  const target = source < insertionIndex ? insertionIndex - 1 : insertionIndex;
  return Math.max(0, Math.min(count - 1, target));
}

function hmbClearImageDragIndicators(container) {
  if (!container) return;
  container.querySelectorAll?.(".source-row.image").forEach((row) => {
    row.classList?.remove("image-row-dragging", "image-drop-before", "image-drop-after");
  });
}

function hmbSyncSourceRowActivation(row) {
  if (!row || row.classList.contains("image-add-row") || row.classList.contains("video-add-row")) return;
  const nameInput = row.querySelector('.source-label-input[data-field="label"]');
  row.classList.remove("name-missing");
  row.querySelectorAll('.source-select, .source-target-input, .custom-field-input, .custom-inline-input, .source-note-input, .remove-color-pick, .add-color-pick, .frame-range-toggle, .frame-domain-number').forEach((control) => {
    if (control === nameInput) return;
    if (!control.hasAttribute("data-hmb-base-disabled")) control.setAttribute("data-hmb-base-disabled", control.disabled ? "1" : "0");
    const baseDisabled = control.getAttribute("data-hmb-base-disabled") === "1";
    control.disabled = baseDisabled;
  });
}

function hmbSyncAllSourceRowActivation(container) {
  container.querySelectorAll('.source-row[data-index]').forEach(hmbSyncSourceRowActivation);
}

function hmbCopyPromptElementAttributes(target, source) {
  if (!target || !source) return;
  const nextNames = new Set(Array.from(source.attributes || []).map((attribute) => attribute.name));
  Array.from(target.attributes || []).forEach((attribute) => {
    if (!nextNames.has(attribute.name)) target.removeAttribute(attribute.name);
  });
  Array.from(source.attributes || []).forEach((attribute) => {
    if (target.getAttribute(attribute.name) !== attribute.value) {
      target.setAttribute(attribute.name, attribute.value);
    }
  });
}

// Retain only the active editor path while adopting every authoritative
// sibling. This prevents a focused label/textarea (or active IME session) from
// making its whole source row or text group stale.
function hmbPromptEditablePatchKey(element) {
  if (!hmbIsEditableTextControl(element)) return "";
  const textKey = element.getAttribute?.("data-text-key") || "";
  if (textKey) return `text:${textKey}`;
  const row = element.closest?.(".source-row") || null;
  const sourceKey = row?.getAttribute?.("data-source-key") || "";
  return [
    "source", sourceKey,
    row?.getAttribute?.("data-kind") || "",
    element.getAttribute?.("data-field") || "",
    element.getAttribute?.("data-custom-array") || "",
    element.getAttribute?.("data-custom-index") || "",
    element.getAttribute?.("data-frame-domain-number") || "",
  ].join(":");
}

function hmbPromptEditableDescendants(root) {
  const found = [];
  const visit = (node) => {
    if (!node) return;
    if (hmbIsEditableTextControl(node)) found.push(node);
    Array.from(node.childNodes || []).forEach(visit);
  };
  visit(root);
  return found;
}

function hmbPromptDirectChildOnPath(root, descendant) {
  if (!root || !descendant || root === descendant) return descendant === root ? root : null;
  let current = descendant;
  while (current) {
    const parent = current.parentNode || current.parentElement || null;
    if (parent === root) return current;
    current = parent;
  }
  return null;
}

export function hmbPatchPromptElementTree(current, next, activeEditor = null) {
  if (!current || !next) return false;
  const currentEditors = hmbPromptEditableDescendants(current);
  const nextEditors = hmbPromptEditableDescendants(next);
  const activeKey = hmbPromptEditablePatchKey(activeEditor);
  const activeOrdinal = currentEditors.indexOf(activeEditor);
  const nextEditor = nextEditors.find((editor) => (
    activeKey && hmbPromptEditablePatchKey(editor) === activeKey
  )) || (activeOrdinal >= 0 ? nextEditors[activeOrdinal] : null);
  if (!activeEditor || !current.contains?.(activeEditor) || !nextEditor) return false;

  const patchAnchored = (currentNode, nextNode) => {
    const protectsActiveEditor = currentNode === activeEditor;
    const value = protectsActiveEditor && "value" in currentNode ? currentNode.value : undefined;
    const selectionStart = protectsActiveEditor && Number.isFinite(Number(currentNode.selectionStart))
      ? Number(currentNode.selectionStart) : null;
    const selectionEnd = protectsActiveEditor && Number.isFinite(Number(currentNode.selectionEnd))
      ? Number(currentNode.selectionEnd) : null;
    const selectionDirection = protectsActiveEditor
      ? (currentNode.selectionDirection || "none") : "none";
    hmbCopyPromptElementAttributes(currentNode, nextNode);
    if (protectsActiveEditor) {
      if (value !== undefined && currentNode.value !== value) currentNode.value = value;
      if (
        selectionStart != null
        && selectionEnd != null
        && (
          Number(currentNode.selectionStart) !== selectionStart
          || Number(currentNode.selectionEnd) !== selectionEnd
          || String(currentNode.selectionDirection || "none") !== selectionDirection
        )
      ) {
        try { currentNode.setSelectionRange?.(selectionStart, selectionEnd, selectionDirection); } catch (_error) {}
      }
      return;
    }
    const currentAnchor = hmbPromptDirectChildOnPath(currentNode, activeEditor);
    const nextAnchor = hmbPromptDirectChildOnPath(nextNode, nextEditor);
    if (!currentAnchor || !nextAnchor) return;
    const desired = Array.from(nextNode.childNodes || []).map((child) => (
      child === nextAnchor ? currentAnchor : child
    ));
    const anchorIndex = desired.indexOf(currentAnchor);
    desired.slice(0, anchorIndex).forEach((child) => {
      currentNode.insertBefore?.(child, currentAnchor);
    });
    const liveChildren = Array.from(currentNode.childNodes || []);
    const liveAnchorIndex = liveChildren.indexOf(currentAnchor);
    const trailingReference = liveAnchorIndex >= 0 ? liveChildren[liveAnchorIndex + 1] || null : null;
    desired.slice(anchorIndex + 1).forEach((child) => {
      currentNode.insertBefore?.(child, trailingReference);
    });
    const retained = new Set(desired);
    Array.from(currentNode.childNodes || []).forEach((child) => {
      if (!retained.has(child)) child.remove?.();
    });
    patchAnchored(currentAnchor, nextAnchor);
  };
  patchAnchored(current, next);
  return true;
}

function hmbPromptDirectSourceRows(scrollbox) {
  return Array.from(scrollbox?.children || []).filter((element) => (
    element?.classList?.contains?.("source-row")
  ));
}

function hmbPromptRowPatchKey(row) {
  const stable = row?.getAttribute?.("data-source-key") || "";
  if (stable) return `source:${stable}`;
  return `utility:${row?.getAttribute?.("data-kind") || ""}`;
}

export function hmbPatchPromptSourceSection(currentSection, nextSection) {
  if (!currentSection || !nextSection) return false;
  hmbCopyPromptElementAttributes(currentSection, nextSection);
  const currentHeading = currentSection.querySelector?.("h3");
  const nextHeading = nextSection.querySelector?.("h3");
  if (currentHeading && nextHeading && currentHeading.innerHTML !== nextHeading.innerHTML) {
    currentHeading.innerHTML = nextHeading.innerHTML;
  }
  const currentScrollbox = currentSection.querySelector?.(".source-scrollbox");
  const nextScrollbox = nextSection.querySelector?.(".source-scrollbox");
  if (!currentScrollbox || !nextScrollbox) return false;
  hmbCopyPromptElementAttributes(currentScrollbox, nextScrollbox);
  const currentHeader = currentScrollbox.querySelector?.(".source-header");
  const nextHeader = nextScrollbox.querySelector?.(".source-header");
  if (currentHeader && nextHeader && currentHeader.innerHTML !== nextHeader.innerHTML) {
    currentHeader.innerHTML = nextHeader.innerHTML;
  }
  const existing = new Map(
    hmbPromptDirectSourceRows(currentScrollbox).map((row) => [hmbPromptRowPatchKey(row), row]),
  );
  const retained = new Set();
  for (const nextRow of hmbPromptDirectSourceRows(nextScrollbox)) {
    const key = hmbPromptRowPatchKey(nextRow);
    let row = existing.get(key);
    if (!row) {
      row = nextRow;
    } else {
      const preserveActiveEditor = Boolean(
        hmbIsEditableTextControl(row.ownerDocument?.activeElement)
        && row.contains?.(row.ownerDocument.activeElement)
      );
      const contentChanged = row.outerHTML !== nextRow.outerHTML;
      hmbCopyPromptElementAttributes(row, nextRow);
      if (contentChanged) {
        if (preserveActiveEditor) {
          hmbPatchPromptElementTree(row, nextRow, row.ownerDocument.activeElement);
        } else row.innerHTML = nextRow.innerHTML;
      }
    }
    retained.add(row);
    currentScrollbox.appendChild(row);
  }
  hmbPromptDirectSourceRows(currentScrollbox).forEach((row) => {
    if (!retained.has(row)) row.remove?.();
  });
  const currentResize = currentSection.querySelector?.("[data-resize-group]");
  const nextResize = nextSection.querySelector?.("[data-resize-group]");
  if (currentResize && nextResize) hmbCopyPromptElementAttributes(currentResize, nextResize);
  return true;
}

// Retained-mode structural paint.  The dashboard and stable source-row nodes
// survive add/remove/reorder/language/authority updates, so there is no blank
// frame and the browser can restore focus to the same source identity.
export function hmbPatchPromptDashboard(container, markup) {
  const currentClip = container?.querySelector?.(".hmb-dashboard-clip");
  const currentRoot = currentClip?.querySelector?.(".hmb-dashboard")
    || container?.querySelector?.(".hmb-dashboard");
  const documentRef = currentRoot?.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  if (!currentRoot || !documentRef?.createElement) return false;
  const staging = documentRef.createElement("div");
  staging.innerHTML = String(markup || "");
  const nextClip = staging.querySelector?.(".hmb-dashboard-clip");
  const nextRoot = nextClip?.querySelector?.(".hmb-dashboard")
    || staging.querySelector?.(".hmb-dashboard");
  if (!nextRoot) return false;
  if (currentClip && nextClip) hmbCopyPromptElementAttributes(currentClip, nextClip);
  hmbCopyPromptElementAttributes(currentRoot, nextRoot);

  const currentTopbar = currentRoot.querySelector?.(".topbar");
  const nextTopbar = nextRoot.querySelector?.(".topbar");
  if (currentTopbar && nextTopbar && currentTopbar.innerHTML !== nextTopbar.innerHTML) {
    currentTopbar.innerHTML = nextTopbar.innerHTML;
  }

  for (const nextSection of Array.from(nextRoot.querySelectorAll?.("[data-group-id]") || [])) {
    const groupId = nextSection.getAttribute("data-group-id");
    const currentSection = Array.from(currentRoot.querySelectorAll?.("[data-group-id]") || [])
      .find((section) => section.getAttribute("data-group-id") === groupId);
    if (!currentSection) continue;
    if (["imageSources", "videoSources"].includes(groupId)) {
      hmbPatchPromptSourceSection(currentSection, nextSection);
    } else if (currentSection.innerHTML !== nextSection.innerHTML) {
      const active = currentSection.ownerDocument?.activeElement;
      const preserveActiveEditor = Boolean(
        hmbIsEditableTextControl(active) && currentSection.contains?.(active)
      );
      if (preserveActiveEditor) hmbPatchPromptElementTree(currentSection, nextSection, active);
      else {
        hmbCopyPromptElementAttributes(currentSection, nextSection);
        currentSection.innerHTML = nextSection.innerHTML;
      }
    }
  }
  return true;
}

export default function HMBPromptLibraryScopedBindingWidget(container, props) {
  if (!container) {
    return {
      cleanup() {},
      update() {},
    };
  }
  props = props || {};
  if (typeof container.__hmbPromptLibraryCleanupProxy !== "function") {
    container.__hmbPromptLibraryCleanupProxy = () => {
      const currentCleanup = container.__hmbPromptLibraryCleanup;
      if (typeof currentCleanup === "function") currentCleanup();
    };
  }
  if (typeof container.__hmbPromptLibraryApplyProps === "function") {
    container.__hmbPromptLibraryApplyProps(props || {});
    return {
      cleanup: container.__hmbPromptLibraryCleanupProxy,
      update(nextProps) {
        container.__hmbPromptLibraryApplyProps?.(nextProps || {});
      },
    };
  }
  const previousCleanup = container.__hmbPromptLibraryCleanup;
  if (typeof previousCleanup === "function") previousCleanup();
  const lifecycle = { disposed: false, tasks: new Set() };
  const lifecycleCurrent = () => (
    !lifecycle.disposed && container.__hmbPromptLibraryLifecycle === lifecycle
  );
  const scheduleLifecycleFrame = (callback) => {
    if (!lifecycleCurrent() || typeof callback !== "function") return 0;
    const task = { kind: "raf", handle: 0, cancelled: false };
    const run = () => {
      lifecycle.tasks.delete(task);
      if (!task.cancelled && lifecycleCurrent()) callback();
    };
    lifecycle.tasks.add(task);
    try {
      if (typeof requestAnimationFrame === "function") {
        task.handle = requestAnimationFrame(run);
      } else {
        task.kind = "timeout";
        task.handle = setTimeout(run, 0);
      }
    } catch (_error) {
      try {
        task.kind = "timeout";
        task.handle = setTimeout(run, 0);
      } catch (__error) {
        lifecycle.tasks.delete(task);
      }
    }
    return task.handle;
  };
  const scheduleLifecycleMicrotask = (callback) => {
    if (!lifecycleCurrent() || typeof callback !== "function") return;
    const task = { kind: "microtask", handle: 0, cancelled: false };
    const run = () => {
      lifecycle.tasks.delete(task);
      if (!task.cancelled && lifecycleCurrent()) callback();
    };
    lifecycle.tasks.add(task);
    try {
      if (typeof queueMicrotask === "function") queueMicrotask(run);
      else {
        task.kind = "timeout";
        task.handle = setTimeout(run, 0);
      }
    } catch (_error) {
      try {
        task.kind = "timeout";
        task.handle = setTimeout(run, 0);
      } catch (__error) {
        lifecycle.tasks.delete(task);
      }
    }
  };
  const disposeLifecycle = () => {
    lifecycle.disposed = true;
    for (const task of lifecycle.tasks) {
      task.cancelled = true;
      try {
        if (task.kind === "raf" && typeof cancelAnimationFrame === "function") {
          cancelAnimationFrame(task.handle);
        } else if (task.kind === "timeout") {
          clearTimeout(task.handle);
        }
      } catch (_error) {}
    }
    lifecycle.tasks.clear();
  };
  container.__hmbPromptLibraryLifecycle = lifecycle;
  container.__hmbPromptLibraryScheduleFrame = scheduleLifecycleFrame;
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  let state = hmbMergeStoredGroupHeights(container, parseValue(props.value));
  state.disabled = Boolean(props.disabled);
  hmbRememberPromptRevisionState(container, state, state.disabled, false);
  state.ui = state.ui && typeof state.ui === "object" ? state.ui : defaultUi();
  const listeners = [];
  hmbApplyInitialNodeSizeOnce(container);
  const stopFluidSync = hmbInstallFluidLayoutSync(container, () => state);
  hmbApplyDashboardHostSizing(container, state);
  let discoveryRequested = false;
  let renderRevision = 0;
  const remount = (nextState = null) => {
    const ownRenderRevision = ++renderRevision;
    if (nextState && typeof nextState === "object") {
      const normalizedNextState = hmbMergeStoredGroupHeights(container, normalizeState(nextState));
      hmbReconcilePromptSourceIdentities(state, normalizedNextState);
      state = normalizedNextState;
    }
    hmbClearActivePromptResize(container);
    try { container.__hmbFrameRangeDragCleanup?.(); } catch (_e) {}
    const preserveActiveText = Boolean(
      container.__hmbPromptLibraryCommitPending
      || container.__hmbPromptLibraryCompositionActive
    );
    const activeText = typeof document !== "undefined" ? document.activeElement : null;
    if (preserveActiveText && activeText && container.contains?.(activeText)) {
      hmbRememberPromptDirtyTextControl(container, activeText, state);
    }
    const compositionWasActive = Boolean(container.__hmbPromptLibraryCompositionActive);
    hmbCaptureTextEditingState(container);
    hmbCapturePromptControlFocus(container);
    hmbCaptureUiBeforeStateEmit(container, state);
    for (const [el, event, handler, options] of listeners.splice(0)) {
      try { el.removeEventListener(event, handler, options); } catch (_e) {}
    }
    state = hmbMergeStoredGroupHeights(container, normalizeState(state));
    const markup = hmbScopeWidgetStyleMarkup(render(state), ".hmb-dashboard");
    if (!hmbPatchPromptDashboard(container, markup)) container.innerHTML = markup;
    if (
      compositionWasActive
      && (!activeText || !container.contains?.(activeText))
    ) hmbReleasePromptCompositionLatch(container);
    hmbSyncAllSourceRowActivation(container);
    hmbFitGroupHeightsToCenter(container, state);
    hmbInstallPromptInteractionIsolation(container, listeners);
    hmbInstallSourceScrollPositionLock(container, listeners);
    hmbInstallGroupResizers(container, state, props, listeners);
    hmbInstallKeepOutResizers(container, state, props, listeners);
    hmbInstallFrameRangeInteractions(container, state, props, listeners);
    hmbRestoreSourceScroll(container);
    hmbRestorePromptControlFocus(container);
    hmbRestoreTextEditingStateDeferred(container);
    const clearTextFocusOnPointerDown = (event) => {
      hmbRememberPromptTextPointerTarget(container, event);
      if (!hmbIsEditableTextControl(event && event.target)) hmbClearTextEditingState(container);
    };
    container.addEventListener("pointerdown", clearTextFocusOnPointerDown, true);
    listeners.push([container, "pointerdown", clearTextFocusOnPointerDown, true]);
    const clearPendingTextTargetOnFocusIn = (event) => {
      if (!hmbIsEditableTextControl(event && event.target)) return;
      try { container.__hmbPromptLibraryPointerTextTarget = null; } catch (_e) {}
    };
    container.addEventListener("focusin", clearPendingTextTargetOnFocusIn);
    listeners.push([container, "focusin", clearPendingTextTargetOnFocusIn]);
    const compositionStart = (event) => {
      if (!hmbIsEditableTextControl(event && event.target)) return;
      container.__hmbPromptLibraryCompositionActive = true;
      hmbRememberPromptDirtyTextControl(container, event.target, state);
    };
    const compositionEnd = (event) => {
      if (!hmbIsEditableTextControl(event && event.target)) return;
      hmbRememberPromptDirtyTextControl(container, event.target, state);
      hmbReleasePromptCompositionLatch(container);
      hmbScheduleImmediateStateCommit(container, props, state);
    };
    container.addEventListener("compositionstart", compositionStart);
    container.addEventListener("compositionend", compositionEnd);
    listeners.push([container, "compositionstart", compositionStart]);
    listeners.push([container, "compositionend", compositionEnd]);
    if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
      const shotCatalogHandler = (event) => {
        const result = hmbApplyRemoteShotCatalog(state, event?.detail);
        state = result.state || state;
        if (result.changed) hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      window.addEventListener("hmb-shot-routing-catalog-v1", shotCatalogHandler);
      listeners.push([window, "hmb-shot-routing-catalog-v1", shotCatalogHandler]);
      const discover = () => {
        try {
          window.dispatchEvent(new CustomEvent("hmb-shot-routing-discover-v1", {
            detail: { schema: "hmb-shot-routing-discover", version: 1, participant_kind: "prompt" },
          }));
        } catch (_e) {}
      };
      if (!discoveryRequested) {
        discoveryRequested = true;
        scheduleLifecycleMicrotask(discover);
      }
    }
    scheduleLifecycleFrame(() => {
      if (ownRenderRevision !== renderRevision) return;
      hmbApplyStoredGroupHeightsToDom(container, state);
      hmbEnsureOuterNodeFitsGroups(container, state, false);
      hmbRestoreSourceScroll(container);
      hmbRestorePromptControlFocus(container);
      hmbRestoreTextEditingState(container);
    });

    container.querySelectorAll(".source-label-input").forEach((input) => {
      const row = input.closest(".source-row");
      const kind = row ? row.getAttribute("data-kind") : "";
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const field = input.getAttribute("data-field") || "label";
      const liveHandler = () => {
        const target = kind === "image" ? state.images : state.videos;
        if (target[index]) {
          target[index][field] = input.value;
          if (field === "label") {
            if (kind === "video") target[index].picker_auto_label = "";
            target[index].present = false;
            target[index].present = kind === "image"
              ? hasImageMeaning(target[index])
              : hasVideoMeaning(target[index]);
            hmbSyncSourceRowActivation(row);
            if (kind === "video") hmbRefreshImageColorControls(container, state);
            if (kind === "image") refreshImageTargetControls(container, state);
          }
          hmbRememberPromptDirtyTextControl(container, input, state);
          hmbScheduleImmediateStateCommit(container, props, state);
        }
      };
      const handler = (event) => {
        const target = kind === "image" ? state.images : state.videos;
        if (target[index]) {
          target[index][field] = input.value;
          if (field === "label") {
            if (kind === "video") target[index].picker_auto_label = "";
            target[index].present = Boolean(input.value.trim());
            if (kind === "video") hmbRefreshImageColorControls(container, state);
          }
          hmbRememberPromptDirtyTextControl(container, input, state);
          if (event && event.type === "blur") {
            hmbFinalizePromptTextBlur(container, event, () => {
              hmbCaptureUiBeforeStateEmit(container, state);
              emit(props, state, container);
              hmbRestoreSourceScroll(container);
            });
          } else {
            hmbScheduleImmediateStateCommit(container, props, state);
          }
        }
      };
      input.addEventListener("input", liveHandler);
      input.addEventListener("blur", handler);
      input.addEventListener("change", handler);
      listeners.push([input, "input", liveHandler]);
      listeners.push([input, "blur", handler]);
      listeners.push([input, "change", handler]);
    });

    container.querySelectorAll(".custom-field-input, .custom-inline-input").forEach((input) => {
      const row = input.closest(".source-row");
      const kind = row ? row.getAttribute("data-kind") : "";
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const commit = (emitAfter, event = null) => {
        const target = kind === "image" ? state.images : state.videos;
        if (!target[index]) return;
        const arrayField = input.getAttribute("data-custom-array");
        if (arrayField) {
          const customIndex = Number(input.getAttribute("data-custom-index") || 0);
          const maxCount = MAX_COLOR_PICKS;
          const baseCount = normalizeColorPicks(target[index].color_picks).length;
          if (kind === "image" && arrayField === "binding_custom_scopes") {
            normalizeImageBindingFields(target[index], videoSlotCount(state));
            target[index][arrayField] = Array.from(
              { length: target[index].binding_scopes.length },
              () => input.value,
            );
          } else {
            target[index][arrayField] = normalizeParallelTextList(target[index][arrayField], baseCount, maxCount);
            target[index][arrayField][customIndex] = input.value;
          }
        } else {
          target[index][input.getAttribute("data-field")] = input.value;
        }
        hmbRememberPromptDirtyTextControl(container, input, state);
        hmbScheduleImmediateStateCommit(container, props, state);
        if (emitAfter) {
          hmbFinalizePromptTextBlur(container, event, () => {
            hmbCaptureUiBeforeStateEmit(container, state);
            emit(props, state, container);
            hmbRestoreSourceScroll(container);
          });
        }
      };
      const inputHandler = () => commit(false);
      const blurHandler = (event) => commit(true, event);
      const changeHandler = () => commit(false);
      input.addEventListener("input", inputHandler);
      input.addEventListener("blur", blurHandler);
      input.addEventListener("change", changeHandler);
      listeners.push([input, "input", inputHandler]);
      listeners.push([input, "blur", blurHandler]);
      listeners.push([input, "change", changeHandler]);
    });

    container.querySelectorAll(".source-select").forEach((select) => {
      const row = select.closest(".source-row");
      const kind = row ? row.getAttribute("data-kind") : "";
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const field = select.getAttribute("data-field") || "source_type";
      const handler = () => {
        const target = kind === "image" ? state.images : state.videos;
        if (target[index]) {
          if (kind === "image" && field === "color_picks") {
            const colorIndex = Number(select.getAttribute("data-color-index") || 0);
            normalizeImageBindingFields(target[index]);
            const picks = normalizeColorPicks(target[index].color_picks);
            picks[colorIndex] = select.value;
            target[index].color_picks = normalizeColorPicks(picks);
            target[index].frame_range_color_index = colorIndex;
            normalizeImageBindingFields(target[index], videoSlotCount(state));
            enforceColorPickUniquenessByVideo(state.images, videoSlotCount(state));
          } else if (kind === "image" && field === "binding_scopes") {
            normalizeImageBindingFields(target[index]);
            const bindingCount = target[index].binding_scopes.length;
            const customScope = select.value === "Custom scope"
              ? clean(target[index].binding_custom_scopes[0])
              : "";
            target[index].binding_scopes = Array.from({ length: bindingCount }, () => select.value);
            target[index].binding_custom_scopes = Array.from({ length: bindingCount }, () => customScope);
            target[index].scope = select.value;
          } else if (kind === "image" && field === "binding_video_slots") {
            const count = MAX_VIDEOS;
            normalizeImageBindingFields(target[index], count);
            const bindingIndex = Math.max(0, Math.min(
              target[index].binding_video_slots.length - 1,
              Number(select.getAttribute("data-binding-index") || 0),
            ));
            const previousVideo = target[index].binding_video_slots[bindingIndex];
            const previousColor = clean(target[index].color_picks[bindingIndex]);
            const nextVideo = normalizeMarkerVideo(select.value, MAX_VIDEOS);
            target[index].binding_video_slots[bindingIndex] = nextVideo;
            target[index].marker_video = target[index].binding_video_slots[0];
            target[index].frame_range_color_index = bindingIndex;
            if (
              nextVideo !== previousVideo
              && clean(target[index].picker_auto_color) === previousColor
              && normalizeMarkerVideo(target[index].picker_auto_video || 1, MAX_VIDEOS) === previousVideo
            ) {
              target[index].picker_auto_color = "";
              target[index].picker_auto_video = 0;
              target[index].picker_auto_source = "";
            }
            enforceColorPickUniquenessByVideo(state.images, videoSlotCount(state));
          } else {
            target[index][field] = select.value;
            if (kind === "image" && field === "source_type") {
              if (select.value !== "Custom") target[index].custom_source_type = "";
              reconcileImageBindingAfterTypeChange(target[index], target);
            }
            if (kind === "video" && field === "source_type") {
              if (select.value !== "Custom") target[index].custom_source_type = "";
              applyVideoRoleDefaultForSourceType(target[index]);
              if (
                select.value === "Maya Preview / Playblast"
                && target[index].control_role === "Primary Unified Shot Control"
              ) {
                target[index].control_role = "";
                target[index].custom_control_role = "";
              }
              if (select.value === "Ignore / Unused") {
                hmbSuppressPickerVideoSlot(state, target[index].slot || index + 1);
              } else {
                hmbReleasePickerVideoSlotSuppression(state, target[index].slot || index + 1);
              }
            }
            if (kind === "video" && field === "control_role" && select.value !== "Custom Role") target[index].custom_control_role = "";
          }
          if (kind === "image") syncCurrentFrameRangeBinding(target[index]);
          hmbSyncSourceSelectDom(container, state, row, kind, index, field);
          hmbCaptureUiBeforeStateEmit(container, state);
          hmbEmitLocalPromptState(container, props, state);
          hmbRestoreSourceScroll(container);
        }
      };
      select.addEventListener("change", handler);
      listeners.push([select, "change", handler]);
    });

    container.querySelectorAll(".move-image-up, .move-image-down").forEach((button) => {
      const row = button.closest(".source-row");
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const direction = button.classList.contains("move-image-up") ? -1 : 1;
      const handler = () => {
        if (state?.image_asset?.enabled && state?.image_asset?.order_managed) return;
        const targetIndex = index + direction;
        if (!swapImageRowsWithoutReset(state, index, targetIndex)) return;
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });

    container.querySelectorAll("[data-image-drag-handle]").forEach((handle) => {
      const row = handle.closest(".source-row.image");
      const sourceIndex = row ? Number(row.getAttribute("data-index")) : -1;
      const pointerDown = (event) => {
        event.stopPropagation();
      };
      const dragStart = (event) => {
        event.stopPropagation();
        if (
          state.disabled
          || (state?.image_asset?.enabled && state?.image_asset?.order_managed)
          || state.images.length < 2
          || sourceIndex < 0
        ) {
          event.preventDefault();
          return;
        }
        hmbCaptureSourceScroll(container);
        container.__hmbPromptImageDragIndex = sourceIndex;
        row?.classList?.add("image-row-dragging");
        try {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(sourceIndex));
        } catch (_error) {}
      };
      const dragEnd = (event) => {
        event.stopPropagation();
        hmbClearImageDragIndicators(container);
        delete container.__hmbPromptImageDragIndex;
      };
      const keyDown = (event) => {
        if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
        if (state.disabled || (state?.image_asset?.enabled && state?.image_asset?.order_managed)) return;
        const targetIndex = sourceIndex + (event.key === "ArrowUp" ? -1 : 1);
        if (!swapImageRowsWithoutReset(state, sourceIndex, targetIndex)) return;
        event.preventDefault();
        event.stopPropagation();
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      handle.addEventListener("pointerdown", pointerDown);
      handle.addEventListener("dragstart", dragStart);
      handle.addEventListener("dragend", dragEnd);
      handle.addEventListener("keydown", keyDown);
      listeners.push([handle, "pointerdown", pointerDown]);
      listeners.push([handle, "dragstart", dragStart]);
      listeners.push([handle, "dragend", dragEnd]);
      listeners.push([handle, "keydown", keyDown]);
    });

    container.querySelectorAll(".source-row.image:not(.image-add-row)").forEach((row) => {
      const hoverIndex = Number(row.getAttribute("data-index"));
      const dropPosition = (event) => {
        const rect = row.getBoundingClientRect?.();
        if (!rect) return false;
        return Number(event.clientY || 0) >= Number(rect.top || 0) + Number(rect.height || 0) / 2;
      };
      const dragOver = (event) => {
        if (state?.image_asset?.enabled && state?.image_asset?.order_managed) return;
        const sourceIndex = Number(container.__hmbPromptImageDragIndex);
        if (!Number.isInteger(sourceIndex) || sourceIndex < 0 || sourceIndex >= state.images.length) return;
        event.preventDefault();
        event.stopPropagation();
        try { event.dataTransfer.dropEffect = "move"; } catch (_error) {}
        hmbClearImageDragIndicators(container);
        const sourceRow = container.querySelector(`.source-row.image[data-index="${sourceIndex}"]`);
        sourceRow?.classList?.add("image-row-dragging");
        row.classList.add(dropPosition(event) ? "image-drop-after" : "image-drop-before");
      };
      const drop = (event) => {
        if (state?.image_asset?.enabled && state?.image_asset?.order_managed) return;
        event.preventDefault();
        event.stopPropagation();
        let sourceIndex = Number(container.__hmbPromptImageDragIndex);
        if (!Number.isInteger(sourceIndex)) {
          try { sourceIndex = Number(event.dataTransfer.getData("text/plain")); } catch (_error) {}
        }
        const targetIndex = hmbImageDropTargetIndex(
          sourceIndex,
          hoverIndex,
          dropPosition(event),
          state.images.length,
        );
        hmbClearImageDragIndicators(container);
        delete container.__hmbPromptImageDragIndex;
        if (targetIndex < 0 || !moveImageRowWithoutReset(state, sourceIndex, targetIndex)) return;
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      row.addEventListener("dragover", dragOver);
      row.addEventListener("drop", drop);
      listeners.push([row, "dragover", dragOver]);
      listeners.push([row, "drop", drop]);
    });

    container.querySelectorAll(".clear-source").forEach((button) => {
      const row = button.closest(".source-row");
      const kind = row ? row.getAttribute("data-kind") : "";
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const handler = () => {
        if (kind === "video" && hmbPromptVideoRowsLocked(state)) return;
        const target = kind === "image" ? state.images : state.videos;
        if (target[index]) {
          if (kind === "image") {
            if (
              target[index].asset_managed
              && state?.image_asset?.enabled
              && state?.image_asset?.order_managed
            ) return;
            const result = removeImageRowAndPromote(state, index);
            if (!result.changed) return;
            hmbCommitLocalPromptStructure(container, props, state, remount);
            return;
          }
          const isLast = index === target.length - 1;
          const minimum = 1;
          const removedSlot = Number(target[index].slot || index + 1);
          hmbSuppressPickerVideoSlot(state, removedSlot);
          if (isLast && target.length > minimum) {
            target.pop();
          } else {
            const slot = removedSlot;
            target[index] = defaultVideo(slot);
            if (kind === "video" && slot === 1) target[index].manual = true;
          }
          if (kind === "video") {
            state.ui = normalizeUi(state.ui);
            delete state.ui.textarea_heights[hmbTextareaKey("video", removedSlot, "keep_out")];
          }
          hmbCommitLocalPromptStructure(container, props, state, remount);
        }
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });


    container.querySelectorAll(".remove-color-pick").forEach((button) => {
      const row = button.closest(".source-row");
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const handler = () => {
        if (!state.images[index]) return;
        normalizeImageBindingFields(state.images[index]);
        const picks = normalizeColorPicks(state.images[index].color_picks);
        const scopes = normalizeBindingScopes(state.images[index].binding_scopes, state.images[index].scope, picks.length);
        const videoSlots = normalizeBindingVideoSlots(
          state.images[index].binding_video_slots,
          state.images[index].marker_video,
          picks.length,
          videoSlotCount(state),
        );
        if (picks.length > 1) {
          const removedColor = clean(picks[picks.length - 1]);
          const removedVideo = videoSlots[videoSlots.length - 1];
          picks.pop();
          scopes.pop();
          videoSlots.pop();
          const customScopes = normalizeParallelTextList(state.images[index].binding_custom_scopes, picks.length + 1, MAX_COLOR_PICKS);
          customScopes.pop();
          state.images[index].color_picks = picks;
          state.images[index].binding_scopes = scopes;
          state.images[index].binding_custom_scopes = customScopes;
          state.images[index].binding_video_slots = videoSlots;
          state.images[index].marker_video = videoSlots[0];
          if (removedColor) {
            const bindings = normalizeFrameRangeBindings(
              state.images[index].frame_range_bindings,
              state.images[index].frame_range_binding,
            );
            delete bindings[frameBindingKey(removedVideo, removedColor)];
            state.images[index].frame_range_bindings = bindings;
            state.images[index].frame_range_binding = null;
          }
          state.images[index].frame_range_color_index = Math.min(
            Number(state.images[index].frame_range_color_index) || 0,
            picks.length - 1,
          );
          if (
            clean(state.images[index].picker_auto_color) === removedColor
            && normalizeMarkerVideo(state.images[index].picker_auto_video || 1, MAX_VIDEOS) === removedVideo
          ) {
            state.images[index].picker_auto_color = "";
            state.images[index].picker_auto_video = 0;
            state.images[index].picker_auto_source = "";
          }
          state.images[index].scope = scopes[0] || "";
          syncCurrentFrameRangeBinding(state.images[index]);
          enforceColorPickUniquenessByVideo(state.images, videoSlotCount(state));
          hmbCommitLocalPromptStructure(container, props, state, remount);
        }
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });


    container.querySelectorAll(".add-color-pick").forEach((button) => {
      const row = button.closest(".source-row");
      const index = row ? Number(row.getAttribute("data-index")) : -1;
      const handler = () => {
        if (!state.images[index]) return;
        normalizeImageBindingFields(state.images[index]);
        const picks = normalizeColorPicks(state.images[index].color_picks);
        const scopes = normalizeBindingScopes(state.images[index].binding_scopes, state.images[index].scope, picks.length);
        const videoSlots = normalizeBindingVideoSlots(
          state.images[index].binding_video_slots,
          state.images[index].marker_video,
          picks.length,
          videoSlotCount(state),
        );
        if (picks.length < MAX_COLOR_PICKS) {
          picks.push("");
          scopes.push(scopes[0] || "");
          videoSlots.push(videoSlots[videoSlots.length - 1] || 1);
          const customScopes = normalizeParallelTextList(state.images[index].binding_custom_scopes, picks.length - 1, MAX_COLOR_PICKS);
          customScopes.push(customScopes[0] || "");
          state.images[index].color_picks = picks;
          state.images[index].binding_scopes = scopes;
          state.images[index].binding_custom_scopes = customScopes;
          state.images[index].binding_video_slots = videoSlots;
          state.images[index].marker_video = videoSlots[0];
          state.images[index].scope = scopes[0] || "";
          enforceColorPickUniquenessByVideo(state.images, videoSlotCount(state));
          hmbCommitLocalPromptStructure(container, props, state, remount);
        }
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });

    container.querySelectorAll(".add-image-source").forEach((button) => {
      const handler = () => {
        if (!hmbCanAddPromptImageRow(state)) return;
        const next = defaultImage((state.images || []).length + 1);
        next.manual = true;
        state.images.push(next);
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });

    const shotSelector = container.querySelector("[data-shot-selector]");
    if (shotSelector) {
      const handler = () => {
        const shotUuid = clean(shotSelector.value);
        if (shotUuid === HMB_PROMPT_ONLY_SHOT_VALUE) {
          state.shot = normalizeShotSelection({});
          hmbCommitLocalPromptStructure(
            container,
            props,
            state,
            remount,
            () => hmbApplyPromptShotFeedback(container, state),
          );
          return;
        }
        if (!shotUuid) return;
        const catalog = hmbPromptVerifiedShotCatalog(state);
        const selected = catalog.find((item) => item.shot_uuid === shotUuid);
        if (!selected) return;
        state.shot = selected;
        hmbCommitLocalPromptStructure(
          container,
          props,
          state,
          remount,
          () => hmbApplyPromptShotFeedback(container, state),
        );
      };
      shotSelector.addEventListener("change", handler);
      listeners.push([shotSelector, "change", handler]);
    }

    const languageButton = container.querySelector("[data-language-toggle]");
    if (languageButton) {
      const handler = (event) => {
        event.preventDefault();
        event.stopPropagation();
        state.ui = state.ui && typeof state.ui === "object" ? state.ui : defaultUi();
        state.ui.language = uiLanguage(state) === "ko" ? "en" : "ko";
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      languageButton.addEventListener("click", handler);
      listeners.push([languageButton, "click", handler]);
    }

    container.querySelectorAll(".add-video-source").forEach((button) => {
      const handler = () => {
        if (!hmbCanAddPromptVideoRow(state)) return;
        const next = defaultVideo((state.videos || []).length + 1);
        next.manual = true;
        state.videos.push(next);
        hmbCommitLocalPromptStructure(container, props, state, remount);
      };
      button.addEventListener("click", handler);
      listeners.push([button, "click", handler]);
    });

    container.querySelectorAll("[data-text-key]").forEach((field) => {
      const key = field.getAttribute("data-text-key");
      const inputHandler = () => {
        state.text[key] = field.value;
        hmbRememberPromptDirtyTextControl(container, field, state);
        hmbScheduleImmediateStateCommit(container, props, state);
      };
      const blurHandler = (event) => {
        state.text[key] = field.value;
        hmbRememberPromptDirtyTextControl(container, field, state);
        hmbFinalizePromptTextBlur(container, event, () => {
          hmbCaptureUiBeforeStateEmit(container, state);
          emit(props, state, container);
          hmbRestoreSourceScroll(container);
        });
      };
      field.addEventListener("input", inputHandler);
      field.addEventListener("blur", blurHandler);
      listeners.push([field, "input", inputHandler]);
      listeners.push([field, "blur", blurHandler]);
    });
    try { container.__hmbPromptLastPaintedValue = JSON.stringify(state); } catch (_e) {}
    return state;
  };
  remount();
  const applyProps = (nextProps = {}) => {
    if (hmbConsumePendingPromptStateEcho(container, nextProps || {})) {
      // Do not replace the live callbacks/state with an older retained-mode
      // payload. Exact current echoes may refresh host callbacks, while stale
      // lower-revision echoes are acknowledgements only.
      if (!container.__hmbPromptLastConsumedEchoWasStale) {
        props = nextProps || {};
      } else {
        props = { ...props, disabled: Boolean(nextProps?.disabled) };
      }
      state.disabled = Boolean(nextProps?.disabled);
      hmbRememberPromptRevisionState(container, state, state.disabled, false);
      container.querySelector?.(".hmb-dashboard")?.classList?.toggle("disabled", state.disabled);
      return;
    }
    hmbInvalidatePromptPublication(container);
    const hadUncommittedText = Boolean(
      container.__hmbPromptLibraryCommitPending
      || container.__hmbPromptLibraryCompositionActive
      || container.__hmbPromptLibraryDirtyText instanceof Map
    );
    if (hadUncommittedText) {
      const activeText = typeof document !== "undefined" ? document.activeElement : null;
      if (activeText && container.contains?.(activeText)) {
        hmbRememberPromptDirtyTextControl(container, activeText, state);
      }
    }
    const dirtyText = hmbPromptDirtyTextEntries(container);
    if (hadUncommittedText) {
      hmbClearImmediateStateCommit(container);
      // The old composing DOM may be replaced below, so explicitly finish that
      // session and arm a fresh trailing commit against the merged state.
      hmbReleasePromptCompositionLatch(container);
    }
    let nextState = hmbMergeStoredGroupHeights(container, parseValue(nextProps?.value));
    if (dirtyText.length) {
      nextState = hmbMergePromptDirtyTextState(nextState, dirtyText);
    }
    nextState.disabled = Boolean(nextProps?.disabled);
    nextState.ui = nextState.ui && typeof nextState.ui === "object" ? nextState.ui : defaultUi();
    hmbReconcilePromptSourceIdentities(state, nextState);
    const currentValue = JSON.stringify(normalizeState(state));
    const nextValue = JSON.stringify(normalizeState(nextState));
    const disabledChanged = Boolean(state.disabled) !== Boolean(nextState.disabled);
    const shotRegionOnly = Boolean(
      !disabledChanged
      && hmbPromptNonShotStateFingerprint(state)
        === hmbPromptNonShotStateFingerprint(nextState)
    );
    props = nextProps || {};
    if (currentValue === nextValue && !disabledChanged) {
      if (dirtyText.length) hmbScheduleImmediateStateCommit(container, props, state);
      return;
    }
    state = nextState;
    hmbRememberPromptRevisionState(container, state, state.disabled, false);
    if (shotRegionOnly) {
      hmbApplyPromptShotFeedback(container, state);
      container.querySelector?.(".hmb-dashboard")?.classList?.toggle(
        "disabled",
        state.disabled,
      );
      try { container.__hmbPromptLastPaintedValue = JSON.stringify(state); } catch (_e) {}
    } else {
      remount();
    }
    if (dirtyText.length) hmbScheduleImmediateStateCommit(container, props, state);
  };
  container.__hmbPromptLibraryApplyProps = applyProps;
  const cleanup = () => {
    disposeLifecycle();
    hmbInvalidatePromptPublication(container);
    try { hmbClearActivePromptResize(container); } catch (_e) {}
    // A real library unload must never publish an in-progress draft. Publishing
    // from cleanup can synchronously re-enter a disposed widget and is the
    // delete/reload freeze that this cancellation path prevents.
    try { hmbClearImmediateStateCommit(container); } catch (_e) {}
    hmbInvalidatePromptPublication(container);
    try { hmbClearPendingPromptStateEchoes(container); } catch (_e) {}
    try { hmbClearPromptDirtyText(container); } catch (_e) {}
    try { container.__hmbPromptLibraryPointerTextTarget = null; } catch (_e) {}
    try { hmbReleasePromptCompositionLatch(container); } catch (_e) {}
    try {
      if (container.__hmbPromptHostResizeTimer) {
        clearTimeout(container.__hmbPromptHostResizeTimer);
      }
      container.__hmbPromptHostResizeTimer = null;
    } catch (_e) {}
    try { container.__hmbFrameRangeDragCleanup?.(); } catch (_e) {}
    try { stopFluidSync && stopFluidSync(); } catch (_e) {}
    for (const [el, event, handler, options] of listeners.splice(0)) {
      try { el.removeEventListener(event, handler, options); } catch (_e) {}
    }
    if (container.__hmbPromptLibraryApplyProps === applyProps) {
      delete container.__hmbPromptLibraryApplyProps;
    }
    if (container.__hmbPromptLibraryCleanup === cleanup) {
      delete container.__hmbPromptLibraryCleanup;
    }
    if (container.__hmbPromptLibraryLifecycle === lifecycle) {
      delete container.__hmbPromptLibraryLifecycle;
    }
    if (container.__hmbPromptLibraryScheduleFrame === scheduleLifecycleFrame) {
      delete container.__hmbPromptLibraryScheduleFrame;
    }
    try {
      delete container.__hmbPromptCurrentUiEditRevision;
      delete container.__hmbPromptLatestLocalUiEditRevision;
      delete container.__hmbPromptCurrentSourceSyncRevision;
      delete container.__hmbPromptCurrentDisabled;
      delete container.__hmbPromptCurrentShotCatalogRouting;
      delete container.__hmbPromptLastPaintedValue;
      delete container.__hmbPromptLastConsumedEchoWasStale;
    } catch (_e) {}
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.innerHTML = "";
  };
  container.__hmbPromptLibraryCleanup = cleanup;
  return {
    cleanup: container.__hmbPromptLibraryCleanupProxy,
    update(nextProps) {
      applyProps(nextProps || {});
    },
  };
}
