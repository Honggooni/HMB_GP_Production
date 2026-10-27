"""Synchronize the standalone widget deletion-safety contract without imports.

Griptape evaluates each registered JS widget as a standalone data module, so
relative JS imports cannot supply this shared lease. Keep one generated literal
identical in the nine visible HMB widgets. --check is read-only.
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
      const title = doc.createElement("strong"); title.textContent = "HMB 통합 설치가 필요합니다";
      const text = doc.createElement("p");
      text.textContent = "Git Update만으로는 네이티브 UI 패치가 적용되지 않습니다. 엔진 응답 전에 화면에서 노드가 사라지는 문제를 막기 위해 HMB 노드 삭제를 일시 중단했습니다. 작업 저장 → Griptape 완전 종료 → Runtime ZIP의 Install_HMB_GP_Production.ps1 실행 → 재시작 후 다시 삭제하세요. 연결된 노드는 계속 보호되며, 연결이 없는 노드는 통합 설치 후 정상 삭제됩니다.";
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
      badge.setAttribute("aria-label", "HMB 네이티브 UI 통합 설치 안내");
      badge.textContent = "HMB 통합 설치 필요 · 안전 삭제 보호 중";
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
    for name in WIDGETS:
        target = ROOT / "widgets" / name
        source = target.read_text(encoding="utf-8")
        desired = render(source, name)
        if source != desired:
            changed.append(name)
            if not args.check:
                with target.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(desired)
    if args.check and changed:
        raise SystemExit("Native stock safety is stale: " + ", ".join(changed))
    print(f"HMB native stock safety: {'PASS' if args.check else 'synchronized'} ({len(WIDGETS)} widgets)")


if __name__ == "__main__":
    main()
