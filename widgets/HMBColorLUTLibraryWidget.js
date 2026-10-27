// Standalone Griptape widget: one persistent mount, local LUT preview and captured commands.
export const HMB_COLOR_LUT_SCHEMA_VERSION = 1;
export const HMB_COLOR_LUT_CUBE_SIZE = 33;
export const HMB_COLOR_LUT_PRECISION_VERSION = 2;
export const HMB_COLOR_LUT_MAX_STEP = 12;
export const HMB_COLOR_LUT_ONLY_SHOT_VALUE = "__hmb_only__";
export const HMB_COLOR_LUT_COMMAND_FIELD = "__hmb_color_lut_command__";
export const HMB_COLOR_LUT_SHOT_PALETTE = Object.freeze({ 1: "#F472B6", 2: "#3B82F6", 3: "#10B981", 4: "#8B5CF6", 5: "#EAB308" });
export const HMB_COLOR_LUT_CONTROLS = Object.freeze(["exposure", "temperature", "contrast", "saturation", "shadows", "highlights"]);
const record = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : {};
const clean = (v, max = 4096) => String(v ?? "").trim().slice(0, max);
const finite = (v, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const escape = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const copy = (v) => JSON.parse(JSON.stringify(v));

export function hmbColorLUTSettings(value = {}) {
  const raw = record(value), result = { enabled: raw.enabled === true, precision_version: HMB_COLOR_LUT_PRECISION_VERSION };
  // Strengths keep their original [-3, 3] domain. Only the slider granularity
  // changes; loading an old preset must not round or weaken its actual look.
  for (const key of HMB_COLOR_LUT_CONTROLS) result[key] = raw.precision_version === HMB_COLOR_LUT_PRECISION_VERSION
    ? Math.round(clamp(finite(raw[key]), -3, 3) * 4) / 4 : clamp(Math.trunc(finite(raw[key])), -3, 3);
  return result;
}
export const hmbColorLUTStrengthFromStep = (step) => Math.round(clamp(finite(step), -HMB_COLOR_LUT_MAX_STEP, HMB_COLOR_LUT_MAX_STEP)) * 3 / HMB_COLOR_LUT_MAX_STEP;
const sliderStep = (strength) => Math.round(strength * HMB_COLOR_LUT_MAX_STEP / 3);
export function hmbColorLUTShotCatalog(value) {
  const s = record(value);
  if (s.schema !== "hmb-shot-routing-catalog" || s.version !== 1 || !clean(s.publisher_instance_uuid, 128) || !clean(s.channel_uuid, 128)
    || !Number.isSafeInteger(s.generation) || s.generation < 1 || !/^[a-f0-9]{64}$/i.test(s.metadata_sha256 || "")
    || !Array.isArray(s.shots) || !s.shots.length || s.shots.length > 5) return {};
  const ids = new Set(), nums = new Set(), shots = [];
  for (const raw of s.shots) {
    const shot = record(raw), id = clean(shot.shot_uuid, 128), n = shot.number;
    if (!id || ids.has(id) || !Number.isInteger(n) || n < 1 || n > 5 || nums.has(n) || !clean(shot.name, 128)
      || !Number.isSafeInteger(shot.revision) || shot.revision < 0) return {};
    ids.add(id); nums.add(n);
    shots.push({ shot_uuid: id, number: n, name: clean(shot.name, 128), revision: shot.revision });
  }
  return { schema: s.schema, version: 1, publisher_instance_uuid: clean(s.publisher_instance_uuid, 128), channel_uuid: clean(s.channel_uuid, 128),
    generation: s.generation, metadata_sha256: s.metadata_sha256.toLowerCase(), shots: shots.sort((a, b) => a.number - b.number) };
}
const onlyShot = () => ({ channel_uuid: "", shot_uuid: "", number: 1, name: "Only" });
const uploadProject = (value) => {
  const p = record(value), id = clean(p.id, 128), name = clean(p.name, 256);
  return /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(id) && name ? { id, name } : null;
};
export function hmbColorLUTShotOptions(value) {
  const state = record(value), catalog = hmbColorLUTShotCatalog(state.shot_catalog);
  const selected = catalog.channel_uuid === state.shot?.channel_uuid && catalog.shots?.find((s) => s.shot_uuid === state.shot?.shot_uuid);
  return [{ key: HMB_COLOR_LUT_ONLY_SHOT_VALUE, ...onlyShot(), number: 0, only: true, selected: !selected }, ...(catalog.shots || []).map((shot) => ({
    ...shot, channel_uuid: catalog.channel_uuid, key: `${catalog.channel_uuid}\u001f${shot.shot_uuid}`, only: false, selected: shot.shot_uuid === selected?.shot_uuid,
  }))];
}
export function hmbColorLUTShotAccent(state) {
  const selected = hmbColorLUTShotOptions(state).find((option) => option.selected);
  return HMB_COLOR_LUT_SHOT_PALETTE[selected?.number] || "#64748B";
}
export function hmbColorLUTState(input = {}) {
  const wrapper = record(input);
  let value = wrapper.value ?? wrapper.parameterValue ?? wrapper.defaultValue ?? input;
  if (typeof value === "string") { try { value = JSON.parse(value); } catch { value = {}; } }
  const s = record(value), catalog = hmbColorLUTShotCatalog(s.shot_catalog ?? wrapper.shot_catalog);
  const rawShot = record(s.shot ?? wrapper.shot);
  const selected = catalog.channel_uuid === rawShot.channel_uuid && catalog.shots?.find((shot) => shot.shot_uuid === rawShot.shot_uuid);
  const shot = selected ? { channel_uuid: catalog.channel_uuid, shot_uuid: selected.shot_uuid, number: selected.number, name: selected.name } : onlyShot();
  const source = record(s.source), output = record(s.output), status = record(s.status), result = record(s.result), upload = record(s.web_upload);
  const profiles = (Array.isArray(s.profiles) ? s.profiles : []).filter((p) => p && p.name).map((p) => ({
    id: clean(p.id, 128), name: clean(p.name, 80), project_id: clean(p.project_id), settings: hmbColorLUTSettings(p.settings),
    deletable: p.deletable === true, read_only: p.read_only === true,
  }));
  const sourceMatches = shot.shot_uuid ? source.shot_uuid === shot.shot_uuid && source.channel_uuid === shot.channel_uuid : !source.shot_uuid;
  const manualProject = uploadProject(s.manual_project) || {};
  const projects = (Array.isArray(s.upload_projects) ? s.upload_projects : []).slice(0, 100).map(uploadProject).filter(Boolean);
  const manualReady = manualProject.id && projects.some(p => p.id === manualProject.id && p.name === manualProject.name) && source.path;
  return { schema_version: 1, revision: Math.max(0, Math.trunc(finite(s.revision))), language: s.language === "en" ? "en" : "ko",
    shot, shot_catalog: catalog, project_id: clean(s.project_id), project: record(s.project), preset_name: clean(s.preset_name, 80), preset_id: clean(s.preset_id, 128), profiles,
    manual_project: manualProject, upload_projects: projects,
    settings: hmbColorLUTSettings(s.settings), source: sourceMatches ? { path: clean(source.path), url: clean(source.url), name: clean(source.name, 256),
      revision: clean(source.revision, 128), shot_uuid: clean(source.shot_uuid, 128), channel_uuid: clean(source.channel_uuid, 128),
      width: Math.max(0, finite(source.width)), height: Math.max(0, finite(source.height)), fps: Math.max(0, finite(source.fps)), duration: Math.max(0, finite(source.duration)) } : {},
    output: { codec: ["hevc10", "prores", "ffv1"].includes(output.codec) ? output.codec : "hevc10", manual_output_enabled: output.manual_output_enabled === true, path: clean(output.path) },
    status: { phase: clean(status.phase, 40) || "idle", message: clean(status.message), progress: clamp(finite(status.progress)) },
    web_upload: { enabled: upload.enabled === true && Boolean(shot.shot_uuid || manualReady), phase: clean(upload.phase, 32), reason: clean(upload.reason, 512) },
    result: { ...result, path: clean(result.path), url: clean(result.url) } };
}
export const hmbNormalizeColorLUTWidgetValue = hmbColorLUTState;

export function hmbColorLUTSelectedProfile(state) {
  if (!state?.preset_id) return null;
  const matches = (state.profiles || []).filter((profile) => profile.id === state.preset_id
    && profile.project_id === state.project_id && profile.name === state.preset_name);
  return matches.length === 1 ? matches[0] : null;
}
export function hmbColorLUTCanDeleteProfile(state) {
  const profile = hmbColorLUTSelectedProfile(state);
  return Boolean(profile?.deletable === true && profile.read_only !== true);
}

// Same display-domain transform as hmb_color_lut_engine.py; cube vertices are
// rounded to the exported .cube precision before float32 preview storage.
export function hmbColorLUTTransform(rgb, settings) {
  return transformNormalized(rgb, hmbColorLUTSettings(settings));
}
function transformNormalized(rgb, s) {
  let [r, g, b] = rgb.map((v) => clamp(finite(v)));
  if (!s.enabled) return [r, g, b];
  const exposure = 2 ** (0.22 * s.exposure);
  r = r * exposure + 7 / 255 * s.temperature; g *= exposure; b = b * exposure - 7 / 255 * s.temperature;
  let y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const lum = clamp(y), offset = 0.04 * s.shadows * (1 - lum) ** 2 + 0.04 * s.highlights * lum ** 2;
  const contrast = 1 + 0.13 * s.contrast;
  r = (r + offset - 0.5) * contrast + 0.5; g = (g + offset - 0.5) * contrast + 0.5; b = (b + offset - 0.5) * contrast + 0.5;
  y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const sat = 1 + 0.16 * s.saturation;
  return [r, g, b].map((v) => clamp(y + (v - y) * sat));
}
export function hmbColorLUTCube(settings, size = HMB_COLOR_LUT_CUBE_SIZE) {
  if (!Number.isInteger(size) || size < 2 || size > 65) throw new Error("Unsupported cube size.");
  const normalized = hmbColorLUTSettings(settings);
  const cube = new Float32Array(size ** 3 * 3);
  fillCube(cube, normalized, size, 0, size ** 3);
  return cube;
}
function fillCube(cube, normalized, size, start, end) {
  const plane = size * size;
  for (let cell = start; cell < end; cell++) {
    const r = cell % size, g = Math.floor(cell / size) % size, b = Math.floor(cell / plane);
    const rgb = transformNormalized([r / (size - 1), g / (size - 1), b / (size - 1)], normalized);
    for (let channel = 0; channel < 3; channel++) cube[cell * 3 + channel] = Math.floor(rgb[channel] * 1e9 + .5) / 1e9;
  }
}
// One slider movement must not occupy an entire animation frame. The same
// vertex math and order as the exported cube are spread across short tasks.
export function hmbColorLUTCubeChunked(settings, schedule, cancelScheduled, complete, size = HMB_COLOR_LUT_CUBE_SIZE, chunkSize = 4096) {
  if (!Number.isInteger(size) || size < 2 || size > 65) throw new Error("Unsupported cube size.");
  const normalized = hmbColorLUTSettings(settings), cube = new Float32Array(size ** 3 * 3);
  const total = size ** 3;
  let next = 0, ticket = 0, cancelled = false;
  const step = () => {
    ticket = 0;
    if (cancelled) return;
    const end = Math.min(total, next + Math.max(1, Math.trunc(chunkSize)));
    fillCube(cube, normalized, size, next, end);
    next = end;
    if (next < total) ticket = schedule(step);
    else complete(cube);
  };
  ticket = schedule(step);
  return () => { cancelled = true; if (ticket) cancelScheduled(ticket); };
}
export function hmbColorLUTSample(cube, rgb, size = HMB_COLOR_LUT_CUBE_SIZE) {
  const p = rgb.map((v) => clamp(v) * (size - 1)), lo = p.map(Math.floor), hi = lo.map((v) => Math.min(size - 1, v + 1)), f = p.map((v, i) => v - lo[i]);
  const out = [0, 0, 0];
  for (let z = 0; z < 2; z++) for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) {
    const index = (((z ? hi[2] : lo[2]) * size + (y ? hi[1] : lo[1])) * size + (x ? hi[0] : lo[0])) * 3;
    const weight = (x ? f[0] : 1 - f[0]) * (y ? f[1] : 1 - f[1]) * (z ? f[2] : 1 - f[2]);
    for (let c = 0; c < 3; c++) out[c] += cube[index + c] * weight;
  }
  return out;
}
// The 2D fallback avoids allocating several arrays for every video pixel.
// Keep the same eight samples and summation order as hmbColorLUTSample.
export function hmbColorLUTGradePixels(data, width, cube, mode, wipe, size = HMB_COLOR_LUT_CUBE_SIZE) {
  const scale = size - 1, compareEdge = wipe * width;
  for (let i = 0; i < data.length; i += 4) {
    if (mode === 1 && (i / 4) % width < compareEdge) continue;
    const rp = data[i] / 255 * scale, gp = data[i + 1] / 255 * scale, bp = data[i + 2] / 255 * scale;
    const r0 = Math.floor(rp), g0 = Math.floor(gp), b0 = Math.floor(bp);
    const r1 = Math.min(scale, r0 + 1), g1 = Math.min(scale, g0 + 1), b1 = Math.min(scale, b0 + 1);
    const rf = rp - r0, gf = gp - g0, bf = bp - b0;
    let red = 0, green = 0, blue = 0;
    for (let z = 0; z < 2; z++) for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) {
      const index = (((z ? b1 : b0) * size + (y ? g1 : g0)) * size + (x ? r1 : r0)) * 3;
      const weight = (x ? rf : 1 - rf) * (y ? gf : 1 - gf) * (z ? bf : 1 - bf);
      red += cube[index] * weight; green += cube[index + 1] * weight; blue += cube[index + 2] * weight;
    }
    data[i] = Math.round(red * 255); data[i + 1] = Math.round(green * 255); data[i + 2] = Math.round(blue * 255);
  }
  return data;
}
export function hmbColorLUTCommand(action, state, id = `cl-${Date.now()}-${Math.random().toString(36).slice(2)}`) {
  if (!["browse_video", "export", "export_upload", "cancel", "save_profile", "delete_profile", "upload_web", "select_upload_project", "refresh_upload_projects"].includes(action)) throw new Error("Unsupported Color LUT action.");
  const captured = hmbColorLUTState(state);
  if (action === "delete_profile") {
    if (!hmbColorLUTCanDeleteProfile(captured)) throw new Error("Select a saved personal preset before deleting.");
    return { id, action, state: captured, preset_id: captured.preset_id, project_id: captured.project_id, preset_name: captured.preset_name };
  }
  return { id, action, state: captured };
}

const TEXT = {
  ko: { subtitle: "최종 영상 컬러 마감", language: "언어", shot: "바인딩 샷", preview: "미리보기", original: "원본", compare: "비교", graded: "보정", wipe: "비교 위치",
    browse: "영상 불러오기", standalone: "Only · 독립 영상 입력", empty: "완료 영상을 연결하거나 영상 불러오기로 시작하세요", loading: "영상을 불러오는 중", ready: "준비됨", sourceError: "영상을 읽을 수 없습니다", previewError: "컬러 미리보기를 표시할 수 없습니다", transportError: "상태 전송을 사용할 수 없습니다", commandError: "요청을 전달할 수 없습니다",
    play: "▶ 재생", pause: "Ⅱ 일시정지", step: "한 프레임", seek: "프레임 탐색", frame: "프레임", enable: "사용", grade: "프로젝트 룩 · 샷 보정", project: "프로젝트", profileName: "프리셋 이름", apply: "프리셋 적용", deleteProfile: "프리셋 삭제", deleteProfileHint: "현재 선택한 개인 로컬 프리셋만 삭제", reset: "원본 값", save: "프리셋 저장", upload: "웹 업로드", uploadCheck: "업로드 상태 확인", uploaded: "웹 업로드 완료", uploading: "웹 업로드 중…", neutral: "기본", stage: "단계",
    exposure: "노출", temperature: "색온도", contrast: "대비", saturation: "채도", shadows: "그림자", highlights: "하이라이트", low: ["어둡게", "차갑게", "부드럽게", "낮게", "깊게", "억제"], high: ["밝게", "따뜻하게", "선명하게", "높게", "밝게", "강조"],
    enabled: "샷별 보정 적용 중", disabled: "원본 유지 · 보정 사용 안함", live: "조절 중 미리보기", output: "최종 영상 출력", outputUpload: "최종출력 & 웹 업로드", outputSource: "영상을 연결하거나 불러온 뒤 출력하세요.", outputUploadProject: "업로드할 프로젝트 또는 My Box를 선택하세요.", outputLocalFormat: "FFV1은 웹 업로드 없이 로컬에 무손실 영상으로 출력합니다.", outputNote: "원본 해상도 · FPS 유지 / 원본에서 1회 인코딩", manual: "출력 경로 직접 지정", path: "출력 경로", autoPath: "자동 · 입력 영상 폴더 / 새 버전 파일", customPath: "저장할 전체 파일 경로", codec: "출력 형식", hevc: "HEVC 10-bit · 고품질", prores: "ProRes 422 HQ · 마스터", ffv1: "FFV1 · 무손실", cancel: "출력 취소", result: "출력 영상 열기", pending: "요청을 처리하는 중", bound: "샷 연결", unbound: "샷 바인딩 없음" },
  en: { subtitle: "Final video color finishing", language: "Language", shot: "Bound shot", preview: "Preview", original: "Original", compare: "Compare", graded: "Graded", wipe: "Compare position",
    browse: "Import video", standalone: "Only · Standalone video", empty: "Connect a completed video or import a video to begin", loading: "Loading video", ready: "Ready", sourceError: "Unable to load video", previewError: "Unable to display color preview", transportError: "State transport is unavailable", commandError: "Unable to deliver request",
    play: "▶ Play", pause: "Ⅱ Pause", step: "One frame", seek: "Seek frame", frame: "Frame", enable: "Enable", grade: "Project look · Shot grade", project: "Project", profileName: "Preset name", apply: "Apply preset", deleteProfile: "Delete preset", deleteProfileHint: "Delete only the selected personal local preset", reset: "Original values", save: "Save preset", upload: "Upload to web", uploadCheck: "Check upload", uploaded: "Uploaded", uploading: "Uploading…", neutral: "Neutral", stage: "stage",
    exposure: "Exposure", temperature: "Temperature", contrast: "Contrast", saturation: "Saturation", shadows: "Shadows", highlights: "Highlights", low: ["Darker", "Cooler", "Softer", "Lower", "Deeper", "Suppress"], high: ["Brighter", "Warmer", "Sharper", "Higher", "Brighter", "Emphasize"],
    enabled: "Shot grade enabled", disabled: "Original · Grading disabled", live: "Live preview while adjusting", output: "Export final video", outputUpload: "Final export & web upload", outputSource: "Connect or import a video before exporting.", outputUploadProject: "Select an upload project or My Box.", outputLocalFormat: "FFV1 exports lossless video locally without web upload.", outputNote: "Original resolution · FPS / Encode once from source", manual: "Set output path", path: "Output path", autoPath: "Automatic · Source folder / New version file", customPath: "Full output file path", codec: "Output format", hevc: "HEVC 10-bit · High quality", prores: "ProRes 422 HQ · Master", ffv1: "FFV1 · Lossless", cancel: "Cancel export", result: "Open output video", pending: "Processing request", bound: "Shot linked", unbound: "No shot binding" },
};
const textFor = (s) => TEXT[s.language] || TEXT.ko;
const exportAction = (state) => {
  const text = textFor(state);
  const local = state.output.codec === "ffv1";
  const label = local ? text.output : text.outputUpload;
  let reason = !state.source.path && !state.source.url ? text.outputSource : "";
  if (!reason && !local && !state.shot.shot_uuid && !state.upload_projects.some(project => project.id === state.manual_project.id
    && project.name === state.manual_project.name)) reason = text.outputUploadProject;
  return { action: local ? "export" : "export_upload", label, reason,
    title: reason ? `${reason}${local ? ` ${text.outputLocalFormat}` : ""}` : local ? text.outputLocalFormat : label };
};
const stageLabel = (s, key) => {
  const step = sliderStep(s.settings[key]);
  if (!step) return textFor(s).neutral;
  return `${step > 0 ? "+" : "−"}${Math.abs(step)} ${textFor(s).stage}`;
};
const shotMarkup = (s) => hmbColorLUTShotOptions(s).map((option) => `<option value="${escape(option.key)}"${option.selected ? " selected" : ""}>${escape(option.only ? "Only" : `${String(option.number).padStart(2, "0")} · ${option.name}`)}</option>`).join("");

export function hmbRenderColorLUTWidget(input = {}) {
  const s = hmbColorLUTState(input), t = textFor(s), accent = hmbColorLUTShotAccent(s);
  const label = (key) => `<span data-text="${key}">${escape(t[key])}</span>`;
  return `<style>
.hmb-color-lut{--cl-accent:${accent};--cl-rgb:${accent.slice(1).match(/../g).map((x) => parseInt(x, 16)).join(",")};--cl-bg:#090c16;--cl-panel:#0f1726;--cl-line:#283347;--cl-muted:#a7b3c6;color:#e8eef7;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:12px;line-height:1.45;background:var(--cl-bg);border:1px solid rgba(var(--cl-rgb),.5);border-radius:11px;overflow:auto;width:100%;height:100%;min-height:640px;container-type:inline-size;color-scheme:dark;box-shadow:0 8px 24px #0004}
.hmb-color-lut *{box-sizing:border-box}.hmb-color-lut [hidden]{display:none!important}.hmb-color-lut :is(button,input,select):not([data-hmb-native-identity] *,[data-hmb-native-actions] *){font:inherit}.hmb-color-lut :is(button,select,input[type=text]):not([data-hmb-native-identity] *,[data-hmb-native-actions] *){min-height:32px;border:1px solid #344057;border-radius:6px;background:#0b111d;color:#edf2fa;padding:5px 9px}.hmb-color-lut button:not([data-hmb-native-identity] *,[data-hmb-native-actions] *){cursor:pointer}.hmb-color-lut :disabled:not([data-hmb-native-identity] *,[data-hmb-native-actions] *){opacity:.5;cursor:default}.hmb-color-lut :focus-visible:not([data-hmb-native-identity] *,[data-hmb-native-actions] *){outline:2px solid var(--cl-accent);outline-offset:2px}.hmb-color-lut button:not([data-hmb-native-identity] *,[data-hmb-native-actions] *)[aria-pressed=true]{border-color:var(--cl-accent);background:rgba(var(--cl-rgb),.19)}.hmb-color-lut label{min-width:0}
.hmb-color-lut .cl-head{display:flex;align-items:center;gap:12px;padding:0 16px;height:68px;background:linear-gradient(90deg,rgba(var(--cl-rgb),.2),#090c16fa);border-bottom:1px solid rgba(var(--cl-rgb),.4)}.hmb-color-lut .cl-mark{flex:0 0 30px;width:30px;height:30px;display:grid;place-items:center;border:1px solid var(--cl-accent);border-radius:8px;color:var(--cl-accent);font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-color-lut .cl-brand{flex:1;min-width:0;overflow:hidden}.hmb-color-lut .cl-brand strong{display:block;font-size:15px;font-weight:800;white-space:nowrap}.hmb-color-lut .cl-brand small{display:block;color:var(--cl-muted);font-size:9px;white-space:nowrap}.hmb-color-lut .cl-shot-shell{display:flex;gap:7px;align-items:center;flex:0 1 210px;width:210px;min-width:120px}.hmb-color-lut .cl-shot-shell>span{font-size:8px;color:var(--cl-muted);font-weight:900}.hmb-color-lut .cl-shot-shell select{width:100%;height:44px;font-size:13px;font-weight:800;border-color:rgba(var(--cl-rgb),.6);background:rgba(var(--cl-rgb),.1)}.hmb-color-lut option{background:#0b111d}.hmb-color-lut .cl-lang{height:30px;min-width:58px;font-size:12px;font-weight:800;border-color:rgba(var(--cl-rgb),.6)}
.hmb-color-lut .cl-input{display:flex;align-items:center;gap:9px;padding:10px 14px;border-bottom:1px solid var(--cl-line);flex-wrap:wrap}.hmb-color-lut .cl-dot{width:7px;height:7px;border-radius:50%;background:var(--cl-accent)}.hmb-color-lut .cl-source{flex:1;min-width:120px;overflow-wrap:anywhere}.hmb-color-lut .cl-input small{color:var(--cl-muted);font-size:10px}.hmb-color-lut .cl-input button{font-size:11px}.hmb-color-lut .cl-work{display:grid;grid-template-columns:minmax(0,1.85fr) minmax(250px,1fr);gap:12px;padding:12px}.hmb-color-lut :is(.cl-preview,.cl-grade){min-width:0;border:1px solid var(--cl-line);border-radius:8px;background:var(--cl-panel);overflow:hidden}.hmb-color-lut .cl-panel-head{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--cl-line);min-height:46px}.hmb-color-lut .cl-panel-head>span:first-child{flex:1}.hmb-color-lut .cl-mode{display:flex;gap:4px}.hmb-color-lut .cl-mode button{font-size:11px;min-height:28px;padding:4px 8px}
.hmb-color-lut .cl-screen{position:relative;background:#05070c;aspect-ratio:16/10;overflow:hidden}.hmb-color-lut canvas{position:absolute;width:100%;height:100%;object-fit:contain;inset:0}.hmb-color-lut .cl-seam{position:absolute;inset:0 auto 0 50%;width:1px;background:#fff;pointer-events:none}.hmb-color-lut .cl-seam button{position:absolute;top:45%;left:-20px;width:40px;height:40px;min-width:40px;min-height:40px;padding:0;border-radius:50%;background:#142033;border:1px solid #b8c9e1;display:grid;place-items:center;pointer-events:auto;touch-action:none;cursor:ew-resize}.hmb-color-lut .cl-label{position:absolute;top:12px;font-size:11px;padding:4px 8px;border-radius:4px;background:#090e18dc;pointer-events:none}.hmb-color-lut .cl-before{left:12px}.hmb-color-lut .cl-after{right:12px;color:var(--cl-accent)}.hmb-color-lut .cl-empty{position:absolute;inset:0;background:#0a101b;display:grid;place-items:center;padding:20px;text-align:center;color:var(--cl-muted)}.hmb-color-lut input[type=range]{width:100%;accent-color:var(--cl-accent);cursor:pointer;margin:0;min-height:23px;touch-action:pan-y}.hmb-color-lut .cl-transport{padding:12px;border-top:1px solid var(--cl-line)}.hmb-color-lut .cl-player-row{display:flex;align-items:center;gap:8px;margin-top:7px}.hmb-color-lut .cl-player-row small{margin-left:auto;color:var(--cl-muted);font-size:10px;font-variant-numeric:tabular-nums}.hmb-color-lut .cl-player-row button{font-size:11px;min-height:29px}.hmb-color-lut .cl-note{display:flex;justify-content:space-between;gap:8px;padding:10px 12px;border-top:1px solid var(--cl-line);color:var(--cl-muted);font-size:10px}
.hmb-color-lut .cl-grade-body{padding:12px}.hmb-color-lut .cl-project{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}.hmb-color-lut .cl-project label{display:flex;flex-direction:column;gap:5px;color:var(--cl-muted);font-size:11px}.hmb-color-lut .cl-project :is(select,input){width:100%;font-size:12px}.hmb-color-lut .cl-project button{grid-column:1/-1;font-size:11px}.hmb-color-lut .cl-profile-actions{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,7fr) minmax(0,3fr);gap:8px}.hmb-color-lut .cl-profile-actions button{grid-column:auto;min-width:0}.hmb-color-lut .cl-enable{display:flex;align-items:center;gap:6px;font-size:11px}.hmb-color-lut input[type=checkbox]{accent-color:var(--cl-accent);width:14px;height:14px}.hmb-color-lut .cl-control{margin:0 0 9px}.hmb-color-lut .cl-control label{display:flex;flex-direction:column;gap:2px;font-size:12px}.hmb-color-lut .cl-control label>span:first-child{display:flex;justify-content:space-between;gap:6px}.hmb-color-lut .cl-value{color:var(--cl-accent);font-size:11px}.hmb-color-lut .cl-endpoints{display:flex;justify-content:space-between;color:#8795aa;font-size:10px;margin-top:-3px}.hmb-color-lut .cl-grade-actions{display:flex;gap:6px;padding-top:8px;border-top:1px solid var(--cl-line)}.hmb-color-lut .cl-grade-actions button{flex:1;font-size:11px}.hmb-color-lut .cl-grade-actions button:last-child{border-color:rgba(var(--cl-rgb),.65)}
.hmb-color-lut .cl-web-upload{display:flex;flex-direction:column;gap:3px;margin-top:4px}.hmb-color-lut .cl-web-upload button{width:100%;font-weight:700;border-color:rgba(var(--cl-rgb),.65)}.hmb-color-lut .cl-web-upload small{color:var(--cl-muted);font-size:10px;line-height:1.4;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;max-height:2.8em}.hmb-color-lut .cl-output{padding:12px;border-top:1px solid var(--cl-line);background:#0c1220}.hmb-color-lut .cl-output-top{display:flex;gap:10px;align-items:center;margin-bottom:9px}.hmb-color-lut .cl-output-top>span{flex:1}.hmb-color-lut .cl-output-top small{color:var(--cl-muted);font-size:10px}.hmb-color-lut .cl-output-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.hmb-color-lut .cl-output-controls label{display:flex;gap:6px;align-items:center;font-size:11px;white-space:nowrap}.hmb-color-lut .cl-output-controls input[type=text]{flex:1;min-width:120px;font-size:11px}.hmb-color-lut .cl-output-controls :is(select,button){font-size:11px}.hmb-color-lut .cl-export{flex:0 0 auto;width:auto;min-width:max-content;white-space:nowrap;padding-inline:20px;background:rgba(var(--cl-rgb),.85);border-color:var(--cl-accent);color:#090d17;font-weight:700}.hmb-color-lut .cl-status{padding:10px 14px;border-top:1px solid var(--cl-line);display:flex;align-items:center;gap:8px;color:#b5c0d0;font-size:11px;min-height:38px;overflow-wrap:anywhere}.hmb-color-lut .cl-status progress{width:80px;accent-color:var(--cl-accent)}.hmb-color-lut .cl-status a{color:var(--cl-accent)}
@container(max-width:720px){.hmb-color-lut .cl-head{gap:9px;padding:0 12px}.hmb-color-lut .cl-brand small{display:none}.hmb-color-lut .cl-shot-shell{flex:1;width:auto}.hmb-color-lut .cl-work{grid-template-columns:1fr}.hmb-color-lut .cl-control-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}.hmb-color-lut .cl-output-controls input[type=text]{min-width:50%;flex-basis:60%}.hmb-color-lut .cl-output-top{flex-wrap:wrap}}
@container(max-width:430px){.hmb-color-lut .cl-mark,.hmb-color-lut .cl-shot-shell>span{display:none}.hmb-color-lut .cl-brand strong{font-size:12px}.hmb-color-lut .cl-lang{min-width:46px;padding-inline:5px}.hmb-color-lut .cl-work{padding:7px}.hmb-color-lut .cl-panel-head{flex-wrap:wrap}.hmb-color-lut .cl-note{flex-wrap:wrap}.hmb-color-lut .cl-output-controls>*{max-width:100%}}
/* Mini Studio 04 visual prototype. Existing geometry, text and behavior remain native. */
.hmb-color-lut{--cl-bg:#0b0f18;--cl-panel:#101725;--cl-line:#202936;--cl-muted:#9caabd;background:linear-gradient(155deg,#101521,#0b0f18 72%);border-color:rgba(var(--cl-rgb),.24);border-radius:22px;box-shadow:0 12px 30px #0003}
.hmb-color-lut :is(button,select,input[type=text]):not([data-hmb-native-identity] *,[data-hmb-native-actions] *){background:#080d15;border-color:#242d3b;border-radius:12px}
.hmb-color-lut button:not([data-hmb-native-identity] *,[data-hmb-native-actions] *){background:#1b2533;border-radius:999px;box-shadow:inset 0 1px 0 #ffffff05}
.hmb-color-lut button:not([data-hmb-native-identity] *,[data-hmb-native-actions] *)[aria-pressed=true]{background:rgba(var(--cl-rgb),.18);border-color:rgba(var(--cl-rgb),.5);color:var(--cl-accent)}
.hmb-color-lut .cl-head{background:linear-gradient(100deg,rgba(var(--cl-rgb),.1),#101521 68%);border-bottom-color:#202936}
.hmb-color-lut .cl-mark{background:rgba(var(--cl-rgb),.09);border-color:rgba(var(--cl-rgb),.2);border-radius:999px}
.hmb-color-lut .cl-shot-shell select{background:rgba(var(--cl-rgb),.08);border-color:rgba(var(--cl-rgb),.32)}
.hmb-color-lut option{background:#0b111b}
.hmb-color-lut :is(.cl-preview,.cl-grade){background:#101725;border-color:#202936}
.hmb-color-lut .cl-grade{border-radius:18px}
.hmb-color-lut .cl-panel-head{background:linear-gradient(105deg,#121b28,#101725)}
.hmb-color-lut .cl-empty{background:#0a101b}
.hmb-color-lut .cl-seam button{background:#1b2838;border-color:#6f8198}
.hmb-color-lut .cl-grade-actions button:last-child,.hmb-color-lut .cl-web-upload button{background:rgba(var(--cl-rgb),.1);border-color:rgba(var(--cl-rgb),.32)}
.hmb-color-lut .cl-output{background:#0e1520}
.hmb-color-lut .cl-export{background:var(--cl-accent);border-color:var(--cl-accent);color:#080e16;box-shadow:none}
.hmb-color-lut .cl-output-controls button.cl-export{flex:0 0 auto;width:max-content;min-width:180px;padding-inline:20px;white-space:nowrap}
/* End Mini Studio 04 visual prototype. */
.hmb-color-lut .cl-native-identity,.hmb-color-lut .cl-native-actions{display:none;min-width:0;--node-header-text:#e8eef7}
.hmb-color-lut[data-hmb-native-header=active] .cl-mark,.hmb-color-lut[data-hmb-native-header=active] .cl-brand{display:none}
.hmb-color-lut[data-hmb-native-header=active] .cl-native-identity{display:flex;align-items:center;flex:1;min-width:0}
.hmb-color-lut[data-hmb-native-header=active] .cl-native-actions{display:flex;align-items:center;flex:0 0 auto}
.hmb-color-lut .cl-native-identity>div{min-width:0;max-width:100%}.hmb-color-lut .cl-native-actions svg{flex-shrink:0}
.hmb-color-lut[data-hmb-native-header=active] .cl-head{cursor:grab}.hmb-color-lut[data-hmb-native-header=active] .cl-head:active{cursor:grabbing}
</style><div class="hmb-color-lut nodrag nowheel" data-language="${s.language}" data-shot-number="${hmbColorLUTShotOptions(s).find((x) => x.selected)?.number || 0}" tabindex="0">
<header class="cl-head group"><div class="cl-mark" aria-hidden="true">CL</div><div class="cl-brand"><strong>HMB Color LUT</strong><small data-text="subtitle">${t.subtitle}</small></div><div class="cl-native-identity" data-hmb-native-identity></div><div class="cl-native-actions nodrag" data-hmb-native-actions></div><label class="cl-shot-shell nodrag"><span>SHOT</span><select data-shot-selector aria-label="${t.shot}">${shotMarkup(s)}</select></label><button class="cl-lang nodrag" data-language-toggle type="button" aria-label="${t.language}">${s.language === "ko" ? "한국어" : "EN"}</button></header>
<div class="cl-input nodrag"><span class="cl-dot"></span><span class="cl-source" data-source></span><small data-source-revision></small><button data-action="browse_video" type="button">${label("browse")}</button></div>
<main class="cl-work nodrag"><section class="cl-preview"><div class="cl-panel-head">${label("preview")}<div class="cl-mode">${["original", "compare", "graded"].map((view) => `<button type="button" data-view="${view}" aria-pressed="${view === "compare"}">${label(view)}</button>`).join("")}</div></div><div class="cl-screen"><canvas data-preview width="960" height="540" role="img" aria-label="${t.preview}"></canvas><span class="cl-label cl-before" data-text="original">${t.original}</span><span class="cl-label cl-after" data-text="graded">${t.graded}</span><div class="cl-seam"><button type="button" data-wipe-handle role="slider" aria-label="${t.wipe}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50">↔</button></div><div class="cl-empty" data-empty>${t.empty}</div></div><div class="cl-transport"><input data-seek type="range" min="0" max="0" value="0" step="1" aria-label="${t.seek}" disabled><div class="cl-player-row"><button data-play type="button" disabled>${t.play}</button><button data-step type="button" disabled>${label("step")}</button><small data-frame></small></div></div><div class="cl-note"><span data-preview-note></span>${label("live")}</div></section>
<section class="cl-grade"><div class="cl-panel-head">${label("grade")}<label class="cl-enable"><input data-enable type="checkbox"${s.settings.enabled ? " checked" : ""}>${label("enable")}</label></div><div class="cl-grade-body"><div class="cl-project"><label>${label("project")}<select data-project disabled><option value="${escape(s.project_id)}">${escape(s.project.name || "—")}</option></select></label><label>${label("profileName")}<input type="text" data-profile-name maxlength="80" list="cl-presets" value="${escape(s.preset_name)}"><datalist data-presets id="cl-presets"></datalist></label><div class="cl-profile-actions"><button type="button" data-apply-profile>${label("apply")}</button><button type="button" data-action="delete_profile" title="${escape(t.deleteProfileHint)}" disabled>${label("deleteProfile")}</button></div></div><div class="cl-control-grid">${HMB_COLOR_LUT_CONTROLS.map((key, i) => `<div class="cl-control"><label><span>${label(key)}<output class="cl-value" data-value="${key}">${escape(stageLabel(s, key))}</output></span><input data-adjust="${key}" type="range" min="-${HMB_COLOR_LUT_MAX_STEP}" max="${HMB_COLOR_LUT_MAX_STEP}" step="1" value="${sliderStep(s.settings[key])}" aria-label="${t[key]}" aria-valuetext="${escape(stageLabel(s, key))}"><span class="cl-endpoints"><span data-low="${i}">${t.low[i]}</span><span data-high="${i}">${t.high[i]}</span></span></label></div>`).join("")}</div><div class="cl-grade-actions"><button data-reset type="button">${label("reset")}</button><button data-action="save_profile" type="button">${label("save")}</button></div><div class="cl-web-upload"><button data-action="upload_web" type="button" disabled>${label("upload")}</button><small data-upload-reason aria-live="polite"></small></div></div></section></main>
<section class="cl-output nodrag"><div class="cl-output-top">${label("output")}<small data-text="outputNote">${t.outputNote}</small></div><div class="cl-output-controls"><label><input data-manual-output type="checkbox"${s.output.manual_output_enabled ? " checked" : ""}>${label("manual")}</label><input data-output-path type="text" value="${escape(s.output.path)}" aria-label="${t.path}" placeholder="${s.output.manual_output_enabled ? t.customPath : t.autoPath}"${s.output.manual_output_enabled ? "" : " disabled"}><select data-codec aria-label="${t.codec}">${[["hevc10", "hevc"], ["prores", "prores"], ["ffv1", "ffv1"]].map(([v, k]) => `<option value="${v}" data-text="${k}"${s.output.codec === v ? " selected" : ""}>${t[k]}</option>`).join("")}</select><button class="cl-export" data-action="export" type="button" ${exportAction(s).reason ? "disabled" : ""} title="${escape(exportAction(s).title)}" aria-label="${escape(exportAction(s).label)}">${escape(exportAction(s).label)}</button><button data-action="cancel" type="button" hidden>${label("cancel")}</button></div></section><div class="cl-status nodrag" role="status" aria-live="polite"><span data-status>${t.ready}</span><progress data-progress max="1" value="0" hidden></progress><a data-result target="_blank" rel="noopener noreferrer" hidden>${t.result}</a></div></div>`;
}

// Manual texel fetch provides trilinear RGB32F on WebGL2 even without the float
// linear filtering extension. This samples the exact exported 33^3 LUT.
export const HMB_COLOR_LUT_FRAGMENT_SHADER = `#version 300 es
precision highp float;
precision highp sampler3D;
uniform sampler2D sourceVideo;
uniform sampler3D colorCube;
uniform int compareMode;
uniform float wipe;
in vec2 uv;
out vec4 result;
vec3 lookup(vec3 color){
  vec3 p=clamp(color,0.,1.)*32.; ivec3 lo=ivec3(floor(p)); ivec3 hi=min(lo+ivec3(1),ivec3(32)); vec3 f=fract(p);
  vec3 a=mix(texelFetch(colorCube,ivec3(lo.x,lo.y,lo.z),0).rgb,texelFetch(colorCube,ivec3(hi.x,lo.y,lo.z),0).rgb,f.x);
  vec3 b=mix(texelFetch(colorCube,ivec3(lo.x,hi.y,lo.z),0).rgb,texelFetch(colorCube,ivec3(hi.x,hi.y,lo.z),0).rgb,f.x);
  vec3 c=mix(texelFetch(colorCube,ivec3(lo.x,lo.y,hi.z),0).rgb,texelFetch(colorCube,ivec3(hi.x,lo.y,hi.z),0).rgb,f.x);
  vec3 d=mix(texelFetch(colorCube,ivec3(lo.x,hi.y,hi.z),0).rgb,texelFetch(colorCube,ivec3(hi.x,hi.y,hi.z),0).rgb,f.x);
  return mix(mix(a,b,f.y),mix(c,d,f.y),f.z);
}
void main(){vec3 color=texture(sourceVideo,uv).rgb;result=vec4(compareMode==0||(compareMode==1&&uv.x<wipe)?color:lookup(color),1.);}`;

function createRenderer(canvas) {
  const gl = canvas.getContext?.("webgl2", { alpha: false, antialias: false, preserveDrawingBuffer: false });
  if (gl) {
    const shaders = [], textures = []; let program;
    try {
      const compile = (kind, source) => {
        const shader = gl.createShader(kind); shaders.push(shader); gl.shaderSource(shader, source); gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader)); return shader;
      };
      program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, `#version 300 es\nout vec2 uv;void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0.,1.);}`));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, HMB_COLOR_LUT_FRAGMENT_SHADER)); gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
      const videoTexture = gl.createTexture(), cubeTexture = gl.createTexture(); textures.push(videoTexture, cubeTexture);
      gl.useProgram(program); gl.uniform1i(gl.getUniformLocation(program, "sourceVideo"), 0); gl.uniform1i(gl.getUniformLocation(program, "colorCube"), 1);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, videoTexture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, cubeTexture);
      for (const field of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, field, gl.NEAREST);
      for (const field of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, field, gl.CLAMP_TO_EDGE);
      const modeLocation = gl.getUniformLocation(program, "compareMode"), wipeLocation = gl.getUniformLocation(program, "wipe");
      if ("drawingBufferColorSpace" in gl) gl.drawingBufferColorSpace = "srgb";
      if ("unpackColorSpace" in gl) gl.unpackColorSpace = "srgb";
      return { maxWidth: 1280, setCube(cube) { gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false); gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, cubeTexture); gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGB32F, 33, 33, 33, 0, gl.RGB, gl.FLOAT, cube); },
        clear() { gl.clearColor(0.02, 0.03, 0.05, 1); gl.clear(gl.COLOR_BUFFER_BIT); },
        draw(video, mode, wipe) { gl.viewport(0, 0, canvas.width, canvas.height); gl.useProgram(program); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, videoTexture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, video); gl.uniform1i(modeLocation, mode); gl.uniform1f(wipeLocation, wipe); gl.drawArrays(gl.TRIANGLES, 0, 3); },
        dispose() { for (const texture of textures) gl.deleteTexture(texture); for (const shader of shaders) gl.deleteShader(shader); gl.deleteProgram(program); } };
    } catch (error) { for (const texture of textures) gl.deleteTexture(texture); for (const shader of shaders) gl.deleteShader(shader); if (program) gl.deleteProgram(program); throw error; }
  }
  const ctx = canvas.getContext?.("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("No canvas renderer available.");
  let cube;
  return { maxWidth: 640, setCube(value) { cube = value; }, clear() { ctx.clearRect(0, 0, canvas.width, canvas.height); },
    draw(video, mode, wipe) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      if (mode === 0 || !cube) return;
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height), d = pixels.data;
      hmbColorLUTGradePixels(d, canvas.width, cube, mode, wipe);
      ctx.putImageData(pixels, 0, 0);
    }, dispose() { cube = null; } };
}

function hmbNativeUiImplementation(container, props = {}) {
  if (!container) return { cleanup() {}, update() {} };
  if (container.__hmbColorLUTController) { container.__hmbColorLUTController.update(props); return container.__hmbColorLUTController; }
  let latestProps = props, state = hmbColorLUTState(props), disposed = false, visible = true, sourceRevision = 0;
  let renderer = null, video = null, sourceKey = "", drawFrame = 0, playbackFrame = 0, videoFrame = 0, commitTimer = 0;
  let mode = "compare", wipe = 0.5, cubeKey = "", pendingCube = null, pendingShot = null, localMessage = "", pendingEdit = false, lastSeek = 0, responseRevision = 0;
  let lastHostRevision = state.revision;
  const cleanups = [], videoCleanups = [], settingsCache = new Map(), cubeCache = new Map();
  const doc = container.ownerDocument || globalThis.document, win = doc?.defaultView || globalThis;
  const raf = (fn) => win.requestAnimationFrame(fn), caf = (id) => { if (id) win.cancelAnimationFrame(id); };
  const bind = (target, type, fn, options, list = cleanups) => { target?.addEventListener?.(type, fn, options); list.push(() => target?.removeEventListener?.(type, fn, options)); };
  const cacheKey = (s = state) => `${s.project_id}\u001f${s.shot.channel_uuid}\u001f${s.shot.shot_uuid}`;
  const shotKey = (s) => s.shot.shot_uuid
    ? `${s.shot.channel_uuid}\u001f${s.shot.shot_uuid}` : HMB_COLOR_LUT_ONLY_SHOT_VALUE;
  // Transport completions belong to the intent that created them, not merely
  // to a matching Project/Shot (which can leave and return before completion).
  const responseStateKey = () => JSON.stringify([state.revision, cacheKey(), state.settings, state.source, state.output, state.preset_name, state.preset_id, state.profiles, state.status, state.result, state.web_upload]);
  const acceptResponseState = (previousKey) => { if (responseStateKey() !== previousKey) responseRevision++; };
  const q = (selector) => container.querySelector?.(selector), all = (selector) => Array.from(container.querySelectorAll?.(selector) || []);
  const hadContainerNoDrag = container.classList?.contains?.("nodrag");
  container.innerHTML = hmbRenderColorLUTWidget(state); // The only mount: updates patch existing controls and preserve the canvas.
  container.classList?.add("nodrag"); container.setAttribute?.("data-hmb-node-delete-protected", "true");
  container.setAttribute?.("data-hmb-color-lut-widget", "");
  const root = q(".hmb-color-lut"), canvas = q("[data-preview]");
  const nativeHeaderTarget = target => Boolean(target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"));
  const announceNativeHeader = phase => {
    if (typeof win.CustomEvent === "function") doc?.dispatchEvent?.(new win.CustomEvent(`hmb-color-lut-header-${phase}`, { detail: { container } }));
  };
  bind(container, "hmb-color-lut-header-state", event => {
    if (disposed || event.target !== container) return;
    const active = event.detail?.active === true;
    root?.setAttribute("data-hmb-native-header", active ? "active" : "fallback");
    root?.classList.toggle("nodrag", !active);
    container.classList?.toggle("nodrag", !active);
  });
  const canDraw = () => !disposed && visible && !doc?.hidden;
  const say = (message) => { localMessage = String(message || ""); if (q("[data-status]")) q("[data-status]").textContent = localMessage || state.status.message || textFor(state).ready; };
  const updateFrameLabel = () => {
    const fps = state.source.fps || 24, duration = Number.isFinite(video?.duration) ? video.duration : state.source.duration || 0;
    const total = Math.max(1, Math.ceil(duration * fps)), frame = Math.min(total - 1, Math.max(0, Math.round((video?.currentTime || 0) * fps)));
    const seek = q("[data-seek]"); if (seek) { seek.max = String(total - 1); seek.value = String(frame); seek.disabled = !video || video.readyState < 2; }
    if (q("[data-frame]")) q("[data-frame]").textContent = `${textFor(state).frame} ${frame + 1} / ${total} · ${Math.round(fps * 1000) / 1000} FPS`;
    if (q("[data-play]")) { q("[data-play]").textContent = video && !video.paused ? textFor(state).pause : textFor(state).play; q("[data-play]").disabled = !video || video.readyState < 2; }
    if (q("[data-step]")) q("[data-step]").disabled = !video || video.readyState < 2;
  };
  const stopLoop = () => { caf(playbackFrame); playbackFrame = 0; if (videoFrame && video?.cancelVideoFrameCallback) video.cancelVideoFrameCallback(videoFrame); videoFrame = 0; };
  const pause = () => { stopLoop(); video?.pause?.(); updateFrameLabel(); };
  const cancelPendingCube = () => { pendingCube?.cancel(); pendingCube = null; };
  const installCube = (key, cube) => {
    cancelPendingCube(); renderer.setCube(cube); cubeKey = key;
    cubeCache.delete(key); cubeCache.set(key, cube);
    if (cubeCache.size > 4) cubeCache.delete(cubeCache.keys().next().value);
  };
  const draw = () => {
    drawFrame = 0;
    if (!canDraw() || !renderer || !video || video.readyState < 2) return;
    try {
      const key = JSON.stringify(state.settings);
      if (key === cubeKey && pendingCube) cancelPendingCube();
      if (key !== cubeKey) {
        if (cubeCache.has(key)) installCube(key, cubeCache.get(key));
        else if (!cubeKey) installCube(key, hmbColorLUTCube(state.settings));
        else if (pendingCube?.key !== key) {
          cancelPendingCube();
          const requested = { key, cancel: null };
          requested.cancel = hmbColorLUTCubeChunked(state.settings,
            (fn) => win.setTimeout(fn, 0), (ticket) => win.clearTimeout(ticket),
            (cube) => {
              if (disposed || pendingCube !== requested || key !== JSON.stringify(state.settings) || !renderer) return;
              installCube(key, cube); queueDraw();
            });
          pendingCube = requested;
        }
      }
      const ratio = Math.min(1, renderer.maxWidth / Math.max(1, video.videoWidth)), width = Math.max(1, Math.round(video.videoWidth * ratio)), height = Math.max(1, Math.round(video.videoHeight * ratio));
      if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
      renderer.draw(video, mode === "original" ? 0 : mode === "compare" ? 1 : 2, wipe); updateFrameLabel();
    } catch (error) { pause(); say(`${textFor(state).previewError}: ${error.message || error}`); }
  };
  const queueDraw = () => { if (canDraw() && !drawFrame) drawFrame = raf(draw); };
  const playLoop = () => {
    if (!canDraw() || !video || video.paused || video.ended || videoFrame || playbackFrame) return;
    const ownedVideo = video, token = sourceRevision;
    if (video.requestVideoFrameCallback) videoFrame = video.requestVideoFrameCallback(() => {
      videoFrame = 0; if (disposed || token !== sourceRevision || video !== ownedVideo) return; queueDraw(); playLoop();
    });
    else playbackFrame = raf(() => { playbackFrame = 0; if (disposed || token !== sourceRevision || video !== ownedVideo) return; queueDraw(); playLoop(); });
  };
  const clearVideo = () => {
    sourceRevision++; stopLoop(); caf(drawFrame); drawFrame = 0; cancelPendingCube();
    for (const cleanup of videoCleanups.splice(0)) cleanup();
    if (video) { video.pause(); video.removeAttribute("src"); video.load(); video = null; }
    renderer?.clear(); updateFrameLabel();
  };
  const loadSource = () => {
    const s = state.source, nextKey = JSON.stringify([state.shot.channel_uuid, state.shot.shot_uuid, s.path || "", s.url || "", s.revision || ""]);
    if (nextKey === sourceKey) return;
    sourceKey = nextKey; clearVideo(); const url = clean(s.url);
    q("[data-empty]").hidden = false; q("[data-empty]").textContent = url ? textFor(state).loading : textFor(state).empty;
    if (!url) return; // Local filesystem paths must be served by the backend's media URL transport.
    const candidate = doc.createElement("video"), token = sourceRevision;
    video = candidate; candidate.preload = "auto"; candidate.muted = true; candidate.playsInline = true; candidate.crossOrigin = "anonymous";
    const current = () => !disposed && token === sourceRevision && candidate === video;
    bind(candidate, "loadeddata", () => { if (!current()) return; q("[data-empty]").hidden = true; localMessage = ""; updateFrameLabel(); queueDraw(); }, undefined, videoCleanups);
    bind(candidate, "loadedmetadata", () => { if (current()) updateFrameLabel(); }, undefined, videoCleanups);
    bind(candidate, "seeked", () => { if (current()) { updateFrameLabel(); queueDraw(); } }, undefined, videoCleanups);
    bind(candidate, "play", () => { if (current()) { updateFrameLabel(); playLoop(); } }, undefined, videoCleanups);
    bind(candidate, "pause", () => { if (current()) { stopLoop(); updateFrameLabel(); queueDraw(); } }, undefined, videoCleanups);
    bind(candidate, "ended", () => { if (current()) { stopLoop(); updateFrameLabel(); queueDraw(); } }, undefined, videoCleanups);
    bind(candidate, "error", () => { if (current()) { pause(); q("[data-empty]").hidden = false; q("[data-empty]").textContent = textFor(state).sourceError; say(textFor(state).sourceError); } }, undefined, videoCleanups);
    candidate.src = url; candidate.load();
  };
  const sync = () => {
    if (disposed) return;
    const t = textFor(state), accent = hmbColorLUTShotAccent(state), busy = state.web_upload.phase === "uploading" || ["working", "busy", "exporting", "running", "probing", "encoding", "cancelling"].includes(state.status.phase);
    root.style.setProperty("--cl-accent", accent); root.style.setProperty("--cl-rgb", accent.slice(1).match(/../g).map((x) => parseInt(x, 16)).join(","));
    root.setAttribute("data-language", state.language); root.setAttribute("data-shot-number", String(hmbColorLUTShotOptions(state).find((s) => s.selected)?.number || 0));
    for (const el of all("[data-text]")) el.textContent = t[el.getAttribute("data-text")] || "";
    for (const el of all("[data-low]")) el.textContent = t.low[Number(el.getAttribute("data-low"))];
    for (const el of all("[data-high]")) el.textContent = t.high[Number(el.getAttribute("data-high"))];
    const shot = q("[data-shot-selector]"), options = shotMarkup(state); if (shot.innerHTML !== options) shot.innerHTML = options;
    shot.value = hmbColorLUTShotOptions(state).find((s) => s.selected)?.key || HMB_COLOR_LUT_ONLY_SHOT_VALUE; shot.setAttribute("aria-label", t.shot);
    q("[data-language-toggle]").textContent = state.language === "ko" ? "한국어" : "EN"; q("[data-language-toggle]").setAttribute("aria-label", t.language);
    q("[data-source]").textContent = state.source.name || (state.shot.shot_uuid ? `${state.shot.name}` : t.standalone);
    q("[data-source-revision]").textContent = `${state.source.revision ? `r${state.source.revision} · ` : ""}${state.shot.shot_uuid ? t.bound : t.unbound}`;
    q('[data-action="browse_video"]').hidden = Boolean(state.shot.shot_uuid);
    q("[data-enable]").checked = state.settings.enabled;
    for (const key of HMB_COLOR_LUT_CONTROLS) { const el = q(`[data-adjust="${key}"]`); el.value = String(sliderStep(state.settings[key])); el.setAttribute("aria-valuetext", stageLabel(state, key)); el.setAttribute("aria-label", t[key]); q(`[data-value="${key}"]`).textContent = stageLabel(state, key); }
    const project = q("[data-project]");
    const boundProject = Boolean(state.shot.shot_uuid);
    const manual = state.manual_project;
    const projectMarkup = boundProject ? `<option value="${escape(state.project_id)}">${escape(state.project.name || "—")}</option>`
      : `<option value="">—</option>${manual.id && !state.upload_projects.some(p => p.id === manual.id) ? `<option value="${escape(manual.id)}" disabled>${escape(manual.name)}</option>` : ""}${state.upload_projects.map(p => `<option value="${escape(p.id)}">${escape(p.name)}</option>`).join("")}`;
    if (project.innerHTML !== projectMarkup) project.innerHTML = projectMarkup;
    project.value = boundProject ? state.project_id : manual.id || "";
    project.disabled = boundProject || busy || state.web_upload.phase === "uploading";
    if (doc.activeElement !== q("[data-profile-name]")) q("[data-profile-name]").value = state.preset_name;
    const presets = q("[data-presets]");
    const presetOptions = state.profiles.filter((p) => p.project_id === state.project_id).map((p) => `<option value="${escape(p.name)}"></option>`).join("");
    if (presets.innerHTML !== presetOptions) presets.innerHTML = presetOptions;
    const deleteProfile = q('[data-action="delete_profile"]'); deleteProfile.disabled = busy || !hmbColorLUTCanDeleteProfile(state); deleteProfile.title = t.deleteProfileHint;
    q("[data-preview-note]").textContent = state.settings.enabled ? t.enabled : t.disabled;
    q("[data-manual-output]").checked = state.output.manual_output_enabled;
    const path = q("[data-output-path]"); path.disabled = !state.output.manual_output_enabled; path.placeholder = state.output.manual_output_enabled ? t.customPath : t.autoPath; path.setAttribute("aria-label", t.path); if (doc.activeElement !== path) path.value = state.output.path;
    q("[data-codec]").value = state.output.codec; q("[data-codec]").setAttribute("aria-label", t.codec);
    const exportMode = exportAction(state);
    const exportButton = q('[data-action="export"]'); exportButton.disabled = busy || Boolean(exportMode.reason);
    exportButton.textContent = exportMode.label;
    exportButton.title = exportMode.title; exportButton.setAttribute("aria-label", exportMode.label); q('[data-action="cancel"]').hidden = !busy;
    const upload = q('[data-action="upload_web"]'); upload.disabled = busy || !state.web_upload.enabled; upload.title = state.web_upload.reason; upload.textContent = state.web_upload.phase === "uploading" ? t.uploading : state.web_upload.phase === "complete" ? t.uploaded : state.web_upload.phase === "unknown" ? t.uploadCheck : t.upload; q("[data-upload-reason]").textContent = state.web_upload.reason;
    q("[data-progress]").hidden = !busy; q("[data-progress]").value = state.status.progress;
    q("[data-status]").textContent = localMessage || state.status.message || t.ready;
    const result = q("[data-result]"); result.textContent = t.result; result.hidden = !state.result.url; if (state.result.url && /^(https?:|blob:|\/)/i.test(state.result.url)) result.href = state.result.url; else { result.removeAttribute("href"); result.hidden = true; }
    for (const key of ["seek"]) q(`[data-${key}]`).setAttribute("aria-label", t[key]); canvas.setAttribute("aria-label", t.preview);
    q(".cl-before").hidden = mode === "graded"; q(".cl-after").hidden = mode === "original"; q(".cl-seam").hidden = mode !== "compare"; q(".cl-seam").style.left = `${wipe * 100}%`;
    for (const button of all("[data-view]")) button.setAttribute("aria-pressed", String(button.getAttribute("data-view") === mode));
    loadSource(); if (!video) q("[data-empty]").textContent = t.empty; else if (video.readyState < 2 && !video.error) q("[data-empty]").textContent = t.loading;
    updateFrameLabel(); queueDraw();
  };
  const publish = (shotSelection = false) => {
    if (commitTimer) { win.clearTimeout(commitTimer); commitTimer = 0; }
    if (disposed) return false;
    pendingEdit = false; if (!shotSelection) invalidateUpload(); state.revision++; settingsCache.set(cacheKey(), copy(state.settings));
    const token = ++responseRevision, current = () => !disposed && token === responseRevision;
    if (typeof latestProps.onChange !== "function") { if (shotSelection) pendingShot = null; say(textFor(state).transportError); return false; }
    const captured = copy(state);
    const shotRequest = shotSelection ? pendingShot : null;
    try { Promise.resolve(latestProps.onChange(captured)).catch((error) => { if (current()) { if (shotRequest && pendingShot === shotRequest) pendingShot = null; say(`${textFor(state).transportError}: ${error.message || error}`); } }); return true; }
    catch (error) { if (current()) { if (shotRequest && pendingShot === shotRequest) pendingShot = null; say(`${textFor(state).transportError}: ${error.message || error}`); } return false; }
  };
  const invalidateUpload = () => { state.web_upload.enabled = false; const button = q('[data-action="upload_web"]'); if (button) button.disabled = true; };
  const scheduleCommit = () => { invalidateUpload(); responseRevision++; pendingEdit = true; if (commitTimer) win.clearTimeout(commitTimer); commitTimer = win.setTimeout(publish, 180); };
  const command = (action, extra = {}) => {
    if (action === "export") {
      const mode = exportAction(state);
      if (mode.reason) { say(mode.reason); return; }
      action = mode.action;
    }
    if (action === "delete_profile" && !hmbColorLUTCanDeleteProfile(state)) return;
    if (action === "upload_web" && !state.web_upload.enabled) return;
    if (action === "upload_web") { state.web_upload.enabled = false; state.web_upload.phase = "uploading"; }
    if (commitTimer) { win.clearTimeout(commitTimer); commitTimer = 0; } pendingEdit = false;
    state.output.path = clean(q("[data-output-path]").value);
    const authoredPresetName = clean(q("[data-profile-name]").value, 80);
    if (authoredPresetName !== state.preset_name) state.preset_id = "";
    state.preset_name = authoredPresetName;
    if (action === "delete_profile" && !hmbColorLUTCanDeleteProfile(state)) { sync(); return; }
    const quiet = action === "refresh_upload_projects";
    if (!quiet) state.revision++; settingsCache.set(cacheKey(), copy(state.settings)); const captured = copy(state), request = { ...hmbColorLUTCommand(action, captured), ...extra };
    const token = ++responseRevision, current = () => !disposed && token === responseRevision;
    try {
      let result;
      if (typeof latestProps.onCommand === "function") result = latestProps.onCommand(JSON.stringify(request));
      else if (typeof latestProps.onChange === "function") result = latestProps.onChange({ ...captured, [HMB_COLOR_LUT_COMMAND_FIELD]: request });
      else throw new Error(textFor(state).transportError);
      if (current()) { if (!quiet) say(textFor(state).pending); sync(); }
      Promise.resolve(result).catch((error) => { if (current()) say(`${textFor(state).commandError}: ${error.message || error}`); });
    } catch (error) { if (current()) say(`${textFor(state).commandError}: ${error.message || error}`); }
  };
  const switchContext = (mutate) => {
    if (pendingEdit) publish(); settingsCache.set(cacheKey(), copy(state.settings)); pause();
    const previousKey = shotKey(state);
    mutate();
    const blockedKeys = new Set(pendingShot?.blockedKeys || []);
    blockedKeys.add(previousKey);
    pendingShot = { targetKey: shotKey(state), blockedKeys };
    state.settings = copy(settingsCache.get(cacheKey()) || hmbColorLUTSettings()); state.source = {}; state.result = {}; state.web_upload = { enabled: false, phase: "unavailable", reason: "" }; localMessage = ""; publish(true); sync();
  };
  bind(q("[data-shot-selector]"), "change", (event) => { const option = hmbColorLUTShotOptions(state).find((s) => s.key === event.target.value); if (option) switchContext(() => { state.shot = option.only ? onlyShot() : { channel_uuid: option.channel_uuid, shot_uuid: option.shot_uuid, number: option.number, name: option.name }; }); });
  bind(q("[data-project]"), "change", (event) => { if (!state.shot.shot_uuid && event.target.value !== (state.manual_project.id || "")) { invalidateUpload(); command("select_upload_project", { project_id: clean(event.target.value, 128) }); } });
  bind(q("[data-project]"), "focus", () => { if (!state.shot.shot_uuid) command("refresh_upload_projects"); });
  bind(q("[data-profile-name]"), "change", (event) => { state.preset_name = clean(event.target.value, 80); const matches = state.profiles.filter((profile) => profile.project_id === state.project_id && profile.name === state.preset_name); state.preset_id = matches.length === 1 ? matches[0].id : ""; publish(); sync(); });
  bind(q("[data-language-toggle]"), "click", () => { state.language = state.language === "ko" ? "en" : "ko"; localMessage = ""; publish(); sync(); });
  bind(q("[data-enable]"), "change", (event) => { state.settings.enabled = event.target.checked; publish(); sync(); });
  for (const el of all("[data-adjust]")) {
    bind(el, "input", () => { const key = el.getAttribute("data-adjust"); state.settings[key] = hmbColorLUTStrengthFromStep(el.value); el.value = String(sliderStep(state.settings[key])); state.settings.enabled = true; q("[data-enable]").checked = true; el.setAttribute("aria-valuetext", stageLabel(state, key)); q(`[data-value="${key}"]`).textContent = stageLabel(state, key); q("[data-preview-note]").textContent = textFor(state).enabled; queueDraw(); scheduleCommit(); });
    bind(el, "change", () => { if (pendingEdit) publish(); });
  }
  bind(q("[data-reset]"), "click", () => { state.settings = hmbColorLUTSettings(); publish(); sync(); });
  bind(q("[data-apply-profile]"), "click", () => { const preset = hmbColorLUTSelectedProfile(state) || state.profiles.find((p) => p.project_id === state.project_id && p.name === state.preset_name); if (preset) { state.settings = copy(preset.settings); state.preset_id = preset.id; publish(); sync(); } });
  bind(q("[data-manual-output]"), "change", (event) => { state.output.manual_output_enabled = event.target.checked; publish(); sync(); });
  bind(q("[data-output-path]"), "change", (event) => { state.output.path = clean(event.target.value); publish(); });
  bind(q("[data-codec]"), "change", (event) => { state.output.codec = event.target.value; publish(); sync(); });
  for (const button of all("[data-action]")) bind(button, "click", () => command(button.getAttribute("data-action")));
  for (const button of all("[data-view]")) bind(button, "click", () => { mode = button.getAttribute("data-view"); sync(); });
  const handle = q("[data-wipe-handle]");
  let wipePointer = null;
  const setWipe = (position) => { wipe = clamp(position); q(".cl-seam").style.left = `${wipe * 100}%`; handle.setAttribute("aria-valuenow", String(Math.round(wipe * 100))); queueDraw(); };
  const dragWipe = (event) => { const box = q(".cl-screen").getBoundingClientRect(); if (box.width) setWipe((event.clientX - box.left) / box.width); event.preventDefault(); event.stopPropagation(); };
  bind(handle, "pointerdown", (event) => { if (event.button !== 0) return; wipePointer = event.pointerId; handle.setPointerCapture?.(wipePointer); dragWipe(event); });
  bind(handle, "pointermove", (event) => { if (event.pointerId === wipePointer) dragWipe(event); });
  const endWipe = (event) => { if (event.pointerId !== wipePointer) return; const id = wipePointer; wipePointer = null; if (handle.hasPointerCapture?.(id)) handle.releasePointerCapture(id); event.stopPropagation(); };
  bind(handle, "pointerup", endWipe); bind(handle, "pointercancel", endWipe); bind(handle, "lostpointercapture", endWipe);
  bind(handle, "keydown", (event) => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); event.stopPropagation(); setWipe(event.key === "Home" ? 0 : event.key === "End" ? 1 : wipe + (event.key === "ArrowRight" ? .01 : -.01)); } });
  const seekTo = (frame) => { if (!video || video.readyState < 2) return; pause(); const fps = state.source.fps || 24, duration = Number.isFinite(video.duration) ? video.duration : state.source.duration; lastSeek = clamp(frame / fps, 0, Math.max(0, duration - 1 / fps)); video.currentTime = lastSeek; updateFrameLabel(); };
  bind(q("[data-seek]"), "input", (event) => seekTo(finite(event.target.value)));
  bind(q("[data-step]"), "click", () => seekTo(Math.floor((video?.currentTime || lastSeek) * (state.source.fps || 24) + 0.001) + 1));
  bind(q("[data-play]"), "click", () => { if (!video) return; if (!video.paused) pause(); else { if (video.ended) video.currentTime = 0; const owned = video, token = sourceRevision; Promise.resolve(video.play()).then(() => { if (disposed || owned !== video || token !== sourceRevision) { owned.pause(); return; } updateFrameLabel(); playLoop(); }).catch((error) => { if (token === sourceRevision) say(error.message || error); }); } });
  bind(doc, "visibilitychange", () => { if (doc.hidden) { pause(); caf(drawFrame); drawFrame = 0; cancelPendingCube(); } else queueDraw(); });
  bind(container, "pointerdown", (event) => { if (!nativeHeaderTarget(event.target) && event.target?.closest?.("button,input,select,a")) event.stopPropagation?.(); });
  bind(container, "keydown", (event) => { if (!nativeHeaderTarget(event.target) && (["Backspace", "Delete"].includes(event.key) || event.target?.closest?.("button,input,select"))) event.stopPropagation?.(); });
  bind(canvas, "webglcontextlost", (event) => { event.preventDefault(); pause(); cancelPendingCube(); renderer?.dispose(); renderer = null; say(textFor(state).previewError); });
  bind(canvas, "webglcontextrestored", () => { try { renderer = createRenderer(canvas); cubeKey = ""; queueDraw(); } catch (error) { say(error.message || error); } });
  let observer = null;
  if (typeof win.IntersectionObserver === "function") { observer = new win.IntersectionObserver((entries) => { visible = entries.some((entry) => entry.isIntersecting); if (!visible) { pause(); caf(drawFrame); drawFrame = 0; cancelPendingCube(); } else queueDraw(); }); observer.observe(container); }
  try { renderer = createRenderer(canvas); } catch (error) { say(`${textFor(state).previewError}: ${error.message || error}`); }
  const presetListId = `cl-presets-${Math.random().toString(36).slice(2)}`;
  q("[data-presets]").id = presetListId; q("[data-profile-name]").setAttribute("list", presetListId);
  const controller = {
    update(nextProps = {}) {
      if (disposed) return;
      latestProps = nextProps; const incoming = hmbColorLUTState(nextProps), sameShot = incoming.shot.channel_uuid === state.shot.channel_uuid && incoming.shot.shot_uuid === state.shot.shot_uuid;
      const previousResponseState = responseStateKey();
      if (incoming.project_id !== state.project_id) {
        // Project selection belongs to ImageAsset. A local slider revision may
        // run ahead while its debounce is pending, so compare host revisions
        // separately and retire the old project's timer before adopting it.
        if (incoming.revision <= lastHostRevision) return;
        lastHostRevision = incoming.revision;
        if (commitTimer) { win.clearTimeout(commitTimer); commitTimer = 0; }
        pendingEdit = false; pendingShot = null;
        settingsCache.set(cacheKey(), copy(state.settings)); pause();
        state = incoming; settingsCache.set(cacheKey(), copy(state.settings));
        localMessage = ""; acceptResponseState(previousResponseState); sync(); return;
      }
      lastHostRevision = Math.max(lastHostRevision, incoming.revision);
      const editedShotRemoved = pendingEdit && state.shot.shot_uuid
        && Number(incoming.shot_catalog.generation || 0) > Number(state.shot_catalog.generation || 0)
        && !(incoming.shot_catalog.shots || []).some(shot =>
          incoming.shot_catalog.channel_uuid === state.shot.channel_uuid && shot.shot_uuid === state.shot.shot_uuid);
      if (editedShotRemoved) {
        // The displayed fallback may already be Only while a debounce still
        // owns the deleted Shot. Retire that edit before accepting the catalog.
        if (commitTimer) { win.clearTimeout(commitTimer); commitTimer = 0; }
        pendingEdit = false; pendingShot = null;
        settingsCache.set(cacheKey(), copy(state.settings)); pause();
        state = incoming; settingsCache.set(cacheKey(), copy(state.settings));
        localMessage = ""; acceptResponseState(previousResponseState); sync(); return;
      }
      if (pendingShot) {
        const incomingKey = shotKey(incoming);
        if (incomingKey === pendingShot.targetKey) pendingShot = null;
        else {
          const targetAvailable = pendingShot.targetKey === HMB_COLOR_LUT_ONLY_SHOT_VALUE
            || (incoming.shot_catalog.shots || []).some(
              (shot) => `${incoming.shot_catalog.channel_uuid}\u001f${shot.shot_uuid}` === pendingShot.targetKey,
            );
          const catalogAdvanced = Number(incoming.shot_catalog.generation || 0) > Number(state.shot_catalog.generation || 0);
          if (!targetAvailable && catalogAdvanced) {
            pendingShot = null;
            settingsCache.set(cacheKey(), copy(state.settings)); state = incoming; settingsCache.set(cacheKey(), copy(state.settings));
            acceptResponseState(previousResponseState);
            sync(); return;
          }
          if (pendingShot.blockedKeys.has(incomingKey)) {
            if (catalogAdvanced) state.shot_catalog = incoming.shot_catalog;
            sync(); return;
          }
          pendingShot = null;
        }
      }
      if (incoming.revision < state.revision || pendingEdit) {
        // Host echoes can arrive after a newer local drag/shot selection. Preserve authored data.
        if (sameShot && incoming.revision >= state.revision) { state.source = incoming.source; state.status = incoming.status; state.result = incoming.result; state.revision = incoming.revision; }
        if (incoming.shot_catalog.generation >= (state.shot_catalog.generation || 0)) state.shot_catalog = incoming.shot_catalog;
      } else { settingsCache.set(cacheKey(), copy(state.settings)); state = incoming; settingsCache.set(cacheKey(), copy(state.settings)); }
      acceptResponseState(previousResponseState);
      if (state.status.message || state.status.phase !== "idle") localMessage = "";
      sync();
    },
    cleanup() {
      if (disposed) return;
      announceNativeHeader("retire");
      if (pendingEdit) publish(); disposed = true; responseRevision++;
      pendingShot = null;
      if (commitTimer) win.clearTimeout(commitTimer); clearVideo(); observer?.disconnect();
      cancelPendingCube(); for (const cleanup of cleanups.splice(0)) cleanup(); renderer?.dispose(); renderer = null; settingsCache.clear(); cubeCache.clear();
      container.innerHTML = "";
      if (hadContainerNoDrag) container.classList?.add("nodrag"); else container.classList?.remove("nodrag");
      container.removeAttribute?.("data-hmb-node-delete-protected");
      container.removeAttribute?.("data-hmb-color-lut-widget");
      if (container.__hmbColorLUTController === controller) delete container.__hmbColorLUTController;
    },
  };
  container.__hmbColorLUTController = controller; sync(); announceNativeHeader("ready"); return controller;
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

export default function HMBColorLUTLibraryWidget(container, props) {
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "lut", allowControl: target => Boolean(target?.closest?.("[data-play],[data-step],[data-seek],[data-view],[data-wipe-handle],[data-action='cancel'],[data-hmb-native-identity],[data-hmb-native-actions]")) });
}
