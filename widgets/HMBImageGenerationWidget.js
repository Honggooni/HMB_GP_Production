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

/** Static HMB header. Native SDK parameters own all image controls and state. */
const mountedHeaders = new WeakMap();
const headerHostStyles = [
  ["height", "64px"], ["min-height", "64px"], ["max-height", "64px"],
  ["flex-grow", "0"], ["flex-shrink", "0"], ["flex-basis", "64px"], ["box-sizing", "border-box"],
];

function compactHeaderHost(element) {
  if (!element.style) return;
  for (const [name, value] of headerHostStyles) {
    if (element.style.getPropertyValue(name) !== value || element.style.getPropertyPriority(name) !== "important") {
      element.style.setProperty(name, value, "important");
    }
  }
}

export default function HMBImageGenerationWidget(element, _context) {
  if (!element?.ownerDocument) return { update() {}, cleanup() {} };
  const current = mountedHeaders.get(element);
  if (current?.active && current.header.parentNode === element) {
    compactHeaderHost(element);
    current.nativeHeader.refresh();
    return current.handle;
  }
  current?.handle.cleanup();

  // The editor's widget carrier reserves its own minimum height. Sizing only
  // the painted header leaves that reservation below it (the blank strip).
  // Compact only our carrier; do not resize the node, its parents or controls.
  const originalHostStyles = headerHostStyles.map(([name]) => [
    name, element.style?.getPropertyValue(name) || "", element.style?.getPropertyPriority(name) || "",
  ]);
  compactHeaderHost(element);

  const header = element.ownerDocument.createElement("div");
  header.className = "hmb-image-generation-header";
  header.setAttribute("aria-label", "HMBImageGeneration");
  header.innerHTML = `
    <style>
      .hmb-image-generation-header{
        position:relative;box-sizing:border-box;width:100%;min-width:0;
        height:64px;min-height:64px;max-height:64px;overflow:hidden;
        border:1px solid rgba(244,114,182,.5);border-radius:11px;
        background:radial-gradient(circle at 8% -45%,rgba(244,114,182,.25),transparent 54%),linear-gradient(90deg,rgba(244,114,182,.2),rgba(14,23,38,.96) 46%,#060912);
        color:#e6edf7;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 24px rgba(0,0,0,.24),0 0 18px rgba(244,114,182,.18);
        font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;
        user-select:none;pointer-events:none;
      }
      .hmb-image-generation-header__row{
        box-sizing:border-box;height:100%;min-width:0;display:flex;
        align-items:center;gap:11px;padding:8px 13px;
      }
      .hmb-image-generation-header__badge{
        box-sizing:border-box;flex:0 0 35px;width:35px;height:35px;
        display:grid;place-items:center;border:1px solid rgba(244,114,182,.52);
        border-radius:8px;background:linear-gradient(145deg,rgba(244,114,182,.14),rgba(5,9,16,.86));
        color:#F472B6;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px rgba(244,114,182,.19);
        font-size:9px;font-weight:950;letter-spacing:.06em;
      }
      .hmb-image-generation-header__title{
        box-sizing:border-box;flex:1 1 auto;min-width:0;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap;color:#e6edf7;font-size:14px;font-weight:850;
      }
      .hmb-image-generation-header__native-identity,.hmb-image-generation-header__native-actions{display:none;min-width:0;pointer-events:auto;--node-header-text:#e6edf7}
      .hmb-image-generation-header[data-hmb-native-header=active]{border:0;border-radius:0;box-shadow:none}
      .hmb-image-generation-header[data-hmb-native-header=active] .hmb-image-generation-header__badge,
      .hmb-image-generation-header[data-hmb-native-header=active] .hmb-image-generation-header__title{display:none}
      .hmb-image-generation-header[data-hmb-native-header=active] .hmb-image-generation-header__native-identity{display:flex;align-items:center;flex:1 1 auto}
      .hmb-image-generation-header[data-hmb-native-header=active] .hmb-image-generation-header__native-actions{display:flex;align-items:center;flex:0 0 auto}
      .hmb-image-generation-header__native-identity>div{min-width:0;max-width:100%}
    </style>
    <div class="hmb-image-generation-header__row group">
      <span class="hmb-image-generation-header__badge" aria-hidden="true">IG</span>
      <span class="hmb-image-generation-header__title">HMBImageGeneration</span>
      <div class="hmb-image-generation-header__native-identity" data-hmb-native-identity></div>
      <div class="hmb-image-generation-header__native-actions nodrag" data-hmb-native-actions></div>
    </div>`;
  element.appendChild(header);

  const nativeHeader = hmbInstallNativeHeaderBridge(element, "HMBImageGeneration", ".hmb-image-generation-header");
  const state = { active: true, header, nativeHeader, handle: null };
  const handle = {
    // The header is deliberately independent of task/provider/lock changes.
    update() { if (state.active) { compactHeaderHost(element); nativeHeader.refresh(); } },
    cleanup() {
      if (!state.active) return;
      state.active = false;
      nativeHeader.cleanup();
      if (header.parentNode === element) header.remove();
      if (mountedHeaders.get(element) === state) {
        mountedHeaders.delete(element);
        for (const [name, value, priority] of originalHostStyles) {
          const owned = headerHostStyles.find(([property]) => property === name)?.[1];
          if (element.style?.getPropertyValue(name) !== owned || element.style?.getPropertyPriority(name) !== "important") continue;
          if (value) element.style.setProperty(name, value, priority);
          else element.style.removeProperty(name);
        }
      }
    },
  };
  state.handle = handle;
  mountedHeaders.set(element, state);
  return handle;
}
