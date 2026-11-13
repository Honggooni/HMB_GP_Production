const shotColors = ["#f18bbd", "#8bb6ff", "#75e0bc", "#bf9bf9", "#edca81"];
const kindLabels = {image: "이미지", video: "동영상", audio: "오디오"};
const categoryLabels = {
  camera: "카메라", motion: "동작", cut_timing: "컷 타이밍",
  effect_shape: "이펙트 형태", effect_timing: "이펙트 타이밍",
  composition: "구도·프레이밍", lighting_reference: "라이팅 참고", color_look: "컬러 룩",
  character_pose: "캐릭터 포즈", appearance: "캐릭터·소품 외형",
  audio_content: "대사·발음", audio_delivery: "말투·감정", audio_rhythm: "리듬·강약",
  audio_effects: "효과음·환경음", audio_timing: "시작·종료 타이밍",
};
const promptFields = Object.freeze({
  PROJECT_STYLE_LOOK: ["시각 방향", "프로젝트 / 시퀀스 시각 방향"],
  SCENE_CONTEXT: ["장면 사실", "샷 장면 / 서사 사실"],
  EMOTION_INTENT: ["연기·감정", "대상 연기 / 감정"],
  PRESERVED_TEXT: ["정확 문자열", "정확히 보존할 문자열"],
  VIDEO_VFX: ["VFX", "영상 작업 / 립싱크 / VFX"],
});
const firstPromptField = Object.keys(promptFields)[0];

const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
}[char]));
const dict = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const list = value => Array.isArray(value) ? value : [];
const disabled = value => value ? " disabled" : "";
const checked = value => value ? " checked" : "";
const finiteSeconds = value => value === "" || value == null ? null :
  Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null;
const MAX_ANALYSIS_RANGES = 8;

function intervalSpec(kind, source) {
  if (kind === "video") {
    const count = Number(source.frame_count);
    return Number.isSafeInteger(count) && count > 0
      ? {kind, min: 0, max: count - 1, unit: "프레임"}
      : null;
  }
  if (kind !== "audio") return null;
  const min = finiteSeconds(source.start_seconds) ?? 0;
  const end = finiteSeconds(source.end_seconds);
  const duration = finiteSeconds(source.duration_seconds);
  const max = end !== null && end > min ? end : duration !== null && duration > min ? duration : null;
  return max !== null ? {kind, min, max, unit: "초"} : null;
}

function normalizeIntervals(rows, spec) {
  if (!spec) return [];
  const value = number => spec.kind === "video" ? Math.round(number) : Math.round(number * 1000) / 1000;
  const valid = list(rows).flatMap(row => {
    if (!row || !Number.isFinite(Number(row.start)) || !Number.isFinite(Number(row.end))) return [];
    const start = value(Math.max(spec.min, Math.min(spec.max, Number(row.start))));
    const end = value(Math.max(spec.min, Math.min(spec.max, Number(row.end))));
    return end >= start && (spec.kind === "video" || end > start) ? [{start, end}] : [];
  }).sort((a, b) => a.start - b.start || a.end - b.end);
  const merged = [];
  for (const row of valid) {
    const previous = merged.at(-1);
    if (previous && row.start <= previous.end + (spec.kind === "video" ? 1 : 0)) previous.end = Math.max(previous.end, row.end);
    else merged.push({...row});
  }
  return merged.slice(0, MAX_ANALYSIS_RANGES);
}

function intervalTotal(rows, kind) {
  return rows.reduce((total, row) => total + row.end - row.start + (kind === "video" ? 1 : 0), 0);
}

function intervalMessage(rows, kind) {
  const total = intervalTotal(rows, kind);
  const quantity = kind === "video" ? `총 ${total}프레임` : `총 ${Math.round(total * 100) / 100}초 / 최대 30초`;
  return quantity;
}

function analysisIntervalMessage(rows, kind, videoRangesEnabled) {
  return kind === "video" && (!videoRangesEnabled || !rows.length)
    ? "전체 영상 분석"
    : intervalMessage(rows, kind);
}

function canAnalyze(state, locked, pending, spec, intervals) {
  if (locked || pending || state.busy || state.running || !state.source?.source_id ||
      !state.shot_uuid ||
      !list(state.shots).some(shot => shot?.shot_uuid === state.shot_uuid)) return false;
  return state.slot?.kind !== "audio" || Boolean(spec && intervals.length && intervalTotal(intervals, "audio") <= 30);
}

function read(props) {
  let value = props?.value ?? props?.parameterValue ?? props?.data ?? props;
  if (typeof value === "string") {
    try { value = JSON.parse(value); } catch { value = {}; }
  }
  return dict(value);
}

function previewURL(value) {
  if (typeof value !== "string" || /[\u0000-\u001f\u007f]/.test(value)) return "";
  if (/^\/(?![\\/])/.test(value)) return value;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) &&
      !url.username && !url.password ? url.href : "";
  } catch {
    return "";
  }
}

function renderPreview(source, slot) {
  const url = source.source_id ? escape([
    slot.preview_url, source.preview_url, dict(slot.preview).url, slot.preview,
  ].map(previewURL).find(Boolean) || "") : "";
  const label = escape(source.name || "선택한 미디어");
  const kind = source.kind || slot.kind;
  const fallback = `<span data-preview-fallback>${label} · 미리보기를 열 수 없습니다.</span>`;
  if (url && kind === "image") return `<img src="${url}" alt="${label}">${fallback}`;
  if (url && kind === "video") return `<video src="${url}" controls preload="metadata" aria-label="${label}"></video>${fallback}`;
  if (url && kind === "audio") return `<audio src="${url}" controls preload="none" aria-label="${label}"></audio>${fallback}`;
  return `<span>${source.name ? label : "Prompt 또는 직접 선택한 파일의 미리보기"}</span>`;
}

const style = `
  .hmb-analysis {
    --line: #41485f; --muted: #aab8d1;
    color: #e8edf8; background: #101724; border: 1px solid #505773;
    border-radius: 10px; overflow: hidden; font: 12px/1.5 "Segoe UI", sans-serif;
    display: flex; flex-direction: column; height: 100%; min-height: 0; container-type: inline-size;
  }
  .hmb-analysis *, .hmb-analysis { box-sizing: border-box; }
  .hmb-analysis :is(button, input, select, textarea):not([data-hmb-native-identity] *,[data-hmb-native-actions] *) {
    color: inherit; font: inherit; min-width: 0; border-radius: 5px;
    border: 1px solid var(--line); background: #131b2c; padding: 4px 7px;
  }
  .hmb-analysis button { cursor: pointer; }
  .hmb-analysis button:disabled { opacity: .5; cursor: default; }
  .hmb-analysis :is(button, input, select, textarea):focus-visible { outline: 2px solid #c497ec; outline-offset: 1px; }
  .hmb-analysis [data-primary] { background: #53376a; border-color: #8b65a6; font-weight: 700; }
  .hmb-analysis .ha-header {
    display: flex; gap: 8px; align-items: center; padding: 8px 10px;
    background: linear-gradient(105deg, #442e55, #211e33 58%, #171e2d);
    border-bottom: 1px solid #584767; flex-shrink: 0;
  }
  .hmb-analysis .ha-mark {
    display: grid; place-items: center; width: 22px; height: 22px; border-radius: 5px;
    color: #eed0ff; border: 1px solid #8d72a1;
  }
  .hmb-analysis .ha-header > b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .hmb-analysis .ha-role { margin-inline: auto 14px; display: flex; flex: 0 0 auto; gap: 4px; padding: 2px; border: 1px solid #4b4b65; border-radius: 7px; background: #1b2030; }
  .hmb-analysis .ha-role button { width: 76px; padding: 2px 5px; white-space: nowrap; color: var(--role-ink); background: #131b2c; border-color: var(--role-line); }
  .hmb-analysis .ha-role [data-role=before] { --role-ink: #ffc7e5; --role-line: #9c5d85; --role-on: #633655; }
  .hmb-analysis .ha-role [data-role=after] { --role-ink: #b3f1ee; --role-line: #3d8c94; --role-on: #214d58; }
  .hmb-analysis .ha-role [aria-pressed=true] { background: var(--role-on); box-shadow: inset 0 0 0 1px var(--role-line); }
  .hmb-analysis .ha-role-conflict { margin: 6px 8px 0; color: #fda7bd; }
  .hmb-analysis .ha-tabs { padding: 7px 8px 0; display: flex; gap: 5px; }
  .hmb-analysis .ha-tabs button {
    flex: 1 1 0; text-align: left; color: var(--shot); font-weight: 700; overflow: hidden;
    white-space: nowrap; text-overflow: ellipsis; min-height: 29px;
    background: linear-gradient(108deg, color-mix(in srgb, var(--shot) 15%, #171a2b), #161d2d);
    border-color: color-mix(in srgb, var(--shot) 42%, #252a38);
  }
  .hmb-analysis .ha-tabs [aria-selected=true] {
    border-color: var(--shot); background: color-mix(in srgb, var(--shot) 25%, #202036);
  }
  .hmb-analysis .ha-content { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; overflow: auto; padding: 8px; }
  .hmb-analysis .ha-panel {
    display: flex; flex-direction: column; flex: 1 0 auto; gap: 7px; min-height: 100%; padding: 8px; border: 1px solid #424861;
    border-radius: 7px; background: #152031;
  }
  .hmb-analysis .ha-workspace { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .hmb-analysis .ha-workspace > * { min-width: 0; }
  .hmb-analysis .ha-guidance { position: relative; width: 100%; aspect-ratio: 16 / 9; }
  .hmb-analysis .ha-guidance textarea { position: absolute; inset: 0; height: 100%; min-height: 0; resize: none; overflow: auto; }
  @container (max-width: 560px) {
    .hmb-analysis .ha-workspace { grid-template-columns: minmax(0, 1fr); }
    .hmb-analysis .ha-guidance { aspect-ratio: 32 / 9; min-height: 82px; }
    .hmb-analysis .ha-header { gap: 4px; padding-inline: 6px; }
    .hmb-analysis .ha-role { margin-inline-end: 3px; }
    .hmb-analysis .ha-role button { width: 64px; }
  }
  .hmb-analysis .ha-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .hmb-analysis .ha-source-heading { justify-content: space-between; }
  .hmb-analysis .ha-source-heading button { margin-inline-start: auto; }
  .hmb-analysis .ha-source-row {
    display: grid; grid-template-columns: minmax(0, 22%) minmax(0, 1fr) minmax(82px, 13%);
    gap: 7px; align-items: stretch; width: 100%;
  }
  .hmb-analysis .ha-source-row select { width: 100%; text-overflow: ellipsis; }
  .hmb-analysis .ha-source-row [data-action=clear] { width: 100%; white-space: nowrap; }
  @container (max-width: 420px) {
    .hmb-analysis .ha-source-row { grid-template-columns: minmax(66px, 24%) minmax(0, 1fr) 76px; gap: 4px; }
  }
  .hmb-analysis .ha-subtle { color: var(--muted); }
  .hmb-analysis .ha-preview {
    display: grid; place-items: center; width: 100%; aspect-ratio: 16 / 9; align-self: start; min-height: 0;
    border: 1px solid #3d4860; background: #0b1322; border-radius: 6px;
    color: var(--muted); overflow: hidden; text-align: center;
  }
  .hmb-analysis .ha-preview :is(img, video) { width: 100%; height: 100%; min-width: 0; min-height: 0; object-fit: contain; }
  .hmb-analysis .ha-preview audio { width: min(100%, 350px); }
  .hmb-analysis .ha-preview [data-preview-fallback],
  .hmb-analysis .ha-preview[data-preview-failed] :is(img, video, audio) { display: none; }
  .hmb-analysis .ha-preview[data-preview-failed] [data-preview-fallback] { display: block; }
  .hmb-analysis .ha-tabs[hidden] { display: none; }
  .hmb-analysis .ha-range { display: grid; grid-template-columns: 79px minmax(0,1fr) 79px; gap: 6px; }
  .hmb-analysis .ha-range label { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .hmb-analysis .ha-range input { width: 100%; font-variant-numeric: tabular-nums; }
  .hmb-analysis .ha-range .ha-subtle { grid-column: 1 / -1; }
  .hmb-analysis .ha-range-track { position: relative; align-self: end; height: 28px; min-width: 0; border: 1px solid #527c85;
    border-radius: 6px; background: #091421; cursor: crosshair; touch-action: none; user-select: none; overflow: hidden; }
  .hmb-analysis .ha-range-track:focus-visible { outline: 2px solid #22d3ee; }
  .hmb-analysis .ha-range-track[aria-disabled=true] { opacity: .5; cursor: default; }
  .hmb-analysis .ha-range-grid { position: absolute; inset: 0; pointer-events: none;
    background: repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), rgba(148,163,184,.13) calc(10% - 1px), rgba(148,163,184,.13) 10%); }
  .hmb-analysis .ha-range-bar { position: absolute; top: 3px; height: 20px; min-width: 2px; border: 1px solid #22d3ee;
    border-radius: 5px; background: rgba(8,145,178,.7); cursor: grab; }
  .hmb-analysis .ha-range-bar b { display: block; overflow: hidden; text-align: center; white-space: nowrap; font-size: 9px; line-height: 18px; pointer-events: none; }
  .hmb-analysis .ha-range-handle { position: absolute; top: -1px; bottom: -1px; width: 9px; background: rgba(255,255,255,.5); cursor: ew-resize; }
  .hmb-analysis .ha-range-handle[data-range-handle=start] { left: -1px; border-radius: 4px 0 0 4px; }
  .hmb-analysis .ha-range-handle[data-range-handle=end] { right: -1px; border-radius: 0 4px 4px 0; }
  .hmb-analysis .ha-intervals { display: grid; gap: 5px; }
  .hmb-analysis .ha-interval-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .hmb-analysis .ha-interval-header b { font-size: 11px; }
  .hmb-analysis .ha-interval-header button { margin-left: auto; }
  .hmb-analysis .ha-interval-header .ha-range-toggle { display: inline-flex; align-items: center; gap: 8px; margin-left: 0; }
  .hmb-analysis .ha-range-toggle em { font-style: normal; font-size: 10px; font-weight: 700; color: #aab8d1; }
  .hmb-analysis .ha-range-toggle[aria-expanded=true] { background: #214657; border-color: #4e9dad; }
  .hmb-analysis .ha-range-toggle[aria-expanded=true] em { color: #a7f3f5; }
  .hmb-analysis .ha-interval-track { position: relative; height: 32px; border: 1px solid #527c85; border-radius: 6px;
    background: #091421; cursor: crosshair; touch-action: none; user-select: none; overflow: hidden; }
  .hmb-analysis .ha-interval-track[aria-disabled=true] { cursor: default; opacity: .55; }
  .hmb-analysis .ha-interval-track:focus-visible { outline: 2px solid #22d3ee; }
  .hmb-analysis .ha-interval-placeholder { display: grid; place-items: center; min-height: 32px; border: 1px solid #364b61;
    border-radius: 6px; color: var(--muted); background: #101927; font-size: 11px; }
  .hmb-analysis .ha-interval-bar { position: absolute; top: 4px; height: 23px; min-width: 3px; border: 1px solid #22d3ee;
    border-radius: 5px; background: rgba(8,145,178,.7); cursor: grab; }
  .hmb-analysis .ha-interval-bar.selected { border-color: #f8fafc; box-shadow: 0 0 0 1px #22d3ee; }
  .hmb-analysis .ha-interval-bar b { display: block; overflow: hidden; text-align: center; white-space: nowrap; font-size: 9px; line-height: 21px; pointer-events: none; }
  .hmb-analysis .ha-interval-handle { position: absolute; top: -1px; bottom: -1px; width: 9px; background: rgba(255,255,255,.5); cursor: ew-resize; }
  .hmb-analysis .ha-interval-handle[data-interval-handle=start] { left: -1px; border-radius: 4px 0 0 4px; }
  .hmb-analysis .ha-interval-handle[data-interval-handle=end] { right: -1px; border-radius: 0 4px 4px 0; }
  .hmb-analysis .ha-interval-message { color: #aab8d1; font-size: 10px; }
  .hmb-analysis .ha-interval-message[data-error=true] { color: #fda7bd; }
  .hmb-analysis textarea { display: block; width: 100%; resize: vertical; min-height: 40px; }
  .hmb-analysis fieldset { margin: 0; min-inline-size: 0; min-height: 180px; flex: 1 1 auto; display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 6px; padding: 4px 7px 7px; }
  .hmb-analysis legend { color: #d3c3e8; padding: 0 4px; }
  .hmb-analysis input[type=checkbox] { accent-color: #bd8edd; }
  .hmb-analysis .ha-choice { display: inline-flex; align-items: center; gap: 3px; }
  .hmb-analysis .ha-model-route { column-gap: 14px; }
  .hmb-analysis .ha-model-route [data-model] { max-width: 172px; }
  .hmb-analysis .ha-delivery { display: flex; flex-wrap: wrap; gap: 4px 11px; }
  .hmb-analysis .ha-delivery .ha-choice { white-space: nowrap; }
  .hmb-analysis .ha-results-toggle-wrap { position: relative; display: inline-flex; align-items: center; min-width: 178px; cursor: pointer; }
  .hmb-analysis .ha-results-toggle-wrap input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; z-index: 2; cursor: pointer; }
  .hmb-analysis .ha-results-toggle-ui { display: inline-flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; min-height: 27px;
    padding: 3px 7px; border: 1px solid #456079; border-radius: 6px; background: #091421; color: #b9c8da; font-size: 10px; }
  .hmb-analysis .ha-results-toggle-ui em { font-style: normal; font-weight: 800; color: #7c91a8; }
  .hmb-analysis .ha-results-toggle-wrap input:checked + .ha-results-toggle-ui { border-color: #22d3ee; color: #dcfaff; background: rgba(8,145,178,.22); }
  .hmb-analysis .ha-results-toggle-wrap input:checked + .ha-results-toggle-ui em { color: #67e8f9; }
  .hmb-analysis .ha-results-toggle-wrap input:focus-visible + .ha-results-toggle-ui { outline: 2px solid #c497ec; outline-offset: 1px; }
  .hmb-analysis .ha-results-toggle-wrap input:disabled + .ha-results-toggle-ui { opacity: .5; }
  .hmb-analysis :is(.ha-field-tabs, .ha-categories) { display: grid; grid-template-columns: repeat(5, minmax(74px, 1fr));
    width: 100%; max-width: 520px; gap: 4px; overflow-x: auto; padding: 2px 1px 4px; }
  .hmb-analysis .ha-categories .ha-choice { position: relative; justify-content: center; min-height: 28px; padding: 3px;
    border: 1px solid var(--line); border-radius: 5px; background: #131b2c; white-space: nowrap; }
  .hmb-analysis .ha-categories .ha-choice:has(input:checked) { background: #214657; border-color: #59aab7; color: #dcfaff; }
  .hmb-analysis .ha-categories .ha-choice:has(input:disabled) { opacity: .55; }
  .hmb-analysis .ha-categories .ha-choice:focus-within { outline: 2px solid #c497ec; outline-offset: -2px; }
  .hmb-analysis .ha-categories .ha-choice input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; }
  .hmb-analysis .ha-categories .ha-choice input:disabled { cursor: default; }
  .hmb-analysis .ha-categories .ha-subtle { grid-column: 1 / -1; }
  .hmb-analysis .ha-result { max-height: 136px; overflow: auto; color: #c5d4ec; padding: 0 3px; }
  .hmb-analysis .ha-result p { margin: 3px 0; overflow-wrap: anywhere; }
  .hmb-analysis .ha-result small { color: #a9c8e7; }
  .hmb-analysis .ha-result-text { flex: 1 1 auto; min-height: 104px; height: 100%; max-height: none; resize: vertical; white-space: pre-wrap; }
  .hmb-analysis .ha-result-help { display: block; margin: 4px 0; color: var(--muted); }
  .hmb-analysis .ha-field-tabs { margin: 3px 0 6px; }
  .hmb-analysis .ha-field-tabs button { min-height: 28px; white-space: nowrap; }
  .hmb-analysis .ha-field-tabs [aria-selected=true] { background: #53376a; border-color: #a581bb; color: #f4dbff; }
  .hmb-analysis .ha-field-editor { display: flex; flex: 1 1 auto; flex-direction: column; gap: 5px; }
  .hmb-analysis .ha-field-editor textarea { flex: 1 1 auto; min-height: 104px; }
  .hmb-analysis .ha-bottom { display: flex; justify-content: flex-end; align-items: center; gap: 6px; flex-wrap: wrap; }
  .hmb-analysis .ha-bottom button[data-action=analyze][data-primary] { min-height: 42px; padding: 6px 11px; font-size: 18px; }
  .hmb-analysis .ha-status { margin-right: auto; color: #9ae2c7; overflow-wrap: anywhere; }
  .hmb-analysis .ha-status[data-error=true] { color: #fda7bd; }
  .hmb-analysis [data-hmb-native-identity], .hmb-analysis [data-hmb-native-actions] { display: none; }
  .hmb-analysis[data-hmb-native-header=active] [data-hmb-native-identity],
  .hmb-analysis[data-hmb-native-header=active] [data-hmb-native-actions] { display: flex; align-items: center; }
  .hmb-analysis[data-hmb-native-header=active] [data-hmb-native-identity] { flex: 1 1 auto; min-width: 0; }
  .hmb-analysis[data-hmb-native-header=active] [data-hmb-native-actions] { flex: 0 0 auto; }
  .hmb-analysis[data-hmb-native-header=active] .ha-brand { display: none; }
`;

function render(state, view, locked, pending, notice) {
  const shots = list(state.shots).filter(shot => shot?.shot_uuid && Number.isInteger(shot.number) &&
    shot.number >= 1 && shot.number <= shotColors.length);
  const active = shots.find(shot => shot.shot_uuid === state.shot_uuid);
  const slot = dict(state.slot);
  const deliveryDraft = view.deliveryDraft?.shot_uuid === state.shot_uuid ? view.deliveryDraft : null;
  const source = dict(state.source);
  const intervalDraft = view.intervalDraft?.shot_uuid === state.shot_uuid &&
    view.intervalDraft.source_id === (slot.source_id || "") ? view.intervalDraft : null;
  const result = dict(slot.result);
  const observations = dict(result.observations);
  const usable = Boolean(source.source_id);
  const kind = slot.kind || view.kind;
  const busy = state.busy === true;
  const role = state.role === "before" ? "before" : "after";
  const availableRoles = Array.isArray(state.available_roles) ? state.available_roles : ["before", "after"];
  const editDisabled = locked || pending || busy || !active;
  const sourceLabel = role === "before" ? "샷 참고 소스" : "Prompt 참고 소스";
  const sourceCount = list(state.sources).length;
  const roles = [["before", "To Prompt"], ["after", "To Agent"]].map(([key, label]) => {
    const available = availableRoles.includes(key);
    return `<button type="button" data-role="${key}" aria-pressed="${role === key}"${disabled(locked || pending || busy || state.running === true || !available)}${available ? "" : ' title="이 위치에 연결된 Analysis Agent가 있습니다."'}>${label}</button>`;
  }).join("");
  const tabs = shots.map(shot => {
    const name = shot.name || `샷 ${shot.number}`;
    const status = shot.busy ? " · 분석 중" : shot.applied ? " · 적용" : "";
    return `<button type="button" role="tab" aria-selected="${shot === active}" data-shot="${escape(shot.shot_uuid)}"
      style="--shot:${shotColors[shot.number - 1]}" title="${escape(name + status)}"${disabled(locked || pending)}>${String(shot.number).padStart(2, "0")} ${escape(name + status)}</button>`;
  }).join("");
  const kinds = Object.entries(kindLabels).map(([key, label]) =>
    `<option value="${key}"${view.kind === key ? " selected" : ""}>${label}</option>`).join("");
  const choices = list(state.sources).filter(row => row.kind === view.kind).map(row => {
    const selected = slot.origin === "prompt" && slot.source_id === row.source_id;
    return `<option value="${escape(row.source_id)}"${selected ? " selected" : ""}>${escape(row.name)}</option>`;
  }).join("");
  const argonSelected = slot.model === "gemini-4-argon";
  const carbonSelected = slot.model === "gemini-4-carbon";
  const spec = intervalSpec(kind, source);
  const intervals = normalizeIntervals(intervalDraft ? intervalDraft.ranges :
    kind === "video" ? slot.frame_ranges : slot.time_ranges, spec);
  const timedSource = kind === "video" || kind === "audio";
  const rangeExpanded = kind === "video" ? view.videoRangesEnabled : kind === "audio" ? !view.audioRangesCollapsed : true;
  const rangeLabel = kind === "audio" ? "분석 오디오 구간" : "분석 프레임 구간";
  const selectedInterval = Math.max(0, Math.min(intervals.length - 1, view.selectedInterval || 0));
  const overLimit = kind === "audio" && intervalTotal(intervals, kind) > 30;
  const span = spec ? Math.max(spec.kind === "video" ? 1 : .001, spec.max - spec.min + (spec.kind === "video" ? 1 : 0)) : 1;
  const bars = intervals.map((row, index) => {
    const left = (row.start - spec.min) / span * 100;
    const width = (row.end - row.start + (spec.kind === "video" ? 1 : 0)) / span * 100;
    const label = `${row.start}–${row.end}${spec.unit}`;
    return `<span class="ha-interval-bar${index === selectedInterval ? " selected" : ""}" data-interval-index="${index}" style="left:${left}%;width:${width}%" title="${label}"><i class="ha-interval-handle" data-interval-handle="start"></i><b>${label}</b><i class="ha-interval-handle" data-interval-handle="end"></i></span>`;
  }).join("");
  const range = `<div class="ha-intervals">
    <div class="ha-interval-header">
      <button type="button" class="ha-range-toggle" data-action="toggle-range" aria-expanded="${timedSource && rangeExpanded}"
        title="${kind === "video" ? "OFF에서 전체 영상 분석 · 선택한 구간 유지" : "구간 편집 열기 또는 닫기 · 선택한 구간 유지"}"${disabled(!timedSource)}><b>${rangeLabel}</b><em>${timedSource && rangeExpanded ? "ON" : "OFF"}</em></button>
      ${timedSource ? `<span class="ha-subtle" data-interval-count>${intervals.length}/${MAX_ANALYSIS_RANGES} 구간</span>
      <span class="ha-interval-message" data-interval-message data-error="${overLimit}">${analysisIntervalMessage(intervals, kind, view.videoRangesEnabled)}</span>` : ""}
      <button type="button" data-action="remove-interval"${disabled(editDisabled || !rangeExpanded || !intervals.length)}>선택 구간 삭제</button>
    </div>
    <div data-ha-key="range-track-area"${rangeExpanded ? "" : " hidden"}>
      ${spec ? `<div class="ha-interval-track" data-interval-track data-interval-min="${spec.min}" data-interval-max="${spec.max}" data-interval-kind="${kind}" role="slider" tabindex="${editDisabled || !usable ? -1 : 0}" aria-label="${rangeLabel} 편집" aria-valuemin="${spec.min}" aria-valuemax="${spec.max}" aria-valuenow="${intervals[selectedInterval]?.start ?? spec.min}" aria-valuetext="${intervals.length ? `${intervals.length}개 분리 구간` : "선택 구간 없음"}" aria-disabled="${editDisabled || !usable}"><span class="ha-range-grid"></span>${bars}</div>`
        : `<div class="ha-interval-placeholder">${kind === "audio" ? "오디오 길이를 확인 중입니다." : kind === "video" && usable ? "영상 프레임 수를 확인 중입니다." : "동영상 소스를 선택하면 프레임 구간을 설정할 수 있습니다."}</div>`}
    </div>
  </div>`;
  const reviewCategories = list(state.categories).slice(0, 5);
  const chosenCategories = deliveryDraft ? list(deliveryDraft.categories) : list(slot.categories);
  const hasResults = reviewCategories.some(key => list(observations[key]).length > 0);
  const categories = reviewCategories.map(key => {
    const available = list(observations[key]).length > 0;
    return `<label class="ha-choice"${!available && hasResults ? ' title="이 항목의 분석 결과가 없습니다."' : ""}><input type="checkbox" data-category="${escape(key)}"
      ${checked(chosenCategories.includes(key))}${disabled(editDisabled || !available)}>${escape(categoryLabels[key] || key)}</label>`;
  }).join("");
  const details = reviewCategories.flatMap(key => list(observations[key]).map(row =>
    `<p><b>${escape(categoryLabels[key] || key)}</b> ${row.start != null ? `<small>${escape(row.start)}초${row.end != null ? `–${escape(row.end)}초` : ""}</small> ` : ""}
      ${escape(row.observation)}${row.interpretation ? ` <small>· 해석 ${escape(row.interpretation)}</small>` : ""}</p>`)).join("");
  const resultsOnly = deliveryDraft ? deliveryDraft.results_only : slot.results_only === true;
  const resultText = view.resultTextDraft?.shot_uuid === state.shot_uuid
    ? view.resultTextDraft.value : String(state.result_text ?? "");
  const field = view.promptField;
  const fieldText = view.fieldDraft?.shot_uuid === state.shot_uuid && view.fieldDraft.field === field
    ? view.fieldDraft.value : String(dict(slot.fields)[field] ?? "");
  const fieldTabs = Object.entries(promptFields).map(([key, [label, title]]) =>
    `<button type="button" role="tab" aria-selected="${key === field}" data-field-tab="${key}" title="${title}"${disabled(locked || pending)}>${label}</button>`).join("");
  const categoryGroup = `<div class="ha-categories"${categories ? ' role="group" tabindex="0" aria-label="분석 항목 5개"' : ""}>${categories || '<span class="ha-subtle">소스를 선택하면 항목이 표시됩니다.</span>'}</div>`;
  const review = role === "before" ? `<fieldset class="ha-review" data-ha-key="review"><legend>Prompt 입력 미리보기</legend>
    <div class="ha-field-tabs" role="tablist" aria-label="Prompt 입력 항목">${fieldTabs}</div>
    <label class="ha-field-editor" role="tabpanel"><b>${promptFields[field][1]}</b>
      <textarea data-field-text="${field}" maxlength="${field === "VIDEO_VFX" ? 20000 : 6000}" aria-label="${promptFields[field][1]}" placeholder="분석이 완료되면 입력 문구가 표시됩니다."${disabled(editDisabled || !details)}>
${escape(fieldText)}</textarea></label>
    <small class="ha-result-help">선택된 샷의 Prompt에 반영됩니다. 정확한 문자열은 확인된 원문만 입력하세요.</small>
    ${categoryGroup}</fieldset>` : `<fieldset class="ha-review" data-ha-key="review"><legend>이 샷에 가져올 결과</legend>${categoryGroup}
    ${usable && !details ? '<div class="ha-subtle" data-analysis-result-hint>분석이 완료되면 결과가 있는 항목을 선택할 수 있습니다.</div>' : ""}
    <small class="ha-result-help">선택 항목이 없으면 분석 결과 전체를 사용합니다. 아래 내용을 수정하면 해당 샷에 저장됩니다. 내용을 비우면 자동 생성 문구로 복원됩니다.</small>
    <textarea class="ha-result-text" data-result-text maxlength="26000" aria-label="분석 결과 편집" placeholder="분석이 완료되면 결과가 표시됩니다."${disabled(editDisabled || !details)}>${escape(resultText)}</textarea>
  </fieldset>`;
  const actions = `<div class="ha-bottom" data-ha-key="actions"><span class="ha-status" role="status" data-error="${Boolean(notice || state.error)}">${escape(notice || state.status || (result.cache_hit ? "저장 결과 재사용" : ""))}</span>
    ${busy ? `<button type="button" data-action="cancel"${disabled(locked || pending)}>분석 취소</button>` : ""}
    <button type="button" data-action="analyze" data-primary${disabled(!canAnalyze(state, locked, pending, spec, intervals))}>${role === "before" ? "To Prompt 실행" : "To Agent 실행"}</button></div>`;
  return `<style>${style}</style><div class="hmb-analysis nodrag nowheel nopan" data-hmb-analysis-widget data-hmb-color-lut-widget
    data-hmb-node-type="HMBAnalysisAgent" data-hmb-native-node-type="HMBAnalysisAgent"${view.nativeHeader ? ' data-hmb-native-header="active"' : ""}>
    <header class="ha-header group"><span class="ha-mark ha-brand">◈</span><b class="ha-brand">HMB Analysis Agent</b>
      <div data-hmb-native-identity></div><div class="ha-role" role="group" aria-label="Analysis Agent 위치">${roles}</div><div data-hmb-native-actions></div>
    </header>
    <span class="ha-role-conflict" role="status"${state.role_conflict ? "" : " hidden"}>같은 위치에 Analysis Agent가 연결되어 있습니다.</span>
    <div class="ha-tabs" role="tablist" aria-label="분석 샷"${tabs ? "" : " hidden"}>${tabs}</div>
    <div class="ha-content" role="tabpanel"><div class="ha-panel">
      <div class="ha-row ha-source-heading" data-ha-key="source-heading"><b>${escape(active?.name || "Prompt 샷 연결 대기")}</b>
        <span class="ha-subtle">${slot.origin === "direct" ? "직접 선택 파일" : `${sourceLabel} ${sourceCount}개`}</span>
        <button type="button" data-action="refresh" aria-label="샷 및 소스 새로고침" title="샷 및 소스 새로고침"${disabled(locked || pending)}>↻</button></div>
      <div class="ha-source-row" data-ha-key="source-row">
        <select data-kind aria-label="미디어 유형"${disabled(editDisabled)}>${kinds}</select>
        <select data-source aria-label="${sourceLabel}" title="${escape(source.name || "참고 파일 1개 선택")}"${disabled(editDisabled)}><option value="">파일 1개 선택</option>${choices}</select>
        <button type="button" data-action="clear"${disabled(editDisabled || !usable)}>소스 해제</button>
      </div>
      <div class="ha-workspace" data-ha-key="workspace">
        <div class="ha-preview">${renderPreview(source, slot)}</div>
        <div class="ha-guidance"><textarea data-guidance maxlength="500" aria-label="참고 지시 (선택)"${disabled(editDisabled || !usable)}
          placeholder="참고 지시 (선택) · 예시 이펙트의 모양과 시작 시점을 봐 주세요.">${escape(slot.guidance)}</textarea></div>
      </div>
      <div data-ha-key="range">${range}</div>
      <div class="ha-row ha-model-route" data-ha-key="settings">
        <label>분석 모델 <select data-model${disabled(editDisabled || !usable)}><option value="">${escape(state.default_model || "None")}</option><option value="gemini-4-carbon" title="운영 Broker 분석 모델"${carbonSelected ? " selected" : ""}>Gemini 4 Carbon</option><option value="gemini-4-argon" title="운영 Broker 분석 모델"${argonSelected ? " selected" : ""}>Gemini 4 Argon</option></select></label>
        ${role === "after" ? `<div class="ha-delivery" role="group" aria-label="전달 방식">
          <label class="ha-results-toggle-wrap" title="체크하면 분석용 원본을 Agent와 Generator에서 제외합니다."><input type="checkbox" data-results-only aria-label="Agent에 분석 결과만 전달"${checked(resultsOnly)}${disabled(editDisabled)}><span class="ha-results-toggle-ui"><b>Agent에 분석 결과만 전달</b><em>${resultsOnly ? "ON" : "OFF"}</em></span></label>
        </div>` : ""}
      </div>
      ${review}
      ${actions}
    </div></div>
  </div>`;
}

const stableControlKeys = ["data-ha-key", "data-hmb-native-identity", "data-hmb-native-actions",
  "data-shot", "data-role", "data-action", "data-field-tab", "data-field-text",
  "data-category", "data-interval-index", "data-preview-fallback", "value"];

function paintKey(node) {
  if (node.nodeType !== 1) return node.nodeName;
  const name = stableControlKeys.find(key => node.hasAttribute(key));
  return name ? `${node.nodeName}:${name}:${node.getAttribute(name)}` : node.nodeName;
}

function patchPaintNode(current, next, scopeChanged) {
  if (current.nodeType !== 1) {
    if (current.nodeValue !== next.nodeValue) current.nodeValue = next.nodeValue;
    return;
  }
  // The host owns these two live portal destinations.
  if (current.matches("[data-hmb-native-identity],[data-hmb-native-actions]")) return;
  const textarea = current.tagName === "TEXTAREA";
  const select = current.tagName === "SELECT";
  const selectedDefault = select ? [...current.options].find(option => option.defaultSelected)?.value ?? current.options[0]?.value : "";
  const nextSelected = select ? next.value : "";
  if (current.hasAttribute("data-preview-failed")) {
    const media = node => node.querySelector(":is(img,video,audio)");
    const previous = media(current);
    const incoming = media(next);
    if (scopeChanged || previous?.tagName !== incoming?.tagName ||
        previous?.getAttribute("src") !== incoming?.getAttribute("src")) current.removeAttribute("data-preview-failed");
  }
  for (const name of current.getAttributeNames()) {
    if (name === "data-preview-failed" || (textarea && name === "style")) continue;
    if (!next.hasAttribute(name)) current.removeAttribute(name);
  }
  for (const attr of next.attributes) {
    if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
  }
  if (textarea) {
    if (scopeChanged || current.defaultValue !== next.defaultValue) {
      if (current.defaultValue !== next.defaultValue) current.defaultValue = next.defaultValue;
      if (current.value !== next.value) current.value = next.value;
    }
    return;
  }
  if (current.matches('input[type="checkbox"]') && current.checked !== next.checked) current.checked = next.checked;

  const available = new Map();
  for (const child of current.childNodes) {
    const key = paintKey(child);
    if (!available.has(key)) available.set(key, []);
    available.get(key).push(child);
  }
  const pairs = [...next.childNodes].map(child => [available.get(paintKey(child))?.shift(), child]);
  for (const unused of available.values()) for (const child of unused) child.remove();
  let cursor = current.firstChild;
  for (const [existing, candidate] of pairs) {
    const child = existing || candidate;
    if (child !== cursor) current.insertBefore(child, cursor);
    if (existing) patchPaintNode(existing, candidate, scopeChanged);
    cursor = child.nextSibling;
  }
  if (select && (scopeChanged || !current.hasAttribute("data-model") ||
      selectedDefault !== nextSelected) && current.value !== nextSelected) current.value = nextSelected;
}

function hmbNativeStockSafetyImplementation(container, props = {}) {
  if (container.__hmbAnalysisController) {
    container.__hmbAnalysisController.update(props);
    return container.__hmbAnalysisController;
  }
  const doc = container.ownerDocument;
  let state = read(props);
  let latest = props;
  let pending = "";
  let pendingAction = "";
  let pendingRouteOnly = false;
  let displayPage = null;
  let timer;
  let deliveryTimer;
  let queuedNavigation = null;
  let rangeDragCleanup;
  let lastPaintScope = "";
  let lastMediaScope = "";
  const resultHeights = new Map();
  let disposed = false;
  let notice = "";
  const view = {kind: state.slot?.kind || "image", nativeHeader: false,
    deliveryDraft: null, resultTextDraft: null, promptField: firstPromptField, fieldDraft: null,
    intervalDraft: null, selectedInterval: 0, videoRangesEnabled: false, audioRangesCollapsed: false};
  const frame = doc.createElement("div");
  frame.style.cssText = "height:100%;min-height:0";
  container.replaceChildren(frame);

  function paint() {
    if (disposed) return;
    // Canonical state continues to own all commands. A prepared page changes
    // only what is painted while its exact select request is in flight.
    const shown = displayPage || state;
    const scroll = frame.querySelector(".ha-content")?.scrollTop || 0;
    const fieldTabScroll = frame.querySelector(".ha-field-tabs")?.scrollLeft || 0;
    const currentEditor = frame.querySelector("[data-result-text],[data-field-text]");
    const scope = JSON.stringify([shown.channel_uuid, shown.shot_uuid, shown.slot?.source_id,
      shown.role === "before" ? view.promptField : "result"]);
    const mediaScope = JSON.stringify([shown.channel_uuid, shown.shot_uuid, shown.slot?.source_id]);
    if (currentEditor?.style.height && lastPaintScope) resultHeights.set(lastPaintScope, currentEditor.style.height);
    const editingResult = Boolean(currentEditor && doc.activeElement === currentEditor);
    const resultSelection = editingResult ? {
      start: doc.activeElement.selectionStart, end: doc.activeElement.selectionEnd,
    } : null;
    const template = doc.createElement("template");
    template.innerHTML = render(shown, view, latest.disabled === true, Boolean(pending), notice);
    const currentRoot = frame.querySelector(".hmb-analysis");
    const nextRoot = template.content.querySelector(".hmb-analysis");
    if (currentRoot && nextRoot) {
      patchPaintNode(currentRoot, nextRoot, mediaScope !== lastMediaScope);
    } else {
      frame.replaceChildren(template.content);
    }
    const content = frame.querySelector(".ha-content");
    if (content) content.scrollTop = scroll;
    const fieldTabs = frame.querySelector(".ha-field-tabs");
    if (fieldTabs) fieldTabs.scrollLeft = fieldTabScroll;
    const editor = frame.querySelector("[data-result-text],[data-field-text]");
    if (editor && lastPaintScope !== scope) editor.style.height = resultHeights.get(scope) || "";
    if (resultSelection && lastPaintScope === scope &&
        (view.resultTextDraft?.shot_uuid === state.shot_uuid || view.fieldDraft?.shot_uuid === state.shot_uuid)) {
      if (editor && !editor.disabled) {
        editor.focus({preventScroll: true});
        editor.setSelectionRange(resultSelection.start, resultSelection.end);
      }
    }
    lastPaintScope = scope;
    lastMediaScope = mediaScope;
  }

  function routeShape(value) {
    return JSON.stringify({...value, revision: 0, ack: "", status: "", error: "",
      slot: {...dict(value.slot), results_only: false, applied: false},
      shots: list(value.shots).map(shot => ({...shot, applied: false}))});
  }

  function patchRouteOnly() {
    const toggle = frame.querySelector("[data-results-only]");
    if (toggle) {
      toggle.checked = state.slot?.results_only === true;
      toggle.disabled = Boolean(latest.disabled || state.busy || pending || !state.shot_uuid);
    }
    const label = frame.querySelector(".ha-results-toggle-ui em");
    if (label) label.textContent = toggle?.checked ? "ON" : "OFF";
    const run = frame.querySelector("[data-action=analyze]");
    if (run && run.dataset.routePrevDisabled !== undefined) {
      run.disabled = run.dataset.routePrevDisabled === "true" ||
        Boolean(latest.disabled || state.busy || state.running);
      delete run.dataset.routePrevDisabled;
    }
    const status = frame.querySelector(".ha-status");
    if (status) {
      status.textContent = state.status || (state.slot?.result?.cache_hit ? "저장 결과 재사용" : "");
      status.dataset.error = String(Boolean(state.error));
    }
    const tabs = new Map([...frame.querySelectorAll(".ha-tabs [data-shot]")].map(tab => [tab.dataset.shot, tab]));
    for (const shot of list(state.shots)) {
      const tab = tabs.get(shot.shot_uuid);
      if (!tab) continue;
      const suffix = shot.busy ? " · 분석 중" : shot.applied ? " · 적용" : "";
      const name = shot.name || `샷 ${shot.number}`;
      tab.textContent = `${String(shot.number).padStart(2, "0")} ${name}${suffix}`;
      tab.title = `${name}${suffix}`;
    }
  }

  function command(action, fields = {}) {
    if (disposed || pending || latest.disabled || typeof latest.onChange !== "function") return;
    const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const fail = () => {
      if (pending !== id) return;
      pending = "";
      pendingAction = "";
      pendingRouteOnly = false;
      displayPage = null;
      view.kind = state.slot?.kind || "image";
      clearTimeout(timer);
      notice = "요청 확인 응답을 받지 못했습니다. 분석 상태를 새로고침하세요.";
      view.deliveryDraft = null;
      queuedNavigation = null;
      paint();
    };
    pending = id;
    pendingAction = action;
    if(action === "select_shot" && state.shots?.some(row=>row.shot_uuid===fields.shot_uuid)){
      const page = state.display_pages?.[fields.shot_uuid];
      if(page && typeof page === "object"){
        displayPage = {...state, slot:{}, result_text:"", source:{}, sources:[], default_model:null,
          ...page, channel_uuid:state.channel_uuid, shot_uuid:fields.shot_uuid, status:"", error:""};
        view.kind = displayPage.slot?.kind || "image";
        view.intervalDraft = null; view.selectedInterval = 0; view.videoRangesEnabled = false;
      }
    }
    pendingRouteOnly = action === "delivery" && typeof fields.results_only === "boolean" && fields.result_text === undefined &&
      JSON.stringify(fields.categories) === JSON.stringify(list(state.slot?.categories)) &&
      fields.results_only !== (state.slot?.results_only === true);
    notice = "";
    if (pendingRouteOnly) {
      const toggle = frame.querySelector("[data-results-only]");
      if (toggle) toggle.disabled = true;
      const label = frame.querySelector(".ha-results-toggle-ui em");
      if (label) label.textContent = fields.results_only ? "ON" : "OFF";
      const run = frame.querySelector("[data-action=analyze]");
      if (run) {
        run.dataset.routePrevDisabled = String(run.disabled);
        run.disabled = true;
      }
      const status = frame.querySelector(".ha-status");
      if (status) status.textContent = "전달 설정 저장 중…";
    } else paint();
    timer = setTimeout(fail, 12000);
    try {
      Promise.resolve(latest.onChange({__hmb_analysis_command: {id, action,
        channel_uuid: state.channel_uuid, shot_uuid: state.shot_uuid, revision: state.revision, ...fields}})).catch(fail);
    } catch {
      fail();
    }
  }

  function configuration() {
    const value = selector => frame.querySelector(selector)?.value ?? "";
    const kind = state.slot?.kind;
    const spec = intervalSpec(kind, dict(state.source));
    const ranges = currentIntervals(spec);
    const fields = {model: value("[data-model]"), guidance: value("[data-guidance]")};
    if (kind === "video") {
      fields.full_video = !view.videoRangesEnabled || !ranges.length;
      if (spec) fields.frame_ranges = ranges;
    } else if (kind === "audio") {
      fields.time_ranges = ranges;
    }
    return fields;
  }

  function selectedCategories() {
    return [...frame.querySelectorAll("[data-category]:checked")].map(input => input.dataset.category);
  }

  function destinations() {
    if (state.role === "before") return {};
    return {results_only: frame.querySelector("[data-results-only]")?.checked === true};
  }

  function currentIntervals(spec = intervalSpec(state.slot?.kind, dict(state.source))) {
    if (!spec) return [];
    const draft = view.intervalDraft?.shot_uuid === state.shot_uuid &&
      view.intervalDraft.source_id === (state.slot?.source_id || "") ? view.intervalDraft : null;
    return normalizeIntervals(draft ? draft.ranges : spec.kind === "video" ? state.slot?.frame_ranges : state.slot?.time_ranges, spec);
  }

  function paintIntervalTrack(spec, ranges) {
    const track = frame.querySelector("[data-interval-track]");
    if (!track || !spec) return;
    const selected = Math.max(0, Math.min(ranges.length - 1, view.selectedInterval || 0));
    const span = Math.max(spec.kind === "video" ? 1 : .001, spec.max - spec.min + (spec.kind === "video" ? 1 : 0));
    track.querySelectorAll(".ha-interval-bar").forEach(bar => bar.remove());
    for (const [index, row] of ranges.entries()) {
      const bar = doc.createElement("span");
      bar.className = `ha-interval-bar${index === selected ? " selected" : ""}`;
      bar.dataset.intervalIndex = String(index);
      bar.style.left = `${(row.start - spec.min) / span * 100}%`;
      bar.style.width = `${(row.end - row.start + (spec.kind === "video" ? 1 : 0)) / span * 100}%`;
      const label = `${row.start}–${row.end}${spec.unit}`;
      bar.title = label;
      bar.innerHTML = '<i class="ha-interval-handle" data-interval-handle="start"></i><b></b><i class="ha-interval-handle" data-interval-handle="end"></i>';
      bar.querySelector("b").textContent = label;
      track.append(bar);
    }
    track.setAttribute("aria-valuenow", String(ranges[selected]?.start ?? spec.min));
    track.setAttribute("aria-valuetext", ranges.length ? `${ranges.length}개 분리 구간` : "선택 구간 없음");
    const count = frame.querySelector("[data-interval-count]");
    if (count) count.textContent = `${ranges.length}/${MAX_ANALYSIS_RANGES} 구간`;
    const overLimit = spec.kind === "audio" && intervalTotal(ranges, spec.kind) > 30;
    const message = frame.querySelector("[data-interval-message]");
    if (message) {
      message.dataset.error = String(overLimit);
      message.textContent = analysisIntervalMessage(ranges, spec.kind, view.videoRangesEnabled);
    }
    const remove = frame.querySelector("[data-action=remove-interval]");
    if (remove) remove.disabled = !ranges.length || Boolean(pending || latest.disabled || state.busy);
    const run = frame.querySelector("[data-action=analyze]");
    if (run) run.disabled = !canAnalyze(state, latest.disabled, pending, spec, ranges);
  }

  function setIntervals(rows, selected) {
    const spec = intervalSpec(state.slot?.kind, dict(state.source));
    if (!spec) return;
    const ranges = normalizeIntervals(rows, spec);
    view.intervalDraft = {shot_uuid: state.shot_uuid, source_id: state.slot?.source_id || "", ranges};
    view.selectedInterval = Math.max(0, Math.min(ranges.length - 1, selected));
    paintIntervalTrack(spec, ranges);
  }

  function intervalPointerDown(event) {
    const track = event.target.closest?.("[data-interval-track]");
    if (!track || track.getAttribute("aria-disabled") === "true" || (event.button != null && event.button !== 0)) return;
    event.preventDefault();
    event.stopPropagation();
    rangeDragCleanup?.();
    const spec = intervalSpec(state.slot?.kind, dict(state.source));
    if (!spec) return;
    const original = currentIntervals(spec);
    const rect = track.getBoundingClientRect();
    const extent = spec.max - spec.min + (spec.kind === "video" ? 1 : 0);
    const at = pointer => {
      const raw = spec.min + (pointer.clientX - rect.left) / Math.max(1, rect.width) * extent;
      const value = Math.max(spec.min, Math.min(spec.max, raw));
      return spec.kind === "video" ? Math.floor(value) : Math.round(value * 1000) / 1000;
    };
    const bar = event.target.closest?.("[data-interval-index]");
    const index = bar ? Number(bar.dataset.intervalIndex) : -1;
    const handle = event.target.closest?.("[data-interval-handle]")?.dataset.intervalHandle;
    const mode = handle || (bar ? "move" : "create");
    if (mode === "create" && original.length >= MAX_ANALYSIS_RANGES) return;
    const anchor = at(event);
    const anchorX = event.clientX;
    view.selectedInterval = index < 0 ? original.length : index;
    const sample = pointer => {
      const current = at(pointer);
      const next = original.map(row => ({...row}));
      const row = next[index];
      if (mode === "create") {
        const start = Math.min(anchor, current);
        let end = Math.max(anchor, current);
        if (spec.kind === "audio" && end === start) end = Math.min(spec.max, start + .001);
        next.push({start, end});
      } else if (row && mode === "move") {
        const length = row.end - row.start;
        const start = Math.max(spec.min, Math.min(spec.max - length, row.start + current - anchor));
        row.start = start; row.end = start + length;
      } else if (row && mode === "start") {
        row.start = Math.max(spec.min, Math.min(row.end - (spec.kind === "video" ? 0 : .001), current));
      } else if (row && mode === "end") {
        row.end = Math.min(spec.max, Math.max(row.start + (spec.kind === "video" ? 0 : .001), current));
      }
      setIntervals(next, mode === "create" ? next.length - 1 : index);
    };
    const move = pointer => { pointer.preventDefault(); sample(pointer); };
    const finish = pointer => { pointer.preventDefault(); if (mode === "create" || Math.abs(pointer.clientX - anchorX) > 2) sample(pointer); rangeDragCleanup?.(); };
    rangeDragCleanup = () => {
      doc.removeEventListener("pointermove", move, true);
      doc.removeEventListener("pointerup", finish, true);
      doc.removeEventListener("pointercancel", rangeDragCleanup, true);
      rangeDragCleanup = null;
    };
    doc.addEventListener("pointermove", move, true);
    doc.addEventListener("pointerup", finish, true);
    doc.addEventListener("pointercancel", rangeDragCleanup, true);
  }

  function intervalKeydown(event) {
    const track = event.target.closest?.("[data-interval-track]");
    if (!track || track.getAttribute("aria-disabled") === "true") return;
    const spec = intervalSpec(state.slot?.kind, dict(state.source));
    if (!spec) return;
    const rows = currentIntervals(spec);
    const index = Math.max(0, Math.min(rows.length - 1, view.selectedInterval || 0));
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault(); rows.splice(index, 1); setIntervals(rows, Math.max(0, index - 1)); return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (rows.length >= MAX_ANALYSIS_RANGES) return;
      const start = spec.min;
      const end = spec.kind === "video" ? start : Math.min(spec.max, start + .1);
      setIntervals([...rows, {start, end}], rows.length); return;
    }
    if (rows.length && (event.key === "PageDown" || event.key === "PageUp")) {
      event.preventDefault(); view.selectedInterval = (index + (event.key === "PageDown" ? 1 : rows.length - 1)) % rows.length;
      paintIntervalTrack(spec, rows); return;
    }
    if (!rows.length) return;
    const row = {...rows[index]};
    const step = spec.kind === "video" ? (event.shiftKey ? 10 : 1) : (event.shiftKey ? 1 : .1);
    const delta = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
    if (delta) {
      const start = Math.max(spec.min, Math.min(spec.max - (row.end - row.start), row.start + delta));
      row.end += start - row.start; row.start = start;
    } else if (event.key === "Home") { row.end -= row.start - spec.min; row.start = spec.min; }
    else if (event.key === "End") { row.start += spec.max - row.end; row.end = spec.max; }
    else return;
    event.preventDefault(); rows[index] = row; setIntervals(rows, index);
  }

  function deliver(includeText = false) {
    clearTimeout(deliveryTimer);
    const route = destinations();
    const fields = {categories: selectedCategories(), ...route};
    const textChanged = view.resultTextDraft?.shot_uuid === state.shot_uuid &&
      view.resultTextDraft.value !== String(state.result_text ?? "");
    if (includeText || textChanged) {
      fields.result_text = frame.querySelector("[data-result-text]")?.value ?? "";
      fields.result_text_categories = list(view.resultTextDraft?.categories);
    }
    view.deliveryDraft = {shot_uuid: state.shot_uuid, ...fields};
    command("delivery", fields);
  }

  function dirtyPromptField() {
    const draft = view.fieldDraft;
    return state.role === "before" && draft?.shot_uuid === state.shot_uuid &&
      draft.value !== String(dict(state.slot?.fields)[draft.field] ?? "") ? draft : null;
  }

  function savePromptField() {
    clearTimeout(deliveryTimer);
    const draft = dirtyPromptField();
    if (draft) command("set_field", {field: draft.field, text: draft.value});
  }

  function finishNavigation(next) {
    if (next.action === "field_tab") {
      view.promptField = next.fields.field;
      paint();
      frame.querySelector(`[data-field-tab="${view.promptField}"]`)?.focus({preventScroll: true});
    } else {
      command(next.action, next.fields);
    }
  }

  function navigate(action, fields) {
    const next = {action, fields};
    if (dirtyPromptField()) {
      queuedNavigation = next;
      savePromptField();
    } else if (view.resultTextDraft?.shot_uuid === state.shot_uuid &&
        view.resultTextDraft.value !== String(state.result_text ?? "")) {
      queuedNavigation = next;
      deliver(true);
    } else {
      finishNavigation(next);
    }
  }

  function click(event) {
    const button = event.target.closest?.("button");
    if (!button || button.disabled || button.closest("[data-hmb-native-actions],[data-hmb-native-identity]")) return;
    event.stopPropagation();
    if (button.dataset.shot) {
      if (button.dataset.shot !== state.shot_uuid) navigate("select_shot", {shot_uuid: button.dataset.shot});
      return;
    }
    if (button.dataset.role) {
      if (button.dataset.role !== (state.role || "after")) navigate("set_role", {role: button.dataset.role});
      return;
    }
    if (button.dataset.fieldTab) {
      if (button.dataset.fieldTab !== view.promptField) navigate("field_tab", {field: button.dataset.fieldTab});
      return;
    }
    const action = button.dataset.action;
    if (action === "analyze") {
      command(action, {...configuration(), confirmed_paid: true});
    } else if (action === "toggle-range") {
      rangeDragCleanup?.();
      if (state.slot?.kind === "video") view.videoRangesEnabled = !view.videoRangesEnabled;
      else view.audioRangesCollapsed = !view.audioRangesCollapsed;
      paint();
    } else if (action === "remove-interval") {
      const spec = intervalSpec(state.slot?.kind, dict(state.source));
      const rows = currentIntervals(spec);
      const index = Math.max(0, Math.min(rows.length - 1, view.selectedInterval || 0));
      rows.splice(index, 1);
      setIntervals(rows, Math.max(0, index - 1));
    } else if (action) {
      command(action);
    }
  }

  function change(event) {
    const control = event.target;
    if (control.matches("[data-kind]")) {
      view.kind = control.value;
      paint();
    } else if (control.matches("[data-source]") && control.value) {
      command("select_source", {kind: view.kind, source_id: control.value});
    } else if (control.matches("[data-category],[data-results-only]")) {
      deliver();
    } else if (control.matches("[data-result-text]")) {
      if (control.value !== String(state.result_text ?? "")) {
        clearTimeout(deliveryTimer);
        deliveryTimer = setTimeout(() => { if (!pending) deliver(true); }, 0);
      } else view.resultTextDraft = null;
    } else if (control.matches("[data-field-text]")) {
      clearTimeout(deliveryTimer);
      if (dirtyPromptField()) deliveryTimer = setTimeout(() => { if (!pending) savePromptField(); }, 0);
      else view.fieldDraft = null;
    }
  }

  function input(event) {
    if (event.target.matches("[data-result-text]")) {
      const prior = view.resultTextDraft?.shot_uuid === state.shot_uuid ? view.resultTextDraft : null;
      view.resultTextDraft = {shot_uuid: state.shot_uuid, value: event.target.value,
        categories: prior ? prior.categories : selectedCategories()};
    } else if (event.target.matches("[data-field-text]")) {
      view.fieldDraft = {shot_uuid: state.shot_uuid, field: event.target.dataset.fieldText, value: event.target.value};
    }
  }

  function holdCanvasInput(event) {
    const target = event.target;
    if (target.closest?.("button,input,select,textarea,video,audio") &&
        !target.closest("[data-hmb-native-actions],[data-hmb-native-identity]")) event.stopPropagation();
  }

  function nativeHeader(event) {
    view.nativeHeader = event.detail?.active === true;
    if (view.nativeHeader) root.setAttribute("data-hmb-native-header", "active");
    else root.removeAttribute("data-hmb-native-header");
  }

  function previewError(event) {
    const media = event.target;
    if (!media.matches?.(".ha-preview :is(img,video,audio)")) return;
    media.parentElement.setAttribute("data-preview-failed", "");
  }

  frame.addEventListener("click", click);
  frame.addEventListener("change", change);
  frame.addEventListener("input", input);
  frame.addEventListener("pointerdown", intervalPointerDown);
  frame.addEventListener("keydown", intervalKeydown);
  frame.addEventListener("error", previewError, true);
  for (const name of ["pointerdown", "mousedown", "keydown", "keyup"]) frame.addEventListener(name, holdCanvasInput);
  const controller = {
    update(next = {}) {
      if (disposed) return;
      const previous = state;
      const incoming = read(next);
      if (incoming.__hmb_analysis_command || (pending && !Number.isSafeInteger(incoming.revision))) return;
      if (Number.isSafeInteger(incoming.revision) && incoming.revision < previous.revision) return;
      latest = next;
      const inPlaceRoute = pendingRouteOnly && incoming.ack === pending &&
        routeShape(incoming) === routeShape(previous);
      state = incoming;
      if(displayPage && (state.channel_uuid !== previous.channel_uuid || state.role !== previous.role ||
          !list(state.shots).some(row=>row.shot_uuid===displayPage.shot_uuid))) displayPage=null;
      if (state.ack && state.ack === pending) {
        displayPage = null;
        pending = "";
        clearTimeout(timer);
        const completedAction = pendingAction;
        if (!state.error && completedAction === "analyze") view.intervalDraft = null;
        pendingAction = "";
        pendingRouteOnly = false;
        view.deliveryDraft = null;
        if (state.error) {
          queuedNavigation = null;
        } else {
          view.resultTextDraft = null;
          if (completedAction === "set_field") view.fieldDraft = null;
          if (queuedNavigation) {
            const next = queuedNavigation;
            queuedNavigation = null;
            queueMicrotask(() => { if (!disposed && !pending) finishNavigation(next); });
          } else if (completedAction === "delivery" && dirtyPromptField()) {
            queueMicrotask(() => { if (!disposed && !pending) savePromptField(); });
          }
        }
      }
      if (state.channel_uuid !== previous.channel_uuid || state.shot_uuid !== previous.shot_uuid ||
          state.role !== previous.role || state.slot?.kind !== previous.slot?.kind) {
        view.kind = state.slot?.kind || "image";
        view.deliveryDraft = null;
        view.resultTextDraft = null;
        view.fieldDraft = null;
        view.intervalDraft = null;
        view.selectedInterval = 0;
        view.videoRangesEnabled = false;
      } else if (state.slot?.source_id !== previous.slot?.source_id) {
        view.deliveryDraft = null;
        view.resultTextDraft = null;
        view.fieldDraft = null;
        view.intervalDraft = null;
        view.selectedInterval = 0;
        view.videoRangesEnabled = false;
      }
      if (JSON.stringify(state) !== JSON.stringify(previous) || Boolean(next.disabled) !== Boolean(props.disabled)) {
        notice = "";
        const modelOption = frame.querySelector('[data-model] option[value=""]');
        if (modelOption && Boolean(next.disabled) === Boolean(props.disabled) &&
            state.default_model !== previous.default_model &&
            JSON.stringify({...state, default_model: previous.default_model}) === JSON.stringify(previous)) {
          modelOption.textContent = state.default_model || "None";
        } else if (inPlaceRoute) patchRouteOnly();
        else paint();
      }
      props = next;
    },
    cleanup() {
      if (disposed) return;
      disposed = true;
      clearTimeout(timer);
      clearTimeout(deliveryTimer);
      rangeDragCleanup?.();
      frame.removeEventListener("click", click);
      frame.removeEventListener("change", change);
      frame.removeEventListener("input", input);
      frame.removeEventListener("pointerdown", intervalPointerDown);
      frame.removeEventListener("keydown", intervalKeydown);
      frame.removeEventListener("error", previewError, true);
      for (const name of ["pointerdown", "mousedown", "keydown", "keyup"]) frame.removeEventListener(name, holdCanvasInput);
      root.removeEventListener("hmb-color-lut-header-state", nativeHeader);
      doc.dispatchEvent(new doc.defaultView.CustomEvent("hmb-color-lut-header-retire", {detail: {container: root}}));
      frame.remove();
      delete container.__hmbAnalysisController;
    },
  };
  container.__hmbAnalysisController = controller;
  paint();
  const root = frame.querySelector(".hmb-analysis");
  root.addEventListener("hmb-color-lut-header-state", nativeHeader);
  doc.dispatchEvent(new doc.defaultView.CustomEvent("hmb-color-lut-header-ready", {detail: {container: root}}));
  return controller;
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
    let contextNode = null, notice = null, noticeTimer = null, disposed = false;
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
    const dismiss = () => { win.clearTimeout(noticeTimer); notice?.remove(); notice = null; };
    const show = () => {
      if (disposed || nativeReady()) return;
      if (notice?.isConnected) { notice.querySelector("button")?.focus(); return; }
      notice = doc.createElement("section");
      notice.setAttribute("data-hmb-native-safety-notice", "required");
      notice.setAttribute("role", "alert");
      Object.assign(notice.style, { position: "fixed", zIndex: "2147483647", right: "20px", bottom: "64px", maxWidth: "420px", padding: "18px", border: "1px solid #b89458", borderRadius: "18px", background: "#151c29", color: "#f8fafc", font: "13px/1.6 system-ui,sans-serif", boxShadow: "0 8px 32px #0008" });
      const title = doc.createElement("strong"); title.textContent = "HMB 노드 삭제를 중단했습니다";
      const text = doc.createElement("p");
      text.textContent = "현재 화면에서 연결 상태를 확인할 수 없습니다. 작업을 저장하고 Griptape를 다시 시작한 뒤 확인하세요.";
      const close = doc.createElement("button"); close.type = "button"; close.textContent = "확인";
      Object.assign(close.style, { border: "1px solid #64748b", borderRadius: "999px", background: "#243044", color: "#f8fafc", padding: "6px 18px", cursor: "pointer" });
      close.addEventListener("click", dismiss); notice.append(title, text, close); doc.body.append(notice); close.focus();
      noticeTimer = win.setTimeout(dismiss, 8000);
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
      else if (!event.target?.closest?.("[data-hmb-native-safety-notice]")) { contextNode = null; dismiss(); }
    };
    const contextmenu = event => { contextNode = rootOf(event.target); };
    const dispose = () => {
      if (disposed) return;
      disposed = true; observer?.disconnect(); dismiss(); contextNode = null;
      win.removeEventListener("keydown", keydown, true); win.removeEventListener("click", click, true); win.removeEventListener("contextmenu", contextmenu, true);
      if (doc[key] === shared) delete doc[key];
    };
    const sync = () => {
      if (disposed) return;
      const retained = roots();
      if (!owners.size && !retained.size) { dispose(); return; }
      if (nativeReady() || !retained.size) dismiss();
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

export default function HMBAnalysisAgentWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
