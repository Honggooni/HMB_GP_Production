"""Build the connection management UI for the reviewed stock Editor 0.130."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

EDITOR = Path(__file__).resolve().parents[1] / "resources/editor"
STOCK_SHA256 = "841b879c94cd6bb18601f5b360daf094508bdfbfa0ec88b830a1caaf0df5871e"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Editor anchor changed: {old}")
    return source.replace(old, new, 1)


def connection_ui() -> str:
    """Reuse the connection dialog and header icon with the 0.130 SDK."""
    source = (EDITOR / "hmb-color-lut-native-header.js").read_text(encoding="utf-8")
    open_action = source[source.index("function hmbNativeOpenConnections("):source.index("function hmbNativeOpenBlockedConnections(")]
    icon = source[source.index("function hmbNativeConnectionActions("):source.index("function hmbNativeConnectionMenu(")]
    icon = icon.replace("hmbNativeConnectionActions(nodeName, library, actions, className, style)", "hmb130ConnectionIcon(nodeName, library)")
    icon = icon.replace("if (!hmbNativeConnectionManaged(library) || !actions) return actions;", 'if (library !== "HMB_GP_Production") return null;')
    icon = icon.replace('${className || ""} nodrag', "nodrag hover:bg-white/10 rounded")
    icon = icon.replace("...style, width:", "width:")
    icon = replace_once(icon, "return (0, S.cloneElement)(actions, { children: [button, actions.props.children] });", "return button;")
    dialog = source[source.index("function hmbNativeConnectionSnapshot("):source.index("let hmbNativeDeletionHostCount")]
    dialog = replace_once(dialog, 'if (typeof kq !== "undefined") kq.getState().setDirty(true);',
                          "fO.getState().setIsSaved(false);")
    return "\n".join((open_action, icon, dialog)).replace(
        "(0, R.", "(0, Z.").replace("(0, S.", "(0, Y.").replace(
        "(0, T.createPortal)", "(0, Cm.createPortal)").replace(
        "Xd.request(", "hmb130ConnectionRequest(").replace("vg(", "hmb130ConnectionError(")


CONNECTION_HOST = r"""
let hmbNativeStudioFlowEpoch = 0;

function hmb130ConnectionRequest(type, payload, options) {
  return yn.request(type, payload, options);
}

function hmb130ConnectionError(reason) {
  return reason?.result_details || reason?.message || String(reason);
}

function Hmb130ConnectionManager({flowName, workflowName}) {
  Y.useLayoutEffect(() => {
    hmbNativeStudioFlowEpoch += 1;
    document.dispatchEvent(new Event("hmb-native-connection-context-reset"));
    return () => { hmbNativeStudioFlowEpoch += 1; };
  }, [flowName, workflowName]);
  return hmbUseNativeConnectionManager();
}

"""

def build(stock: bytes) -> bytes:
    if sha256(stock).hexdigest() != STOCK_SHA256:
        raise ValueError("Unsupported stock Editor 0.130 bundle")
    source = stock.decode("utf-8")
    source = replace_once(source, "function hFn(){", f"{CONNECTION_HOST}\n{connection_ui()}\nfunction hFn(){{")
    source = replace_once(source, "onDoubleClick:b,children:x,color:S})=>{let{settings:C}",
                          "onDoubleClick:b,children:x,color:S,hmbLibrary})=>{let{settings:C}")
    source = replace_once(source, "children:[he.map(e=>_e(e)),te?",
                          "children:[hmb130ConnectionIcon(e,hmbLibrary),he.map(e=>_e(e)),te?")
    source = replace_once(source, "isVisible:qe,minHeight:Je,minWidth:Ye",
                          "isVisible:qe,handleStyle:r.metadata?.library===`HMB_GP_Production`?{opacity:0}:void 0,lineStyle:r.metadata?.library===`HMB_GP_Production`?{opacity:0}:void 0,minHeight:Je,minWidth:Ye")
    source = replace_once(source, "t[158]!==Ze?(Qe=(0,Z.jsxs)(bIe,{...Te,children:[Ze,d]}),",
                          "t[158]!==Ze||t[159]?.props.hmbLibrary!==r.metadata?.library?(Qe=(0,Z.jsxs)(bIe,{...Te,hmbLibrary:r.metadata?.library,children:[Ze,d]}),")
    source = replace_once(source, "children:[(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,",
                          "children:[e&&!Lt&&Z.jsx(Hmb130ConnectionManager,{flowName:y,workflowName:fO.getState().workflowName}),(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,")
    return source.encode("utf-8")
