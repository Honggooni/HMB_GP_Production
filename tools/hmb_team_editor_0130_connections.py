"""Build the connection management UI for the reviewed stock Editor 0.130."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
from pathlib import Path

EDITOR = Path(__file__).resolve().parents[1] / "resources/editor"
header_spec = importlib.util.spec_from_file_location("hmb_team_header_0130", Path(__file__).with_name("hmb_editor_0130_header.py"))
header = importlib.util.module_from_spec(header_spec)
header_spec.loader.exec_module(header)
STOCK_SHA256 = "841b879c94cd6bb18601f5b360daf094508bdfbfa0ec88b830a1caaf0df5871e"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Editor anchor changed: {old}")
    return source.replace(old, new, 1)


def connection_ui(helper: str | None = None) -> str:
    """Reuse the connection dialog and header icon with the 0.130 SDK."""
    source = helper if helper is not None else (EDITOR / "hmb-color-lut-native-header.js").read_text(encoding="utf-8")
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

function hmb130Library(node) {
  return node?.node_category === "HMB_GP_Production" ? node.node_category : node?.metadata?.library;
}

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

def build(stock: bytes, helper: str | None = None) -> bytes:
    if sha256(stock).hexdigest() != STOCK_SHA256:
        raise ValueError("Unsupported stock Editor 0.130 bundle")
    source = stock.decode("utf-8")
    source = replace_once(source, "function hFn(){", f"{CONNECTION_HOST}\n{connection_ui(helper)}\n{header.HEADER_SOURCE.read_text(encoding="utf-8")}\nfunction hFn(){{")
    source = header.integrate_header(source, replace_once)
    source = replace_once(source, "isVisible:qe,minHeight:Je,minWidth:Ye",
                          "isVisible:qe,handleStyle:hmb130Library(r)===`HMB_GP_Production`?{opacity:0}:void 0,lineStyle:hmb130Library(r)===`HMB_GP_Production`?{opacity:0}:void 0,minHeight:Je,minWidth:Ye")
    source = replace_once(source, "t[158]!==Ze?(Qe=(0,Z.jsxs)(bIe,{...Te,children:[Ze,d]}),",
                          "t[158]!==Ze||t[159]?.props.hmbLibrary!==hmb130Library(r)?(Qe=(0,Z.jsxs)(bIe,{...Te,hmbLibrary:hmb130Library(r),children:[Ze,d]}),")
    source = replace_once(source, "children:[(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,",
                          "children:[e&&!Lt&&Z.jsx(Hmb130ConnectionManager,{flowName:y,workflowName:fO.getState().workflowName}),(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,")
    return source.encode("utf-8")

def approval_evidence() -> dict:
    # Do not turn successful transformation or an isolated DOM test into
    # approval for a Team install. The release profile must verify the
    # installed renderer and deletion behavior on this exact candidate.
    return {"status": "review_required", "structural_anchors": "matched",
            "live_renderer_verified": False, "deletion_verified": False}


def patch_editor_source(source: str, helper: str) -> tuple[str, dict]:
    candidate = build(source.encode("utf-8"), helper)
    evidence = approval_evidence()
    evidence.update(source_sha256=STOCK_SHA256,
                    candidate_sha256=sha256(candidate).hexdigest(),
                    helper_sha256=sha256(helper.encode("utf-8")).hexdigest())
    return candidate.decode("utf-8"), evidence
