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

const HMB_SHOT_ONLY_KEY = "__hmb_shot_only__";
const HMB_SHOT_WAITING_KEY = "__hmb_shot_waiting__";
const HMB_SEEDANCE_MODE_SELECTION_SCHEMA = "hmb-seedance-mode-selection";
const HMB_SEEDANCE_PREVIEW_SCHEMA = "hmb-seedance-generation-preview";
const HMB_SEEDANCE_PREVIEW_VERSION = 1;
const HMB_SEEDANCE_COMMAND_SCHEMA = "hmb-seedance-refresh-command";
const HMB_SEEDANCE_COMMAND_VERSION = 1;
const HMB_SEEDANCE_COMMAND_REGISTRY_KEY = "__HMB_SEEDANCE_REFRESH_BRIDGES_V1__";
const HMB_SEEDANCE_BROKER_PARAMETER = "broker_server_url";
const HMB_SEEDANCE_BROKER_DIALOGS = new WeakMap();
const HMB_SEEDANCE_LOCAL_PREVIEW_LOADS = new WeakMap();
const HMB_SEEDANCE_PROMPT_EDGE_REGISTRY_KEY = "__HMB_SEEDANCE_PROMPT_EDGE_REGISTRY_V1__";
const HMB_SEEDANCE_PROMPT_EDGE_ATTRIBUTE = "data-hmb-seedance-prompt-edge";
export const HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS = 10_000;

const HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT = (
  "요청 전달을 확인하지 못했습니다. 잠시 후 다시 시도하세요."
);
const HMB_SEEDANCE_REFRESH_TRANSPORT_UNAVAILABLE = (
  "기존 작업 확인 기능을 사용할 수 없습니다. 노드를 다시 연 뒤 재시도하세요."
);

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

function localOriginalPreview(value) {
  if (!value || typeof value !== "object") return null;
  const source = value.source;
  const url = value.url;
  if (
    typeof source !== "string" || !source || source.length > 8192
    || typeof url !== "string" || !url || url.length > 16384
    || /[\u0000-\u001f\u007f]/.test(source + url)
    || /^(?:https?:|data:|blob:)/i.test(source)
  ) return null;
  try {
    const parsed = new URL(url);
    const filename = source.replace(/\\/g, "/").split("/").pop();
    const path = decodeURIComponent(parsed.pathname);
    if (
      !["http:", "https:"].includes(parsed.protocol)
      || !["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname)
      || parsed.username || parsed.password || parsed.hash
      || !/(?:^|\/)(?:workspace|external)\//.test(path)
      || !filename || !path.endsWith(`/${filename}`)
    ) return null;
  } catch { return null; }
  return { source, url };
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
  const normalized = {
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
  const localPreview = localOriginalPreview(candidate.local_preview);
  if (localPreview) normalized.local_preview = localPreview;
  return normalized;
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
  const previewError = options.previewError === true;
  const elapsed = elapsedLabel(generation.elapsed_seconds);
  const base = {
    visible: true,
    phase: generation.phase,
    mode: visibleVideo ? "badge" : "center",
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
      // The native Griptape video loader owns loading, errors and playback.
      // A completed original must retain its own controls even before canplay
      // or after a transient media error; our status cannot hide that player.
      if (visibleVideo || playableVideo) return { ...base, visible: false, action: "none" };
      if (previewError) {
        return {
          ...base,
          title: "영상 재생 오류",
          detail: "파일은 저장되었습니다. 기본 비디오 로더에서 원본 영상을 확인하세요.",
          busy: false,
          tone: "warning",
          action: "none",
        };
      }
      return {
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

function hmbSeedanceNodeName(value) {
  if (typeof value !== "string") return "";
  const normalized = value.trim();
  if (
    !normalized
    || normalized.length > 512
    || Array.from(normalized).some((character) => character.charCodeAt(0) < 32)
  ) return "";
  return normalized;
}

export function hmbSeedanceRemotePromptRoute(value) {
  const source = value && typeof value === "object" && !Array.isArray(value)
    ? (value.remote_prompt_route && typeof value.remote_prompt_route === "object"
      ? value.remote_prompt_route : value)
    : {};
  const disconnected = {
    schema: "hmb-seedance-remote-prompt-route",
    version: 1,
    connected: false,
    source_node_name: "",
    previous_source_node_name: "",
    target_node_name: "",
    previous_target_node_name: "",
    source_parameter: "output",
    target_parameter: "prompt",
  };
  const sourceNodeName = hmbSeedanceNodeName(source.source_node_name);
  const rawPreviousSourceNodeName = source.previous_source_node_name ?? "";
  const previousSourceNodeName = rawPreviousSourceNodeName
    ? hmbSeedanceNodeName(rawPreviousSourceNodeName) : "";
  const targetNodeName = hmbSeedanceNodeName(source.target_node_name);
  const rawPreviousTargetNodeName = source.previous_target_node_name ?? "";
  const previousTargetNodeName = rawPreviousTargetNodeName
    ? hmbSeedanceNodeName(rawPreviousTargetNodeName) : "";
  if (
    source.schema !== disconnected.schema
    || Number(source.version) !== disconnected.version
    || source.connected !== true
    || source.source_parameter !== "output"
    || source.target_parameter !== "prompt"
    || !sourceNodeName
    || (rawPreviousSourceNodeName && !previousSourceNodeName)
    || !targetNodeName
    || (rawPreviousTargetNodeName && !previousTargetNodeName)
  ) return disconnected;
  return {
    ...disconnected,
    connected: true,
    source_node_name: sourceNodeName,
    previous_source_node_name: previousSourceNodeName === sourceNodeName
      ? "" : previousSourceNodeName,
    target_node_name: targetNodeName,
    previous_target_node_name: previousTargetNodeName === targetNodeName
      ? "" : previousTargetNodeName,
  };
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

function hmbSeedanceModeFields(source) {
  if (!Object.prototype.hasOwnProperty.call(source, "execution_mode")) return null;
  const valid = ["auto", "only", "shot", "waiting"].includes(source.execution_mode)
    && ["auto", "only", "shot"].includes(source.requested_mode)
    && (source.execution_mode !== "only" || source.requested_mode === "only")
    && (source.requested_mode !== "only" || source.execution_mode === "only")
    && Number.isSafeInteger(source.execution_mode_revision) && source.execution_mode_revision >= 0
    && Number.isSafeInteger(source.execution_mode_state_revision) && source.execution_mode_state_revision >= 0
    && /^[0-9a-f]{32}$/.test(String(source.execution_mode_instance || ""));
  // A partial modern snapshot cannot assert independent execution. Old hosts
  // without mode fields retain the legacy selector contract below.
  return valid ? {
    execution_mode: source.execution_mode,
    requested_mode: source.requested_mode,
    execution_mode_revision: source.execution_mode_revision,
    execution_mode_state_revision: source.execution_mode_state_revision,
    execution_mode_instance: source.execution_mode_instance,
  } : { execution_mode: "auto", requested_mode: "auto", execution_mode_revision: 0,
    execution_mode_state_revision: 0, execution_mode_instance: "" };
}

function hmbSeedanceShotIdentity(value) {
  const channel = uuid(value?.channel_uuid);
  const shot = uuid(value?.shot_uuid);
  if (!channel || !shot) return null;
  return { channel_uuid: channel, shot_uuid: shot,
    number: boundedInteger(value.number, { min: 1, max: 5 }), name: text(value.name, 160) };
}

function hmbSeedanceSelectionRequest(source, mode) {
  const request = source.selection_request;
  return mode?.execution_mode_instance && request?.schema === HMB_SEEDANCE_MODE_SELECTION_SCHEMA
    && request.version === 1 && ["only", "shot"].includes(request.mode)
    && request.expected_revision === mode.execution_mode_revision
    && request.expected_instance === mode.execution_mode_instance
    ? { schema: HMB_SEEDANCE_MODE_SELECTION_SCHEMA, version: 1, mode: request.mode,
      expected_revision: request.expected_revision, expected_instance: request.expected_instance } : null;
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
  const mode = hmbSeedanceModeFields(source);
  const request = hmbSeedanceSelectionRequest(source, mode);
  const pendingShot = hmbSeedanceShotIdentity(source.pending_shot) || hmbSeedanceShotIdentity(requested);
  const selection = mode?.requested_mode === "shot" && !request ? pendingShot : null;
  const selectionChannel = selection?.channel_uuid || requestedChannel;
  const selectionUuid = selection?.shot_uuid || requestedUuid;
  const requestedSelection = catalog.channel_uuid === selectionChannel
    ? catalog.shots?.find((shot) => shot.shot_uuid === selectionUuid) || null
    : null;
  const selected = mode?.execution_mode === "only" && !request ? null : requestedSelection || null;
  const state = {
    schema: "hmb-seedance-shot-ui",
    schema_version: 2,
    shot_catalog: catalog,
    shot: selected ? {
      channel_uuid: catalog.channel_uuid,
      shot_uuid: selected.shot_uuid,
      number: selected.number,
      name: selected.name,
    } : mode && (request?.mode === "shot" || mode.requested_mode === "shot") && pendingShot ? pendingShot : {
      channel_uuid: "",
      shot_uuid: "",
      number: 1,
      name: "Only",
    },
    generation: hmbSeedanceGenerationPreview(source.generation),
    draft: hmbSeedanceDraftState(!selected && (requested.channel_uuid || requested.shot_uuid)
      ? { cancel_available: source.draft?.cancel_available, active_job_id: source.draft?.active_job_id }
      : source.draft),
    remote_prompt_route: hmbSeedanceRemotePromptRoute(source),
  };
  if (mode) {
    Object.assign(state, mode);
    state.pending_shot = pendingShot || { channel_uuid: "", shot_uuid: "", number: 1, name: "" };
    if (request) state.selection_request = request;
  }
  return state;
}

export function hmbSeedanceDraftState(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    visible: source.visible === true,
    action: text(source.action, 80),
    preview_available: source.preview_available === true,
    final_available: source.final_available === true,
    job_id: text(source.job_id, 160),
    effective_resolution: text(source.effective_resolution, 16),
    busy: source.busy === true,
    final_busy: source.final_busy === true,
    final_state: text(source.final_state, 32),
    final_visible: Object.prototype.hasOwnProperty.call(source, "final_visible") ? source.final_visible === true : undefined,
    final_task_id: text(source.final_task_id, 128),
    active_action: text(source.active_action, 80),
    cancel_available: source.cancel_available === true,
    active_job_id: text(source.active_job_id, 160),
    reason: text(source.reason, 360),
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
  if (hmbSeedanceShotWaiting(state)) options.unshift({ key: HMB_SHOT_WAITING_KEY,
    channel_uuid: "", shot_uuid: "", number: 1, name: hmbSeedanceModeLabel(state), only: false, waiting: true });
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
  if (state?.execution_mode && hmbSeedanceShotWaiting(state)) {
    const pending = state.pending_shot || shot;
    return HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[pending.number] ? pending.number : 1;
  }
  if (!shot.channel_uuid || !shot.shot_uuid || catalog.channel_uuid !== shot.channel_uuid) return 1;
  const selected = (catalog.shots || []).find((item) => item.shot_uuid === shot.shot_uuid);
  return selected && HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[selected.number] ? selected.number : 1;
}

export function hmbSeedanceShotAccent(state) {
  return HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[hmbSeedancePaletteShotNumber(state)];
}

function optionLabel(item) {
  if (item.waiting) return item.name;
  if (item.only) return "Only";
  return `${String(item.number).padStart(2, "0")} · ${item.name}`;
}

function optionMarkup(state) {
  const currentKey = hmbSeedanceShotKey(state);
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
    disabled: item.waiting === true,
  }));
  const current = Array.from(select.options || []);
  const optionsChanged = current.length !== desired.length || desired.some((item, index) => {
    const option = current[index];
    return !option
      || String(option.value) !== item.value
      || String(option.textContent ?? option.text ?? "") !== item.label
      || Boolean(option.disabled) !== item.disabled;
  });
  if (optionsChanged) select.innerHTML = optionMarkup(state);
  const expected = hmbSeedanceShotKey(state);
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
      .hmb-seedance-shot :is(button,input,select,textarea):not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){font-family:inherit}
      .hmb-seedance-preview-overlay :is(button,input,select,textarea){font-family:inherit}
      .hmb-seedance-shot{--shot-accent:${accent};--shot-rgb:${theme.rgb};--shot-soft:${theme.soft};position:relative;width:100%;height:64px;overflow:hidden;box-sizing:border-box;border:1px solid rgba(var(--shot-rgb),.5);border-radius:11px;background:radial-gradient(circle at 8% -45%,rgba(var(--shot-rgb),.25),transparent 54%),linear-gradient(90deg,rgba(var(--shot-rgb),.2),rgba(14,23,38,.96) 46%,#060912);color:#e6edf7;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 24px rgba(0,0,0,.24),0 0 18px rgba(var(--shot-rgb),.18);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none}
      .hmb-seedance-shot *:not(:where([data-hmb-native-identity] *,[data-hmb-native-actions] *)){box-sizing:border-box;min-width:0}.hmb-seedance-shot__row{height:100%;display:flex;align-items:center;gap:11px;padding:8px 13px}.hmb-seedance-shot__mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(var(--shot-rgb),.52);border-radius:8px;background:linear-gradient(145deg,rgba(var(--shot-rgb),.14),rgba(5,9,16,.86));color:var(--shot-accent);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px rgba(var(--shot-rgb),.19);font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-seedance-shot__title{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e6edf7;font-size:14px;font-weight:850}.hmb-seedance-shot__status{flex:0 1 190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fb7185;font-size:8px;font-weight:800;text-align:right}.hmb-seedance-shot__status:empty{display:none}.hmb-seedance-shot__select{flex:0 1 210px;width:210px;height:29px;margin-left:auto;padding:0 28px 0 10px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(255,255,255,.04),transparent),rgba(var(--shot-rgb),.16);color:var(--shot-soft);box-shadow:inset 0 1px 0 rgba(255,255,255,.045),0 0 12px rgba(var(--shot-rgb),.18);font:inherit;font-size:10px;font-weight:850;letter-spacing:.035em}.hmb-seedance-shot__select:focus{border-color:var(--shot-accent);box-shadow:0 0 0 2px rgba(var(--shot-rgb),.18)}.hmb-seedance-shot__select option{background:#0b1020;color:#e6edf7}@container(max-width:360px){.hmb-seedance-shot__status{display:none}.hmb-seedance-shot__select{flex-basis:120px;width:120px}.hmb-seedance-shot__title{font-size:12px}}
      /* Match the Prompt header while preserving the existing selector position and responsive width. */
      .hmb-seedance-shot__title{font-size:15px;font-weight:800;letter-spacing:.01em;line-height:normal}
      .hmb-seedance-shot__select{height:44px;font-size:13px;font-weight:800;line-height:normal}
      .hmb-seedance-shot__number{flex:0 0 auto;min-width:34px;padding:5px 7px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;color:var(--shot-soft);font-size:11px;font-weight:900;text-align:center}
      .hmb-seedance-shot__final{flex:0 0 auto;height:36px;padding:0 10px;border:1px solid rgba(var(--shot-rgb),.7);border-radius:7px;background:rgba(var(--shot-rgb),.2);color:var(--shot-soft);font-size:11px;font-weight:850;cursor:pointer;white-space:nowrap}.hmb-seedance-shot__final:hover{background:rgba(var(--shot-rgb),.34)}.hmb-seedance-shot__final:disabled{cursor:default;opacity:.55}.hmb-seedance-shot__final[hidden]{display:none}
      .hmb-seedance-preview-overlay{position:absolute;inset:0;z-index:24;display:flex;align-items:center;justify-content:center;padding:18px;pointer-events:none;color:#f8fafc;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif}
      .hmb-seedance-preview-overlay[data-mode="center"]{background:radial-gradient(circle at 50% 42%,rgba(30,41,59,.34),rgba(0,0,0,.76) 74%)}
      [data-hmb-seedance-preview-static="true"]>:not(.hmb-seedance-preview-overlay),[data-hmb-seedance-preview-static="true"]>:not(.hmb-seedance-preview-overlay) *{visibility:hidden!important;pointer-events:none!important}
      .hmb-seedance-preview-overlay[data-static="true"]{background:#080d17}
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
      .react-flow__edge[${HMB_SEEDANCE_PROMPT_EDGE_ATTRIBUTE}="true"]{display:none!important}
      /* HMB_NATIVE_HEADER_SLOTS_BEGIN */
      .hmb-seedance-shot__native-identity,.hmb-seedance-shot__native-actions{display:none;min-width:0;--node-header-text:#e6edf7}
      .hmb-seedance-shot[data-hmb-native-header=active]{border:0;border-radius:0;box-shadow:none}
      .hmb-seedance-shot[data-hmb-native-header=active] .hmb-seedance-shot__mark,.hmb-seedance-shot[data-hmb-native-header=active] .hmb-seedance-shot__title{display:none}
      .hmb-seedance-shot[data-hmb-native-header=active] .hmb-seedance-shot__native-identity{display:flex;align-items:center;flex:1 1 auto}
      .hmb-seedance-shot[data-hmb-native-header=active] .hmb-seedance-shot__native-actions{display:flex;align-items:center;flex:0 0 auto}
      .hmb-seedance-shot__native-identity>div{min-width:0;max-width:100%}
      /* HMB_NATIVE_HEADER_SLOTS_END */
      @keyframes hmb-seedance-preview-spin{to{transform:rotate(360deg)}}
    </style>
    <div class="hmb-seedance-shot nodrag" data-shot-number="${number}">
      <div class="hmb-seedance-shot__row group">
        <div class="hmb-seedance-shot__mark" aria-hidden="true">SD</div>
        <div class="hmb-seedance-shot__title">HMBSeedanceGeneration</div>
        <div class="hmb-seedance-shot__native-identity" data-hmb-native-identity></div>
        <div class="hmb-seedance-shot__native-actions nodrag" data-hmb-native-actions></div>
        <span class="hmb-seedance-shot__status" role="status" aria-live="polite" aria-atomic="true"></span>
        <button type="button" class="hmb-seedance-shot__final nodrag" data-hmb-seedance-finalize-draft hidden disabled title="완료된 Draft로 현재 Generator만 1회 실행해 1080p로 받습니다. 현재 프롬프트·소스·설정은 다시 전송하지 않으며 Agent도 재실행하지 않습니다. MOV 기본 · MOV 미지원 시 MP4.">Draft final</button>
        <span class="hmb-seedance-shot__number" data-seedance-shot-number>${hmbSeedanceShotBadge(state)}</span>
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

export function hmbSeedanceRemotePromptEdgeMatches(element, value) {
  const route = hmbSeedanceRemotePromptRoute(value);
  if (!route.connected || !element?.getAttribute) return false;
  const edgeId = String(element.getAttribute("data-id") || "");
  const ariaLabel = String(element.getAttribute("aria-label") || "");
  const sourceAliases = [route.source_node_name, route.previous_source_node_name]
    .filter(Boolean);
  const targetAliases = [route.target_node_name, route.previous_target_node_name]
    .filter(Boolean);
  const idMatches = sourceAliases.some((sourceNodeName) => (
    targetAliases.some((targetNodeName) => edgeId.startsWith(
      `${sourceNodeName}-${route.source_parameter}-`
      + `${targetNodeName}-${route.target_parameter}-`,
    ))
  ));
  const labelMatches = sourceAliases.some((sourceNodeName) => (
    targetAliases.some((targetNodeName) => (
      ariaLabel === `Edge from ${sourceNodeName} to ${targetNodeName}`
    ))
  ));
  // During Reset Node, React Flow can retain temporary endpoint names in the
  // edge id while its aria label already uses final names. The two proven
  // aliases for each endpoint may therefore match independently, but both
  // public handles and every accepted endpoint remain exact.
  return idMatches && labelMatches;
}

function hmbSeedancePromptEdgeRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_SEEDANCE_PROMPT_EDGE_REGISTRY_KEY] instanceof WeakMap)) {
    root[HMB_SEEDANCE_PROMPT_EDGE_REGISTRY_KEY] = new WeakMap();
  }
  return root[HMB_SEEDANCE_PROMPT_EDGE_REGISTRY_KEY];
}

function hmbSeedanceEdgeLayer(container) {
  const nodeRoot = hmbSeedanceNodeRoot(container);
  let current = nodeRoot?.parentElement || null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const layer = current.querySelector?.(".react-flow__edges");
    if (layer) return layer;
  }
  return null;
}

function hmbSeedanceScanPromptEdges(controller) {
  if (!controller?.layer) return;
  for (const edge of controller.markedEdges) {
    edge?.removeAttribute?.(HMB_SEEDANCE_PROMPT_EDGE_ATTRIBUTE);
  }
  controller.markedEdges.clear();
  const routes = Array.from(controller.entries.values()).filter((route) => route.connected);
  if (!routes.length) return;
  const edges = controller.layer.querySelectorAll?.(
    ".react-flow__edge[data-id][aria-label]",
  ) || [];
  for (const edge of edges) {
    if (!routes.some((route) => hmbSeedanceRemotePromptEdgeMatches(edge, route))) continue;
    edge.setAttribute?.(HMB_SEEDANCE_PROMPT_EDGE_ATTRIBUTE, "true");
    controller.markedEdges.add(edge);
  }
}

function hmbSeedanceSchedulePromptEdgeScan(controller) {
  if (!controller || controller.scheduled !== null) return;
  const run = () => {
    controller.scheduled = null;
    hmbSeedanceScanPromptEdges(controller);
  };
  if (typeof requestAnimationFrame === "function") {
    controller.scheduled = { type: "frame", id: requestAnimationFrame(run) };
  } else if (typeof setTimeout === "function") {
    controller.scheduled = { type: "timeout", id: setTimeout(run, 0) };
  } else {
    run();
  }
}

function hmbSeedanceCancelPromptEdgeScan(controller) {
  const scheduled = controller?.scheduled;
  if (!scheduled) return;
  if (scheduled.type === "frame" && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(scheduled.id);
  } else if (scheduled.type === "timeout" && typeof clearTimeout === "function") {
    clearTimeout(scheduled.id);
  }
  controller.scheduled = null;
}

function hmbSeedanceUnregisterRemotePromptEdge(container) {
  const layer = container?.__hmbSeedancePromptEdgeLayer;
  if (!layer) return false;
  const registry = hmbSeedancePromptEdgeRegistry();
  const controller = registry?.get(layer);
  delete container.__hmbSeedancePromptEdgeLayer;
  if (!controller) return false;
  controller.entries.delete(container);
  if (controller.entries.size) {
    hmbSeedanceSchedulePromptEdgeScan(controller);
    return true;
  }
  controller.observer?.disconnect?.();
  hmbSeedanceCancelPromptEdgeScan(controller);
  for (const edge of controller.markedEdges) {
    edge?.removeAttribute?.(HMB_SEEDANCE_PROMPT_EDGE_ATTRIBUTE);
  }
  controller.markedEdges.clear();
  registry.delete(layer);
  return true;
}

function hmbSeedanceSyncRemotePromptEdge(container, state) {
  const route = hmbSeedanceRemotePromptRoute(state);
  const layer = route.connected ? hmbSeedanceEdgeLayer(container) : null;
  if (container?.__hmbSeedancePromptEdgeLayer !== layer) {
    hmbSeedanceUnregisterRemotePromptEdge(container);
  }
  if (!container || !layer || !route.connected) return false;
  const registry = hmbSeedancePromptEdgeRegistry();
  if (!registry) return false;
  let controller = registry.get(layer);
  if (!controller) {
    controller = {
      layer,
      entries: new Map(),
      markedEdges: new Set(),
      observer: null,
      scheduled: null,
    };
    if (typeof MutationObserver === "function") {
      controller.observer = new MutationObserver(() => {
        hmbSeedanceSchedulePromptEdgeScan(controller);
      });
      // Five generators share this one edge-layer observer. Reset Node may
      // rename the retained edge in place, so watch only the two host-owned
      // endpoint attributes. Our own hiding marker is intentionally outside
      // this filter and therefore cannot retrigger the observer.
      controller.observer.observe(layer, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["data-id", "aria-label"],
      });
    }
    registry.set(layer, controller);
  }
  const previousRoute = controller.entries.get(container);
  const routeUnchanged = Boolean(
    previousRoute
    && previousRoute.connected === route.connected
    && previousRoute.source_node_name === route.source_node_name
    && previousRoute.previous_source_node_name === route.previous_source_node_name
    && previousRoute.target_node_name === route.target_node_name
    && previousRoute.previous_target_node_name === route.previous_target_node_name
    && previousRoute.source_parameter === route.source_parameter
    && previousRoute.target_parameter === route.target_parameter
  );
  controller.entries.set(container, route);
  container.__hmbSeedancePromptEdgeLayer = layer;
  if (!routeUnchanged) hmbSeedanceScanPromptEdges(controller);
  return true;
}

export function hmbSeedanceCleanupRemotePromptEdge(container) {
  return hmbSeedanceUnregisterRemotePromptEdge(container);
}

function hmbSeedanceCommandRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_SEEDANCE_COMMAND_REGISTRY_KEY] instanceof WeakMap)) {
    root[HMB_SEEDANCE_COMMAND_REGISTRY_KEY] = new WeakMap();
  }
  return root[HMB_SEEDANCE_COMMAND_REGISTRY_KEY];
}

function hmbSeedanceCommandValue(props) {
  const candidate = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  return candidate && typeof candidate === "object" && !Array.isArray(candidate)
    ? candidate : {};
}

function hmbSeedanceCommandProps(props) {
  const value = hmbSeedanceCommandValue(props);
  return value.schema === HMB_SEEDANCE_COMMAND_SCHEMA
    && Number(value.version) === HMB_SEEDANCE_COMMAND_VERSION;
}

function hmbSeedanceCommandContainer(container) {
  let current = container || null;
  for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
    if (
      current.getAttribute?.("data-parameter-name")
      === "HMB_SEEDANCE_REFRESH_COMMAND"
    ) return true;
  }
  return false;
}

function hmbSeedanceBrokerContainer(container) {
  let current = container || null;
  for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
    if (current.getAttribute?.("data-parameter-name") === HMB_SEEDANCE_BROKER_PARAMETER) return true;
  }
  return false;
}

export function hmbSeedanceNormalizeBrokerUrl(raw) {
  const authored = String(raw ?? "");
  const value = authored.trim();
  if (/[\x00-\x1f\x7f]/.test(authored)) {
    return { ok: false, value: "", error: "제어 문자가 없는 HTTPS 브로커 주소를 입력하세요." };
  }
  if (!value) return { ok: true, value: "", error: "" };
  if (value.length > 2048) {
    return { ok: false, value: "", error: "브로커 주소가 너무 깁니다." };
  }
  // Validate the authored path before URL canonicalization can silently remove
  // dot segments, backslashes or duplicate separators. The desktop backend owns
  // the shared persistent setting; this widget never stores an independent URL.
  const literal = /^https:\/\/([^/?#]+)(\/[^?#]*)?$/i.exec(value);
  const rawPath = literal?.[2] || "";
  const segments = rawPath.replace(/\/$/, "").split("/").slice(1);
  const invalid = () => ({
    ok: false,
    value: "",
    error: "HTTPS 서버 주소와 선택 경로만 허용합니다. 계정·쿼리·인코딩·중복 또는 상위 경로는 제외하세요.",
  });
  if (!literal || /[\s\\%]/.test(value)
    || /[^\x21-\x7e]/.test(value) || literal[1].includes("@")
    || rawPath.includes("//")
    || segments.some((segment) => !/^[A-Za-z0-9._~-]+$/.test(segment)
      || segment === "." || segment === "..")) return invalid();
  let parsed;
  try { parsed = new URL(value); } catch {
    return { ok: false, value: "", error: "올바른 HTTPS 브로커 주소를 입력하세요." };
  }
  if (
    parsed.protocol !== "https:"
    || !parsed.hostname
    || parsed.port === "0"
    || literal[1].endsWith(":")
    || parsed.username
    || parsed.password
    || value.includes("?")
    || value.includes("#")
  ) {
    return invalid();
  }
  if (!parsed.hostname.startsWith("[")) {
    const host = parsed.hostname.toLowerCase();
    const rawHost = literal[1].split(":")[0].toLowerCase();
    const labels = host.split(".");
    if (rawHost !== host
      || !/^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$/.test(host)
      || labels.some((part) => !part || part.length > 63 || part.startsWith("-") || part.endsWith("-"))
      || (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host) && /^(?:\d+|0x[0-9a-f]+)$/.test(labels.at(-1)))) {
      return invalid();
    }
  }
  return { ok: true, value: `${parsed.origin}${rawPath.replace(/\/$/, "")}`, error: "" };
}

function hmbSeedanceInstallBrokerStyles(ownerDocument) {
  if (!ownerDocument?.head || ownerDocument.getElementById?.("hmb-seedance-broker-settings-style")) return;
  const style = ownerDocument.createElement("style");
  style.id = "hmb-seedance-broker-settings-style";
  style.textContent = `
    .hmb-seedance-broker-icon,.hmb-seedance-gallery-icon{position:absolute;right:8px;top:50%;transform:translateY(-50%);z-index:2;width:29px;height:29px;padding:0;display:grid;place-items:center;border:1px solid #64748b;border-radius:7px;background:#151c2b;color:#dbeafe;font:18px system-ui;line-height:1;cursor:pointer}
    .hmb-seedance-gallery-icon{right:46px}.hmb-seedance-gallery-icon:disabled{opacity:.55;cursor:wait}
    .hmb-seedance-broker-icon:hover,.hmb-seedance-broker-icon:focus-visible,.hmb-seedance-gallery-icon:hover,.hmb-seedance-gallery-icon:focus-visible{border-color:#f472b6;color:#fff;outline:2px solid transparent;box-shadow:0 0 0 2px rgba(244,114,182,.25)}
    .hmb-seedance-broker-backdrop{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(1,5,14,.78);font-family:Inter,"Noto Sans KR",system-ui,sans-serif;color:#e7edf7}
    .hmb-seedance-broker-dialog{width:min(520px,100%);padding:20px;border:1px solid #9b4d7d;border-radius:13px;background:#0b1120;box-shadow:0 20px 50px rgba(0,0,0,.55)}
    .hmb-seedance-broker-dialog h2{margin:0 0 12px;font-size:18px}.hmb-seedance-broker-dialog p{margin:0 0 16px;color:#b5c2d5;font-size:12px;line-height:1.55}
    .hmb-seedance-broker-dialog label{display:block;margin-bottom:7px;font-size:12px;font-weight:700}.hmb-seedance-broker-dialog input{box-sizing:border-box;width:100%;height:40px;padding:8px 11px;border:1px solid #61708c;border-radius:7px;outline:none;background:#060b16;color:#f8fafc;font:13px system-ui}
    .hmb-seedance-broker-dialog input:focus{border-color:#f472b6;box-shadow:0 0 0 2px rgba(244,114,182,.2)}.hmb-seedance-broker-error{min-height:18px;margin:8px 0;color:#fb7185;font-size:12px}
    .hmb-seedance-broker-actions{display:flex;justify-content:flex-end;gap:9px}.hmb-seedance-broker-actions button{min-width:78px;padding:8px 12px;border:1px solid #52617a;border-radius:7px;background:#182338;color:#e7edf7;font:12px system-ui;cursor:pointer}
    .hmb-seedance-broker-actions button[data-broker-save]{border-color:#f472b6;background:#9d326d;color:#fff}.hmb-seedance-broker-actions button:disabled{opacity:.55;cursor:wait}
  `;
  ownerDocument.head.appendChild(style);
}

function hmbSeedanceBrokerSettingsWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  const existing = container.__hmbSeedanceBrokerInstance;
  if (existing && typeof existing.update === "function") {
    existing.update(props);
    return existing;
  }
  hmbSeedanceMakeCommandContainerInert(container);
  let latestProps = props || {};
  let nodeRoot = null;
  let modelRow = null;
  let button = null;
  let galleryButton = null;
  let modelStyle = null;
  let observer = null;
  let observedRoot = null;
  let syncQueued = false;
  let closeDialog = null;
  let syncDialogDisabled = null;
  let disposed = false;

  const detachButton = () => {
    if (button) button.remove();
    if (galleryButton) galleryButton.remove();
    if (modelRow?.style && modelStyle) {
      for (const [property, value, priority] of modelStyle) {
        if (value) modelRow.style.setProperty(property, value, priority);
        else modelRow.style.removeProperty(property);
      }
    }
    modelRow = null;
    modelStyle = null;
    button = null;
    galleryButton = null;
  };

  const openDialog = () => {
    const ownerDocument = container.ownerDocument;
    if (!ownerDocument?.body) return;
    hmbSeedanceInstallBrokerStyles(ownerDocument);
    HMB_SEEDANCE_BROKER_DIALOGS.get(ownerDocument)?.();
    const backdrop = ownerDocument.createElement("div");
    backdrop.className = "hmb-seedance-broker-backdrop";
    backdrop.innerHTML = `
      <form class="hmb-seedance-broker-dialog" role="dialog" aria-modal="true" aria-labelledby="hmb-seedance-broker-title" aria-describedby="hmb-seedance-broker-help">
        <h2 id="hmb-seedance-broker-title">FN AI Broker 주소</h2>
        <p id="hmb-seedance-broker-help">HTTPS 서버 주소를 입력하세요. 모든 제네레이터에 공통 적용되며, 재시작 후에도 직접 바꾸기 전까지 유지됩니다. 비워서 저장하면 미설정 상태로 연결하지 않습니다. 저장만으로 렌더를 시작하지 않습니다.</p>
        <label for="hmb-seedance-broker-url">서버 주소</label>
        <input id="hmb-seedance-broker-url" data-broker-url type="url" inputmode="url" autocomplete="off" spellcheck="false" maxlength="2048" placeholder="https://broker.example.com:8080" value="${escapeHtml(latestProps?.value ?? latestProps?.parameterValue ?? latestProps?.defaultValue ?? "")}">
        <div class="hmb-seedance-broker-error" data-broker-error role="alert" aria-live="polite"></div>
        <div class="hmb-seedance-broker-actions"><button type="button" data-broker-cancel>취소</button><button type="submit" data-broker-save>저장</button></div>
      </form>`;
    const form = backdrop.querySelector("form");
    const input = backdrop.querySelector("[data-broker-url]");
    const error = backdrop.querySelector("[data-broker-error]");
    const save = backdrop.querySelector("[data-broker-save]");
    const cancel = backdrop.querySelector("[data-broker-cancel]");
    let pending = false;
    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      const ownsDialog = HMB_SEEDANCE_BROKER_DIALOGS.get(ownerDocument) === close;
      backdrop.remove();
      if (ownsDialog) {
        HMB_SEEDANCE_BROKER_DIALOGS.delete(ownerDocument);
      }
      if (closeDialog === close) closeDialog = null;
      if (syncDialogDisabled === syncDisabled) syncDialogDisabled = null;
      if (!disposed && ownsDialog) button?.focus?.();
    };
    closeDialog = close;
    const syncDisabled = () => {
      if (closed || pending) return;
      const disabled = Boolean(latestProps?.disabled);
      if (input.disabled !== disabled) input.disabled = disabled;
      if (save.disabled !== disabled) save.disabled = disabled;
    };
    syncDialogDisabled = syncDisabled;
    syncDisabled();
    HMB_SEEDANCE_BROKER_DIALOGS.set(ownerDocument, close);
    const stop = (event) => event.stopPropagation?.();
    backdrop.addEventListener("pointerdown", stop);
    backdrop.addEventListener("keydown", (event) => {
      event.stopPropagation?.();
      if (event.key === "Escape") { event.preventDefault?.(); if (!pending) close(); }
      if (event.key === "Tab") {
        const controls = [input, cancel, save].filter((element) => !element.disabled);
        if (!controls.length) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && ownerDocument.activeElement === first) {
          event.preventDefault?.();
          last.focus?.();
        } else if (!event.shiftKey && ownerDocument.activeElement === last) {
          event.preventDefault?.();
          first.focus?.();
        }
      }
    });
    backdrop.addEventListener("click", (event) => {
      event.stopPropagation?.();
      if (event.target === backdrop && !pending) close();
    });
    cancel.addEventListener("click", () => { if (!pending) close(); });
    form.addEventListener("submit", async (event) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      if (pending || latestProps?.disabled) return;
      const parsed = hmbSeedanceNormalizeBrokerUrl(input.value);
      if (!parsed.ok) { error.textContent = parsed.error; input.focus?.(); return; }
      if (typeof latestProps?.onChange !== "function") {
        error.textContent = "브로커 주소 저장 기능을 사용할 수 없습니다. 노드를 다시 열어주세요.";
        return;
      }
      pending = true;
      save.disabled = true;
      cancel.disabled = true;
      error.textContent = "";
      try {
        await latestProps.onChange(parsed.value);
        close();
      } catch {
        if (disposed || closed) return;
        error.textContent = "브로커 주소를 저장하지 못했습니다. 주소와 연결 상태를 확인하세요.";
        pending = false;
        save.disabled = Boolean(latestProps?.disabled);
        cancel.disabled = false;
      }
    });
    ownerDocument.body.appendChild(backdrop);
    input.focus?.();
    input.select?.();
  };

  const syncButton = () => {
    if (disposed) return;
    nodeRoot = hmbSeedanceNodeRoot(container);
    const nextRow = nodeRoot?.querySelector?.(
      '[data-parameter-name="model_id"], [data-parameter="model_id"], .model_id',
    ) || null;
    if (!nextRow || (nextRow === modelRow && button?.isConnected && galleryButton?.isConnected)) return;
    detachButton();
    if (!nextRow || !nextRow.style) return;
    hmbSeedanceInstallBrokerStyles(container.ownerDocument);
    modelRow = nextRow;
    modelStyle = ["position", "padding-right"].map((property) => [
      property,
      modelRow.style.getPropertyValue(property),
      modelRow.style.getPropertyPriority(property),
    ]);
    const computedPadding = container.ownerDocument?.defaultView?.getComputedStyle?.(modelRow)?.paddingRight || "0px";
    modelRow.style.setProperty("position", "relative");
    modelRow.style.setProperty("padding-right", `calc(${computedPadding} + 76px)`);
    button = container.ownerDocument.createElement("button");
    button.type = "button";
    button.className = "hmb-seedance-broker-icon nodrag";
    button.textContent = "⚙";
    button.setAttribute("aria-label", "FN AI Broker 서버 주소 설정");
    button.setAttribute("aria-haspopup", "dialog");
    button.title = "FN AI Broker 서버 주소 설정";
    button.addEventListener("pointerdown", (event) => event.stopPropagation?.());
    button.addEventListener("click", (event) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      openDialog();
    });
    modelRow.appendChild(button);
    galleryButton = container.ownerDocument.createElement("button");
    galleryButton.type = "button";
    galleryButton.className = "hmb-seedance-gallery-icon nodrag";
    galleryButton.textContent = "▦";
    galleryButton.setAttribute("aria-label", "내 영상 / 리뷰 웹 갤러리");
    galleryButton.title = "내 영상 / 리뷰 웹 갤러리";
    galleryButton.addEventListener("pointerdown", (event) => event.stopPropagation?.());
    galleryButton.addEventListener("click", async (event) => {
      event.preventDefault?.();
      event.stopPropagation?.();
      const clicked = galleryButton;
      if (disposed || clicked.disabled) return;
      const bridge = hmbSeedanceRefreshCommandBridge(container);
      if (!bridge || typeof bridge.dispatch !== "function") {
        clicked.title = "갤러리 연결 기능을 사용할 수 없습니다. 노드를 다시 열어주세요.";
        return;
      }
      clicked.disabled = true;
      try {
        // Backend resolves the validated shared server and optional prefix. Credentials,
        // URLs and Task IDs never cross the browser command boundary.
        await bridge.dispatch({ action: "open_gallery", action_id: `gallery-${Date.now()}-${Math.random().toString(16).slice(2)}`,
          issued_at_ms: Date.now() });
      } catch {
        if (!disposed && clicked.isConnected) clicked.title = "웹 갤러리를 열지 못했습니다. 연결 상태를 확인하세요.";
      } finally {
        if (!disposed && clicked.isConnected) clicked.disabled = false;
      }
    });
    modelRow.appendChild(galleryButton);
  };

  const scheduleSync = () => {
    if (disposed || syncQueued) return;
    syncQueued = true;
    Promise.resolve().then(() => { syncQueued = false; syncButton(); });
  };
  const Observer = container.ownerDocument?.defaultView?.MutationObserver
    || (typeof MutationObserver === "function" ? MutationObserver : null);
  const observeRoot = () => {
    if (!Observer || nodeRoot === observedRoot) return;
    observer?.disconnect?.();
    observedRoot = nodeRoot;
    if (!nodeRoot) return;
    observer = new Observer(() => {
      if (!modelRow?.isConnected || !button?.isConnected || !galleryButton?.isConnected) scheduleSync();
    });
    observer.observe(nodeRoot, { childList: true, subtree: true });
  };
  syncButton();
  observeRoot();
  const cleanup = () => {
    disposed = true;
    observer?.disconnect?.();
    closeDialog?.();
    detachButton();
    hmbSeedanceRestoreCarrierLayout(container);
    if (container.__hmbSeedanceBrokerInstance === instance) delete container.__hmbSeedanceBrokerInstance;
  };
  const instance = {
    cleanup,
    update(nextProps) {
      latestProps = nextProps || {};
      syncDialogDisabled?.();
      hmbSeedanceMakeCommandContainerInert(container);
      syncButton();
      observeRoot();
    },
  };
  container.__hmbSeedanceBrokerInstance = instance;
  return instance;
}

function hmbSeedanceMakeCommandContainerInert(container) {
  if (!container?.style) return;
  const existing = container.__hmbSeedanceCarrierLayout;
  if (existing) { existing.sync(); return; }
  const documentRef = container.ownerDocument;
  if (documentRef?.head && !documentRef.getElementById("hmb-seedance-carrier-layout-style")) {
    const style = documentRef.createElement("style");
    style.id = "hmb-seedance-carrier-layout-style";
    style.textContent = `
      [data-hmb-seedance-hidden-carrier="true"]{height:0!important;min-height:0!important;max-height:0!important;flex:0 0 0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important}
      [data-hmb-seedance-carrier-slot="true"]{position:absolute!important;height:0!important;min-height:0!important;max-height:0!important;flex:0 0 0!important;margin:0!important;padding:0!important;border:0!important;overflow:hidden!important;opacity:0!important;pointer-events:none!important}
    `;
    documentRef.head.appendChild(style);
  }
  const snapshots = new Map();
  let observer = null;
  let observedRoot = null;
  let syncQueued = false;
  let disposed = false;
  const restore = (element, attributes) => {
    for (const [name, value] of attributes) {
      if (value === null) element.removeAttribute?.(name);
      else element.setAttribute?.(name, value);
    }
  };
  const sync = () => {
    if (disposed) return;
    const nodeRoot = hmbSeedanceNodeRoot(container);
    let parameterRow = null;
    for (let current = container, depth = 0; current && current !== nodeRoot && depth < 8; current = current.parentElement, depth += 1) {
      const name = current.getAttribute?.("data-parameter-name");
      if (name === HMB_SEEDANCE_BROKER_PARAMETER || name === "HMB_SEEDANCE_REFRESH_COMMAND") {
        parameterRow = current;
        break;
      }
    }
    const targets = new Map([[container, "data-hmb-seedance-hidden-carrier"]]);
    if (parameterRow) {
      targets.set(parameterRow, "data-hmb-seedance-hidden-carrier");
      const parameterName = parameterRow.getAttribute("data-parameter-name");
      // Griptape allocates its own 40px slot outside the widget. Collapse only
      // this dedicated slot, leaving the mounted command/settings transport
      // and the shared parameter stack intact.
      for (let current = parameterRow.parentElement, depth = 0; current && current !== nodeRoot && depth < 8; current = current.parentElement, depth += 1) {
        const parameters = Array.from(current.querySelectorAll?.("[data-parameter-name]") || []);
        if (parameters.some((element) => element.getAttribute("data-parameter-name") !== parameterName)) break;
        if (current.classList?.contains("flex-shrink-0")
          && current.classList.contains("overflow-hidden")
          && current.parentElement?.classList?.contains("flex-col")) {
          targets.set(current, "data-hmb-seedance-carrier-slot");
          break;
        }
      }
    }
    for (const [element, attributes] of snapshots) {
      if (!targets.has(element)) { restore(element, attributes); snapshots.delete(element); }
    }
    for (const [element, marker] of targets) {
      if (!snapshots.has(element)) {
        snapshots.set(element, [marker, "aria-hidden"].map((name) => [name, element.getAttribute?.(name) ?? null]));
      }
      if (element.getAttribute?.(marker) !== "true") element.setAttribute?.(marker, "true");
      if (element.getAttribute?.("aria-hidden") !== "true") element.setAttribute?.("aria-hidden", "true");
    }
    if (nodeRoot !== observedRoot) {
      observer?.disconnect?.();
      observedRoot = nodeRoot;
      const Observer = documentRef?.defaultView?.MutationObserver;
      if (nodeRoot && Observer) {
        observer = new Observer((records) => {
          const moved = records.some((record) => [...record.addedNodes, ...record.removedNodes].some(
            (element) => element === container || element.contains?.(container),
          ));
          if (!moved || syncQueued || disposed) return;
          syncQueued = true;
          Promise.resolve().then(() => { syncQueued = false; sync(); });
        });
        observer.observe(nodeRoot, { childList: true, subtree: true });
      }
    }
  };
  container.__hmbSeedanceCarrierLayout = {
    sync,
    cleanup() {
      disposed = true;
      observer?.disconnect?.();
      for (const [element, attributes] of snapshots) restore(element, attributes);
      snapshots.clear();
    },
  };
  sync();
}

function hmbSeedanceRestoreCarrierLayout(container) {
  container?.__hmbSeedanceCarrierLayout?.cleanup();
  if (container) delete container.__hmbSeedanceCarrierLayout;
}

function hmbSeedanceCommandBridgeWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  container.__hmbSeedanceCommandBridgeCleanup?.();
  hmbSeedanceMakeCommandContainerInert(container);
  let latestProps = props || {};
  let registeredRoot = null;
  const token = `hmb-seedance-command-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const registry = hmbSeedanceCommandRegistry();
  const register = () => {
    if (registeredRoot && registry?.get(registeredRoot)?.token === token) {
      registry.delete(registeredRoot);
    }
    registeredRoot = hmbSeedanceNodeRoot(container);
    if (!registeredRoot || !registry) return;
    registry.set(registeredRoot, {
      token,
      dispatch(rawCommand) {
        if (typeof latestProps?.onChange !== "function") {
          throw new Error("Seedance refresh command transport is unavailable.");
        }
        const source = rawCommand && typeof rawCommand === "object" ? rawCommand : {};
        const action = text(source.action, 48).toLowerCase();
        const actionId = text(source.action_id, 128);
        if (!["refresh_existing", "open_gallery", "finalize_draft", "cancel_draft_final"].includes(action) || !actionId) {
          throw new Error("Seedance refresh command is invalid.");
        }
        const expectedDraftJobId = text(source.expected_draft_job_id, 160);
        const draftCommand = ["finalize_draft", "cancel_draft_final"].includes(action);
        // This is an identity assertion only. The host separately authorizes
        // public Shot/Only and owner-private My Box sources before any submit.
        if (draftCommand && !/^job-(?:mybox-)?[0-9a-f]{32}$/.test(expectedDraftJobId)) {
          throw new Error("Seedance Final requires the displayed completed Draft identity.");
        }
        return latestProps.onChange({
          schema: HMB_SEEDANCE_COMMAND_SCHEMA,
          version: HMB_SEEDANCE_COMMAND_VERSION,
          action,
          action_id: actionId,
          issued_at_ms: Math.max(0, Math.floor(Number(source.issued_at_ms || Date.now()))),
          // Equality assertion only: the host chooses its current stored source.
          ...(draftCommand ? { expected_draft_job_id: expectedDraftJobId } : {}),
        });
      },
    });
  };
  register();
  const cleanup = () => {
    if (registeredRoot && registry?.get(registeredRoot)?.token === token) {
      registry.delete(registeredRoot);
    }
    registeredRoot = null;
    hmbSeedanceRestoreCarrierLayout(container);
    if (container.__hmbSeedanceCommandBridgeCleanup === cleanup) {
      delete container.__hmbSeedanceCommandBridgeCleanup;
    }
  };
  container.__hmbSeedanceCommandBridgeCleanup = cleanup;
  return {
    cleanup,
    update(nextProps) {
      latestProps = nextProps || {};
      hmbSeedanceMakeCommandContainerInert(container);
      register();
    },
  };
}

function hmbSeedanceRefreshCommandBridge(container) {
  const root = hmbSeedanceNodeRoot(container);
  return root ? hmbSeedanceCommandRegistry()?.get(root) || null : null;
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

function sameLocalPreviewUrl(left, right) {
  try { return new URL(left).href === new URL(right).href; }
  catch { return false; }
}

export function hmbSeedanceConnectLocalPreview(container, generation, video, binding = null) {
  if (!container || container.__hmbSeedancePreviewDisposed || !video) return false;
  const local = localOriginalPreview(generation?.local_preview);
  if (!local) return false;
  const raw = video.getAttribute?.("data-raw-video-value") || "";
  const src = video.getAttribute?.("src") || "";
  const revision = boundedInteger(generation?.media_revision);
  const previousOriginal = container.__hmbSeedanceLocalOriginalPreview;
  // The display-only ParameterVideo may already receive the exact local HTTP
  // URL, while VIDEO_OUT retains the canonical file. Accept only that proved
  // pair; an unrelated HTTP source must never acquire another result's state.
  const matchingOriginal = raw === local.source || raw === local.url;
  if (matchingOriginal && sameLocalPreviewUrl(src, local.url)) {
    // An unchanged, versioned local URL still denotes the same saved bytes
    // when a restored session rebases its private media counter. Adopt that
    // counter without reloading; the actual decoder owns source readiness.
    const decoded = !video.error && Number(video.readyState) >= 3
      && sameLocalPreviewUrl(video.currentSrc, local.url);
    if (binding) {
      binding.awaitingRevision = revision;
      binding.confirmedRevision = decoded ? revision : null;
      binding.canPlay = decoded;
      binding.previewError = Boolean(video.error) || (!decoded && binding.previewError);
    }
    container.__hmbSeedancePreviewReloadKey = `${revision}\u001f${videoIdentity(video)}`;
    if (decoded && container.__hmbSeedanceConfirmedPreviewMedia?.identity === videoIdentity(video)) {
      container.__hmbSeedanceConfirmedPreviewMedia.media_revision = revision;
    }
    container.__hmbSeedanceLocalOriginalPreview = { ...local, media_revision: revision };
    return false;
  }
  // The native converter retains its last HTTP URL while resolving a new
  // artifact. Replace only that previously proved original on a newer result;
  // unrelated native HTTP sources and converted fallbacks remain untouched.
  const replacingPreviousOriginal = matchingOriginal
    && canonicalPreviewPhase(generation?.phase) === "succeeded"
    && previousOriginal && revision > previousOriginal.media_revision
    && sameLocalPreviewUrl(src, previousOriginal.url);
  if ((raw && !matchingOriginal) || (src !== local.source && !(raw === local.source && !src))) {
    if (!replacingPreviousOriginal) return false;
  }
  const key = `${revision}\u001f${local.source}\u001f${local.url}`;
  if (HMB_SEEDANCE_LOCAL_PREVIEW_LOADS.get(video) === key) return false;
  HMB_SEEDANCE_LOCAL_PREVIEW_LOADS.set(video, key);
  // Try once for this element/revision, including exceptional host failures.
  // A native remount may try again; progress echoes must never form a loop.
  const previousBinding = binding && {
    canPlay: binding.canPlay,
    previewError: binding.previewError,
    awaitingRevision: binding.awaitingRevision,
    confirmedRevision: binding.confirmedRevision,
  };
  const previousReloadKey = container.__hmbSeedancePreviewReloadKey;
  const previousFailure = container.__hmbSeedancePreviewFailure;
  if (binding) {
    binding.canPlay = false;
    binding.previewError = false;
    binding.awaitingRevision = generation.media_revision;
    binding.confirmedRevision = null;
  }
  container.__hmbSeedancePreviewReloadKey = `${generation.media_revision}\u001f${videoIdentity(video)}`;
  if (container.__hmbSeedancePreviewFailure?.key === binding?.mediaKey) {
    delete container.__hmbSeedancePreviewFailure;
  }
  // This is Griptape's local file route to the original bytes. Keep the native
  // element, controls, canonical artifact and authoring settings unchanged.
  try {
    video.setAttribute("src", local.url);
    video.load?.();
  } catch {
    if (binding) Object.assign(binding, previousBinding);
    container.__hmbSeedancePreviewReloadKey = previousReloadKey;
    container.__hmbSeedancePreviewFailure = previousFailure;
    return false;
  }
  container.__hmbSeedanceLocalOriginalPreview = { ...local, media_revision: revision };
  return true;
}

function videoMediaFormat(identity) {
  const path = text(identity, 2048).toLowerCase().split(/[?#]/, 1)[0];
  const extension = path.match(/\.([a-z0-9]{2,8})$/)?.[1] || "";
  return extension === "mov" || extension === "mp4" ? extension : "";
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
  binding.video?.removeEventListener?.("error", binding.onError);
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
    previewError: Boolean(video.error),
    mediaKey: "",
    awaitingRevision: null,
    confirmedRevision: null,
    onCanPlay: null,
    onEmptied: null,
    onError: null,
  };
  binding.onCanPlay = () => {
    const nativeSrc = video.getAttribute?.("src") || "";
    if (binding.awaitingRevision !== null && nativeSrc && video.currentSrc
        && !sameLocalPreviewUrl(video.currentSrc, nativeSrc)) return;
    binding.canPlay = true;
    binding.previewError = false;
    if (container.__hmbSeedancePreviewFailure?.key === binding.mediaKey) {
      delete container.__hmbSeedancePreviewFailure;
    }
    if (binding.awaitingRevision !== null) {
      binding.confirmedRevision = binding.awaitingRevision;
    }
    schedulePreviewSync(container);
  };
  binding.onEmptied = () => {
    binding.canPlay = false;
    // Native players reset after a decode error and may remount on each host
    // echo. That reset is not evidence that this same saved file is playable.
    binding.previewError = container.__hmbSeedancePreviewFailure?.key === binding.mediaKey;
    schedulePreviewSync(container);
  };
  binding.onError = () => {
    binding.canPlay = false;
    binding.previewError = true;
    if (binding.mediaKey) container.__hmbSeedancePreviewFailure = {
      key: binding.mediaKey, identity: binding.identity, media_revision: binding.mediaRevision,
    };
    schedulePreviewSync(container);
  };
  video.addEventListener?.("canplay", binding.onCanPlay);
  video.addEventListener?.("loadeddata", binding.onCanPlay);
  video.addEventListener?.("emptied", binding.onEmptied);
  video.addEventListener?.("error", binding.onError);
  container.__hmbSeedancePreviewVideoBinding = binding;
}

function armSameSourceRevisionReload(container, generation, identity, video, binding, previousFailure = null) {
  const confirmed = container?.__hmbSeedanceConfirmedPreviewMedia;
  const previous = confirmed?.identity === identity ? confirmed : previousFailure;
  if (
    !container
    || generation.phase !== "succeeded"
    || !previous
    || previous.identity !== identity
    || previous.media_revision === generation.media_revision
    || !binding
  ) return false;
  const key = `${generation.media_revision}\u001f${identity}`;
  if (container.__hmbSeedancePreviewFailure?.key === key) return false;
  if (container.__hmbSeedancePreviewReloadKey !== key) {
    container.__hmbSeedancePreviewReloadKey = key;
    binding.awaitingRevision = generation.media_revision;
    binding.confirmedRevision = null;
    binding.canPlay = false;
    binding.previewError = false;
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

function draftScope(state, action = "finalize_draft") {
  if (action === "cancel_draft_final") return JSON.stringify([action, state.draft.active_job_id]);
  return JSON.stringify([
    hmbSeedanceShotKey(state), state.shot_catalog?.publisher_instance_uuid || "",
    state.draft.job_id,
  ]);
}

function clearDraftRequest(container) {
  clearTimeout(container.__hmbSeedanceDraftTimeout);
  clearTimeout(container.__hmbSeedanceDraftDispatchTimeout);
  if (container.__hmbSeedanceDraftFrame !== undefined && typeof cancelAnimationFrame === "function") {
    cancelAnimationFrame(container.__hmbSeedanceDraftFrame);
  }
  delete container.__hmbSeedanceDraftTimeout;
  delete container.__hmbSeedanceDraftDispatchTimeout;
  delete container.__hmbSeedanceDraftFrame;
  delete container.__hmbSeedanceDraftPending;
}

export function hmbSeedanceSyncDraftAction(container, state) {
  if (!container) return false;
  const cancelling = state.draft.cancel_available && Boolean(state.draft.active_job_id);
  const action = cancelling ? "cancel_draft_final" : "finalize_draft";
  const scope = draftScope(state, action);
  const pending = container.__hmbSeedanceDraftPending;
  if (pending && (
    pending.scope !== scope || pending.action !== action || pending.root !== hmbSeedanceNodeRoot(container)
    || (pending.action === "finalize_draft" && (state.draft.busy || !state.draft.final_available || container.__hmbSeedancePendingShot))
    || container.isConnected === false
  )) {
    clearDraftRequest(container);
    delete container.__hmbSeedanceDraftAttempt;
    delete container.__hmbSeedanceDraftError;
  }
  if (container.__hmbSeedanceDraftError?.scope !== scope) delete container.__hmbSeedanceDraftError;
  const button = container.querySelector?.("[data-hmb-seedance-finalize-draft]");
  if (!button) return false;
  const waiting = Boolean(container.__hmbSeedanceDraftPending);
  const hiddenFinal = state.draft.final_visible === false
    || ["completed", "consumed", "expired", "not_draft"].includes(state.draft.final_state);
  const verifiedAvailable = !state.draft.final_state || state.draft.final_state === "available";
  button.hidden = !cancelling && (hiddenFinal || !state.draft.visible || !state.draft.job_id || Boolean(container.__hmbSeedancePendingShot));
  button.disabled = button.hidden || waiting || (!cancelling && (!verifiedAvailable || !state.draft.final_available || state.draft.busy));
  button.setAttribute?.("aria-busy", waiting || (!cancelling && state.draft.final_busy) ? "true" : "false");
  button.title = container.__hmbSeedanceDraftError?.message || (cancelling
    ? "로컬 Final 조회를 중지합니다. 접수된 서버 렌더는 계속될 수 있습니다."
    : state.draft.reason || "완료된 Draft로 현재 Generator만 1회 실행해 1080p로 받습니다. 현재 프롬프트·소스·설정은 다시 전송하지 않으며 Agent도 재실행하지 않습니다. MOV 기본 · MOV 미지원 시 MP4.");
  const statusLabel = state.draft.final_state === "checking" ? "Final 상태 확인 중…"
    : ["reserved", "running"].includes(state.draft.final_state) ? "Final 처리 중…"
    : ["unknown", "unavailable"].includes(state.draft.final_state) ? "Final 확인 필요" : "Draft final";
  setElementText(button, cancelling ? (waiting ? "중지 요청 중…" : "Final 중지")
    : waiting || state.draft.final_busy ? "Final 처리 중…" : statusLabel);
  return !button.hidden;
}

export function hmbSeedanceRequestDraftFinal(container) {
  return requestDraftAction(container, "finalize_draft");
}

export function hmbSeedanceRequestDraftCancel(container) {
  return requestDraftAction(container, "cancel_draft_final");
}

function requestDraftAction(container, action) {
  const state = hmbSeedanceShotState(container?.__hmbSeedanceLatestProps || {});
  const root = hmbSeedanceNodeRoot(container);
  const cancelling = action === "cancel_draft_final";
  const available = (live) => cancelling
    ? live.draft.cancel_available && Boolean(live.draft.active_job_id)
    : !container.__hmbSeedancePendingShot && live.draft.visible && Boolean(live.draft.job_id)
      && live.draft.final_visible !== false && (!live.draft.final_state || live.draft.final_state === "available")
      && live.draft.final_available && !live.draft.busy && !live.draft.cancel_available;
  if (
    !container || container.__hmbSeedancePreviewDisposed || container.isConnected === false
    || !root || root.isConnected === false || !available(state) || container.__hmbSeedanceDraftPending
    || container.__hmbSeedancePreviewActionPending
  ) return false;
  const scope = draftScope(state, action);
  const update = () => refresh(container, container.__hmbSeedanceLatestProps || {});
  if (!hmbSeedanceRefreshCommandBridge(container)) {
    container.__hmbSeedanceDraftError = { scope, message: "Final 요청을 전달할 수 없습니다. 노드를 다시 연 뒤 재시도하세요." };
    update();
    return false;
  }
  // Reuse an unacknowledged action ID after a delivery timeout. A slow reply
  // must not turn another click into a second billable Final request.
  const attempt = container.__hmbSeedanceDraftAttempt;
  const pending = {
    scope, root, action, expected_draft_job_id: cancelling ? state.draft.active_job_id : state.draft.job_id,
    action_id: attempt?.scope === scope ? attempt.action_id
      : `${cancelling ? "cancel-final" : "final"}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`,
  };
  container.__hmbSeedanceDraftAttempt = pending;
  container.__hmbSeedanceDraftPending = pending;
  delete container.__hmbSeedanceDraftError;
  const current = () => {
    const live = hmbSeedanceShotState(container.__hmbSeedanceLatestProps || {});
    return container.__hmbSeedanceDraftPending === pending
      && !container.__hmbSeedancePreviewDisposed && container.isConnected !== false
      && root.isConnected !== false && hmbSeedanceNodeRoot(container) === root
      && draftScope(live, action) === scope && available(live);
  };
  const reject = (message) => {
    if (!current()) return;
    clearDraftRequest(container);
    container.__hmbSeedanceDraftError = { scope, message: text(message || HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT, 240) };
    update();
  };
  container.__hmbSeedanceDraftTimeout = setTimeout(
    () => reject(HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT), HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS,
  );
  container.__hmbSeedanceDraftTimeout?.unref?.();
  update();
  const dispatch = () => {
    delete container.__hmbSeedanceDraftDispatchTimeout;
    if (!current()) {
      if (container.__hmbSeedanceDraftPending === pending) clearDraftRequest(container);
      return;
    }
    const bridge = hmbSeedanceRefreshCommandBridge(container);
    if (!bridge) { reject("Final 요청 전달 경로가 닫혔습니다. 노드를 다시 연 뒤 재시도하세요."); return; }
    try {
      const result = bridge.dispatch({
        action, action_id: pending.action_id, issued_at_ms: Date.now(),
        expected_draft_job_id: pending.expected_draft_job_id,
      });
      if (result && typeof result.then === "function") Promise.resolve(result).catch((error) => reject(error?.message || error));
    } catch (error) { reject(error?.message || error); }
  };
  const afterPaint = () => {
    delete container.__hmbSeedanceDraftFrame;
    if (current()) container.__hmbSeedanceDraftDispatchTimeout = setTimeout(dispatch, 0);
  };
  if (typeof requestAnimationFrame === "function") container.__hmbSeedanceDraftFrame = requestAnimationFrame(afterPaint);
  else afterPaint();
  return true;
}

export function hmbSeedanceRequestExistingResult(container) {
  const state = hmbSeedanceShotState(container?.__hmbSeedanceLatestProps || {});
  const generation = state.generation;
  if (
    !container
    || generation.action !== "refresh_existing"
    || !generation.job_id
    || state.draft.busy || container?.__hmbSeedanceDraftPending
    || previewActionPending(container, generation)
  ) return false;
  if (!hmbSeedanceRefreshCommandBridge(container)) {
    container.__hmbSeedancePreviewActionError = HMB_SEEDANCE_REFRESH_TRANSPORT_UNAVAILABLE;
    schedulePreviewSync(container);
    return false;
  }
  const pendingRequest = {
    job_id: generation.job_id,
    phase: generation.phase,
    media_revision: generation.media_revision,
    action_id: `refresh-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`,
  };
  container.__hmbSeedancePreviewActionPending = pendingRequest;
  delete container.__hmbSeedancePreviewActionError;
  clearTimeout(container.__hmbSeedancePreviewActionTimeout);
  clearTimeout(container.__hmbSeedancePreviewActionDispatchTimeout);
  delete container.__hmbSeedancePreviewActionDispatchTimeout;
  if (
    container.__hmbSeedancePreviewActionDispatchFrame !== undefined
    && typeof cancelAnimationFrame === "function"
  ) {
    cancelAnimationFrame(container.__hmbSeedancePreviewActionDispatchFrame);
  }
  delete container.__hmbSeedancePreviewActionDispatchFrame;
  const releaseRequest = (message) => {
    if (
      container.__hmbSeedancePreviewDisposed
      || container.__hmbSeedancePreviewActionPending !== pendingRequest
    ) return false;
    clearTimeout(container.__hmbSeedancePreviewActionTimeout);
    delete container.__hmbSeedancePreviewActionTimeout;
    clearTimeout(container.__hmbSeedancePreviewActionDispatchTimeout);
    delete container.__hmbSeedancePreviewActionDispatchTimeout;
    if (
      container.__hmbSeedancePreviewActionDispatchFrame !== undefined
      && typeof cancelAnimationFrame === "function"
    ) {
      cancelAnimationFrame(container.__hmbSeedancePreviewActionDispatchFrame);
    }
    delete container.__hmbSeedancePreviewActionDispatchFrame;
    delete container.__hmbSeedancePreviewActionPending;
    container.__hmbSeedancePreviewActionError = text(
      message || HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT,
      240,
    );
    schedulePreviewSync(container);
    return true;
  };
  if (typeof setTimeout === "function") {
    container.__hmbSeedancePreviewActionTimeout = setTimeout(() => {
      releaseRequest(HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT);
    }, HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS);
    container.__hmbSeedancePreviewActionTimeout?.unref?.();
  }
  schedulePreviewSync(container);
  const rejectRequest = (message) => releaseRequest(
    message || HMB_SEEDANCE_REFRESH_DELIVERY_TIMEOUT,
  );
  const dispatch = () => {
    delete container.__hmbSeedancePreviewActionDispatchTimeout;
    if (container.__hmbSeedancePreviewDisposed) return;
    const liveGeneration = hmbSeedanceShotState(
      container.__hmbSeedanceLatestProps || {},
    ).generation;
    if (
      container.__hmbSeedancePreviewActionPending !== pendingRequest
      || !previewActionPending(container, liveGeneration)
    ) return;
    const bridge = hmbSeedanceRefreshCommandBridge(container);
    if (!bridge || typeof bridge.dispatch !== "function") {
      rejectRequest(HMB_SEEDANCE_REFRESH_TRANSPORT_UNAVAILABLE);
      return;
    }
    let result;
    try {
      // The dedicated zero-height command parameter carries only this
      // one-shot action. It is independent of the durable Shot/catalog value,
      // carries no browser task ID, and never enters React's native button.
      result = bridge.dispatch({
        action: "refresh_existing",
        action_id: pendingRequest.action_id,
        issued_at_ms: Date.now(),
      });
    } catch (error) {
      rejectRequest(error?.message || error);
      return;
    }
    if (result && typeof result.then === "function") {
      Promise.resolve(result).catch((error) => {
        rejectRequest(error?.message || error);
      });
    }
  };
  const dispatchAfterPaint = () => {
    delete container.__hmbSeedancePreviewActionDispatchFrame;
    if (container.__hmbSeedancePreviewDisposed) return;
    if (typeof setTimeout === "function") {
      // The frame commits the visible busy state; the timer then leaves that
      // paint task before entering Griptape's retained-mode value transaction.
      container.__hmbSeedancePreviewActionDispatchTimeout = setTimeout(dispatch, 0);
    } else {
      Promise.resolve().then(dispatch);
    }
  };
  if (typeof requestAnimationFrame === "function") {
    // setTimeout(0) alone is not a paint guarantee in Electron. When a retained-
    // mode host callback is slow, dispatching it before the next frame makes the
    // whole node appear frozen even though the request is asynchronous.
    container.__hmbSeedancePreviewActionDispatchFrame = requestAnimationFrame(
      dispatchAfterPaint,
    );
  } else {
    dispatchAfterPaint();
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
    previousRegion.removeAttribute?.("data-hmb-seedance-preview-static");
    restorePreviewRegionPosition(previousRegion);
  }
  container.__hmbSeedancePreviewRegion = region;
  ensurePreviewRegionPosition(region);
  const video = previewVideo(region);
  bindPreviewVideo(container, video);
  const binding = container.__hmbSeedancePreviewVideoBinding;
  const identity = videoIdentity(video);
  const visibleVideo = Boolean(video && identity);
  const previousFailure = container.__hmbSeedancePreviewFailure;
  if (binding) {
    binding.mediaKey = `${generation.media_revision}\u001f${identity}`;
    binding.mediaRevision = generation.media_revision;
    if (container.__hmbSeedancePreviewFailure?.key === binding.mediaKey) {
      // The native player may already have recovered or been remounted before
      // our ready listener runs. Actual decoded media is stronger evidence
      // than an old element's cached error.
      // Undecoded remounts keep the failure, without starting a reload loop.
      if (!video?.error && Number(video.readyState) >= 3) {
        binding.canPlay = true;
        binding.previewError = false;
        delete container.__hmbSeedancePreviewFailure;
      } else {
        binding.previewError = true;
      }
    } else {
      delete container.__hmbSeedancePreviewFailure;
    }
  }
  const connectedLocalPreview = hmbSeedanceConnectLocalPreview(
    container, generation, video, binding,
  );
  const localOriginal = localOriginalPreview(generation.local_preview);
  const nativeRaw = video?.getAttribute?.("data-raw-video-value") || "";
  // A new descriptor can precede React's raw artifact update. Never reload the
  // retained old HTTP source while waiting for that exact original to arrive.
  const awaitingLocalOriginal = Boolean(localOriginal && (
    (nativeRaw && nativeRaw !== localOriginal.source && nativeRaw !== localOriginal.url)
    || !sameLocalPreviewUrl(video?.getAttribute?.("src"), localOriginal.url)
  ));
  const awaitingDecodedRevision = binding?.awaitingRevision === generation.media_revision
    && binding?.confirmedRevision !== generation.media_revision;
  const waitingForSameSourceReload = connectedLocalPreview || awaitingLocalOriginal || awaitingDecodedRevision || armSameSourceRevisionReload(
    container,
    generation,
    identity,
    video,
    binding,
    previousFailure,
  );
  const nativePlayable = Boolean(
    visibleVideo
      && !waitingForSameSourceReload
      && binding?.previewError !== true
      && (Number(video.readyState) >= 3 || binding?.canPlay === true),
  );
  if (binding?.previewError && binding.mediaKey) {
    container.__hmbSeedancePreviewFailure = {
      key: binding.mediaKey, identity: binding.identity, media_revision: generation.media_revision,
    };
  }
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
    previewError: binding?.previewError === true,
    mediaFormat: videoMediaFormat(identity),
  });
  let overlay = region.querySelector?.(".hmb-seedance-preview-overlay");
  if (!presentation.visible) {
    region.removeAttribute?.("data-hmb-seedance-preview-static");
    overlay?.remove?.();
    return true;
  }
  if (!overlay) overlay = createPreviewOverlay(region);
  if (!overlay) return false;
  const pending = previewActionPending(container, generation);
  const visiblyBusy = presentation.busy || pending;
  const staticPreview = !visibleVideo && !playableVideo
    && (!presentation.busy || binding?.previewError === true);
  if (staticPreview) {
    if (region.getAttribute?.("data-hmb-seedance-preview-static") !== "true") {
      region.setAttribute?.("data-hmb-seedance-preview-static", "true");
    }
  } else {
    region.removeAttribute?.("data-hmb-seedance-preview-static");
  }
  overlay.dataset.static = staticPreview ? "true" : "false";
  overlay.dataset.phase = presentation.phase;
  overlay.dataset.mode = presentation.mode;
  overlay.dataset.busy = visiblyBusy ? "true" : "false";
  overlay.setAttribute?.("aria-busy", visiblyBusy ? "true" : "false");
  overlay.dataset.tone = presentation.tone;
  const shotNumber = hmbSeedancePaletteShotNumber(state);
  const theme = SHOT_THEME[shotNumber];
  overlay.style?.setProperty?.("--shot-rgb", theme.rgb);
  overlay.style?.setProperty?.("--shot-soft", theme.soft);
  const title = overlay.querySelector?.(".hmb-seedance-preview-overlay__title");
  const detail = overlay.querySelector?.(".hmb-seedance-preview-overlay__detail");
  const elapsed = overlay.querySelector?.(".hmb-seedance-preview-overlay__elapsed");
  const action = overlay.querySelector?.("[data-hmb-seedance-preview-action]");
  const actionError = text(container.__hmbSeedancePreviewActionError, 240);
  setElementText(
    title,
    pending ? "기존 작업 결과 확인 중…" : presentation.title,
  );
  setElementText(
    detail,
    actionError
      || (pending ? "새 작업을 만들지 않고 기존 작업만 확인합니다." : presentation.detail),
  );
  setElementText(elapsed, presentation.elapsed ? `경과 시간 ${presentation.elapsed}` : "");
  if (elapsed?.style) elapsed.style.display = presentation.elapsed ? "" : "none";
  if (action) {
    if (action.style) {
      action.style.display = presentation.action === "refresh_existing" ? "" : "none";
    }
    action.disabled = pending;
    action.setAttribute?.("aria-busy", pending ? "true" : "false");
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

function hmbSeedancePreviewAncestorKind(element) {
  let current = element || null;
  for (let depth = 0; current && depth < 20; depth += 1, current = current.parentElement) {
    if (current.classList?.contains?.("hmb-seedance-preview-overlay")) return "overlay";
    if (
      String(current.tagName || "").toUpperCase() === "VIDEO"
      || current.hasAttribute?.("data-vp-video-area") === true
      || current.getAttribute?.("data-parameter-name") === "video_url"
      || classTokens(current).includes("video_url")
    ) return "preview";
    const className = String(current.className || "").toLowerCase();
    if (className.includes("react-flow__node")) break;
  }
  return "";
}

function hmbSeedanceNodeContainsPreviewSurface(node) {
  if (!node || typeof node !== "object") return false;
  if (hmbSeedancePreviewAncestorKind(node) === "preview") return true;
  return Boolean(
    node.querySelector?.('[data-parameter-name="video_url"]')
    || node.querySelector?.('[data-vp-video-area]')
    || node.querySelector?.("video")
    || node.querySelector?.(".video_url"),
  );
}

export function hmbSeedancePreviewMutationIsRelevant(record) {
  if (!record || typeof record !== "object") return false;
  const targetKind = hmbSeedancePreviewAncestorKind(record.target);
  if (targetKind === "overlay") return false;
  if (record.type === "attributes") return targetKind === "preview";
  const changedNodes = [
    ...Array.from(record.addedNodes || []),
    ...Array.from(record.removedNodes || []),
  ];
  // A childList record targets the preview region when this widget mounts or
  // removes its own overlay.  Inspect the changed nodes before accepting that
  // target so self-authored status DOM never schedules another rescan.
  if (!changedNodes.length) return targetKind === "preview";
  return changedNodes.some((node) => (
    hmbSeedancePreviewAncestorKind(node) !== "overlay"
    && hmbSeedanceNodeContainsPreviewSurface(node)
  ));
}

function installPreviewObserver(container) {
  if (!container || container.__hmbSeedancePreviewObserver || typeof MutationObserver !== "function") {
    return;
  }
  const nodeRoot = hmbSeedanceNodeRoot(container);
  if (!nodeRoot) return;
  const observer = new MutationObserver((records) => {
    if (records.some((record) => hmbSeedancePreviewMutationIsRelevant(record))) {
      schedulePreviewSync(container);
    }
  });
  observer.observe(nodeRoot, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["src", "data-raw-video-value"],
  });
  container.__hmbSeedancePreviewObserver = observer;
}

export function hmbSeedanceCleanupPreviewOverlay(container) {
  if (!container) return false;
  container.__hmbSeedancePreviewDisposed = true;
  clearDraftRequest(container);
  delete container.__hmbSeedanceDraftAttempt;
  delete container.__hmbSeedanceDraftError;
  container.__hmbSeedancePreviewObserver?.disconnect?.();
  delete container.__hmbSeedancePreviewObserver;
  clearTimeout(container.__hmbSeedancePreviewActionTimeout);
  delete container.__hmbSeedancePreviewActionTimeout;
  clearTimeout(container.__hmbSeedancePreviewActionDispatchTimeout);
  delete container.__hmbSeedancePreviewActionDispatchTimeout;
  if (
    container.__hmbSeedancePreviewActionDispatchFrame !== undefined
    && typeof cancelAnimationFrame === "function"
  ) {
    cancelAnimationFrame(container.__hmbSeedancePreviewActionDispatchFrame);
  }
  delete container.__hmbSeedancePreviewActionDispatchFrame;
  delete container.__hmbSeedancePreviewActionPending;
  delete container.__hmbSeedancePreviewActionError;
  removePreviewVideoListeners(container);
  const region = container.__hmbSeedancePreviewRegion;
  region?.querySelector?.(".hmb-seedance-preview-overlay")?.remove?.();
  region?.removeAttribute?.("data-hmb-seedance-preview-static");
  restorePreviewRegionPosition(region);
  delete container.__hmbSeedancePreviewRegion;
  delete container.__hmbSeedancePreviewOnRetrieve;
  delete container.__hmbSeedancePreviewActionPending;
  delete container.__hmbSeedancePreviewActionError;
  delete container.__hmbSeedanceConfirmedPreviewMedia;
  delete container.__hmbSeedancePreviewReloadKey;
  delete container.__hmbSeedanceLocalOriginalPreview;
  delete container.__hmbSeedancePreviewFailure;
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
  if (container?.ownerDocument?.documentElement?.getAttribute?.("data-hmb-native-deletion-guard") === "engine-preflight") return false;
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
    numberBadge.textContent = hmbSeedanceShotBadge(state);
  }
  hmbSeedanceSyncDraftAction(container, state);
  const error = container.__hmbSeedanceShotChangeError || "";
  const draftError = container.__hmbSeedanceDraftError?.message || "";
  hmbSeedanceSetStatus(
    container,
    error ? "Save failed · previous Shot restored" : container.__hmbSeedanceModeSelectionError || draftError,
    error || container.__hmbSeedanceModeSelectionError || draftError,
  );
  hmbSeedanceSyncPreviewOverlay(container, state);
  installPreviewObserver(container);
  hmbSeedanceSyncRemotePromptEdge(container, state);
  container.__hmbSeedanceFlushShotQueue?.();
  container.__hmbUnifiedNativeHeader?.refresh();
  return true;
}

function hmbSeedanceShotWaiting(state) {
  if (!state?.execution_mode) return false;
  if (state.selection_request) return true;
  if (state.execution_mode === "only") return false;
  return state.execution_mode !== "shot" || !state.shot?.shot_uuid
    || state.shot_catalog?.channel_uuid !== state.shot.channel_uuid
    || !(state.shot_catalog.shots || []).some((shot) => shot.shot_uuid === state.shot.shot_uuid);
}

function hmbSeedanceModeLabel(state) {
  if (state.selection_request?.mode === "only") return "Only · 적용 중";
  if (state.selection_request?.mode === "shot") return "샷 선택 적용 중";
  return state.requested_mode === "shot" || state.execution_mode === "waiting" ? "샷 연결 대기" : "선택 대기";
}

function hmbSeedanceShotBadge(state) {
  if (hmbSeedanceShotWaiting(state)) return "대기";
  return state.shot.shot_uuid ? String(state.shot.number).padStart(2, "0") : "Only";
}

function hmbSeedanceShotKey(state) {
  if (hmbSeedanceShotWaiting(state)) return HMB_SHOT_WAITING_KEY;
  return state?.shot?.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}` : HMB_SHOT_ONLY_KEY;
}

function hmbSeedanceModeIntentKey(state) {
  if (state.requested_mode !== "shot") return state.requested_mode;
  const shot = state.pending_shot || state.shot;
  return `shot\u001f${shot.channel_uuid}\u001f${shot.shot_uuid}`;
}

function hmbSeedanceClearShotSelection(container, clearQueue = false) {
  clearTimeout(container.__hmbSeedanceShotSelectionTimeout);
  delete container.__hmbSeedanceShotSelectionTimeout;
  delete container.__hmbSeedancePendingShot;
  if (clearQueue) delete container.__hmbSeedanceQueuedShot;
}

function hmbSeedanceResolveShotEcho(container, incomingProps) {
  const pending = container.__hmbSeedancePendingShot;
  const incoming = hmbSeedanceShotState(incomingProps);
  const retainedProps = container.__hmbSeedanceLatestProps;
  const retained = hmbSeedanceShotState(retainedProps);
  const reject = () => ({ props: retainedProps, stale: true });
  const instance = incoming.execution_mode_instance;
  const baseline = container.__hmbSeedanceModeBaseline;
  if (baseline && (!instance || container.__hmbSeedanceRetiredModeInstances?.has(instance))) return reject();
  if (instance) {
    if (baseline?.execution_mode_instance === instance) {
      if (incoming.execution_mode_revision < baseline.execution_mode_revision
        || incoming.execution_mode_state_revision < baseline.execution_mode_state_revision
        || (incoming.execution_mode_revision === baseline.execution_mode_revision
          && hmbSeedanceModeIntentKey(incoming) !== hmbSeedanceModeIntentKey(baseline))
        || (incoming.execution_mode_state_revision === baseline.execution_mode_state_revision
          && (incoming.execution_mode !== baseline.execution_mode
            || incoming.execution_mode_revision !== baseline.execution_mode_revision))) return reject();
    } else if (baseline) {
      const retired = container.__hmbSeedanceRetiredModeInstances || new Set();
      retired.add(baseline.execution_mode_instance);
      container.__hmbSeedanceRetiredModeInstances = retired;
      hmbSeedanceClearShotSelection(container, true);
      delete container.__hmbSeedanceShotChangeError;
      delete container.__hmbSeedanceModeSelectionError;
      delete container.__hmbSeedanceUnconfirmedSelection;
      hmbSeedanceNextChangeOwner(container);
    }
    const unconfirmed = container.__hmbSeedanceUnconfirmedSelection;
    if (unconfirmed && instance === unconfirmed.expectedInstance
      && incoming.execution_mode_revision > unconfirmed.expectedRevision
      && incoming.execution_mode === unconfirmed.targetMode
      && hmbSeedanceShotKey(incoming) === unconfirmed.targetKey) {
      if (container.__hmbSeedanceModeSelectionError === unconfirmed.message) delete container.__hmbSeedanceModeSelectionError;
      delete container.__hmbSeedanceUnconfirmedSelection;
    }
    // Store only backend authority. The optimistic selection payload keeps this
    // baseline unchanged until a matching, newer intent is acknowledged.
    if (!incoming.selection_request) container.__hmbSeedanceModeBaseline = incoming;
    if (pending?.expectedInstance && baseline?.execution_mode_instance === instance) {
      const targetMatches = incoming.execution_mode === pending.targetMode
        && (pending.targetMode === "only" || hmbSeedanceShotKey(incoming) === pending.targetKey);
      if (incoming.execution_mode_revision <= pending.expectedRevision) return reject();
      // A newer authoritative selection may supersede this request. It must
      // invalidate a rejected transport promise as well as the pending label.
      if (targetMatches || incoming.execution_mode_revision > pending.expectedRevision) {
        hmbSeedanceClearShotSelection(container);
        return { props: incomingProps, stale: false };
      }
    }
  }
  if (!pending || incomingProps === retainedProps || pending.expectedInstance) return { props: incomingProps, stale: false };
  const catalogOlder = incoming.shot_catalog.channel_uuid === retained.shot_catalog.channel_uuid
    && Number(incoming.shot_catalog.generation || 0) < Number(retained.shot_catalog.generation || 0);
  const catalog = catalogOlder ? retained.shot_catalog : incoming.shot_catalog;
  const incomingKey = hmbSeedanceShotKey(incoming);
  if (incomingKey === pending.targetKey) {
    delete container.__hmbSeedancePendingShot;
    return { props: incomingProps, stale: false };
  }
  const targetAvailable = pending.targetKey === HMB_SHOT_ONLY_KEY || (catalog.shots || []).some(
    (shot) => `${catalog.channel_uuid}\u001f${shot.shot_uuid}` === pending.targetKey,
  );
  if (!targetAvailable || !pending.blockedKeys.has(incomingKey)) {
    delete container.__hmbSeedancePendingShot;
    return { props: incomingProps, stale: false };
  }
  return {
    props: { ...incomingProps, value: retained, parameterValue: retained, defaultValue: retained },
    stale: true,
  };
}

const HMB_SEEDANCE_PREFLIGHT_SCHEMA = "hmb-seedance-render-preflight";
// A document can display one preflight owner. Retiring the old owner also
// retires its timers/results before another Generator opens the same dialog.
const HMB_SEEDANCE_PREFLIGHT_DIALOGS = new WeakMap();

export function hmbSeedancePreflightReport(props) {
  const raw=props?.value ?? props?.parameterValue ?? props?.defaultValue ?? {};
  const issue=value=>({message:String(value?.message || "").slice(0,300),severity:["error","warning","info"].includes(value?.severity)?value.severity:"info"});
  return {schema:HMB_SEEDANCE_PREFLIGHT_SCHEMA,version:1,
    phase:["idle","complete","stale","cancelled"].includes(raw.phase)?raw.phase:"idle",
    request_id:/^[0-9a-f]{32}$/.test(String(raw.request_id || ""))?raw.request_id:"",
    ok:raw.ok===true,notice:String(raw.notice || "점검 시점의 로컬 상태입니다. 업로드·Agent·렌더·연결 변경 없음.").slice(0,400),
    checked_at_ms:boundedInteger(raw.checked_at_ms),
    issues:Array.isArray(raw.issues)?raw.issues.slice(0,20).map(issue):[],
    rows:Array.isArray(raw.rows)?raw.rows.slice(0,5).map(row=>({
      number:boundedInteger(row.number,{min:1,max:5}),name:String(row.name || "Only").slice(0,128),
      generator:String(row.generator || "").slice(0,256),model:String(row.model || "").slice(0,80),
      task:String(row.task || "").slice(0,80),resolution:String(row.resolution || "").slice(0,32),
      output:String(row.output || "").slice(0,128),status:["error","warning","ready"].includes(row.status)?row.status:"error",
      media:row.media && typeof row.media==="object"?row.media:{},
      connections:row.connections && typeof row.connections==="object"?Object.entries(row.connections).slice(0,12).map(([key,value])=>`${String(key).slice(0,64)}: ${String(value).slice(0,128)}`).join(" · "):"",
      issues:Array.isArray(row.issues)?row.issues.slice(0,20).map(issue):[],
    })):[]};
}

function hmbSeedancePreflightContainer(container,props) {
  if((props?.value ?? props?.parameterValue ?? props?.defaultValue)?.schema===HMB_SEEDANCE_PREFLIGHT_SCHEMA)return true;
  let current=container;
  for(let n=0;current && n<8;n++,current=current.parentElement)if(current.getAttribute?.("data-parameter-name")==="HMB_SEEDANCE_PREFLIGHT")return true;
  return false;
}

function hmbSeedancePreflightWidget(container,initialProps) {
  if(container.__hmbSeedancePreflightHandle){container.__hmbSeedancePreflightHandle.update(initialProps);return container.__hmbSeedancePreflightHandle;}
  let props=initialProps || {},disposed=false,report=hmbSeedancePreflightReport(props),pending=null,dialog=null;
  const retired=new Set();const doc=container.ownerDocument || globalThis.document,win=doc?.defaultView || globalThis;
  const nonce=()=>{const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return Array.from(bytes,x=>x.toString(16).padStart(2,"0")).join("");};
  const clientSession=nonce();let sequence=0;
  container.classList?.add("nodrag");
  container.innerHTML=`<style>
    .hmb-seedance-preflight{height:38px;display:flex;align-items:center;gap:9px;font:11px Inter,"Noto Sans KR",system-ui,sans-serif;color:#aeb9c9}
    .hmb-seedance-preflight button{height:28px;padding:0 10px;border:1px solid #64748b;border-radius:7px;background:#151c2b;color:#dbeafe;font:inherit;font-weight:750;cursor:pointer;white-space:nowrap}
    .hmb-seedance-preflight button:hover{border-color:#f472b6;color:#fff}.hmb-seedance-preflight [data-preflight-summary]{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    </style><div class="hmb-seedance-preflight nodrag"><button type="button" data-preflight-open aria-label="5샷 렌더 전 점검">✓ 5샷 점검</button><span data-preflight-summary>생성 없이 연결·입력 확인</span></div>`;
  const openButton=container.querySelector("[data-preflight-open]"),summary=container.querySelector("[data-preflight-summary]");
  const summaryText=()=>pending?"로컬 상태 점검 중…":report.phase==="complete"?(report.ok?(report.rows.some(row=>row.status==="warning") || report.issues.some(item=>item.severity==="warning")?"로컬 오류 없음 · 경고 확인":"로컬 오류 없음 · 결과 보기"):"확인할 항목 있음 · 결과 보기"):report.phase==="stale"?"선택 변경 · 다시 점검":"생성 없이 연결·입력 확인";
  const syncSummary=()=>{const text=summaryText();if(summary.textContent!==text)summary.textContent=text;};
  const stop=()=>{if(!pending)return;for(const id of pending.frames)win.cancelAnimationFrame(id);win.clearTimeout(pending.fallback);win.clearTimeout(pending.timeout);retired.add(pending.id);while(retired.size>256)retired.delete(retired.values().next().value);pending=null;};
  const focusDialog=selector=>{
    const target=dialog?.querySelector(selector || "[data-preflight-cancel],[data-preflight-recheck],[data-preflight-close]");
    target?.focus?.({preventScroll:true});
  };
  const containFocus=event=>{
    if(!disposed && dialog && HMB_SEEDANCE_PREFLIGHT_DIALOGS.get(doc)===close && !dialog.contains(event.target))focusDialog();
  };
  const close=(options={})=>{
    if(!dialog)return;
    const owns=HMB_SEEDANCE_PREFLIGHT_DIALOGS.get(doc)===close;
    if(owns)HMB_SEEDANCE_PREFLIGHT_DIALOGS.delete(doc);
    doc.removeEventListener("focusin",containFocus,true);
    dialog.remove();dialog=null;stop();syncSummary();
    if(!disposed && owns && options.restoreFocus!==false && openButton.isConnected)openButton.focus?.({preventScroll:true});
  };
  const renderDialog=()=>{
    if(!dialog)return;
    const active=doc.activeElement,hadFocus=dialog.contains(active);
    const focusSelector=["data-preflight-close","data-preflight-cancel","data-preflight-recheck"].find(name=>active?.hasAttribute?.(name));
    const scrollTop=dialog.querySelector(".hmb-preflight-scroll")?.scrollTop || 0;
    const rows=report.rows.map(row=>`<tr data-preflight-row="${row.number}" style="--preflight-accent:${HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[row.number]}"><th scope="row"><b>${escapeHtml(String(row.number).padStart(2,"0"))} · ${escapeHtml(row.name)}</b><small>${escapeHtml(row.generator)}</small></th><td>${escapeHtml(row.model)}<small>${escapeHtml(row.task)} · ${escapeHtml(row.resolution)}</small></td><td>이미지 ${Number.isInteger(row.media.images)?row.media.images:"미확인"} · 영상 ${Number.isInteger(row.media.videos)?row.media.videos:"미확인"} · 오디오 ${Number.isInteger(row.media.audio)?row.media.audio:"미확인"}<small>${escapeHtml(row.connections)}</small></td><td>${escapeHtml(row.output || "—")}</td><td data-preflight-status="${row.status}"><b>${({ready:"로컬 확인",warning:"주의",error:"확인 필요"})[row.status]}</b>${row.issues.filter(item=>item.severity!=="info").map(item=>`<small>${escapeHtml(item.message)}</small>`).join("")}</td></tr>`).join("");
    dialog.innerHTML=`<style>
      .hmb-preflight-backdrop{position:fixed;inset:0;z-index:2147483001;display:grid;place-items:center;padding:20px;background:rgba(1,5,14,.78);font-family:Inter,"Noto Sans KR",system-ui,sans-serif;color:#e7edf7}
      .hmb-preflight-dialog{box-sizing:border-box;width:min(1160px,100%);min-width:0;max-height:88vh;display:flex;flex-direction:column;padding:20px;border:1px solid #9b4d7d;border-radius:13px;background:#0b1120;box-shadow:0 20px 50px rgba(0,0,0,.55)}
      .hmb-preflight-dialog h2{margin:0 0 10px;font-size:18px}.hmb-preflight-dialog p{margin:0 0 12px;color:#b5c2d5;font-size:12px;line-height:1.5}.hmb-preflight-scroll{overflow:auto;min-height:0}.hmb-preflight-dialog table{width:100%;border-collapse:collapse;font-size:11px;text-align:left}.hmb-preflight-dialog th,.hmb-preflight-dialog td{padding:10px;border-bottom:1px solid #27324a;vertical-align:top;max-width:290px;overflow-wrap:anywhere}.hmb-preflight-dialog tbody th{border-left:3px solid var(--preflight-accent);color:var(--preflight-accent);min-width:140px}.hmb-preflight-dialog small{display:block;margin-top:5px;font-weight:400;color:#aeb9c9;font-size:10px}.hmb-preflight-dialog [data-preflight-status="error"]>b{color:#fb7185}.hmb-preflight-dialog [data-preflight-status="warning"]>b{color:#eab308}.hmb-preflight-dialog [data-preflight-status="ready"]>b{color:#10b981}.hmb-preflight-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:15px}.hmb-preflight-actions button{padding:8px 12px;border:1px solid #52617a;border-radius:7px;background:#182338;color:#e7edf7;font:12px system-ui;cursor:pointer}.hmb-preflight-actions button[data-preflight-recheck]{border-color:#f472b6;background:#9d326d;color:#fff}.hmb-preflight-busy{padding:25px;color:#dbeafe}
    </style><section class="hmb-preflight-dialog" role="dialog" aria-modal="true" aria-labelledby="hmb-preflight-title"><h2 id="hmb-preflight-title">렌더 전 일괄 점검</h2><p>${escapeHtml(report.notice)}</p><div class="hmb-preflight-scroll">${pending?'<div class="hmb-preflight-busy" role="status">연결·미디어 수량·모델·설정·출력 경로를 확인 중입니다…</div>':`${report.issues.map(item=>`<p role="status">${escapeHtml(item.message)}</p>`).join("")}<table><thead><tr><th>ImageAsset Shot</th><th>모델 / 작업</th><th>입력 / 연결</th><th>출력 파일</th><th>점검 결과</th></tr></thead><tbody>${rows}</tbody></table>${report.checked_at_ms?`<p style="margin-top:12px">점검 시각 ${escapeHtml(new Date(report.checked_at_ms).toLocaleTimeString())} · 설정을 바꾼 후에는 다시 점검하세요.</p>`:""}`}</div><div class="hmb-preflight-actions">${pending?'<button type="button" data-preflight-cancel>점검 취소</button>':'<button type="button" data-preflight-recheck>다시 점검</button>'}<button type="button" data-preflight-close>닫기</button></div></section>`;
    dialog.querySelector("[data-preflight-close]")?.addEventListener("click",close);
    dialog.querySelector("[data-preflight-recheck]")?.addEventListener("click",inspect);
    dialog.querySelector("[data-preflight-cancel]")?.addEventListener("click",()=>{
      const previous=pending;stop();report={...report,phase:"cancelled",rows:[],issues:[{severity:"info",message:"점검을 취소했습니다. 생성 작업에는 영향이 없습니다."}]};renderDialog();syncSummary();
      if(previous?.dispatched && typeof props.onChange==="function")try{Promise.resolve(props.onChange({schema:HMB_SEEDANCE_PREFLIGHT_SCHEMA,version:1,action:"cancel",request_id:previous.id,client_session:clientSession,sequence:previous.sequence})).catch(()=>{});}catch{}
    });
    const scroll=dialog.querySelector(".hmb-preflight-scroll");if(scroll)scroll.scrollTop=scrollTop;
    if(hadFocus)focusDialog(focusSelector && dialog.querySelector(`[${focusSelector}]`)?`[${focusSelector}]`:null);
  };
  const inspect=()=>{
    if(disposed || pending)return;
    const id=nonce();const ticket={id,sequence:++sequence,frames:[],dispatched:false};pending=ticket;renderDialog();syncSummary();
    const fail=()=>{if(disposed || pending!==ticket)return;stop();report={...report,phase:"stale",rows:[],issues:[{severity:"warning",message:"점검 응답을 확인하지 못했습니다. 다시 점검하세요. 생성은 시작되지 않았습니다."}]};renderDialog();syncSummary();};
    const dispatch=()=>{if(disposed || pending!==ticket || ticket.dispatched)return;ticket.dispatched=true;win.clearTimeout(ticket.fallback);try{if(typeof props.onChange!=="function")throw Error("No transport");Promise.resolve(props.onChange({schema:HMB_SEEDANCE_PREFLIGHT_SCHEMA,version:1,action:"inspect",request_id:id,client_session:clientSession,sequence:ticket.sequence})).catch(fail);}catch{fail();}};
    ticket.frames.push(win.requestAnimationFrame(()=>{if(!disposed && pending===ticket)ticket.frames.push(win.requestAnimationFrame(dispatch));}));ticket.fallback=win.setTimeout(dispatch,120);ticket.timeout=win.setTimeout(fail,10000);
  };
  const open=()=>{
    if(disposed)return;
    if(!dialog){
      const previous=HMB_SEEDANCE_PREFLIGHT_DIALOGS.get(doc);if(previous && previous!==close)previous({restoreFocus:false});
      dialog=doc.createElement("div");dialog.className="hmb-preflight-backdrop nodrag";doc.body.appendChild(dialog);
      HMB_SEEDANCE_PREFLIGHT_DIALOGS.set(doc,close);
      dialog.addEventListener("pointerdown",event=>event.stopPropagation?.());
      dialog.addEventListener("click",event=>{event.stopPropagation?.();if(event.target===dialog)close();});
      dialog.addEventListener("keydown",event=>{
        event.stopPropagation?.();
        if(event.key==="Escape"){event.preventDefault?.();close();return;}
        if(event.key!=="Tab")return;
        const controls=Array.from(dialog.querySelectorAll("button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])"));
        if(!controls.length)return;
        const index=controls.indexOf(doc.activeElement);
        if(event.shiftKey && index<=0){event.preventDefault?.();controls.at(-1).focus?.({preventScroll:true});}
        else if(!event.shiftKey && (index<0 || index===controls.length-1)){event.preventDefault?.();controls[0].focus?.({preventScroll:true});}
      });
      doc.addEventListener("focusin",containFocus,true);
    }
    renderDialog();if(!report.rows.length)inspect();focusDialog();
  };
  const isolate=event=>{if(Number(event.button)!==1)event.stopPropagation?.();};
  openButton.addEventListener("click",open);container.addEventListener?.("pointerdown",isolate);
  const handle={update(next){if(disposed)return;props=next || props;const incoming=hmbSeedancePreflightReport(props);if(!pending || !["complete","stale","cancelled"].includes(incoming.phase) || retired.has(incoming.request_id) || incoming.request_id!==pending.id)return;stop();report=incoming;renderDialog();syncSummary();},cleanup(){if(disposed)return;disposed=true;close();stop();openButton.removeEventListener("click",open);container.removeEventListener?.("pointerdown",isolate);delete container.__hmbSeedancePreflightHandle;container.innerHTML="";}};
  container.__hmbSeedancePreflightHandle=handle;syncSummary();return handle;
}

function hmbNativeUiImplementation(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  if(hmbSeedancePreflightContainer(container,props))return hmbSeedancePreflightWidget(container,props);
  if (hmbSeedanceCommandProps(props) || hmbSeedanceCommandContainer(container)) {
    return hmbSeedanceCommandBridgeWidget(container, props);
  }
  if (hmbSeedanceBrokerContainer(container)) {
    return hmbSeedanceBrokerSettingsWidget(container, props);
  }
  delete container.__hmbSeedancePreviewDisposed;
  const latest = props || container.__hmbSeedanceLatestProps || {};
  const resolved = hmbSeedanceResolveShotEcho(container, latest);
  container.__hmbSeedanceLatestProps = resolved.props;
  const previousCleanup = container.__hmbSeedanceCleanup;
  // A factory call with new props is an authoritative lifecycle refresh, just
  // like update(). Invalidate any optimistic promise before accepting it so a
  // late rejection cannot roll the refreshed selector back.
  if (typeof previousCleanup === "function" && !resolved.stale) hmbSeedanceNextChangeOwner(container);
  if (typeof previousCleanup === "function" && refresh(container, resolved.props)) {
    return {
      cleanup: container.__hmbSeedanceCleanupProxy,
      update(nextProps) {
        if (container.__hmbSeedanceCleanup !== previousCleanup) return;
        const incoming = nextProps || container.__hmbSeedanceLatestProps || {};
        const next = hmbSeedanceResolveShotEcho(container, incoming);
        if (!next.stale) hmbSeedanceNextChangeOwner(container);
        container.__hmbSeedanceLatestProps = next.props;
        if (!refresh(container, next.props)) {
          HMBSeedanceGenerationWidget(container, next.props);
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
  const initialState = hmbSeedanceShotState(resolved.props);
  container.innerHTML = render(initialState);
  const nativeHeader = hmbInstallNativeHeaderBridge(container, "HMBSeedanceGeneration", ".hmb-seedance-shot");
  hmbSeedanceSyncDraftAction(container, initialState);
  hmbSeedanceSyncPreviewOverlay(container, initialState);
  installPreviewObserver(container);
  hmbSeedanceSyncRemotePromptEdge(container, initialState);
  const select = container.querySelector?.(".hmb-seedance-shot__select");
  const finalButton = container.querySelector?.("[data-hmb-seedance-finalize-draft]");
  const onFinalize = (event) => {
    event.preventDefault?.();
    event.stopPropagation?.();
    const state = hmbSeedanceShotState(container.__hmbSeedanceLatestProps || {});
    if (state.draft.cancel_available) hmbSeedanceRequestDraftCancel(container);
    else hmbSeedanceRequestDraftFinal(container);
  };
  finalButton?.addEventListener?.("click", onFinalize);
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
    if (previousState.execution_mode) {
      if (!previousState.execution_mode_instance) { refresh(container, liveProps); return; }
      next.selection_request = { schema: HMB_SEEDANCE_MODE_SELECTION_SCHEMA, version: 1,
        expected_revision: previousState.execution_mode_revision,
        expected_instance: previousState.execution_mode_instance, mode: selected.only ? "only" : "shot" };
    }
    // An optimistic Shot change cannot carry the previous Shot's completed Draft.
    next.draft = hmbSeedanceDraftState({ cancel_available: next.draft.cancel_available, active_job_id: next.draft.active_job_id });
    const optimisticProps = { ...liveProps, value: next, parameterValue: next, defaultValue: next };
    if (previousState.execution_mode_instance && container.__hmbSeedancePendingShot?.expectedInstance) {
      // Keep only the user's latest choice while one CAS request is awaiting
      // acknowledgement. Sending it now would reuse the old intent revision.
      const key = selected.only ? HMB_SHOT_ONLY_KEY : selected.key;
      if (key === container.__hmbSeedancePendingShot.targetKey) delete container.__hmbSeedanceQueuedShot;
      else container.__hmbSeedanceQueuedShot = { key, channel_uuid: selected.channel_uuid, shot_uuid: selected.shot_uuid };
      container.__hmbSeedanceLatestProps = optimisticProps;
      refresh(container, optimisticProps);
      return;
    }
    // Preserve the prior descriptor until retained mode has removed or
    // replaced the real edge. This prevents a cable flash during transition.
    const owner = hmbSeedanceNextChangeOwner(container);
    const previousKey = hmbSeedanceShotKey(previousState);
    const blockedKeys = new Set(container.__hmbSeedancePendingShot?.blockedKeys || []);
    blockedKeys.add(previousKey);
    container.__hmbSeedancePendingShot = {
      targetKey: selected.only ? HMB_SHOT_ONLY_KEY : selected.key, blockedKeys,
      ...(previousState.execution_mode_instance ? {
        expectedInstance: previousState.execution_mode_instance,
        expectedRevision: previousState.execution_mode_revision,
        targetMode: selected.only ? "only" : "shot",
      } : {}),
    };
    if (previousState.execution_mode_instance) {
      const ticket = container.__hmbSeedancePendingShot;
      container.__hmbSeedanceShotSelectionTimeout = setTimeout(() => {
        if (container.__hmbSeedancePendingShot !== ticket) return;
        hmbSeedanceClearShotSelection(container, true);
        hmbSeedanceNextChangeOwner(container);
        const canonical = container.__hmbSeedanceModeBaseline || previousState;
        const currentProps = container.__hmbSeedanceLatestProps || liveProps;
        container.__hmbSeedanceLatestProps = { ...currentProps, value: canonical, parameterValue: canonical, defaultValue: canonical };
        const message = "선택 적용 응답을 확인하지 못했습니다. 다시 선택하세요.";
        container.__hmbSeedanceUnconfirmedSelection = { ...ticket, message };
        container.__hmbSeedanceModeSelectionError = message;
        refresh(container, container.__hmbSeedanceLatestProps);
      }, HMB_SEEDANCE_PREVIEW_ACTION_WATCHDOG_MS);
      container.__hmbSeedanceShotSelectionTimeout?.unref?.();
    }
    const accept = () => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      container.__hmbSeedanceLatestProps = optimisticProps;
      delete container.__hmbSeedanceShotChangeError;
      delete container.__hmbSeedanceModeSelectionError;
      delete container.__hmbSeedanceUnconfirmedSelection;
      refresh(container, optimisticProps);
    };
    const rollback = (error) => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      hmbSeedanceClearShotSelection(container, true);
      container.__hmbSeedanceLatestProps = previousProps;
      container.__hmbSeedanceShotChangeError = String(
        error?.message || error || "Shot selection publication failed",
      );
      refresh(container, previousProps);
    };
    accept();
    let result;
    try { result = liveProps.onChange(next); } catch (error) { rollback(error); return; }
    if (result && typeof result.then === "function") Promise.resolve(result).catch(rollback);
  };
  container.__hmbSeedanceFlushShotQueue = () => {
    const queued = container.__hmbSeedanceQueuedShot;
    if (!queued || container.__hmbSeedancePendingShot) return;
    delete container.__hmbSeedanceQueuedShot;
    const state = hmbSeedanceShotState(container.__hmbSeedanceLatestProps || {});
    if (hmbSeedanceShotKey(state) === queued.key) return;
    const target = hmbSeedanceShotOptions(state).find((option) => !option.waiting && option.key === queued.key);
    if (!target) {
      container.__hmbSeedanceModeSelectionError = "선택한 샷을 사용할 수 없습니다. 다시 선택하세요.";
      hmbSeedanceSetStatus(container, container.__hmbSeedanceModeSelectionError);
      return;
    }
    if (select) select.value = target.key;
    onShotChange();
  };
  select?.addEventListener?.("change", onShotChange);
  const guardDelete = (event) => { if (!hmbNativeHeaderTarget(event.target)) hmbGuardSelectedNodeKeyboardDelete(container, event); };
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", guardDelete, true);
  }
  const stopInteriorDelete = (event) => {
    if (hmbNativeHeaderTarget(event.target)) return;
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorSelection = (event) => {
    if (hmbNativeHeaderTarget(event.target)) return;
    if (nativeHeader.active && !event.target?.closest?.("button,input,select,textarea")) return;
    if (Number(event?.button) !== 1) event.stopPropagation?.();
  };
  container.addEventListener?.("keydown", stopInteriorDelete);
  container.addEventListener?.("pointerdown", stopInteriorSelection);
  const cleanup = () => {
    nativeHeader.cleanup();
    hmbSeedanceCleanupRemotePromptEdge(container);
    hmbSeedanceCleanupPreviewOverlay(container);
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", guardDelete, true);
    }
    container.removeEventListener?.("keydown", stopInteriorDelete);
    container.removeEventListener?.("pointerdown", stopInteriorSelection);
    select?.removeEventListener?.("change", onShotChange);
    finalButton?.removeEventListener?.("click", onFinalize);
    if (container.__hmbSeedanceCleanup === cleanup) delete container.__hmbSeedanceCleanup;
    delete container.__hmbSeedanceLatestProps;
    delete container.__hmbSeedanceShotChangeError;
    hmbSeedanceClearShotSelection(container, true);
    delete container.__hmbSeedanceFlushShotQueue;
    delete container.__hmbSeedanceModeSelectionError;
    delete container.__hmbSeedanceUnconfirmedSelection;
    delete container.__hmbSeedanceModeBaseline;
    delete container.__hmbSeedanceRetiredModeInstances;
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
      if (container.__hmbSeedanceCleanup !== cleanup) return;
      const incoming = nextProps || container.__hmbSeedanceLatestProps || {};
      const next = hmbSeedanceResolveShotEcho(container, incoming);
      if (!next.stale) hmbSeedanceNextChangeOwner(container);
      container.__hmbSeedanceLatestProps = next.props;
      if (!refresh(container, next.props)) {
        HMBSeedanceGenerationWidget(container, next.props);
      }
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
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "seedance", allowControl: (target, props) => {
    const el = target?.closest?.("button,input,select,textarea") || target;
    const state = hmbSeedanceShotState(props);
    return hmbNativeHeaderTarget(target) || Boolean(el?.matches?.("[data-hmb-seedance-preview-action]") && state.generation.action === "refresh_existing")
      || Boolean(el?.matches?.("[data-hmb-seedance-finalize-draft]") && state.draft.cancel_available)
      || Boolean(el?.matches?.("[data-preflight-open],[data-preflight-recheck],[data-preflight-cancel],[data-preflight-close]"));
  } });
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

export default function HMBSeedanceGenerationWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
