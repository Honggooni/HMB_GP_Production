"""Prepare or atomically install the pinned HMB native editor UI.

The default mode only writes a reviewable candidate and manifest in reports/.
The prototype --apply mode is retained for local reviews. Release installers
use --release-action prepare/apply/rollback with a verified package descriptor
and a fixed editor target. No app is stopped, workflow reloaded, engine state
changed, or provider contacted by this tool.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import uuid


REPO = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_SHA256 = "1a0429b88c6b8dd1c7e6e053836d03f734a4d6453f8886e0693527c7498909e2"
EXPECTED_EDITOR_VERSION = "0.128.1"
EXPECTED_BUNDLE_NAME = "index-DEZU41rc.js"
MINIMUM_SDK_VERSION = (0, 101, 3)
SUPPORTED_PREVIOUS_CANDIDATE_SHA256 = "7bad6f6517c781c54e6d2e0cf170f0b2ed3bdef28b3cca57be79cce54bdd11bf"
SUPPORTED_PREVIOUS_HELPER_SHA256 = "39e5901cc8aa37d1d11850a255bcc209ab4724afe488817fc3f684a72ab01b63"
SUPPORTED_CURRENT_CANDIDATE_SHA256 = "93b497d21995e23ef6707f0d3a3d39dd897a76d0388f7d7c9677d5cd54ef57c1"
SUPPORTED_CURRENT_HELPER_SHA256 = "2ed5f48b1c454039e84d9cba7499e290111e1d9f1038b157c0391aae794903f8"
HELPER = REPO / "resources/editor/hmb-color-lut-native-header.js"
DEFAULT_SOURCE = Path(os.environ.get("LOCALAPPDATA", "")) / (
    "ai.griptape.nodes.desktop/current/resources/editor-bundle/assets/" + EXPECTED_BUNDLE_NAME
)
REPORT_DIR = REPO / "reports/color-lut-native-header-20261023"
RELEASE_DESCRIPTOR = REPO / "resources/editor/native-editor-patch.json"
RELEASE_STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "HMB_GP_Production/native-editor-installs"


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _replace_once(source: str, old: str, new: str, anchor: str, counts: dict) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"{anchor}: expected one exact anchor, found {count}")
    counts[anchor] = count
    return source.replace(old, new, 1)


def patch_editor_source(source: str) -> tuple[str, dict]:
    """Return patched text and evidence, rejecting every unpinned source bundle."""
    if sha256(source) != EXPECTED_SOURCE_SHA256:
        raise ValueError("Editor source hash is not the reviewed 0.128.1 bundle; no patch was produced.")
    counts: dict[str, int] = {}
    helper = HELPER.read_text(encoding="utf-8")
    if source.count("HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1"):
        raise ValueError("Editor already contains a header prototype.")
    start_anchor = "var D$t=({node_name:e,node_type:t,"
    start = source.index(start_anchor)
    end_anchor = "},O$t=(0,S.createContext)(void 0);"
    end = source.index(end_anchor, start) + 1
    header = source[start:end]
    original_header = header
    native_header_sha256 = sha256(header)
    header = _replace_once(header,
        "children:x,color:C})=>{let{settings:w}=KZ()",
        "children:x,color:C,hmbLibrary:hmbLibrary=null,hmbHostExpanded:hmbHostExpanded=!0,hmbHostRestoreView:hmbHostRestoreView=null})=>{let hmbNativeHeader=hmbUseColorLUTNativeHeader(t,e,hmbHostExpanded,b,hmbHostRestoreView,v);let{settings:w}=KZ()",
        "native_header_hook", counts)
    header = _replace_once(header,
        "let e=w.nodeHeaderItems||[`lock`,`run`,`startFlow`];return kQ.filter",
        "let e=hmbIsNativeStudioType(t)&&hmbNativeHeader.active?[`lock`,`reset`,`run`]:w.nodeHeaderItems||[`lock`,`run`,`startFlow`];return kQ.filter",
        "color_lut_three_native_actions", counts)
    header = _replace_once(header, "[w.nodeHeaderItems,se]),ke=", "[w.nodeHeaderItems,se,t,hmbNativeHeader.active]),ke=",
        "native_action_memo_dependencies", counts)
    header = _replace_once(header,
        "xe=(0,S.useMemo)(()=>FQ(b),[b])",
        "xe=(0,S.useMemo)(()=>FQ(hmbNativeStudioDoubleClick(t,e,b)),[b,t,e])",
        "native_compact_double_click_dispatch", counts)
    output_marker = "je=AQ(t,C),Me=jQ(t,!!je.backgroundColor,P);return"
    if header.count(output_marker) != 1:
        raise ValueError("Native header JSX output anchor changed.")
    head, output = header.split(output_marker)
    children_marker = "children:[(0,R.jsxs)(`div`,{className:`flex items-center min-w-0 gap-3"
    if output.count(children_marker) != 1 or not output.endswith("]})}"):
        raise ValueError("Native header child JSX boundaries changed.")
    child_start = output.index(children_marker) + len("children:[")
    separator = ",t!==`Note`&&(0,R.jsx)(`div`,{className:`flex flex-shrink-0 gap-3`"
    if output.count(separator) != 1:
        raise ValueError("Native identity/action separation anchor changed.")
    split = output.index(separator, child_start)
    identity = output[child_start:split]
    actions = output[split + 1:-4]
    if not identity.endswith("})]})") or not actions.endswith("})})"):
        raise ValueError("Native identity/actions JSX ending changed.")
    outer = output[:child_start - len("children:[")]
    outer = _replace_once(outer, "style:t===`Note`?je:te,",
        "style:hmbNativeHeader.active?{display:`none`}:t===`Note`?je:te,", "native_header_fallback_style", counts)
    header = (head + "je=AQ(t,C),Me=jQ(t,!!je.backgroundColor,P);let hmbNativeIdentity=" + identity
        + ",hmbNativeActions=hmbNativeConnectionActions(e,hmbLibrary," + actions + ",ie,ae);return hmbIsNativeStudioType(t)&&v?hmbNativeStudioCollapsedHeader(e,ee,te,y,_,ge):" + outer
        + "children:hmbNativeHeader.active?hmbColorLUTHeaderPortals(hmbNativeHeader,hmbNativeIdentity,hmbNativeActions,te):[hmbNativeIdentity,hmbNativeActions]})}")
    source = _replace_once(source, original_header, helper + "\n" + header,
        "native_header_component", counts)
    source = _replace_once(source,
        "(0,R.jsxs)(D$t,{...bt,children:[ce?",
        "(0,R.jsxs)(D$t,{...bt,hmbLibrary:e.metadata?.library,hmbHostExpanded:!yt,hmbHostRestoreView:e.hmb_native_studio_restore_view,children:[ce?",
        "host_collapsed_or_rolled_up_gate", counts)
    source = _replace_once(source,
        "getDimensions:(t,r,i,a,o)=>Tjr(t,r,i,a,e.metadata?.size,o)",
        "getDimensions:(t,r,i,a,o)=>hmbNativeStudioDimensions(e.node_type,t,r,i,a,e.metadata?.size,o,e.node_name)",
        "native_icon_collapse_dimensions", counts)
    source = _replace_once(source,
        "...Sjr(fe,O,ee,600,xt,A)",
        "...hmbNativeStudioNodeStyle(e.node_type,fe,O,ee,600,xt,A)",
        "native_icon_collapse_outer_style", counts)
    source = _replace_once(source,
        "(0,S.useEffect)(()=>{me(e.node_name,e=>(e.height||0)<ee?{...e,height:ee}:e)},[ee,e.node_name,me])",
        "(0,S.useEffect)(()=>{if(hmbIsNativeStudioType(e.node_type)&&O)return;me(e.node_name,e=>hmbIsNativeStudioType(e.data?.node_type)&&e.data?.collapsed?e:(e.height||0)<ee?{...e,height:ee}:e)},[ee,e.node_name,e.node_type,O,me])",
        "native_icon_cold_height_floor", counts)
    source = _replace_once(source,
        "(0,S.useEffect)(()=>{e.collapsed!==void 0&&e.collapsed!==O&&k(e.collapsed)},[e.collapsed])",
        "hmbUseNativeStudioCollapseState(e,O,k,A,fe)",
        "native_icon_explicit_intent_state_sync", counts)
    source = _replace_once(source,
        "let ve=(0,S.useCallback)(()=>{let e=!O;k(e),j(!1),de(e)},[O,de])",
        "let ve=(0,S.useCallback)(()=>{let t=!O;hmbNativeStudioRecordCollapsed(e.node_type,e.node_name,t);k(t),j(!1),de(t)},[O,de,e.node_type,e.node_name])",
        "native_icon_explicit_arrow_intent", counts)
    source = _replace_once(source,
        "p(void 0,wn).then(({nodes:e,connections:t})=>{l(null),x([]),O([]),lt(),mt(),x(e),O(t)",
        "p(void 0,wn).then(({nodes:e,connections:t})=>{hmbNativeStudioResetCollapseIntents();l(null),x([]),O([]),lt(),mt(),x(e),O(t)",
        "native_icon_workflow_load_intent_reset", counts)
    source = _replace_once(source,
        "return d}function pkr(){",
        "return hmbNativeStudioConstructedNode(d)}function pkr(){",
        "native_icon_cold_workflow_constructor", counts)
    source = _replace_once(source,
        "C=h.current.getParentId(_);h.current.onBeforeAnimate(t,d)",
        "C=h.current.getParentId(_),hmbNativeViewMetadata=hmbNativeStudioCollapseMetadata(_,t,d);h.current.onBeforeAnimate(t,d)",
        "native_icon_view_capture_before_unmount", counts)
    source = _replace_once(source,
        "metadata:d?{rolledUp:t}:{collapsed:t,rolledUp:!1}",
        "metadata:{...(d?{rolledUp:t}:{collapsed:t,rolledUp:!1}),...hmbNativeViewMetadata}",
        "native_icon_compact_view_persistence", counts)
    source = _replace_once(source,
        "onDoubleClick:pe&&!O?ye:void 0",
        "onDoubleClick:hmbIsNativeStudioType(e.node_type)?void 0:pe&&!O?ye:void 0",
        "native_studio_only_existing_compact_double_click", counts)
    source = _replace_once(source,
        "let t=a?300:e.dimensions.width,r=a?48:e.dimensions.height;",
        "let t=a?(hmbIsNativeStudioType(w.current.find(t=>t.id===e.id)?.data?.node_type)?hmbNativeStudioCollapsedWidth:300):e.dimensions.width,r=a?(hmbIsNativeStudioType(w.current.find(t=>t.id===e.id)?.data?.node_type)?hmbNativeStudioCollapsedHeight:48):e.dimensions.height;",
        "native_icon_initial_collapsed_measured_size", counts)
    source = _replace_once(source,
        "if(!r&&t.type!==`GroupNode`&&!t.data?.metadata?.size){let r=",
        "if(!r&&t.type!==`GroupNode`&&!t.data?.metadata?.size&&!hmbNativeStudioSuppressInitialSize(t,e.dimensions)){let r=",
        "native_icon_skip_folded_initial_size_save", counts)
    source = _replace_once(source,
        "r&&r.type!==`GroupNode`&&!r.data.collapsed){let i=",
        "r&&r.type!==`GroupNode`&&!r.data.collapsed&&!hmbNativeStudioFolded(r)){let i=",
        "native_icon_skip_folded_resize_save", counts)
    source = _replace_once(source,
        "c.has(e.id)&&e.data?.collapsed===!0?{...e,width:300,height:48,measured:{width:300,height:48}}:e",
        "c.has(e.id)&&e.data?.collapsed===!0?hmbNativeStudioCollapsedMeasuredNode(e):e",
        "native_icon_collapsed_dimension_events", counts)
    source = _replace_once(source,
        "x(e=>e.map(e=>c.has(e.id)&&e.data?.collapsed===!0?hmbNativeStudioCollapsedMeasuredNode(e):e))",
        "x(e=>hmbNativeStudioCollapsedMeasuredNodes(e,c))",
        "native_icon_skip_identical_collapsed_measurements", counts)
    source = _replace_once(source,
        "yn=(0,S.useCallback)((e,t)=>{Xd.send(`SetNodeMetadataRequest`,{node_name:e,metadata:t})},[])",
        "yn=(0,S.useCallback)((e,t)=>{Xd.send(`SetNodeMetadataRequest`,{node_name:e,metadata:hmbNativeStudioOutgoingMetadata(e,t)})},[])",
        "native_icon_geometry_metadata_current_view", counts)
    source = _replace_once(source,
        "x(t=>t.map(t=>t.id===r?{...e,position:t.position,width:t.width,height:t.height,selected:t.selected,hidden:t.hidden,parentId:t.parentId,zIndex:t.zIndex,data:{...e.data,__inGroup:t.data.__inGroup}}:t)),A(r)}catch(e){console.error(`Failed to refresh node after parameter alter:`,e)}",
        "x(t=>t.map(t=>t.id===r?{...e,position:t.position,width:t.width,height:t.height,selected:t.selected,hidden:t.hidden,parentId:t.parentId,zIndex:t.zIndex,data:{...e.data,__inGroup:t.data.__inGroup,...(hmbIsNativeStudioType(t.data?.node_type)?{collapsed:t.data.collapsed}:{})}}:t)),A(r)}catch(e){console.error(`Failed to refresh node after parameter alter:`,e)}",
        "native_icon_preserve_collapse_during_parameter_refresh", counts)
    source = _replace_once(source,
        "className:`widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel`,style:g",
        "className:hmbIsNativeStudioWidget(t)?`widget-container flex flex-col w-full h-full min-h-0 nowheel`:`widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel`,style:g",
        "color_lut_widget_drag_ancestor", counts)
    source = _replace_once(source,
        "[a.value,l.status,t]),l.status===`loading`)",
        "[a.value,l.status,t,hmbIsNativeStudioWidget(t)?i:void 0]),l.status===`loading`)",
        "color_lut_widget_disabled_update", counts)
    source = _replace_once(source,
        "function Ejr({data:e,selected:t,onParameterChange:r,onParameterAdd:i,onParameterRemove:a,onParameterAlter:o,onNodeRename:s,headerExtra:c}){let{settings:l}=KZ()",
        "function Ejr({data:e,selected:t,onParameterChange:r,onParameterAdd:i,onParameterRemove:a,onParameterAlter:o,onNodeRename:s,headerExtra:c}){let hmbNativeFrameActive=hmbUseColorLUTFrameActive(e.node_type,e.node_name);let{settings:l}=KZ()",
        "color_lut_native_frame_observer", counts)
    source = _replace_once(source,
        "(0,R.jsx)(sie,{isVisible:t&&!yt&&!fe,minHeight:yt?48:ee,minWidth:O?300:600,onResize:lt,onResizeStart:()=>re(!0),onResizeEnd:()=>re(!1)})",
        "(0,R.jsx)(sie,{isVisible:(t||hmbNativeFrameActive)&&!yt&&!fe,minHeight:yt?48:ee,minWidth:O?300:600,onResize:lt,onResizeStart:()=>re(!0),onResizeEnd:()=>re(!1)})",
        "color_lut_resize_without_selection", counts)
    source = _replace_once(source,
        "{getNodes:C,setNodes:w}=Nu(),{duplicateNodes:T}=Skr()",
        "{getNodes:C,setNodes:w}=Nu(),hmbInitialGeometry=hmbUseColorLUTInitialGeometry(e,hmbNativeFrameActive,C,w),{duplicateNodes:T}=Skr()",
        "color_lut_native_initial_geometry_hook", counts)
    source = _replace_once(source,
        "metadata:{position:l,tempId:d},set_as_new_context:!1};await Xd.send(`CreateNodeRequest`,p)",
        "metadata:hmbColorLUTCreateMetadata(f.node_type,{position:l,tempId:d}),set_as_new_context:!1};await Xd.send(`CreateNodeRequest`,p)",
        "color_lut_factory_drop_metadata_opt_in", counts)
    source = _replace_once(source,
        "node_type:t.node_type,specific_library_name:t.library_name,metadata:{position:r,tempId:i},set_as_new_context:!1})",
        "node_type:t.node_type,specific_library_name:t.library_name,metadata:hmbColorLUTCreateMetadata(t.node_type,{position:r,tempId:i}),set_as_new_context:!1})",
        "color_lut_factory_sidebar_metadata_opt_in", counts)
    source = _replace_once(source,
        "bn=(0,S.useCallback)(e=>{let t=E.current,r=t?e.map",
        "bn=(0,S.useCallback)(e=>hmbNativeGuardNodeDeletion(e,w.current,hmbDeletionChanges=>{let e=hmbDeletionChanges,t=E.current,r=t?e.map",
        "hmb_delete_all_entry_points_preflight", counts)
    source = _replace_once(source,
        "function g2r(){let e=_Wt()",
        "function g2r(){hmbUseNativeDeletionGuardHost();let hmbConnectionManager=hmbUseNativeConnectionManager();let e=_Wt()",
        "hmb_delete_public_host_marker", counts)
    source = _replace_once(source,
        "children:[(0,R.jsx)(N0r,{isLoading:ae||!e,workflowReady:e,stepName:t,currentStep:r,totalSteps:i,currentItem:a,error:o,errorTitle:s,onRetry:Dn})",
        "children:[hmbConnectionManager,(0,R.jsx)(N0r,{isLoading:ae||!e,workflowReady:e,stepName:t,currentStep:r,totalSteps:i,currentItem:a,error:o,errorTitle:s,onRetry:Dn})",
        "hmb_connection_single_canvas_modal", counts)
    source = _replace_once(source,
        "t[73]=M,t[74]=ve):ve=t[74],ve}var rzr=",
        "t[73]=M,t[74]=ve):ve=t[74],hmbNativeConnectionMenu(e,ve)}var rzr=",
        "hmb_connection_preserve_native_context_items", counts)
    source = _replace_once(source,
        "(0,R.jsx)(nzr,{addParameterDisabled:Se,configureParameterDisabled:Ae,",
        "(0,R.jsx)(nzr,{hmbConnectionNode:d||E[0]?.node,hmbClose:()=>c(!1),addParameterDisabled:Se,configureParameterDisabled:Ae,",
        "hmb_connection_context_library_identity", counts)
    source = _replace_once(source,
        "},[C,b,x,yn,on,Zt,A,N.showHelperLines,Ve,Ue,Et,Dt,ze,ut]),xn=",
        "}),[C,b,x,yn,on,Zt,A,N.showHelperLines,Ve,Ue,Et,Dt,ze,ut]),xn=",
        "hmb_delete_controlled_handler_scope", counts)
    source = _replace_once(source,
        "if(Dt(t.id),r?.data?.node_type===`DotNode`)",
        "if(!t.hmbGuardedDelete&&Dt(t.id),r?.data?.node_type===`DotNode`)",
        "hmb_delete_preserve_pending_ui_state", counts)
    source = _replace_once(source,
        "Xd.send(`DeleteNodeRequest`,{node_name:t.id})}),Et()}",
        "Xd.send(`DeleteNodeRequest`,{node_name:t.id})}),a.some(e=>!e.hmbGuardedDelete)&&Et()}",
        "hmb_delete_preserve_pending_parameter_updates", counts)
    source = _replace_once(source,
        "C(l),c.size>0&&(Array.from(c),",
        "C(l.filter(e=>e.type!==`remove`||!e.hmbGuardedDelete)),c.size>0&&(Array.from(c),",
        "hmb_delete_wait_for_engine_success", counts)
    source = _replace_once(source,
        "let r=e?.node_name||t?.node_name;r&&(x(e=>e.filter(e=>e.id!==r&&e.name!==r))",
        "let r=e?.node_name||t?.node_name;r&&(hmbNativeDeletionFinished(r),Dt(r),Et(),x(e=>e.filter(e=>e.id!==r&&e.name!==r))",
        "hmb_delete_success_finalizes_ui", counts)
    source = _replace_once(source,
        "o=m(`DeleteNodeResultFailure`,e=>{console.error(`❌ Node deletion failed:`,e)})",
        "o=m(`DeleteNodeResultFailure`,(e,t)=>{hmbNativeDeletionFinished(t?.node_name||e?.node_name);hmbNativeConnectionDeletionNotice(t,vg(e));console.error(`❌ Node deletion failed:`,e)})",
        "hmb_delete_failure_keeps_ui", counts)
    source = _replace_once(source,
        "let r=zhe(t),i=Rhe(t.result);if(Uhe(t))",
        "let r=zhe(t),i=Rhe(t.result);if(hmbNativeConnectionDeletionNotice(e.request,i)){cg(r,i);return}if(Uhe(t))",
        "hmb_connection_guard_failure_notification_action", counts)
    source = _replace_once(source,
        "uUt=()=>Xd.request(`ClearAllObjectStateRequest`,{i_know_what_im_doing:!0})",
        "uUt=()=>Xd.request(`HMBPrepareWorkflowTransitionRequest`,{})",
        "hmb_safe_native_workflow_transition", counts)
    source = _replace_once(source,
        "se=m(`ClearAllObjectStateResultSuccess`,()=>{x([]),O([]),lt()",
        "se=m(`ClearAllObjectStateResultSuccess`,()=>{hmbNativeStudioResetCollapseIntents();x([]),O([]),lt()",
        "hmb_delete_invalidate_pending_checks_on_clear", counts)
    evidence = {
        "schema": "hmb-color-lut-native-header-prototype", "version": 1,
        "editor_version": EXPECTED_EDITOR_VERSION,
        "source_sha256": EXPECTED_SOURCE_SHA256, "candidate_sha256": sha256(source),
        "helper_sha256": sha256(helper), "native_header_before_sha256": native_header_sha256,
        "native_identity_jsx_sha256": sha256(identity), "native_actions_jsx_sha256": sha256(actions),
        "anchors": counts, "scope": "Explicit HMB native studio presentation allowlists; deletion batches use engine library identity including future HMB tools",
        "hmb_connected_deletion": {
            "request": "HMBCheckNodeDeletionRequest", "ownership": "engine hmb_node_names; no frontend type-prefix inference",
            "batch_preflight_all_or_none": True, "unknown_or_failed_check": "keep all nodes",
            "hmb_ui_removal": "DeleteNodeResultSuccess only", "rejected_delete_preserves_pending_edits": True,
            "standard_node_cleanup": "original optimistic behavior after successful preflight",
            "safe_ui_transition_request": "HMBPrepareWorkflowTransitionRequest",
        },
        "hmb_connection_management": {
            "identity": "metadata.library == HMB_GP_Production; no fixed node type allowlist",
            "list_request": "HMBGetNodeConnectionsRequest", "manage_request": "HMBManageNodeConnectionsRequest",
            "snapshot_fence": "expected_state_token", "host": "one modal per canvas; queries only while opened",
            "header_chain_button": "before original native lock/reset/run actions",
            "collapsed_context_menu": True, "blocked_delete_notification_action": True,
        },
        "native_callbacks_reused": ["Ce", "we", "Ae", "OQ", "EQ", "Ge", "Ye", "et", "ve", "ye", "FEr", "sie"],
        "native_handle_ids_unchanged": True,
        "resize_requires_selection": False, "resize_controls_visible": False,
        "resize_minimum_and_callbacks_unchanged": True,
        "native_icon_collapse": {"width": 320, "height": 64,
            "scope": "explicit HMB 9 node types only", "collapsed_icon": "02 soft-link SVG; expanded native VZ unchanged",
            "label": "Double Click to Unlock", "disc_diameter": 52,
            "single_click_expands": False, "double_click_expands": True,
            "original_expand_callback": True, "cold_constructor_geometry": True,
            "hidden_handle_ids_unchanged": True, "expanded_metadata_size_unchanged": True,
            "compact_view_state_only": "ImageAsset/VideoPicker existing compact only; other HMB headers do not act; pre-existing native rolledUp metadata unchanged"},
        "native_initial_geometry": {"width": 1225, "height": 1057,
            "scope": "explicit fresh prototype-editor placement only", "authored_metadata_unchanged": True},
    }
    return source, evidence


def _read_pinned_source(source: Path) -> str:
    if source.name != EXPECTED_BUNDLE_NAME:
        raise ValueError("Editor bundle filename is not the reviewed target.")
    version_file = source.parent.parent / ".version"
    if version_file.is_file():
        if version_file.read_text(encoding="utf-8").strip() != EXPECTED_EDITOR_VERSION:
            raise ValueError("Installed editor version changed; no patch was produced.")
    else:
        # A follow-up candidate may use the original baseline saved by this
        # installer. Never patch an already modified bundle or an arbitrary copy.
        receipt_file = REPORT_DIR / "local-editor-install.json"
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        if (receipt.get("schema") != "hmb-color-lut-native-header-install"
                or receipt.get("editor_version") != EXPECTED_EDITOR_VERSION
                or receipt.get("source_sha256") != EXPECTED_SOURCE_SHA256
                or Path(receipt.get("backup", "")).resolve() != source.resolve()
                or (REPORT_DIR / "backups").resolve() not in source.resolve().parents):
            raise ValueError("Source is neither the pinned installed editor nor its verified original backup.")
    source_text = source.read_text(encoding="utf-8")
    if sha256(source_text) != EXPECTED_SOURCE_SHA256:
        raise ValueError("Original editor baseline hash changed; no patch was produced.")
    return source_text


def _atomic_write(path: Path, value: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.hmb-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _require_desktop_stopped() -> None:
    if os.name != "nt":
        return
    output = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", "IMAGENAME eq griptape-nodes-desktop.exe"],
        check=True, text=True, encoding="utf-8", errors="replace", capture_output=True).stdout
    if any(row and row[0].casefold() == "griptape-nodes-desktop.exe" for row in csv.reader(io.StringIO(output))):
        raise RuntimeError("Griptape desktop is running; no editor file was changed.")


def _json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def rollback(receipt_path: Path) -> dict:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "hmb-color-lut-native-header-install" or receipt.get("version") != 1:
        raise ValueError("Unsupported rollback receipt.")
    target = Path(receipt["target"]).resolve()
    if target != DEFAULT_SOURCE.resolve() or target.name != EXPECTED_BUNDLE_NAME:
        raise ValueError("Rollback target is outside the reviewed installed editor.")
    backup = Path(receipt["backup"]).resolve()
    if REPORT_DIR.resolve() not in backup.parents:
        raise ValueError("Rollback backup is outside the prototype report directory.")
    original = backup.read_bytes()
    if sha256(original) != EXPECTED_SOURCE_SHA256 or sha256(target.read_bytes()) != receipt["candidate_sha256"]:
        raise ValueError("Editor or backup changed after installation; rollback refused.")
    _require_desktop_stopped()
    _atomic_write(target, original)
    return {"rolled_back": True, "target": str(target), "sha256": sha256(target.read_bytes())}


def _release_plain_path(path: Path) -> Path:
    """Never follow a symlink/junction into another app, user directory or backup."""
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Native editor path contains a symlink or reparse point.")
    return absolute


def _release_descriptor() -> tuple[dict, str]:
    encoded = _release_plain_path(RELEASE_DESCRIPTOR).read_bytes()
    value = json.loads(encoded)
    expected = {
        "schema": "hmb-native-editor-patch-release", "version": 1,
        "editor_version": EXPECTED_EDITOR_VERSION, "bundle_name": EXPECTED_BUNDLE_NAME,
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "helper_path": "resources/editor/hmb-color-lut-native-header.js",
        "patcher_path": "tools/hmb_color_lut_native_header_patch.py",
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Unsupported native editor release descriptor.")
    for key in ("helper_sha256", "patcher_sha256", "candidate_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid native editor release hash.")
    _release_previous_candidates(value)
    if sha256(_release_plain_path(HELPER).read_bytes()) != value["helper_sha256"]:
        raise ValueError("Native editor helper differs from the verified release.")
    if sha256(_release_plain_path(Path(__file__)).read_bytes()) != value["patcher_sha256"]:
        raise ValueError("Native editor patcher differs from the verified release.")
    return value, sha256(encoded)


def _release_previous_candidates(descriptor: dict) -> list[dict]:
    """Accept the original single predecessor or the exact two-release chain."""
    older = {"bundle_sha256": SUPPORTED_PREVIOUS_CANDIDATE_SHA256,
             "helper_sha256": SUPPORTED_PREVIOUS_HELPER_SHA256}
    recent = {"bundle_sha256": SUPPORTED_CURRENT_CANDIDATE_SHA256,
              "helper_sha256": SUPPORTED_CURRENT_HELPER_SHA256}
    if "previous_candidates" in descriptor:
        if "previous_candidate" in descriptor or descriptor["previous_candidates"] != [recent, older]:
            raise ValueError("Unsupported previous native editor candidates.")
        return [recent, older]
    if "previous_candidate" in descriptor:
        if descriptor["previous_candidate"] != older:
            raise ValueError("Unsupported previous native editor candidate.")
        return [older]
    return []


def _release_original_hashes(descriptor: dict) -> set[str]:
    hashes = {EXPECTED_SOURCE_SHA256, descriptor["candidate_sha256"]}
    hashes.update(item["bundle_sha256"] for item in _release_previous_candidates(descriptor))
    return hashes


def _upgrade_previous_helper(original: bytes, descriptor: dict) -> bytes:
    """Replace only the pinned helper; every other editor byte stays intact."""
    original_sha = sha256(original)
    previous = next((item for item in _release_previous_candidates(descriptor)
                     if item["bundle_sha256"] == original_sha), None)
    if not previous:
        raise ValueError("Unknown previous native editor candidate.")
    start_marker = b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1"
    end_marker = b"/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */"
    header_marker = b"var D$t=({node_name:e,node_type:t,"
    if (original.count(start_marker) != 1 or original.count(end_marker) != 1
            or original.count(header_marker) != 1):
        raise ValueError("Previous native editor helper markers are not unique.")
    start = original.index(start_marker)
    marker_end = original.index(end_marker) + len(end_marker)
    header_start = original.index(header_marker)
    # Existing helpers have geometry functions after the original END marker.
    # The transformer inserts the entire helper plus one LF before D$t.
    end = header_start - 1
    if marker_end <= start or marker_end >= end or original[header_start - 2:header_start] != b"\n\n":
        raise ValueError("Previous native editor helper boundary changed.")
    if sha256(original[start:end]) != previous["helper_sha256"]:
        raise ValueError("Previous native editor helper hash changed.")
    # Match the pristine transformer, which normalizes the helper to UTF-8 LF.
    replacement = HELPER.read_text(encoding="utf-8").encode("utf-8")
    candidate = original[:start] + replacement + original[end:]
    if sha256(candidate) != descriptor["candidate_sha256"]:
        raise ValueError("Upgraded native editor candidate differs from the verified release.")
    return candidate


def _release_target() -> Path:
    target = _release_plain_path(DEFAULT_SOURCE)
    if target.name != EXPECTED_BUNDLE_NAME:
        raise ValueError("Unsupported native editor target.")
    version = _release_plain_path(target.parent.parent / ".version")
    if version.read_text("utf-8").strip() != EXPECTED_EDITOR_VERSION:
        raise ValueError("Unsupported installed editor version; no installation was performed.")
    return target


def _release_sdk_preflight() -> dict:
    """Inspect the target SDK without importing it or starting an engine.

    An editor patch cannot compensate for an SDK lacking the pre-dispatch
    boundary. Check the installed sources as well as package metadata before
    the caller moves any library files. These are capability checks, not a
    claim that the guard is already registered in a running engine.
    """
    site = _release_plain_path(DEFAULT_SOURCE.parents[2] / "engine-bundle/python/Lib/site-packages")
    prefix = "Unsupported Griptape SDK; update Griptape before installing HMB. "
    metadata = sorted(site.glob("griptape_nodes-*.dist-info/METADATA"))
    if len(metadata) != 1:
        raise ValueError(prefix + "Expected one griptape-nodes package metadata record.")

    def read_file(path: Path) -> bytes:
        path = _release_plain_path(path)
        try:
            if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError(prefix + "Required SDK source is missing or oversized: " + path.name)
            return path.read_bytes()
        except OSError as error:
            raise ValueError(prefix + "Cannot read required SDK source: " + path.name) from error

    metadata_bytes = read_file(metadata[0])
    metadata_text = metadata_bytes.decode("utf-8-sig")
    names = re.findall(r"^Name: (.+)$", metadata_text, re.MULTILINE)
    versions = re.findall(r"^Version: (.+)$", metadata_text, re.MULTILINE)
    if len(names) != 1 or names[0].strip().lower().replace("_", "-") != "griptape-nodes" or len(versions) != 1:
        raise ValueError(prefix + "Invalid griptape-nodes package metadata.")
    version = versions[0].strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or tuple(map(int, version.split("."))) < MINIMUM_SDK_VERSION:
        raise ValueError(prefix + "griptape-nodes 0.101.3 or newer is required; found " + version + ".")
    sources = {
        "engine": site / "griptape_nodes/retained_mode/engine.py",
        "event_manager": site / "griptape_nodes/retained_mode/managers/event_manager.py",
    }
    trees, hashes = {}, {"metadata": sha256(metadata_bytes)}
    for name, path in sources.items():
        encoded = read_file(path)
        try:
            trees[name] = ast.parse(encoded, filename=str(path))
        except (SyntaxError, ValueError) as error:
            raise ValueError(prefix + "Required SDK source cannot be parsed: " + path.name) from error
        hashes[name] = sha256(encoded)
    current = [node for node in trees["engine"].body if isinstance(node, ast.FunctionDef) and node.name == "current_engine"]
    managers = [node for node in trees["event_manager"].body if isinstance(node, ast.ClassDef) and node.name == "EventManager"]
    if len(current) != 1 or len(managers) != 1:
        raise ValueError(prefix + "Missing engine.current_engine or EventManager API.")
    current_args = current[0].args
    if len(current_args.posonlyargs) + len(current_args.args) != len(current_args.defaults) or any(value is None for value in current_args.kw_defaults):
        raise ValueError(prefix + "engine.current_engine must accept a call without arguments.")
    required = ("add_pre_dispatch_hook", "remove_pre_dispatch_hook", "register_request_handlers")
    for name in required:
        methods = [node for node in managers[0].body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(methods) != 1:
            raise ValueError(prefix + "Missing synchronous EventManager." + name + " API.")
        args = methods[0].args
        positional = args.posonlyargs + args.args
        if len(positional) < 2 or len(positional) - len(args.defaults) > 2 or any(value is None for value in args.kw_defaults):
            raise ValueError(prefix + "EventManager." + name + " must accept one hook argument.")
    return {"package": "griptape-nodes", "version": version,
            "capabilities": ["current_engine", *required], "source_sha256": hashes,
            "verification": "metadata-and-ast-only; active guard checked after app startup"}


def _require_release_stopped() -> None:
    if os.name != "nt":
        return
    # The package CLI never accepts a target/root override. Both the desktop
    # and its bundled Python workers must have stopped; no process is killed.
    command = ("$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | Where-Object { "
               "$_.Name -match 'griptape' -or ($_.ExecutablePath -and "
               "$_.ExecutablePath.StartsWith($env:HMB_NATIVE_PATCH_APP_ROOT,[StringComparison]::OrdinalIgnoreCase)) "
               "} | ForEach-Object { $_.ProcessId }")
    env = dict(os.environ, HMB_NATIVE_PATCH_APP_ROOT=str(DEFAULT_SOURCE.parents[3]) + os.sep)
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                            env=env, check=True, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    # The installer itself runs this helper with the bundled engine Python.
    # Exclude only this exact process, never every Python process in that path.
    active_pids = [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    if any(pid != os.getpid() for pid in active_pids):
        raise RuntimeError("Griptape desktop or bundled engine is running; no editor file was changed.")


def _release_plan(path: Path) -> tuple[dict, Path, dict]:
    root = _release_plain_path(RELEASE_STATE_ROOT)
    path = _release_plain_path(path)
    if path.name != "plan.json" or path.parent.parent != root:
        raise ValueError("Native editor plan is outside the owned install-state folder.")
    try:
        if uuid.UUID(path.parent.name).hex != path.parent.name:
            raise ValueError()
    except ValueError:
        raise ValueError("Native editor plan folder is not a generated transaction.") from None
    value = json.loads(path.read_text("utf-8"))
    descriptor, descriptor_sha = _release_descriptor()
    target = _release_target()
    expected = {"schema": "hmb-native-editor-install-plan", "version": 1,
                "target": str(target), "editor_version": EXPECTED_EDITOR_VERSION,
                "descriptor_sha256": descriptor_sha, "candidate_sha256": descriptor["candidate_sha256"]}
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Native editor install plan changed or belongs to another release.")
    if value.get("original_sha256") not in _release_original_hashes(descriptor):
        raise ValueError("Native editor plan does not identify a supported original.")
    if value.get("already_current") is not (value["original_sha256"] == descriptor["candidate_sha256"]):
        raise ValueError("Native editor no-op plan is inconsistent.")
    if value.get("status") not in ("prepared", "applying", "applied", "rolled_back"):
        raise ValueError("Native editor install plan has an invalid transaction state.")
    return value, path, descriptor


@contextmanager
def _release_write_lock():
    """Serialize direct adapter writes too; OS locks release after a crash."""
    root = _release_plain_path(RELEASE_STATE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = _release_plain_path(root / ".editor-write.lock")
    with lock_path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise RuntimeError("Another native editor write is in progress; no editor file was changed.") from None
        try:
            yield
        finally:
            if acquired:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def prepare_release_install() -> dict:
    descriptor, descriptor_sha = _release_descriptor()
    target = _release_target()
    sdk_preflight = _release_sdk_preflight()
    original = target.read_bytes()
    original_sha = sha256(original)
    if original_sha not in _release_original_hashes(descriptor):
        raise ValueError("Unknown installed editor hash; keep the current app and request a supported package.")
    _require_release_stopped()
    already_current = original_sha == descriptor["candidate_sha256"]
    candidate = None
    if not already_current:
        if original_sha == EXPECTED_SOURCE_SHA256:
            candidate_text, _ = patch_editor_source(original.decode("utf-8"))
            candidate = candidate_text.encode("utf-8")
        else:
            candidate = _upgrade_previous_helper(original, descriptor)
        if sha256(candidate) != descriptor["candidate_sha256"]:
            raise ValueError("Generated native editor candidate differs from the verified release.")
    root = _release_plain_path(RELEASE_STATE_ROOT)
    transaction = root / uuid.uuid4().hex
    transaction.mkdir(parents=True, exist_ok=False)
    plan = {"schema": "hmb-native-editor-install-plan", "version": 1,
            "target": str(target), "editor_version": EXPECTED_EDITOR_VERSION,
            "descriptor_sha256": descriptor_sha, "original_sha256": original_sha,
            "candidate_sha256": descriptor["candidate_sha256"], "already_current": already_current,
            "sdk_preflight": sdk_preflight, "status": "prepared"}
    if not already_current:
        _atomic_write(transaction / "before.js", original)
        _atomic_write(transaction / "candidate.js", candidate)
    path = transaction / "plan.json"
    _json_write(path, plan)
    return {"plan": str(path), "already_current": already_current, "editor_version": EXPECTED_EDITOR_VERSION,
            "original_sha256": original_sha, "candidate_sha256": descriptor["candidate_sha256"],
            "sdk_preflight": sdk_preflight}


def _release_restore(plan: dict, path: Path) -> dict:
    target = _release_target()
    current = sha256(target.read_bytes())
    if plan["status"] in ("prepared", "rolled_back"):
        # A prepared transaction never owned a write. Another completed install
        # may now have the same candidate hash; it must not be rolled back here.
        return {"rolled_back": False, "write_not_started": True, "sha256": current}
    if plan["already_current"]:
        if current != plan["candidate_sha256"]:
            raise ValueError("Already-current editor changed after preparation; recovery refused.")
        return {"rolled_back": False, "already_current": True, "sha256": current}
    backup = _release_plain_path(path.parent / "before.js").read_bytes()
    if sha256(backup) != plan["original_sha256"]:
        raise ValueError("Native editor backup changed; recovery refused.")
    if current == plan["original_sha256"]:
        return {"rolled_back": False, "sha256": current}
    if current != plan["candidate_sha256"]:
        raise ValueError("Native editor changed outside this installation; recovery refused.")
    _atomic_write(target, backup)
    if sha256(target.read_bytes()) != plan["original_sha256"]:
        raise RuntimeError("Native editor recovery hash mismatch; preserved backup requires inspection.")
    return {"rolled_back": True, "sha256": plan["original_sha256"]}


def _apply_release_install_unlocked(path: Path) -> dict:
    plan, path, _ = _release_plan(path)
    _require_release_stopped()
    if _release_sdk_preflight() != plan.get("sdk_preflight"):
        raise ValueError("Griptape SDK changed after preflight; installation refused.")
    target = _release_target()
    current = sha256(target.read_bytes())
    if plan.get("status") == "applied" and current == plan["candidate_sha256"]:
        return {"plan": str(path), "already_current": plan["already_current"], "changed": not plan["already_current"],
                "editor_version": EXPECTED_EDITOR_VERSION, "sha256": current, "sdk_preflight": plan["sdk_preflight"]}
    if current != plan["original_sha256"]:
        raise ValueError("Native editor changed after preflight; installation refused.")
    if not plan["already_current"]:
        candidate = _release_plain_path(path.parent / "candidate.js").read_bytes()
        backup = _release_plain_path(path.parent / "before.js").read_bytes()
        if sha256(candidate) != plan["candidate_sha256"] or sha256(backup) != plan["original_sha256"]:
            raise ValueError("Native editor staged candidate or backup changed.")
    plan = {**plan, "status": "applying"}
    # Persist write ownership before replacement. If replacement or the final
    # receipt fails, both in-process recovery and the PS catch own this write.
    _json_write(path, plan)
    try:
        if not plan["already_current"]:
            _atomic_write(target, candidate)
        if sha256(target.read_bytes()) != plan["candidate_sha256"]:
            raise RuntimeError("Installed native editor hash mismatch.")
        _json_write(path, {**plan, "status": "applied"})
    except Exception:
        _release_restore(plan, path)
        raise
    return {"plan": str(path), "already_current": plan["already_current"], "changed": not plan["already_current"],
            "editor_version": EXPECTED_EDITOR_VERSION, "sha256": plan["candidate_sha256"],
            "sdk_preflight": plan["sdk_preflight"],
            "backup": None if plan["already_current"] else str(path.parent / "before.js")}


def apply_release_install(path: Path) -> dict:
    _release_plan(path)
    with _release_write_lock():
        return _apply_release_install_unlocked(path)


def _rollback_release_install_unlocked(path: Path) -> dict:
    plan, path, _ = _release_plan(path)
    _require_release_stopped()
    result = _release_restore(plan, path)
    _json_write(path, {**plan, "status": "rolled_back"})
    return result


def rollback_release_install(path: Path) -> dict:
    _release_plan(path)
    with _release_write_lock():
        return _rollback_release_install_unlocked(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=REPORT_DIR / "index-DEZU41rc.hmb-native-header.js")
    parser.add_argument("--manifest", type=Path, default=REPORT_DIR / "candidate.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--release-action", choices=("prepare", "apply", "rollback"))
    parser.add_argument("--release-plan", type=Path)
    args = parser.parse_args()
    if args.release_action:
        if args.apply or args.rollback or args.source != DEFAULT_SOURCE:
            raise ValueError("Release installation cannot be combined with prototype target options.")
        if args.release_action == "prepare":
            if args.release_plan:
                raise ValueError("Prepare creates its own bounded native editor plan.")
            result = prepare_release_install()
        elif args.release_plan is None:
            raise ValueError("The release action requires its generated install plan.")
        elif args.release_action == "apply":
            result = apply_release_install(args.release_plan)
        else:
            result = rollback_release_install(args.release_plan)
        print(json.dumps(result, ensure_ascii=False)); return
    if args.rollback:
        print(json.dumps(rollback(args.rollback), ensure_ascii=False)); return
    original = _read_pinned_source(args.source)
    candidate, evidence = patch_editor_source(original)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(args.output, candidate.encode("utf-8"))
    evidence.update(source=str(args.source.resolve()), candidate=str(args.output.resolve()))
    _json_write(args.manifest, evidence)
    if args.apply:
        if args.source.resolve() != DEFAULT_SOURCE.resolve():
            raise ValueError("Only the reviewed installed editor can be patched with --apply.")
        _require_desktop_stopped()
        if sha256(args.source.read_bytes()) != EXPECTED_SOURCE_SHA256:
            raise ValueError("Editor source changed during preparation; installation refused.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = REPORT_DIR / "backups" / stamp / EXPECTED_BUNDLE_NAME
        backup.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(backup, original.encode("utf-8"))
        try:
            _atomic_write(args.source, candidate.encode("utf-8"))
            if sha256(args.source.read_bytes()) != evidence["candidate_sha256"]:
                raise RuntimeError("Installed editor hash did not match the candidate.")
        except Exception:
            _atomic_write(args.source, original.encode("utf-8")); raise
        receipt = {**evidence, "schema": "hmb-color-lut-native-header-install", "target": str(args.source.resolve()),
            "backup": str(backup.resolve()), "installed_at": stamp}
        receipt_path = REPORT_DIR / "local-editor-install.json"
        _json_write(receipt_path, receipt)
        print(json.dumps({"installed": True, "receipt": str(receipt_path), "sha256": receipt["candidate_sha256"]})); return
    print(json.dumps({"prepared": True, "candidate": str(args.output), "manifest": str(args.manifest),
        "sha256": evidence["candidate_sha256"], "anchors": evidence["anchors"]}))


if __name__ == "__main__":
    main()
