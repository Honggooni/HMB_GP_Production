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

function hmbNativeStockSafetyImplementation(element, _context) {
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
      const title = doc.createElement("strong"); title.textContent = "HMB 편집기·삭제 보호 확인이 필요합니다";
      const text = doc.createElement("p");
      text.textContent = "Override 업데이트 로그에서 current/applied를 확인하세요. UI 또는 엔진 보호 상태를 확인하지 못해 감지된 HMB 노드 삭제 시도를 중단했습니다. 작업 저장 후 Griptape 완전 종료·재시작하세요. current/applied는 디스크 파일 상태이며 현재 화면의 통합 상태를 보장하지 않습니다. 실패 시 로그의 원인을 확인하세요. 이 안내만으로 다른 삭제 경로의 엔진 보호가 준비됐다고 보장할 수 없습니다.";
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
      badge.setAttribute("aria-label", "HMB Override 업데이트·재시작 및 삭제 보호 상태 확인");
      badge.textContent = "HMB UI·삭제 보호 상태 확인";
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

export default function HMBImageGenerationWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
