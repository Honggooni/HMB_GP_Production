"""Build the Local Rodong Mart overlay for the reviewed stock Editor 0.130."""
from __future__ import annotations

import base64
import re
from hashlib import sha256
from pathlib import Path

if __package__:
    from .hmb_editor_0130_header import HEADER_SOURCE, integrate_header
    from .restore_rodong_local_editor import EDITOR_1302, editor_profile, entry_for_overlay, stock_entry_from_active
else:
    from hmb_editor_0130_header import HEADER_SOURCE, integrate_header
    from restore_rodong_local_editor import EDITOR_1302, editor_profile, entry_for_overlay, stock_entry_from_active
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
    dialog = replace_once(dialog, 'el("header", { style:', 'el("header", { ref: header => { if (header) window.__hmbStylePopupHeader?.(header, header.parentElement); }, style:')
    return "\n".join((open_action, icon, dialog)).replace(
        "(0, R.", "(0, Z.").replace("(0, S.", "(0, Y.").replace(
        "(0, T.createPortal)", "(0, Cm.createPortal)").replace(
        "Xd.request(", "hmb130ConnectionRequest(").replace("vg(", "hmb130ConnectionError(")


def continue_artwork() -> str:
    source = (EDITOR / "hmb-continue-work-art.js").read_text(encoding="utf-8")
    for group in ("01-10", "11-20", "21-30"):
        artwork = (EDITOR / f"hmb-continue-work-{group}.webp").read_bytes()
        source = replace_once(source, "__HMB_CONTINUE_WORK_" + group.replace("-", "_") + "__",
                              "data:image/webp;base64," + base64.b64encode(artwork).decode("ascii"))
    return source


# The vendor compiler renamed these bindings between the two reviewed bundles.
# Adapt only our insertion points and references, never the vendor source itself.
EDITOR_1302_BINDINGS = {
    "hFn":"CFn", "fO":"NE", "T1":"kQ", "ajn":"pjn", "R$t":"SX",
    "THt":"IWt", "VMn":"YMn", "gFn":"wFn", "ijn":"fjn", "QWt":"nqt",
    "bIe":"vLe", "fIe":"uLe", "UT":"fT", "mIe":"fLe", "tO":"hE",
    "xIe":"yLe", "$D":"pE", "Cm":"Pm",
}
EDITOR_1302_STOCK = EDITOR_1302.stock_digest


def editor_1302_fragment(fragment):
    fragment = fragment.replace("[_,G,te,u,", "[_,G,ne,u,").replace("he.map(e=>_e(e)),te?", "he.map(e=>_e(e)),ne?")
    pattern = r"(?<![\w$])(" + "|".join(map(re.escape, EDITOR_1302_BINDINGS)) + r")(?![\w$])"
    return re.sub(pattern, lambda match: EDITOR_1302_BINDINGS[match.group()], fragment)


def build(stock: bytes, *, header_source: Path = HEADER_SOURCE) -> bytes:
    digest = sha256(stock).hexdigest()
    if digest not in (STOCK_SHA256, EDITOR_1302_STOCK):
        raise ValueError("Unsupported stock Editor 0.130 bundle")
    source = stock.decode("utf-8")
    basket = (EDITOR / "hmb-shot-basket.js").read_text(encoding="utf-8")
    basket = replace_once(basket, 'close.textContent = "로동 작업 계속";',
                          'close.textContent = "로동 작업 계속"; window.__hmbDecorateContinueWork(close);')
    # Local 0.130's transport supports workspace-scoped catalog preparation.
    # Keep legacy/team Editor profiles byte-for-byte unchanged.
    basket = replace_once(basket,
        'choose.addEventListener("change", () => { project = choose.value; update(); });',
        '''choose.addEventListener("change", () => {
        project = choose.value; update();
        // Read-only preparation cannot lock submission or change CGT Work.
        if (project) void request("status", { prewarm:true, project_id:project }).catch(() => {});
      });''')
    for suffix, placeholder in (
        ("launcher", "__HMB_RODONG_MART_ARTWORK__"),
        ("launcher-extra", "__HMB_RODONG_MART_EXTRA_ARTWORK__"),
        ("header", "__HMB_RODONG_MART_HEADER_ARTWORK__"),
    ):
        artwork = (EDITOR / f"hmb-rodong-mart-{suffix}.webp").read_bytes()
        basket = replace_once(basket, placeholder, "data:image/webp;base64," + base64.b64encode(artwork).decode("ascii"))
    adapter = (EDITOR / "hmb-rodong-editor-0130.js").read_text(encoding="utf-8")
    def patch(content, old, new):
        if digest == EDITOR_1302_STOCK:
            old, new = editor_1302_fragment(old), editor_1302_fragment(new)
        return replace_once(content, old, new)

    entry = "CFn" if digest == EDITOR_1302_STOCK else "hFn"
    opening = f"function {entry}(){{"
    components = "\n".join((adapter, connection_ui(), header_source.read_text(encoding="utf-8")))
    if digest == EDITOR_1302_STOCK:
        components = editor_1302_fragment(components)
    source = replace_once(source, opening, f"{continue_artwork()}\n{basket}\n{components}\n{opening}")
    source = patch(
        source, "(S=e=>{let t=c.current,a=t?e.map",
        "(S=e=>hmb130GuardRemovals(e,i.current,hmbChanges=>{let e=hmbChanges,t=c.current,a=t?e.map",
    )
    source = patch(
        source, "measured:{width:300,height:48}}:e)))},t[0]=g,t[1]=h,t[2]=v,t[3]=_",
        "measured:{width:300,height:48}}:e)))}),t[0]=g,t[1]=h,t[2]=v,t[3]=_",
    )
    source = integrate_header(source, patch, artwork=True)
    source = patch(source, "isVisible:qe,minHeight:Je,minWidth:Ye",
                          "isVisible:qe,handleStyle:hmb130Library(r)===`HMB_GP_Production`?{opacity:0}:void 0,lineStyle:hmb130Library(r)===`HMB_GP_Production`?{opacity:0}:void 0,minHeight:Je,minWidth:Ye")
    source = patch(source, "t[158]!==Ze?(Qe=(0,Z.jsxs)(bIe,{...Te,children:[Ze,d]}),",
                          "t[158]!==Ze||t[159]?.props.hmbLibrary!==hmb130Library(r)?(Qe=(0,Z.jsxs)(bIe,{...Te,hmbLibrary:hmb130Library(r),children:[Ze,d]}),")
    source = patch(
        source, "{isOpen:u,close:d,open:f}=T1(),{isOpen:p,close:m,activeTab:g}=ajn()",
        "{isOpen:u,close:d,open:f}=T1(),hmbMart=hmbUseMartStartup(f,a,u,t,d),{isOpen:p,close:m,activeTab:g}=ajn()",
    )
    source = patch(
        source, 'else S(!1),f()}catch(e){console.error(`Failed to check workflow context:`,e),S(!1),f()}})()},[t,a,l,r,f]);',
        'else S(!1),!fO.getState().workflowName&&hmbMart.show()}catch(e){console.error(`Failed to check workflow context:`,e),S(!1),!fO.getState().workflowName&&hmbMart.show()}})()},[t,a,l,r,hmbMart.show]);',
    )
    source = patch(source, "_e=(0,Y.useCallback)(async()=>{try{let e=await h(),t=R$t(",
                          "_e=(0,Y.useCallback)(async hmbBeforeOpen=>{try{let e=await h(),t=R$t(")
    # All three stock New entry points run after the save/discard gate. Use
    # the checked workflow transition, not the deliberately blocked bulk reset.
    # Keep preview cleanup and ordinary node deletion on their original paths.
    if source.count("await kt();") != 3:
        raise ValueError("Editor New workflow transition anchors changed")
    source = source.replace("await kt();", "await hmb130PrepareNewWorkflow();")
    source = patch(source, "function hFn(){", "async function hmb130PrepareNewWorkflow(){"
        "return fO.getState().workflowName?"
        "hmb130ConnectionRequest(`HMBPrepareWorkflowTransitionRequest`,{}):kt();}function hFn(){")
    source = patch(
        source, 'r(c,{isSaved:!1})}catch(e){console.error(`Failed to create workflow:`,e),',
        'typeof hmbBeforeOpen===`function`&&hmbBeforeOpen(c),r(c,{isSaved:!1});return c}catch(e){console.error(`Failed to create workflow:`,e),',
    )
    source = patch(source, "return(0,Z.jsx)(THt,{initialWorkflowName:t||",
                          "return Z.jsxs(Z.Fragment,{children:[(0,Z.jsx)(THt,{initialWorkflowName:t||")
    source = patch(
        source, "_&&s&&(0,Z.jsx)(VMn,{isOpen:_,onClose:v})]})},t)})}var gFn=",
        "_&&s&&(0,Z.jsx)(VMn,{isOpen:_,onClose:v})]})},t)}),"
        "hmbMart.visible&&(hmbMart.entering||hmbMart.awaitingWorkflow||(!t&&a===`connected`))?"
        "Z.jsx(hmbMartStartup,{onDismiss:hmbMart.dismiss,onEnter:()=>hmbMart.enter(_e)}):null]})}var gFn=",
    )
    source = patch(source, "u?(0,Z.jsx)(ijn,{onClose:d}):null",
                          "u&&!hmbMart.visible?(0,Z.jsx)(ijn,{onClose:d,onRodong:!t?hmbMart.reopen:void 0}):null")
    source = patch(source, "function ijn({onClose:e}={})",
                          "function ijn({onClose:e,onRodong:hmbOnRodong}={})")
    source = patch(
        source, '(0,Z.jsx)(`div`,{className:`mb-4`,children:(0,Z.jsx)(`h2`,{className:`text-xl font-semibold text-foreground`,children:`Workflows`})})',
        'Z.jsxs(`div`,{className:`mb-4 flex items-center gap-3`,children:[Z.jsx(`h2`,{className:`text-xl font-semibold text-foreground`,children:`Workflows`}),'
        'hmbOnRodong?Z.jsx(J,{variant:`outline`,onClick:hmbOnRodong,children:`HMB 로동마트`}):null]})',
    )
    return patch(
        source, "children:[(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,",
        "children:[Z.jsx(hmbMartCanvas,{ready:e&&!Lt,empty:!b.length,"
        "hasBasket:b.some(n=>Boolean(n.data?.metadata?.hmb_shot_basket_v1)),"
        "flowName:y,workflowName:fO.getState().workflowName,onCreated:async(flow,isCurrent)=>{"
        "const graph=await p(flow);if(!isCurrent())return;"
        "x(current=>Array.from(new Map([...current,...graph.nodes].map(node=>[node.id,node])).values()));"
        "D(current=>Array.from(new Map([...current,...graph.connections].map(edge=>[edge.id,edge])).values()));"
        "await v();}}),(0,Z.jsx)(QWt,{isLoading:Lt||!e,workflowReady:e,",
    ).encode("utf-8")

def verify_installed(editor: Path) -> Path:
    """Rebuild from the supported stock bundle and verify the active entry."""
    assets = editor / "assets"
    profile = editor_profile((editor / "index-editor.html").read_bytes())
    stock = (assets / profile.bundle).read_bytes()
    candidate = build(stock)
    digest = sha256(candidate).hexdigest()
    active = assets / f"index-hmb-rodong-{digest[:16]}.js"
    entry = (editor / "index-editor.html").read_bytes()
    if entry != entry_for_overlay(stock_entry_from_active(entry, active.name), active.name):
        raise ValueError("Editor is not serving the verified Rodong Mart entry")
    if not active.is_file() or sha256(active.read_bytes()).hexdigest() != digest:
        raise ValueError("Installed Rodong Mart asset differs from the verified build")
    return active


if __name__ == "__main__":
    import argparse
    from importlib.metadata import distribution

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor-dir", type=Path, help="Inspect a staged editor instead of the bundled install.")
    args = parser.parse_args()
    editor = args.editor_dir
    if editor is None:
        package = distribution("griptape-nodes-editor-dist")
        if package.version not in ("0.130.0", "0.130.2"):
            parser.exit(1, f"Editor {package.version} needs a compatibility check before local rollout.\n")
        editor = package.locate_file("griptape_nodes_editor_dist/editor")
    try:
        print(f"Editor 0.130 Rodong Mart verified: {verify_installed(editor)}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
