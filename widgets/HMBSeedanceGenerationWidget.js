const HMB_SHOT_ONLY_KEY = "__hmb_shot_only__";
const HMB_SEEDANCE_PREVIEW_SCHEMA = "hmb-seedance-generation-preview";
const HMB_SEEDANCE_PREVIEW_VERSION = 1;

const PREVIEW_PHASE_ALIASES = Object.freeze({
  "": "idle",
  ready: "idle",
  resolving_inputs: "preparing",
  preparing_output: "preparing",
  connecting_broker: "preparing",
  preparing_media: "preparing",
  resuming: "retrieving",
  retrying_same_request: "retrieving",
  refreshing: "retrieving",
  completed: "succeeded",
  complete: "succeeded",
  cancelled: "cancelled_locally",
  error: "failed",
});

const PREVIEW_PHASES = new Set([
  "idle", "preparing", "submitting", "queued", "running", "retrieving",
  "downloading", "verifying", "cancelled_locally", "timed_out",
  "submission_unknown", "failed", "succeeded",
]);

export const HMB_SEEDANCE_JEWEL_NIGHT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});

const SHOT_THEME = Object.freeze({
  1: Object.freeze({ rgb: "244,114,182", soft: "#FBCFE8" }),
  2: Object.freeze({ rgb: "59,130,246", soft: "#DBEAFE" }),
  3: Object.freeze({ rgb: "16,185,129", soft: "#D1FAE5" }),
  4: Object.freeze({ rgb: "139,92,246", soft: "#EDE9FE" }),
  5: Object.freeze({ rgb: "234,179,8", soft: "#FEF3C7" }),
});

function text(value, limit = 128) {
  return String(value ?? "").trim().replace(/\s+/g, " ").slice(0, limit);
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

function boundedInteger(value, { min = 0, max = Number.MAX_SAFE_INTEGER } = {}) {
  const number = Number(value);
  if (!Number.isSafeInteger(number)) return min;
  return Math.min(max, Math.max(min, number));
}

function canonicalPreviewPhase(value) {
  const raw = text(value, 48).toLowerCase().replace(/[ -]+/g, "_");
  const phase = PREVIEW_PHASE_ALIASES[raw] ?? raw;
  return PREVIEW_PHASES.has(phase) ? phase : "idle";
}

export function hmbSeedanceGenerationPreview(value) {
  const candidate = value && typeof value === "object" && !Array.isArray(value)
    ? (value.generation && typeof value.generation === "object" ? value.generation : value)
    : {};
  if (
    candidate.schema !== HMB_SEEDANCE_PREVIEW_SCHEMA
    || Number(candidate.version) !== HMB_SEEDANCE_PREVIEW_VERSION
  ) {
    return {
      schema: HMB_SEEDANCE_PREVIEW_SCHEMA,
      version: HMB_SEEDANCE_PREVIEW_VERSION,
      phase: "idle",
      job_id: "",
      started_at_ms: 0,
      elapsed_seconds: 0,
      guidance: "",
      action: "none",
      has_existing_video: false,
      media_revision: 0,
    };
  }
  const action = text(candidate.action, 32).toLowerCase() === "refresh_existing"
    ? "refresh_existing" : "none";
  return {
    schema: HMB_SEEDANCE_PREVIEW_SCHEMA,
    version: HMB_SEEDANCE_PREVIEW_VERSION,
    phase: canonicalPreviewPhase(candidate.phase),
    job_id: text(candidate.job_id, 160),
    started_at_ms: boundedInteger(candidate.started_at_ms, { max: 9_999_999_999_999 }),
    elapsed_seconds: boundedInteger(candidate.elapsed_seconds, { max: 604_800 }),
    guidance: text(candidate.guidance, 360),
    action,
    has_existing_video: candidate.has_existing_video === true,
    media_revision: boundedInteger(candidate.media_revision),
  };
}

function elapsedLabel(seconds) {
  const value = boundedInteger(seconds, { max: 604_800 });
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainder = value % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function hmbSeedancePreviewPresentation(value, options = {}) {
  const generation = hmbSeedanceGenerationPreview(value);
  const playableVideo = options.playableVideo === true;
  const visibleVideo = options.visibleVideo === true;
  const elapsed = elapsedLabel(generation.elapsed_seconds);
  const base = {
    visible: true,
    phase: generation.phase,
    mode: generation.has_existing_video && visibleVideo ? "badge" : "center",
    title: "",
    detail: generation.guidance,
    elapsed: "",
    busy: false,
    tone: "neutral",
    action: generation.action,
  };
  switch (generation.phase) {
    case "preparing":
      return { ...base, title: "준비 중…", detail: base.detail || "입력과 저장 위치를 확인하고 있습니다.", busy: true };
    case "submitting":
      return { ...base, title: "작업 제출 중…", detail: base.detail || "FN AI Broker에 작업을 안전하게 전달하고 있습니다.", busy: true };
    case "queued":
      return { ...base, title: "렌더 대기 중…", detail: base.detail || "서버 렌더 순서를 기다리고 있습니다.", elapsed, busy: true };
    case "running":
      return { ...base, title: "렌더 중…", detail: base.detail || "서버에서 영상을 생성하고 있습니다.", elapsed, busy: true };
    case "retrieving":
      return { ...base, title: "기존 작업 결과 확인 중…", detail: base.detail || "새 작업을 만들지 않고 기존 작업만 확인합니다.", busy: true };
    case "downloading":
      return { ...base, title: "완료된 영상 다운로드 중…", detail: base.detail || "서버 결과를 로컬 출력으로 가져오고 있습니다.", busy: true };
    case "verifying":
      return { ...base, title: "영상 검증 중…", detail: base.detail || "다운로드된 MP4를 재생 검증하고 있습니다.", busy: true };
    case "cancelled_locally":
      return {
        ...base,
        title: "로컬 조회가 중단되었습니다",
        detail: base.detail || "서버 렌더는 계속 진행될 수 있습니다.",
        tone: "warning",
      };
    case "timed_out":
      return {
        ...base,
        title: "자동 조회 시간이 초과되었습니다",
        detail: base.detail || "서버 렌더는 계속 진행될 수 있습니다.",
        tone: "warning",
      };
    case "submission_unknown":
      return {
        ...base,
        title: "제출 결과 확인이 필요합니다",
        detail: base.detail || "새 작업을 제출하지 말고 기존 요청 결과를 확인하세요.",
        tone: "warning",
      };
    case "failed":
      return {
        ...base,
        title: "영상 생성에 실패했습니다",
        detail: base.detail || "Status의 오류 내용을 확인하세요.",
        tone: "error",
      };
    case "succeeded":
      return playableVideo
        ? { ...base, visible: false, action: "none" }
        : {
            ...base,
            title: "완료 영상을 준비 중…",
            detail: base.detail || "영상이 재생 가능해지는 즉시 표시합니다.",
            busy: true,
            action: "none",
          };
    default:
      return { ...base, visible: false, action: "none" };
  }
}

export function hmbSeedanceNextChangeOwner(container) {
  const next = Math.max(0, Number(container?.__hmbSeedanceChangeOwner) || 0) + 1;
  if (container) container.__hmbSeedanceChangeOwner = next;
  return next;
}

export function hmbSeedanceOwnsChange(container, owner) {
  return Math.max(0, Number(container?.__hmbSeedanceChangeOwner) || 0) === owner;
}

function uuid(value) {
  const normalized = text(value).toLowerCase();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(normalized)
    ? normalized : "";
}

export function hmbSeedanceShotCatalog(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  if (JSON.stringify(Object.keys(source).sort()) !== JSON.stringify([
    "channel_uuid", "generation", "metadata_sha256", "publisher_instance_uuid",
    "schema", "shots", "version",
  ])) return {};
  const publisher = uuid(source.publisher_instance_uuid);
  const channel = uuid(source.channel_uuid);
  const generation = Number(source.generation);
  const metadataSha256 = text(source.metadata_sha256, 64).toLowerCase();
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
  const numbers = new Set();
  const shots = [];
  for (const raw of source.shots) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    if (JSON.stringify(Object.keys(raw).sort()) !== JSON.stringify([
      "name", "number", "revision", "shot_uuid",
    ])) return {};
    const shotUuid = uuid(raw.shot_uuid);
    const number = Number(raw.number);
    const name = text(raw.name);
    const revision = Number(raw.revision);
    if (
      !shotUuid
      || shotIds.has(shotUuid)
      || !Number.isInteger(number)
      || number < 1
      || number > 5
      || numbers.has(number)
      || !name
      || name !== raw.name
      || !Number.isSafeInteger(revision)
      || revision < 0
    ) return {};
    shotIds.add(shotUuid);
    numbers.add(number);
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

export function hmbSeedanceShotState(props) {
  const candidate = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  let raw = candidate;
  if (typeof candidate === "string") {
    try { raw = JSON.parse(candidate); } catch { raw = {}; }
  }
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const catalog = hmbSeedanceShotCatalog(source.shot_catalog);
  const requested = source.shot && typeof source.shot === "object" ? source.shot : {};
  const requestedChannel = uuid(requested.channel_uuid);
  const requestedUuid = uuid(requested.shot_uuid);
  const requestedSelection = catalog.channel_uuid === requestedChannel
    ? catalog.shots?.find((shot) => shot.shot_uuid === requestedUuid) || null
    : null;
  const selected = requestedSelection || null;
  return {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: catalog,
    shot: selected ? {
      channel_uuid: catalog.channel_uuid,
      shot_uuid: selected.shot_uuid,
      number: selected.number,
      name: selected.name,
    } : {
      channel_uuid: "",
      shot_uuid: "",
      number: 1,
      name: "Only",
    },
    generation: hmbSeedanceGenerationPreview(source.generation),
  };
}

export function hmbSeedanceShotOptions(state) {
  const catalog = state?.shot_catalog;
  const options = [{
    key: HMB_SHOT_ONLY_KEY,
    channel_uuid: "",
    shot_uuid: "",
    number: 1,
    name: "Only",
    only: true,
    waiting: false,
  }];
  if (!catalog?.channel_uuid || !Array.isArray(catalog.shots) || !catalog.shots.length) {
    return options;
  }
  for (const shot of catalog.shots) {
    options.push({
      key: `${catalog.channel_uuid}\u001f${shot.shot_uuid}`,
      channel_uuid: catalog.channel_uuid,
      ...shot,
      waiting: false,
    });
  }
  return options;
}

export function hmbSeedancePaletteShotNumber(state) {
  const shot = state?.shot && typeof state.shot === "object" ? state.shot : {};
  const catalog = state?.shot_catalog && typeof state.shot_catalog === "object"
    ? state.shot_catalog : {};
  if (!shot.channel_uuid || !shot.shot_uuid || catalog.channel_uuid !== shot.channel_uuid) return 1;
  const selected = (catalog.shots || []).find((item) => item.shot_uuid === shot.shot_uuid);
  return selected && HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[selected.number] ? selected.number : 1;
}

export function hmbSeedanceShotAccent(state) {
  return HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[hmbSeedancePaletteShotNumber(state)];
}

function optionLabel(item) {
  if (item.only) return "Only";
  return `${String(item.number).padStart(2, "0")} · ${item.name}`;
}

function optionMarkup(state) {
  const currentKey = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}` : HMB_SHOT_ONLY_KEY;
  return hmbSeedanceShotOptions(state).map((item) => {
    const label = optionLabel(item);
    return `<option value="${escapeHtml(item.key)}"${item.key === currentKey ? " selected" : ""}${item.waiting ? " disabled" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

export function hmbSeedanceSyncShotSelect(select, state) {
  if (!select) return false;
  const desired = hmbSeedanceShotOptions(state).map((item) => ({
    value: item.key,
    label: optionLabel(item),
  }));
  const current = Array.from(select.options || []);
  const optionsChanged = current.length !== desired.length || desired.some((item, index) => {
    const option = current[index];
    return !option
      || String(option.value) !== item.value
      || String(option.textContent ?? option.text ?? "") !== item.label;
  });
  if (optionsChanged) select.innerHTML = optionMarkup(state);
  const expected = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}`
    : HMB_SHOT_ONLY_KEY;
  if (String(select.value || "") !== expected) select.value = expected;
  select.disabled = false;
  return optionsChanged;
}

function hmbSeedanceSetStatus(container, message = "", detail = "") {
  const status = container?.querySelector?.(".hmb-seedance-shot__status");
  if (!status) return false;
  status.textContent = String(message || "");
  status.setAttribute?.("title", message ? String(detail?.message || detail || message) : "");
  return true;
}

function render(state) {
  const number = hmbSeedancePaletteShotNumber(state);
  const accent = HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[number];
  const theme = SHOT_THEME[number];
  return `
    <style>
      .hmb-seedance-shot{--shot-accent:${accent};--shot-rgb:${theme.rgb};--shot-soft:${theme.soft};position:relative;width:100%;height:64px;overflow:hidden;box-sizing:border-box;border:1px solid rgba(var(--shot-rgb),.5);border-radius:11px;background:radial-gradient(circle at 8% -45%,rgba(var(--shot-rgb),.25),transparent 54%),linear-gradient(90deg,rgba(var(--shot-rgb),.2),rgba(14,23,38,.96) 46%,#060912);color:#e6edf7;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 24px rgba(0,0,0,.24),0 0 18px rgba(var(--shot-rgb),.18);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none}
      .hmb-seedance-shot *{box-sizing:border-box;min-width:0}.hmb-seedance-shot__row{height:100%;display:flex;align-items:center;gap:11px;padding:8px 13px}.hmb-seedance-shot__mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(var(--shot-rgb),.52);border-radius:8px;background:linear-gradient(145deg,rgba(var(--shot-rgb),.14),rgba(5,9,16,.86));color:var(--shot-accent);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px rgba(var(--shot-rgb),.19);font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-seedance-shot__title{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e6edf7;font-size:14px;font-weight:850}.hmb-seedance-shot__status{flex:0 1 190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fb7185;font-size:8px;font-weight:800;text-align:right}.hmb-seedance-shot__status:empty{display:none}.hmb-seedance-shot__select{flex:0 1 210px;width:210px;height:29px;margin-left:auto;padding:0 28px 0 10px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(255,255,255,.04),transparent),rgba(var(--shot-rgb),.16);color:var(--shot-soft);box-shadow:inset 0 1px 0 rgba(255,255,255,.045),0 0 12px rgba(var(--shot-rgb),.18);font:inherit;font-size:10px;font-weight:850;letter-spacing:.035em}.hmb-seedance-shot__select:focus{border-color:var(--shot-accent);box-shadow:0 0 0 2px rgba(var(--shot-rgb),.18)}.hmb-seedance-shot__select option{background:#0b1020;color:#e6edf7}@container(max-width:360px){.hmb-seedance-shot__status{display:none}.hmb-seedance-shot__select{flex-basis:120px;width:120px}.hmb-seedance-shot__title{font-size:12px}}
      /* Match the Prompt header while preserving the existing selector position and responsive width. */
      .hmb-seedance-shot__title{font-size:15px;font-weight:800;letter-spacing:.01em;line-height:normal}
      .hmb-seedance-shot__select{height:44px;font-size:13px;font-weight:800;line-height:normal}
      .hmb-seedance-shot__number{flex:0 0 auto;min-width:34px;padding:5px 7px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;color:var(--shot-soft);font-size:11px;font-weight:900;text-align:center}
      .hmb-seedance-preview-overlay{position:absolute;inset:0;z-index:24;display:flex;align-items:center;justify-content:center;padding:18px;pointer-events:none;color:#f8fafc;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif}
      .hmb-seedance-preview-overlay[data-mode="center"]{background:radial-gradient(circle at 50% 42%,rgba(30,41,59,.34),rgba(0,0,0,.76) 74%)}
      .hmb-seedance-preview-overlay[data-mode="badge"]{align-items:flex-start;justify-content:flex-start;padding:10px;background:linear-gradient(180deg,rgba(0,0,0,.38),transparent 44%)}
      .hmb-seedance-preview-overlay__panel{display:flex;flex-direction:column;align-items:center;gap:7px;max-width:min(420px,88%);padding:15px 18px;border:1px solid rgba(148,163,184,.2);border-radius:12px;background:rgba(3,7,18,.8);box-shadow:0 14px 34px rgba(0,0,0,.32);backdrop-filter:blur(8px);text-align:center}
      .hmb-seedance-preview-overlay[data-mode="badge"] .hmb-seedance-preview-overlay__panel{align-items:flex-start;max-width:min(360px,78%);padding:8px 11px;gap:3px;border-radius:8px;text-align:left;background:rgba(3,7,18,.76)}
      .hmb-seedance-preview-overlay__indicator{width:22px;height:22px;border:2px solid rgba(255,255,255,.18);border-top-color:#e2e8f0;border-radius:50%}
      .hmb-seedance-preview-overlay[data-mode="badge"] .hmb-seedance-preview-overlay__indicator{width:13px;height:13px;position:absolute;margin:2px 0 0 -1px}
      .hmb-seedance-preview-overlay[data-busy="true"] .hmb-seedance-preview-overlay__indicator{animation:hmb-seedance-preview-spin .85s linear infinite}
      .hmb-seedance-preview-overlay[data-busy="false"] .hmb-seedance-preview-overlay__indicator{border-color:#f59e0b;background:#f59e0b;box-shadow:0 0 13px rgba(245,158,11,.5)}
      .hmb-seedance-preview-overlay[data-tone="error"] .hmb-seedance-preview-overlay__indicator{border-color:#fb7185;background:#fb7185;box-shadow:0 0 13px rgba(251,113,133,.5)}
      .hmb-seedance-preview-overlay__title{font-size:14px;font-weight:850;letter-spacing:.01em;line-height:1.3}
      .hmb-seedance-preview-overlay[data-mode="badge"] .hmb-seedance-preview-overlay__title{padding-left:19px;font-size:11px}
      .hmb-seedance-preview-overlay__detail{color:#aeb9c9;font-size:11px;line-height:1.45}
      .hmb-seedance-preview-overlay[data-mode="badge"] .hmb-seedance-preview-overlay__detail{font-size:9px}
      .hmb-seedance-preview-overlay__elapsed{color:#cbd5e1;font-variant-numeric:tabular-nums;font-size:10px;font-weight:750}
      .hmb-seedance-preview-overlay__action{margin-top:5px;padding:7px 11px;border:1px solid rgba(var(--shot-rgb),.7);border-radius:7px;background:rgba(var(--shot-rgb),.2);color:var(--shot-soft);font:inherit;font-size:10px;font-weight:850;cursor:pointer;pointer-events:auto}
      .hmb-seedance-preview-overlay__action:hover{background:rgba(var(--shot-rgb),.34)}.hmb-seedance-preview-overlay__action:disabled{cursor:wait;opacity:.55}
      @keyframes hmb-seedance-preview-spin{to{transform:rotate(360deg)}}
    </style>
    <div class="hmb-seedance-shot nodrag" data-shot-number="${number}">
      <div class="hmb-seedance-shot__row">
        <div class="hmb-seedance-shot__mark" aria-hidden="true">SD</div>
        <div class="hmb-seedance-shot__title">HMBSeedanceGeneration</div>
        <span class="hmb-seedance-shot__status" role="status" aria-live="polite" aria-atomic="true"></span>
        <span class="hmb-seedance-shot__number" data-seedance-shot-number>${state.shot.shot_uuid ? String(state.shot.number).padStart(2, "0") : "Only"}</span>
        <select class="hmb-seedance-shot__select nodrag" aria-label="Shot">${optionMarkup(state)}</select>
      </div>
    </div>`;
}

function compactHost(container) {
  if (!container?.style) return;
  for (const [name, value] of [
    ["height", "64px"], ["min-height", "64px"], ["max-height", "64px"],
    ["flex", "0 0 64px"], ["flex-basis", "64px"], ["overflow", "hidden"],
    ["box-sizing", "border-box"],
  ]) container.style.setProperty(name, value, "important");
  container.classList?.remove("nopan", "nowheel");
  container.classList?.add("nodrag");
}

function hmbSeedanceNodeRoot(container) {
  let current = container?.parentElement || null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) return null;
  }
  return null;
}

function classTokens(element) {
  return String(element?.className || "").split(/\s+/).filter(Boolean);
}

export function hmbSeedanceFindPreviewRegion(container) {
  const nodeRoot = hmbSeedanceNodeRoot(container);
  if (!nodeRoot) return null;
  const parameter = nodeRoot.querySelector?.('[data-parameter-name="video_url"]')
    || nodeRoot.querySelector?.(".video_url");
  if (!parameter || parameter.contains?.(container)) return null;
  const modern = parameter.querySelector?.("[data-vp-video-area]");
  if (modern) return modern;
  const video = parameter.querySelector?.("video[data-raw-video-value]")
    || parameter.querySelector?.("video");
  if (video?.parentElement && parameter.contains?.(video.parentElement)) {
    return video.parentElement;
  }
  const candidates = Array.from(parameter.querySelectorAll?.("div") || []).reverse();
  return candidates.find((candidate) => {
    const tokens = new Set(classTokens(candidate));
    return tokens.has("justify-center")
      && tokens.has("items-center")
      && tokens.has("w-full")
      && tokens.has("h-full");
  }) || null;
}

function previewVideo(region) {
  return region?.querySelector?.("video[data-raw-video-value]")
    || region?.querySelector?.("video")
    || null;
}

function videoIdentity(video) {
  return text(
    video?.getAttribute?.("data-raw-video-value")
      || video?.currentSrc
      || video?.src,
    2048,
  );
}

function setElementText(element, value) {
  const next = String(value || "");
  if (element && element.textContent !== next) element.textContent = next;
}

function ensurePreviewRegionPosition(region) {
  if (!region?.style || region.getAttribute?.("data-hmb-seedance-preview-positioned") === "true") {
    return;
  }
  const inline = region.style.getPropertyValue?.("position") || region.style.position || "";
  region.setAttribute?.("data-hmb-seedance-preview-prior-position", inline);
  region.setAttribute?.("data-hmb-seedance-preview-positioned", "true");
  if (!inline) region.style.setProperty?.("position", "relative");
}

function restorePreviewRegionPosition(region) {
  if (!region?.style || region.getAttribute?.("data-hmb-seedance-preview-positioned") !== "true") {
    return;
  }
  const prior = region.getAttribute?.("data-hmb-seedance-preview-prior-position") || "";
  if (prior) region.style.setProperty?.("position", prior);
  else region.style.removeProperty?.("position");
  region.removeAttribute?.("data-hmb-seedance-preview-prior-position");
  region.removeAttribute?.("data-hmb-seedance-preview-positioned");
}

function createPreviewOverlay(region) {
  const documentRef = region?.ownerDocument || (typeof document !== "undefined" ? document : null);
  if (!documentRef?.createElement) return null;
  const overlay = documentRef.createElement("div");
  overlay.className = "hmb-seedance-preview-overlay nodrag nowheel";
  overlay.setAttribute("role", "status");
  overlay.setAttribute("aria-live", "polite");
  overlay.setAttribute("aria-atomic", "true");
  const panel = documentRef.createElement("div");
  panel.className = "hmb-seedance-preview-overlay__panel";
  const indicator = documentRef.createElement("div");
  indicator.className = "hmb-seedance-preview-overlay__indicator";
  indicator.setAttribute("aria-hidden", "true");
  const title = documentRef.createElement("div");
  title.className = "hmb-seedance-preview-overlay__title";
  const detail = documentRef.createElement("div");
  detail.className = "hmb-seedance-preview-overlay__detail";
  const elapsed = documentRef.createElement("div");
  elapsed.className = "hmb-seedance-preview-overlay__elapsed";
  const action = documentRef.createElement("button");
  action.className = "hmb-seedance-preview-overlay__action nodrag";
  action.type = "button";
  action.setAttribute("data-hmb-seedance-preview-action", "refresh_existing");
  action.textContent = "기존 작업 결과 확인";
  panel.append(indicator, title, detail, elapsed, action);
  overlay.append(panel);
  region.append(overlay);
  return overlay;
}

function removePreviewVideoListeners(container) {
  const binding = container?.__hmbSeedancePreviewVideoBinding;
  if (!binding) return;
  binding.video?.removeEventListener?.("canplay", binding.onCanPlay);
  binding.video?.removeEventListener?.("loadeddata", binding.onCanPlay);
  binding.video?.removeEventListener?.("emptied", binding.onEmptied);
  delete container.__hmbSeedancePreviewVideoBinding;
}

function schedulePreviewSync(container) {
  if (!container || container.__hmbSeedancePreviewSyncScheduled) return;
  container.__hmbSeedancePreviewSyncScheduled = true;
  const run = () => {
    delete container.__hmbSeedancePreviewSyncScheduled;
    if (container.__hmbSeedancePreviewDisposed) return;
    hmbSeedanceSyncPreviewOverlay(
      container,
      hmbSeedanceShotState(container.__hmbSeedanceLatestProps || {}),
      container.__hmbSeedancePreviewOnRetrieve,
    );
  };
  if (typeof queueMicrotask === "function") queueMicrotask(run);
  else Promise.resolve().then(run);
}

function bindPreviewVideo(container, video) {
  const identity = videoIdentity(video);
  const previous = container?.__hmbSeedancePreviewVideoBinding;
  if (previous?.video === video && previous.identity === identity) return;
  removePreviewVideoListeners(container);
  if (!container || !video) return;
  const binding = {
    video,
    identity,
    canPlay: Number(video.readyState) >= 3,
    awaitingRevision: null,
    confirmedRevision: null,
    onCanPlay: null,
    onEmptied: null,
  };
  binding.onCanPlay = () => {
    binding.canPlay = true;
    if (binding.awaitingRevision !== null) {
      binding.confirmedRevision = binding.awaitingRevision;
    }
    schedulePreviewSync(container);
  };
  binding.onEmptied = () => {
    binding.canPlay = false;
    schedulePreviewSync(container);
  };
  video.addEventListener?.("canplay", binding.onCanPlay);
  video.addEventListener?.("loadeddata", binding.onCanPlay);
  video.addEventListener?.("emptied", binding.onEmptied);
  container.__hmbSeedancePreviewVideoBinding = binding;
}

function armSameSourceRevisionReload(container, generation, identity, video, binding) {
  const confirmed = container?.__hmbSeedanceConfirmedPreviewMedia;
  if (
    !container
    || generation.phase !== "succeeded"
    || !confirmed
    || confirmed.identity !== identity
    || confirmed.media_revision === generation.media_revision
    || !binding
  ) return false;
  const key = `${generation.media_revision}\u001f${identity}`;
  if (container.__hmbSeedancePreviewReloadKey !== key) {
    container.__hmbSeedancePreviewReloadKey = key;
    binding.awaitingRevision = generation.media_revision;
    binding.confirmedRevision = null;
    binding.canPlay = false;
    try { video?.load?.(); } catch { /* Keep the overlay; retrieval remains safe. */ }
  }
  return binding.confirmedRevision !== generation.media_revision;
}

function completedPreviewIsPlayable(container, generation, identity, playable, binding) {
  const confirmed = container?.__hmbSeedanceConfirmedPreviewMedia;
  if (generation.phase !== "succeeded") {
    if (container && identity && playable) {
      container.__hmbSeedanceConfirmedPreviewMedia = {
        identity,
        media_revision: generation.media_revision,
      };
    }
    return playable;
  }
  if (!identity || !playable) return false;
  if (!confirmed) {
    container.__hmbSeedanceConfirmedPreviewMedia = {
      identity,
      media_revision: generation.media_revision,
    };
    return true;
  }
  if (
    confirmed.identity === identity
    && confirmed.media_revision !== generation.media_revision
  ) {
    // The backend has published a new completed media revision, but React is
    // still showing the retained previous video. Keep the status overlay until
    // the native player switches source and that exact source reaches canplay.
    if (binding?.confirmedRevision !== generation.media_revision) return false;
  }
  container.__hmbSeedanceConfirmedPreviewMedia = {
    identity,
    media_revision: generation.media_revision,
  };
  return true;
}

function previewActionPending(container, generation) {
  const pending = container?.__hmbSeedancePreviewActionPending;
  if (!pending) return false;
  const changed = generation.job_id !== pending.job_id
    || generation.phase !== pending.phase
    || generation.media_revision !== pending.media_revision;
  if (changed) {
    clearTimeout(container.__hmbSeedancePreviewActionTimeout);
    delete container.__hmbSeedancePreviewActionTimeout;
    delete container.__hmbSeedancePreviewActionPending;
    delete container.__hmbSeedancePreviewActionError;
    return false;
  }
  return true;
}

export function hmbSeedanceRequestExistingResult(container) {
  const props = container?.__hmbSeedanceLatestProps || {};
  const state = hmbSeedanceShotState(props);
  const generation = state.generation;
  if (
    !container
    || generation.action !== "refresh_existing"
    || !generation.job_id
    || typeof props.onChange !== "function"
    || previewActionPending(container, generation)
  ) return false;
  container.__hmbSeedancePreviewActionPending = {
    job_id: generation.job_id,
    phase: generation.phase,
    media_revision: generation.media_revision,
  };
  delete container.__hmbSeedancePreviewActionError;
  clearTimeout(container.__hmbSeedancePreviewActionTimeout);
  if (typeof setTimeout === "function") {
    container.__hmbSeedancePreviewActionTimeout = setTimeout(() => {
      delete container.__hmbSeedancePreviewActionPending;
      delete container.__hmbSeedancePreviewActionTimeout;
      schedulePreviewSync(container);
    }, 90_000);
    container.__hmbSeedancePreviewActionTimeout?.unref?.();
  }
  schedulePreviewSync(container);
  const request = { ...state, request: { action: "refresh_existing" } };
  let result;
  try {
    result = props.onChange(request);
  } catch (error) {
    clearTimeout(container.__hmbSeedancePreviewActionTimeout);
    delete container.__hmbSeedancePreviewActionTimeout;
    delete container.__hmbSeedancePreviewActionPending;
    container.__hmbSeedancePreviewActionError = text(
      error?.message || error || "Existing task refresh failed",
      240,
    );
    schedulePreviewSync(container);
    return false;
  }
  if (result && typeof result.then === "function") {
    Promise.resolve(result).catch((error) => {
      clearTimeout(container.__hmbSeedancePreviewActionTimeout);
      delete container.__hmbSeedancePreviewActionTimeout;
      delete container.__hmbSeedancePreviewActionPending;
      container.__hmbSeedancePreviewActionError = text(
        error?.message || error || "Existing task refresh failed",
        240,
      );
      schedulePreviewSync(container);
    });
  }
  return true;
}

export function hmbSeedanceSyncPreviewOverlay(container, state, onRetrieve = null) {
  if (!container || container.__hmbSeedancePreviewDisposed) return false;
  container.__hmbSeedancePreviewOnRetrieve = typeof onRetrieve === "function"
    ? onRetrieve : () => hmbSeedanceRequestExistingResult(container);
  const generation = hmbSeedanceGenerationPreview(state?.generation);
  const region = hmbSeedanceFindPreviewRegion(container);
  if (!region) return false;
  const previousRegion = container.__hmbSeedancePreviewRegion;
  if (previousRegion && previousRegion !== region) {
    previousRegion.querySelector?.(".hmb-seedance-preview-overlay")?.remove?.();
    restorePreviewRegionPosition(previousRegion);
  }
  container.__hmbSeedancePreviewRegion = region;
  ensurePreviewRegionPosition(region);
  const video = previewVideo(region);
  bindPreviewVideo(container, video);
  const binding = container.__hmbSeedancePreviewVideoBinding;
  const identity = videoIdentity(video);
  const visibleVideo = Boolean(video && identity);
  const waitingForSameSourceReload = armSameSourceRevisionReload(
    container,
    generation,
    identity,
    video,
    binding,
  );
  const nativePlayable = Boolean(
    visibleVideo
      && !waitingForSameSourceReload
      && (Number(video.readyState) >= 3 || binding?.canPlay === true),
  );
  const playableVideo = completedPreviewIsPlayable(
    container,
    generation,
    identity,
    nativePlayable,
    binding,
  );
  const presentation = hmbSeedancePreviewPresentation(generation, {
    visibleVideo,
    playableVideo,
  });
  let overlay = region.querySelector?.(".hmb-seedance-preview-overlay");
  if (!presentation.visible) {
    overlay?.remove?.();
    return true;
  }
  if (!overlay) overlay = createPreviewOverlay(region);
  if (!overlay) return false;
  overlay.dataset.phase = presentation.phase;
  overlay.dataset.mode = presentation.mode;
  overlay.dataset.busy = presentation.busy ? "true" : "false";
  overlay.dataset.tone = presentation.tone;
  const shotNumber = hmbSeedancePaletteShotNumber(state);
  const theme = SHOT_THEME[shotNumber];
  overlay.style?.setProperty?.("--shot-rgb", theme.rgb);
  overlay.style?.setProperty?.("--shot-soft", theme.soft);
  const title = overlay.querySelector?.(".hmb-seedance-preview-overlay__title");
  const detail = overlay.querySelector?.(".hmb-seedance-preview-overlay__detail");
  const elapsed = overlay.querySelector?.(".hmb-seedance-preview-overlay__elapsed");
  const action = overlay.querySelector?.("[data-hmb-seedance-preview-action]");
  const pending = previewActionPending(container, generation);
  const actionError = text(container.__hmbSeedancePreviewActionError, 240);
  setElementText(title, presentation.title);
  setElementText(detail, actionError || presentation.detail);
  setElementText(elapsed, presentation.elapsed ? `경과 시간 ${presentation.elapsed}` : "");
  if (elapsed?.style) elapsed.style.display = presentation.elapsed ? "" : "none";
  if (action) {
    if (action.style) {
      action.style.display = presentation.action === "refresh_existing" ? "" : "none";
    }
    action.disabled = pending;
    setElementText(action, pending ? "기존 작업 확인 중…" : "기존 작업 결과 확인");
    if (!action.__hmbSeedancePreviewActionBound) {
      action.__hmbSeedancePreviewActionBound = true;
      action.addEventListener?.("pointerdown", (event) => event.stopPropagation?.());
      action.addEventListener?.("click", (event) => {
        event.preventDefault?.();
        event.stopPropagation?.();
        container.__hmbSeedancePreviewOnRetrieve?.();
      });
    }
  }
  return true;
}

function installPreviewObserver(container) {
  if (!container || container.__hmbSeedancePreviewObserver || typeof MutationObserver !== "function") {
    return;
  }
  const nodeRoot = hmbSeedanceNodeRoot(container);
  if (!nodeRoot) return;
  const observer = new MutationObserver(() => schedulePreviewSync(container));
  observer.observe(nodeRoot, { childList: true, subtree: true });
  container.__hmbSeedancePreviewObserver = observer;
}

export function hmbSeedanceCleanupPreviewOverlay(container) {
  if (!container) return false;
  container.__hmbSeedancePreviewDisposed = true;
  container.__hmbSeedancePreviewObserver?.disconnect?.();
  delete container.__hmbSeedancePreviewObserver;
  clearTimeout(container.__hmbSeedancePreviewActionTimeout);
  delete container.__hmbSeedancePreviewActionTimeout;
  removePreviewVideoListeners(container);
  const region = container.__hmbSeedancePreviewRegion;
  region?.querySelector?.(".hmb-seedance-preview-overlay")?.remove?.();
  restorePreviewRegionPosition(region);
  delete container.__hmbSeedancePreviewRegion;
  delete container.__hmbSeedancePreviewOnRetrieve;
  delete container.__hmbSeedancePreviewActionPending;
  delete container.__hmbSeedancePreviewActionError;
  delete container.__hmbSeedanceConfirmedPreviewMedia;
  delete container.__hmbSeedancePreviewReloadKey;
  delete container.__hmbSeedancePreviewSyncScheduled;
  return true;
}

function hmbSeedanceNodeSelected(root) {
  if (!root) return false;
  return root.classList?.contains("selected")
    || String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true"
    || String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true"
    || Boolean(root.querySelector?.(
      ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
    ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  )) return false;
  if (!hmbSeedanceNodeSelected(hmbSeedanceNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function refresh(container, props) {
  const root = container?.querySelector?.(".hmb-seedance-shot");
  if (!root) return false;
  compactHost(container);
  const state = hmbSeedanceShotState(props);
  const number = hmbSeedancePaletteShotNumber(state);
  const theme = SHOT_THEME[number];
  root.dataset.shotNumber = String(number);
  root.style.setProperty("--shot-accent", HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[number]);
  root.style.setProperty("--shot-rgb", theme.rgb);
  root.style.setProperty("--shot-soft", theme.soft);
  const select = root.querySelector?.(".hmb-seedance-shot__select");
  if (select) hmbSeedanceSyncShotSelect(select, state);
  const numberBadge = root.querySelector?.("[data-seedance-shot-number]");
  if (numberBadge) {
    numberBadge.textContent = state.shot.shot_uuid
      ? String(state.shot.number).padStart(2, "0")
      : "Only";
  }
  const error = container.__hmbSeedanceShotChangeError || "";
  hmbSeedanceSetStatus(
    container,
    error ? "Save failed · previous Shot restored" : "",
    error,
  );
  hmbSeedanceSyncPreviewOverlay(container, state);
  installPreviewObserver(container);
  return true;
}

export default function HMBSeedanceGenerationWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  delete container.__hmbSeedancePreviewDisposed;
  const latest = props || container.__hmbSeedanceLatestProps || {};
  container.__hmbSeedanceLatestProps = latest;
  const previousCleanup = container.__hmbSeedanceCleanup;
  // A factory call with new props is an authoritative lifecycle refresh, just
  // like update(). Invalidate any optimistic promise before accepting it so a
  // late rejection cannot roll the refreshed selector back.
  if (typeof previousCleanup === "function") hmbSeedanceNextChangeOwner(container);
  if (typeof previousCleanup === "function" && refresh(container, latest)) {
    return {
      cleanup: container.__hmbSeedanceCleanupProxy,
      update(nextProps) {
        hmbSeedanceNextChangeOwner(container);
        container.__hmbSeedanceLatestProps = nextProps || container.__hmbSeedanceLatestProps || {};
        if (!refresh(container, container.__hmbSeedanceLatestProps)) {
          HMBSeedanceGenerationWidget(container, container.__hmbSeedanceLatestProps);
        }
      },
    };
  }
  if (typeof previousCleanup === "function") previousCleanup();
  if (typeof container.__hmbSeedanceCleanupProxy !== "function") {
    container.__hmbSeedanceCleanupProxy = () => {
      const cleanup = container.__hmbSeedanceCleanup;
      if (typeof cleanup === "function") cleanup();
    };
  }
  compactHost(container);
  const initialState = hmbSeedanceShotState(latest);
  container.innerHTML = render(initialState);
  hmbSeedanceSyncPreviewOverlay(container, initialState);
  installPreviewObserver(container);
  const select = container.querySelector?.(".hmb-seedance-shot__select");
  const onShotChange = () => {
    const liveProps = container.__hmbSeedanceLatestProps || {};
    const previousProps = liveProps;
    const previousState = hmbSeedanceShotState(liveProps);
    const selected = hmbSeedanceShotOptions(previousState).find((item) => item.key === select?.value);
    if (!selected || typeof liveProps.onChange !== "function") {
      refresh(container, liveProps);
      return;
    }
    const next = hmbSeedanceShotState(liveProps);
    if (selected.waiting) {
      refresh(container, liveProps);
      return;
    }
    next.shot = {
      channel_uuid: selected.channel_uuid,
      shot_uuid: selected.shot_uuid,
      number: selected.number,
      name: selected.name,
    };
    const owner = hmbSeedanceNextChangeOwner(container);
    const optimisticProps = { ...liveProps, value: next, parameterValue: next, defaultValue: next };
    const accept = () => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      container.__hmbSeedanceLatestProps = optimisticProps;
      delete container.__hmbSeedanceShotChangeError;
      refresh(container, optimisticProps);
    };
    const rollback = (error) => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      container.__hmbSeedanceLatestProps = previousProps;
      container.__hmbSeedanceShotChangeError = String(
        error?.message || error || "Shot selection publication failed",
      );
      refresh(container, previousProps);
    };
    let result;
    try { result = liveProps.onChange(next); } catch (error) { rollback(error); return; }
    accept();
    if (result && typeof result.then === "function") Promise.resolve(result).catch(rollback);
  };
  select?.addEventListener?.("change", onShotChange);
  const guardDelete = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", guardDelete, true);
  }
  const stopInteriorDelete = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorSelection = (event) => event.stopPropagation?.();
  container.addEventListener?.("keydown", stopInteriorDelete);
  container.addEventListener?.("pointerdown", stopInteriorSelection);
  const cleanup = () => {
    hmbSeedanceCleanupPreviewOverlay(container);
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", guardDelete, true);
    }
    container.removeEventListener?.("keydown", stopInteriorDelete);
    container.removeEventListener?.("pointerdown", stopInteriorSelection);
    select?.removeEventListener?.("change", onShotChange);
    if (container.__hmbSeedanceCleanup === cleanup) delete container.__hmbSeedanceCleanup;
    delete container.__hmbSeedanceLatestProps;
    delete container.__hmbSeedanceShotChangeError;
    // Invalidate promise callbacks from this lifecycle without resetting the
    // monotonic token. A remount can otherwise reuse owner=1 and let an old
    // rejection roll the new selector back.
    hmbSeedanceNextChangeOwner(container);
    container.innerHTML = "";
  };
  container.__hmbSeedanceCleanup = cleanup;
  return {
    cleanup: container.__hmbSeedanceCleanupProxy,
    update(nextProps) {
      hmbSeedanceNextChangeOwner(container);
      container.__hmbSeedanceLatestProps = nextProps || container.__hmbSeedanceLatestProps || {};
      if (!refresh(container, container.__hmbSeedanceLatestProps)) {
        HMBSeedanceGenerationWidget(container, container.__hmbSeedanceLatestProps);
      }
    },
  };
}
