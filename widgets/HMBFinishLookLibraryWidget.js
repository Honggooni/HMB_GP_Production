// Module-local opt-in to the host's original React header portals. No SDK calls.
function hmbNativeHeaderTarget(target) {
  return Boolean(target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"));
}
function hmbInstallNativeHeaderBridge(container, nodeType, selector) {
  const previous = container.__hmbUnifiedNativeHeader;
  if (previous?.nodeType === nodeType) { previous.refresh(); return previous; }
  previous?.cleanup();
  const doc = container.ownerDocument, win = doc?.defaultView || globalThis;
  const oldContainerNoDrag = Boolean(container.classList?.contains?.("nodrag"));
  const oldMarker = container.getAttribute?.("data-hmb-color-lut-widget");
  const oldType = container.getAttribute?.("data-hmb-native-node-type");
  const roots = new Map();
  let active = false, disposed = false;
  const noDrag = (element, value) => { if (Boolean(element?.classList?.contains?.("nodrag")) === value) return; if (value) element?.classList?.add?.("nodrag"); else element?.classList?.remove?.("nodrag"); };
  const refresh = () => {
    if (disposed) return;
    const root = container.querySelector?.(selector);
    if (root) {
      if (!roots.has(root)) roots.set(root, Boolean(root.classList?.contains?.("nodrag")));
      const status = active ? "active" : "fallback";
      if (root.getAttribute?.("data-hmb-native-header") !== status) root.setAttribute?.("data-hmb-native-header", status);
      noDrag(root, active ? false : roots.get(root));
    }
    noDrag(container, active ? false : oldContainerNoDrag);
  };
  const announce = phase => {
    if (typeof win.CustomEvent === "function") doc?.dispatchEvent?.(new win.CustomEvent(`hmb-color-lut-header-${phase}`, { detail: { container } }));
  };
  const state = event => {
    if (disposed || event.target !== container) return;
    active = event.detail?.active === true; refresh();
  };
  const bridge = { nodeType, get active() { return active; }, refresh, cleanup() {
    if (disposed) return;
    announce("retire"); disposed = true; active = false;
    container.removeEventListener?.("hmb-color-lut-header-state", state);
    noDrag(container, oldContainerNoDrag);
    for (const [root, old] of roots) { root.removeAttribute?.("data-hmb-native-header"); noDrag(root, old); }
    if (oldMarker === null || oldMarker === undefined) container.removeAttribute?.("data-hmb-color-lut-widget");
    else container.setAttribute?.("data-hmb-color-lut-widget", oldMarker);
    if (oldType === null || oldType === undefined) container.removeAttribute?.("data-hmb-native-node-type");
    else container.setAttribute?.("data-hmb-native-node-type", oldType);
    if (container.__hmbUnifiedNativeHeader === bridge) delete container.__hmbUnifiedNativeHeader;
  } };
  container.setAttribute?.("data-hmb-color-lut-widget", "");
  container.setAttribute?.("data-hmb-native-node-type", nodeType);
  container.addEventListener?.("hmb-color-lut-header-state", state);
  container.__hmbUnifiedNativeHeader = bridge;
  refresh(); announce("ready"); return bridge;
}

export const HMB_FINISH_LOOK_SCHEMA_VERSION = 2;
export const HMB_FINISH_LOOK_WIDGET_SCHEMA_VERSION = 1;
export const HMB_FINISH_LOOK_ONLY_SHOT_VALUE = "__hmb_only__";
export const HMB_JEWEL_NIGHT_SHOT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});
export const HMB_FINISH_LOOK_SHOT_PALETTE = HMB_JEWEL_NIGHT_SHOT_PALETTE;

export const HMB_FINISH_LOOK_NUMBER_RULES = Object.freeze({
  "beauty.soften_shadows": Object.freeze({ min: -1, max: 1, step: 0.01, precision: 2 }),
  "beauty.shadow_threshold": Object.freeze({ min: 0, max: 1, step: 0.01, precision: 2 }),
  "beauty.saturation": Object.freeze({ min: -2, max: 8, step: 0.01, precision: 2 }),
  "beauty.brightness": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.glow_brightness": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.glow_threshold": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.glow_width": Object.freeze({ min: 0, max: null, step: 0.1, precision: 2 }),
  "beauty.soft_focus": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.blur_amount": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.pore_size": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "beauty.reduce_shine": Object.freeze({ min: 0, max: 1, step: 0.01, precision: 2 }),
});

// Discrete UI stops use representative values of the existing compiler contract.
// The transport remains numeric; arbitrary numeric editing is not exposed.
const strengthSteps = (values = [0, 0.05, 0.1, 0.2, 0.4, 0.8]) => steps(values,
  ["끔", "거의 없음", "매우 약함", "약함", "보통", "강함"],
  ["Off", "Almost none", "Very subtle", "Subtle", "Moderate", "Strong"]);
function steps(values, ko, en) {
  return Object.freeze(values.map((value, index) => Object.freeze({ value, ko: ko[index], en: en[index] })));
}
export const HMB_FINISH_LOOK_STEPS = Object.freeze({
  "beauty.soften_shadows": steps([-0.5, -0.1, 0, 0.11, 0.2, 0.5],
    ["그림자 강하게", "그림자 선명하게", "중립", "살짝 부드럽게", "보통 부드럽게", "많이 부드럽게"],
    ["Strong definition", "Moderate definition", "Neutral", "Gently softened", "Moderately softened", "Strongly softened"]),
  "beauty.shadow_threshold": steps([0.1, 0.27, 0.6], ["낮음", "보통", "넓은 범위"], ["Low", "Moderate", "Broad range"]),
  "beauty.saturation": steps([-1.5, -0.8, -0.2, 0, 0.8, 0.95, 1, 1.05, 1.2],
    ["강한 색 반전", "색 반전", "약한 색 반전", "흑백", "채도 감소", "채도 약간 감소", "중립", "채도 약간 증가", "채도 증가"],
    ["Strong inverted chroma", "Inverted chroma", "Subtle inverted chroma", "Monochrome", "Reduced saturation", "Slightly reduced", "Neutral", "Slightly increased", "Increased saturation"]),
  "beauty.brightness": steps([0.5, 0.8, 1, 1.2, 1.5], ["많이 어둡게", "어둡게", "중립", "밝게", "많이 밝게"], ["Much darker", "Darker", "Neutral", "Brighter", "Much brighter"]),
  "beauty.glow_brightness": strengthSteps(),
  "beauty.glow_threshold": steps([0, 0.2, 0.5, 0.8], ["검정 외 전체", "낮음", "보통", "높음"], ["All non-black areas", "Low", "Moderate", "High"]),
  "beauty.glow_width": steps([0, 8, 16, 32, 64], ["최소", "좁게", "기본", "넓게", "매우 넓게"], ["Minimum", "Narrow", "Default", "Wide", "Very wide"]),
  "beauty.soft_focus": strengthSteps(),
  "beauty.blur_amount": strengthSteps(),
  "beauty.pore_size": steps([0, 0.05, 0.1, 0.2, 0.4, 0.8], ["끔", "아주 작은 결", "작은 결", "보통 결", "큰 결", "아주 큰 결"], ["Off", "Very fine texture", "Fine texture", "Medium texture", "Coarse texture", "Very coarse texture"]),
  "beauty.reduce_shine": strengthSteps(),
});

export function hmbFinishLookStepIndex(path, value) {
  const options = HMB_FINISH_LOOK_STEPS[path];
  if (!options) return -1;
  return options.reduce((best, option, index) => (
    Math.abs(option.value - Number(value)) < Math.abs(options[best].value - Number(value)) ? index : best
  ), 0);
}

export function hmbFinishLookStepValue(path, index) {
  if (String(index).trim() === "") return null;
  const number = Number(index);
  return Number.isInteger(number) ? HMB_FINISH_LOOK_STEPS[path]?.[number]?.value ?? null : null;
}

const HMB_TEXT = Object.freeze({
  en: Object.freeze({
    subtitle: "Character Beauty",
    language: "Language",
    shot: "SHOT",
    only: "Only",
    bound: "BOUND",
    beauty: "CHARACTER BEAUTY",
    enable: "Enable",
    primary: "PRIMARY CONTROLS",
    advanced: "ADVANCED",
    softenShadows: "Soften Shadows",
    shadowThreshold: "Shadow Threshold",
    saturation: "Saturation",
    brightness: "Brightness",
    glowBrightness: "Glow Brightness",
    glowThreshold: "Glow Threshold",
    glowWidth: "Glow Width",
    softFocus: "Soft Focus",
    blurAmount: "Blur Amount",
    poreSize: "Pore Size",
    reduceShine: "Reduce Shine",
    ready: "Ready",
  }),
  ko: Object.freeze({
    subtitle: "캐릭터 뷰티",
    language: "언어",
    shot: "SHOT",
    only: "Only",
    bound: "BOUND",
    beauty: "캐릭터 뷰티",
    enable: "사용",
    primary: "기본 조절",
    advanced: "고급 조절",
    softenShadows: "그림자 부드럽게",
    shadowThreshold: "그림자 임계값",
    saturation: "채도",
    brightness: "밝기",
    glowBrightness: "글로우 밝기",
    glowThreshold: "글로우 임계값",
    glowWidth: "글로우 폭",
    softFocus: "소프트 포커스",
    blurAmount: "블러 양",
    poreSize: "모공 크기",
    reduceShine: "광택 감소",
    ready: "준비됨",
  }),
});

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
          if (rootToken.test(cleanSelector) || cleanSelector.includes(":root")) {
            return cleanSelector.replaceAll(":root", root);
          }
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
  return String(markup || "").replace(
    /<style>([\s\S]*?)<\/style>/g,
    (_match, css) => `<style>${hmbScopeWidgetCss(css, rootSelector)}</style>`,
  );
}

function hmbRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function hmbRawWidgetValue(input) {
  const wrapper = hmbRecord(input);
  const wrapperShotCatalog = hmbRecord(wrapper.shot_catalog);
  const wrapperShot = hmbRecord(wrapper.shot);
  let value = input;
  if (wrapper === input && (
    Object.prototype.hasOwnProperty.call(wrapper, "value")
    || Object.prototype.hasOwnProperty.call(wrapper, "parameterValue")
    || Object.prototype.hasOwnProperty.call(wrapper, "defaultValue")
  )) value = wrapper.value ?? wrapper.parameterValue ?? wrapper.defaultValue;
  if (typeof value === "string") {
    try { value = JSON.parse(value); } catch (_error) { value = {}; }
  }
  const unwrapped = hmbRecord(value);
  let merged = unwrapped;
  if (
    !Object.keys(hmbRecord(unwrapped.shot_catalog)).length
    && Object.keys(wrapperShotCatalog).length
  ) merged = { ...merged, shot_catalog: wrapperShotCatalog };
  if (
    !Object.keys(hmbRecord(unwrapped.shot)).length
    && Object.keys(wrapperShot).length
  ) merged = { ...merged, shot: wrapperShot };
  if (
    typeof unwrapped.remote_connected !== "boolean"
    && typeof wrapper.remote_connected === "boolean"
  ) merged = { ...merged, remote_connected: wrapper.remote_connected };
  return merged;
}

function hmbFinishLookOnlyShot() {
  return { channel_uuid: "", shot_uuid: "", number: 1, name: "Only" };
}

export function hmbNormalizeFinishLookShotCatalog(value) {
  const source = hmbRecord(value);
  const publisher = String(source.publisher_instance_uuid || "").trim().slice(0, 128);
  const channel = String(source.channel_uuid || "").trim().slice(0, 128);
  const generation = Number(source.generation);
  const metadataSha256 = String(source.metadata_sha256 || "").trim().toLowerCase();
  if (
    source.schema !== "hmb-shot-routing-catalog"
    || source.version !== 1
    || !publisher
    || !channel
    || !Number.isSafeInteger(generation)
    || generation < 1
    || !/^[0-9a-f]{64}$/.test(metadataSha256)
    || !Array.isArray(source.shots)
    || source.shots.length < 1
    || source.shots.length > 5
  ) return {};
  const shotIds = new Set();
  const shotNumbers = new Set();
  const shots = [];
  for (const rawValue of source.shots) {
    const raw = hmbRecord(rawValue);
    const shotUuid = String(raw.shot_uuid || "").trim().slice(0, 128);
    const number = Number(raw.number);
    const name = String(raw.name || "").trim().replace(/\s+/g, " ").slice(0, 128);
    const revision = Number(raw.revision);
    if (
      !shotUuid
      || shotIds.has(shotUuid)
      || !Number.isInteger(number)
      || number < 1
      || number > 5
      || shotNumbers.has(number)
      || !name
      || !Number.isSafeInteger(revision)
      || revision < 0
    ) return {};
    shotIds.add(shotUuid);
    shotNumbers.add(number);
    shots.push({ shot_uuid: shotUuid, number, name, revision });
  }
  shots.sort((left, right) => left.number - right.number || left.shot_uuid.localeCompare(right.shot_uuid));
  return {
    schema: "hmb-shot-routing-catalog",
    version: 1,
    publisher_instance_uuid: publisher,
    channel_uuid: channel,
    generation,
    metadata_sha256: metadataSha256,
    shots,
  };
}

export function hmbNormalizeFinishLookShotSelection(value, catalogValue = {}) {
  const source = hmbRecord(value);
  const channelUuid = String(source.channel_uuid || "").trim().slice(0, 128);
  const shotUuid = String(source.shot_uuid || "").trim().slice(0, 128);
  if (!channelUuid || !shotUuid) return hmbFinishLookOnlyShot();
  const catalog = hmbNormalizeFinishLookShotCatalog(catalogValue);
  if (catalog.channel_uuid && catalog.channel_uuid !== channelUuid) return hmbFinishLookOnlyShot();
  const selected = (catalog.shots || []).find((shot) => shot.shot_uuid === shotUuid) || null;
  if (catalog.channel_uuid && !selected) return hmbFinishLookOnlyShot();
  const numericNumber = Number(source.number);
  const number = selected?.number
    || (Number.isInteger(numericNumber) ? Math.max(1, Math.min(5, numericNumber)) : 1);
  const fallbackName = `Shot ${number}`;
  const name = selected?.name
    || String(source.name || fallbackName).trim().replace(/\s+/g, " ").slice(0, 128)
    || fallbackName;
  return { channel_uuid: channelUuid, shot_uuid: shotUuid, number, name };
}

function hmbFinishLookBoundShot(state) {
  const catalog = hmbNormalizeFinishLookShotCatalog(state?.shot_catalog);
  const current = hmbNormalizeFinishLookShotSelection(state?.shot, catalog);
  if (!catalog.channel_uuid || current.channel_uuid !== catalog.channel_uuid) return null;
  return (catalog.shots || []).find((shot) => (
    shot.shot_uuid === current.shot_uuid && shot.number === current.number
  )) || null;
}

export function hmbFinishLookShotOptions(state) {
  const catalog = hmbNormalizeFinishLookShotCatalog(state?.shot_catalog);
  const selected = hmbFinishLookBoundShot(state);
  const options = [{
    key: HMB_FINISH_LOOK_ONLY_SHOT_VALUE,
    channel_uuid: "",
    shot_uuid: "",
    number: 0,
    name: "Only",
    revision: 0,
    selected: !selected,
    only: true,
  }];
  for (const shot of catalog.shots || []) {
    options.push({
      key: `${catalog.channel_uuid}\u001f${shot.shot_uuid}`,
      channel_uuid: catalog.channel_uuid,
      ...shot,
      selected: shot.shot_uuid === selected?.shot_uuid,
      only: false,
    });
  }
  return options;
}

export function hmbFinishLookPaletteShotNumber(state) {
  return hmbFinishLookBoundShot(state)?.number || 0;
}

export function hmbFinishLookShotAccent(state) {
  return HMB_JEWEL_NIGHT_SHOT_PALETTE[hmbFinishLookPaletteShotNumber(state)] || "#64748B";
}

function hmbBoolean(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

function hmbFiniteNumber(value, fallback, min = null, max = null) {
  if (typeof value === "boolean" || value === null || value === "") return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  if (min !== null && number < min) return fallback;
  if (max !== null && number > max) return fallback;
  return number;
}

function hmbInteger(value, fallback, min = 0, max = null) {
  const number = hmbFiniteNumber(value, fallback, min, max);
  return Number.isInteger(number) ? number : fallback;
}

function hmbPath(value) {
  return String(value ?? "").slice(0, 4096);
}

function hmbLanguage(value) {
  return String(value ?? "").trim().toLowerCase() === "en" ? "en" : "ko";
}

function hmbDefaultFinishLook() {
  return {
    schema_version: HMB_FINISH_LOOK_SCHEMA_VERSION,
    beauty: {
      enabled: false,
      soften_shadows: 0.11,
      shadow_threshold: 0.27,
      saturation: 1,
      brightness: 1,
      glow_brightness: 0,
      glow_threshold: 0.2,
      glow_width: 16,
      soft_focus: 0,
      blur_amount: 0,
      pore_size: 0,
      reduce_shine: 0,
    },
  };
}

function hmbNormalizeFinishNumber(group, key, value, fallback) {
  const rule = HMB_FINISH_LOOK_NUMBER_RULES[`${group}.${key}`];
  if (rule?.integer) return hmbInteger(value, fallback, rule.min ?? 0, rule.max ?? null);
  return hmbFiniteNumber(value, fallback, rule?.min ?? null, rule?.max ?? null);
}

export function hmbNormalizeFinishLookWidgetValue(input = {}) {
  const source = hmbRawWidgetValue(input);
  const shotCatalog = hmbNormalizeFinishLookShotCatalog(source.shot_catalog);
  const shot = hmbNormalizeFinishLookShotSelection(source.shot, shotCatalog);
  const rawFinish = Object.keys(hmbRecord(source.finish_look)).length
    ? hmbRecord(source.finish_look)
    : (source.beauty ? source : {});
  const defaults = hmbDefaultFinishLook();
  const rawBeauty = hmbRecord(rawFinish.beauty);
  const beauty = { enabled: hmbBoolean(rawBeauty.enabled, defaults.beauty.enabled) };
  for (const [key, fallback] of Object.entries(defaults.beauty)) {
    if (key !== "enabled") beauty[key] = hmbNormalizeFinishNumber("beauty", key, rawBeauty[key], fallback);
  }
  const normalized = {
    schema_version: HMB_FINISH_LOOK_WIDGET_SCHEMA_VERSION,
    language: hmbLanguage(source.language),
    remote_connected: hmbBoolean(source.remote_connected, false),
    shot_catalog: shotCatalog,
    shot,
    finish_look: {
      schema_version: HMB_FINISH_LOOK_SCHEMA_VERSION,
      beauty,
    },
    shot_manager: source.shot_manager !== false,
    shot_editor_expanded: source.shot_editor_expanded !== false,
    shot_documents: Object.fromEntries(Object.entries(hmbRecord(source.shot_documents)).slice(0,5).map(([key,value])=>[key,hmbNormalizeFinishLookWidgetValue({finish_look:value}).finish_look])),
  };
  return normalized;
}

export function hmbFinishLookPublication(input) {
  return hmbNormalizeFinishLookWidgetValue(input);
}

export function hmbFinishLookUITransport(input) {
  const value=hmbRecord(hmbRawWidgetValue(input).ui_transport);
  const statuses=new Set(["state","accepted","refreshed","duplicate","conflict","stale_session","stale_client","stale_sequence","target_unavailable","remote_locked","invalid_command"]);
  if(value.schema!=="hmb-finish-ui-transport" || value.version!==1 || typeof value.session_id!=="string" || !value.session_id || value.session_id.length>128
    || !Number.isSafeInteger(value.revision) || value.revision<1 || !statuses.has(value.status)
    || !Number.isSafeInteger(value.sequence) || value.sequence<0
    || ["client_id","client_epoch","request_id"].some(key=>typeof value[key]!=="string" || value[key].length>128))return null;
  const targets=hmbRecord(value.target_revisions);
  if(Object.keys(targets).length>6 || Object.entries(targets).some(([key,revision])=>!key || key.length>257 || !Number.isSafeInteger(revision) || revision<0 || revision>value.revision))return null;
  return {...value,target_revisions:{...targets}};
}

export function hmbFinishLookLabels(language) {
  return HMB_TEXT[hmbLanguage(language)];
}

export function hmbValidateFinishLookNumber(path, rawValue) {
  const rule = HMB_FINISH_LOOK_NUMBER_RULES[path];
  if (!rule) return { ok: false, error: `Unknown numeric field: ${path}` };
  if (typeof rawValue === "boolean" || String(rawValue ?? "").trim() === "") {
    return { ok: false, error: "A numeric value is required." };
  }
  const value = Number(rawValue);
  if (!Number.isFinite(value)) return { ok: false, error: "The value must be finite." };
  if (rule.integer && !Number.isInteger(value)) {
    return { ok: false, error: "The value must be an integer." };
  }
  if (rule.min !== null && value < rule.min) {
    return { ok: false, error: `The value must be at least ${rule.min}.` };
  }
  if (rule.max !== null && value > rule.max) {
    return { ok: false, error: `The value must be at most ${rule.max}.` };
  }
  return { ok: true, value };
}

function hmbEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

function hmbUiNumber(value, precision) {
  return Number(value).toFixed(precision);
}

function hmbSelectOptions(options, current, labels = {}) {
  return options.map((value) => (
    `<option value="${hmbEscape(value)}"${value === current ? " selected" : ""}>`
    + `${hmbEscape(labels[value] || value)}</option>`
  )).join("");
}

export function hmbFinishLookShotOptionLabel(item) {
  return item?.only
    ? "Only"
    : `${String(item?.number || 1).padStart(2, "0")} · ${item?.name || `Shot ${item?.number || 1}`}`;
}

function hmbFinishLookShotOptionsMarkup(state) {
  return hmbFinishLookShotOptions(state).map((item) => (
    `<option value="${hmbEscape(item.key)}"${item.only ? "" : ` data-shot-number="${item.number}"`}${item.selected ? " selected" : ""}>${hmbEscape(hmbFinishLookShotOptionLabel(item))}</option>`
  )).join("");
}

function hmbFinishLookShotOptionNodes(select) {
  const direct = Array.from(select?.options || []);
  return direct.length ? direct : Array.from(select?.querySelectorAll?.("option") || []);
}

export function hmbSyncFinishLookShotSelect(select, state) {
  if (!select) return false;
  const desired = hmbFinishLookShotOptions(state);
  const existingNodes = hmbFinishLookShotOptionNodes(select);
  const existing = new Map(existingNodes.map((option) => [String(option?.value || ""), option]));
  const ownerDocument = select.ownerDocument
    || (typeof document !== "undefined" ? document : null);
  let changed = existingNodes.length !== desired.length;
  const retained = new Set();
  for (const [desiredIndex, item] of desired.entries()) {
    const label = hmbFinishLookShotOptionLabel(item);
    let option = existing.get(item.key) || null;
    if (!option && ownerDocument?.createElement) {
      option = ownerDocument.createElement("option");
      changed = true;
    }
    if (!option) {
      select.innerHTML = hmbFinishLookShotOptionsMarkup(state);
      option = null;
      changed = true;
      break;
    }
    retained.add(item.key);
    if (String(option.value || "") !== item.key) { option.value = item.key; changed = true; }
    if (String(option.textContent ?? option.text ?? "") !== label) {
      option.textContent = label;
      changed = true;
    }
    option.selected = Boolean(item.selected);
    option.setAttribute?.("value", item.key);
    if (item.only) option.removeAttribute?.("data-shot-number");
    else option.setAttribute?.("data-shot-number", String(item.number));
    const ordered = hmbFinishLookShotOptionNodes(select);
    const currentAtIndex = ordered[desiredIndex] || null;
    if (currentAtIndex !== option) {
      if (typeof select.insertBefore === "function") select.insertBefore(option, currentAtIndex);
      else if (typeof select.appendChild === "function") select.appendChild(option);
      changed = true;
    }
  }
  existing.forEach((option, value) => {
    if (!retained.has(value)) { option.remove?.(); changed = true; }
  });
  const selected = desired.find((item) => item.selected) || desired[0];
  const selectedValue = selected?.key || HMB_FINISH_LOOK_ONLY_SHOT_VALUE;
  if (String(select.value || "") !== selectedValue) {
    select.value = selectedValue;
    changed = true;
  }
  const disabled = desired.length <= 1;
  if (Boolean(select.disabled) !== disabled) changed = true;
  select.disabled = disabled;
  if (disabled) select.setAttribute?.("disabled", "");
  else select.removeAttribute?.("disabled");
  return changed;
}

export function hmbApplyFinishLookShotFeedback(container, state) {
  const root = container?.querySelector?.(".hmb-finish-look");
  if (!root) return false;
  const shotNumber = hmbFinishLookPaletteShotNumber(state);
  const bound = shotNumber > 0;
  root.setAttribute?.("data-shot-number", String(shotNumber));
  root.setAttribute?.("data-shot-bound", bound ? "true" : "false");
  hmbSyncFinishLookShotSelect(root.querySelector?.("[data-shot-selector]"), state);
  const badge = root.querySelector?.("[data-shot-bound-badge]");
  if (badge) {
    if (bound) badge.removeAttribute?.("hidden");
    else badge.setAttribute?.("hidden", "");
  }
  return true;
}

export function hmbFinishLookNonShotStateFingerprint(input) {
  const normalized = hmbNormalizeFinishLookWidgetValue(input || {});
  const { shot_catalog: _shotCatalog, shot: _shot, ...rest } = normalized;
  return JSON.stringify(rest);
}

export function hmbFinishLookStepLabel(path, value, language = "ko") {
  const option = HMB_FINISH_LOOK_STEPS[path][hmbFinishLookStepIndex(path, value)];
  const text = option[language === "ko" ? "ko" : "en"];
  // Do not silently quantize an existing saved/remote setting just by viewing it.
  return option.value === Number(value) ? text : `${language === "ko" ? "기존 설정 ≈" : "Existing setting ≈"} ${text}`;
}

export function hmbFinishLookFieldEnabled(state, path) {
  if (!Object.hasOwn(HMB_FINISH_LOOK_STEPS, path) || state.remote_connected) return false;
  const beauty = state.finish_look?.beauty;
  if (!beauty?.enabled) return false;
  if (["beauty.glow_threshold", "beauty.glow_width"].includes(path)) {
    return Number(beauty.glow_brightness) > 0;
  }
  if (path === "beauty.shadow_threshold") return Number(beauty.soften_shadows) !== 0;
  return true;
}

export function hmbApplyFinishLookControlAvailability(container, state) {
  for (const input of container.querySelectorAll?.("[data-finish-step]") || []) {
    const disabled = !hmbFinishLookFieldEnabled(state, input.getAttribute("data-finish-step"));
    if (input.disabled !== disabled) input.disabled = disabled;
  }
}

function hmbApplyFinishLookActiveEditor(container, state) {
  const root=container.querySelector?.(".hmb-finish-look");
  if(!root)return false;
  const attribute=(element,name,value)=>{if(element?.getAttribute(name)!==String(value))element?.setAttribute(name,String(value));};
  attribute(root,"data-shot-number",hmbFinishLookPaletteShotNumber(state));
  attribute(root,"data-shot-bound",Boolean(state.shot.shot_uuid));
  for(const button of container.querySelectorAll?.("[data-finish-shot]") || []){
    const selected=button.getAttribute("data-finish-shot")===state.shot.shot_uuid;
    attribute(button,"aria-pressed",selected);attribute(button,"aria-expanded",selected);
  }
  const toggle=container.querySelector?.('[data-enable="beauty"]');
  if(toggle){if(toggle.checked!==state.finish_look.beauty.enabled)toggle.checked=state.finish_look.beauty.enabled;if(toggle.disabled!==state.remote_connected)toggle.disabled=state.remote_connected;}
  for(const input of container.querySelectorAll?.("[data-finish-step]") || []){
    const path=input.getAttribute("data-finish-step"),value=hmbGetPath(state.finish_look,path);
    const index=String(hmbFinishLookStepIndex(path,value));if(input.value!==index)input.value=index;
    const text=hmbFinishLookStepLabel(path,value,state.language);attribute(input,"aria-valuetext",text);
    const output=container.querySelector?.(`[data-step-label="${path}"]`);if(output && output.textContent!==text)output.textContent=text;
  }
  hmbApplyFinishLookControlAvailability(container,state);
  return true;
}

function hmbStepField(path, label, value, disabled, language) {
  const options = HMB_FINISH_LOOK_STEPS[path];
  const index = hmbFinishLookStepIndex(path, value);
  const text = hmbFinishLookStepLabel(path, value, language);
  const lang = language === "ko" ? "ko" : "en";
  return `<label class="hmb-finish-look__field"><span>${hmbEscape(label)}</span><output data-step-label="${hmbEscape(path)}">${hmbEscape(text)}</output><input type="range" data-finish-step="${hmbEscape(path)}" value="${index}" min="0" max="${options.length - 1}" step="1" aria-label="${hmbEscape(label)}" aria-valuetext="${hmbEscape(text)}"${disabled ? " disabled" : ""}><span class="hmb-finish-look__step-ends" aria-hidden="true"><small>${hmbEscape(options[0][lang])}</small><small>${hmbEscape(options.at(-1)[lang])}</small></span></label>`;
}

function hmbRenderFinishLook(state) {
  const t = hmbFinishLookLabels(state.language);
  const beauty = state.finish_look.beauty;
  const remoteLocked = state.remote_connected;
  const paletteShotNumber = hmbFinishLookPaletteShotNumber(state);
  const shotBound = paletteShotNumber > 0;
  const shotOptions = hmbFinishLookShotOptions(state);
  const managed = state.shot_manager && Boolean(state.shot_catalog.channel_uuid);
  const tabs = managed ? (state.shot_catalog.shots || []).map(shot=>`<div class="hmb-finish-look__shot-tab" data-finish-shot-row="${hmbEscape(shot.shot_uuid)}" data-shot-number="${shot.number}"><button type="button" data-finish-shot="${hmbEscape(shot.shot_uuid)}" aria-pressed="${state.shot.shot_uuid===shot.shot_uuid}" aria-expanded="${state.shot.shot_uuid===shot.shot_uuid}" title="${hmbEscape(shot.name)}"><span>${String(shot.number).padStart(2,"0")}</span><b>${hmbEscape(shot.name)}</b></button></div>`).join("") : "";
  const beautyDisabled = !beauty.enabled || remoteLocked;
  const hmbNumericField = (path, label, value, disabled) => hmbStepField(
    path, label, value, disabled || !hmbFinishLookFieldEnabled(state, path), state.language,
  );
  const headerMark = "FL";
  const headerTitle = "HMB Finish Look";
  const headerSubtitle = t.subtitle;
  return `
    <style>
      .hmb-finish-look :is(button,input,select,textarea):not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){font-family:inherit}
      .hmb-finish-look__field output{color:var(--hmb-shot-soft);font-size:11px;font-weight:750;min-height:16px;overflow-wrap:anywhere}.hmb-finish-look__field input[type="range"]{width:100%;height:26px;margin:0;cursor:ew-resize;accent-color:var(--hmb-shot-accent);touch-action:pan-y}.hmb-finish-look__field .hmb-finish-look__step-ends{display:flex;justify-content:space-between;gap:8px;color:var(--hmb-muted);font-size:8px}.hmb-finish-look__step-ends small:last-child{text-align:right}.hmb-finish-look__field:has(input:disabled) output{opacity:.42}
      .hmb-finish-look{--jewel-pink:#F472B6;--jewel-blue:#3B82F6;--jewel-green:#10B981;--jewel-purple:#8B5CF6;--jewel-yellow:#EAB308;--hmb-bg:#090c16;--hmb-panel:#0f1726;--hmb-panel-2:#111c2d;--hmb-line:#263b58;--hmb-text:#e8eef7;--hmb-muted:#91a2b7;--hmb-accent:#3B82F6;--hmb-soft:#DBEAFE;position:relative;width:100%;height:100%;min-height:720px;overflow:hidden;container-type:inline-size;border:1px solid rgba(59,130,246,.52);border-radius:11px;background:radial-gradient(circle at 8% -24%,rgba(59,130,246,.2),transparent 42%),linear-gradient(180deg,#0b1020,var(--hmb-bg));color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;box-sizing:border-box;user-select:none}
      .hmb-finish-look *:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){box-sizing:border-box;min-width:0}.hmb-finish-look [hidden]{display:none!important}.hmb-finish-look__scroll{height:100%;min-height:720px;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-bottom:12px}.hmb-finish-look[data-dropdown-open="true"] .hmb-finish-look__scroll{padding-bottom:230px}
      .hmb-finish-look__topbar{position:sticky;z-index:30;top:0;display:flex;align-items:center;height:68px;min-height:68px;gap:16px;padding:0 16px;border-bottom:1px solid rgba(59,130,246,.35);background:linear-gradient(90deg,rgba(30,58,96,.98),rgba(9,12,22,.98))}.hmb-finish-look__mark{flex:0 0 30px;width:30px;height:30px;display:grid;place-items:center;border:1px solid rgba(59,130,246,.65);border-radius:8px;background:rgba(59,130,246,.13);color:#93c5fd;font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-finish-look__heading{display:flex;flex:1 1 auto;flex-direction:column;gap:2px;overflow:hidden}.hmb-finish-look__heading b,.hmb-finish-look__heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-finish-look__heading b{font-size:15px}.hmb-finish-look__heading span{color:var(--hmb-muted);font-size:9px}.hmb-finish-look__remote-badge{padding:4px 7px;border:1px solid rgba(244,114,182,.65);border-radius:999px;background:rgba(190,24,93,.25);color:#fbcfe8;font-size:8px;font-weight:950;letter-spacing:.12em}.hmb-finish-look__language{height:30px;min-width:58px;padding:0 10px;border:1px solid rgba(96,165,250,.55);border-radius:7px;background:#101a2a;color:#bfdbfe;font-size:12px;font-weight:800;cursor:pointer}
      .hmb-finish-look__content{display:grid;grid-template-columns:minmax(0,1fr);gap:9px;padding:10px}.hmb-finish-look__section{border:1px solid rgba(59,130,246,.28);border-radius:9px;background:rgba(15,23,38,.9);overflow:visible}.hmb-finish-look__section-header{display:flex;align-items:center;gap:8px;min-height:39px;padding:7px 10px;border-bottom:1px solid rgba(148,163,184,.13);background:linear-gradient(90deg,rgba(59,130,246,.13),transparent)}.hmb-finish-look__section-header h2{flex:1;margin:0;color:#dbeafe;font-size:12px;letter-spacing:.055em}.hmb-finish-look__enable{display:flex;align-items:center;gap:6px;color:#cbd5e1;font-size:10px;cursor:pointer}.hmb-finish-look__enable input{accent-color:var(--hmb-accent)}.hmb-finish-look__section-body{padding:9px}.hmb-finish-look__subhead{margin:8px 0 6px;color:#7fb4f0;font-size:9px;font-weight:900;letter-spacing:.1em}.hmb-finish-look__subhead:first-child{margin-top:0}.hmb-finish-look__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.hmb-finish-look__field{display:flex;flex-direction:column;gap:4px}.hmb-finish-look__field--wide{grid-column:1/-1}.hmb-finish-look__field>span{color:#b7c5d6;font-size:9px;font-weight:750}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)),.hmb-finish-look select:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)),.hmb-finish-look button:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){font:inherit}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *))[type="number"],.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *))[type="text"],.hmb-finish-look select:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){width:100%;height:30px;padding:0 8px;border:1px solid rgba(148,163,184,.28);border-radius:6px;outline:none;background:#080f1b;color:#e5edf7;font-size:10px}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus,.hmb-finish-look select:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus,.hmb-finish-look button:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus-visible{border-color:#60a5fa;outline:none;box-shadow:0 0 0 1px rgba(96,165,250,.5)}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):disabled,.hmb-finish-look select:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):disabled,.hmb-finish-look button:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):disabled{opacity:.42;cursor:not-allowed}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *))[aria-invalid="true"]{border-color:#fb7185}
      .hmb-finish-look__status{min-height:28px;margin:8px 10px 10px;padding:6px 9px;border:1px solid rgba(148,163,184,.16);border-radius:7px;background:#0a111d;color:#93a4b8;font-size:9px}.hmb-finish-look__status[data-tone="error"]{border-color:rgba(251,113,133,.48);color:#fda4af}.hmb-finish-look__status[data-tone="success"]{border-color:rgba(52,211,153,.4);color:#6ee7b7}
      .hmb-finish-look{--hmb-shot-accent:#64748B;--hmb-shot-rgb:100,116,139;--hmb-shot-deep:#334155;--hmb-shot-soft:#CBD5E1;--hmb-shot-line:rgba(100,116,139,.4);--hmb-shot-glow:rgba(100,116,139,.08);--hmb-accent:var(--hmb-shot-accent);--hmb-soft:var(--hmb-shot-soft);border-color:var(--hmb-shot-line);background:radial-gradient(circle at 8% -24%,var(--hmb-shot-glow),transparent 42%),linear-gradient(180deg,#0b1020,var(--hmb-bg));box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24),0 0 18px var(--hmb-shot-glow)}.hmb-finish-look[data-shot-number="1"]{--hmb-shot-accent:#F472B6;--hmb-shot-rgb:244,114,182;--hmb-shot-deep:#BE185D;--hmb-shot-soft:#FBCFE8;--hmb-shot-line:rgba(244,114,182,.5);--hmb-shot-glow:rgba(244,114,182,.2)}.hmb-finish-look[data-shot-number="2"]{--hmb-shot-accent:#3B82F6;--hmb-shot-rgb:59,130,246;--hmb-shot-deep:#1D4ED8;--hmb-shot-soft:#DBEAFE;--hmb-shot-line:rgba(59,130,246,.5);--hmb-shot-glow:rgba(59,130,246,.2)}.hmb-finish-look[data-shot-number="3"]{--hmb-shot-accent:#10B981;--hmb-shot-rgb:16,185,129;--hmb-shot-deep:#047857;--hmb-shot-soft:#D1FAE5;--hmb-shot-line:rgba(16,185,129,.5);--hmb-shot-glow:rgba(16,185,129,.2)}.hmb-finish-look[data-shot-number="4"]{--hmb-shot-accent:#8B5CF6;--hmb-shot-rgb:139,92,246;--hmb-shot-deep:#6D28D9;--hmb-shot-soft:#EDE9FE;--hmb-shot-line:rgba(139,92,246,.5);--hmb-shot-glow:rgba(139,92,246,.2)}.hmb-finish-look[data-shot-number="5"]{--hmb-shot-accent:#EAB308;--hmb-shot-rgb:234,179,8;--hmb-shot-deep:#A16207;--hmb-shot-soft:#FEF3C7;--hmb-shot-line:rgba(234,179,8,.5);--hmb-shot-glow:rgba(234,179,8,.2)}
      .hmb-finish-look__topbar{border-bottom-color:var(--hmb-shot-line);background:linear-gradient(90deg,rgba(var(--hmb-shot-rgb),.2),rgba(9,12,22,.98))}.hmb-finish-look__mark{border-color:var(--hmb-shot-line);background:rgba(var(--hmb-shot-rgb),.13);color:var(--hmb-shot-soft);box-shadow:0 0 12px var(--hmb-shot-glow)}.hmb-finish-look__section{border-color:rgba(var(--hmb-shot-rgb),.28)}.hmb-finish-look__section-header{background:linear-gradient(90deg,rgba(var(--hmb-shot-rgb),.13),transparent)}.hmb-finish-look__section-header h2,.hmb-finish-look__subhead{color:var(--hmb-shot-soft)}.hmb-finish-look input:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus,.hmb-finish-look select:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus,.hmb-finish-look button:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)):focus-visible{border-color:var(--hmb-shot-accent);box-shadow:0 0 0 1px var(--hmb-shot-line)}.hmb-finish-look__tab.is-active{border-color:var(--hmb-shot-accent);background:rgba(var(--hmb-shot-rgb),.2);color:var(--hmb-shot-soft)}.hmb-finish-look__actions .is-primary{border-color:var(--hmb-shot-accent);background:rgba(var(--hmb-shot-rgb),.22)}
      .hmb-finish-look__shot-shell{flex:0 1 210px;width:210px;min-width:120px;max-width:210px;display:flex;align-items:center;gap:7px}.hmb-finish-look__shot-shell>span{flex:0 0 auto;color:var(--hmb-muted);font-size:8px;font-weight:900;letter-spacing:.12em}.hmb-finish-look__shot-select{width:100%;height:44px;padding:0 10px;border:1px solid var(--hmb-shot-line);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(var(--hmb-shot-rgb),.14),rgba(8,15,27,.96));color:var(--hmb-shot-soft);box-shadow:0 0 10px var(--hmb-shot-glow);font-size:13px;font-weight:800;line-height:normal}.hmb-finish-look__shot-select option{background:#0b1020;color:#e8eef7}.hmb-finish-look__shot-select:disabled{border-color:rgba(100,116,139,.28);background:#0b111c;color:#7c8a9d;box-shadow:none;opacity:.78}.hmb-finish-look__bound-badge,.hmb-finish-look__remote-badge{padding:4px 7px;border-radius:999px;font-size:8px;font-weight:950;letter-spacing:.12em;white-space:nowrap}.hmb-finish-look__bound-badge{border:1px solid var(--hmb-shot-line);background:rgba(var(--hmb-shot-rgb),.2);color:var(--hmb-shot-soft);box-shadow:0 0 10px var(--hmb-shot-glow)}.hmb-finish-look__language{border-color:var(--hmb-shot-line);color:var(--hmb-shot-soft)}
      .hmb-finish-look{--hmb-mode-rgb:var(--hmb-shot-rgb);--hmb-mode-soft:var(--hmb-shot-soft);border-color:rgba(var(--hmb-mode-rgb),.5)}.hmb-finish-look__topbar{border-bottom-color:rgba(var(--hmb-mode-rgb),.48);background:linear-gradient(90deg,rgba(var(--hmb-mode-rgb),.24),rgba(9,12,22,.98));cursor:default}.hmb-finish-look__mark{border-color:rgba(var(--hmb-mode-rgb),.62);background:rgba(var(--hmb-mode-rgb),.15);color:var(--hmb-mode-soft)}.hmb-finish-look__heading b{font-weight:800}.hmb-finish-look__heading em{margin-top:1px;color:rgba(var(--hmb-mode-rgb),.82);font-size:8px;font-style:normal;font-weight:750}
      @container(max-width:780px){.hmb-finish-look__heading span{display:none}.hmb-finish-look__shot-shell{flex-basis:210px;width:210px}.hmb-finish-look__bound-badge,.hmb-finish-look__remote-badge{padding-inline:5px;font-size:7px}}@container(max-width:680px){.hmb-finish-look__content{grid-template-columns:1fr}.hmb-finish-look__topbar{gap:9px;padding-inline:10px}.hmb-finish-look__shot-shell{flex:1 1 auto;width:auto;max-width:none}.hmb-finish-look__shot-shell>span,.hmb-finish-look__bound-badge{display:none}}@container(max-width:500px){.hmb-finish-look__heading{display:flex}.hmb-finish-look__heading span,.hmb-finish-look__heading em,.hmb-finish-look__shot-shell>span,.hmb-finish-look__bound-badge{display:none}.hmb-finish-look__mark{display:none}.hmb-finish-look__shot-shell{min-width:0}.hmb-finish-look__language{min-width:46px;padding-inline:6px}}@container(max-width:400px){.hmb-finish-look__grid{grid-template-columns:repeat(3,minmax(0,1fr))}.hmb-finish-look__remote-badge{display:none}}
      .hmb-finish-look{display:flex;flex-direction:column;min-width:0;min-height:0;max-height:100%}.hmb-finish-look__topbar{position:relative;top:auto;flex:0 0 68px}.hmb-finish-look__scroll{flex:1 1 0;min-width:0;min-height:0;height:auto;max-height:none;overflow:auto}.hmb-finish-look__content{min-width:0;min-height:0}
      .hmb-finish-look__shot-tabs{flex:0 0 auto;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;padding:9px 10px 0;min-width:0}.hmb-finish-look__shot-tab{min-width:0;--tab:#F472B6}.hmb-finish-look__shot-tab[data-shot-number="2"]{--tab:#3B82F6}.hmb-finish-look__shot-tab[data-shot-number="3"]{--tab:#10B981}.hmb-finish-look__shot-tab[data-shot-number="4"]{--tab:#8B5CF6}.hmb-finish-look__shot-tab[data-shot-number="5"]{--tab:#EAB308}
      .hmb-finish-look__shot-tab button{display:flex;align-items:center;gap:7px;min-width:0;width:100%;height:42px;padding:6px 8px;border:1px solid color-mix(in srgb,var(--tab) 34%,transparent);border-radius:7px;background:color-mix(in srgb,var(--tab) 6%,#080f1b);color:#aebed0;font-size:10px;font-weight:750;text-align:left}.hmb-finish-look__shot-tab button[aria-pressed="true"]{border-color:var(--tab);background:color-mix(in srgb,var(--tab) 23%,#080f1b);color:var(--hmb-text);box-shadow:inset 3px 0 var(--tab),0 0 10px color-mix(in srgb,var(--tab) 18%,transparent)}.hmb-finish-look__shot-tab span{flex:0 0 auto;color:var(--tab);font-size:10px}.hmb-finish-look__shot-tab b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
      @container(max-width:460px){.hmb-finish-look__shot-tabs{grid-template-columns:repeat(3,minmax(0,1fr))}.hmb-finish-look__shot-tab button{padding:5px;gap:4px}}
      .hmb-finish-look__native-identity,.hmb-finish-look__native-actions{display:none;min-width:0;--node-header-text:#e8eef7}
      .hmb-finish-look[data-hmb-native-header=active]{border:0;border-radius:0;box-shadow:none}
      .hmb-finish-look[data-hmb-native-header=active] .hmb-finish-look__mark,.hmb-finish-look[data-hmb-native-header=active] .hmb-finish-look__heading{display:none}
      .hmb-finish-look[data-hmb-native-header=active] .hmb-finish-look__native-identity{display:flex;align-items:center;flex:1 1 auto}
      .hmb-finish-look[data-hmb-native-header=active] .hmb-finish-look__native-actions{display:flex;align-items:center;flex:0 0 auto}
      .hmb-finish-look__native-identity>div{min-width:0;max-width:100%}
    </style>
    <div class="hmb-finish-look nodrag nowheel" data-language="${state.language}" data-remote-connected="${remoteLocked ? "true" : "false"}" data-shot-number="${paletteShotNumber}" data-shot-bound="${shotBound ? "true" : "false"}" data-workspace-mode="finish" tabindex="0">
        <header class="hmb-finish-look__topbar group"><div class="hmb-finish-look__mark" aria-hidden="true">${headerMark}</div><div class="hmb-finish-look__heading"><b>${hmbEscape(headerTitle)}</b><span>${hmbEscape(headerSubtitle)}</span></div><div class="hmb-finish-look__native-identity" data-hmb-native-identity></div><div class="hmb-finish-look__native-actions nodrag" data-hmb-native-actions></div><label class="hmb-finish-look__shot-shell nodrag" data-no-finish-toggle${managed ? " hidden" : ""}><span>${hmbEscape(t.shot)}</span><select class="hmb-finish-look__shot-select nodrag" data-shot-selector aria-label="Shot"${shotOptions.length > 1 ? "" : " disabled"}>${hmbFinishLookShotOptionsMarkup(state)}</select></label><span class="hmb-finish-look__bound-badge" data-shot-bound-badge${shotBound ? "" : " hidden"}>${hmbEscape(t.bound)}</span><span class="hmb-finish-look__remote-badge"${remoteLocked ? "" : " hidden"}>REMOTE</span><button type="button" class="hmb-finish-look__language nodrag" data-no-finish-toggle data-language-toggle aria-label="${hmbEscape(t.language)}">${state.language === "ko" ? "한국어" : "EN"}</button></header>
        <nav class="hmb-finish-look__shot-tabs nodrag" aria-label="Shots"${managed ? "" : " hidden"}>${tabs}</nav>
      <div class="hmb-finish-look__scroll nodrag">
        <main class="hmb-finish-look__content">
          <section class="hmb-finish-look__section" data-finish-section="beauty"><header class="hmb-finish-look__section-header"><h2>${hmbEscape(t.beauty)}</h2><label class="hmb-finish-look__enable"><input type="checkbox" data-enable="beauty"${beauty.enabled ? " checked" : ""}${remoteLocked ? " disabled" : ""}><span>${hmbEscape(t.enable)}</span></label></header><div class="hmb-finish-look__section-body"><div class="hmb-finish-look__subhead">${hmbEscape(t.primary)}</div><div class="hmb-finish-look__grid">${hmbNumericField("beauty.soften_shadows", t.softenShadows, beauty.soften_shadows, beautyDisabled)}${hmbNumericField("beauty.shadow_threshold", t.shadowThreshold, beauty.shadow_threshold, beautyDisabled)}${hmbNumericField("beauty.saturation", t.saturation, beauty.saturation, beautyDisabled)}${hmbNumericField("beauty.brightness", t.brightness, beauty.brightness, beautyDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.advanced)}</div><div class="hmb-finish-look__grid">${hmbNumericField("beauty.glow_brightness", t.glowBrightness, beauty.glow_brightness, beautyDisabled)}${hmbNumericField("beauty.glow_threshold", t.glowThreshold, beauty.glow_threshold, beautyDisabled)}${hmbNumericField("beauty.glow_width", t.glowWidth, beauty.glow_width, beautyDisabled)}${hmbNumericField("beauty.soft_focus", t.softFocus, beauty.soft_focus, beautyDisabled)}${hmbNumericField("beauty.blur_amount", t.blurAmount, beauty.blur_amount, beautyDisabled)}${hmbNumericField("beauty.pore_size", t.poreSize, beauty.pore_size, beautyDisabled)}${hmbNumericField("beauty.reduce_shine", t.reduceShine, beauty.reduce_shine, beautyDisabled)}</div></div></section>
        </main>
        <div class="hmb-finish-look__status" data-status role="status" aria-live="polite" data-tone="neutral">${hmbEscape(t.ready)}</div>
      </div>
    </div>`;
}

export function hmbRenderFinishLookWidget(input = {}) {
  const state = hmbNormalizeFinishLookWidgetValue(input);
  return hmbScopeWidgetStyleMarkup(hmbRenderFinishLook(state), ".hmb-finish-look");
}

function hmbNodeRoot(container) {
  let current = container?.parentElement || null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) return null;
  }
  return null;
}

function hmbNodeSelected(root) {
  if (!root) return false;
  if (root.classList?.contains("selected")) return true;
  if (String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true") return true;
  if (String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true") return true;
  return Boolean(root.querySelector?.(
    ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
  ));
}

function hmbEditingTarget(event) {
  return Boolean(event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (container?.ownerDocument?.documentElement?.getAttribute?.("data-hmb-native-deletion-guard") === "engine-preflight") return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbEditingTarget(event)) return false;
  if (!hmbNodeSelected(hmbNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function hmbGetPath(root, path) {
  return String(path || "").split(".").reduce((value, key) => value?.[key], root);
}

function hmbSetPath(root, path, value) {
  const keys = String(path || "").split(".");
  let target = root;
  for (const key of keys.slice(0, -1)) target = target[key];
  target[keys.at(-1)] = value;
}

function hmbSetStatus(container, message, tone = "neutral") {
  const status = container?.querySelector?.("[data-status]");
  if (!status) return false;
  status.textContent = String(message || "");
  status.setAttribute?.("data-tone", tone);
  return true;
}

export function hmbCaptureFinishLookView(container) {
  const scroll = container?.querySelector?.(".hmb-finish-look__scroll");
  const active = container?.ownerDocument?.activeElement
    || (typeof document !== "undefined" ? document.activeElement : null);
  const focusKeys = ["data-finish-step", "data-enable", "data-shot-selector", "data-language-toggle"];
  let focus = null;
  if (active && container?.contains?.(active)) {
    for (const key of focusKeys) {
      if (active.hasAttribute?.(key)) {
        focus = { key, value: active.getAttribute(key) };
        break;
      }
    }
  }
  return scroll ? { top: scroll.scrollTop, left: scroll.scrollLeft, focus } : { focus };
}

export function hmbRestoreFinishLookView(container, view) {
  if (!container || !view) return;
  if (view.focus) {
    const { key, value } = view.focus;
    const candidate = Array.from(container.querySelectorAll?.(`[${key}]`) || [])
      .find((control) => control.getAttribute?.(key) === value);
    if (candidate && !candidate.disabled) {
      try { candidate.focus?.({ preventScroll: true }); }
      catch (_error) { candidate.focus?.(); }
    }
  }
  const scroll = container.querySelector?.(".hmb-finish-look__scroll");
  if (scroll && Number.isFinite(view.top) && Number.isFinite(view.left)) {
    scroll.scrollTop = view.top;
    scroll.scrollLeft = view.left;
  }
}

function hmbFinishLookShotKey(state) {
  return state?.shot?.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}` : HMB_FINISH_LOOK_ONLY_SHOT_VALUE;
}

function hmbFinishLookTransportTargetKey(state) {
  return state?.shot?.shot_uuid ? hmbFinishLookShotKey(state) : "__standalone__";
}

function hmbMorphFinishLook(current, desired) {
  if (!current || !desired) return;
  if (current.nodeType !== desired.nodeType || current.nodeName !== desired.nodeName) {
    current.replaceWith(desired.cloneNode(true));return;
  }
  if (current.nodeType === 3) {if(current.nodeValue!==desired.nodeValue)current.nodeValue=desired.nodeValue;return;}
  if (current.nodeType !== 1) return;
  // React owns the portal children; morphology must retain their slot and subtree.
  if (current.hasAttribute("data-hmb-native-identity") || current.hasAttribute("data-hmb-native-actions")) return;
  for(const attribute of Array.from(current.attributes))if(!desired.hasAttribute(attribute.name))current.removeAttribute(attribute.name);
  for(const attribute of Array.from(desired.attributes))if(current.getAttribute(attribute.name)!==attribute.value)current.setAttribute(attribute.name,attribute.value);
  if (current.tagName === "INPUT") {
    if(current.type === "checkbox" && current.checked!==desired.checked)current.checked=desired.checked;
    if(current.type !== "checkbox" && current.value!==desired.value)current.value=desired.value;
  }
  const wanted=Array.from(desired.childNodes);
  for(let index=0;index<wanted.length;index++){
    if(current.childNodes[index])hmbMorphFinishLook(current.childNodes[index],wanted[index]);
    else current.appendChild(wanted[index].cloneNode(true));
  }
  while(current.childNodes.length>wanted.length)current.lastChild.remove();
}

function hmbNativeUiImplementation(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  const incoming = props || container.__hmbFinishLookLatestProps || {};
  if (typeof container.__hmbFinishLookCleanupProxy !== "function") {
    container.__hmbFinishLookCleanupProxy = () => container.__hmbFinishLookCleanup?.();
  }
  if (typeof container.__hmbFinishLookCleanup === "function") {
    container.__hmbFinishLookApplyProps?.(incoming);
    return {
      cleanup: container.__hmbFinishLookCleanupProxy,
      update(nextProps) { container.__hmbFinishLookApplyProps?.(nextProps || {}); },
    };
  }

  let state = hmbNormalizeFinishLookWidgetValue(incoming);
  let disposed = false;
  let nativeHeader = null;
  let listenerCleanups = [];
  let publicationOwner = 0;
  let pendingShot = null;
  let resizeObserver = null;
  let resizeFrame = 0;
  let queuedTab = null;
  let tabFrame = 0;
  let uiClock=hmbFinishLookUITransport(incoming);
  let transportEnabled=Boolean(uiClock),transportEpoch="",transportSequence=0,transportFlight=null;
  let transportQueue=[],transportFrames=[],transportTimer=0,transportFallback=0;
  const retiredSessions=new Set();
  const transportId=()=>globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  const transportClient=transportId();
  container.__hmbFinishLookLatestProps = incoming;

  const clearListeners = () => {
    for (const cleanup of listenerCleanups.splice(0)) {
      try { cleanup(); } catch (_error) {}
    }
  };
  const bind = (target, eventName, handler, options) => {
    if (!target?.addEventListener) return;
    target.addEventListener(eventName, handler, options);
    listenerCleanups.push(() => target.removeEventListener?.(eventName, handler, options));
  };
  const cloneState = () => hmbNormalizeFinishLookWidgetValue(hmbFinishLookPublication(state));
  let confirmedState=cloneState();
  const tabWindow=container.ownerDocument?.defaultView;
  const cancelQueuedTab=()=>{queuedTab=null;if(tabFrame){tabWindow?.cancelAnimationFrame?.(tabFrame);tabFrame=0;}};
  const flushQueuedTab=()=>{
    const queued=queuedTab;cancelQueuedTab();return queued && !disposed ? queued.send() : true;
  };
  const clearTransportSchedule=()=>{
    for(const frame of transportFrames)tabWindow?.cancelAnimationFrame?.(frame);transportFrames=[];
    clearTimeout(transportFallback);transportFallback=0;
  };
  const retainTransportProps=(nextProps)=>{
    const value={...hmbFinishLookPublication(state),...(uiClock?{ui_transport:uiClock}:{})};
    container.__hmbFinishLookLatestProps={...nextProps,value,parameterValue:value,defaultValue:value};
  };
  const rejectTransportDraft=(message)=>{
    if(transportQueue.some(command=>command.operation==="edit"))container.__hmbFinishLookUnappliedDraft=transportQueue.filter(command=>command.operation==="edit").map(command=>structuredClone(command.payload));
    transportQueue=[];clearTransportSchedule();pendingShot=null;state=hmbNormalizeFinishLookWidgetValue(confirmedState);
    retainTransportProps(container.__hmbFinishLookLatestProps || {});remount();
    if(message)hmbSetStatus(container,message,"error");
  };
  const queueTransportRefresh=()=>{
    if(disposed || transportFlight?.operation==="refresh" || transportQueue.some(command=>command.operation==="refresh"))return;
    transportQueue.unshift({operation:"refresh",payload:cloneState(),request_id:transportId()});
    scheduleTransport(false);
  };
  const dispatchTransport=()=>{
    clearTransportSchedule();if(disposed || transportFlight || !transportQueue.length)return;
    if(!transportEpoch && transportQueue[0].operation!=="refresh")transportQueue.unshift({operation:"refresh",payload:cloneState(),request_id:transportId()});
    const command=transportQueue.shift(),key=hmbFinishLookTransportTargetKey(command.payload);
    if(command.operation!=="refresh" && (!uiClock || !Object.hasOwn(uiClock.target_revisions,key))){rejectTransportDraft("선택한 샷이 삭제되었거나 사용할 수 없습니다.");queueTransportRefresh();return;}
    command.sequence=++transportSequence;
    const envelope={schema:"hmb-finish-ui-transport",version:1,operation:command.operation,session_id:uiClock?.session_id || "",base_revision:uiClock?.revision || 0,
      base_target_revision:command.baseTarget ?? uiClock?.target_revisions[key] ?? 0,client_id:transportClient,client_epoch:transportEpoch,request_id:command.request_id,sequence:command.sequence};
    command.envelope=envelope;transportFlight=command;
    const failed=error=>{
      if(disposed || transportFlight!==command)return;
      if(command.operation==="edit")container.__hmbFinishLookUnappliedDraft=[structuredClone(command.payload)];
      clearTimeout(transportTimer);transportFlight=null;rejectTransportDraft(String(error?.message || "Finish Look 상태 확인에 실패했습니다."));
      if(command.operation!=="refresh")queueTransportRefresh();
    };
    transportTimer=setTimeout(()=>failed(new Error("Finish Look 응답을 확인하지 못했습니다. 현재 상태를 다시 조회합니다.")),15000);
    try{
      const onChange=container.__hmbFinishLookLatestProps?.onChange;
      if(typeof onChange!=="function")throw new Error("Finish Look state transport is unavailable.");
      const result=onChange({...hmbFinishLookPublication(command.payload),ui_transport:envelope});
      if(result && typeof result.then==="function")Promise.resolve(result).catch(failed);
    }catch(error){failed(error);}
  };
  function scheduleTransport(deferred){
    if(disposed || transportFlight)return;
    if(!deferred){dispatchTransport();return;}
    clearTransportSchedule();
    if(tabWindow?.requestAnimationFrame)transportFrames.push(tabWindow.requestAnimationFrame(()=>{
      transportFrames.push(tabWindow.requestAnimationFrame(dispatchTransport));
    }));
    transportFallback=setTimeout(dispatchTransport,120);
  }
  const enqueueTransport=(payload,tabOnly)=>{
    const command={operation:tabOnly?"select":"edit",payload:hmbFinishLookPublication(payload),request_id:transportId(),baseTarget:uiClock?.target_revisions[hmbFinishLookTransportTargetKey(payload)] ?? 0};
    if(tabOnly && transportQueue.at(-1)?.operation==="select")transportQueue.pop();
    transportQueue.push(command);scheduleTransport(tabOnly);return true;
  };
  const receiveTransport=(nextProps,nextState)=>{
    const meta=hmbFinishLookUITransport(nextProps),raw=hmbRecord(hmbRawWidgetValue(nextProps).ui_transport);
    if(!transportEnabled && !meta)return false;
    transportEnabled=true;
    const matches=Boolean(meta && transportFlight && meta.client_id===transportClient && meta.request_id===transportFlight.request_id && meta.sequence===transportFlight.sequence);
    if(!meta){
      retainTransportProps(nextProps);
      // The host may briefly echo its outgoing command before Python publishes
      // the authoritative reply. Delivery alone never acknowledges the editor.
      if(raw.client_id===transportClient && raw.request_id===transportFlight?.request_id)return true;
      queueTransportRefresh();return true;
    }
    if(uiClock && meta.session_id!==uiClock.session_id){
      if(retiredSessions.has(meta.session_id)){retainTransportProps(nextProps);return true;}
      if(!(matches && transportFlight.operation==="refresh" && ["refreshed","duplicate"].includes(meta.status))){
        retainTransportProps(nextProps);
        if(matches){clearTimeout(transportTimer);transportFlight=null;transportEpoch="";rejectTransportDraft("Finish Look 세션이 변경되어 현재 상태를 확인합니다.");}
        queueTransportRefresh();return true;
      }
      retiredSessions.add(uiClock.session_id);transportEpoch="";
    }
    if(uiClock && meta.session_id===uiClock.session_id && meta.revision<uiClock.revision){
      retainTransportProps(nextProps);
      if(matches){clearTimeout(transportTimer);transportFlight=null;rejectTransportDraft();queueTransportRefresh();}
      return true;
    }
    const sameRevision=uiClock && meta.session_id===uiClock.session_id && meta.revision===uiClock.revision;
    if(sameRevision && JSON.stringify(nextState)!==JSON.stringify(confirmedState)
      && !(matches && transportFlight.operation==="refresh" && ["refreshed","duplicate"].includes(meta.status))){
      retainTransportProps(nextProps);queueTransportRefresh();return true;
    }
    if(sameRevision && !matches && JSON.stringify(nextState)===JSON.stringify(confirmedState)){
      uiClock=meta;retainTransportProps(nextProps);return true;
    }
    const completed=matches?transportFlight:null;
    if(completed){clearTimeout(transportTimer);transportFlight=null;transportEpoch=meta.client_epoch || transportEpoch;}
    uiClock=meta;confirmedState=hmbNormalizeFinishLookWidgetValue(nextState);
    const failed=completed && !["accepted","refreshed","duplicate"].includes(meta.status);
    if(failed){
      if(completed.operation==="edit")container.__hmbFinishLookUnappliedDraft=[structuredClone(completed.payload)];
      if(["stale_client","stale_session"].includes(meta.status))transportEpoch="";
      rejectTransportDraft("최신 상태와 변경이 충돌해 적용하지 않았습니다. 현재 값을 확인해 주세요.");
      retainTransportProps(nextProps);
      if(["stale_client","stale_session"].includes(meta.status))queueTransportRefresh();
      return true;
    }
    if(completed && completed.operation==="edit"){
      const key=hmbFinishLookTransportTargetKey(completed.payload);
      for(const queued of transportQueue)if(queued.operation==="edit" && hmbFinishLookTransportTargetKey(queued.payload)===key && queued.baseTarget===completed.envelope.base_target_revision)queued.baseTarget=meta.target_revisions[key];
    }
    if(transportQueue.some(command=>command.operation!=="refresh" && !Object.hasOwn(meta.target_revisions,hmbFinishLookTransportTargetKey(command.payload)))){
      rejectTransportDraft("선택한 샷이 삭제되었거나 사용할 수 없습니다.");
    }
    const draft=transportQueue.filter(command=>command.operation!=="refresh").at(-1)
      || (transportFlight?.operation!=="refresh" ? transportFlight : null);
    state=draft?hmbNormalizeFinishLookWidgetValue(draft.payload):hmbNormalizeFinishLookWidgetValue(nextState);
    state.remote_connected=nextState.remote_connected;
    if(nextState.remote_connected && transportQueue.some(command=>command.operation==="edit"
      && JSON.stringify(command.payload.finish_look)!==JSON.stringify(
        hmbFinishLookTransportTargetKey(command.payload)===hmbFinishLookTransportTargetKey(nextState)
          ? nextState.finish_look : nextState.shot_documents[hmbFinishLookTransportTargetKey(command.payload)] || hmbDefaultFinishLook())))rejectTransportDraft("REMOTE 연결 중에는 Finish Look 값을 수정할 수 없습니다.");
    pendingShot=null;cancelQueuedTab();publicationOwner+=1;retainTransportProps(nextProps);remount();
    if(!transportFlight)scheduleTransport(false);
    return true;
  };

  const remount = () => {
    if (disposed) return;
    const view = hmbCaptureFinishLookView(container);
    const markup=hmbRenderFinishLookWidget(state);
    const root=container.querySelector?.(".hmb-finish-look");
    const document=container.ownerDocument;
    if(root && document?.createElement && root.childNodes){
      const template=document.createElement("template");template.innerHTML=markup;
      hmbMorphFinishLook(root,template.content.querySelector(".hmb-finish-look"));
    }else{
      clearListeners();container.innerHTML=markup;
      container.classList?.add("nodrag");container.setAttribute?.("data-hmb-node-delete-protected","true");installInteractions();
    }
    nativeHeader = hmbInstallNativeHeaderBridge(container, "HMBFinishLookLibrary", ".hmb-finish-look");
    hmbRestoreFinishLookView(container, view);
  };

  const rollback = (previous, owner, error) => {
    if (disposed || owner !== publicationOwner) return;
    cancelQueuedTab();
    pendingShot = null;
    state = previous;
    const retained = hmbFinishLookPublication(state);
    container.__hmbFinishLookLatestProps = {
      ...container.__hmbFinishLookLatestProps,
      value: retained, parameterValue: retained, defaultValue: retained,
    };
    remount();
    hmbSetStatus(container, String(error?.message || error || "Publication failed."), "error");
  };

  const publish = (previous = cloneState(), repaint = true, tabOnly = false) => {
    const liveProps = container.__hmbFinishLookLatestProps || {};
    if (typeof liveProps.onChange !== "function") {
      rollback(hmbNormalizeFinishLookWidgetValue(confirmedState), publicationOwner, new Error("Finish Look state transport is unavailable."));
      return false;
    }
    const owner = ++publicationOwner;
    const payload = hmbFinishLookPublication(state);
    // A queued selection or earlier edit is not authoritative until echoed by
    // the host. If several publications fail, never restore an unconfirmed view.
    const rollbackState=hmbNormalizeFinishLookWidgetValue(confirmedState);
    const persisted = hmbFinishLookPublication(state);
    container.__hmbFinishLookLatestProps = {
      ...liveProps,
      value: persisted,
      parameterValue: persisted,
      defaultValue: persisted,
    };
    // Paint the local selection before the host bridge can serialize or wake
    // the graph. Ordinary authoring transport remains unchanged.
    if (repaint) {if(!tabOnly || !hmbApplyFinishLookActiveEditor(container,state))remount();}
    if(transportEnabled)return enqueueTransport(payload,tabOnly);
    const send=()=>{
      if(disposed || owner !== publicationOwner)return false;
      const onChange=container.__hmbFinishLookLatestProps?.onChange;
      if(typeof onChange!=="function"){
        rollback(rollbackState,owner,new Error("Finish Look state transport is unavailable."));return false;
      }
      let result;
      try{result=onChange(payload);}catch(error){rollback(rollbackState,owner,error);return false;}
      if(result && typeof result.then==="function")Promise.resolve(result).catch(error=>rollback(rollbackState,owner,error));
      return true;
    };
    if(tabOnly && tabWindow?.requestAnimationFrame){
      cancelQueuedTab();queuedTab={previous:rollbackState,send};
      tabFrame=tabWindow.requestAnimationFrame(()=>{
        tabFrame=tabWindow.requestAnimationFrame(()=>{tabFrame=0;const queued=queuedTab;queuedTab=null;if(!disposed)queued?.send();});
      });
    }else send();
    return true;
  };

  const mutate = (mutator, repaint = true) => {
    if(!flushQueuedTab())return false;
    const previous = cloneState();
    mutator(state);
    return publish(previous, repaint);
  };

  function installInteractions() {
    const root = container.querySelector?.(".hmb-finish-look");
    if (!root) return;
    const ownerDocument = container.ownerDocument || (typeof document !== "undefined" ? document : null);
    bind(container,"click",event=>{
      const button=event.target?.closest?.("[data-finish-shot]");
      if(!button || !state.shot_manager)return;
      const shot=state.shot_catalog.shots.find(row=>row.shot_uuid===button.getAttribute("data-finish-shot"));
      if(!shot || state.shot.shot_uuid===shot.shot_uuid)return;
      const previous=cloneState(),previousKey=hmbFinishLookShotKey(state);
      state.shot_documents[previousKey]=JSON.parse(JSON.stringify(state.finish_look));
      state.shot={channel_uuid:state.shot_catalog.channel_uuid,...shot};
      state.finish_look=JSON.parse(JSON.stringify(state.shot_documents[hmbFinishLookShotKey(state)] || hmbDefaultFinishLook()));
      state.shot_editor_expanded=true;
      const blockedKeys=new Set(pendingShot?.blockedKeys||[]);blockedKeys.add(previousKey);
      pendingShot={targetKey:hmbFinishLookShotKey(state),blockedKeys};publish(previous,true,true);
    });
    // No workspace double-click handler: Finish Look remains the finish editor.
    const shotSelect = container.querySelector?.("[data-shot-selector]");
    bind(shotSelect, "change", () => {
      const option = hmbFinishLookShotOptions(state).find((item) => item.key === shotSelect?.value);
      if (!option) {
        hmbApplyFinishLookShotFeedback(container, state);
        return;
      }
      const previous = cloneState();
      const previousKey = hmbFinishLookShotKey(state);
      state.shot = option.only ? hmbFinishLookOnlyShot() : {
        channel_uuid: option.channel_uuid,
        shot_uuid: option.shot_uuid,
        number: option.number,
        name: option.name,
      };
      const blockedKeys = new Set(pendingShot?.blockedKeys || []);
      blockedKeys.add(previousKey);
      pendingShot = { targetKey: hmbFinishLookShotKey(state), blockedKeys };
      hmbApplyFinishLookShotFeedback(container, state);
      publish(previous, false);
    });
    bind(container.querySelector?.("[data-language-toggle]"), "click", () => {
      mutate((next) => { next.language = next.language === "ko" ? "en" : "ko"; }, true);
    });
    for (const toggle of container.querySelectorAll?.("[data-enable]") || []) {
      bind(toggle, "change", () => {
        if (state.remote_connected) return;
        const group = toggle.getAttribute("data-enable");
        if (group !== "beauty") return;
        const enabled = Boolean(toggle.checked);
        mutate((next) => { next.finish_look[group].enabled = enabled; }, true);
      });
    }
    for (const input of container.querySelectorAll?.("[data-finish-step]") || []) {
      const path = input.getAttribute("data-finish-step");
      if (!Object.hasOwn(HMB_FINISH_LOOK_STEPS, path)) continue;
      const preview = () => {
        if (input.disabled || !hmbFinishLookFieldEnabled(state, path)) return null;
        const value = hmbFinishLookStepValue(path, input.value);
        if (value === null) return null;
        const text = hmbFinishLookStepLabel(path, value, state.language);
        input.setAttribute?.("aria-valuetext", text);
        const output = container.querySelector?.(`[data-step-label="${path}"]`);
        if (output) output.textContent = text;
        return value;
      };
      // Dragging is local-only. Commit once on release/keyboard change, without remounting.
      bind(input, "input", preview);
      bind(input, "change", () => {
        const requestedValue = input.value;
        if(!flushQueuedTab())return;
        input.value = requestedValue;
        const value = preview();
        if (value === null || hmbGetPath(state.finish_look, path) === value) return;
        const previous = cloneState();
        hmbSetPath(state.finish_look, path, value);
        hmbApplyFinishLookControlAvailability(container, state);
        publish(previous, false);
      });
    }
    const stopInteriorInteraction = (event) => {
      if (hmbNativeHeaderTarget(event.target)) return;
      if (event.target?.closest?.("button,input,select,textarea,[role='option']")) event.stopPropagation?.();
    };
    const stopInteriorDelete = (event) => {
      if (hmbNativeHeaderTarget(event.target)) return;
      if (["Backspace", "Delete"].includes(event.key)) event.stopPropagation?.();
    };
    bind(container, "pointerdown", stopInteriorInteraction);
    bind(container, "keydown", stopInteriorDelete);
    const guardDelete = (event) => { if (!hmbNativeHeaderTarget(event.target)) hmbGuardSelectedNodeKeyboardDelete(container, event); };
    const ownerWindow = ownerDocument?.defaultView || (typeof window !== "undefined" ? window : null);
    bind(ownerWindow, "keydown", guardDelete, true);
  }

  container.__hmbFinishLookApplyProps = (nextProps = {}) => {
    if (disposed) return;
    const nextState = hmbNormalizeFinishLookWidgetValue(nextProps);
    if(receiveTransport(nextProps,nextState))return;
    if(JSON.stringify(nextState)===JSON.stringify(state)){
      pendingShot=null;publicationOwner+=1;cancelQueuedTab();confirmedState=hmbNormalizeFinishLookWidgetValue(nextState);
      container.__hmbFinishLookLatestProps=nextProps;return;
    }
    if (pendingShot && nextProps !== container.__hmbFinishLookLatestProps) {
      const incomingKey = hmbFinishLookShotKey(nextState);
      if (incomingKey === pendingShot.targetKey) pendingShot = null;
      else {
        const catalogOlder = nextState.shot_catalog.channel_uuid === state.shot_catalog.channel_uuid
          && Number(nextState.shot_catalog.generation || 0) < Number(state.shot_catalog.generation || 0);
        const catalog = catalogOlder ? state.shot_catalog : nextState.shot_catalog;
        const targetAvailable = pendingShot.targetKey === HMB_FINISH_LOOK_ONLY_SHOT_VALUE
          || (catalog.shots || []).some(
            (shot) => `${catalog.channel_uuid}\u001f${shot.shot_uuid}` === pendingShot.targetKey,
          );
        if (targetAvailable && pendingShot.blockedKeys.has(incomingKey)) {
          const retained = hmbFinishLookPublication(state);
          container.__hmbFinishLookLatestProps = {
            ...nextProps, value: retained, parameterValue: retained, defaultValue: retained,
          };
          if (nextState.remote_connected && !state.remote_connected) {
            state.remote_connected = true;
            remount();
          }
          return;
        }
        pendingShot = null;cancelQueuedTab();
      }
    }
    cancelQueuedTab();
    publicationOwner += 1;
    const previousFingerprint = hmbFinishLookNonShotStateFingerprint(state);
    container.__hmbFinishLookLatestProps = nextProps;
    state = nextState;
    confirmedState=hmbNormalizeFinishLookWidgetValue(nextState);
    const authoredUnchanged = previousFingerprint === hmbFinishLookNonShotStateFingerprint(nextState);
    if (!state.shot_manager && authoredUnchanged && hmbApplyFinishLookShotFeedback(container, nextState)) {
      return;
    }
    remount();
  };
  const cleanup = () => {
    nativeHeader?.cleanup();
    disposed = true;
    clearTransportSchedule();clearTimeout(transportTimer);transportQueue=[];transportFlight=null;
    cancelQueuedTab();
    publicationOwner += 1;
    pendingShot = null;
    clearListeners();
    resizeObserver?.disconnect();
    const ownerWindow=container.ownerDocument?.defaultView;
    if(resizeFrame)ownerWindow?.cancelAnimationFrame?.(resizeFrame);
    container.style?.removeProperty?.("max-height");
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.classList?.remove("nodrag");
    container.innerHTML = "";
    if (container.__hmbFinishLookCleanup === cleanup) delete container.__hmbFinishLookCleanup;
    delete container.__hmbFinishLookApplyProps;
    delete container.__hmbFinishLookLatestProps;
  };
  container.__hmbFinishLookCleanup = cleanup;
  remount();
  const ownerWindow=container.ownerDocument?.defaultView;
  const NodeResizeObserver=ownerWindow?.ResizeObserver;
  if(typeof NodeResizeObserver==="function"){
    const node=hmbNodeRoot(container);
    const fit=()=>{
      resizeFrame=0;if(disposed || !node)return;
      const nodeRect=node.getBoundingClientRect(),rect=container.getBoundingClientRect();
      const scale=node.offsetHeight>0?nodeRect.height/node.offsetHeight:1;
      const available=Math.max(120,Math.floor((nodeRect.bottom-rect.top)/Math.max(scale,0.01)-16));
      const next=available+"px";
      if(container.style.getPropertyValue("max-height")!==next)container.style.setProperty("max-height",next);
    };
    resizeObserver=new NodeResizeObserver(()=>{if(!resizeFrame)resizeFrame=ownerWindow.requestAnimationFrame(fit);});
    resizeObserver.observe(container);if(node)resizeObserver.observe(node);
  }
  return {
    cleanup: container.__hmbFinishLookCleanupProxy,
    update(nextProps) { container.__hmbFinishLookApplyProps?.(nextProps || {}); },
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
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "finish", allowControl: hmbNativeHeaderTarget });
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
      const title = doc.createElement("strong"); title.textContent = "HMB 통합 설치가 필요합니다";
      const text = doc.createElement("p");
      text.textContent = "Git Update만으로는 네이티브 UI 패치가 적용되지 않습니다. 엔진 응답 전에 화면에서 노드가 사라지는 문제를 막기 위해 HMB 노드 삭제를 일시 중단했습니다. 작업 저장 → Griptape 완전 종료 → Runtime ZIP의 Install_HMB_GP_Production.ps1 실행 → 재시작 후 다시 삭제하세요. 연결된 노드는 계속 보호되며, 연결이 없는 노드는 통합 설치 후 정상 삭제됩니다.";
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
      badge.setAttribute("aria-label", "HMB 네이티브 UI 통합 설치 안내");
      badge.textContent = "HMB 통합 설치 필요 · 안전 삭제 보호 중";
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

export default function HMBFinishLookLibraryWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
