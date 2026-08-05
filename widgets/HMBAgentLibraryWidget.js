const HMB_UI_THEME_STORAGE_KEY = "hmb_gp_production_ui_theme";
const HMB_UI_THEME_EVENT = "hmb-gp-production-theme-change";

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

function hmbNormalizeUiTheme(value) {
  return String(value || "").toUpperCase() === "T" ? "T" : "P";
}

function hmbReadSharedUiTheme(fallback = "P") {
  try {
    if (typeof window !== "undefined") {
      if (window.__hmbGpProductionUiTheme === "P" || window.__hmbGpProductionUiTheme === "T") {
        return hmbNormalizeUiTheme(window.__hmbGpProductionUiTheme);
      }
      if (window.sessionStorage) {
        const stored = window.sessionStorage.getItem(HMB_UI_THEME_STORAGE_KEY);
        if (stored === "P" || stored === "T") {
          window.__hmbGpProductionUiTheme = stored;
          return stored;
        }
      }
    }
  } catch (_error) {}
  return hmbNormalizeUiTheme(fallback);
}

function renderAgentDashboard(theme) {
  return `
    <style>
      .hmb-agent-dashboard{--hmb-bg-top:#0b1020;--hmb-bg-bottom:#060912;--hmb-line:rgba(148,163,184,.19);--hmb-accent:#22d3ee;--hmb-highlight:#f472b6;--hmb-text:#e6edf7;--hmb-muted:#8fa3b8;--hmb-haze:rgba(168,85,247,.2);--hmb-head-wash:rgba(72,35,101,.5);--hmb-mark-bg:rgba(8,145,178,.12);--hmb-mark-line:rgba(34,211,238,.7);--hmb-mark-glow:rgba(34,211,238,.16);--hmb-chip-bg:rgba(131,24,67,.2);--hmb-chip-line:rgba(244,114,182,.46);--hmb-chip-text:#fbcfe8;--hmb-chip-glow:rgba(244,114,182,.18);container-type:inline-size;position:relative;width:100%;height:64px;overflow:hidden;border:1px solid var(--hmb-line);border-radius:11px;background:radial-gradient(circle at 8% -42%,var(--hmb-haze),transparent 54%),linear-gradient(90deg,var(--hmb-head-wash),rgba(14,23,38,.95) 46%,var(--hmb-bg-bottom));color:var(--hmb-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 8px 24px rgba(0,0,0,.24),0 0 18px var(--hmb-chip-glow);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;box-sizing:border-box;user-select:none}
      .hmb-agent-dashboard[data-theme="T"]{--hmb-bg-top:#091525;--hmb-bg-bottom:#050a12;--hmb-line:rgba(96,165,250,.3);--hmb-accent:#38bdf8;--hmb-highlight:#60a5fa;--hmb-haze:rgba(37,99,235,.24);--hmb-head-wash:rgba(37,99,235,.25);--hmb-mark-bg:rgba(37,99,235,.17);--hmb-mark-line:rgba(56,189,248,.66);--hmb-mark-glow:rgba(56,189,248,.17);--hmb-chip-bg:rgba(37,99,235,.2);--hmb-chip-line:rgba(96,165,250,.48);--hmb-chip-text:#dbeafe;--hmb-chip-glow:rgba(37,99,235,.2)}
      .hmb-agent-dashboard *{box-sizing:border-box;min-width:0}.hmb-agent-dashboard .agent-topbar{position:relative;height:100%;display:flex;align-items:center;gap:11px;padding:8px 13px}.hmb-agent-dashboard .agent-topbar::after{content:"";position:absolute;right:13px;bottom:0;left:13px;height:1px;background:linear-gradient(90deg,var(--hmb-accent),var(--hmb-highlight),transparent);opacity:.32}.hmb-agent-dashboard .agent-mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;overflow:hidden;border:1px solid var(--hmb-mark-line);border-radius:8px;background:linear-gradient(145deg,var(--hmb-mark-bg),rgba(5,9,16,.86));color:var(--hmb-accent);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px var(--hmb-mark-glow);font-size:10px;font-weight:950;letter-spacing:.08em}.hmb-agent-dashboard .agent-heading{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:3px;overflow:hidden}.hmb-agent-dashboard .agent-heading b,.hmb-agent-dashboard .agent-heading span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-agent-dashboard .agent-heading b{color:var(--hmb-text);font-size:15px;font-weight:850;line-height:1;letter-spacing:.01em}.hmb-agent-dashboard .agent-heading span{color:var(--hmb-muted);font-size:9px;font-weight:650;line-height:1;letter-spacing:.055em}.hmb-agent-dashboard .agent-native-badge{flex:0 1 auto;max-width:190px;height:27px;display:flex;align-items:center;gap:6px;margin-left:auto;padding:0 10px;border:1px solid var(--hmb-chip-line);border-radius:99px;background:linear-gradient(180deg,rgba(255,255,255,.04),transparent),var(--hmb-chip-bg);color:var(--hmb-chip-text);box-shadow:inset 0 1px 0 rgba(255,255,255,.045),0 0 12px var(--hmb-chip-glow);font-size:8px;font-weight:900;letter-spacing:.055em;white-space:nowrap}.hmb-agent-dashboard .agent-native-badge i{flex:0 0 5px;width:5px;height:5px;border-radius:50%;background:var(--hmb-highlight);box-shadow:0 0 8px var(--hmb-highlight)}.hmb-agent-dashboard .agent-native-badge span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      @container(max-width:360px){.hmb-agent-dashboard .agent-native-badge{flex-basis:27px;width:27px;padding:0;justify-content:center}.hmb-agent-dashboard .agent-native-badge span{display:none}}@container(max-width:280px){.hmb-agent-dashboard .agent-heading span{display:none}.hmb-agent-dashboard .agent-heading b{font-size:13px}}
    </style>
    <div class="hmb-agent-dashboard nodrag" data-theme="${theme}" tabindex="0">
      <header class="agent-topbar">
        <div class="agent-mark" aria-hidden="true"><span>AG</span></div>
        <div class="agent-heading"><b>HMBAgentLibrary</b><span>DISPLAY → FINAL TEXT</span></div>
        <div class="agent-native-badge"><i aria-hidden="true"></i><span>AGENT STATE · CHAIN</span></div>
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

function hmbRefreshAgentDashboard(container) {
  const root = container?.querySelector?.(".hmb-agent-dashboard");
  if (!root) return false;
  compactAgentWidgetHost(container);
  root.setAttribute("data-theme", hmbReadSharedUiTheme());
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
  if (typeof previousCleanup === "function" && hmbRefreshAgentDashboard(container)) {
    return {
      cleanup: container.__hmbAgentCleanupProxy,
      update(nextProps) {
        props = nextProps || props || {};
        if (!hmbRefreshAgentDashboard(container)) {
          HMBAgentLibraryWidget(container, props);
        }
      },
    };
  }
  if (typeof previousCleanup === "function") previousCleanup();

  compactAgentWidgetHost(container);
  container.setAttribute?.("data-hmb-node-delete-protected", "true");
  container.innerHTML = hmbScopeWidgetStyleMarkup(
    renderAgentDashboard(hmbReadSharedUiTheme()),
    ".hmb-agent-dashboard",
  );
  hmbPrepareAgentCanvasGestures(container);
  const sharedThemeHandler = (event) => {
    const root = container.querySelector(".hmb-agent-dashboard");
    if (!root) return;
    const eventTheme = event && event.detail ? event.detail.theme : "";
    root.setAttribute("data-theme", hmbNormalizeUiTheme(eventTheme || hmbReadSharedUiTheme()));
  };
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener(HMB_UI_THEME_EVENT, sharedThemeHandler);
  }
  const stopSelectedNodeDeleteShortcut = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
  }
  const stopNodeDeleteShortcut = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorNodeSelection = (event) => event.stopPropagation();
  container.addEventListener?.("keydown", stopNodeDeleteShortcut);
  container.addEventListener?.("pointerdown", stopInteriorNodeSelection);

  const cleanup = () => {
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener(HMB_UI_THEME_EVENT, sharedThemeHandler);
      window.removeEventListener("keydown", stopSelectedNodeDeleteShortcut, true);
    }
    container.removeEventListener?.("keydown", stopNodeDeleteShortcut);
    container.removeEventListener?.("pointerdown", stopInteriorNodeSelection);
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
    container.innerHTML = "";
  };
  container.__hmbAgentCleanup = cleanup;
  return {
    cleanup: container.__hmbAgentCleanupProxy,
    update(nextProps) {
      props = nextProps || props || {};
      if (!hmbRefreshAgentDashboard(container)) {
        HMBAgentLibraryWidget(container, props);
      }
    },
  };
}
