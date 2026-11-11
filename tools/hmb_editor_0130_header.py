"""Shared HMB header transformation for the pinned Editor 0.130 bundle."""
from pathlib import Path


HEADER_SOURCE = Path(__file__).resolve().parents[1] / "resources/editor/hmb-header-0130.js"


def integrate_header(source, replace_once, *, artwork=False):
    art = "hmb130HeaderArtwork(e,hmbLibrary)" if artwork else "void 0"
    source = replace_once(source, "onDoubleClick:b,children:x,color:S})=>{let{settings:C}",
        "onDoubleClick:b,children:x,color:S,hmbLibrary})=>{const hmbHeaderHost=Y.useRef(null),"
        f"hmbArtworkRef={art},hmbHeaderSlots=hmbUse130IntegratedHeader(hmbHeaderHost,e,t,hmbLibrary,v,hmbArtworkRef);"
        "let{settings:C}")
    source = replace_once(source, 'let e=C.nodeHeaderItems||[`lock`,`run`,`startFlow`];return fIe.filter',
                          'let e=hmb130HeaderItems(t,hmbLibrary,C.nodeHeaderItems);return fIe.filter')
    source = replace_once(source, '},[C.nodeHeaderItems,W]),ge=', '},[C.nodeHeaderItems,W,t,hmbLibrary]),ge=')
    source = replace_once(source, 'onClick:e=>{e.preventDefault(),e.stopPropagation(),m()},style:U,type:`button`,children:(0,Z.jsx)(UT',
                          'onClick:hmbEvent=>{hmbEvent.preventDefault(),hmbEvent.stopPropagation(),hmbLibrary===`HMB_GP_Production`?hmb130RefreshConnections(e):m()},style:U,type:`button`,children:(0,Z.jsx)(UT')
    source = replace_once(source, '[_,G,te,u,c,l,d,f,p,m,h,H,U,ee,pe,ue,de,fe,me,ge])',
                          '[_,G,te,u,c,l,d,f,p,m,h,H,U,ee,pe,ue,de,fe,me,ge,hmbLibrary,e])')
    source = replace_once(source, "ye=mIe(t,!!ve.backgroundColor,N);return(0,Z.jsxs)(`div`,",
                          "ye=mIe(t,!!ve.backgroundColor,N);return hmb130IntegratedHeader(hmbHeaderSlots,(0,Z.jsxs)(`div`,")
    source = replace_once(source, "onDoubleClick:ce,style:tO(t)?ve:R,children:",
                          "onDoubleClick:ce,ref:hmbHeaderHost,style:tO(t)?ve:R,children:")
    source = replace_once(source, "children:[he.map(e=>_e(e)),te?",
                          "children:[hmb130ConnectionIcon(e,hmbLibrary),he.map(e=>_e(e)),te?")
    return replace_once(source, 'nodeName:e})]})})]})};function xIe', 'nodeName:e})]})})]}))};function xIe')
