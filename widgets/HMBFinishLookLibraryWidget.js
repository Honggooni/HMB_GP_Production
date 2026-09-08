export const HMB_FINISH_LOOK_SCHEMA_VERSION = 1;
export const HMB_FINISH_LOOK_ONLY_SHOT_VALUE = "__hmb_only__";
export const HMB_JEWEL_NIGHT_SHOT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});
export const HMB_FINISH_LOOK_SHOT_PALETTE = HMB_JEWEL_NIGHT_SHOT_PALETTE;

export const HMB_NEGATIVE_FILM_STOCKS = Object.freeze([
  "None",
  "Kodak 5245",
]);

export const HMB_PRINT_FILM_STOCKS = Object.freeze([
  "None",
  "Kodak 2383",
]);

export const HMB_FILM_STOCK_CATALOG_FALLBACK = Object.freeze({
  negative: HMB_NEGATIVE_FILM_STOCKS,
  print: HMB_PRINT_FILM_STOCKS,
  reversal: Object.freeze([]),
});

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
  "film.scale_cc": Object.freeze({ min: 0, max: 5, step: 0.01, precision: 2 }),
  "film.printer_light_r": Object.freeze({ min: 0, max: 50, step: 1, precision: 0, integer: true }),
  "film.printer_light_g": Object.freeze({ min: 0, max: 50, step: 1, precision: 0, integer: true }),
  "film.printer_light_b": Object.freeze({ min: 0, max: 50, step: 1, precision: 0, integer: true }),
  "film.input_gamma": Object.freeze({ min: 0.1, max: null, step: 0.05, precision: 2 }),
  "film.output_gamma": Object.freeze({ min: 0.1, max: null, step: 0.05, precision: 2 }),
  "film.negative_exposure": Object.freeze({ min: null, max: null, step: 0.05, precision: 2 }),
  "film.print_exposure": Object.freeze({ min: null, max: null, step: 0.05, precision: 2 }),
  "film.glow_brightness": Object.freeze({ min: 0, max: null, step: 0.01, precision: 2 }),
  "film.soft_focus": Object.freeze({ min: 0, max: 1, step: 0.01, precision: 2 }),
  "film.vignette": Object.freeze({ min: 0, max: 1, step: 0.01, precision: 2 }),
});

// Discrete UI stops use representative values of the existing compiler contract.
// The transport remains numeric; arbitrary numeric editing is not exposed.
const strengthSteps = (values = [0, 0.05, 0.1, 0.2, 0.4, 0.8]) => steps(values,
  ["끔", "거의 없음", "매우 약함", "약함", "보통", "강함"],
  ["Off", "Almost none", "Very subtle", "Subtle", "Moderate", "Strong"]);
function steps(values, ko, en) {
  return Object.freeze(values.map((value, index) => Object.freeze({ value, ko: ko[index], en: en[index] })));
}
const exposureSteps = (print = false) => steps([-2, -1, -0.5, -0.25, -0.1, 0, 0.1, 0.25, 0.5, 1, 2],
  print
    ? ["매우 밝게", "많이 밝게", "보통 밝게", "약하게 밝게", "미세하게 밝게", "중립", "미세하게 어둡게", "약하게 어둡게", "보통 어둡게", "많이 어둡게", "매우 어둡게"]
    : ["매우 어둡게", "많이 어둡게", "보통 어둡게", "약하게 어둡게", "미세하게 어둡게", "중립", "미세하게 밝게", "약하게 밝게", "보통 밝게", "많이 밝게", "매우 밝게"],
  print
    ? ["Very light", "Much lighter", "Moderately lighter", "Slightly lighter", "Very slightly lighter", "Neutral", "Very slightly darker", "Slightly darker", "Moderately darker", "Much darker", "Very dark"]
    : ["Very dark", "Much darker", "Moderately darker", "Slightly darker", "Very slightly darker", "Neutral", "Very slightly brighter", "Slightly brighter", "Moderately brighter", "Much brighter", "Very bright"]);
const printerSteps = (lowKo, highKo, lowEn, highEn) => steps([17, 21, 23, 24, 25, 26, 27, 29, 33],
  [`${lowKo} 강`, `${lowKo} 중`, `${lowKo} 약`, `${lowKo} 미세`, "중립", `${highKo} 미세`, `${highKo} 약`, `${highKo} 중`, `${highKo} 강`],
  [`Strong ${lowEn}`, `Moderate ${lowEn}`, `Subtle ${lowEn}`, `Very subtle ${lowEn}`, "Neutral", `Very subtle ${highEn}`, `Subtle ${highEn}`, `Moderate ${highEn}`, `Strong ${highEn}`]);
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
  "film.scale_cc": steps([0, 0.1, 0.3, 0.6, 0.8, 1], ["끔", "매우 약함", "약함", "보통", "강함", "매우 강함"], ["Off", "Very subtle", "Subtle", "Moderate", "Strong", "Very strong"]),
  "film.printer_light_r": printerSteps("빨강", "시안", "red", "cyan"),
  "film.printer_light_g": steps([17, 21, 23, 25, 27, 29, 33],
    ["초록 강", "초록 중", "초록 약", "중립", "마젠타 약", "마젠타 중", "마젠타 강"],
    ["Strong green", "Moderate green", "Subtle green", "Neutral", "Subtle magenta", "Moderate magenta", "Strong magenta"]),
  "film.printer_light_b": printerSteps("파랑", "노랑", "blue", "yellow"),
  "film.input_gamma": steps([0.6, 0.9, 1.2, 1.5, 1.8], ["매우 낮음", "낮음", "기본", "높음", "매우 높음"], ["Very low", "Low", "Default", "High", "Very high"]),
  "film.output_gamma": steps([1.4, 1.8, 2.2, 2.6, 3], ["매우 낮음", "낮음", "기본", "높음", "매우 높음"], ["Very low", "Low", "Default", "High", "Very high"]),
  "film.negative_exposure": exposureSteps(),
  "film.print_exposure": exposureSteps(true),
  "film.glow_brightness": strengthSteps(),
  "film.soft_focus": strengthSteps(),
  "film.vignette": strengthSteps(),
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
    subtitle: "Character Beauty and photographic filter application",
    language: "Language",
    shot: "SHOT",
    only: "Only",
    bound: "BOUND",
    beauty: "CHARACTER BEAUTY",
    film: "FILTER APPLICATION",
    enable: "Enable",
    primary: "PRIMARY CONTROLS",
    advanced: "ADVANCED",
    filmStock: "FILM STOCK",
    colorCorrection: "COLOR CORRECTION",
    printerLights: "PRINTER LIGHTS",
    tone: "TONE",
    exposure: "EXPOSURE",
    glow: "GLOW",
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
    negativeFilm: "Negative Film",
    printFilm: "Print Film",
    scaleCc: "Scale CC",
    inputGamma: "Input Gamma",
    outputGamma: "Output Gamma",
    negativeExposure: "Negative Exposure",
    printExposure: "Print Exposure",
    vignette: "Vignette",
    ready: "Ready",
    reversalNote: "Ignored while a reversal print film is selected",
  }),
  ko: Object.freeze({
    subtitle: "캐릭터 뷰티 및 사진 필터 적용",
    language: "언어",
    shot: "SHOT",
    only: "Only",
    bound: "BOUND",
    beauty: "캐릭터 뷰티",
    film: "필터 적용",
    enable: "사용",
    primary: "기본 조절",
    advanced: "고급 조절",
    filmStock: "필름 스톡",
    colorCorrection: "색 보정",
    printerLights: "프린터 라이트",
    tone: "톤",
    exposure: "노출",
    glow: "글로우",
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
    negativeFilm: "네거티브 필름",
    printFilm: "프린트 필름",
    scaleCc: "색 보정 강도",
    inputGamma: "입력 감마",
    outputGamma: "출력 감마",
    negativeExposure: "네거티브 노출",
    printExposure: "프린트 노출",
    vignette: "비네트",
    ready: "준비됨",
    reversalNote: "리버설 프린트 필름 선택 중에는 적용되지 않습니다",
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
  const wrapperCatalog = hmbRecord(wrapper.catalog);
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
  if (!Object.keys(hmbRecord(unwrapped.catalog)).length && Object.keys(wrapperCatalog).length) {
    merged = { ...merged, catalog: wrapperCatalog };
  }
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

function hmbCatalogItems(value, fallback) {
  if (!Array.isArray(value)) return [...fallback];
  const seen = new Set();
  const items = [];
  for (const candidate of value) {
    const item = String(candidate ?? "").trim();
    if (!item || seen.has(item)) continue;
    seen.add(item);
    items.push(item);
  }
  return items.length ? items : [...fallback];
}

export function hmbNormalizeFilmStockCatalog(value) {
  const source = hmbRecord(value);
  return {
    negative: hmbCatalogItems(source.negative, HMB_FILM_STOCK_CATALOG_FALLBACK.negative),
    print: hmbCatalogItems(source.print, HMB_FILM_STOCK_CATALOG_FALLBACK.print),
    reversal: hmbCatalogItems(source.reversal, HMB_FILM_STOCK_CATALOG_FALLBACK.reversal),
  };
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

function hmbChoice(value, choices, fallback) {
  return choices.includes(value) ? value : fallback;
}

function hmbPath(value) {
  return String(value ?? "").slice(0, 4096);
}

function hmbLanguage(value) {
  return String(value ?? "").trim().toLowerCase() === "en" ? "en" : "ko";
}

function hmbDefaultFinishLook(catalog = HMB_FILM_STOCK_CATALOG_FALLBACK) {
  const negativeFilm = catalog.negative.includes("Kodak 5245")
    ? "Kodak 5245"
    : (catalog.negative[0] || "None");
  const printFilm = catalog.print.includes("Kodak 2383")
    ? "Kodak 2383"
    : (catalog.print[0] || "None");
  return {
    schema_version: HMB_FINISH_LOOK_SCHEMA_VERSION,
    beauty: {
      enabled: true,
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
    film: {
      enabled: true,
      negative_film: negativeFilm,
      print_film: printFilm,
      scale_cc: 0.3,
      printer_light_r: 26,
      printer_light_g: 25,
      printer_light_b: 24,
      input_gamma: 1.2,
      output_gamma: 2.2,
      negative_exposure: 0,
      print_exposure: 0,
      glow_brightness: 0.1,
      soft_focus: 0,
      vignette: 0,
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
  const catalog = hmbNormalizeFilmStockCatalog(source.catalog);
  const shotCatalog = hmbNormalizeFinishLookShotCatalog(source.shot_catalog);
  const shot = hmbNormalizeFinishLookShotSelection(source.shot, shotCatalog);
  const rawFinish = Object.keys(hmbRecord(source.finish_look)).length
    ? hmbRecord(source.finish_look)
    : ((source.beauty || source.film) ? source : {});
  const defaults = hmbDefaultFinishLook(catalog);
  const rawBeauty = hmbRecord(rawFinish.beauty);
  const rawFilm = hmbRecord(rawFinish.film);
  const beauty = { enabled: hmbBoolean(rawBeauty.enabled, defaults.beauty.enabled) };
  for (const [key, fallback] of Object.entries(defaults.beauty)) {
    if (key !== "enabled") beauty[key] = hmbNormalizeFinishNumber("beauty", key, rawBeauty[key], fallback);
  }
  const film = {
    enabled: hmbBoolean(rawFilm.enabled, defaults.film.enabled),
    negative_film: hmbChoice(
      rawFilm.negative_film,
      catalog.negative,
      defaults.film.negative_film,
    ),
    print_film: hmbChoice(rawFilm.print_film, catalog.print, defaults.film.print_film),
  };
  for (const [key, fallback] of Object.entries(defaults.film)) {
    if (!["enabled", "negative_film", "print_film"].includes(key)) {
      film[key] = hmbNormalizeFinishNumber("film", key, rawFilm[key], fallback);
    }
  }

  const normalized = {
    schema_version: HMB_FINISH_LOOK_SCHEMA_VERSION,
    language: hmbLanguage(source.language),
    remote_connected: hmbBoolean(source.remote_connected, false),
    shot_catalog: shotCatalog,
    shot,
    catalog,
    finish_look: {
      schema_version: HMB_FINISH_LOOK_SCHEMA_VERSION,
      beauty,
      film,
    },
  };
  return normalized;
}

export function hmbFinishLookPublication(input) {
  return hmbNormalizeFinishLookWidgetValue(input);
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

export function hmbDropdownNavigationIndex(key, currentIndex, itemCount) {
  const count = Math.max(0, Number(itemCount) || 0);
  if (!count) return -1;
  const current = Number.isInteger(currentIndex) && currentIndex >= 0 ? currentIndex : 0;
  if (key === "ArrowDown") return (current + 1) % count;
  if (key === "ArrowUp") return (current - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return current;
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

function hmbStepField(path, label, value, disabled, language) {
  const options = HMB_FINISH_LOOK_STEPS[path];
  const index = hmbFinishLookStepIndex(path, value);
  const text = hmbFinishLookStepLabel(path, value, language);
  const lang = language === "ko" ? "ko" : "en";
  return `<label class="hmb-finish-look__field"><span>${hmbEscape(label)}</span><output data-step-label="${hmbEscape(path)}">${hmbEscape(text)}</output><input type="range" data-finish-step="${hmbEscape(path)}" value="${index}" min="0" max="${options.length - 1}" step="1" aria-label="${hmbEscape(label)}" aria-valuetext="${hmbEscape(text)}"${disabled ? " disabled" : ""}><span class="hmb-finish-look__step-ends" aria-hidden="true"><small>${hmbEscape(options[0][lang])}</small><small>${hmbEscape(options.at(-1)[lang])}</small></span></label>`;
}

function hmbStockDropdown(kind, label, value, options, disabled, note = "") {
  const optionMarkup = options.map((item) => (
    `<button type="button" role="option" tabindex="-1" data-stock-option="${hmbEscape(item)}" aria-selected="${item === value ? "true" : "false"}" class="${item === value ? "is-selected" : ""}">${hmbEscape(item)}</button>`
  )).join("");
  return `<div class="hmb-finish-look__stock" data-stock-dropdown="${hmbEscape(kind)}"><span class="hmb-finish-look__stock-label">${hmbEscape(label)}</span><button type="button" class="hmb-finish-look__stock-trigger" data-stock-trigger aria-haspopup="listbox" aria-expanded="false"${disabled ? " disabled" : ""}><span>${hmbEscape(value)}</span><i aria-hidden="true">▾</i></button><div class="hmb-finish-look__stock-menu" data-stock-menu role="listbox" hidden>${optionMarkup}</div>${note ? `<small>${hmbEscape(note)}</small>` : ""}</div>`;
}

function hmbRenderFinishLook(state) {
  const t = hmbFinishLookLabels(state.language);
  const beauty = state.finish_look.beauty;
  const film = state.finish_look.film;
  const remoteLocked = state.remote_connected;
  const paletteShotNumber = hmbFinishLookPaletteShotNumber(state);
  const shotBound = paletteShotNumber > 0;
  const shotOptions = hmbFinishLookShotOptions(state);
  const beautyDisabled = !beauty.enabled || remoteLocked;
  const filmDisabled = !film.enabled || remoteLocked;
  const reversal = state.catalog.reversal.includes(film.print_film);
  const hmbNumericField = (path, label, value, disabled) => hmbStepField(path, label, value, disabled, state.language);
  const headerMark = "FL";
  const headerTitle = "HMB Finish Look";
  const headerSubtitle = t.subtitle;
  return `
    <style>
      .hmb-finish-look :is(button,input,select,textarea){font-family:inherit}
      .hmb-finish-look__field output{color:var(--hmb-shot-soft);font-size:11px;font-weight:750;min-height:16px;overflow-wrap:anywhere}.hmb-finish-look__field input[type="range"]{width:100%;height:26px;margin:0;cursor:ew-resize;accent-color:var(--hmb-shot-accent);touch-action:pan-y}.hmb-finish-look__field .hmb-finish-look__step-ends{display:flex;justify-content:space-between;gap:8px;color:var(--hmb-muted);font-size:8px}.hmb-finish-look__step-ends small:last-child{text-align:right}.hmb-finish-look__field:has(input:disabled) output{opacity:.42}
      .hmb-finish-look{--jewel-pink:#F472B6;--jewel-blue:#3B82F6;--jewel-green:#10B981;--jewel-purple:#8B5CF6;--jewel-yellow:#EAB308;--hmb-bg:#090c16;--hmb-panel:#0f1726;--hmb-panel-2:#111c2d;--hmb-line:#263b58;--hmb-text:#e8eef7;--hmb-muted:#91a2b7;--hmb-accent:#3B82F6;--hmb-soft:#DBEAFE;position:relative;width:100%;height:100%;min-height:720px;overflow:hidden;container-type:inline-size;border:1px solid rgba(59,130,246,.52);border-radius:11px;background:radial-gradient(circle at 8% -24%,rgba(59,130,246,.2),transparent 42%),linear-gradient(180deg,#0b1020,var(--hmb-bg));color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;box-sizing:border-box;user-select:none}
      .hmb-finish-look *{box-sizing:border-box;min-width:0}.hmb-finish-look [hidden]{display:none!important}.hmb-finish-look__scroll{height:100%;min-height:720px;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable;padding-bottom:12px}.hmb-finish-look[data-dropdown-open="true"] .hmb-finish-look__scroll{padding-bottom:230px}
      .hmb-finish-look__topbar{position:sticky;z-index:30;top:0;display:flex;align-items:center;height:68px;min-height:68px;gap:16px;padding:0 16px;border-bottom:1px solid rgba(59,130,246,.35);background:linear-gradient(90deg,rgba(30,58,96,.98),rgba(9,12,22,.98))}.hmb-finish-look__mark{flex:0 0 30px;width:30px;height:30px;display:grid;place-items:center;border:1px solid rgba(59,130,246,.65);border-radius:8px;background:rgba(59,130,246,.13);color:#93c5fd;font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-finish-look__heading{display:flex;flex:1 1 auto;flex-direction:column;gap:2px;overflow:hidden}.hmb-finish-look__heading b,.hmb-finish-look__heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-finish-look__heading b{font-size:15px}.hmb-finish-look__heading span{color:var(--hmb-muted);font-size:9px}.hmb-finish-look__remote-badge{padding:4px 7px;border:1px solid rgba(244,114,182,.65);border-radius:999px;background:rgba(190,24,93,.25);color:#fbcfe8;font-size:8px;font-weight:950;letter-spacing:.12em}.hmb-finish-look__language{height:30px;min-width:58px;padding:0 10px;border:1px solid rgba(96,165,250,.55);border-radius:7px;background:#101a2a;color:#bfdbfe;font-size:12px;font-weight:800;cursor:pointer}
      .hmb-finish-look__content{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;padding:10px}.hmb-finish-look__section{border:1px solid rgba(59,130,246,.28);border-radius:9px;background:rgba(15,23,38,.9);overflow:visible}.hmb-finish-look__section-header{display:flex;align-items:center;gap:8px;min-height:39px;padding:7px 10px;border-bottom:1px solid rgba(148,163,184,.13);background:linear-gradient(90deg,rgba(59,130,246,.13),transparent)}.hmb-finish-look__section-header h2{flex:1;margin:0;color:#dbeafe;font-size:12px;letter-spacing:.055em}.hmb-finish-look__enable{display:flex;align-items:center;gap:6px;color:#cbd5e1;font-size:10px;cursor:pointer}.hmb-finish-look__enable input{accent-color:var(--hmb-accent)}.hmb-finish-look__section-body{padding:9px}.hmb-finish-look__subhead{margin:8px 0 6px;color:#7fb4f0;font-size:9px;font-weight:900;letter-spacing:.1em}.hmb-finish-look__subhead:first-child{margin-top:0}.hmb-finish-look__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.hmb-finish-look__field{display:flex;flex-direction:column;gap:4px}.hmb-finish-look__field--wide{grid-column:1/-1}.hmb-finish-look__field>span,.hmb-finish-look__stock-label{color:#b7c5d6;font-size:9px;font-weight:750}.hmb-finish-look input,.hmb-finish-look select,.hmb-finish-look button{font:inherit}.hmb-finish-look input[type="number"],.hmb-finish-look input[type="text"],.hmb-finish-look select,.hmb-finish-look__stock-trigger{width:100%;height:30px;padding:0 8px;border:1px solid rgba(148,163,184,.28);border-radius:6px;outline:none;background:#080f1b;color:#e5edf7;font-size:10px}.hmb-finish-look input:focus,.hmb-finish-look select:focus,.hmb-finish-look button:focus-visible{border-color:#60a5fa;outline:none;box-shadow:0 0 0 1px rgba(96,165,250,.5)}.hmb-finish-look input:disabled,.hmb-finish-look select:disabled,.hmb-finish-look button:disabled{opacity:.42;cursor:not-allowed}.hmb-finish-look input[aria-invalid="true"]{border-color:#fb7185}.hmb-finish-look__printer{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.hmb-finish-look__stock{position:relative;display:grid;grid-template-columns:1fr;gap:4px;margin-bottom:7px}.hmb-finish-look__stock-trigger{display:flex;align-items:center;text-align:left;cursor:pointer}.hmb-finish-look__stock-trigger span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-finish-look__stock-trigger i{color:#93c5fd;font-style:normal}.hmb-finish-look__stock small{color:#fbbf24;font-size:8px;line-height:1.25}.hmb-finish-look__stock-menu{position:absolute;z-index:80;top:calc(100% + 4px);right:0;left:0;max-height:220px;overflow:auto;padding:4px;border:1px solid #3d5c80;border-radius:6px;background:#0c1524;box-shadow:0 12px 24px rgba(0,0,0,.55)}.hmb-finish-look__stock-menu button{display:block;width:100%;min-height:28px;padding:6px 8px;border:0;border-radius:4px;background:transparent;color:#dce7f5;text-align:left;cursor:pointer}.hmb-finish-look__stock-menu button:hover,.hmb-finish-look__stock-menu button:focus-visible,.hmb-finish-look__stock-menu button.is-selected{background:#1d3b61;color:#fff}
      .hmb-finish-look__status{min-height:28px;margin:8px 10px 10px;padding:6px 9px;border:1px solid rgba(148,163,184,.16);border-radius:7px;background:#0a111d;color:#93a4b8;font-size:9px}.hmb-finish-look__status[data-tone="error"]{border-color:rgba(251,113,133,.48);color:#fda4af}.hmb-finish-look__status[data-tone="success"]{border-color:rgba(52,211,153,.4);color:#6ee7b7}
      .hmb-finish-look{--hmb-shot-accent:#64748B;--hmb-shot-rgb:100,116,139;--hmb-shot-deep:#334155;--hmb-shot-soft:#CBD5E1;--hmb-shot-line:rgba(100,116,139,.4);--hmb-shot-glow:rgba(100,116,139,.08);--hmb-accent:var(--hmb-shot-accent);--hmb-soft:var(--hmb-shot-soft);border-color:var(--hmb-shot-line);background:radial-gradient(circle at 8% -24%,var(--hmb-shot-glow),transparent 42%),linear-gradient(180deg,#0b1020,var(--hmb-bg));box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24),0 0 18px var(--hmb-shot-glow)}.hmb-finish-look[data-shot-number="1"]{--hmb-shot-accent:#F472B6;--hmb-shot-rgb:244,114,182;--hmb-shot-deep:#BE185D;--hmb-shot-soft:#FBCFE8;--hmb-shot-line:rgba(244,114,182,.5);--hmb-shot-glow:rgba(244,114,182,.2)}.hmb-finish-look[data-shot-number="2"]{--hmb-shot-accent:#3B82F6;--hmb-shot-rgb:59,130,246;--hmb-shot-deep:#1D4ED8;--hmb-shot-soft:#DBEAFE;--hmb-shot-line:rgba(59,130,246,.5);--hmb-shot-glow:rgba(59,130,246,.2)}.hmb-finish-look[data-shot-number="3"]{--hmb-shot-accent:#10B981;--hmb-shot-rgb:16,185,129;--hmb-shot-deep:#047857;--hmb-shot-soft:#D1FAE5;--hmb-shot-line:rgba(16,185,129,.5);--hmb-shot-glow:rgba(16,185,129,.2)}.hmb-finish-look[data-shot-number="4"]{--hmb-shot-accent:#8B5CF6;--hmb-shot-rgb:139,92,246;--hmb-shot-deep:#6D28D9;--hmb-shot-soft:#EDE9FE;--hmb-shot-line:rgba(139,92,246,.5);--hmb-shot-glow:rgba(139,92,246,.2)}.hmb-finish-look[data-shot-number="5"]{--hmb-shot-accent:#EAB308;--hmb-shot-rgb:234,179,8;--hmb-shot-deep:#A16207;--hmb-shot-soft:#FEF3C7;--hmb-shot-line:rgba(234,179,8,.5);--hmb-shot-glow:rgba(234,179,8,.2)}
      .hmb-finish-look__topbar{border-bottom-color:var(--hmb-shot-line);background:linear-gradient(90deg,rgba(var(--hmb-shot-rgb),.2),rgba(9,12,22,.98))}.hmb-finish-look__mark{border-color:var(--hmb-shot-line);background:rgba(var(--hmb-shot-rgb),.13);color:var(--hmb-shot-soft);box-shadow:0 0 12px var(--hmb-shot-glow)}.hmb-finish-look__section{border-color:rgba(var(--hmb-shot-rgb),.28)}.hmb-finish-look__section-header{background:linear-gradient(90deg,rgba(var(--hmb-shot-rgb),.13),transparent)}.hmb-finish-look__section-header h2,.hmb-finish-look__subhead{color:var(--hmb-shot-soft)}.hmb-finish-look input:focus,.hmb-finish-look select:focus,.hmb-finish-look button:focus-visible{border-color:var(--hmb-shot-accent);box-shadow:0 0 0 1px var(--hmb-shot-line)}.hmb-finish-look__stock-trigger i{color:var(--hmb-shot-soft)}.hmb-finish-look__stock-menu{border-color:var(--hmb-shot-line)}.hmb-finish-look__stock-menu button:hover,.hmb-finish-look__stock-menu button:focus-visible,.hmb-finish-look__stock-menu button.is-selected{background:rgba(var(--hmb-shot-rgb),.24)}.hmb-finish-look__tab.is-active{border-color:var(--hmb-shot-accent);background:rgba(var(--hmb-shot-rgb),.2);color:var(--hmb-shot-soft)}.hmb-finish-look__actions .is-primary{border-color:var(--hmb-shot-accent);background:rgba(var(--hmb-shot-rgb),.22)}
      .hmb-finish-look__shot-shell{flex:0 1 210px;width:210px;min-width:120px;max-width:210px;display:flex;align-items:center;gap:7px}.hmb-finish-look__shot-shell>span{flex:0 0 auto;color:var(--hmb-muted);font-size:8px;font-weight:900;letter-spacing:.12em}.hmb-finish-look__shot-select{width:100%;height:44px;padding:0 10px;border:1px solid var(--hmb-shot-line);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(var(--hmb-shot-rgb),.14),rgba(8,15,27,.96));color:var(--hmb-shot-soft);box-shadow:0 0 10px var(--hmb-shot-glow);font-size:13px;font-weight:800;line-height:normal}.hmb-finish-look__shot-select option{background:#0b1020;color:#e8eef7}.hmb-finish-look__shot-select:disabled{border-color:rgba(100,116,139,.28);background:#0b111c;color:#7c8a9d;box-shadow:none;opacity:.78}.hmb-finish-look__bound-badge,.hmb-finish-look__remote-badge{padding:4px 7px;border-radius:999px;font-size:8px;font-weight:950;letter-spacing:.12em;white-space:nowrap}.hmb-finish-look__bound-badge{border:1px solid var(--hmb-shot-line);background:rgba(var(--hmb-shot-rgb),.2);color:var(--hmb-shot-soft);box-shadow:0 0 10px var(--hmb-shot-glow)}.hmb-finish-look__language{border-color:var(--hmb-shot-line);color:var(--hmb-shot-soft)}
      .hmb-finish-look{--hmb-mode-rgb:244,114,182;--hmb-mode-soft:#FBCFE8;border-color:rgba(var(--hmb-mode-rgb),.5)}.hmb-finish-look__topbar{border-bottom-color:rgba(var(--hmb-mode-rgb),.48);background:linear-gradient(90deg,rgba(var(--hmb-mode-rgb),.24),rgba(9,12,22,.98));cursor:default}.hmb-finish-look__mark{border-color:rgba(var(--hmb-mode-rgb),.62);background:rgba(var(--hmb-mode-rgb),.15);color:var(--hmb-mode-soft)}.hmb-finish-look__heading b{font-weight:800}.hmb-finish-look__heading em{margin-top:1px;color:rgba(var(--hmb-mode-rgb),.82);font-size:8px;font-style:normal;font-weight:750}
      @container(max-width:780px){.hmb-finish-look__heading span{display:none}.hmb-finish-look__shot-shell{flex-basis:210px;width:210px}.hmb-finish-look__bound-badge,.hmb-finish-look__remote-badge{padding-inline:5px;font-size:7px}}@container(max-width:680px){.hmb-finish-look__content{grid-template-columns:1fr}.hmb-finish-look__topbar{gap:9px;padding-inline:10px}.hmb-finish-look__shot-shell{flex:1 1 auto;width:auto;max-width:none}.hmb-finish-look__shot-shell>span,.hmb-finish-look__bound-badge{display:none}}@container(max-width:500px){.hmb-finish-look__heading{display:flex}.hmb-finish-look__heading span,.hmb-finish-look__heading em,.hmb-finish-look__shot-shell>span,.hmb-finish-look__bound-badge{display:none}.hmb-finish-look__mark{display:none}.hmb-finish-look__shot-shell{min-width:0}.hmb-finish-look__language{min-width:46px;padding-inline:6px}}@container(max-width:400px){.hmb-finish-look__grid,.hmb-finish-look__printer{grid-template-columns:repeat(3,minmax(0,1fr))}.hmb-finish-look__remote-badge{display:none}}
    </style>
    <div class="hmb-finish-look nodrag nowheel" data-language="${state.language}" data-remote-connected="${remoteLocked ? "true" : "false"}" data-shot-number="${paletteShotNumber}" data-shot-bound="${shotBound ? "true" : "false"}" data-workspace-mode="finish" data-dropdown-open="false" tabindex="0">
      <div class="hmb-finish-look__scroll">
        <header class="hmb-finish-look__topbar"><div class="hmb-finish-look__mark" aria-hidden="true">${headerMark}</div><div class="hmb-finish-look__heading"><b>${hmbEscape(headerTitle)}</b><span>${hmbEscape(headerSubtitle)}</span></div><label class="hmb-finish-look__shot-shell nodrag" data-no-finish-toggle><span>${hmbEscape(t.shot)}</span><select class="hmb-finish-look__shot-select nodrag" data-shot-selector aria-label="Shot"${shotOptions.length > 1 ? "" : " disabled"}>${hmbFinishLookShotOptionsMarkup(state)}</select></label><span class="hmb-finish-look__bound-badge" data-shot-bound-badge${shotBound ? "" : " hidden"}>${hmbEscape(t.bound)}</span><span class="hmb-finish-look__remote-badge"${remoteLocked ? "" : " hidden"}>REMOTE</span><button type="button" class="hmb-finish-look__language nodrag" data-no-finish-toggle data-language-toggle aria-label="${hmbEscape(t.language)}">${state.language === "ko" ? "한국어" : "EN"}</button></header>
        <main class="hmb-finish-look__content">
          <section class="hmb-finish-look__section" data-finish-section="beauty"><header class="hmb-finish-look__section-header"><h2>${hmbEscape(t.beauty)}</h2><label class="hmb-finish-look__enable"><input type="checkbox" data-enable="beauty"${beauty.enabled ? " checked" : ""}${remoteLocked ? " disabled" : ""}><span>${hmbEscape(t.enable)}</span></label></header><div class="hmb-finish-look__section-body"><div class="hmb-finish-look__subhead">${hmbEscape(t.primary)}</div><div class="hmb-finish-look__grid">${hmbNumericField("beauty.soften_shadows", t.softenShadows, beauty.soften_shadows, beautyDisabled)}${hmbNumericField("beauty.shadow_threshold", t.shadowThreshold, beauty.shadow_threshold, beautyDisabled)}${hmbNumericField("beauty.saturation", t.saturation, beauty.saturation, beautyDisabled)}${hmbNumericField("beauty.brightness", t.brightness, beauty.brightness, beautyDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.advanced)}</div><div class="hmb-finish-look__grid">${hmbNumericField("beauty.glow_brightness", t.glowBrightness, beauty.glow_brightness, beautyDisabled)}${hmbNumericField("beauty.glow_threshold", t.glowThreshold, beauty.glow_threshold, beautyDisabled)}${hmbNumericField("beauty.glow_width", t.glowWidth, beauty.glow_width, beautyDisabled)}${hmbNumericField("beauty.soft_focus", t.softFocus, beauty.soft_focus, beautyDisabled)}${hmbNumericField("beauty.blur_amount", t.blurAmount, beauty.blur_amount, beautyDisabled)}${hmbNumericField("beauty.pore_size", t.poreSize, beauty.pore_size, beautyDisabled)}${hmbNumericField("beauty.reduce_shine", t.reduceShine, beauty.reduce_shine, beautyDisabled)}</div></div></section>
          <section class="hmb-finish-look__section" data-finish-section="film"><header class="hmb-finish-look__section-header"><h2>${hmbEscape(t.film)}</h2><label class="hmb-finish-look__enable"><input type="checkbox" data-enable="film"${film.enabled ? " checked" : ""}${remoteLocked ? " disabled" : ""}><span>${hmbEscape(t.enable)}</span></label></header><div class="hmb-finish-look__section-body"><div class="hmb-finish-look__subhead">${hmbEscape(t.filmStock)}</div>${hmbStockDropdown("negative_film", t.negativeFilm, film.negative_film, state.catalog.negative, filmDisabled || reversal, reversal ? t.reversalNote : "")}${hmbStockDropdown("print_film", t.printFilm, film.print_film, state.catalog.print, filmDisabled)}<div class="hmb-finish-look__subhead">${hmbEscape(t.colorCorrection)}</div><div class="hmb-finish-look__grid">${hmbNumericField("film.scale_cc", t.scaleCc, film.scale_cc, filmDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.printerLights)}</div><div class="hmb-finish-look__printer">${hmbNumericField("film.printer_light_r", "R", film.printer_light_r, filmDisabled)}${hmbNumericField("film.printer_light_g", "G", film.printer_light_g, filmDisabled)}${hmbNumericField("film.printer_light_b", "B", film.printer_light_b, filmDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.tone)}</div><div class="hmb-finish-look__grid">${hmbNumericField("film.input_gamma", t.inputGamma, film.input_gamma, filmDisabled)}${hmbNumericField("film.output_gamma", t.outputGamma, film.output_gamma, filmDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.exposure)}</div><div class="hmb-finish-look__grid">${hmbNumericField("film.negative_exposure", t.negativeExposure, film.negative_exposure, filmDisabled)}${hmbNumericField("film.print_exposure", t.printExposure, film.print_exposure, filmDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.glow)}</div><div class="hmb-finish-look__grid">${hmbNumericField("film.glow_brightness", t.glowBrightness, film.glow_brightness, filmDisabled)}</div><div class="hmb-finish-look__subhead">${hmbEscape(t.advanced)}</div><div class="hmb-finish-look__grid">${hmbNumericField("film.soft_focus", t.softFocus, film.soft_focus, filmDisabled)}${hmbNumericField("film.vignette", t.vignette, film.vignette, filmDisabled)}</div></div></section>
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

export default function HMBFinishLookLibraryWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  const incoming = props || container.__hmbFinishLookLatestProps || {};
  container.__hmbFinishLookLatestProps = incoming;
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
  let listenerCleanups = [];
  let publicationOwner = 0;
  let openDropdown = "";

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

  const remount = () => {
    if (disposed) return;
    clearListeners();
    openDropdown = "";
    container.innerHTML = hmbRenderFinishLookWidget(state);
    container.classList?.add("nodrag");
    container.setAttribute?.("data-hmb-node-delete-protected", "true");
    installInteractions();
  };

  const rollback = (previous, owner, error) => {
    if (disposed || owner !== publicationOwner) return;
    state = previous;
    remount();
    hmbSetStatus(container, String(error?.message || error || "Publication failed."), "error");
  };

  const publish = (previous = cloneState(), repaint = true) => {
    const liveProps = container.__hmbFinishLookLatestProps || {};
    if (typeof liveProps.onChange !== "function") {
      rollback(previous, publicationOwner, new Error("Finish Look state transport is unavailable."));
      return false;
    }
    const owner = ++publicationOwner;
    const payload = hmbFinishLookPublication(state);
    let result;
    try { result = liveProps.onChange(payload); } catch (error) { rollback(previous, owner, error); return false; }
    const persisted = hmbFinishLookPublication(state);
    container.__hmbFinishLookLatestProps = {
      ...liveProps,
      value: persisted,
      parameterValue: persisted,
      defaultValue: persisted,
    };
    if (repaint) remount();
    if (result && typeof result.then === "function") Promise.resolve(result).catch((error) => rollback(previous, owner, error));
    return true;
  };

  const mutate = (mutator, repaint = true) => {
    const previous = cloneState();
    mutator(state);
    return publish(previous, repaint);
  };

  function installStockDropdowns(root, ownerDocument) {
    const close = (restoreFocus = false) => {
      if (!openDropdown) return;
      const shell = root.querySelector?.(`[data-stock-dropdown="${openDropdown}"]`);
      shell?.querySelector?.("[data-stock-menu]")?.setAttribute?.("hidden", "");
      const trigger = shell?.querySelector?.("[data-stock-trigger]");
      trigger?.setAttribute?.("aria-expanded", "false");
      root.setAttribute?.("data-dropdown-open", "false");
      openDropdown = "";
      if (restoreFocus) trigger?.focus?.();
    };
    const open = (kind, requestedIndex = null) => {
      close(false);
      const shell = root.querySelector?.(`[data-stock-dropdown="${kind}"]`);
      const trigger = shell?.querySelector?.("[data-stock-trigger]");
      const menu = shell?.querySelector?.("[data-stock-menu]");
      if (!shell || trigger?.disabled || !menu) return;
      openDropdown = kind;
      menu.removeAttribute?.("hidden");
      trigger.setAttribute?.("aria-expanded", "true");
      root.setAttribute?.("data-dropdown-open", "true");
      menu.scrollIntoView?.({ block: "nearest" });
      const options = Array.from(menu.querySelectorAll?.("[data-stock-option]") || []);
      const selected = options.findIndex((item) => item.getAttribute?.("aria-selected") === "true");
      const index = requestedIndex === null ? Math.max(0, selected) : requestedIndex;
      options[index]?.focus?.();
    };
    for (const shell of root.querySelectorAll?.("[data-stock-dropdown]") || []) {
      const kind = shell.getAttribute("data-stock-dropdown");
      const trigger = shell.querySelector?.("[data-stock-trigger]");
      const menu = shell.querySelector?.("[data-stock-menu]");
      const options = Array.from(menu?.querySelectorAll?.("[data-stock-option]") || []);
      bind(trigger, "click", () => (openDropdown === kind ? close(true) : open(kind)));
      bind(trigger, "keydown", (event) => {
        if (!["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
          if (event.key === "Escape") { event.preventDefault(); close(true); }
          return;
        }
        event.preventDefault();
        const selected = options.findIndex((item) => item.getAttribute?.("aria-selected") === "true");
        open(kind, event.key === "ArrowUp" ? Math.max(0, selected) : Math.max(0, selected));
      });
      options.forEach((option, index) => {
        const select = () => {
          if (state.remote_connected) return;
          const value = option.getAttribute("data-stock-option");
          const catalog = kind === "negative_film" ? state.catalog.negative : state.catalog.print;
          if (!catalog.includes(value)) return;
          close(false);
          mutate((next) => { next.finish_look.film[kind] = value; }, true);
        };
        bind(option, "click", select);
        bind(option, "keydown", (event) => {
          if (["Enter", " "].includes(event.key)) { event.preventDefault(); select(); return; }
          if (event.key === "Escape") { event.preventDefault(); close(true); return; }
          if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          options[hmbDropdownNavigationIndex(event.key, index, options.length)]?.focus?.();
        });
      });
    }
    bind(ownerDocument, "pointerdown", (event) => {
      if (openDropdown && !event.target?.closest?.("[data-stock-dropdown]")) close(false);
    }, true);
    bind(ownerDocument, "keydown", (event) => {
      if (openDropdown && event.key === "Escape") { event.preventDefault?.(); close(true); }
    }, true);
  }

  function installInteractions() {
    const root = container.querySelector?.(".hmb-finish-look");
    if (!root) return;
    const ownerDocument = container.ownerDocument || (typeof document !== "undefined" ? document : null);
    // No workspace double-click handler: Finish Look remains the finish editor.
    const shotSelect = container.querySelector?.("[data-shot-selector]");
    bind(shotSelect, "change", () => {
      const option = hmbFinishLookShotOptions(state).find((item) => item.key === shotSelect?.value);
      if (!option) {
        hmbApplyFinishLookShotFeedback(container, state);
        return;
      }
      const previous = cloneState();
      state.shot = option.only ? hmbFinishLookOnlyShot() : {
        channel_uuid: option.channel_uuid,
        shot_uuid: option.shot_uuid,
        number: option.number,
        name: option.name,
      };
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
        mutate((next) => { next.finish_look[group].enabled = Boolean(toggle.checked); }, true);
      });
    }
    for (const input of container.querySelectorAll?.("[data-finish-step]") || []) {
      const path = input.getAttribute("data-finish-step");
      const preview = () => {
        if (input.disabled || state.remote_connected) return null;
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
        const value = preview();
        if (value === null || hmbGetPath(state.finish_look, path) === value) return;
        const previous = cloneState();
        hmbSetPath(state.finish_look, path, value);
        publish(previous, false);
      });
    }
    installStockDropdowns(root, ownerDocument);
    const stopInteriorInteraction = (event) => {
      if (event.target?.closest?.("button,input,select,textarea,[role='option']")) event.stopPropagation?.();
    };
    const stopInteriorDelete = (event) => {
      if (["Backspace", "Delete"].includes(event.key)) event.stopPropagation?.();
    };
    bind(container, "pointerdown", stopInteriorInteraction);
    bind(container, "keydown", stopInteriorDelete);
    const guardDelete = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
    const ownerWindow = ownerDocument?.defaultView || (typeof window !== "undefined" ? window : null);
    bind(ownerWindow, "keydown", guardDelete, true);
  }

  container.__hmbFinishLookApplyProps = (nextProps = {}) => {
    if (disposed) return;
    publicationOwner += 1;
    const previousFingerprint = hmbFinishLookNonShotStateFingerprint(state);
    const nextState = hmbNormalizeFinishLookWidgetValue(nextProps);
    container.__hmbFinishLookLatestProps = nextProps;
    state = nextState;
    const authoredUnchanged = previousFingerprint === hmbFinishLookNonShotStateFingerprint(nextState);
    if (authoredUnchanged && hmbApplyFinishLookShotFeedback(container, nextState)) {
      return;
    }
    remount();
  };
  const cleanup = () => {
    disposed = true;
    publicationOwner += 1;
    clearListeners();
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.classList?.remove("nodrag");
    container.innerHTML = "";
    if (container.__hmbFinishLookCleanup === cleanup) delete container.__hmbFinishLookCleanup;
    delete container.__hmbFinishLookApplyProps;
    delete container.__hmbFinishLookLatestProps;
  };
  container.__hmbFinishLookCleanup = cleanup;
  remount();
  return {
    cleanup: container.__hmbFinishLookCleanupProxy,
    update(nextProps) { container.__hmbFinishLookApplyProps?.(nextProps || {}); },
  };
}
