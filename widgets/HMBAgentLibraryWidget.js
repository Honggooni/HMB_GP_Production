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

function hmbAgentEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

function hmbAgentCatalog(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
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
  for (const raw of source.shots) {
    const shotUuid = String(raw?.shot_uuid || "").trim().slice(0, 128);
    const number = Number(raw?.number);
    const name = String(raw?.name || "").trim().replace(/\s+/g, " ").slice(0, 128);
    const revision = Number(raw?.revision);
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

export function hmbAgentState(props) {
  const raw = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  const state = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const shot = state.shot && typeof state.shot === "object" ? state.shot : {};
  const shotUuid = String(shot.shot_uuid || "").trim().slice(0, 128);
  const channelUuid = String(shot.channel_uuid || "").trim().slice(0, 128);
  const bound = Boolean(shotUuid && channelUuid);
  const catalog = hmbAgentCatalog(state.shot_catalog);
  const manualRaw=state.manual_rebind && typeof state.manual_rebind==="object" ? state.manual_rebind : {};
  const manual=/^[0-9a-f]{64}$/.test(String(manualRaw.expected_source_digest || "")) ? {
    required:manualRaw.required===true,status:String(manualRaw.status || ""),reason:String(manualRaw.reason || ""),
    error:String(manualRaw.error || ""),request_id:String(manualRaw.request_id || ""),
    source_node_name:String(manualRaw.source_node_name || ""),backup_path:String(manualRaw.backup_path || ""),
    expected_source_digest:String(manualRaw.expected_source_digest)} : null;
  const catalogMatchesChannel = manual?.required || !bound || catalog.channel_uuid === channelUuid;
  const selected = bound && catalogMatchesChannel
    ? (catalog.shots || []).find((item) => item.shot_uuid === shotUuid) || null
    : null;
  const executionPhase = ["authorizing", "preparing", "running"].includes(
    String(state.execution_phase || "").trim().toLowerCase(),
  ) ? String(state.execution_phase).trim().toLowerCase() : "";
  return {
    schema: "hmb-agent-ui", schema_version: 2, native_agent: true,
    policy_vault: "sealed", policy_injection: "runtime_only", output_sanitizer: true,
    execution_phase: executionPhase,
    shot_manager: true,
    shot_editor_expanded: state.shot_editor_expanded !== false,
    shot_states: Object.fromEntries(Object.entries(state.shot_states || {}).filter(([, value]) => ["running", "succeeded", "failed", "cancelled"].includes(value))),
    shot_catalog: catalogMatchesChannel ? catalog : {},
    ...(manual ? {manual_rebind:manual} : {}),
    shot: {
      channel_uuid: selected ? channelUuid : "",
      shot_uuid: selected ? selected.shot_uuid : "",
      number: selected ? selected.number : 1,
      name: selected ? selected.name : "샷 선택",
    },
  };
}

export function hmbAgentShotOptions(state) {
  const catalog = state?.shot_catalog && typeof state.shot_catalog === "object"
    ? state.shot_catalog : {};
  const options = [];
  // This bounded catalog arrived in widget props only after Python reconciled
  // the exact same-flow publisher. Process-global browser events are never an
  // option source and can therefore not cross-adopt a cloned Flow.
  if (
    catalog.channel_uuid
    && (!state.shot.channel_uuid || catalog.channel_uuid === state.shot.channel_uuid)
  ) {
    for (const shot of catalog.shots || []) {
      options.push({ key: `${catalog.channel_uuid}\u001f${shot.shot_uuid}`, channel_uuid: catalog.channel_uuid, ...shot, only: false });
    }
  }
  return options;
}

export const HMB_JEWEL_NIGHT_SHOT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});

export function hmbAgentPaletteShotNumber(state) {
  const current = state?.shot && typeof state.shot === "object" ? state.shot : {};
  const catalog = state?.shot_catalog && typeof state.shot_catalog === "object"
    ? state.shot_catalog : {};
  if (!current.channel_uuid || !current.shot_uuid || catalog.channel_uuid !== current.channel_uuid) return 1;
  const exact = (catalog.shots || []).find((shot) => (
    shot.shot_uuid === current.shot_uuid && shot.number === current.number
  ));
  return exact && HMB_JEWEL_NIGHT_SHOT_PALETTE[exact.number] ? exact.number : 1;
}

export function hmbAgentShotAccent(state) {
  return HMB_JEWEL_NIGHT_SHOT_PALETTE[hmbAgentPaletteShotNumber(state)];
}

function hmbAgentShotOptionLabel(item) {
  return item.only
    ? "Only"
    : `${String(item.number).padStart(2, "0")} · ${item.name || `Shot ${item.number}`}`;
}

function hmbAgentShotOptionsMarkup(state) {
  const options = hmbAgentShotOptions(state);
  const current = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}`
    : "__hmb_only__";
  return options.map((item) => {
    const label = hmbAgentShotOptionLabel(item);
    return `<option value="${hmbAgentEscape(item.key)}"${item.key === current ? " selected" : ""}>${hmbAgentEscape(label)}</option>`;
  }).join("");
}

export function hmbSyncAgentShotSelect(select, state) {
  if (!select) return false;
  const desired = hmbAgentShotOptions(state).map((item) => ({
    value: item.key,
    label: hmbAgentShotOptionLabel(item),
  }));
  const current = Array.from(select.options || []);
  const changed = current.length !== desired.length || desired.some((item, index) => {
    const option = current[index];
    return !option
      || String(option.value) !== item.value
      || String(option.textContent ?? option.text ?? "") !== item.label;
  });
  if (changed) select.innerHTML = hmbAgentShotOptionsMarkup(state);
  const expected = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}`
    : "__hmb_only__";
  if (String(select.value || "") !== expected) select.value = expected;
  return changed;
}

function hmbAgentSetAttribute(element, name, value) {
  if (element?.getAttribute?.(name) !== String(value)) element?.setAttribute?.(name, String(value));
}

function hmbSetAgentStatus(container, message = "", detail = "") {
  const status = container?.querySelector?.(".agent-publication-status");
  if (!status) return false;
  const nextText = String(message || "");
  if (status.textContent !== nextText) status.textContent = nextText;
  hmbAgentSetAttribute(status, "title", message ? String(detail?.message || detail || message) : "");
  return true;
}

function hmbAgentExecutionStatus(phase) {
  return ({
    authorizing: "정책 확인 중…",
    preparing: "프롬프트 준비 중…",
    running: "Agent 실행 중…",
  })[String(phase || "")] || "";
}

export function hmbAgentWidgetHeight(state) { return state?.manual_rebind?.required ? 144 : 64; }

function hmbAgentRows(state) {
  if (!state.shot_manager) return "";
  const shots = state.shot_catalog.shots || [];
  if (!shots.length) return '<div class="agent-shot-empty">ImageAsset에서 샷을 추가하세요.</div>';
  return shots.map((shot) => {
    const selected = shot.shot_uuid === state.shot.shot_uuid;
    const status = state.shot_states[shot.shot_uuid] || "";
    const running = status === "running";
    return `<div class="agent-shot-row" data-shot-number="${shot.number}" data-active="${selected}" data-agent-row="${hmbAgentEscape(shot.shot_uuid)}">
      <button type="button" class="agent-shot-tab nodrag" data-agent-select="${hmbAgentEscape(shot.shot_uuid)}" aria-pressed="${selected}"><span class="agent-row-number">${String(shot.number).padStart(2, "0")}</span><b>${hmbAgentEscape(shot.name)}</b><span class="agent-row-status">${({running:"Agent 실행 중…",succeeded:"완료",failed:"실패",cancelled:"취소"})[status] || ""}</span></button>
      <button type="button" class="agent-shot-run nodrag" data-agent-run="${hmbAgentEscape(shot.shot_uuid)}" title="${running ? "이 샷 Agent만 취소" : "이 샷 Agent만 실행"}" aria-label="${running ? "Cancel Shot Agent" : "Run Shot Agent"}">${running ? "■" : "▷"}</button>
    </div>`;
  }).join("");
}

function renderAgentDashboard(state, container) {
  const paletteShotNumber = hmbAgentDisplayShotNumber(container, state);
  const executionStatus = hmbAgentExecutionStatus(state.execution_phase);
  const height = hmbAgentWidgetHeight(state);
  return `
    <style>
      .hmb-agent-dashboard :is(button,input,select,textarea):not([data-hmb-native-identity] *):not([data-hmb-native-actions] *){font-family:inherit}
      .hmb-agent-dashboard{--hmb-shot-accent:#F472B6;--hmb-shot-rgb:244,114,182;--hmb-shot-deep:#BE185D;--hmb-shot-soft:#FBCFE8;--hmb-shot-line:rgba(244,114,182,.48);--hmb-shot-glow:rgba(244,114,182,.2);--hmb-bg-top:#0b1020;--hmb-bg-bottom:#060912;--hmb-line:var(--hmb-shot-line);--hmb-accent:var(--hmb-shot-accent);--hmb-highlight:var(--hmb-shot-soft);--hmb-text:#e6edf7;--hmb-muted:#8fa3b8;--hmb-haze:var(--hmb-shot-glow);--hmb-head-wash:rgba(var(--hmb-shot-rgb),.22);--hmb-mark-bg:rgba(var(--hmb-shot-rgb),.12);--hmb-mark-line:var(--hmb-shot-line);--hmb-mark-glow:var(--hmb-shot-glow);--hmb-chip-bg:rgba(var(--hmb-shot-rgb),.18);--hmb-chip-line:var(--hmb-shot-line);--hmb-chip-text:var(--hmb-shot-soft);--hmb-chip-glow:var(--hmb-shot-glow);--hmb-status-error:#FB7185;--hmb-status-warning:#FBBF24;--hmb-status-success:#34D399;container-type:inline-size;position:relative;width:100%;height:64px;overflow:hidden;border:1px solid var(--hmb-line);border-radius:11px;background:radial-gradient(circle at 8% -42%,var(--hmb-haze),transparent 54%),linear-gradient(90deg,var(--hmb-head-wash),rgba(14,23,38,.95) 46%,var(--hmb-bg-bottom));color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24),0 0 18px var(--hmb-chip-glow);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;box-sizing:border-box;user-select:none}
      .hmb-agent-dashboard[data-shot-number="2"]{--hmb-shot-accent:#3B82F6;--hmb-shot-rgb:59,130,246;--hmb-shot-deep:#1D4ED8;--hmb-shot-soft:#DBEAFE;--hmb-shot-line:rgba(59,130,246,.5);--hmb-shot-glow:rgba(59,130,246,.2)}
      .hmb-agent-dashboard[data-shot-number="3"]{--hmb-shot-accent:#10B981;--hmb-shot-rgb:16,185,129;--hmb-shot-deep:#047857;--hmb-shot-soft:#D1FAE5;--hmb-shot-line:rgba(16,185,129,.5);--hmb-shot-glow:rgba(16,185,129,.2)}
      .hmb-agent-dashboard[data-shot-number="4"]{--hmb-shot-accent:#8B5CF6;--hmb-shot-rgb:139,92,246;--hmb-shot-deep:#6D28D9;--hmb-shot-soft:#EDE9FE;--hmb-shot-line:rgba(139,92,246,.5);--hmb-shot-glow:rgba(139,92,246,.2)}
      .hmb-agent-dashboard[data-shot-number="5"]{--hmb-shot-accent:#EAB308;--hmb-shot-rgb:234,179,8;--hmb-shot-deep:#A16207;--hmb-shot-soft:#FEF3C7;--hmb-shot-line:rgba(234,179,8,.5);--hmb-shot-glow:rgba(234,179,8,.2)}
      .hmb-agent-dashboard *{box-sizing:border-box;min-width:0}.hmb-agent-dashboard .agent-topbar{position:relative;height:100%;display:flex;align-items:center;gap:11px;padding:8px 13px}.hmb-agent-dashboard .agent-topbar::after{content:"";position:absolute;right:13px;bottom:0;left:13px;height:1px;background:linear-gradient(90deg,var(--hmb-accent),var(--hmb-highlight),transparent);opacity:.32}.hmb-agent-dashboard .agent-mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;overflow:hidden;border:1px solid var(--hmb-mark-line);border-radius:8px;background:linear-gradient(145deg,var(--hmb-mark-bg),rgba(5,9,16,.86));color:var(--hmb-accent);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px var(--hmb-mark-glow);font-size:10px;font-weight:950;letter-spacing:.08em}.hmb-agent-dashboard .agent-heading{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:3px;overflow:hidden}.hmb-agent-dashboard .agent-heading b,.hmb-agent-dashboard .agent-heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-agent-dashboard .agent-heading b{color:var(--hmb-text);font-size:15px;font-weight:850;line-height:1;letter-spacing:.01em}.hmb-agent-dashboard .agent-heading span{color:var(--hmb-muted);font-size:9px;font-weight:650;line-height:1;letter-spacing:.055em}.hmb-agent-dashboard .agent-publication-status{flex:0 1 190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--hmb-status-error);font-size:8px;font-weight:800;text-align:right}.hmb-agent-dashboard[data-execution-phase]:not([data-execution-phase=""]) .agent-publication-status{color:var(--hmb-status-warning)}.hmb-agent-dashboard .agent-publication-status:empty{display:none}.hmb-agent-dashboard .agent-shot-select{flex:0 1 210px;width:210px;height:29px;margin-left:auto;padding:0 28px 0 10px;border:1px solid var(--hmb-chip-line);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(255,255,255,.04),transparent),var(--hmb-chip-bg);color:var(--hmb-chip-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.045),0 0 12px var(--hmb-chip-glow);font:inherit;font-size:10px;font-weight:850;letter-spacing:.035em}.hmb-agent-dashboard .agent-shot-select:focus{border-color:var(--hmb-accent);box-shadow:0 0 0 2px var(--hmb-mark-glow)}.hmb-agent-dashboard .agent-shot-select option{background:#0b1020;color:var(--hmb-text)}
      @container(max-width:420px){.hmb-agent-dashboard .agent-shot-select{flex-basis:120px;width:120px}}@container(max-width:280px){.hmb-agent-dashboard .agent-heading span{display:none}.hmb-agent-dashboard .agent-heading b{font-size:13px}}
      /* Match the Prompt header while preserving the existing selector position and responsive width. */
      .hmb-agent-dashboard .agent-heading b{font-size:15px;font-weight:800;letter-spacing:.01em;line-height:normal}
      .hmb-agent-dashboard .agent-shot-select{height:44px;font-size:13px;font-weight:800;line-height:normal}
      .hmb-agent-dashboard .agent-topbar{height:64px}
      .hmb-agent-dashboard .agent-rebind-panel{display:none;padding:0 12px 10px;gap:6px;flex-wrap:wrap;align-items:center;font-size:10px;color:var(--hmb-text)}
      .hmb-agent-dashboard .agent-rebind-panel>span{flex:1 0 100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#FBBF24}
      .hmb-agent-dashboard .agent-rebind-select{flex:1;min-width:100px;height:32px;border:1px solid var(--hmb-chip-line);border-radius:6px;background:#0b1020;color:var(--hmb-text)}
      .hmb-agent-dashboard .agent-rebind-confirm{height:32px;border:1px solid var(--hmb-chip-line);border-radius:6px;background:var(--hmb-chip-bg);color:var(--hmb-text);padding:0 10px}
      .hmb-agent-dashboard .agent-only-toggle{flex:0 0 auto;height:29px;padding:0 10px;border:1px solid var(--hmb-chip-line);border-radius:7px;background:var(--hmb-chip-bg);color:var(--hmb-chip-text);font:inherit;font-size:10px;font-weight:850}
      .hmb-agent-dashboard .agent-only-toggle[aria-pressed="true"]{box-shadow:0 0 10px var(--hmb-chip-glow);border-color:var(--hmb-shot-accent)}
      .hmb-agent-dashboard .agent-shot-list{padding:0 8px 8px;display:flex;flex-direction:column;gap:0}
      .hmb-agent-dashboard .agent-shot-row{--hmb-shot-accent:#F472B6;--row-rgb:244,114,182;display:flex;align-items:center;gap:6px;height:42px;border-top:1px solid rgba(var(--row-rgb),.35);background:linear-gradient(90deg,rgba(var(--row-rgb),.12),transparent);border-radius:5px}
      .hmb-agent-dashboard .agent-shot-row[data-shot-number="2"]{--hmb-shot-accent:#3B82F6;--row-rgb:59,130,246}.hmb-agent-dashboard .agent-shot-row[data-shot-number="3"]{--hmb-shot-accent:#10B981;--row-rgb:16,185,129}.hmb-agent-dashboard .agent-shot-row[data-shot-number="4"]{--hmb-shot-accent:#8B5CF6;--row-rgb:139,92,246}.hmb-agent-dashboard .agent-shot-row[data-shot-number="5"]{--hmb-shot-accent:#EAB308;--row-rgb:234,179,8}
      .hmb-agent-dashboard .agent-shot-row[data-active="true"]{box-shadow:inset 3px 0 var(--hmb-shot-accent);background:linear-gradient(90deg,rgba(var(--row-rgb),.23),rgba(var(--row-rgb),.04))}
      .hmb-agent-dashboard .agent-shot-tab{flex:1;display:flex;align-items:center;gap:10px;height:100%;padding:4px 8px;border:0;background:transparent;color:var(--hmb-text);text-align:left;font:inherit;font-size:11px}
      .hmb-agent-dashboard .agent-row-number{width:29px;height:29px;display:grid;place-items:center;border:1px solid var(--hmb-shot-accent);border-radius:7px;color:var(--hmb-shot-accent);font-weight:850}
      .hmb-agent-dashboard .agent-shot-tab b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-agent-dashboard .agent-row-status{margin-left:auto;color:var(--hmb-muted);font-size:9px}
      .hmb-agent-dashboard .agent-shot-run{flex:0 0 29px;height:29px;margin-right:6px;border:1px solid rgba(var(--row-rgb),.5);border-radius:7px;background:rgba(var(--row-rgb),.12);color:var(--hmb-shot-accent);font-size:16px}
      .hmb-agent-dashboard .agent-shot-empty{height:42px;display:flex;align-items:center;justify-content:center;color:var(--hmb-muted);font-size:10px}
      .hmb-agent-dashboard .agent-native-identity,.hmb-agent-dashboard .agent-native-actions{display:none;min-width:0;--node-header-text:var(--hmb-text)}
      .hmb-agent-dashboard[data-hmb-native-header="active"] .agent-mark,.hmb-agent-dashboard[data-hmb-native-header="active"] .agent-heading{display:none}
      .hmb-agent-dashboard[data-hmb-native-header="active"] .agent-native-identity{display:flex;align-items:center;flex:1;min-width:0}
      .hmb-agent-dashboard[data-hmb-native-header="active"] .agent-native-actions{display:flex;align-items:center;flex:0 0 auto}
      .hmb-agent-dashboard .agent-native-identity>div{min-width:0;max-width:100%}.hmb-agent-dashboard .agent-native-actions svg{flex-shrink:0}
      .hmb-agent-dashboard[data-hmb-native-header="active"] .agent-topbar{cursor:grab}.hmb-agent-dashboard[data-hmb-native-header="active"] .agent-topbar:active{cursor:grabbing}
    </style>
    <div class="hmb-agent-dashboard nodrag" data-shot-number="${paletteShotNumber}" data-execution-phase="${hmbAgentEscape(state.execution_phase)}" style="height:${height}px" tabindex="0">
      <header class="agent-topbar group">
        <div class="agent-mark" aria-hidden="true"><span>AG</span></div>
        <div class="agent-heading"><b>HMB Agent</b></div>
        <div class="agent-native-identity" data-hmb-native-identity></div>
        <div class="agent-native-actions nodrag" data-hmb-native-actions></div>
        <span class="agent-publication-status" role="status" aria-live="polite" aria-atomic="true">${hmbAgentEscape(executionStatus)}</span>
      </header>
      <div class="agent-rebind-panel nodrag"><span role="status"></span><select class="agent-rebind-select" aria-label="기존 Agent를 연결할 샷 선택"></select><button type="button" class="agent-rebind-confirm">직접 재연결</button></div>
    </div>`;
}

function compactAgentWidgetHost(container, state = null) {
  if (!container?.style) return;
  const height = hmbAgentWidgetHeight(state);
  const values = {height:`${height}px`,"min-height":`${height}px`,"max-height":`${height}px`,flex:`0 0 ${height}px`,"flex-basis":`${height}px`,overflow:"hidden","box-sizing":"border-box"};
  for (const [name,value] of Object.entries(values)) {
    if (container.style.getPropertyValue?.(name) !== value) container.style.setProperty(name,value,"important");
  }
}

function hmbRefreshAgentDashboard(container, props) {
  const root = hmbAgentDashboardRoot(container);
  if (!root) return false;
  const state = hmbAgentState(props);
  compactAgentWidgetHost(container, state);
  if (root.style.height !== `${hmbAgentWidgetHeight(state)}px`) root.style.height = `${hmbAgentWidgetHeight(state)}px`;
  hmbPrepareAgentCanvasGestures(container);
  const paletteShotNumber = hmbAgentDisplayShotNumber(container, state);
  const error = container.__hmbAgentShotChangeError || "";
  const signature = JSON.stringify([paletteShotNumber, state.execution_phase, error,
    state.shot_manager, state.only_mode, state.shot, state.shot_catalog,state.manual_rebind,
    container.__hmbAgentManualPending?.request_id,container.__hmbAgentManualError]);
  if (root.__hmbAgentPresentationSignature === signature) return true;
  root.__hmbAgentPresentationSignature = signature;
  const toggle = root.querySelector?.(".agent-only-toggle");
  if (toggle) { toggle.setAttribute("aria-pressed", String(state.only_mode)); toggle.disabled = Boolean(state.execution_phase); }
  const rows = root.querySelector?.(".agent-shot-list");
  if (rows) {
    rows.style.display = state.shot_manager ? "flex" : "none";
    const html = hmbAgentRows(state);
    if (rows.__hmbRowsMarkup !== html) { rows.innerHTML = html; rows.__hmbRowsMarkup = html; }
  }
  hmbAgentSetAttribute(root,"data-shot-number",String(paletteShotNumber));
  hmbAgentSetAttribute(root,"data-execution-phase",state.execution_phase || "");
  const select = root.querySelector?.(".agent-shot-select");
  if (select) {
    hmbSyncAgentShotSelect(select, state);
    select.style.display = state.shot_manager || state.only_mode ? "none" : "";
  }
  const executionStatus = hmbAgentExecutionStatus(state.execution_phase);
  hmbRefreshManualAgentRebind(container,state);
  hmbSetAgentStatus(
    container,
    error ? "Save failed · previous Shot restored" : executionStatus,
    error || executionStatus,
  );
  if (select) select.disabled = Boolean(state.execution_phase);
  return true;
}

function hmbRefreshManualAgentRebind(container,state){
  const panel=container.querySelector?.(".agent-rebind-panel");if(!panel)return;
  const manual=state.manual_rebind || {},pending=container.__hmbAgentManualPending;
  if(pending && manual.request_id===pending.request_id){clearTimeout(pending.timer);pending.guardCleanup?.();delete container.__hmbAgentManualPending;}
  panel.style.display=manual.required ? "flex" : "none";
  if(!manual.required)return;
  const select=panel.querySelector("select"),button=panel.querySelector("button"),message=panel.querySelector("span");
  const options=hmbAgentShotOptions(state),signature=JSON.stringify(options.map(item=>[item.key,item.name,item.number]));
  if(select.__hmbOptionSignature!==signature){const value=select.value;select.innerHTML='<option value="">재연결할 샷 선택…</option>'+options.map(item=>`<option value="${hmbAgentEscape(item.key)}">${hmbAgentEscape(hmbAgentShotOptionLabel(item))}</option>`).join("");select.__hmbOptionSignature=signature;select.value=options.some(item=>item.key===value) ? value : "";}
  const busy=Boolean(container.__hmbAgentManualPending);select.disabled=busy;button.disabled=busy || !select.value;
  message.textContent=container.__hmbAgentManualError || manual.error || manual.reason || "기존 입력을 보존했습니다. 해당 샷을 직접 선택한 뒤 재연결하세요.";
  message.title=manual.backup_path || "";
  button.textContent=busy ? "확인 중…" : "직접 재연결";
}

function hmbAgentShotKey(state) {
  return state?.shot?.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}` : "__hmb_only__";
}

function hmbAgentResolveShotEcho(container, incomingProps) {
  const manualPending=container.__hmbAgentManualPending;
  if(manualPending && incomingProps!==container.__hmbAgentLatestProps){
    const incoming=hmbAgentState(incomingProps).manual_rebind;
    if(!incoming || incoming.expected_source_digest!==manualPending.expected_source_digest
        || (!incoming.required && incoming.request_id!==manualPending.request_id)){
      return {props:container.__hmbAgentLatestProps || incomingProps,stale:true};
    }
  }
  const pending = container.__hmbAgentPendingShot;
  if (!pending || incomingProps === container.__hmbAgentLatestProps) return { props: incomingProps, stale: false };
  const incoming = hmbAgentState(incomingProps);
  const selected = hmbAgentState(container.__hmbAgentLatestProps);
  const catalogOlder = incoming.shot_catalog.channel_uuid === selected.shot_catalog.channel_uuid
    && Number(incoming.shot_catalog.generation || 0) < Number(selected.shot_catalog.generation || 0);
  const catalog = catalogOlder ? selected.shot_catalog : incoming.shot_catalog;
  const incomingKey = hmbAgentShotKey(incoming);
  if (incomingKey === pending.targetKey && incoming.shot_manager === pending.targetMode) {
    delete container.__hmbAgentPendingShot;
    return { props: incomingProps, stale: false };
  }
  const targetAvailable = pending.targetKey === "__hmb_only__" || (catalog.shots || []).some(
    (shot) => `${catalog.channel_uuid}\u001f${shot.shot_uuid}` === pending.targetKey,
  );
  const previousModeEcho = incomingKey === pending.targetKey && incoming.shot_manager !== pending.targetMode;
  if (!targetAvailable || (!pending.blockedKeys.has(incomingKey) && !previousModeEcho)) {
    delete container.__hmbAgentPendingShot;
    return { props: incomingProps, stale: false };
  }
  const retained = { ...incoming, shot_catalog: catalog, shot: selected.shot, shot_manager:selected.shot_manager, only_mode:selected.only_mode };
  return {
    props: { ...incomingProps, value: retained, parameterValue: retained, defaultValue: retained },
    stale: true,
  };
}

export function hmbPrepareAgentCanvasGestures(container) {
  if (!container) return;
  // The widget surface must not drag the node itself, but it must not retain
  // broad pan/zoom guards from an older mount. With no local pointer or wheel
  // handlers, Griptape owns left/middle-button pan, wheel zoom, and its native
  // grab -> grabbing cursor transition.
  for (const name of ["nopan","nowheel"]) if (container.classList?.contains(name)) container.classList.remove(name);
  const nativeActive = container.__hmbAgentNativeHeaderActive === true;
  container.classList?.toggle("nodrag", !nativeActive);
  const root = hmbAgentDashboardRoot(container);
  for (const name of ["nopan","nowheel"]) if (root?.classList?.contains(name)) root.classList.remove(name);
  root?.classList?.toggle("nodrag", !nativeActive);
}

function hmbAgentNativeHeaderTarget(target) {
  return Boolean(target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]"));
}

function hmbAgentDashboardRoot(container) {
  let root = container?.__hmbAgentDashboardRoot;
  if (!root || container?.contains?.(root) === false) {
    root = container?.querySelector?.(".hmb-agent-dashboard");
    if (root) container.__hmbAgentDashboardRoot = root;
  }
  return root;
}

function hmbAgentDisplayShotNumber(container, state) {
  const fallback = hmbAgentPaletteShotNumber(state);
  const channel = state?.shot_catalog?.channel_uuid || state?.shot?.channel_uuid;
  const entry = hmbAgentRowChannels.get(channel);
  const host = hmbAgentNodeRoot(container);
  if (!entry || !host) return fallback;
  const pending = entry.pending;
  if (pending?.kind === "select" && !pending.recovering && hmbAgentNodeRoot(pending.owner) === host) return pending.shotNumber;
  const confirmed = entry.themes.get(host);
  return confirmed && (state.shot_catalog?.shots || []).some(shot => shot.shot_uuid === confirmed.shotUuid)
    ? confirmed.number : fallback;
}

function hmbAgentNodeRoot(container) {
  let current = container?.parentElement || null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) return null;
  }
  return null;
}

function hmbAgentNodeIsSelected(root) {
  if (!root) return false;
  if (root.classList?.contains("selected")) return true;
  if (String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true") return true;
  if (String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true") return true;
  return Boolean(root.querySelector?.(
    ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
  ));
}

function hmbAgentDeleteEditingTarget(event) {
  return Boolean(event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (container?.ownerDocument?.documentElement?.getAttribute?.("data-hmb-native-deletion-guard") === "engine-preflight") return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbAgentDeleteEditingTarget(event)) return false;
  if (!hmbAgentNodeIsSelected(hmbAgentNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function hmbNativeUiImplementation(container, props) {
  const rawValue = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  if (rawValue?.schema === "hmb-agent-shot-row") return hmbAgentShotRowWidget(container, props);
  if (!container) return { cleanup() {}, update() {} };
  // The host can call the factory again without replacing the mounted DOM.
  // Keep callbacks/state pointed at the newest props instead of the first
  // mount's closure.
  const incomingProps = props || container.__hmbAgentLatestProps || {};
  const resolved = hmbAgentResolveShotEcho(container, incomingProps);
  if (!resolved.stale && container.__hmbAgentLatestProps && incomingProps !== container.__hmbAgentLatestProps) {
    container.__hmbAgentShotChangeOwner = Math.max(
      0,
      Number(container.__hmbAgentShotChangeOwner) || 0,
    ) + 1;
  }
  container.__hmbAgentLatestProps = resolved.props;
  props = resolved.props;
  if (typeof container.__hmbAgentCleanupProxy !== "function") {
    container.__hmbAgentCleanupProxy = () => {
      const currentCleanup = container.__hmbAgentCleanup;
      if (typeof currentCleanup === "function") currentCleanup();
    };
  }
  const previousCleanup = container.__hmbAgentCleanup;
  // Griptape can invoke the widget factory again for an ordinary value or
  // selection refresh. Keep the mounted dashboard intact so the host never
  // observes the former cleanup -> empty container -> rebuild sequence.
  if (typeof previousCleanup === "function" && hmbRefreshAgentDashboard(container, resolved.props)) {
    return {
      cleanup: container.__hmbAgentCleanupProxy,
      update(nextProps) {
        const incoming = nextProps || container.__hmbAgentLatestProps || {};
        const next = hmbAgentResolveShotEcho(container, incoming);
        if (!next.stale) container.__hmbAgentShotChangeOwner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
        props = next.props;
        container.__hmbAgentLatestProps = next.props;
        if (!hmbRefreshAgentDashboard(container, next.props)) {
          HMBAgentLibraryWidget(container, next.props);
        }
      },
    };
  }
  if (typeof previousCleanup === "function") previousCleanup();

  // A transport Promise can reject after the host has fully unmounted and
  // remounted this same container. Keep one monotonic epoch on the container;
  // old accept/rollback closures may never acquire a replacement mount even
  // if its local numeric change owner happens to match.
  const lifecycleEpoch = Math.max(
    0,
    Number(container.__hmbAgentLifecycleEpoch) || 0,
  ) + 1;
  container.__hmbAgentLifecycleEpoch = lifecycleEpoch;
  let disposed = false;
  const ownsLifecycle = () => (
    !disposed && container.__hmbAgentLifecycleEpoch === lifecycleEpoch
  );

  compactAgentWidgetHost(container, hmbAgentState(props));
  const hadContainerNoDrag = container.classList?.contains("nodrag");
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  container.setAttribute?.("data-hmb-color-lut-widget", "");
  container.setAttribute?.("data-hmb-native-node-type", "HMBAgentLibrary");
  container.innerHTML = hmbScopeWidgetStyleMarkup(
    renderAgentDashboard(hmbAgentState(props), container),
    ".hmb-agent-dashboard",
  );
  hmbPrepareAgentCanvasGestures(container);
  const documentRef = container.ownerDocument || (typeof document !== "undefined" ? document : null);
  const announceNativeHeader = (phase) => {
    const Event = documentRef?.defaultView?.CustomEvent || (typeof CustomEvent !== "undefined" ? CustomEvent : null);
    if (Event) documentRef?.dispatchEvent?.(new Event(`hmb-color-lut-header-${phase}`, {detail:{container}}));
  };
  const nativeHeaderState = (event) => {
    if (!ownsLifecycle() || event.target !== container) return;
    container.__hmbAgentNativeHeaderActive = event.detail?.active === true;
    hmbAgentDashboardRoot(container)?.setAttribute("data-hmb-native-header", container.__hmbAgentNativeHeaderActive ? "active" : "fallback");
    hmbPrepareAgentCanvasGestures(container);
  };
  container.addEventListener?.("hmb-color-lut-header-state", nativeHeaderState);
  // Discovery asks a local publisher to refresh its backend state. The
  // process-global response is deliberately not observed by this widget.
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    try { window.dispatchEvent(new CustomEvent("hmb-shot-routing-discover-v1")); } catch (_error) {}
  }
  const shotSelect = container.querySelector?.(".agent-shot-select");
  const manualSelect=container.querySelector?.(".agent-rebind-select"),manualConfirm=container.querySelector?.(".agent-rebind-confirm");
  const manualSelectHandler=()=>{delete container.__hmbAgentManualError;hmbRefreshManualAgentRebind(container,hmbAgentState(container.__hmbAgentLatestProps || props));};
  const manualConfirmHandler=()=>{
    const live=container.__hmbAgentLatestProps || props,state=hmbAgentState(live),manual=state.manual_rebind;
    if(!ownsLifecycle() || !manual?.required || live.disabled || container.__hmbAgentManualPending || typeof live.onChange!=="function")return;
    const selected=hmbAgentShotOptions(state).find(item=>item.key===manualSelect?.value);if(!selected)return;
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);const requestId=Array.from(bytes,byte=>byte.toString(16).padStart(2,"0")).join("");
    const ticket={request_id:requestId,expected_source_digest:manual.expected_source_digest,owner:container,recovering:false};
    container.__hmbAgentManualPending=ticket;delete container.__hmbAgentManualError;
    ticket.guardCleanup=hmbGuardPendingAgentEditor(container,ticket);
    const pending=()=>ownsLifecycle() && container.__hmbAgentManualPending===ticket;
    const uncertain=()=>{if(!pending())return;ticket.recovering=true;container.__hmbAgentManualError="응답 확인이 필요합니다. 자동 재전송하지 않으며 현재 안내를 다시 확인하세요.";hmbRefreshManualAgentRebind(container,hmbAgentState(container.__hmbAgentLatestProps || props));};
    ticket.timer=setTimeout(uncertain,15000);
    hmbRefreshManualAgentRebind(container,state);
    const next={...state,action:{kind:"manual_rebind",request_id:requestId,
      expected_source_digest:manual.expected_source_digest,channel_uuid:selected.channel_uuid,shot_uuid:selected.shot_uuid}};
    try{Promise.resolve(live.onChange(next)).catch(uncertain);}catch{uncertain();}
  };
  manualSelect?.addEventListener?.("change",manualSelectHandler);manualConfirm?.addEventListener?.("click",manualConfirmHandler);
  hmbRefreshManualAgentRebind(container,hmbAgentState(props));
  const shotChangeHandler = (requestedState = null) => {
    const liveProps = container.__hmbAgentLatestProps || props || {};
    const option = hmbAgentShotOptions(hmbAgentState(liveProps)).find((item) => item.key === shotSelect?.value);
    if ((!requestedState && !option) || typeof liveProps?.onChange !== "function") {
      hmbRefreshAgentDashboard(container, liveProps);
      return;
    }
    const previousProps = liveProps;
    const next = requestedState || hmbAgentState(liveProps);
    if (!requestedState) next.shot = option.only ? {
      channel_uuid: "", shot_uuid: "", number: 1, name: "Only",
    } : {
      channel_uuid: option.channel_uuid,
      shot_uuid: option.shot_uuid,
      number: option.number,
      name: option.name,
    };
    const owner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
    container.__hmbAgentShotChangeOwner = owner;
    const previousKey = hmbAgentShotKey(hmbAgentState(liveProps));
    const blockedKeys = new Set(container.__hmbAgentPendingShot?.blockedKeys || []);
    blockedKeys.add(previousKey);
    container.__hmbAgentPendingShot = { targetKey: hmbAgentShotKey(next), targetMode:next.shot_manager, blockedKeys };
    const optimisticState = hmbAgentState({ value: next });
    const optimisticProps = { ...liveProps, value: optimisticState, parameterValue: optimisticState, defaultValue: optimisticState };
    const accept = () => {
      if (!ownsLifecycle() || container.__hmbAgentShotChangeOwner !== owner) return false;
      props = optimisticProps;
      container.__hmbAgentLatestProps = props;
      delete container.__hmbAgentShotChangeError;
      hmbRefreshAgentDashboard(container, props);
      return true;
    };
    const rollback = (error) => {
      if (!ownsLifecycle() || container.__hmbAgentShotChangeOwner !== owner) return false;
      delete container.__hmbAgentPendingShot;
      props = previousProps;
      container.__hmbAgentLatestProps = previousProps;
      container.__hmbAgentShotChangeError = String(error?.message || error || "Shot selection publication failed");
      hmbRefreshAgentDashboard(container, previousProps);
      return true;
    };
    accept();
    let result;
    try {
      result = liveProps.onChange(next);
    } catch (error) {
      rollback(error);
      return;
    }
    if (result && typeof result.then === "function") {
      Promise.resolve(result).catch(rollback);
    }
  };
  const legacyShotChangeHandler = () => shotChangeHandler();
  shotSelect?.addEventListener?.("change", legacyShotChangeHandler);
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
  }
  const stopNodeDeleteShortcut = (event) => {
    if (hmbAgentNativeHeaderTarget(event.target)) return;
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorNodeSelection = (event) => {
    if (hmbAgentNativeHeaderTarget(event.target)
      || container.__hmbAgentNativeHeaderActive && event.target?.closest?.(".agent-topbar")
        && !event.target?.closest?.("button,input,select,textarea,label,a")) return;
    if (Number(event?.button) !== 1) event.stopPropagation?.();
  };
  container.addEventListener?.("keydown", stopNodeDeleteShortcut);
  container.addEventListener?.("pointerdown", stopInteriorNodeSelection);

  const cleanup = () => {
    announceNativeHeader("retire");
    disposed = true;
    if (container.__hmbAgentLifecycleEpoch === lifecycleEpoch) {
      container.__hmbAgentLifecycleEpoch = lifecycleEpoch + 1;
    }
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
    }
    container.removeEventListener?.("keydown", stopNodeDeleteShortcut);
    container.removeEventListener?.("pointerdown", stopInteriorNodeSelection);
    container.removeEventListener?.("hmb-color-lut-header-state", nativeHeaderState);
    shotSelect?.removeEventListener?.("change", legacyShotChangeHandler);
    manualSelect?.removeEventListener?.("change",manualSelectHandler);manualConfirm?.removeEventListener?.("click",manualConfirmHandler);
    const manualPending=container.__hmbAgentManualPending;if(manualPending){clearTimeout(manualPending.timer);manualPending.guardCleanup?.();delete container.__hmbAgentManualPending;}
    delete container.__hmbAgentManualError;
    container.removeAttribute?.("data-hmb-node-delete-protected");
    container.removeAttribute?.("data-hmb-color-lut-widget");
    container.removeAttribute?.("data-hmb-native-node-type");
    delete container.__hmbAgentNativeHeaderActive;
    container.classList?.toggle("nodrag", Boolean(hadContainerNoDrag));
    try {
      container.style.removeProperty("height");
      container.style.removeProperty("min-height");
      container.style.removeProperty("max-height");
      container.style.removeProperty("flex");
      container.style.removeProperty("flex-basis");
      container.style.removeProperty("overflow");
      container.style.removeProperty("box-sizing");
    } catch (_error) {}
    if (container.__hmbAgentCleanup === cleanup) {
      delete container.__hmbAgentCleanup;
    }
    delete container.__hmbAgentLatestProps;
    delete container.__hmbAgentDashboardRoot;
    delete container.__hmbAgentPendingShot;
    // Preserve monotonic ownership across a real cleanup/remount. Deleting
    // this counter allowed a replacement mount to reuse an old pending
    // request's owner value.
    container.__hmbAgentShotChangeOwner = Math.max(
      0,
      Number(container.__hmbAgentShotChangeOwner) || 0,
    ) + 1;
    delete container.__hmbAgentShotChangeError;
    container.innerHTML = "";
  };
  container.__hmbAgentCleanup = cleanup;
  announceNativeHeader("ready");
  return {
    cleanup: container.__hmbAgentCleanupProxy,
    update(nextProps) {
      const incoming = nextProps || container.__hmbAgentLatestProps || {};
      const next = hmbAgentResolveShotEcho(container, incoming);
      if (!next.stale) container.__hmbAgentShotChangeOwner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
      props = next.props;
      container.__hmbAgentLatestProps = next.props;
      if (!hmbRefreshAgentDashboard(container, next.props)) {
        HMBAgentLibraryWidget(container, next.props);
      }
    },
  };
}


export function hmbAgentShotRowState(props) {
  const raw = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  const shot = raw?.shot && typeof raw.shot === "object" ? raw.shot : {};
  const number = Number(shot.number);
  const valid = raw?.schema === "hmb-agent-shot-row" && raw.version === 1
    && typeof shot.channel_uuid === "string" && shot.channel_uuid.trim()
    && typeof shot.shot_uuid === "string" && shot.shot_uuid.trim()
    && Number.isInteger(number) && number >= 1 && number <= 5;
  return {schema:"hmb-agent-shot-row",version:1,
    shot:valid ? {channel_uuid:shot.channel_uuid,shot_uuid:shot.shot_uuid,number,name:String(shot.name || `Shot ${number}`).slice(0,128),revision:Number(shot.revision)||0} : {},
    selected:valid && raw.selected === true,expanded:valid && raw.expanded === true,
    ...(raw?.routing_pending===true ? {routing_pending:true} : {}),
    request_id:/^[0-9a-f]{32}$/.test(String(raw?.request_id || "")) ? raw.request_id : "",
    ...(/^[0-9a-f]{32}$/.test(String(raw?.rejected_request_id || "")) && raw?.error_code==="SHOT_IDENTITY_UNAVAILABLE"
      ? {rejected_request_id:raw.rejected_request_id,error_code:raw.error_code} : {}),
    status:["running","succeeded","failed","cancelled"].includes(raw?.status) ? raw.status : ""};
}

// One Agent manager owns one channel. All five row widgets share this short
// command lease, so a second Shot/Run cannot overtake a pending native switch.
const hmbAgentRowChannels = new Map();

function hmbGuardPendingAgentEditor(container,ticket) {
  const host=hmbAgentNodeRoot(container);
  if(!host?.addEventListener)return ()=>{};
  // The SDK owns native parameter rows and their element IDs. Quarantine only
  // those editors and Shot actions while their identity is unconfirmed. The
  // host header, Delete menu and canvas must remain usable even after a lost
  // ACK; guarding the whole node made a local transport error look like a hang.
  const guard=event=>{
    if(Number(event.button)===1 || event.target?.closest?.(".react-flow__handle,.react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']"))return;
    if(ticket.recovering && event.target?.closest?.(".agent-shot-run")===container.querySelector?.(".agent-shot-run"))return;
    const action=event.target?.closest?.(".agent-shot-tab,.agent-shot-run");
    const parameter=event.target?.closest?.("[data-parameter-name],[data-parameter],[data-parameter-key]");
    const name=String(parameter?.getAttribute?.("data-parameter-name") || parameter?.getAttribute?.("data-parameter") || parameter?.getAttribute?.("data-parameter-key") || "");
    const nativeEditor=parameter && host.contains?.(parameter) && name!=="HMB_AGENT_UI" && !/^HMB_AGENT_SHOT_ROW_[1-5]$/.test(name);
    if(!action && !nativeEditor)return;
    event.preventDefault?.();event.stopImmediatePropagation?.();event.stopPropagation?.();
  };
  const events=["pointerdown","mousedown","click","dblclick","keydown","beforeinput","input","change","paste","drop"];
  for(const name of events)host.addEventListener(name,guard,true);
  return ()=>{for(const name of events)host.removeEventListener(name,guard,true);};
}

function hmbAgentShotRowWidget(container, initialProps) {
  if (!container) return {cleanup(){},update(){}};
  if (container.__hmbAgentRowHandle) {
    container.__hmbAgentRowHandle.update(initialProps);
    return container.__hmbAgentRowHandle;
  }
  let props=initialProps || {};let disposed=false;let channel="";let acceptedAck="";let lastError="";let lastRejected=false;
  const retiredAcks=new Set();
  const channelEntry=()=>hmbAgentRowChannels.get(channel);
  const refreshChannel=()=>{for(const owner of channelEntry()?.owners || [])owner.refresh();};
  const unregister=()=>{const entry=channelEntry();if(!entry)return;if(entry.pending?.owner===container)finish(entry.pending);entry.owners.delete(owner);if(!entry.owners.size)hmbAgentRowChannels.delete(channel);};
  const register=()=>{const next=hmbAgentShotRowState(props).shot.channel_uuid || "";if(next===channel)return;unregister();channel=next;acceptedAck="";retiredAcks.clear();if(channel){if(!hmbAgentRowChannels.has(channel))hmbAgentRowChannels.set(channel,{owners:new Set(),pending:null,themes:new WeakMap()});channelEntry().owners.add(owner);}};
  const rememberTheme=state=>{const host=hmbAgentNodeRoot(container);if(state.selected && host)channelEntry()?.themes.set(host,{shotUuid:state.shot.shot_uuid,number:state.shot.number});};
  const finish=(ticket,error)=>{const entry=channelEntry();if(entry?.pending!==ticket)return;for(const id of ticket.frames)cancelAnimationFrame(id);clearTimeout(ticket.fallback);clearTimeout(ticket.expiry);ticket.guardCleanup?.();entry.pending=null;if(error && !disposed)lastError=String(error?.message||error);refreshChannel();};
  const recover=(ticket,error)=>{if(disposed || channelEntry()?.pending!==ticket)return;ticket.recovering=true;lastRejected=false;lastError=String(error?.message||error);clearTimeout(ticket.expiry);refreshChannel();};
  const reject=(ticket,error)=>{
    if(disposed || channelEntry()?.pending!==ticket)return;
    for(const id of ticket.acceptedIds)retiredAcks.add(id);
    while(retiredAcks.size>256)retiredAcks.delete(retiredAcks.values().next().value);
    lastRejected=true;finish(ticket,error);
  };
  container.classList?.add("nodrag");container.classList?.remove("nopan","nowheel");
  container.setAttribute?.("data-hmb-node-delete-protected","true");
  const state=hmbAgentShotRowState(props);
  const header=hmbScopeWidgetStyleMarkup(renderAgentDashboard(hmbAgentState({value:{}}),container),".hmb-agent-dashboard");
  const style=header.match(/<style>[\s\S]*?<\/style>/)?.[0] || "";
  container.innerHTML=style+`<div class="hmb-agent-dashboard hmb-agent-shot-accordion nodrag" style="height:42px;border-radius:7px;box-shadow:none" data-shot-number="${state.shot.number || 1}"><div class="agent-shot-row" style="height:40px" data-shot-number="${state.shot.number || 1}"><button type="button" class="agent-shot-tab nodrag" data-agent-shot="${hmbAgentEscape(state.shot.shot_uuid || "")}" aria-expanded="false"><span class="agent-row-number"></span><b></b><span class="agent-row-status"></span><span class="agent-row-chevron" aria-hidden="true"></span></button><button type="button" class="agent-shot-run nodrag" aria-label="Run Shot Agent"></button></div></div>`;
  const root=container.querySelector(".hmb-agent-dashboard"),row=container.querySelector(".agent-shot-row"),select=container.querySelector(".agent-shot-tab"),run=container.querySelector(".agent-shot-run");
  const number=select.querySelector(".agent-row-number"),label=select.querySelector("b"),status=select.querySelector(".agent-row-status"),chevron=select.querySelector(".agent-row-chevron");
  let presentationSignature="";
  const refresh=()=>{
    const canonical=hmbAgentShotRowState(props);const shot=canonical.shot;
    const ticket=channelEntry()?.pending;const switching=ticket?.kind==="select" && !ticket.recovering;
    const own=ticket?.owner===container;
    const current=switching ? {...canonical,selected:own,expanded:own && ticket.expanded} : canonical;
    const recovering=own && ticket?.recovering;
    const text=canonical.routing_pending ? "샷 연결 확인 중…" : own ? (recovering ? "응답 확인 필요" : switching ? "전환 중…" : "전달 중…") : lastError ? (lastRejected ? "요청 거절됨" : "응답 확인 필요") : ({running:"Agent 실행 중…",succeeded:"완료",failed:"실패",cancelled:"취소"})[current.status] || "";
    const running=current.status==="running",runText=recovering ? "↻" : running ? "■" : "▷";
    const title=recovering?"현재 상태만 확인합니다. Agent/Run은 다시 실행하지 않습니다.":lastError || (running?"이 샷 Agent만 취소":"이 샷 Agent만 실행");
    const disabled=Boolean(ticket) || Boolean(canonical.routing_pending) || !shot.shot_uuid,runDisabled=disabled && (!recovering || Boolean(canonical.routing_pending));
    // The host may update geometry independently of the authored value.
    for(const [key,value] of [["height","42px"],["min-height","42px"],["max-height","42px"],["flex","0 0 42px"],["overflow","hidden"]])if(container.style?.getPropertyValue?.(key)!==value)container.style?.setProperty?.(key,value,"important");
    const signature=JSON.stringify([shot,current.selected,current.expanded,text,runText,title,Boolean(ticket),disabled,runDisabled,Boolean(props.disabled)]);
    if(signature===presentationSignature)return;
    presentationSignature=signature;
    hmbAgentSetAttribute(root,"data-shot-number",String(shot.number || 1));hmbAgentSetAttribute(row,"data-shot-number",String(shot.number || 1));
    hmbAgentSetAttribute(row,"data-active",String(current.selected));hmbAgentSetAttribute(row,"data-shot-uuid",shot.shot_uuid || "");
    hmbAgentSetAttribute(select,"data-agent-shot",shot.shot_uuid || "");hmbAgentSetAttribute(select,"aria-expanded",String(current.expanded));hmbAgentSetAttribute(select,"aria-pressed",String(current.selected));
    if(number.textContent!==String(shot.number||0).padStart(2,"0"))number.textContent=String(shot.number||0).padStart(2,"0");
    if(label.textContent!==(shot.name||""))label.textContent=shot.name||"";
    if(status.textContent!==text)status.textContent=text;
    const arrow=current.expanded ? "▾" : "▸";if(chevron.textContent!==arrow)chevron.textContent=arrow;
    if(run.textContent!==runText)run.textContent=runText;
    hmbAgentSetAttribute(run,"aria-label",recovering?"Refresh Agent Shot":running?"Cancel Shot Agent":"Run Shot Agent");hmbAgentSetAttribute(run,"title",title);
    hmbAgentSetAttribute(row,"aria-busy",String(Boolean(ticket)));
    if(select.disabled!==disabled)select.disabled=disabled;
    if(run.disabled!==runDisabled)run.disabled=runDisabled;
    const host=hmbAgentNodeRoot(container),header=host?.querySelector?.(".hmb-agent-dashboard:not(.hmb-agent-shot-accordion)");
    const headerContainer=header?.parentElement,headerProps=headerContainer?.__hmbAgentLatestProps;
    if(headerProps)hmbAgentSetAttribute(header,"data-shot-number",String(hmbAgentDisplayShotNumber(headerContainer,hmbAgentState(headerProps))));
  };
  const send=(kind)=>{
    const previous=channelEntry()?.pending;
    if(disposed || (previous && !(kind==="refresh" && previous.recovering && previous.owner===container)) || typeof props.onChange!=="function")return;
    const current=hmbAgentShotRowState(props);if(!current.shot.shot_uuid || current.routing_pending)return;
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);
    const requestId=Array.from(bytes,byte=>byte.toString(16).padStart(2,"0")).join("");
    const acceptedIds=new Set([...(previous?.acceptedIds || []),requestId]);
    while(acceptedIds.size>256)acceptedIds.delete(acceptedIds.values().next().value);
    const mutationIds=new Set(previous?.mutationIds || []),rejectedIds=new Set(previous?.rejectedIds || []);
    if(kind!=="refresh")mutationIds.add(requestId);
    const ticket={owner:container,kind,requestId,acceptedIds,mutationIds,rejectedIds,shotNumber:current.shot.number,expanded:current.selected ? !current.expanded : true,frames:[],dispatched:false};
    const {rejected_request_id:_rejectedRequest,error_code:_errorCode,...commandState}=current;
    const next={...commandState,action:{kind,request_id:requestId,...(kind==="select" ? {expanded:ticket.expanded} : {})}};
    lastError="";lastRejected=false;
    if(previous)finish(previous);
    channelEntry().pending=ticket;ticket.guardCleanup=hmbGuardPendingAgentEditor(container,ticket);refreshChannel();
    const dispatch=()=>{
      if(disposed || channelEntry()?.pending!==ticket || ticket.dispatched)return;
      if(props.disabled && !["refresh","cancel_selected"].includes(kind)){
        reject(ticket,new Error("Griptape에서 잠긴 요청은 전달하지 않았습니다. 잠금이 해제된 후 다시 선택하세요."));return;
      }
      ticket.dispatched=true;clearTimeout(ticket.fallback);
      let result;try{result=props.onChange(next);}catch(error){recover(ticket,error);return;}
      // Resolution alone only confirms delivery. Keep the row/Run lease until
      // its canonical request ID acknowledges the actual native editor change.
      Promise.resolve(result).catch(error=>recover(ticket,error));
    };
    ticket.frames.push(requestAnimationFrame(()=>{if(!disposed && channelEntry()?.pending===ticket)ticket.frames.push(requestAnimationFrame(dispatch));}));
    // Background tabs can throttle rAF. This fallback still yields to painting;
    // the guarded dispatcher makes rAF/timer/duplicates exactly one command.
    ticket.fallback=setTimeout(dispatch,120);
    ticket.expiry=setTimeout(()=>recover(ticket,new Error("Agent 응답을 확인하지 못했습니다. ↻로 현재 상태를 확인하세요. Agent/Run은 자동 재전송하지 않습니다.")),15000);
  };
  const selectClick=()=>send("select"),runClick=()=>send(channelEntry()?.pending?.recovering ? "refresh" : hmbAgentShotRowState(props).status==="running"?"cancel_selected":"run_selected");
  const keydown=event=>{if(["Backspace","Delete"].includes(event.key))event.stopPropagation?.();};
  const pointerdown=event=>{if(Number(event.button)!==1)event.stopPropagation?.();};
  select.addEventListener("click",selectClick);run.addEventListener("click",runClick);container.addEventListener?.("keydown",keydown);container.addEventListener?.("pointerdown",pointerdown);
  const owner={refresh};
  const handle={update(next){
    if(disposed)return;
    const incoming=hmbAgentShotRowState(next || props),previous=hmbAgentShotRowState(props);
    const same=incoming.shot.channel_uuid===previous.shot.channel_uuid && incoming.shot.shot_uuid===previous.shot.shot_uuid;
    const pending=channelEntry()?.pending;
    const rejected=pending?.owner===container && pending.acceptedIds.has(incoming.rejected_request_id);
    if(rejected){
      pending.rejectedIds.add(incoming.rejected_request_id);
      const error=new Error("샷 목록이 변경되어 요청이 적용되지 않았습니다. 현재 샷을 다시 선택하세요.");
      // A rejection of a later read-only Refresh says nothing about an older
      // uncertain mutation. Keep that lease until its own NACK or exact ACK.
      if([...pending.mutationIds].every(id=>pending.rejectedIds.has(id)))reject(pending,error);
      else recover(pending,error);
    }
    // A late unacknowledged echo must not move the editor highlight backwards.
    if(same && !rejected && (retiredAcks.has(incoming.request_id) || (acceptedAck && !incoming.request_id)))return;
    // The SDK keeps five row parameter IDs while catalog numbering can move a
    // different UUID into a row. An acknowledgement belongs to that UUID,
    // never to the row's previous occupant or its replacement after deletion.
    if(!same){acceptedAck="";retiredAcks.clear();if(!rejected){lastError="";lastRejected=false;}}
    props=next || props;register();
    if(incoming.selected && (!same || !previous.selected || incoming.shot.number!==previous.shot.number || incoming.request_id!==previous.request_id))rememberTheme(incoming);
    const ticket=channelEntry()?.pending;
    if(ticket?.owner===container && (!same || ticket.acceptedIds.has(incoming.request_id))){
      if(ticket.acceptedIds.has(incoming.request_id)){
        for(const id of ticket.acceptedIds)if(id!==incoming.request_id)retiredAcks.add(id);
        if(acceptedAck)retiredAcks.add(acceptedAck);acceptedAck=incoming.request_id;lastError="";
      }
      finish(ticket);
    }else if(incoming.request_id){if(acceptedAck && acceptedAck!==incoming.request_id)retiredAcks.add(acceptedAck);acceptedAck=incoming.request_id;}
    while(retiredAcks.size>256)retiredAcks.delete(retiredAcks.values().next().value);
    refresh();
  },cleanup(){
    if(disposed)return;disposed=true;unregister();
    select.removeEventListener("click",selectClick);run.removeEventListener("click",runClick);container.removeEventListener?.("keydown",keydown);container.removeEventListener?.("pointerdown",pointerdown);container.removeAttribute?.("data-hmb-node-delete-protected");delete container.__hmbAgentRowHandle;container.innerHTML="";
  }};
  container.__hmbAgentRowHandle=handle;register();rememberTheme(state);refresh();return handle;
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
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "agent", allowControl: (target, props, container) => {
    if (hmbAgentNativeHeaderTarget(target)) return true;
    const button = target?.closest?.(".agent-shot-run");
    if (!button) return false;
    const state = hmbAgentShotRowState(props), pending = hmbAgentRowChannels.get(state.shot.channel_uuid)?.pending;
    return state.status === "running" || Boolean(pending?.recovering && pending.owner === container);
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

export default function HMBAgentLibraryWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
