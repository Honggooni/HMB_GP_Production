"""Synchronize the standalone widget deletion-safety contract without imports.

Griptape evaluates each registered JS widget as a standalone data module, so
relative JS imports cannot supply this shared lease. Keep one generated literal
identical in the visible HMB widgets. --check is read-only.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WIDGETS = (
    "HMBAgentLibraryWidget.js", "HMBColorLUTLibraryWidget.js",
    "HMBFinishLookLibraryWidget.js", "HMBImageAssetLibraryWidget.js",
    "HMBImageBashWidget.js", "HMBImageGenerationWidget.js",
    "HMBPromptLibraryScopedBindingWidget.js", "HMBSeedanceGenerationWidget.js",
    "HMBVideoPickerLibraryWidget_v032.js",
    "HMBAnalysisAgentWidget.js",
)
BEGIN = "// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN"
END = "// HMB_NATIVE_STOCK_SAFETY_V1_END"
IMPLEMENTATION = "hmbNativeStockSafetyImplementation"
SAFETY_SOURCE = r"""// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN
// Public DOM capture only. Never inspect React internals, replay Delete, or
// pretend a disk/Git update installed the native editor safety contract.
function hmbAcquireNativeStockSafety(container) {
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!doc?.documentElement || !win?.addEventListener || !doc.createElement) return null;
  const key = "__HMB_NATIVE_STOCK_SAFETY_V1__";
  let shared = doc[key];
  if (!shared) {
    const owners = new Set(), identities = new Set();
    let parents = new WeakSet(), awaitingMount = false;
    let contextNode = null, notice = null, noticeTimer = null, disposed = false;
    const nativeReady = () => doc.documentElement.getAttribute("data-hmb-native-deletion-guard") === "engine-preflight"
      && doc.documentElement.getAttribute("data-hmb-native-deletion-protection-version") === "2";
    const rootOf = value => value?.closest?.(".react-flow__node[data-id]") || null;
    const currentRoot = owner => owner.container?.isConnected ? rootOf(owner.container) : null;
    const trackParents = element => {
      for (let parent = element?.parentNode; parent && !parents.has(parent); parent = parent.parentNode) {
        parents.add(parent);
      }
    };
    const roots = () => {
      parents = new WeakSet();
      awaitingMount = false;
      for (const owner of owners) {
        owner.node = currentRoot(owner);
        if (owner.node) identities.add(owner.node);
        if (owner.container.isConnected) trackParents(owner.container);
        else awaitingMount = true;
      }
      // A stock fold/virtualized widget unmount is not a node deletion. Keep
      // its exact outer DOM identity until that node actually leaves the view.
      for (const node of identities) {
        if (!node.isConnected) identities.delete(node);
        else trackParents(node);
      }
      return identities;
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
    // Card and prompt edits occur below the widget host and cannot move its
    // outer node. Still observe reparenting, folds, native markers and late mounts.
    const observer = typeof win.MutationObserver === "function" ? new win.MutationObserver(records => {
      if (awaitingMount || records.some(record => record.type === "attributes" || parents.has(record.target))) sync();
    }) : null;
    observer?.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-hmb-native-deletion-guard", "data-hmb-native-deletion-protection-version", "data-id"], childList: true, subtree: true });
    win.addEventListener("keydown", keydown, true); win.addEventListener("click", click, true); win.addEventListener("contextmenu", contextmenu, true);
    shared = { owners, sync, refresh(owner) {
      if (currentRoot(owner) !== owner.node) sync();
    }, release(owner) {
      owner.active = false; owners.delete(owner);
      sync();
    } };
    doc[key] = shared;
  }
  const owner = { container, active: true };
  shared.owners.add(owner);
  shared.sync();
  return { refresh() { if (owner.active) (shared.refresh || shared.sync)(owner); }, cleanup() { if (owner.active) shared.release(owner); } };
}

// Griptape loads each widget as a separate module. One selection per editor
// document also covers stock parameter fields rendered beside an HMB widget.
function hmbAcquireCanvasWheel(container) {
  const node = container?.matches?.(".widget-container") && container.closest?.(".react-flow__node");
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!node?.closest?.(".react-flow") || !win?.WheelEvent) return null;
  const key = "__HMB_CANVAS_WHEEL_SELECTION_V1__";
  let router = doc[key];
  if (!router) {
    const nodes = new Map();
    let selected = null;
    const activeScroll = "data-hmb-active-scroll";
    const activeSelector = `[${activeScroll}]`;
    const outlineStyle = doc.createElement("style");
    outlineStyle.textContent = `.react-flow .react-flow__node.nowheel ${activeSelector} {
      outline: 2px solid #4dd8ff !important;
      outline-offset: -2px !important;
      anchor-name: --hmb-selected-viewport;
      overscroll-behavior: contain !important;
    }
    .react-flow [data-hmb-scroll-frame] {
      position: absolute !important;
      position-anchor: --hmb-selected-viewport;
      top: anchor(top); left: anchor(left);
      width: anchor-size(width); height: anchor-size(height);
      box-sizing: border-box; border: 2px solid #4dd8ff;
      padding: 0; margin: 0; background: transparent;
      pointer-events: none !important; z-index: 1000;
    }`;
    doc.head.appendChild(outlineStyle);
    // Paint above composited thumbnails and sticky headers, outside the scrolling
    // content. CSS anchors follow native scroll, resize and React Flow zoom.
    const frame = doc.createElement("span");
    frame.setAttribute("data-hmb-scroll-frame", "");
    frame.setAttribute("aria-hidden", "true");
    const anchored = win.CSS?.supports("position-anchor", "--hmb-selected-viewport")
      && win.CSS.supports("width", "anchor-size(width)");
    const modal = "dialog,[role='dialog'],[aria-modal='true'],[role='menu'],[role='listbox']:not(select),[data-registration-backdrop],[data-refresh-review-backdrop]";
    const hasScroll = (element, horizontal) => {
      const room = horizontal ? element.scrollWidth - element.clientWidth : element.scrollHeight - element.clientHeight;
      if (room <= 1) return false;
      const style = win.getComputedStyle(element);
      return /^(auto|scroll|overlay)$/.test(horizontal ? style.overflowX : style.overflowY);
    };
    const canScroll = surface => hasScroll(surface, false) || hasScroll(surface, true);
    const surfaceAt = (target, root) => {
      const group = target.closest?.("[data-hmb-scroll-viewport]");
      if (group && root.contains(group)) return group;
      for (let el = target; el && el !== root; el = el.parentElement) {
        if (el.matches?.("textarea")) return el;
        if (el.matches?.("select,input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit])")) return null;
        if (canScroll(el)) return el;
      }
      return null;
    };
    const syncOutline = () => {
      const surface = selected?.surface;
      if (!surface?.isConnected) return false;
      const scrollable = canScroll(surface);
      surface.toggleAttribute(activeScroll, scrollable);
      if (anchored && scrollable && frame.previousElementSibling !== surface) {
        frame.style.borderRadius = win.getComputedStyle(surface).borderRadius;
        surface.after(frame);
      } else if (!scrollable) {
        frame.remove();
      }
      return scrollable;
    };
    const resized = win.ResizeObserver && new win.ResizeObserver(syncOutline);
    const clearOutline = () => {
      const {root, surface} = selected;
      frame.remove();
      surface.removeAttribute(activeScroll);
      for (const copy of root.querySelectorAll(activeSelector)) copy.removeAttribute(activeScroll);
      for (const copy of root.querySelectorAll("[data-hmb-scroll-frame]")) copy.remove();
    };
    const restoreViewport = () => {
      const {root, key} = selected;
      if (!key || !root.isConnected) return false;
      const matches = [...root.querySelectorAll("[data-hmb-wheel-key]")].filter(el => el.dataset.hmbWheelKey === key);
      if (matches.length !== 1) return false;
      activate(root, matches[0]);
      return true;
    };
    const changed = win.MutationObserver && new win.MutationObserver(records => {
      if (!selected) return;
      const {root, surface} = selected;
      if (!root.contains(surface)) {
        if (restoreViewport()) return;
        changed.disconnect();
        resized?.disconnect();
        clearOutline();
        // Give the renderer one turn to attach the replacement. Release the
        // detached card tree even if there is no subsequent pointer event.
        const detached = selected;
        win.setTimeout(() => {
          if (selected === detached && !restoreViewport()) clear();
        }, 0);
        return;
      }
      if (selected.key !== surface.dataset.hmbWheelKey) { clear(); return; }
      // A cloned field inherits attributes, but only the original owns the wheel.
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added.nodeType !== 1) continue;
          if (added !== frame && added.hasAttribute("data-hmb-scroll-frame")) {
            added.remove();
            continue;
          }
          if (added !== surface) added.removeAttribute(activeScroll);
          for (const copy of added.querySelectorAll(`${activeSelector},[data-hmb-scroll-frame]`)) {
            if (copy.hasAttribute("data-hmb-scroll-frame")) {
              if (copy !== frame) copy.remove();
            } else if (copy !== surface) copy.removeAttribute(activeScroll);
          }
        }
      }
      if (records.some(record => surface.contains(record.target))
          || (anchored && surface.hasAttribute(activeScroll) && frame.previousElementSibling !== surface)) syncOutline();
    });
    const clear = () => {
      if (!selected) return;
      const {surface, root, addedNoWheel, previousOverscroll} = selected;
      changed?.disconnect();
      resized?.disconnect();
      surface.removeEventListener("input", syncOutline, true);
      surface.removeEventListener("load", syncOutline, true);
      clearOutline();
      if (addedNoWheel && root.classList.contains("nowheel")) root.classList.remove("nowheel");
      if (surface.style.overscrollBehavior === "contain") surface.style.overscrollBehavior = previousOverscroll;
      selected = null;
    };
    const activate = (root, surface) => {
      if (surface === selected?.surface) return;
      clear();
      if (!surface) return;
      // Some widget renderers use the viewport className as their scroll
      // restoration key. Put the native wheel filter on the stock node only.
      selected = {root, surface, key:surface.dataset.hmbWheelKey, addedNoWheel: !root.classList.contains("nowheel"), previousOverscroll: surface.style.overscrollBehavior};
      if (selected.addedNoWheel) root.classList.add("nowheel");
      surface.style.overscrollBehavior = "contain";
      syncOutline();
      surface.addEventListener("input", syncOutline, true);
      surface.addEventListener("load", syncOutline, true);
      resized?.observe(surface);
      changed?.observe(root, {subtree:true, childList:true});
      changed?.observe(surface, {subtree:true, childList:true, characterData:true,
        attributes:true, attributeFilter:[activeScroll,"data-hmb-wheel-key","class","style","hidden","rows"]});
    };
    const select = event => {
      if (event.button !== 0 || event.isPrimary === false) return;
      const target = event.target, root = target?.closest?.(".react-flow__node");
      activate(root, nodes.has(root) && !target.closest(modal) ? surfaceAt(target, root) : null);
    };
    const actionAt = target => target.closest("button,textarea,[data-asset],[data-asset-key],[data-video-uid],[data-group-path],[data-instance]");
    const actionKey = element => element && Array.from(element.attributes)
      .filter(a => a.name !== activeScroll && (a.name === "id" || a.name === "name" || a.name.startsWith("data-")))
      .map(a => JSON.stringify([a.name,a.value])).sort().join(",");
    const afterClick = event => {
      const current = selected;
      if (event.button !== 0 || !current?.surface.contains(event.target)) return;
      const action = actionAt(event.target), identity = actionKey(action);
      if (!identity) return;
      const shotAt = el => actionKey(el.closest("[data-shot-row],[data-workspace-uuid],[data-shot-uuid]"));
      const shot = shotAt(action);
      // A card/folder button can repaint its list on click. Reacquire only
      // the same action and viewport under this completed pointer gesture.
      const {clientX, clientY} = event;
      win.setTimeout(() => {
        if (selected !== current || current.surface.isConnected) return;
        const hit = doc.elementFromPoint(clientX, clientY);
        if (!hit || hit.closest(".react-flow__node") !== current.root || hit.closest(modal)) return;
        const nextAction = actionAt(hit), next = surfaceAt(hit, current.root);
        if (next && next.dataset.hmbWheelKey === current.key && next.tagName === current.surface.tagName && next.className === current.surface.className
            && nextAction?.tagName === action.tagName && actionKey(nextAction) === identity
            && shotAt(nextAction) === shot) activate(current.root, next);
      }, 0);
    };
    const escape = event => { if (event.key === "Escape") clear(); };
    const wheel = event => {
      const target = event.target, root = target?.closest?.(".react-flow__node");
      if (!nodes.has(root) || event.defaultPrevented || target.closest(modal)) return;
      if (selected && !selected.root.contains(selected.surface) && !restoreViewport()) clear();
      if (selected && selected.key !== selected.surface.dataset.hmbWheelKey) clear();
      if (!event.ctrlKey && !event.metaKey && selected?.root === root && selected.surface.contains(target)) {
        const surface = selected.surface;
        if (surfaceAt(target, root) === surface && syncOutline()) {
          // Keep native scrolling and widget handlers (virtual lists and
          // horizontal card strips) on the original, trusted event.
          if (!root.classList.contains("nowheel")) root.classList.add("nowheel");
          return;
        }
      }
      // Stock parameters can stop wheel at React's capture phase, before
      // the widget sees it. Deliver one event at the same pointer position
      // to the native canvas handler, above those parameter-specific guards.
      event.preventDefault();
      event.stopPropagation();
      const canvasLayer = root.closest(".react-flow__nodes") || root.parentElement;
      canvasLayer.dispatchEvent(new win.WheelEvent("wheel", event));
    };
    doc.addEventListener("pointerdown", select, true);
    doc.addEventListener("click", afterClick, true);
    doc.addEventListener("keydown", escape, true);
    doc.addEventListener("wheel", wheel, {capture: true, passive: false});
    router = {acquire(root) {
      nodes.set(root, (nodes.get(root) || 0) + 1);
      return () => {
        const count = nodes.get(root) - 1;
        if (count) nodes.set(root, count);
        else {
          nodes.delete(root);
          if (selected?.root === root) clear();
        }
        if (nodes.size) return;
        doc.removeEventListener("pointerdown", select, true);
        doc.removeEventListener("click", afterClick, true);
        doc.removeEventListener("keydown", escape, true);
        doc.removeEventListener("wheel", wheel, true);
        outlineStyle.remove();
        delete doc[key];
      };
    }};
    doc[key] = router;
  }
  return router.acquire(node);
}

function hmbNativeStockSafetyContract(container, props, mount) {
  const previous = container?.__hmbNativeStockSafety;
  const lease = previous?.active ? previous.lease : hmbAcquireNativeStockSafety(container);
  // The stock WidgetLoader adds nowheel to the entire widget host. Leave
  // wheel ownership to each HMB widget's concrete scroll surfaces instead.
  const canvasHost = container?.matches?.(".widget-container") && container.closest?.(".react-flow__node") ? container : null;
  const restoreWheelClass = previous?.active ? previous.restoreWheelClass : canvasHost?.classList.contains("nowheel");
  let handle;
  try { handle = mount(container, props); }
  catch (error) { if (!previous?.active) lease?.cleanup(); throw error; }
  lease?.refresh();
  if (!lease) return handle;
  const allowCanvasWheel = () => {
    if (canvasHost?.classList.contains("nowheel")) canvasHost.classList.remove("nowheel");
  };
  allowCanvasWheel();
  if (previous?.active && previous.handle === handle) return previous.proxy;
  if (previous) previous.active = false;
  const releaseWheel = previous?.releaseWheel || hmbAcquireCanvasWheel(container);
  const state = { active: true, lease, handle, restoreWheelClass, releaseWheel, proxy: null };
  state.proxy = {
    update(next) {
      if (!state.active) return;
      handle?.update?.(next);
      allowCanvasWheel();
      lease.refresh();
    },
    cleanup() {
      if (!state.active) return;
      state.active = false;
      try { if (typeof handle === "function") handle(); else handle?.cleanup?.(); }
      finally {
        releaseWheel?.();
        lease.cleanup();
        if (container.__hmbNativeStockSafety === state) {
          if (restoreWheelClass) canvasHost?.classList.add("nowheel");
          delete container.__hmbNativeStockSafety;
        }
      }
    },
  };
  container.__hmbNativeStockSafety = state;
  return state.proxy;
}
// HMB_NATIVE_STOCK_SAFETY_V1_END
"""

def render(source: str, filename: str) -> str:
    normalized = source.replace("\r\n", "\n")
    if BEGIN in normalized:
        start = normalized.index(BEGIN)
        end = normalized.index(END, start) + len(END)
        normalized = normalized[:start] + normalized[end:]
        normalized = re.sub(r"\nexport default function \w+\(container, props\) \{\n  return hmbNativeStockSafetyContract\(container, props, hmbNativeStockSafetyImplementation\);\n\}\n?", "\n", normalized)
        match = re.search(r"function hmbNativeStockSafetyImplementation\(", normalized)
        if not match:
            raise ValueError(f"Missing generated implementation: {filename}")
        name = filename.removesuffix("_v032.js").removesuffix(".js")
    else:
        match = re.search(r"export default function (\w+)\(", normalized)
        if not match:
            raise ValueError(f"Missing standalone widget entrypoint: {filename}")
        name = match.group(1)
        normalized = normalized[:match.start()] + normalized[match.start():].replace(
            "export default function " + name + "(", "function " + IMPLEMENTATION + "(", 1)
    wrapper = (f"\nexport default function {name}(container, props) {{\n"
               "  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);\n}\n")
    return normalized.rstrip() + "\n\n" + SAFETY_SOURCE.rstrip() + "\n" + wrapper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = []
    for name in (*WIDGETS, "HMBSoundLibraryWidget.js"):
        target = ROOT / "widgets" / name
        source = target.read_text(encoding="utf-8")
        if name == "HMBSoundLibraryWidget.js":
            start = source.index(BEGIN)
            end = source.index(END, start) + len(END)
            desired = source[:start] + SAFETY_SOURCE.rstrip() + source[end:]
        else:
            desired = render(source, name)
        if source != desired:
            changed.append(name)
            if not args.check:
                with target.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(desired)
    if args.check and changed:
        raise SystemExit("Native stock safety is stale: " + ", ".join(changed))
    print(f"HMB native stock safety: {'PASS' if args.check else 'synchronized'} ({len(WIDGETS) + 1} widgets)")


if __name__ == "__main__":
    main()
