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
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
import uuid


REPO = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_SHA256 = "1a0429b88c6b8dd1c7e6e053836d03f734a4d6453f8886e0693527c7498909e2"
SOURCE_PROFILE = "reviewed-stock"
EXPECTED_BUNDLE_NAME = "index-DEZU41rc.js"
SUPPORTED_PREVIOUS_CANDIDATE_SHA256 = "7bad6f6517c781c54e6d2e0cf170f0b2ed3bdef28b3cca57be79cce54bdd11bf"
SUPPORTED_PREVIOUS_HELPER_SHA256 = "39e5901cc8aa37d1d11850a255bcc209ab4724afe488817fc3f684a72ab01b63"
SUPPORTED_CURRENT_CANDIDATE_SHA256 = "93b497d21995e23ef6707f0d3a3d39dd897a76d0388f7d7c9677d5cd54ef57c1"
SUPPORTED_CURRENT_HELPER_SHA256 = "2ed5f48b1c454039e84d9cba7499e290111e1d9f1038b157c0391aae794903f8"
SUPPORTED_RECENT_CANDIDATE_SHA256 = "5e358586ae4b47fd698225c640fb65a4ed5b53dd27a398aa291b0606501e3131"
SUPPORTED_RECENT_HELPER_SHA256 = "34657ae82e7862d3c5fa798184623369537d798fe0b4baa313188e33fb15cec6"
SUPPORTED_LATEST_CANDIDATE_SHA256 = "c7100b21f4cca2fa55a368b9ac2740c923b5545c3a526005835b3fe47c65e343"
SUPPORTED_LATEST_HELPER_SHA256 = "9d67418745b5264ec892835370da1d19a0695d878cb03c80de696f00601f52b5"
HELPER = REPO / "resources/editor/hmb-color-lut-native-header.js"
DEFAULT_SOURCE = Path(os.environ.get("LOCALAPPDATA", "")) / (
    "ai.griptape.nodes.desktop/current/resources/editor-bundle/assets/" + EXPECTED_BUNDLE_NAME
)
REPORT_DIR = REPO / "reports/color-lut-native-header-20261023"
RELEASE_DESCRIPTOR = REPO / "resources/editor/native-editor-patch.json"
RELEASE_STATE_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "HMB_GP_Production/native-editor-installs"


class NativeEditorWriteBusy(RuntimeError):
    """A cooperating installer already owns the native editor write boundary."""


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
        raise ValueError("Editor source hash is not the reviewed source; no patch was produced.")
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
        "source_profile": SOURCE_PROFILE,
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
    if source.resolve() != DEFAULT_SOURCE.resolve():
        # A follow-up candidate may use the original baseline saved by this
        # installer. Never patch an already modified bundle or an arbitrary copy.
        receipt_file = REPORT_DIR / "local-editor-install.json"
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        if (receipt.get("schema") != "hmb-color-lut-native-header-install"
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
        "source_profile": SOURCE_PROFILE, "bundle_name": EXPECTED_BUNDLE_NAME,
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "helper_path": "resources/editor/hmb-color-lut-native-header.js",
        "patcher_path": "tools/hmb_color_lut_native_header_patch.py",
    }
    if "editor_version" in value or any(value.get(key) != item for key, item in expected.items()):
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
    _additional_profiles(value)
    return value, sha256(encoded)


def _additional_profiles(descriptor: dict) -> list[dict]:
    """Accept release-reviewed adapters, independent of version or bundle name."""
    profiles = descriptor.get("additional_profiles", [])
    if not isinstance(profiles, list) or len(profiles) > 16:
        raise ValueError("Invalid native editor adapter list.")
    seen = {EXPECTED_SOURCE_SHA256, descriptor.get("candidate_sha256")}
    seen.update(item["bundle_sha256"] for item in _release_previous_candidates(descriptor))
    result = []
    for profile in profiles:
        required = {
            "source_sha256", "candidate_sha256", "adapter_path", "adapter_sha256", "structural_fallback"
        }
        if (not isinstance(profile, dict) or not required.issubset(profile)
                or set(profile) - required - {"previous_candidate_sha256"}):
            raise ValueError("Invalid native editor adapter profile.")
        if type(profile["structural_fallback"]) is not bool:
            raise ValueError("Invalid native editor structural compatibility policy.")
        if profile["structural_fallback"]:
            raise ValueError("Unreviewed structural fallback cannot be enabled before renderer and safety validation.")
        for key in ("source_sha256", "candidate_sha256", "adapter_sha256"):
            digest = profile[key]
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Invalid native editor adapter hash.")
        if profile["source_sha256"] in seen or profile["candidate_sha256"] in seen or profile["source_sha256"] == profile["candidate_sha256"]:
            raise ValueError("Duplicate native editor adapter hash.")
        previous = profile.get("previous_candidate_sha256", [])
        if (not isinstance(previous, list) or len(previous) > 16
                or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in previous)
                or len(set(previous)) != len(previous)
                or any(item in seen or item in (profile["source_sha256"], profile["candidate_sha256"]) for item in previous)):
            raise ValueError("Invalid previous native editor adapter candidates.")
        if profile["adapter_path"] != "tools/hmb_native_semantic_adapter.py":
            raise ValueError("Unsupported native editor adapter path.")
        path = _release_plain_path(REPO / profile["adapter_path"])
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024 or sha256(path.read_bytes()) != profile["adapter_sha256"]:
            raise ValueError("Native editor adapter differs from the verified release.")
        seen.update((profile["source_sha256"], profile["candidate_sha256"]))
        seen.update(previous)
        result.append(profile)
    return result


def _active_git_profile(descriptor: dict) -> tuple[Path, dict | None] | None:
    """Resolve the editor's actual entry point, then match only reviewed bytes.

    No version number, supplied path, wildcard search, or old-file fallback is
    used. A missing or ambiguous entry is unsupported and never patched.
    """
    root = _release_plain_path(DEFAULT_SOURCE.parent.parent)
    entry = _release_plain_path(root / "index-editor.html")
    if not entry.exists():
        raise ValueError("Installed editor entry HTML is missing; existing files preserved.")
    if not entry.is_file() or entry.stat().st_size > 1024 * 1024:
        raise ValueError("Invalid installed editor entry HTML.")
    html = entry.read_text("utf-8")
    matches = re.findall(r'''\bsrc\s*=\s*["']\./assets/(index-[A-Za-z0-9_-]+\.js)["']''', html)
    if len(matches) != 1:
        raise ValueError("Installed editor entry must reference one unambiguous JS bundle.")
    target = _release_plain_path(root / "assets" / matches[0])
    if not target.is_file() or target.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Installed editor entry bundle is missing or oversized.")
    digest = sha256(target.read_bytes())
    if digest in _release_original_hashes(descriptor):
        return target, None
    for profile in _additional_profiles(descriptor):
        if digest in (profile["source_sha256"], profile["candidate_sha256"], *profile.get("previous_candidate_sha256", [])):
            return target, profile
    fallback = [profile for profile in _additional_profiles(descriptor) if profile["structural_fallback"]]
    if len(fallback) == 1:
        return target, fallback[0]
    raise ValueError("Unknown installed editor bundle; existing file preserved.")


def _release_previous_candidates(descriptor: dict) -> list[dict]:
    """Accept only reviewed helper chains and their previously released schemas."""
    older = {"bundle_sha256": SUPPORTED_PREVIOUS_CANDIDATE_SHA256,
             "helper_sha256": SUPPORTED_PREVIOUS_HELPER_SHA256}
    recent = {"bundle_sha256": SUPPORTED_CURRENT_CANDIDATE_SHA256,
              "helper_sha256": SUPPORTED_CURRENT_HELPER_SHA256}
    latest = {"bundle_sha256": SUPPORTED_RECENT_CANDIDATE_SHA256,
              "helper_sha256": SUPPORTED_RECENT_HELPER_SHA256}
    current = {"bundle_sha256": SUPPORTED_LATEST_CANDIDATE_SHA256,
               "helper_sha256": SUPPORTED_LATEST_HELPER_SHA256}
    if "previous_candidates" in descriptor:
        candidates = descriptor["previous_candidates"]
        if "previous_candidate" in descriptor or candidates not in ([current, latest, recent, older], [latest, recent, older], [recent, older]):
            raise ValueError("Unsupported previous native editor candidates.")
        return list(candidates)
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
    if len(names) != 1 or names[0].strip().lower().replace("_", "-") != "griptape-nodes":
        raise ValueError(prefix + "Invalid griptape-nodes package metadata.")
    sources = {
        "engine": site / "griptape_nodes/retained_mode/engine.py",
        "event_manager": site / "griptape_nodes/retained_mode/managers/event_manager.py",
        "node_manager": site / "griptape_nodes/retained_mode/managers/node_manager.py",
        **{name: site / ("griptape_nodes/retained_mode/events/" + name + ".py")
           for name in ("node_events", "flow_events", "workflow_events", "object_events", "connection_events")},
    }
    trees, hashes = {}, {}
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
    event_methods = {n.name: n for n in managers[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "_run_pre_dispatch_hooks" not in event_methods or not any(
            isinstance(n, ast.FunctionDef) and n.name == "current_request_type" for n in trees["event_manager"].body):
        raise ValueError(prefix + "Missing reentrant dispatch or request context capability.")
    boundary = event_methods["_run_pre_dispatch_hooks"]
    args = boundary.args
    positional = args.posonlyargs + args.args
    if (not isinstance(boundary, ast.FunctionDef) or len(positional) < 3
            or len(positional) - len(args.defaults) > 3 or any(value is None for value in args.kw_defaults)):
        raise ValueError(prefix + "Reentrant dispatch must accept request and context.")
    event_attrs = {n.attr for n in ast.walk(managers[0]) if isinstance(n, ast.Attribute)}
    if not {"_pre_dispatch_hooks", "_pre_dispatch_hooks_lock", "_hook_evaluation", "_request_type_to_manager"} <= event_attrs:
        raise ValueError(prefix + "Missing guarded dispatch ownership fields.")
    node_managers = [n for n in trees["node_manager"].body if isinstance(n, ast.ClassDef) and n.name == "NodeManager"]
    if len(node_managers) != 1:
        raise ValueError(prefix + "Missing node manager capability.")
    node_methods = {n.name for n in node_managers[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    guarded_node_methods = ("get_node_by_name", "get_node_parent_flow_by_name", "on_delete_node_request",
                            "on_reset_node_to_defaults_request", "on_add_nodes_to_node_group_request",
                            "on_remove_node_from_node_group_request")
    if not set(guarded_node_methods) <= node_methods:
        raise ValueError(prefix + "Missing node lookup or guarded delete/reset capability.")
    for name in guarded_node_methods:
        method = next(n for n in node_managers[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        args = method.args
        positional = args.posonlyargs + args.args
        if len(positional) < 2 or len(positional) - len(args.defaults) > 2 or any(value is None for value in args.kw_defaults):
            raise ValueError(prefix + "Guarded node method must accept its request/name: " + name)
    if not any(isinstance(n, ast.Attribute) and n.attr == "_name_to_parent_flow_name" for n in ast.walk(node_managers[0])):
        raise ValueError(prefix + "Missing retained-node inventory capability.")
    required_payloads = {
        "node_events": {"DeleteNodeRequest", "DeleteNodeResultFailure", "ResetNodeToDefaultsRequest", "ResetNodeToDefaultsResultFailure", "MoveNodeToNewFlowRequest", "MoveNodeToNewFlowResultFailure",
                        "AddNodesToNodeGroupRequest", "AddNodesToNodeGroupResultFailure",
                        "RemoveNodeFromNodeGroupRequest", "RemoveNodeFromNodeGroupResultFailure"},
        "flow_events": {"DeleteFlowRequest", "DeleteFlowResultFailure"},
        "workflow_events": {"DeleteWorkflowRequest", "DeleteWorkflowResultFailure"},
        "object_events": {"ClearAllObjectStateRequest", "ClearAllObjectStateResultFailure", "RenameObjectRequest", "RenameObjectResultFailure"},
        "connection_events": {"CreateConnectionRequest", "CreateConnectionResultFailure", "ListConnectionsForNodeRequest"},
    }
    for name, names_required in required_payloads.items():
        classes = {n.name for n in trees[name].body if isinstance(n, ast.ClassDef)}
        if not names_required <= classes:
            raise ValueError(prefix + "Missing guarded request or result capability: " + name)
    return {"package": "griptape-nodes",
            "capabilities": ["current_engine", *required, "reentrant_dispatch", "guarded_handler_ownership", "node_inventory", "guarded_request_payloads"], "source_sha256": hashes,
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
                "target": str(target), "source_profile": SOURCE_PROFILE,
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
            raise NativeEditorWriteBusy("Another native editor write is in progress; no editor file was changed.") from None
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
            "target": str(target), "source_profile": SOURCE_PROFILE,
            "descriptor_sha256": descriptor_sha, "original_sha256": original_sha,
            "candidate_sha256": descriptor["candidate_sha256"], "already_current": already_current,
            "sdk_preflight": sdk_preflight, "status": "prepared"}
    if not already_current:
        _atomic_write(transaction / "before.js", original)
        _atomic_write(transaction / "candidate.js", candidate)
    path = transaction / "plan.json"
    _json_write(path, plan)
    return {"plan": str(path), "already_current": already_current, "source_profile": SOURCE_PROFILE,
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
                "source_profile": SOURCE_PROFILE, "sha256": current, "sdk_preflight": plan["sdk_preflight"]}
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
            "source_profile": SOURCE_PROFILE, "sha256": plan["candidate_sha256"],
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


def _git_override_app_identity() -> dict:
    """Read the packaged-app prefix only; never write or extract app.asar."""
    resources = _release_plain_path(DEFAULT_SOURCE.parents[2])
    if DEFAULT_SOURCE != resources / "editor-bundle/assets" / EXPECTED_BUNDLE_NAME:
        raise ValueError("Git override target is outside the fixed packaged editor location.")
    archive = _release_plain_path(resources / "app.asar")
    info = archive.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Packaged Griptape app.asar is not a regular file.")
    with archive.open("rb") as stream:
        prefix = stream.read(16)
    if len(prefix) != 16:
        raise ValueError("Packaged Griptape app.asar prefix is invalid.")
    size_pickle, header_size, header_pickle, json_size = struct.unpack("<4I", prefix)
    if (size_pickle != 4 or not 0 < json_size <= header_pickle <= header_size
            or header_size > 16 * 1024 * 1024 or 8 + header_size > info.st_size):
        raise ValueError("Packaged Griptape app.asar prefix is invalid.")
    return {"path": str(archive), "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "prefix_sha256": sha256(prefix)}


def _git_override_result(status: str, reason: str, **details) -> dict:
    ready = status in ("current", "applied")
    return {"schema": "hmb-native-editor-git-override", "version": 1,
            "status": status, "disk_ready": ready, "restart_required": ready,
            "renderer_verified": False, "reason": reason,
            "changed": None if status == "error" else False,
            "already_current": status == "current", **details}


def _git_override_apply_unlocked() -> dict:
    """One bounded disk transaction. Running renderer modules are untouched.

    This explicit Git lifecycle path permits a single atomic file replacement
    while the app is running. It does not weaken the stopped-only ZIP API. A
    sharing violation leaves the original intact and returns a retry state.
    There are no engine requests, reloads, process stops, retries or watchers.
    """
    descriptor, descriptor_sha = _release_descriptor()
    target = _release_target()
    app_identity = _git_override_app_identity()
    sdk_preflight = _release_sdk_preflight()
    original = target.read_bytes()
    original_sha = sha256(original)
    if original_sha not in _release_original_hashes(descriptor):
        raise ValueError("Unknown installed editor hash; Git override preserved the existing file.")
    details = {"target": str(target), "source_profile": SOURCE_PROFILE, "candidate_sha256": descriptor["candidate_sha256"],
               "descriptor_sha256": descriptor_sha, "sdk_preflight": sdk_preflight}
    if original_sha == descriptor["candidate_sha256"]:
        return _git_override_result("current", "Pinned editor is already on disk; loaded renderer was not verified.", **details)
    if original_sha == EXPECTED_SOURCE_SHA256:
        candidate = patch_editor_source(original.decode("utf-8"))[0].encode("utf-8")
    else:
        candidate = _upgrade_previous_helper(original, descriptor)
    if sha256(candidate) != descriptor["candidate_sha256"]:
        raise ValueError("Generated native editor candidate differs from the verified Git release.")
    transaction = _release_plain_path(RELEASE_STATE_ROOT) / uuid.uuid4().hex
    transaction.mkdir(parents=True, exist_ok=False)
    _atomic_write(transaction / "before.js", original)
    _atomic_write(transaction / "candidate.js", candidate)
    path = transaction / "plan.json"
    plan = {"schema": "hmb-native-editor-git-override-plan", "version": 1,
            **details, "original_sha256": original_sha, "app_identity": app_identity,
            "already_current": False, "status": "prepared"}
    _json_write(path, plan)
    details.update(plan=str(path), backup=str(transaction / "before.js"))

    # Re-read both package and app immediately before writing. Git checkout or
    # desktop auto-updates racing preparation must never broaden the allowlist.
    def precommit() -> None:
        if _release_descriptor()[1] != descriptor_sha:
            raise ValueError("Git release changed during native preparation; target preserved.")
        if (_release_target() != target or _git_override_app_identity() != app_identity
                or _release_sdk_preflight() != sdk_preflight):
            raise ValueError("Packaged app or SDK changed during native preparation; target preserved.")
        if sha256(_release_plain_path(target).read_bytes()) != original_sha:
            raise ValueError("Native editor changed during Git preparation; target preserved.")
        if (sha256(_release_plain_path(transaction / "before.js").read_bytes()) != original_sha
                or sha256(_release_plain_path(transaction / "candidate.js").read_bytes()) != descriptor["candidate_sha256"]):
            raise ValueError("Git native staged candidate or backup changed; target preserved.")

    precommit()
    plan = {**plan, "status": "applying"}
    _json_write(path, plan)
    # Check again after the durable write-ownership receipt. Only this invocation
    # owns rollback; a later invocation seeing current bytes must not undo them.
    precommit()
    try:
        _atomic_write(target, candidate)
        if sha256(target.read_bytes()) != descriptor["candidate_sha256"]:
            raise RuntimeError("Installed Git native editor hash mismatch.")
        _json_write(path, {**plan, "status": "applied"})
    except Exception as error:
        current = sha256(_release_plain_path(target).read_bytes())
        if current == original_sha:
            # os.replace can fail because Windows holds the destination open.
            # No delete/truncate/retry is attempted and the saved backup remains.
            _json_write(path, {**plan, "status": "pending"})
            if isinstance(error, OSError):
                return _git_override_result("pending", "Native editor replacement was blocked; original retained. Retry after a normal restart.",
                                            reason_code="atomic_replace_blocked", **details)
            raise
        if current != descriptor["candidate_sha256"]:
            raise RuntimeError("Native editor changed outside this Git transaction; foreign bytes preserved and rollback refused.") from error
        # Restore only the exact bytes owned by this transaction, never a
        # different updater's content. Verify the durable backup before use.
        backup = _release_plain_path(transaction / "before.js").read_bytes()
        if sha256(backup) != original_sha:
            raise RuntimeError("Git native backup changed; rollback refused.") from error
        try:
            _atomic_write(target, backup)
            if sha256(target.read_bytes()) != original_sha:
                raise RuntimeError("Git native rollback hash mismatch.")
            _json_write(path, {**plan, "status": "rolled_back"})
        except Exception as recovery_error:
            return _git_override_result("error", "Native editor recovery could not be confirmed; inspect the preserved backup: " + str(recovery_error),
                                        reason_code="rollback_unconfirmed", **details)
        return _git_override_result("error", "Native editor transaction failed and restored its exact original.",
                                    reason_code="rolled_back", changed=False, **details)
    return _git_override_result("applied", "Native editor is ready on disk. Save work and restart Griptape normally once.",
                                changed=True, **details)


def _git_override_apply_active_unlocked() -> dict:
    """Apply a reviewed profile to the active entry, without version matching.

    A structural candidate for previously unseen bytes is deliberately not
    authorized by this path until its adapter contract and actual renderer
    behavior have been validated. Unknown input is never written.
    """
    descriptor, descriptor_sha = _release_descriptor()
    selected = _active_git_profile(descriptor)
    if selected is None:
        return _git_override_apply_unlocked()
    target, profile = selected
    app_identity = _git_override_app_identity()
    sdk_preflight = _release_sdk_preflight()
    original = target.read_bytes()
    original_sha = sha256(original)
    expected_candidate = descriptor["candidate_sha256"] if profile is None else profile["candidate_sha256"]
    source_hash = EXPECTED_SOURCE_SHA256 if profile is None else profile["source_sha256"]
    if original_sha not in ({source_hash, expected_candidate, *profile.get("previous_candidate_sha256", [])} if profile is not None else _release_original_hashes(descriptor)):
        raise ValueError("Editor structure has not been validated for automatic application; existing file preserved.")
    details = {"target": str(target), "source_profile": SOURCE_PROFILE if profile is None else "reviewed-adapter",
               "candidate_sha256": expected_candidate, "descriptor_sha256": descriptor_sha,
               "sdk_preflight": sdk_preflight}
    candidate = None
    if profile is not None:
        adapter_path = _release_plain_path(REPO / profile["adapter_path"])
        code = adapter_path.read_bytes()
        if sha256(code) != profile["adapter_sha256"]:
            raise ValueError("Native editor adapter changed; existing file preserved.")
        module_name = "_hmb_reviewed_native_adapter_" + uuid.uuid4().hex
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(module_name, loader=None))
        module.__file__ = str(adapter_path)
        sys.modules[module_name] = module
        try:
            exec(compile(code, str(adapter_path), "exec"), module.__dict__)
            if original_sha == expected_candidate:
                # The transform cannot run again on already-patched bytes.
                # Require an explicit readiness report rather than returning
                # `current` solely from the candidate hash.
                approval = getattr(module, "approval_evidence", None)
                if not callable(approval):
                    raise ValueError("Native editor adapter has no current-install approval evidence.")
                evidence = approval()
            else:
                transform = getattr(module, "patch_editor_source", None)
                if not callable(transform):
                    raise ValueError("Reviewed native editor adapter has no transform.")
                transformed, evidence = transform(original.decode("utf-8"), HELPER.read_text("utf-8"))
                if not isinstance(transformed, str):
                    raise ValueError("Native editor adapter returned an invalid candidate.")
                candidate = transformed.encode("utf-8")
        finally:
            if sys.modules.get(module_name) is module:
                sys.modules.pop(module_name, None)
        if not isinstance(evidence, dict):
            raise ValueError("Native editor adapter returned invalid evidence.")
        # This is a conservative eligibility gate, not proof that a renderer
        # or deletion path was actually tested. The release still needs an
        # independently reviewed descriptor, source and candidate hashes, and
        # corresponding real-runtime evidence before a profile is shipped.
        if (evidence.get("status") != "approved"
                or evidence.get("structural_anchors") != "matched"
                or evidence.get("live_renderer_verified") is not True
                or evidence.get("deletion_verified") is not True):
            raise ValueError("Native editor adapter is not approved for automatic installation; existing file preserved.")
        if (evidence.get("source_sha256") != source_hash
                or evidence.get("candidate_sha256") != expected_candidate
                or evidence.get("helper_sha256") != descriptor["helper_sha256"]):
            raise ValueError("Native editor adapter approval hashes are stale; existing file preserved.")
    if original_sha == expected_candidate:
        return _git_override_result("current", "Pinned editor is already on disk; loaded renderer was not verified.", **details)
    if profile is None:
        candidate = (patch_editor_source(original.decode("utf-8"))[0].encode("utf-8")
                     if original_sha == source_hash else _upgrade_previous_helper(original, descriptor))
    if sha256(candidate) != expected_candidate:
        raise ValueError("Native editor candidate differs from the reviewed profile.")
    transaction = _release_plain_path(RELEASE_STATE_ROOT) / uuid.uuid4().hex
    transaction.mkdir(parents=True, exist_ok=False)
    _atomic_write(transaction / "before.js", original)
    _atomic_write(transaction / "candidate.js", candidate)
    path = transaction / "plan.json"
    plan = {"schema": "hmb-native-editor-git-override-plan", "version": 1,
            **details, "original_sha256": original_sha, "app_identity": app_identity,
            "already_current": False, "status": "prepared"}
    _json_write(path, plan)
    details.update(plan=str(path), backup=str(transaction / "before.js"))
    def precommit() -> None:
        current_descriptor, digest = _release_descriptor()
        current = _active_git_profile(current_descriptor)
        if (digest != descriptor_sha or current != (target, profile)
                or _git_override_app_identity() != app_identity or _release_sdk_preflight() != sdk_preflight):
            raise ValueError("Editor entry or release changed during preparation; target preserved.")
        if (sha256(target.read_bytes()) != original_sha
                or sha256((transaction / "before.js").read_bytes()) != original_sha
                or sha256((transaction / "candidate.js").read_bytes()) != expected_candidate):
            raise ValueError("Editor or staged bytes changed during preparation; target preserved.")
    precommit()
    plan = {**plan, "status": "applying"}
    _json_write(path, plan)
    precommit()
    try:
        _atomic_write(target, candidate)
        if sha256(target.read_bytes()) != expected_candidate:
            raise RuntimeError("Installed native editor hash mismatch.")
        _json_write(path, {**plan, "status": "applied"})
    except Exception as error:
        current = sha256(_release_plain_path(target).read_bytes())
        if current == original_sha:
            _json_write(path, {**plan, "status": "pending"})
            if isinstance(error, OSError):
                return _git_override_result("pending", "Native editor replacement was blocked; original retained. Retry after a normal restart.", reason_code="atomic_replace_blocked", **details)
            raise
        if current != expected_candidate:
            raise RuntimeError("Native editor changed outside this Git transaction; foreign bytes preserved and rollback refused.") from error
        backup = _release_plain_path(transaction / "before.js").read_bytes()
        if sha256(backup) != original_sha:
            raise RuntimeError("Native editor backup changed; rollback refused.") from error
        try:
            _atomic_write(target, backup)
            if sha256(target.read_bytes()) != original_sha:
                raise RuntimeError("Native editor rollback hash mismatch.")
            _json_write(path, {**plan, "status": "rolled_back"})
        except Exception as recovery_error:
            return _git_override_result("error", "Native editor recovery could not be confirmed; inspect the preserved backup: " + str(recovery_error), reason_code="rollback_unconfirmed", **details)
        return _git_override_result("error", "Native editor transaction failed and restored its exact original.", reason_code="rolled_back", changed=False, **details)
    return _git_override_result("applied", "Native editor is ready on disk. Save work and restart Griptape normally once.", changed=True, **details)


def apply_git_override() -> dict:
    """Public ZIP-free lifecycle API; results describe disk state only."""
    try:
        # Reject unsupported source/package/app before even creating lock state.
        descriptor, _ = _release_descriptor()
        selected = _active_git_profile(descriptor)
        if selected is None:
            _release_target()
        _git_override_app_identity()
        _release_sdk_preflight()
        with _release_write_lock():
            return _git_override_apply_active_unlocked() if selected is not None else _git_override_apply_unlocked()
    except NativeEditorWriteBusy as error:
        return _git_override_result("pending", str(error), reason_code="write_lock_busy")
    except ValueError as error:
        return _git_override_result("unsupported", str(error), reason_code="preflight_rejected")
    except Exception as error:
        return _git_override_result("error", str(error), reason_code="native_transaction_failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=REPORT_DIR / "index-DEZU41rc.hmb-native-header.js")
    parser.add_argument("--manifest", type=Path, default=REPORT_DIR / "candidate.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--release-action", choices=("prepare", "apply", "rollback"))
    parser.add_argument("--release-plan", type=Path)
    parser.add_argument("--apply-git-override", action="store_true")
    args = parser.parse_args()
    if args.apply_git_override:
        if (args.release_action or args.release_plan or args.apply or args.rollback
                or args.source != DEFAULT_SOURCE or args.output != REPORT_DIR / "index-DEZU41rc.hmb-native-header.js"
                or args.manifest != REPORT_DIR / "candidate.json"):
            raise ValueError("Git override cannot be combined with target, prototype or release options.")
        # -I ignores Python encoding environment overrides. Keep this pipe
        # ASCII-safe even under Windows CP949 or a non-Latin user profile;
        # the parent decodes JSON bytes as UTF-8.
        print(json.dumps(apply_git_override(), ensure_ascii=True)); return
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
