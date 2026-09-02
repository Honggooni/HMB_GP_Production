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
  const catalogMatchesChannel = !bound || catalog.channel_uuid === channelUuid;
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
    shot_catalog: catalogMatchesChannel ? catalog : {},
    shot: {
      channel_uuid: selected ? channelUuid : "",
      shot_uuid: selected ? selected.shot_uuid : "",
      number: selected ? selected.number : 1,
      name: selected ? selected.name : "Only",
    },
  };
}

export function hmbAgentShotOptions(state) {
  const catalog = state?.shot_catalog && typeof state.shot_catalog === "object"
    ? state.shot_catalog : {};
  const options = [{
    key: "__hmb_only__", channel_uuid: "", shot_uuid: "", number: 0,
    name: "Only", revision: 0, only: true,
  }];
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

function hmbSetAgentStatus(container, message = "", detail = "") {
  const status = container?.querySelector?.(".agent-publication-status");
  if (!status) return false;
  status.textContent = String(message || "");
  status.setAttribute?.("title", message ? String(detail?.message || detail || message) : "");
  return true;
}

function hmbAgentExecutionStatus(phase) {
  return ({
    authorizing: "정책 확인 중…",
    preparing: "프롬프트 준비 중…",
    running: "Agent 실행 중…",
  })[String(phase || "")] || "";
}

function renderAgentDashboard(state, container) {
  const paletteShotNumber = hmbAgentPaletteShotNumber(state);
  const executionStatus = hmbAgentExecutionStatus(state.execution_phase);
  return `
    <style>
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
    </style>
    <div class="hmb-agent-dashboard nodrag" data-shot-number="${paletteShotNumber}" data-execution-phase="${hmbAgentEscape(state.execution_phase)}" tabindex="0">
      <header class="agent-topbar">
        <div class="agent-mark" aria-hidden="true"><span>AG</span></div>
        <div class="agent-heading"><b>HMBAgentLibrary</b></div>
        <span class="agent-publication-status" role="status" aria-live="polite" aria-atomic="true">${hmbAgentEscape(executionStatus)}</span>
        <select class="agent-shot-select nodrag" aria-label="Shot"${state.execution_phase ? " disabled" : ""}>${hmbAgentShotOptionsMarkup(state)}</select>
      </header>
    </div>`;
}

function compactAgentWidgetHost(container) {
  if (!container?.style) return;
  try {
    container.style.setProperty("height", "64px", "important");
    container.style.setProperty("min-height", "64px", "important");
    container.style.setProperty("max-height", "64px", "important");
    container.style.setProperty("flex", "0 0 64px", "important");
    container.style.setProperty("flex-basis", "64px", "important");
    container.style.setProperty("overflow", "hidden", "important");
    container.style.setProperty("box-sizing", "border-box", "important");
  } catch (_error) {}
}

function hmbRefreshAgentDashboard(container, props) {
  const root = container?.querySelector?.(".hmb-agent-dashboard");
  if (!root) return false;
  compactAgentWidgetHost(container);
  const state = hmbAgentState(props);
  root.setAttribute("data-shot-number", String(hmbAgentPaletteShotNumber(state)));
  root.setAttribute("data-execution-phase", state.execution_phase || "");
  const select = root.querySelector?.(".agent-shot-select");
  if (select) {
    hmbSyncAgentShotSelect(select, state);
  }
  const error = container.__hmbAgentShotChangeError || "";
  const executionStatus = hmbAgentExecutionStatus(state.execution_phase);
  hmbSetAgentStatus(
    container,
    error ? "Save failed · previous Shot restored" : executionStatus,
    error || executionStatus,
  );
  if (select) select.disabled = Boolean(state.execution_phase);
  hmbPrepareAgentCanvasGestures(container);
  return true;
}

export function hmbPrepareAgentCanvasGestures(container) {
  if (!container) return;
  // The widget surface must not drag the node itself, but it must not retain
  // broad pan/zoom guards from an older mount. With no local pointer or wheel
  // handlers, Griptape owns left/middle-button pan, wheel zoom, and its native
  // grab -> grabbing cursor transition.
  container.classList?.remove("nopan", "nowheel");
  container.classList?.add("nodrag");
  const root = container.querySelector?.(".hmb-agent-dashboard");
  root?.classList?.remove("nopan", "nowheel");
  root?.classList?.add("nodrag");
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
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (hmbAgentDeleteEditingTarget(event)) return false;
  if (!hmbAgentNodeIsSelected(hmbAgentNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

export default function HMBAgentLibraryWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  // The host can call the factory again without replacing the mounted DOM.
  // Keep callbacks/state pointed at the newest props instead of the first
  // mount's closure.
  const incomingProps = props || container.__hmbAgentLatestProps || {};
  if (container.__hmbAgentLatestProps && incomingProps !== container.__hmbAgentLatestProps) {
    container.__hmbAgentShotChangeOwner = Math.max(
      0,
      Number(container.__hmbAgentShotChangeOwner) || 0,
    ) + 1;
  }
  container.__hmbAgentLatestProps = incomingProps;
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
  if (typeof previousCleanup === "function" && hmbRefreshAgentDashboard(container, props)) {
    return {
      cleanup: container.__hmbAgentCleanupProxy,
      update(nextProps) {
        container.__hmbAgentShotChangeOwner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
        props = nextProps || props || {};
        container.__hmbAgentLatestProps = props;
        if (!hmbRefreshAgentDashboard(container, props)) {
          HMBAgentLibraryWidget(container, props);
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

  compactAgentWidgetHost(container);
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  container.innerHTML = hmbScopeWidgetStyleMarkup(
    renderAgentDashboard(hmbAgentState(props), container),
    ".hmb-agent-dashboard",
  );
  hmbPrepareAgentCanvasGestures(container);
  // Discovery asks a local publisher to refresh its backend state. The
  // process-global response is deliberately not observed by this widget.
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    try { window.dispatchEvent(new CustomEvent("hmb-shot-routing-discover-v1")); } catch (_error) {}
  }
  const shotSelect = container.querySelector?.(".agent-shot-select");
  const shotChangeHandler = () => {
    const liveProps = container.__hmbAgentLatestProps || props || {};
    const option = hmbAgentShotOptions(hmbAgentState(liveProps)).find((item) => item.key === shotSelect?.value);
    if (!option || typeof liveProps?.onChange !== "function") {
      hmbRefreshAgentDashboard(container, liveProps);
      return;
    }
    const previousProps = liveProps;
    const next = hmbAgentState(liveProps);
    next.shot = option.only ? {
      channel_uuid: "", shot_uuid: "", number: 1, name: "Only",
    } : {
      channel_uuid: option.channel_uuid,
      shot_uuid: option.shot_uuid,
      number: option.number,
      name: option.name,
    };
    const owner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
    container.__hmbAgentShotChangeOwner = owner;
    const optimisticProps = { ...liveProps, value: next, parameterValue: next, defaultValue: next };
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
      props = previousProps;
      container.__hmbAgentLatestProps = previousProps;
      container.__hmbAgentShotChangeError = String(error?.message || error || "Shot selection publication failed");
      hmbRefreshAgentDashboard(container, previousProps);
      return true;
    };
    let result;
    try {
      result = liveProps.onChange(next);
    } catch (error) {
      rollback(error);
      return;
    }
    accept();
    if (result && typeof result.then === "function") {
      Promise.resolve(result).catch(rollback);
    }
  };
  shotSelect?.addEventListener?.("change", shotChangeHandler);
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
  }
  const stopNodeDeleteShortcut = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorNodeSelection = (event) => {
    if (Number(event?.button) !== 1) event.stopPropagation?.();
  };
  container.addEventListener?.("keydown", stopNodeDeleteShortcut);
  container.addEventListener?.("pointerdown", stopInteriorNodeSelection);

  const cleanup = () => {
    disposed = true;
    if (container.__hmbAgentLifecycleEpoch === lifecycleEpoch) {
      container.__hmbAgentLifecycleEpoch = lifecycleEpoch + 1;
    }
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
    }
    container.removeEventListener?.("keydown", stopNodeDeleteShortcut);
    container.removeEventListener?.("pointerdown", stopInteriorNodeSelection);
    shotSelect?.removeEventListener?.("change", shotChangeHandler);
    container.removeAttribute?.("data-hmb-node-delete-protected");
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
  return {
    cleanup: container.__hmbAgentCleanupProxy,
    update(nextProps) {
      container.__hmbAgentShotChangeOwner = Math.max(0, Number(container.__hmbAgentShotChangeOwner) || 0) + 1;
      props = nextProps || props || {};
      container.__hmbAgentLatestProps = props;
      if (!hmbRefreshAgentDashboard(container, props)) {
        HMBAgentLibraryWidget(container, props);
      }
    },
  };
}
