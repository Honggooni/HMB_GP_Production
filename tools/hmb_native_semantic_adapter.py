"""HMB native editor adapter with an exact reviewed capability profile.

Every critical structural anchor is required exactly once. Only the exact
compiled-renderer and SDK-tested source/helper/candidate combination is eligible
for local application. Unknown bytes remain unvalidated. Desktop validation and
team release approval are separate from this source-level eligibility.
"""
from __future__ import annotations
import re

def _hmb_inline_iframe_session_binding():
    MARKER = '/* HMB_NATIVE_IFRAME_SESSION_BINDING_V1 */'
    HELPER = '/* HMB_NATIVE_IFRAME_SESSION_BINDING_V1 */\nfunction hmbNativeCreateIframeSessionBinder(apiClient) {\n  let sessionStateObserved = false;\n  return {\n    state(message) {\n      // An explicit null is authoritative too. Never manufacture a session or\n      // retain the previous session when the parent has cleared it.\n      sessionStateObserved = true;\n      apiClient.setSessionId(message.sessionId);\n    },\n    ready(config) {\n      // READY_ACK is only the initial fallback snapshot. A SESSION_STATE that\n      // arrived while initialize() awaited it is newer authority.\n      if (!sessionStateObserved) apiClient.setSessionId(config?.sessionId ?? null);\n    },\n  };\n}\nfunction hmbNativeUseIframeSessionBinder() {\n  // Witness belongs to this provider instance, never the module/API singleton.\n  // Remounting creates a fresh fallback boundary. The existing jYt effect\n  // cleanup prevents an old initialize continuation from invoking onReady.\n  const binding = (0,C.useRef)(null);\n  if (!binding.current) binding.current = hmbNativeCreateIframeSessionBinder(Id);\n  return binding.current;\n}\n'
    _PROVIDER = 'var gra=({children:e})=>{let t=jYt('
    _PROVIDER_BOUND = 'var gra=({children:e})=>{let hmbIframeSessionBinding=hmbNativeUseIframeSessionBinder();let t=jYt('
    _STATE = 'onSessionState:e=>Id.setSessionId(e.sessionId)'
    _STATE_BOUND = 'onSessionState:e=>hmbIframeSessionBinding.state(e)'
    _READY = 'Id.setSessionId(e.config.sessionId??null),e.config'
    _READY_BOUND = 'hmbIframeSessionBinding.ready(e.config),e.config'
    _GUARD = 'Refusing to send ${e} without a session: no topicOptions provided and apiClient has no sessionId.'

    def _one(source: str, old: str, new: str) -> str:
        count = source.count(old)
        if count != 1:
            raise ValueError(f'iframe session anchor count {count}: {old[:100]}')
        return source.replace(old, new, 1)

    def patch_iframe_session_binding(source: str) -> tuple[str, dict]:
        """Return candidate bytes plus a small receipt; unknown shapes fail closed.

    This is the ordered binder only. It does not alter no-session send guards,
    request topics, queueing, native optimistic setters, widget props or SDK.
    """
        if source.count(_GUARD) != 1:
            raise ValueError('native no-session guard is missing or ambiguous')
        if MARKER in source:
            if source.count(MARKER) != 1 or source.count(HELPER) != 1 or source.count(_PROVIDER_BOUND) != 1 or (source.count(_STATE_BOUND) != 1) or (source.count(_READY_BOUND) != 1) or any((anchor in source for anchor in (_PROVIDER, _STATE, _READY))):
                raise ValueError('partial or foreign iframe session binder; bytes preserved')
            return (source, {'kind': 'ordered_iframe_session_binder', 'changed': False, 'already_applied': True, 'guard_preserved': True})
        source = _one(source, _PROVIDER, HELPER + _PROVIDER_BOUND)
        source = _one(source, _STATE, _STATE_BOUND)
        source = _one(source, _READY, _READY_BOUND)
        return (source, {'kind': 'ordered_iframe_session_binder', 'changed': True, 'already_applied': False, 'guard_preserved': True, 'session_state': 'authoritative_including_null', 'ready_ack': 'provider_local_fallback_only'})
    return patch_iframe_session_binding

def _hmb_inline_parameter_send_first():
    MARKER = '/* HMB_NATIVE_HMB_PARAMETER_SEND_FIRST_V1 */'
    _HEAD = 'function pui(e){let t=(0,w.c)(12),'
    _HEAD_PATCHED = 'function pui(e){let t=(0,w.c)(13),'
    _MEMO = 's;t[0]===r?s=t[1]:(s=(e,t,i)=>'
    _MEMO_PATCHED = 's;t[0]===r&&t[12]===a?s=t[1]:(s=(e,t,i)=>'
    _TAIL = '},t[0]=r,t[1]=s);let c=s,l=hui'
    _TAIL_PATCHED = '},t[0]=r,t[1]=s,t[12]=a);let c=s,l=hui'
    _UPDATER = 'r(r=>{let a=r.find(t=>t.id===e);return a&&a.data.elements&&a.data.elements.map(e=>({id:e.id,name:e.name,matches_elem_id:e.id===t||e.name===t})),r.map(r=>tui(r,e,t,i))})'
    _SEND = 'Id.send(`SetParameterValueRequest`,{node_name:e,parameter_name:t,value:i})'
    _BODY = '{' + _UPDATER + ',' + _SEND + '}'
    _BODY_PATCHED = '{' + MARKER + 'const hmbNode=Array.isArray(a.current)?a.current.find(node=>node.id===e):null;' + 'const hmbSendFirst=hmbNode?.data?.metadata?.library===`HMB_GP_Production`' + '&&hmbIsNativeStudioType(hmbNode?.data?.node_type,hmbNode?.data?.metadata);' + 'if(hmbSendFirst)' + _SEND + ';' + _UPDATER + ';if(!hmbSendFirst)' + _SEND + '}'
    _GUARD = 'Refusing to send ${e} without a session: no topicOptions provided and apiClient has no sessionId.'

    def patch_hmb_parameter_send_first(source: str) -> tuple[str, dict]:
        """Retain native void/throw/guard semantics; only owned HMB order changes."""
        if not isinstance(source, str):
            raise TypeError('native source must be text')
        if source.count(_GUARD) != 1 or source.count('const hmbIsNativeStudioType =') != 1:
            raise ValueError('native session guard or existing HMB ownership predicate changed')
        pairs = ((_HEAD, _HEAD_PATCHED), (_MEMO, _MEMO_PATCHED), (_BODY, _BODY_PATCHED), (_TAIL, _TAIL_PATCHED))
        if MARKER in source:
            if source.count(MARKER) != 1 or any((source.count(new) != 1 or old in source for old, new in pairs)):
                raise ValueError('partial or foreign HMB native setter ordering patch')
            return (source, {'kind': 'hmb_parameter_send_first', 'changed': False, 'already_applied': True, 'guard_preserved': True, 'native_return_contract': 'void_or_same_sync_throw'})
        if any((source.count(old) != 1 for old, _ in pairs)):
            raise ValueError('native parameter setter anchors changed or ambiguous')
        for old, new in pairs:
            source = source.replace(old, new, 1)
        return (source, {'kind': 'hmb_parameter_send_first', 'changed': True, 'already_applied': False, 'guard_preserved': True, 'hmb_scope': 'owned_metadata_and_existing_type_predicate', 'memo_dependency': 'setNodes_and_nodesRef', 'native_return_contract': 'void_or_same_sync_throw', 'standard_node_order': 'optimistic_then_send', 'semantic_replay_added': False})
    return patch_hmb_parameter_send_first

_hmb_patch_iframe_session_binding = _hmb_inline_iframe_session_binding()
_hmb_patch_parameter_send_first = _hmb_inline_parameter_send_first()

def _hmb_session_bound_editor_source(source: str) -> str:
    source = _hmb_patch_iframe_session_binding(source)[0]
    return _hmb_patch_parameter_send_first(source)[0]


def one(value, old, new):
    if value.count(old) != 1:
        raise ValueError(f'header anchor count {value.count(old)}: {old[:100]}')
    return value.replace(old, new, 1)

def _fragments(source: str) -> tuple[str, str, str]:
    start = source.index('var k8t=({node_name:')
    end = source.index('};function A8t', start) + 2
    header = source[start:end]
    header = one(header, 'children:x,color:S})=>{let{settings:w}=h$()', 'children:x,color:S,hmbLibrary:hmbLibrary=null,hmbMetadata:hmbMetadata=null,hmbHostExpanded:hmbHostExpanded=!0,hmbHostRestoreView:hmbHostRestoreView=null})=>{let hmbNativeHeader=hmbUseColorLUTNativeHeader(t,e,hmbHostExpanded,hmbNativeStudioDoubleClick(t,e,b,hmbMetadata),hmbHostRestoreView,v,hmbMetadata);let{settings:w}=h$()')
    header = one(header, 'let e=w.nodeHeaderItems||[`lock`,`run`,`startFlow`];return x8t.filter', 'let e=hmbIsNativeStudioType(t,hmbMetadata)&&hmbNativeHeader.active?[`lock`,`reset`,`run`]:w.nodeHeaderItems||[`lock`,`run`,`startFlow`];return x8t.filter')
    header = one(header, '[w.nodeHeaderItems,oe]),we=', '[w.nodeHeaderItems,oe,t,hmbNativeHeader.active,hmbMetadata]),we=')
    header = one(header, 'ge=(0,C.useMemo)(()=>D8t(b),[b])', 'ge=(0,C.useMemo)(()=>D8t(hmbNativeStudioDoubleClick(t,e,b,hmbMetadata)),[b,t,e,hmbMetadata])')
    marker = 'Ee=S8t(t,S),De=C8t(t,!!Ee.backgroundColor,P);return'
    if header.count(marker) != 1:
        raise ValueError('header output anchor changed')
    head, output = header.split(marker)
    child_marker = 'children:[(0,z.jsxs)(`div`,{className:`flex items-center min-w-0 gap-3'
    separator = ',!VJ(t)&&(0,z.jsx)(`div`,{className:`flex flex-shrink-0 gap-3`'
    if output.count(child_marker) != 1 or output.count(separator) != 1 or (not output.endswith(']})};')):
        raise ValueError('header child boundaries changed')
    child_start = output.index(child_marker) + len('children:[')
    split = output.index(separator, child_start)
    identity = output[child_start:split]
    actions = output[split + 1:-5]
    if not identity.endswith('})]})') or not actions.endswith('})})'):
        raise ValueError('header child ending changed')
    outer = output[:child_start - len('children:[')]
    outer = one(outer, 'style:VJ(t)?Ee:ee,', 'style:hmbNativeHeader.active?{display:`none`}:VJ(t)?Ee:ee,')
    header = head + 'Ee=S8t(t,S),De=C8t(t,!!Ee.backgroundColor,P);let hmbNativeIdentity=' + identity + ',hmbNativeActions=hmbNativeConnectionActions(e,hmbLibrary,' + actions + ',re,ie);return hmbIsNativeStudioType(t,hmbMetadata)&&v?hmbNativeStudioCollapsedHeader(e,R,ee,y,_,de):' + outer + 'children:hmbNativeHeader.active?hmbColorLUTHeaderPortals(hmbNativeHeader,hmbNativeIdentity,hmbNativeActions,ee):[hmbNativeIdentity,hmbNativeActions]})};'
    start = source.index('function Dqr(')
    end = source.index('}function Oqr(', start) + 1
    parent = source[start:end]
    parent = one(parent, 'v=eZ(KX),y;t[0]', 'v=eZ(KX),y;let hmbNativeFrameActive=hmbUseColorLUTFrameActive(r.node_type,d,r.metadata),hmbFlow=xu();hmbUseColorLUTInitialGeometry(r,hmbNativeFrameActive,hmbFlow.getNodes,hmbFlow.setNodes);t[0]')
    parent = one(parent, 'let Xe=i&&!Se&&!ve,Ze=', 'let Xe=(i||hmbNativeFrameActive)&&!Se&&!ve,Ze=')
    old_geometry = 't[44]!==r.collapsed||t[45]!==d||t[46]!==fe.minHeight||t[47]!==pe||t[48]!==me?(he={nodeName:d,collapsed:r.collapsed,rolledUp:pe,metadataSize:me,fallbackHeight:fe.minHeight},t[44]=r.collapsed,t[45]=d,t[46]=fe.minHeight,t[47]=pe,t[48]=me,t[49]=he):he=t[49];'
    parent = one(parent, old_geometry, 'he={nodeName:d,nodeType:r.node_type,data:r,collapsed:r.collapsed,rolledUp:pe,metadataSize:me,fallbackHeight:fe.minHeight};')
    old_style = 't[87]!==ve||t[88]!==ge||t[89]!==F||t[90]!==_e||t[91]!==fe.minHeight?(Pe=$Gt(ve,ge,fe.minHeight,600,F,_e),t[87]=ve,t[88]=ge,t[89]=F,t[90]=_e,t[91]=fe.minHeight,t[92]=Pe):Pe=t[92];'
    parent = one(parent, old_style, 'Pe=hmbNativeStudioNodeStyle(r.node_type,ve,ge,fe.minHeight,600,F,_e,r.metadata);')
    old = 'let tt;t[150]!==u||t[151]!==Oe||t[152]!==et?(tt=(0,z.jsxs)(k8t,{...Oe,children:[et,u]}),t[150]=u,t[151]=Oe,t[152]=et,t[153]=tt):tt=t[153];'
    parent = one(parent, old, 'let tt=(0,z.jsxs)(k8t,{...Oe,hmbLibrary:r.metadata?.library,hmbMetadata:r.metadata,hmbHostExpanded:!Se,hmbHostRestoreView:r.hmb_native_studio_restore_view,children:[et,u]});')
    start = source.index('function lqr(')
    end = source.index('}function uqr(', start) + 1
    fold = source[start:end]
    fold = one(fold, '{nodeName:r,collapsed:i,rolledUp:a,metadataSize:o,fallbackHeight:s}=e', '{nodeName:r,nodeType:hmbNodeType,data:hmbData,collapsed:i,rolledUp:a,metadataSize:o,fallbackHeight:s}=e')
    fold = one(fold, 'let g;\nt[6]', 'let g;\nt[6]') if '\n' in fold else fold
    fold = one(fold, 't[0]===o?p=t[1]:(p=(e,t,r,i,a)=>oqr(e,t,r,i,o,a),t[0]=o,t[1]=p);', 'p=(e,t,n,i,a)=>hmbNativeStudioDimensions(hmbNodeType,e,t,n,i,o,a,r,hmbData?.metadata);')
    fold = one(fold, 'a!==T&&(E(a),f(!!a)),tHr(r,`${l}|${d}`);', 'a!==T&&(E(a),f(!!a)),tHr(r,`${l}|${d}`);hmbUseNativeStudioCollapseState(hmbData,l,u,d,y);')
    fold = one(fold, 'D=()=>{let e=!l;u(e),f(!1),v(e)}', 'D=()=>{let e=!l;hmbNativeStudioRecordCollapsed(hmbNodeType,r,e,hmbData?.metadata);u(e),f(!1),v(e)}')
    return (header, parent, fold)

def _compiled_helper(helper: str) -> str:
    helper = one(helper, 'if (typeof kq !== "undefined") kq.getState().setDirty(true);',
                 'if (typeof vY !== "undefined") vY.getState().setDirty(true);')
    helper = one(helper, 'function hmbNativeConnectionDeletionNotice(request, message) {',
                 '''function hmbNativePortRetainedNotice(result, request) {
  const message = __r(result);
  if (typeof message !== "string" || !message.includes("[HMB_CONNECTION_PORT_RETAINED]")) return false;
  const key = `${hmbNativeStudioFlowEpoch}:retained-port:${request?.node_name || ""}:${message}`;
  if ((hmbNativeConnectionNotices.get(key) || 0) + 1000 < Date.now()) {
    hmbNativeConnectionNotices.set(key, Date.now());
    CJ.info("다시 연결할 포트를 유지했습니다", { description: "기존 샷과 결과는 유지됩니다.", duration: 3000 });
  }
  return true;
}
function hmbNativeConnectionDeletionNotice(request, message) {''')
    for old, new in [('S.use', 'C.use'), ('S.cloneElement', 'C.cloneElement'), ('R.jsx', 'z.jsx'), ('R.jsxs', 'z.jsxs'), ('R.Fragment', 'z.Fragment'), ('T.createPortal', 'Cl.createPortal'), ('FEr()', 'eHr()'), ('Nu()', 'xu()'), ('Tjr(', 'oqr('), ('Sjr(', '$Gt('), ('wjr(', 'cqr('), (', mq, refresh)', ', JJ, refresh)'), ('className: H8', 'className: L8'), ('className: U8', 'className: R8'), ('className: W8', 'className: z8'), ('typeof vg', 'typeof __r')]:
        helper = helper.replace(old, new)
    helper = re.sub('\\bXd\\.', 'Id.', helper)
    helper = re.sub('\\big\\.', 'CJ.', helper)
    helper = re.sub('\\bvg\\(', '__r(', helper)
    helper = one(helper, 'return active;\n}\n\nfunction hmbColorLUTHeaderPortals', 'return active && hmbIsNativeStudioType(nodeType,metadata);\n}\n\nfunction hmbColorLUTHeaderPortals')
    ordered = "/* Experimental editor batch coordinator; only injected into research output. */\nfunction hmbMixedDeletionPlan(changes, nodes) {\n  const byId = new Map(nodes.map(node => [node.id, node]));\n  const ids = new Set(changes.map(change => change.id));\n  if (ids.size !== changes.length || [...ids].some(id => !byId.has(id))) throw Error('stale selection');\n  let related = false;\n  const plan = changes.map((change, index) => {\n    let node = byId.get(change.id), depth = 0, seen = new Set([change.id]);\n    const expectedParent = node.parentId;\n    while (node.parentId) {\n      if (seen.has(node.parentId) || !byId.has(node.parentId)) throw Error('invalid parent graph');\n      if (ids.has(node.parentId)) related = true;\n      seen.add(node.parentId); node = byId.get(node.parentId); depth++;\n    }\n    return { change, index, depth, expectedParent, group: nodes.some(child => child.parentId === change.id) };\n  }).sort((a, b) => b.depth - a.depth || a.index - b.index);\n  return related ? plan : null;\n}\nclass HmbOrderedDeletes {\n  constructor(plan, epoch, getNodes, apply, operation) {\n    this.plan = plan; this.epoch = epoch; this.getNodes = getNodes; this.apply = apply;\n    this.operation = operation; this.current = null; this.cancelled = false;\n  }\n  async run() {\n    for (const row of this.plan) {\n      if (this.cancelled || this.epoch !== hmbNativeStudioFlowEpoch) return 'stale';\n      const node = this.getNodes().find(item => item.id === row.change.id);\n      if (!node || node.parentId !== row.expectedParent) return 'changed';\n      const signal = new Promise(resolve => { this.current = { id: row.change.id, group: row.group, event: null, applied: false, resolve }; });\n      const currentId = row.change.id;\n      const warning = setTimeout(() => {\n        if (this.current?.id === currentId && !this.cancelled)\n          CJ.warning('삭제 결과 확인 중', { description: '결과가 확인되기 전에는 후속 삭제를 진행하지 않습니다.', duration: 8000 });\n      }, 30000);\n      try { this.apply([{ ...row.change, hmbGuardedDelete: true }]); }\n      catch (_) { this.notify(row.change.id, false); }\n      const result = await signal;\n      clearTimeout(warning);\n      if (this.cancelled || this.epoch !== hmbNativeStudioFlowEpoch) return 'stale';\n      if (result !== true) return result === 'unknown' ? 'unknown' : 'failed';\n    }\n    this.current = null; return 'complete';\n  }\n  notify(id, success) {\n    const item = this.current;\n    if (!item || item.id !== id || item.event !== null || this.cancelled) return;\n    item.event = success === true;\n    if (!item.event || !item.group || item.applied) item.resolve(item.event);\n  }\n  groupApplied(id, success) {\n    const item = this.current;\n    if (!item || item.id !== id || !item.group || item.applied || this.cancelled) return;\n    if (success !== true) { item.resolve(false); return; }\n    item.applied = true; if (item.event === true) item.resolve(true);\n  }\n  cancel() { this.cancelled = true; this.current?.resolve('stale'); }\n}\n"
    helper = one(helper, 'function hmbNativeGuardNodeDeletion(changes, nodes, apply) {', ordered + '\nfunction hmbNativeGuardNodeDeletion(changes, nodes, apply, getNodes = () => nodes) {')
    helper = one(helper, '  hmbNativeDeletionPending.clear();\n  hmbNativeConnectionNotices.clear();', '  for (const op of hmbNativeDeletionPending.values()) op?.sequence?.cancel();\n  hmbNativeDeletionPending.clear();\n  hmbNativeConnectionNotices.clear();')
    helper = one(helper, '      apply(removals.map(change => hmbNames.has(change.id)', '      let plan = null;\n      if (names.some(name => hmbNames.has(name))) {\n        try { plan = hmbMixedDeletionPlan(removals, getNodes()); }\n        catch (_) { release(); CJ.warning("삭제 대상을 다시 확인하세요", { description: "노드 구성 변경으로 삭제를 중단했습니다." }); return; }\n      }\n      if (plan) {\n        operation.until = Number.POSITIVE_INFINITY;\n        operation.sequence = new HmbOrderedDeletes(plan, epoch, getNodes, apply, operation);\n        operation.sequence.run().then(state => {\n          release();\n          if (state === "changed" || state === "failed") CJ.warning("남은 삭제 중단", { description: "노드 구성이 변경되었거나 삭제가 거절되었습니다." });\n        }).catch(() => { release(); CJ.error("삭제 확인 실패", { description: "남은 노드 삭제를 중단했습니다." }); });\n        return;\n      }\n      apply(removals.map(change => hmbNames.has(change.id)')
    helper = one(helper, 'function hmbNativeGuardNodeDeletion(changes, nodes, apply, getNodes = () => nodes) {', 'function hmbNativeSubmitCheckedDelete(nodeName) {\n  const operation=hmbNativeDeletionPending.get(nodeName);\n  if (!operation || operation.epoch!==hmbNativeStudioFlowEpoch || typeof operation.checkToken!=="string" || !operation.checkToken)\n    return Promise.reject(new Error("[HMB_DELETE_SELECTION_CHANGED] 삭제 대상을 다시 확인하세요."));\n  return Id.request("HMBDeleteCheckedNodeRequest", {node_name:nodeName, check_token:operation.checkToken});\n}\nfunction hmbNativeCheckedDeleteFailure(nodeName, error) {\n  const operation=hmbNativeDeletionPending.get(nodeName);\n  if (!operation || operation.epoch!==hmbNativeStudioFlowEpoch) return;\n  operation.sequence?.notify(nodeName,false);\n  hmbNativeDeletionFinished(nodeName);\n  CJ.warning("삭제 중단", {description:__r(error),duration:8000});\n}\n\nfunction hmbNativeGuardNodeDeletion(changes, nodes, apply, getNodes = () => nodes) {')
    helper = one(helper, 'const liveNames = new Set(nodes.map(node => node.id));', 'operation.checkToken=result.check_token;\n      if (hmbNames.size && (typeof operation.checkToken!=="string" || !operation.checkToken)) { release(); CJ.warning("삭제 보호를 다시 시작해야 합니다", {description:"현재 엔진의 객체 확인 기능이 준비되지 않았습니다."}); return; }\n      const liveNames = new Set(nodes.map(node => node.id));')
    return helper


_SOUND_READ_PREVIOUS_CANDIDATE = "033e68f8583319ee9e4d6f4c80089b736f9057d09b2c7a2fc8644eded8b06f50"
_SHOT_BASKET_BASE = "1abf6fb7d18cbf32bb556fe93c4c5c05a20829407423ad62ba446d5c62ab1da6"
_SHOT_BASKET_PREVIOUS_CANDIDATE = "d7f5a296f6dbed3db3ea6018e4116caa98d70a4d9e2efba86364c80d963b096b"
_SHOT_BASKET_HEADER_PREVIOUS_CANDIDATE = "9e601029eba8cdb0ad72f93b66700d463be2ccf09d48122a842a185bebf0f128"
_SHOT_BASKET_SPRITE_PREVIOUS_CANDIDATE = "60dd6a2d4cfb03455be340c1bf6db83a35ad4b4d42d6bcc679c5feed0d18f44c"
_SHOT_BASKET_COMPACT_PREVIOUS_CANDIDATE = "6e25fa65084ecad3fa13dc5beb3b9cecd21e2080d3588a3a6df7f8816e6a1b9c"
_SHOT_BASKET_STARTUP_PREVIOUS_CANDIDATE = "56ae29378596be76fe0d72ab15d6d2fec4f7c5521a8257ed9af901be22db4cd6"
_SHOT_BASKET_FLICKER_PREVIOUS_CANDIDATE = "21e6bac07d06895989328cb7bfd22fe4ea29a6ed79177e2bb04c50de6692326a"
_SHOT_BASKET_HEADER_FADE_PREVIOUS_CANDIDATE = "3faf55400109cc2f7ce8fadae0533c188399d67b7e20f47365d7e15175d041c7"
# Payload integrity only. The reviewed candidate hash below remains an
# independent admission gate; changing UI bytes never approves a new editor.
_SHOT_BASKET_UI_SHA256 = "5a4213870298c7d2fa1d5087e08065ac1b2c3008244f9cce44b3d019f84b8fbc"
_SHOT_BASKET_ARTWORK_SHA256 = "e152f842096b8abdf976c9d843197fdc90e0189bc96ca712f16738601ceb6cfa"
_SHOT_BASKET_EXTRA_ARTWORK_SHA256 = "2a17375f028dfdeb019ed2a39ca61dac5bf4b247de9618da77e370d9895b128e"
_SHOT_BASKET_HEADER_ARTWORK_SHA256 = "d41540bd6b75b4c7d73962948f223ff1aacc0cf41f88a6ef00b6c443ae9f7b9c"
_SHOT_BASKET_CANDIDATE = "3b4d4ad3b820c2fc194b230b4678baa3c63c0341efec2275f19eb2d9536430db"
_REVIEWED_PREVIOUS_CANDIDATES = (
    _SOUND_READ_PREVIOUS_CANDIDATE,
    "47950ae47b76152c2923597fb47a6b514e3ce87dcfe4bf9291270512fa92e2df",
    "3cf11148efbf8c107daa6ce0fb597d3808794912cd1d2b913373917c481401e1",
    "e594ed5b6e94d68b7dbc4cdfda0440190fff95e9588e03838a0f9284f9d55f67",
    "463f2dc87b98e63af151f11ef7aa9dbf0ea249d399a8dc5a508e4a8917352158",
    "d208403e7463adac2b3f778151aab55d3709892460460e8142fae8e91add4fbe",
    "c9d95e131cce8db713447a1196c273edb4e5377e24efc4d7f94ca4715e3dc02f",
    "9ec59e780c665cd304703d5e303fa0844de4149a1583fc66490a38369da87b78",
    "72dc87c51089c65554a9fcb44f80e38872338bb5a9c1ca4c9058d582e981f6e5",
    "ccabfc9bfddb67896231e0e75b067e659287f19fca143b2355f2c295d5da5251",
    "bcb4ea1649a78258c87b795cb73762e09c96575b0f811cb8ec34f609e21c3e17",
)


def _upgrade_reviewed_candidate(source: str, helper: str) -> str:
    """Replace only our helper in an exact previously reviewed compiled bundle."""
    import hashlib
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if source_digest not in _REVIEWED_PREVIOUS_CANDIDATES:
        raise ValueError("unknown previous HMB editor candidate; existing bytes preserved")
    marker = "/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1"
    boundary = "\nvar k8t=({node_name:"
    if source.count(marker) != 1 or source.count(boundary) != 1:
        raise ValueError("ambiguous HMB helper boundaries")
    start = source.index(marker)
    end = source.index(boundary, start)
    source = source[:start] + _compiled_helper(helper) + source[end:]
    if source_digest in {_SOUND_READ_PREVIOUS_CANDIDATE,
                         "47950ae47b76152c2923597fb47a6b514e3ce87dcfe4bf9291270512fa92e2df",
                         "3cf11148efbf8c107daa6ce0fb597d3808794912cd1d2b913373917c481401e1",
                         "e594ed5b6e94d68b7dbc4cdfda0440190fff95e9588e03838a0f9284f9d55f67",
                         "463f2dc87b98e63af151f11ef7aa9dbf0ea249d399a8dc5a508e4a8917352158",
                         "d208403e7463adac2b3f778151aab55d3709892460460e8142fae8e91add4fbe"}:
        return source
    if source_digest == "c9d95e131cce8db713447a1196c273edb4e5377e24efc4d7f94ca4715e3dc02f":
        return _bash_snapshot_transport_bridge(source)
    if source_digest == "9ec59e780c665cd304703d5e303fa0844de4149a1583fc66490a38369da87b78":
        return _bash_snapshot_transport_bridge(_capsule_motion_bridge(source))
    if source_digest == "72dc87c51089c65554a9fcb44f80e38872338bb5a9c1ca4c9058d582e981f6e5":
        return _capsule_motion_bridge(_bash_readiness_bridge(source))
    return _capsule_motion_bridge(_bash_live_input_bridge(_port_retention_notice_bridge(source)))


def _capsule_motion_bridge(source: str) -> str:
    return one(source,
        'E,(e,t,r)=>m({w:t,h:r}),d?f:void 0,d),Id.request(`SetNodeMetadataRequest`',
        'E,(e,t,r)=>m({w:t,h:r}),d?f:hmbNativeStudioCapsuleDuration(_,s),d),Id.request(`SetNodeMetadataRequest`')


def _bash_live_input_bridge(source: str) -> str:
    """Merge live HMB sources while preserving the stock editor and dirty layers."""
    src = source
    helpers = "// Validate and merge scoped HMB Image Bash source updates without replacing editor layers.\nfunction hmbModalLiveBindings(meta) {\n  const hmb = meta && meta.hmb_image_bash;\n  const rows = hmb && hmb.source_bindings;\n  if (!Array.isArray(rows)) throw new Error('source bindings unavailable');\n  const byUid = new Map(), ids = new Set();\n  for (const row of rows) {\n    if (!row || typeof row.source_uid !== 'string' || !row.source_uid || typeof row.source_id !== 'string' || !row.source_id || typeof row.url !== 'string' || !row.url || byUid.has(row.source_uid) || ids.has(row.source_id)) throw new Error('ambiguous source identities');\n    byUid.set(row.source_uid, row); ids.add(row.source_id);\n  }\n  return byUid;\n}\nfunction hmbModalLivePlan(oldMeta, nextMeta) {\n  const old = hmbModalLiveBindings(oldMeta), next = hmbModalLiveBindings(nextMeta);\n  const inputs = nextMeta?.input_images, images = nextMeta?.konva_json?.images;\n  if (!Array.isArray(inputs) || !Array.isArray(images)) throw new Error('scene is unavailable');\n  const aliases = [];\n  for (const [uid, prior] of old) {\n    const current = next.get(uid);\n    if (!current || current.source_id !== prior.source_id) throw new Error('existing input changed or removed');\n    const before = oldMeta?.hmb_image_bash?.prepared_source_hashes?.['input:' + prior.source_id];\n    const after = nextMeta?.hmb_image_bash?.prepared_source_hashes?.['input:' + current.source_id];\n    const keys = ['sha256','rgba_sha256','width','height'];\n    const valid = p => p && /^[a-f0-9]{64}$/.test(p.sha256) && /^[a-f0-9]{64}$/.test(p.rgba_sha256) && Number.isInteger(p.width) && p.width > 0 && Number.isInteger(p.height) && p.height > 0;\n    if (before || after) {\n      if (!valid(before) || !valid(after) || keys.some(k => before[k] !== after[k])) throw new Error('existing input content changed');\n    } else if (prior.url !== current.url) throw new Error('unverified source URL changed');\n    if (prior.url !== current.url) aliases.push({source_uid:uid, source_id:current.source_id, src:current.url});\n  }\n  const suppressed = nextMeta.hmb_image_bash.suppressed_source_uids || [];\n  if (!Array.isArray(suppressed)) throw new Error('invalid suppressed sources');\n  const additions = [];\n  for (const [uid, current] of next) {\n    if (old.has(uid) || suppressed.includes(uid)) continue;\n    const sourceRows = inputs.filter(x => x?.source_uid === uid && x?.id === current.source_id && x?.url === current.url);\n    const layers = images.filter(x => x?.source_uid === uid && x?.source_id === current.source_id && x?.type === 'image');\n    if (sourceRows.length !== 1 || layers.length !== 1 || !layers[0].id || layers[0].src !== current.url) throw new Error('new source mapping is incomplete');\n    additions.push({...layers[0], name: sourceRows[0].name || layers[0].name || 'Image Layer'});\n  }\n  return {additions, aliases};\n}\nfunction hmbModalLiveMerge(existing, additions) {\n  if (!Array.isArray(existing) || !Array.isArray(additions)) throw new Error('invalid layer collection');\n  const ids = new Set(existing.map(row => row.id)), uids = new Set(existing.map(row => row.source_uid).filter(Boolean));\n  if (ids.size !== existing.length) throw new Error('existing layer ids are ambiguous');\n  for (const row of additions) if (!row.id || !row.source_uid || ids.has(row.id) || uids.has(row.source_uid)) throw new Error('new layer identity collision');\n  let order = Math.max(-1, ...existing.map(row => Number.isFinite(row.order) ? row.order : -1));\n  return existing.concat(additions.map(row => ({...row, order: ++order})));\n}\nfunction hmbModalLiveOutputURL(layer, meta) {\n  if (!meta || layer?.type !== 'image' || !layer.source_uid || !layer.source_id) return layer?.src || '';\n  const binding=hmbModalLiveBindings(meta).get(layer.source_uid);\n  return binding && binding.source_id===layer.source_id ? binding.url : (layer.src || '');\n}\nfunction hmbModalLiveBound(promise, signal, ms) {\n  return new Promise((resolve,reject)=>{\n    let done=false, timer;\n    const end=(fn,value)=>{if(done)return;done=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);fn(value)};\n    const abort=()=>end(reject,new Error('canceled'));\n    if (signal?.aborted) return abort();\n    signal?.addEventListener('abort',abort,{once:true});\n    timer=setTimeout(()=>end(reject,new Error('source_timeout')),Math.max(0,ms));\n    Promise.resolve(promise).then(value=>end(resolve,value),error=>end(reject,error));\n  });\n}\nfunction hmbModalLiveImage(src, signal) {\n  return new Promise((resolve,reject)=>{\n    const image=new window.Image;image.crossOrigin='anonymous';let done=false;\n    const end=(ok)=>{if(done)return;done=true;image.onload=null;image.onerror=null;signal?.removeEventListener('abort',abort);ok?resolve():reject(new Error('image_load_failed'))};\n    const abort=()=>{if(done)return;image.onload=null;image.onerror=null;image.src='';done=true;signal?.removeEventListener('abort',abort);reject(new Error('canceled'))};\n    if(signal?.aborted)return abort();signal?.addEventListener('abort',abort,{once:true});image.onload=()=>end(true);image.onerror=()=>end(false);image.src=src;\n  });\n}\n"
    anchor = 'var iri=C.memo(function(){let{workflowName:e}=N2(),{engineVersion:t}=j$(),'
    assert src.count(anchor) == 1
    src = src.replace(anchor, helpers + '\n' + anchor + '{subscribeToEvent:hmbLiveSubscribe}=IX(),{getNode:hmbLiveNode}=xu(),hmbLiveFlow=eZ(v=>v.flowName),', 1)
    anchor = '},[lt]);(0,C.useEffect)(()=>{if(F&&D===`select`&&fe.current)'
    assert src.count(anchor) == 1
    hook = '},[lt]);\nconst hmbMetaRef=(0,C.useRef)(null),hmbPending=(0,C.useRef)(null),hmbScope=(0,C.useRef)(null),hmbRevision=(0,C.useRef)(0),hmbLayers=(0,C.useRef)(j),hmbCommit=(0,C.useRef)(null),hmbQueued=(0,C.useRef)(null),hmbSaving=(0,C.useRef)(false),hmbBlocked=(0,C.useRef)(false);\nconst [hmbTick,hmbSetTick]=(0,C.useState)(0),[hmbWarning,hmbSetWarning]=(0,C.useState)(``),[hmbBusy,hmbSetBusy]=(0,C.useState)(false);hmbLayers.current=j;\nconst hmbUiNode=hmbLiveNode(b),hmbSession=hmbScope.current?.name===b&&hmbScope.current?.flow===hmbLiveFlow&&hmbScope.current?.epoch===hmbNativeStudioFlowEpoch,hmbUiActive=!!hmbSession&&(!hmbUiNode||(hmbUiNode?.data?.node_type===`HMBImageBash`&&hmbUiNode?.data?.metadata?.library===`HMB_GP_Production`&&hmbScope.current?.workspace===hmbUiNode?.data?.metadata?.hmb_image_bash_workspace_id&&hmbScope.current?.channel===hmbUiNode?.data?.metadata?.hmb_image_bash_channel_uuid));\n(0,C.useEffect)(()=>{\n if(!_||!b||!hmbLiveFlow)return;hmbSetWarning(``);hmbSetBusy(false);const n=hmbLiveNode(b),m=n?.data?.metadata;\n if(n?.data?.node_type!==`HMBImageBash`||m?.library!==`HMB_GP_Production`||!m?.hmb_image_bash_workspace_id||!m?.hmb_image_bash_channel_uuid)return;\n const initial=g?.meta?.hmb_image_bash||{},scope={name:b,flow:hmbLiveFlow,epoch:hmbNativeStudioFlowEpoch,workspace:m.hmb_image_bash_workspace_id,channel:m.hmb_image_bash_channel_uuid,identity:m.hmb_connection_identity_v1||null,instance:initial.node_instance_uuid||null,revision:Number.isInteger(initial.workspace_revision)?initial.workspace_revision:null};\n hmbScope.current=scope;hmbMetaRef.current=g?.meta||{};hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;hmbBlocked.current=false;hmbSetWarning(``);hmbSetBusy(false);let active=true;\n const invalid=()=>{active=false;hmbBlocked.current=true;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;hmbSetBusy(false);hmbSetWarning(`작업 공간이 변경되었습니다. 입력을 확인한 뒤 편집기를 다시 여세요.`)};\n const check=()=>{const x=hmbLiveNode(b),v=x?.data?.metadata;return active&&hmbScope.current===scope&&scope.epoch===hmbNativeStudioFlowEpoch&&x?.data?.node_type===`HMBImageBash`&&v?.library===`HMB_GP_Production`&&v?.hmb_image_bash_workspace_id===scope.workspace&&v?.hmb_image_bash_channel_uuid===scope.channel&&(!scope.identity||v?.hmb_connection_identity_v1===scope.identity)};\n scope.check=check;\n const off=hmbLiveSubscribe(`ExecutionEvent`,event=>{if(event?.payload_type!==`ParameterValueUpdateEvent`||event.payload?.node_name!==b||event.payload?.parameter_name!==`bash_image`)return;if(hmbBlocked.current)return;if(!check()){invalid();return}const doc=event.payload.value,h=doc?.meta?.hmb_image_bash;if(!doc||typeof doc!==`object`||!h)return;if(!scope.instance||scope.revision===null||h.workspace_id!==scope.workspace||h.channel_uuid!==scope.channel||h.node_instance_uuid!==scope.instance||!Number.isInteger(h.workspace_revision)){invalid();return}if(h.workspace_revision<scope.revision)return;scope.revision=h.workspace_revision;if(hmbSaving.current){invalid();return}if(hmbCommit.current){hmbQueued.current={doc,scope,check};return}hmbPending.current={doc,scope,revision:++hmbRevision.current,check};hmbSetBusy(true);hmbSetTick(v=>v+1)});\n const offDelete=hmbLiveSubscribe(`DeleteNodeResultSuccess`,event=>{if(!event?.node_name||event.node_name===b)invalid()});\n const offCreate=hmbLiveSubscribe(`CreateNodeResultSuccess`,event=>{if(event?.node_name===b)invalid()});\n const offReset=hmbLiveSubscribe(`ResetNodeToDefaultsResultSuccess`,event=>{if(event?.node_name===b)invalid()});\n return()=>{active=false;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;if(hmbScope.current===scope){hmbScope.current=null;hmbMetaRef.current=null}off?.();offDelete?.();offCreate?.();offReset?.()};\n},[_,b,e,hmbLiveFlow,hmbLiveNode,hmbLiveSubscribe]);\n(0,C.useEffect)(()=>{\n const pending=hmbPending.current;if(!_||!pending||hmbCommit.current||ee||!xe||!$e.current||$e.current===`loading`)return;let canceled=false;const aborter=new AbortController,deadline=Date.now()+30000;\n (async()=>{try{const meta=pending.doc.meta,plan=hmbModalLivePlan(hmbMetaRef.current,meta),loaded=[];\n   for(const layer of plan.additions){let src=layer.src;try{src=(await hmbModalLiveBound(qY(src,t),aborter.signal,deadline-Date.now())).url||src}catch(error){if(error?.message===`source_timeout`||aborter.signal.aborted)throw error}await hmbModalLiveBound(hmbModalLiveImage(src,aborter.signal),aborter.signal,deadline-Date.now());loaded.push({...layer,src})}\n   if(canceled||hmbPending.current!==pending||pending.revision!==hmbRevision.current||!pending.check())return;\n   hmbModalLiveMerge(hmbLayers.current,loaded);\n   if(!loaded.length){hmbMetaRef.current=meta;hmbPending.current=null;hmbSetWarning(``);hmbSetBusy(false);return}\n   hmbCommit.current={pending,meta,loaded};M(prev=>{if(pending.revision!==hmbRevision.current||!pending.check())return prev;try{return hmbModalLiveMerge(prev,loaded)}catch{return prev}});hmbSetTick(v=>v+1);\n }catch(error){aborter.abort();if(!canceled&&hmbPending.current===pending&&pending.check()){hmbBlocked.current=true;hmbPending.current=null;hmbSetBusy(false);hmbSetWarning(error?.message===`source_timeout`?`이미지 로드 시간이 초과되었습니다. 입력을 확인하고 편집기를 다시 여세요.`:`입력 이미지를 확인할 수 없습니다. 입력을 확인하고 편집기를 다시 여세요.`)}}})();\n return()=>{canceled=true;aborter.abort()};\n},[_,b,e,hmbLiveFlow,hmbTick,ee,xe]);\n(0,C.useEffect)(()=>{const c=hmbCommit.current;if(!c)return;if(c.pending.revision!==hmbRevision.current||!c.pending.check()){hmbCommit.current=null;hmbQueued.current=null;return}const ok=c.loaded.every(x=>j.some(y=>y.id===x.id&&y.source_uid===x.source_uid));hmbCommit.current=null;hmbPending.current=null;if(ok){hmbMetaRef.current=c.meta;hmbSetWarning(``);const queued=hmbQueued.current;hmbQueued.current=null;if(queued&&queued.check()){hmbPending.current={...queued,revision:++hmbRevision.current};hmbSetBusy(true);hmbSetTick(v=>v+1)}else hmbSetBusy(false)}else{hmbBlocked.current=true;hmbQueued.current=null;hmbSetBusy(false);hmbSetWarning(`이미지 레이어가 충돌합니다. 입력을 되돌린 뒤 다시 시도하세요.`)}},[j,hmbTick,_,b,e,hmbLiveFlow]);\n(0,C.useEffect)(()=>{if(F&&D===`select`&&fe.current)'
    src = src.replace(anchor, hook, 1)
    anchor = 'meta:{...g?.meta,created_at:new Date().toISOString()'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'meta:{...g?.meta,...(hmbApplySnapshot?.meta||{}),created_at:new Date().toISOString()', 1)
    anchor = 'c.push({id:e.source_id||e.id,url:e.src||``,name:e.name})'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'c.push({id:e.source_id||e.id,url:hmbApplySnapshot?.meta?hmbModalLiveOutputURL(e,hmbApplySnapshot.meta):(e.src||``),name:e.name})', 1)
    anchor = 'let l=j.map(e=>{let t=e.x,r=e.y;return{...e,x:t,y:r,canvas:e.type===`brush`?{}:void 0}})'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'let l=j.map(e=>{let t=e.x,r=e.y;return{...e,...(hmbApplySnapshot?.meta&&e.type===`image`?{src:hmbModalLiveOutputURL(e,hmbApplySnapshot.meta)}:{}),x:t,y:r,canvas:e.type===`brush`?{}:void 0}})', 1)
    anchor = 'Pt=async()=>{if(!x.current)return;ve(!0);'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'Pt=async()=>{if(!x.current)return;const hmbApplyNode=hmbLiveNode(b),hmbApplyMeta=hmbApplyNode?.data?.metadata,hmbIsBash=hmbApplyNode?.data?.node_type===`HMBImageBash`&&hmbApplyMeta?.library===`HMB_GP_Production`,hmbBound=!!(hmbApplyMeta?.hmb_image_bash_workspace_id&&hmbApplyMeta?.hmb_image_bash_channel_uuid);if(hmbSession&&(!hmbScope.current?.check?.()||hmbSaving.current||hmbPending.current||hmbCommit.current||hmbQueued.current||hmbBlocked.current))return;if(hmbIsBash&&hmbBound&&!hmbSession)return;const hmbApplySnapshot=hmbIsBash&&hmbSession?{scope:hmbScope.current,revision:hmbRevision.current,meta:hmbMetaRef.current}:null;if(hmbApplySnapshot)hmbSaving.current=true;ve(!0);', 1)
    anchor = 'let t=e.getContext(`2d`);if(!t)return;t.fillStyle=he'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'let t=e.getContext(`2d`);if(!t){if(hmbApplySnapshot){hmbSaving.current=false;hmbBlocked.current=true;hmbSetWarning(`이미지를 저장할 수 없습니다. 입력을 확인하고 편집기를 다시 여세요.`);ve(!1)}return}t.fillStyle=he', 1)
    anchor = 'try{await Ft(i)}catch(e){console.error(`Error saving canvas:`,e),ve(!1)}},Ft=async t=>'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'try{await Ft(i,hmbApplySnapshot)}catch(e){console.error(`Error saving canvas:`,e),ve(!1)}finally{if(hmbApplySnapshot)hmbSaving.current=false}},Ft=async(t,hmbApplySnapshot)=>', 1)
    anchor = 'y({value:s.url,type:`ImageUrlArtifact`,name:o,meta:'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'if(hmbApplySnapshot&&(hmbBlocked.current||hmbApplySnapshot.scope!==hmbScope.current||hmbApplySnapshot.revision!==hmbRevision.current||!hmbApplySnapshot.scope.check())){ve(!1);return}y({value:s.url,type:`ImageUrlArtifact`,name:o,meta:', 1)
    anchor = 'children:[(0,z.jsx)(wG,{className:`flex-1`,onClick:e=>{e.stopPropagation(),Kt()},variant:`ghost`,children:`Cancel`}),(0,z.jsx)(wG,{className:`flex-1`,disabled:_e,onClick:e=>{e.stopPropagation(),Pt()}'
    assert src.count(anchor) == 1
    src = src.replace(anchor, 'children:[hmbUiActive&&hmbWarning?(0,z.jsx)(`div`,{role:`status`,className:`text-destructive`,children:hmbWarning}):hmbUiActive&&hmbBusy?(0,z.jsx)(`div`,{role:`status`,children:`새 입력 이미지를 확인하는 중입니다.`}):null,(0,z.jsx)(wG,{className:`flex-1`,onClick:e=>{e.stopPropagation(),Kt()},variant:`ghost`,children:`Cancel`}),(0,z.jsx)(wG,{className:`flex-1`,disabled:_e||(hmbUiActive&&(hmbBusy||!!hmbWarning)),onClick:e=>{e.stopPropagation();if(!hmbUiActive){Pt();return}const scope=hmbScope.current;Pt().catch(()=>{if(scope&&hmbScope.current===scope){hmbBlocked.current=true;hmbSetWarning(`이미지를 저장할 수 없습니다. 입력을 확인하고 편집기를 다시 여세요.`)}}).finally(()=>{if(scope)hmbSaving.current=false})}', 1)
    return _bash_readiness_bridge(src)


def _bash_readiness_bridge(src: str) -> str:
    """Gate editor opening and reconcile current inputs without discarding edits."""
    helpers = r'''// HMB_BASH_PREPARATION_V1: current source readiness, not a timer or image count.
function hmbBashPreparation(value) {
  const p=value?.preparation;
  if (!p || p.schema!=='hmb-image-bash-preparation-v1' || !['idle','preparing','ready','error'].includes(p.phase)
      || typeof p.ready!=='boolean' || !Number.isInteger(p.workspace_revision) || p.workspace_revision<0
      || typeof p.node_instance_uuid!=='string' || !p.node_instance_uuid) throw Error('preparation_unavailable');
  return p;
}
function hmbBashNodeScope(node) {
  const m=node?.data?.metadata;
  return node?.data?.node_type==='HMBImageBash' && m?.library==='HMB_GP_Production'
    ? {workspace:m.hmb_image_bash_workspace_id||'',channel:m.hmb_image_bash_channel_uuid||'',identity:m.hmb_connection_identity_v1||null} : null;
}
function hmbBashMatches(p, scope) {
  return p.workspace_id===scope.workspace && p.channel_uuid===scope.channel;
}
function hmbBashSamePreparation(a,b) {
  return a.node_instance_uuid===b.node_instance_uuid && a.workspace_id===b.workspace_id
    && a.channel_uuid===b.channel_uuid && a.workspace_revision===b.workspace_revision && a.ready===b.ready && a.phase===b.phase;
}
async function hmbBashReadCurrent(name, check) {
  const read=async parameter=>{
    const reply=await Id.request('GetParameterValueRequest',{node_name:name,parameter_name:parameter});
    if (!check()) throw Error('workspace_changed');
    if (!reply || !Object.prototype.hasOwnProperty.call(reply,'value')) throw Error('preparation_unavailable');
    return reply.value;
  };
  const first=hmbBashPreparation(await read('HMB_IMAGE_BASH_UI'));
  if (!first.ready || first.phase==='preparing' || first.phase==='error') return {preparation:first,doc:null};
  const doc=await read('bash_image'),last=hmbBashPreparation(await read('HMB_IMAGE_BASH_UI'));
  if (!hmbBashSamePreparation(first,last)) return {preparation:last,doc:null};
  const h=doc?.meta?.hmb_image_bash;
  if (first.workspace_id && (!h || h.workspace_id!==first.workspace_id || h.channel_uuid!==first.channel_uuid
      || h.node_instance_uuid!==first.node_instance_uuid || h.workspace_revision!==first.workspace_revision)) return {preparation:last,doc:null};
  return {preparation:last,doc};
}
async function hmbBashOpenSnapshot(name, fallback, getNode) {
  const initial=hmbBashNodeScope(getNode(name));
  if (!initial) return {value:fallback};
  const epoch=hmbNativeStudioFlowEpoch;
  const check=()=>{const next=hmbBashNodeScope(getNode(name));return epoch===hmbNativeStudioFlowEpoch && next
    && next.workspace===initial.workspace && next.channel===initial.channel && next.identity===initial.identity};
  try {
    const snapshot=await hmbBashReadCurrent(name,check);
    if (!check() || !hmbBashMatches(snapshot.preparation,initial)) throw Error('workspace_changed');
    if (!snapshot.doc || !snapshot.preparation.ready) {
      CJ.info(snapshot.preparation.phase==='error'?'이미지 소스 확인이 필요합니다':'작업 준비 중…',
        {description:snapshot.preparation.error||'최신 이미지 준비가 끝나면 편집기 열기가 활성화됩니다.'});
      return null;
    }
    return {value:snapshot.doc};
  } catch {
    CJ.info('편집기 준비 상태를 확인할 수 없습니다',{description:'입력 연결을 확인하고 다시 시도하세요. 기존 편집은 유지됩니다.'});
    return null;
  }
}
function hmbUseBashParameterReadiness(props) {
  const {getNode}=xu(),{subscribeToEvent}=IX(),flow=eZ(v=>v.flowName),name=props.nodeName;
  const owned=props.parameterName==='bash_image'&&props.ui_options?.modal==='ImageBashModal'&&!!hmbBashNodeScope(getNode(name));
  const [view,setView]=C.useState(null);
  C.useEffect(()=>{
    if(!owned)return;let active=true,eventGeneration=0;const epoch=hmbNativeStudioFlowEpoch;
    const update=value=>{if(!active||epoch!==hmbNativeStudioFlowEpoch)return;try{setView(hmbBashPreparation(value))}catch{setView(null)}};
    const off=subscribeToEvent('ExecutionEvent',event=>{if(event?.payload_type==='ParameterValueUpdateEvent'
      &&event.payload?.node_name===name&&event.payload?.parameter_name==='HMB_IMAGE_BASH_UI'){eventGeneration++;update(event.payload.value)}});
    const queryGeneration=eventGeneration;
    Id.request('GetParameterValueRequest',{node_name:name,parameter_name:'HMB_IMAGE_BASH_UI'}).then(reply=>{if(queryGeneration===eventGeneration)update(reply?.value)}).catch(()=>{if(active&&epoch===hmbNativeStudioFlowEpoch&&queryGeneration===eventGeneration)setView(null)});
    return()=>{active=false;off?.()};
  },[owned,name,flow,subscribeToEvent]);
  if(!owned)return props;
  const current=hmbBashNodeScope(getNode(name)),valid=view&&current&&hmbBashMatches(view,current);
  const busy=!valid||view.phase==='preparing',failed=valid&&view.phase==='error';
  return {...props,executing:props.executing||busy,
    ui_options:{...props.ui_options,button_label:busy?'작업 준비 중…':failed?'소스 확인 필요':props.ui_options.button_label},
    tooltip:busy?'최신 원본을 확인하고 있습니다. 기존 편집 내용은 유지됩니다.':failed?(view.error||'이미지 라이브러리에서 다시 시도하세요.'):props.tooltip};
}
'''
    # Keep the existing native renderer and memoization contracts. Only the HMB
    # parameter consumes the additional readiness projection; stock nodes return
    # their exact original props and open behavior.
    src = one(src, 'function yLr(e){let t=(0,w.c)(33),',
        'function yLr(e){const {getNode:hmbBashOpenNode}=xu();e=hmbUseBashParameterReadiness(e);let t=(0,w.c)(33),')
    src = one(src, 't=await _({parameterValue:e,nodeName:l});t&&a&&!h&&a(t)',
        'hmbOpen=await hmbBashOpenSnapshot(l,e,hmbBashOpenNode);if(!hmbOpen)return;let t=await _({parameterValue:hmbOpen.value,nodeName:l});t&&a&&!h&&a(t)')
    # Image preview context-menu opens use the same fresh-snapshot handshake.
    src = one(src, '}){let m=(0,C.useMemo)(()=>t?.name??`Image`,[t]),h=',
        '}){const {getNode:hmbBashOpenNode}=xu();let m=(0,C.useMemo)(()=>t?.name??`Image`,[t]),h=')
    src = one(src, 'T=(0,C.useCallback)(async()=>{let e=await y({parameterValue:t,nodeName:c});e&&r&&r(e)},[t,c,y,r])',
        'T=(0,C.useCallback)(async()=>{const ready=await hmbBashOpenSnapshot(c,t,hmbBashOpenNode);if(!ready)return;let e=await y({parameterValue:ready.value,nodeName:c});e&&r&&r(e)},[t,c,y,r])')
    start = src.index('const hmbMetaRef=(0,C.useRef)(null)')
    boundary = '(0,C.useEffect)(()=>{if(F&&D===`select`&&fe.current)'
    end = src.index(boundary, start)
    hook = r'''const hmbMetaRef=C.useRef(null),hmbPending=C.useRef(null),hmbScope=C.useRef(null),hmbRevision=C.useRef(0),hmbLayers=C.useRef(j),hmbCommit=C.useRef(null),hmbQueued=C.useRef(null),hmbSaving=C.useRef(false),hmbBlocked=C.useRef(false),hmbRefresh=C.useRef(null),hmbHydrated=C.useRef(false);
const [hmbTick,hmbSetTick]=C.useState(0),[hmbWarning,hmbSetWarning]=C.useState(''),[hmbBusy,hmbSetBusy]=C.useState(false);hmbLayers.current=j;
const hmbUiNode=hmbLiveNode(b),hmbUiScope=hmbBashNodeScope(hmbUiNode),hmbSession=hmbScope.current?.name===b&&hmbScope.current?.flow===hmbLiveFlow&&hmbScope.current?.epoch===hmbNativeStudioFlowEpoch;
const hmbUiActive=!!hmbSession&&!!hmbUiScope&&hmbScope.current?.workspace===hmbUiScope.workspace&&hmbScope.current?.channel===hmbUiScope.channel;
const hmbRenderPreparing=!!(_&&hmbUiScope?.workspace&&(!hmbUiActive||hmbBusy));
C.useEffect(()=>{
 if(!_||!b||!hmbLiveFlow)return;const initial=hmbBashNodeScope(hmbLiveNode(b));
 if(!initial?.workspace||!initial.channel){hmbScope.current=null;hmbSetBusy(false);hmbSetWarning('');return;}
 const h=g?.meta?.hmb_image_bash||{},scope={name:b,flow:hmbLiveFlow,epoch:hmbNativeStudioFlowEpoch,...initial,
   instance:h.node_instance_uuid||null,revision:Number.isInteger(h.workspace_revision)?h.workspace_revision:-1,wanted:-1};
 hmbScope.current=scope;hmbMetaRef.current=g?.meta||{};hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;hmbBlocked.current=false;hmbHydrated.current=false;
 hmbSetWarning('');hmbSetBusy(true);let active=true,refreshGeneration=0;
 const check=()=>{const n=hmbBashNodeScope(hmbLiveNode(b));return active&&hmbScope.current===scope&&scope.epoch===hmbNativeStudioFlowEpoch&&n
   &&n.workspace===scope.workspace&&n.channel===scope.channel&&n.identity===scope.identity};scope.check=check;
 const warning=message=>{hmbBlocked.current=true;hmbSetBusy(false);hmbSetWarning(message)};
 const invalidate=()=>{active=false;refreshGeneration++;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;
   warning('작업 공간이 변경되었습니다. 편집 내용은 유지됩니다. 연결을 확인하세요.')};
 const preparing=prep=>{if(!check()||!hmbBashMatches(prep,scope)){invalidate();return;}
   if(scope.instance&&prep.node_instance_uuid!==scope.instance){invalidate();return;}
   scope.instance=prep.node_instance_uuid;scope.wanted=Math.max(scope.wanted,prep.workspace_revision);
   refreshGeneration++;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;
   if(prep.phase==='error'){warning(prep.error||'이미지 원본을 확인할 수 없습니다. 다시 시도하세요.');return;}
   hmbBlocked.current=false;hmbSetWarning('');hmbSetBusy(true);
 };
 const accept=(doc,prep)=>{
   if(!check()){invalidate();return;}const meta=doc?.meta,next=meta?.hmb_image_bash;
   if(!prep?.ready||!hmbBashMatches(prep,scope)||!next||next.workspace_id!==scope.workspace||next.channel_uuid!==scope.channel
     ||next.node_instance_uuid!==prep.node_instance_uuid||next.workspace_revision!==prep.workspace_revision)return;
   if(scope.instance&&scope.instance!==next.node_instance_uuid){invalidate();return;}
   if(next.workspace_revision<Math.max(scope.revision,scope.wanted))return;
   if(hmbSaving.current){warning('저장 중 입력이 변경되었습니다. 저장 결과를 적용하지 않았습니다.');return;}
   scope.instance=next.node_instance_uuid;scope.revision=next.workspace_revision;scope.wanted=next.workspace_revision;hmbBlocked.current=false;hmbSetWarning('');
   if(hmbCommit.current){hmbQueued.current={doc,scope,check};return;}
   hmbPending.current={doc,scope,revision:++hmbRevision.current,check};hmbSetBusy(true);hmbSetTick(v=>v+1);
 };
 const refresh=async()=>{
   if(!check())return;const token=++refreshGeneration;hmbSetBusy(true);
   try{const current=await hmbBashReadCurrent(b,()=>check()&&token===refreshGeneration);
     if(!check()||token!==refreshGeneration)return;
     if(!current.preparation.ready||!current.doc){preparing(current.preparation);return;}
     accept(current.doc,current.preparation);
   }catch(error){if(check()&&token===refreshGeneration)warning('최신 이미지 상태를 확인하지 못했습니다. 다시 시도하세요.');}
 };hmbRefresh.current=refresh;
 const off=hmbLiveSubscribe('ExecutionEvent',event=>{
   if(event?.payload_type!=='ParameterValueUpdateEvent'||event.payload?.node_name!==b)return;
   if(!check()){invalidate();return;}
   if(event.payload.parameter_name==='HMB_IMAGE_BASH_UI'){
     try{const prep=hmbBashPreparation(event.payload.value);if(prep.workspace_revision<scope.wanted)return;
       if(!prep.ready)preparing(prep);else {
         if(scope.instance&&prep.node_instance_uuid!==scope.instance){invalidate();return;}
         if(prep.workspace_revision>Math.max(scope.revision,scope.wanted)){
           scope.wanted=prep.workspace_revision;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;
         }
         if(!hmbSaving.current||prep.workspace_revision!==scope.revision)refresh();
       }}catch{warning('입력 준비 상태가 올바르지 않습니다. 다시 시도하세요.');}
   }else if(event.payload.parameter_name==='bash_image'&&!hmbSaving.current){refresh();}
 });
 const offDelete=hmbLiveSubscribe('DeleteNodeResultSuccess',event=>{if(!event?.node_name||event.node_name===b)invalidate()});
 const offCreate=hmbLiveSubscribe('CreateNodeResultSuccess',event=>{if(event?.node_name===b)invalidate()});
 const offReset=hmbLiveSubscribe('ResetNodeToDefaultsResultSuccess',event=>{if(event?.node_name===b)invalidate()});
 // Subscribe before rereading: events between the button click and modal mount
 // cannot strand an old snapshot. An already-open editor uses this same path.
 refresh();
 return()=>{active=false;refreshGeneration++;hmbRevision.current++;hmbPending.current=null;hmbCommit.current=null;hmbQueued.current=null;
   if(hmbScope.current===scope){hmbScope.current=null;hmbMetaRef.current=null;hmbRefresh.current=null;}off?.();offDelete?.();offCreate?.();offReset?.();};
},[_,b,e,hmbLiveFlow,hmbLiveNode,hmbLiveSubscribe]);
C.useEffect(()=>{
 const pending=hmbPending.current;if(!_||!pending||hmbCommit.current||ee||!xe||!x.current)return;
 // Stock's private cache marker can be cleared by a delayed close callback.
 // Observe the actual hydrated layers and stage instead of that marker.
 if(!hmbHydrated.current){const seeded=g?.meta?.konva_json?.images||[];
   if(seeded.some(layer=>!hmbLayers.current.some(current=>current.id===layer.id)))return;
   hmbHydrated.current=true;}
 let canceled=false;const aborter=new AbortController,deadline=Date.now()+30000;
 (async()=>{try{const meta=pending.doc.meta,plan=hmbModalLivePlan(hmbMetaRef.current,meta),loaded=[];
   for(const layer of plan.additions){let src=layer.src;try{src=(await hmbModalLiveBound(qY(src,t),aborter.signal,deadline-Date.now())).url||src}catch(error){if(error?.message==='source_timeout'||aborter.signal.aborted)throw error;}
     await hmbModalLiveBound(hmbModalLiveImage(src,aborter.signal),aborter.signal,deadline-Date.now());loaded.push({...layer,src});}
   if(canceled||hmbPending.current!==pending||pending.revision!==hmbRevision.current||!pending.check())return;
   hmbModalLiveMerge(hmbLayers.current,loaded);
   if(!loaded.length){hmbMetaRef.current=meta;hmbPending.current=null;hmbSetWarning('');hmbSetBusy(false);return;}
   hmbCommit.current={pending,meta,loaded};M(prev=>pending.revision===hmbRevision.current&&pending.check()?hmbModalLiveMerge(prev,loaded):prev);hmbSetTick(v=>v+1);
 }catch(error){aborter.abort();if(!canceled&&hmbPending.current===pending&&pending.check()){
   hmbBlocked.current=true;hmbPending.current=null;hmbSetBusy(false);hmbSetWarning(error?.message==='source_timeout'?'이미지 로드 시간이 초과되었습니다. 같은 창에서 다시 시도하세요.':'이미지 소스 또는 레이어 충돌을 확인하세요. 기존 편집은 유지됩니다.');}}
 })();return()=>{canceled=true;aborter.abort()};
},[_,b,e,hmbLiveFlow,hmbTick,ee,xe,j,g]);
C.useEffect(()=>{const c=hmbCommit.current;if(!c)return;
 if(c.pending.revision!==hmbRevision.current||!c.pending.check()){hmbCommit.current=null;hmbQueued.current=null;return;}
 const ok=c.loaded.every(x=>j.some(y=>y.id===x.id&&y.source_uid===x.source_uid));hmbCommit.current=null;hmbPending.current=null;
 if(ok){hmbMetaRef.current=c.meta;hmbSetWarning('');const queued=hmbQueued.current;hmbQueued.current=null;
   if(queued&&queued.check()){hmbPending.current={...queued,revision:++hmbRevision.current};hmbSetBusy(true);hmbSetTick(v=>v+1);}else hmbSetBusy(false);
 }else{hmbBlocked.current=true;hmbQueued.current=null;hmbSetBusy(false);hmbSetWarning('이미지 레이어가 충돌합니다. 기존 편집은 유지됩니다.');}
},[j,hmbTick,_,b,e,hmbLiveFlow]);
const hmbRetry=()=>{const scope=hmbScope.current;if(!scope?.check?.())return;hmbSetWarning('');hmbSetBusy(true);hmbBlocked.current=false;
 Id.request('GetParameterValueRequest',{node_name:b,parameter_name:'HMB_IMAGE_BASH_UI'}).then(reply=>{
   if(!scope.check())throw Error('workspace_changed');const header=reply?.value,prep=hmbBashPreparation(header);
   const source=header?.bound_source,instance=header?.source_instances?.[source];
   if(!source||!instance||!hmbBashMatches(prep,scope))throw Error('workspace_changed');
   return Id.request('SetParameterValueRequest',{node_name:b,parameter_name:'HMB_IMAGE_BASH_UI',value:{hmb_image_bash_command:{
     operation:'retry_inputs',source_node_name:source,workspace_id:prep.workspace_id,source_instance_id:instance}}});
 }).then(()=>hmbRefresh.current?.()).catch(()=>{if(scope.check()){hmbBlocked.current=true;hmbSetBusy(false);hmbSetWarning('입력을 다시 확인하지 못했습니다. 연결을 확인하세요.');}});};
'''
    src = src[:start] + hook + src[end:]
    src = one(src, 'var iri=C.memo(function(){', helpers + '\nvar iri=C.memo(function(){')
    row = 'className:`flex overflow-hidden flex-row flex-1`,children:['
    heading = src.index('children:`Image Bash Editor`')
    row_start = src.index(row, heading)
    if row_start - heading > 8000:
        raise ValueError('Image Bash editor body boundary changed')
    overlay = 'className:`flex overflow-hidden flex-row flex-1`,style:{position:`relative`},children:[hmbRenderPreparing?(0,z.jsx)(`div`,{role:`status`,"aria-live":`polite`,style:{position:`absolute`,inset:0,zIndex:50,display:`grid`,placeItems:`center`,background:`var(--background,#111827)`},children:`작업 준비 중… 최신 이미지를 불러오고 있습니다.`}):null,'
    src = src[:row_start] + overlay + src[row_start + len(row):]
    src = one(src, 'hmbUiActive&&hmbWarning?(0,z.jsx)(`div`,{role:`status`,className:`text-destructive`,children:hmbWarning})',
        'hmbUiActive&&hmbWarning?(0,z.jsxs)(`div`,{role:`status`,className:`text-destructive`,children:[hmbWarning,(0,z.jsx)(wG,{onClick:hmbRetry,disabled:!hmbScope.current?.check?.(),children:`다시 시도`})]})')
    src = one(src, 'disabled:_e||(hmbUiActive&&(hmbBusy||!!hmbWarning))',
        'disabled:_e||hmbRenderPreparing||(hmbUiActive&&(hmbBusy||!!hmbWarning))')
    return _bash_snapshot_transport_bridge(src)


def _bash_snapshot_transport_bridge(src: str) -> str:
    """Read only small host headers; the current event document stays local.

    A host-issued snapshot token plus scope and editor commit fences the local
    value. Never fetch the canonical PNG/receipt document merely to open a
    modal. Unknown or delayed documents remain closed until an update arrives.
    """
    start = src.index('async function hmbBashReadCurrent(')
    end = src.index('async function hmbBashOpenSnapshot(', start)
    reader = r'''const hmbBashDocumentCache=new Map();
function hmbBashRememberDocument(name,doc,owner,kind='props') {
  const h=doc?.meta?.hmb_image_bash;
  const previous=hmbBashDocumentCache.get(name),owners=previous?.epoch===hmbNativeStudioFlowEpoch?previous.owners:new Set();
  const prior=previous?.epoch===hmbNativeStudioFlowEpoch?previous:null;
  const valid=!!h&&typeof h.editor_snapshot_id==='string'&&!!h.editor_snapshot_id;
  const adopt=valid&&(kind==='event'||!prior?.doc||prior.kind!=='event'||h.editor_snapshot_id===prior.doc?.meta?.hmb_image_bash?.editor_snapshot_id);
  const retired=adopt&&h.editor_snapshot_id!==prior?.retired?null:prior?.retired||null;
  owners.add(owner);hmbBashDocumentCache.set(name,{doc:adopt?doc:prior?.doc||null,owners,kind:adopt?(prior?.kind==='event'?'event':kind):prior?.kind||kind,epoch:hmbNativeStudioFlowEpoch,
    retired,retired_commit:retired?prior?.retired_commit||null:null});
}
function hmbBashParameterPresent(name) {
  const entry=hmbBashDocumentCache.get(name);
  return entry?.epoch===hmbNativeStudioFlowEpoch&&entry.owners.size>0;
}
function hmbBashReleaseDocument(name,owner) {
  const entry=hmbBashDocumentCache.get(name);
  if(!entry||!entry.owners.has(owner))return;
  entry.owners.delete(owner);if(!entry.owners.size)hmbBashDocumentCache.delete(name);
}
function hmbBashOutgoingMeta(meta,name,commit) {
  const h=meta?.hmb_image_bash;
  if (!h || typeof h!=='object') return meta;
  const entry=hmbBashDocumentCache.get(name);
  if(entry?.epoch===hmbNativeStudioFlowEpoch&&h.editor_snapshot_id){entry.retired=h.editor_snapshot_id;entry.retired_commit=commit||null;}
  const {editor_snapshot_id,...rest}=h;
  return {...meta,hmb_image_bash:rest};
}
function hmbBashClearRejectedDocument(name,request,epoch) {
  if(request?.node_name!==name||request?.parameter_name!=='bash_image')return;
  const entry=hmbBashDocumentCache.get(name),h=entry?.doc?.meta?.hmb_image_bash,next=request.value?.meta?.hmb_image_bash;
  if(entry?.epoch!==epoch||!entry.retired_commit||request.value?.meta?.created_at!==entry.retired_commit
    ||entry.retired!==h?.editor_snapshot_id||!next||!['workspace_id','channel_uuid','workspace_revision','node_instance_uuid'].every(key=>next[key]===h[key]))return;
  entry.retired=null;entry.retired_commit=null;
}
async function hmbBashReadHeader(name,check) {
  const reply=await Id.request('GetParameterValueRequest',{node_name:name,parameter_name:'HMB_IMAGE_BASH_UI'},{timeoutMs:10000});
  if(!check())throw Error('workspace_changed');
  if(!reply||!Object.prototype.hasOwnProperty.call(reply,'value'))throw Error('preparation_unavailable');
  return hmbBashPreparation(reply.value);
}
function hmbBashDocumentMatches(doc,p) {
  if(!p.workspace_id)return !!doc;
  const h=doc?.meta?.hmb_image_bash;
  return !!h&&typeof p.editor_snapshot_id==='string'&&!!p.editor_snapshot_id
    &&h.editor_snapshot_id===p.editor_snapshot_id&&h.workspace_id===p.workspace_id
    &&h.channel_uuid===p.channel_uuid&&h.node_instance_uuid===p.node_instance_uuid
    &&h.workspace_revision===p.workspace_revision
    &&(p.editor_commit==null||doc.meta.created_at===p.editor_commit);
}
async function hmbBashReadCurrent(name,check,fallback) {
  const first=await hmbBashReadHeader(name,check);
  if(!first.ready||first.phase==='preparing'||first.phase==='error')return {preparation:first,doc:null};
  const cached=hmbBashDocumentCache.get(name);
  if(cached?.epoch===hmbNativeStudioFlowEpoch&&cached.retired===first.editor_snapshot_id)return {preparation:first,doc:null,waiting:true};
  const doc=hmbBashDocumentMatches(fallback,first)?fallback:
    cached?.epoch===hmbNativeStudioFlowEpoch&&hmbBashDocumentMatches(cached.doc,first)?cached.doc:null;
  if(!doc)return {preparation:first,doc:null,waiting:true};
  const last=await hmbBashReadHeader(name,check);
  if(!hmbBashSamePreparation(first,last)||!hmbBashDocumentMatches(doc,last))return {preparation:last,doc:null,waiting:true};
  return {preparation:last,doc};
}
'''
    src = src[:start] + reader + src[end:]
    src = one(src,
        '&& a.channel_uuid===b.channel_uuid && a.workspace_revision===b.workspace_revision && a.ready===b.ready && a.phase===b.phase;',
        '&& a.channel_uuid===b.channel_uuid && a.workspace_revision===b.workspace_revision && a.ready===b.ready && a.phase===b.phase\n    && a.editor_snapshot_id===b.editor_snapshot_id && a.editor_commit===b.editor_commit;')
    src = one(src, 'const snapshot=await hmbBashReadCurrent(name,check);',
        'const snapshot=await hmbBashReadCurrent(name,check,fallback);')
    src = one(src, 'const [view,setView]=C.useState(null);',
        "const [view,setView]=C.useState(null),[queryError,setQueryError]=C.useState(''),owner=C.useRef(null);if(!owner.current)owner.current={};")
    src = one(src, "  C.useEffect(()=>{\n    if(!owned)return;let active=true,eventGeneration=0;const epoch=hmbNativeStudioFlowEpoch;",
        "  C.useLayoutEffect(()=>{if(owned)hmbBashRememberDocument(name,props.value,owner.current);},[owned,name,flow,props.value]);\n  C.useLayoutEffect(()=>{\n    if(!owned)return;let active=true,eventGeneration=0;const epoch=hmbNativeStudioFlowEpoch;")
    src = one(src, 'if(!owned)return;let active=true,eventGeneration=0;const epoch=hmbNativeStudioFlowEpoch;',
        "if(!owned)return;setView(null);setQueryError('');hmbBashRememberDocument(name,props.value,owner.current);let active=true,eventGeneration=0;const epoch=hmbNativeStudioFlowEpoch;")
    src = one(src, 'try{setView(hmbBashPreparation(value))}catch{setView(null)}};',
        "try{setView(hmbBashPreparation(value));setQueryError('')}catch{setView(null);setQueryError('편집기 준비 정보를 확인할 수 없습니다. 다시 시도하세요.')}};")
    src = one(src,
        "Id.request('GetParameterValueRequest',{node_name:name,parameter_name:'HMB_IMAGE_BASH_UI'}).then(reply=>{if(queryGeneration===eventGeneration)update(reply?.value)}).catch(()=>{if(active&&epoch===hmbNativeStudioFlowEpoch&&queryGeneration===eventGeneration)setView(null)});",
        "Id.request('GetParameterValueRequest',{node_name:name,parameter_name:'HMB_IMAGE_BASH_UI'},{timeoutMs:10000}).then(reply=>{if(queryGeneration===eventGeneration)update(reply?.value)}).catch(()=>{if(active&&epoch===hmbNativeStudioFlowEpoch&&queryGeneration===eventGeneration){setView(null);setQueryError('연결 응답이 지연됩니다. 잠시 후 다시 시도하세요.')}});")
    src = one(src,
        "const off=subscribeToEvent('ExecutionEvent',event=>{if(event?.payload_type==='ParameterValueUpdateEvent'\n      &&event.payload?.node_name===name&&event.payload?.parameter_name==='HMB_IMAGE_BASH_UI'){eventGeneration++;update(event.payload.value)}});",
        "const off=subscribeToEvent('ExecutionEvent',event=>{if(event?.payload_type!=='ParameterValueUpdateEvent'||event.payload?.node_name!==name)return;\n      if(event.payload.parameter_name==='bash_image')hmbBashRememberDocument(name,event.payload.value,owner.current,'event');\n      else if(event.payload.parameter_name==='HMB_IMAGE_BASH_UI'){eventGeneration++;update(event.payload.value)}});")
    src = one(src, 'return()=>{active=false;off?.()};',
        "const offFailure=subscribeToEvent('SetParameterValueResultFailure',(_result,request)=>hmbBashClearRejectedDocument(name,request,epoch));\n    return()=>{active=false;off?.();offFailure?.();hmbBashReleaseDocument(name,owner.current)};")
    src = one(src, "const busy=!valid||view.phase==='preparing',failed=valid&&view.phase==='error';",
        "const busy=!queryError&&(!valid||view.phase==='preparing'||(!!view.workspace_id&&view.ready&&!view.editor_snapshot_id)),failed=!!queryError||(valid&&view.phase==='error');")
    src = one(src, "failed?(view.error||'이미지 라이브러리에서 다시 시도하세요.'):props.tooltip};",
        "failed?(queryError||view?.error||'이미지 라이브러리에서 다시 시도하세요.'):props.tooltip};")
    src = one(src, 'hmbHydrated=C.useRef(false);', 'hmbHydrated=C.useRef(false),hmbLatestDoc=C.useRef(g);')
    src = one(src, "hmbScope.current=scope;hmbMetaRef.current=g?.meta||{};hmbPending.current=null;",
        "hmbScope.current=scope;hmbLatestDoc.current=g;hmbMetaRef.current=g?.meta||{};hmbPending.current=null;")
    src = one(src, 'if(!check())return;const token=++refreshGeneration;hmbSetBusy(true);',
        'if(!check())return;clearTimeout(scope.documentWait);const token=++refreshGeneration;hmbSetBusy(true);')
    src = one(src, 'const current=await hmbBashReadCurrent(b,()=>check()&&token===refreshGeneration);',
        'const current=await hmbBashReadCurrent(b,()=>check()&&token===refreshGeneration,hmbLatestDoc.current);')
    src = one(src, 'if(!current.preparation.ready||!current.doc){preparing(current.preparation);return;}',
        "if(current.waiting){scope.documentWait=setTimeout(()=>{if(check()&&token===refreshGeneration)warning('최신 편집 장면이 아직 도착하지 않았습니다. 기존 편집은 유지됩니다. 다시 시도하세요.')},10000);return;}\n     if(!current.preparation.ready||!current.doc){preparing(current.preparation);return;}")
    src = one(src, "}else if(event.payload.parameter_name==='bash_image'&&!hmbSaving.current){refresh();}",
        "}else if(event.payload.parameter_name==='bash_image'){hmbLatestDoc.current=event.payload.value;if(!hmbSaving.current)refresh();}")
    src = one(src, 'return()=>{active=false;refreshGeneration++;hmbRevision.current++;hmbPending.current=null;',
        'return()=>{active=false;clearTimeout(scope.documentWait);refreshGeneration++;hmbRevision.current++;hmbPending.current=null;')
    src = one(src, '...(hmbApplySnapshot?.meta||{}),created_at:',
        '...(hmbApplySnapshot?.meta?hmbBashOutgoingMeta(hmbApplySnapshot.meta,hmbApplySnapshot.scope.name,hmbApplySnapshot.commit):{}),created_at:')
    src = one(src, 'meta:hmbMetaRef.current}:null;if(hmbApplySnapshot)',
        'meta:hmbMetaRef.current,commit:new Date().toISOString()}:null;if(hmbApplySnapshot)')
    src = one(src, 'hmbApplySnapshot.commit):{}),created_at:new Date().toISOString()',
        'hmbApplySnapshot.commit):{}),created_at:hmbApplySnapshot?.commit||new Date().toISOString()')
    src = one(src, "Id.request('GetParameterValueRequest',{node_name:b,parameter_name:'HMB_IMAGE_BASH_UI'}).then(reply=>{",
        "Id.request('GetParameterValueRequest',{node_name:b,parameter_name:'HMB_IMAGE_BASH_UI'},{timeoutMs:10000}).then(reply=>{")
    src = one(src,
        'CKt=(e,t,r,i)=>Id.request(`SendNodeMessageRequest`,{node_name:e,optional_element_name:t,message_type:r,message:i}),',
        'CKt=(e,t,r,i,a)=>Id.request(`SendNodeMessageRequest`,{node_name:e,optional_element_name:t,message_type:r,message:i},a),')
    src = one(src, 'icon_position:e.icon_position||`left`}});if(t?.response)',
        'icon_position:e.icon_position||`left`}},hmbBashParameterPresent(i)&&a===`output_file`?{timeoutMs:10000}:void 0);if(t?.response)')
    src = one(src, 'catch(e){console.error(`Button press error:`,e)}finally{s(!1),l(!1)}}}',
        'catch(e){console.error(`Button press error:`,e);if(hmbBashParameterPresent(i)&&a===`output_file`)CJ.error(`출력 파일 설정 응답을 확인하지 못했습니다`,{description:`설정 노드가 이미 열렸는지 확인한 뒤 다시 시도하세요. 출력 파일은 삭제하지 않습니다.`})}finally{s(!1),l(!1)}}}')
    return src


def _port_retention_notice_bridge(source: str) -> str:
    """Classify only the explicit successful port-retention guard as information."""
    return one(source,
        'i===`failure`&&(o===`PermissionDeniedResult`?Cra(t,r):w_r({result:t,request:r}))',
        'i===`failure`&&!hmbNativePortRetainedNotice(t,r)&&(o===`PermissionDeniedResult`?Cra(t,r):w_r({result:t,request:r}))')


def _build_candidate_ui_core(source: str, helper: str) -> str:
    """Return an uninstalled candidate or raise when required shape is absent."""
    if not isinstance(source, str) or not isinstance(helper, str):
        raise TypeError('editor source and HMB helper must be text')
    if 'HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1' in source:
        import hashlib
        reviewed = approval_evidence()
        if (hashlib.sha256(source.encode('utf-8')).hexdigest() == _SHOT_BASKET_BASE
                and hashlib.sha256(helper.encode('utf-8')).hexdigest() == reviewed['helper_sha256']):
            return source  # Exact current bytes only; unknown input still fails closed.
        return _upgrade_reviewed_candidate(source, helper)
    for anchor in ('var k8t=({node_name:', '};function A8t', 'function Dqr(', '}function Oqr(', 'function lqr(', '}function uqr('):
        if source.count(anchor) != 1:
            raise ValueError('unsupported or ambiguous editor structure: ' + anchor)
    dependencies = ('C=d(m(),1),w=g(),T=S()', 'var Cl=d(b())', 'z=s(((e,t)=>{t.exports=zn()}))()', 'function xu(){let e=tu(),t=Ol(),r=yu(),i=Dl(bu)', 'function eHr(){let e=(0,w.c)(3),{getState:t}=Ol(),r=id(),i', 'function oqr(e,t,r,i,a,o){', 'function $Gt(e,t,r,i,a,o){', 'function cqr(e,t,r,i){', 'JJ=(e,t)=>Id.request(', 'Id=class e{static instance=null;wsClient=null;connectionManager=null;', 'CJ=Object.assign(qWt,{success:SJ.success,info:SJ.info,warning:SJ.warning,error:SJ.error', '__r=e=>{let{text:t,verbatim:r}=h_r(e)', 'L8=`flex w-full items-center gap-2 px-3 py-2 text-sm text-left rounded-md hover:bg-accent`', 'R8=`flex size-4 shrink-0 items-center justify-center`', 'z8=`min-w-0 flex-1 text-left`')
    for anchor in dependencies:
        if source.count(anchor) != 1:
            raise ValueError('unsupported or ambiguous editor dependency: ' + anchor)
    if source.count('vY=Nd(e=>({isDirty:!1,setDirty:t=>e({isDirty:t})}))') != 1:
        raise ValueError('unsupported or ambiguous native dirty-state store')
    header, parent, fold = _fragments(source)
    helper = _compiled_helper(helper)
    start = source.index('var k8t=({node_name:')
    end = source.index('};function A8t', start) + 2
    source = source[:start] + helper + '\n' + header + source[end:]
    start = source.index('function Dqr(')
    end = source.index('}function Oqr(', start) + 1
    source = source[:start] + parent + source[end:]
    start = source.index('function lqr(')
    end = source.index('}function uqr(', start) + 1
    source = source[:start] + fold + source[end:]
    start = source.index('function Jci(')
    end = source.index('}function ', start) + 1
    delete = source[start:end]
    delete = one(delete, 'S=e=>{let t=c.current,a=t?e.map', 'S=e=>hmbNativeGuardNodeDeletion(e,i.current,hmbDeletionChanges=>{let e=hmbDeletionChanges,t=c.current,a=t?e.map')
    delete = one(delete, 'if(g(t.id),HJ(r?.data?.node_type))', 'if(!t.hmbGuardedDelete&&g(t.id),HJ(r?.data?.node_type))')
    delete = one(delete, 'Id.send(`DeleteNodeRequest`,{node_name:t.id})}),h()}C.length', 'Id.send(`DeleteNodeRequest`,{node_name:t.id})}),!a.some(e=>e.hmbGuardedDelete)&&h()}C.length')
    delete = one(delete, 'l(E),T.size>0', 'l(E.filter(e=>e.type!==`remove`||!e.hmbGuardedDelete)),T.size>0')
    delete = one(delete, 'measured:{width:300,height:48}}:e)))},t[0]=g', 'measured:{width:300,height:48}}:e)))},()=>i.current),t[0]=g')
    delete = one(delete, 'a.length>0&&(d(e=>e.map(e=>{let r=e.parentId===t.id?o.get(e.id):void 0;', 'a.length>0&&!t.hmbGuardedDelete&&(d(e=>e.map(e=>{let r=e.parentId===t.id?o.get(e.id):void 0;')
    delete = one(delete, 'f8(t.id)||_(r,a,o)', 'f8(t.id)||_(t.hmbGuardedDelete?{...r,hmbGuardedDelete:!0,hmbDeletionOperation:hmbNativeDeletionPending.get(t.id)}:r,a,o)')
    source = source[:start] + delete + source[end:]
    start = source.index('function Bci(')
    end = source.index('}function ', start) + 1
    group = source[start:end]
    group = one(group, 'function Bci({constructConnections:e,setNodes:t,setEdges:r,edgesRef:i,settings:a,suppressedEdgeSetRef:o})', 'function Bci({constructConnections:e,setNodes:t,setEdges:r,edgesRef:i,settings:a,suppressedEdgeSetRef:o,updateNodeInternals:hmbRefresh})')
    group = one(group, 'try{if(await Id.request(`DeleteNodeRequest`,{node_name:s}),CJ.success', 'try{await Id.request(`DeleteNodeRequest`,{node_name:s});if(i.hmbGuardedDelete){let hmbOp=i.hmbDeletionOperation;if(!hmbOp||hmbOp.epoch!==hmbNativeStudioFlowEpoch)return;let hmbApplied=await new Promise(resolve=>t(nodes=>{if(hmbOp.epoch!==hmbNativeStudioFlowEpoch){resolve(!1);return nodes}let group=nodes.find(n=>n.id===s),pos=group?.position||hmbOp.finalGroupPosition;if(!pos){resolve(!1);return nodes}let moved=new Map,next=nodes.map(n=>{if(n.parentId!==s)return n;let position={x:n.position.x+(pos.x||0),y:n.position.y+(pos.y||0)};moved.set(n.id,position);return{...n,parentId:void 0,position,hidden:!1,data:{...n.data,__inGroup:void 0}}});o.clear();moved.forEach((position,name)=>o.set(name,position));c.splice(0,c.length,...moved.keys());resolve(!0);return next}));if(!hmbApplied)return;requestAnimationFrame(()=>c.forEach(hmbRefresh))}if(CJ.success')
    group = one(group, 'CJ.error(`Failed to remove group`,{description:Y3(o)});let l=', 'CJ.error(`Failed to remove group`,{description:Y3(o)});if(i.hmbGuardedDelete){i.hmbDeletionOperation?.sequence?.groupApplied(s,!1);return}let l=')
    group = one(group, 'YJ(o),c.length>0', '(i.hmbGuardedDelete?await YJ(o):YJ(o)),c.length>0')
    group = one(group, 'r(e=>zci(e.filter(e=>e.source!==s&&e.target!==s),i))}}catch(o)', 'r(e=>zci(e.filter(e=>e.source!==s&&e.target!==s),i))}i.hmbGuardedDelete&&i.hmbDeletionOperation?.sequence?.groupApplied(s,!0)}catch(o)')
    group = one(group, '}},[e,r,t]),handleDotNodeDeletion:', '}},[e,r,t,hmbRefresh]),handleDotNodeDeletion:')
    source = source[:start] + group + source[end:]
    source = one(source, 'handleGroupNodeDeletion:ze,handleDotNodeDeletion:Be}=Bci({constructConnections:d,setNodes:x,setEdges:O,edgesRef:je,settings:N,suppressedEdgeSetRef:Me})', 'handleGroupNodeDeletion:ze,handleDotNodeDeletion:Be}=Bci({constructConnections:d,setNodes:x,setEdges:O,edgesRef:je,settings:N,suppressedEdgeSetRef:Me,updateNodeInternals:A})')
    source = one(source, 'function Xui(){let e=RX()', 'function Xui(){hmbUseNativeDeletionGuardHost();let hmbConnectionManager=hmbUseNativeConnectionManager();let e=RX()')
    source = one(source, 'children:[(0,z.jsx)(Dui,{isLoading:Ut||!e,workflowReady:e,', 'children:[hmbConnectionManager,(0,z.jsx)(Dui,{isLoading:Ut||!e,workflowReady:e,')
    source = one(source, 't[73]=M,t[74]=_e):_e=t[74],_e}var O0r=', 't[73]=M,t[74]=_e):_e=t[74],hmbNativeConnectionMenu(e,_e)}var O0r=')
    source = one(source, '(0,z.jsx)(D0r,{addParameterDisabled:xe,configureParameterDisabled:ke,', '(0,z.jsx)(D0r,{hmbConnectionNode:d||E[0]?.node,hmbClose:()=>c(!1),addParameterDisabled:xe,configureParameterDisabled:ke,')
    source = one(source, 'updateNodeInternals:p,clearParameterValueUpdates:m,clearSelectedNodes:h,', 'updateNodeInternals:p,clearParameterValueUpdates:m,clearNodeState:hmbClearNodeState,clearSelectedNodes:h,')
    source = one(source, 'updateNodeInternals:A,clearParameterValueUpdates:tt,clearSelectedNodes:We,', 'updateNodeInternals:A,clearParameterValueUpdates:tt,clearNodeState:nt,clearSelectedNodes:We,')
    source = one(source, 'F=r(`DeleteNodeResultSuccess`,(e,t)=>{let r=e?.node_name||t?.node_name;r&&(i(e=>e.filter(e=>e.id!==r&&e.name!==r))', 'F=r(`DeleteNodeResultSuccess`,(e,t)=>{let r=e?.node_name||t?.node_name,hmbOp=r&&hmbNativeDeletionPending.get(r),hmbNode=r&&o.current.find(n=>n.id===r);hmbOp&&hmbNode&&(hmbOp.finalGroupPosition={...hmbNode.position});hmbOp?.sequence?.notify(r,!0);r&&(hmbNativeDeletionPending.has(r)&&hmbClearNodeState(r),hmbNativeDeletionFinished(r),i(e=>e.filter(e=>e.id!==r&&e.name!==r))')
    source = one(source, 'I=r(`DeleteNodeResultFailure`,e=>{console.error(`❌ Node deletion failed:`,e)})', 'I=r(`DeleteNodeResultFailure`,(e,t)=>{let hmbName=t?.node_name||e?.node_name;hmbNativeDeletionPending.get(hmbName)?.sequence?.notify(hmbName,!1);hmbNativeDeletionFinished(hmbName);hmbNativeConnectionDeletionNotice(t,__r(e));console.error(`❌ Node deletion failed:`,e)})')
    source = one(source, 'ie=r(`ClearAllObjectStateResultSuccess`,()=>{i([]),a([]),T(),h(),', 'ie=r(`ClearAllObjectStateResultSuccess`,()=>{hmbNativeStudioResetCollapseIntents();i([]),a([]),T(),h(),')
    source = one(source, '[t,r,i,a,o,s.edgeType,c,l,u,d,f,p,m,h,g,_,v,y,b,x,S,w,T,E,D,O,k,A,j,M,N,P])}', '[t,r,i,a,o,s.edgeType,c,l,u,d,f,p,m,hmbClearNodeState,h,g,_,v,y,b,x,S,w,T,E,D,O,k,A,j,M,N,P])}')
    source = one(source, 'QY=()=>Id.request(`ClearAllObjectStateRequest`,{i_know_what_im_doing:!0})', 'QY=()=>Id.request(`HMBPrepareWorkflowTransitionRequest`,{})')
    source = one(source, 'C=h.current.getParentId(_);h.current.onBeforeAnimate(t,d)', 'C=h.current.getParentId(_),hmbNativeViewMetadata=hmbNativeStudioCollapseMetadata(_,t,d);h.current.onBeforeAnimate(t,d)')
    source = one(source, 'metadata:d?{rolledUp:t}:{collapsed:t,rolledUp:!1}', 'metadata:{...(d?{rolledUp:t}:{collapsed:t,rolledUp:!1}),...hmbNativeViewMetadata}')
    source = one(source, 'return d}function yKr(){let e=(0,w.c)(9)', 'return hmbNativeStudioConstructedNode(d)}function yKr(){let e=(0,w.c)(9)')
    source = one(source, 'u(void 0,b).then(({nodes:e,connections:t})=>{m(null),a([]),o([]),f(),s(),a(e),o(t)', 'u(void 0,b).then(({nodes:e,connections:t})=>{hmbNativeStudioResetCollapseIntents();m(null),a([]),o([]),f(),s(),a(e),o(t)')
    source = one(source, 'a=t.data?.collapsed===!0;if(i){let t=a?300:e.dimensions.width,r=a?48:e.dimensions.height;', 'a=t.data?.collapsed===!0;let hmbCurrent=hmbIsNativeStudioType(t.data?.node_type,t.data?.metadata);if(i){let t=a?(hmbCurrent?hmbNativeStudioCollapsedWidth:300):e.dimensions.width,r=a?(hmbCurrent?hmbNativeStudioCollapsedHeight:48):e.dimensions.height;')
    source = one(source, 'if(!r&&!BJ(t)&&!t.data?.metadata?.size){let r=', 'if(!r&&!BJ(t)&&!t.data?.metadata?.size&&!hmbNativeStudioSuppressInitialSize(t,e.dimensions)){let r=')
    source = one(source, 'r&&!BJ(r)&&!r.data.collapsed){let i=', 'r&&!BJ(r)&&!r.data.collapsed&&!hmbNativeStudioFolded(r)){let i=')
    source = one(source, 'd(e=>e.map(e=>T.has(e.id)&&e.data?.collapsed===!0?{...e,width:300,height:48,measured:{width:300,height:48}}:e))', 'd(e=>hmbNativeStudioCollapsedMeasuredNodes(e,T))')
    source = one(source, 'function tli(e,t){Id.send(`SetNodeMetadataRequest`,{node_name:e,metadata:t})}', 'function tli(e,t){Id.send(`SetNodeMetadataRequest`,{node_name:e,metadata:hmbNativeStudioOutgoingMetadata(e,t)})}')
    source = one(source, 'className:`widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel`,style:g', 'className:hmbIsNativeStudioWidget(t)?`widget-container flex flex-col w-full h-full min-h-0 nowheel`:`widget-container flex flex-col w-full h-full min-h-0 nodrag nowheel`,style:g')
    source = one(source, '[a.value,l.status,t]),l.status===`loading`)', '[a.value,l.status,t,hmbIsNativeStudioWidget(t)?i:void 0]),l.status===`loading`)')
    source = one(source, 'metadata:{position:a,tempId:S},set_as_new_context:!1};await Id.send(`CreateNodeRequest`,h)', 'metadata:hmbColorLUTCreateMetadata(m.node_type,{position:a,tempId:S}),set_as_new_context:!1};await Id.send(`CreateNodeRequest`,h)')
    source = one(source, 'node_type:r.node_type,specific_library_name:r.library_name,metadata:{position:i,tempId:a},set_as_new_context:!1})', 'node_type:r.node_type,specific_library_name:r.library_name,metadata:hmbColorLUTCreateMetadata(r.node_type,{position:i,tempId:a}),set_as_new_context:!1})')
    source = one(source, 'Id.send(`DeleteNodeRequest`,{node_name:t.id})}),!a.some(e=>e.hmbGuardedDelete)&&h()', '(t.hmbGuardedDelete?hmbNativeSubmitCheckedDelete(t.id).catch(e=>hmbNativeCheckedDeleteFailure(t.id,e)):Id.send(`DeleteNodeRequest`,{node_name:t.id}))}),!a.some(e=>e.hmbGuardedDelete)&&h()')
    source = one(source, 'try{await Id.request(`DeleteNodeRequest`,{node_name:s});if(i.hmbGuardedDelete)', 'try{await(i.hmbGuardedDelete?hmbNativeSubmitCheckedDelete(s):Id.request(`DeleteNodeRequest`,{node_name:s}));if(i.hmbGuardedDelete)')
    return _capsule_motion_bridge(_bash_live_input_bridge(_port_retention_notice_bridge(source)))

def _hmb_connection_action_bridge(source: str) -> str:
    """Route header, selection, context menu and outliner resets by node ownership."""
    source = one(source,
        'let e=hmbIsNativeStudioType(t,hmbMetadata)&&hmbNativeHeader.active?[`lock`,`reset`,`run`]:w.nodeHeaderItems||[`lock`,`run`,`startFlow`];return x8t.filter',
        'let e=hmbNativeHeaderItems(t,hmbLibrary,w.nodeHeaderItems);return x8t.filter')
    source = one(source, '[w.nodeHeaderItems,oe,t,hmbNativeHeader.active,hmbMetadata]),we=',
        '[w.nodeHeaderItems,oe,t,hmbLibrary]),we=')
    source = one(source, '(0,z.jsx)(AJ,{children:`Reset Node`})]},`reset`)',
        '(0,z.jsx)(AJ,{children:hmbNativeConnectionManaged(hmbLibrary)?`연결 다시 적용`:`Reset Node`})]},`reset`)')
    source = one(source, 'xKt=e=>Id.request(`ResetNodeToDefaultsRequest`,{node_name:e})',
        'xKt=(e,t)=>hmbNativeConnectionManaged(t)?hmbNativeRefreshConnections(e):Id.request(`ResetNodeToDefaultsRequest`,{node_name:e})')
    source = one(source, 'xKt(e.id).catch(QAi)', 'xKt(e.id,e.data?.metadata?.library).catch(QAi)')
    source = one(source, 'await Id.request(`ResetNodeToDefaultsRequest`,{node_name:e})',
        'await xKt(e,i().find(node=>node.id===e)?.data?.metadata?.library)')
    old = 'await Id.request(`ResetNodeToDefaultsRequest`,{node_name:t.id})'
    if source.count(old) != 2:
        raise ValueError("ambiguous selection/context reset routes")
    source = source.replace(old, 'await xKt(t.id,t.data?.metadata?.library)')
    return source


def _build_base_candidate(source: str, helper: str) -> str:
    """Preserve the reviewed pre-basket canvas and native controls."""
    import hashlib

    candidate = _build_candidate_ui_core(source, helper)
    if candidate is source or hashlib.sha256(source.encode("utf-8")).hexdigest() == _SOUND_READ_PREVIOUS_CANDIDATE:
        # This prior bundle already has the connection and session transforms.
        return candidate
    return _hmb_session_bound_editor_source(_hmb_connection_action_bridge(candidate))


def _shot_basket_canvas(source: str, ui: str) -> str:
    component = r'''
function hmbUseRodongMartHeaderArtwork(library, nodeName, slots, collapsed) {
  const current = C.useRef(null);
  const synchronize = C.useRef(null);
  const epoch = hmbNativeStudioFlowEpoch;
  synchronize.current = () => {
    const artwork = window.__hmbRodongMartHeaderArt;
    if (library !== "HMB_GP_Production" || !artwork) return;
    const node = hmbNativeStudioNode(nodeName);
    let header;
    if (!collapsed && slots.active && slots.identity && slots.actions) {
      for (let row = slots.identity.parentElement; row && row !== slots.container; row = row.parentElement) {
        if (row.contains(slots.actions)) { header = row; break; }
      }
    }
    header ||= node?.querySelector("[data-hmb-native-icon-header],[data-hmb-mart-native-header]");
    if (header && !node?.contains(header)) header = null;
    if (current.current?.epoch !== epoch || current.current?.name !== nodeName) {
      current.current?.cleanup?.();
      current.current = { epoch, name: nodeName, index: artwork.next() };
    }
    const entry = current.current;
    if (entry.header === header) return;
    entry.cleanup?.();
    entry.header = header;
    entry.cleanup = artwork.mount(header, entry.index, true);
  };
  C.useLayoutEffect(() => { synchronize.current(); });
  C.useLayoutEffect(() => {
    if (library !== "HMB_GP_Production") return;
    const ready = event => {
      const container = event.detail?.container;
      if (container?.closest(".react-flow__node")?.getAttribute("data-id") === nodeName) synchronize.current();
    };
    document.addEventListener("hmb-color-lut-header-ready", ready);
    return () => {
      document.removeEventListener("hmb-color-lut-header-ready", ready);
      const entry = current.current;
      entry?.cleanup?.();
      if (entry) { entry.header = null; entry.cleanup = null; }
    };
  }, [library, nodeName]);
}
let hmbRodongMartQueuedWorkflow = "";
let hmbRodongMartProjectHint = [];
function hmbUseRodongMartReadAhead(connection) {
  C.useEffect(() => {
    if (connection !== "connected") return;
    let active = true, retry;
    hmbRodongMartProjectHint = [];
    const read = async (attempt = 0) => {
      try {
        const result = await Id.request("HMBShotBasketRequest", { action: "status",
          payload: { flow_name: "", workflow_name: "", prewarm: attempt === 0 } }, { timeoutMs: 5000 });
        if (!active || result?.data?.ok !== true) return;
        const { projects, status } = result.data;
        if (Array.isArray(projects) && projects.length) hmbRodongMartProjectHint = projects;
        else if (status === "discovering" && attempt < 2) retry = setTimeout(() => void read(attempt + 1), 280);
      } catch { /* The actual view will make its own scoped request. */ }
    };
    void read();
    return () => { active = false; clearTimeout(retry); hmbRodongMartProjectHint = []; };
  }, [connection]);
  C.useEffect(() => {
    if (connection !== "connected" || typeof pVr === "undefined" || typeof cVr === "undefined") return;
    const attempted = new Set();
    let active = true, running = false, timer;
    const schedule = () => {
      if (!active || running || timer !== undefined) return;
      const widgets = pVr.getState().widgets;
      const next = [...widgets].find(([, widget]) => widget.libraryName === "HMB_GP_Production" &&
        widget.bundleUrl && !attempted.has(widget.bundleUrl) && !cVr.has(widget.bundleUrl));
      if (!next) return;
      timer = setTimeout(async () => {
        timer = undefined;
        const [key, widget] = next;
        if (!active || pVr.getState().widgets.get(key) !== widget) { schedule(); return; }
        attempted.add(widget.bundleUrl);
        running = true;
        try {
          const module = await import(widget.bundleUrl);
          const mount = module.default || module[widget.name];
          if (active && typeof mount === "function" && pVr.getState().widgets.get(key) === widget &&
              !cVr.has(widget.bundleUrl)) cVr.set(widget.bundleUrl, mount);
        } catch { /* Native widget loading retains its normal fallback and diagnostics. */ }
        finally { running = false; schedule(); }
      }, 80);
    };
    const unsubscribe = pVr.subscribe(schedule);
    schedule();
    return () => { active = false; clearTimeout(timer); unsubscribe(); };
  }, [connection]);
}
function hmbQueueRodongMartBasket(workflow) {
  hmbRodongMartQueuedWorkflow = workflow;
  queueMicrotask(() => window.dispatchEvent(new Event("hmb-rodong-mart-workflow-ready")));
}
function hmbOpenQueuedRodongMartBasket(controller, context) {
  if (hmbRodongMartQueuedWorkflow && context.ready && context.empty && context.flowName &&
      context.workflowName === hmbRodongMartQueuedWorkflow && controller?.open(hmbRodongMartProjectHint, true)) {
    hmbRodongMartQueuedWorkflow = "";
    window.dispatchEvent(new Event("hmb-rodong-mart-basket-opened"));
  }
}
function hmbUseRodongMartStartup(openWorkflows) {
  const phase = C.useRef("fresh");
  const handoffTimer = C.useRef(undefined);
  const [visible, setVisible] = C.useState(false);
  const [entering, setEntering] = C.useState(false);
  const show = C.useCallback(() => {
    if (phase.current === "visible") return;
    if (phase.current === "done" || typeof window.__hmbMountRodongMartStartup !== "function") {
      openWorkflows(); return;
    }
    phase.current = "visible";
    setVisible(true);
  }, [openWorkflows]);
  const complete = C.useCallback(() => {
    clearTimeout(handoffTimer.current);
    phase.current = "done";
    setEntering(false); setVisible(false);
  }, []);
  const dismiss = C.useCallback(() => { complete(); openWorkflows(); }, [complete, openWorkflows]);
  const enter = C.useCallback(async create => {
    setEntering(true);
    const workflow = await create(hmbQueueRodongMartBasket);
    if (!workflow) { setEntering(false); return false; }
    if (phase.current === "visible") handoffTimer.current = setTimeout(() => {
      if (hmbRodongMartQueuedWorkflow === workflow) hmbRodongMartQueuedWorkflow = "";
      complete();
    }, 30000);
    return true;
  }, [complete]);
  C.useLayoutEffect(() => {
    window.addEventListener("hmb-rodong-mart-basket-opened", complete);
    return () => { window.removeEventListener("hmb-rodong-mart-basket-opened", complete); clearTimeout(handoffTimer.current); };
  }, [complete]);
  return { visible, entering, show, enter, dismiss };
}
function hmbRodongMartStartup({onDismiss, onEnter}) {
  const host = C.useRef(null), latest = C.useRef(null);
  latest.current = { onDismiss, onEnter };
  C.useLayoutEffect(() => {
    if (!host.current) return;
    return window.__hmbMountRodongMartStartup?.({ host: host.current,
      onDismiss: () => latest.current.onDismiss(), onEnter: () => latest.current.onEnter() });
  }, []);
  return (0,z.jsx)("div", {ref:host});
}
function hmbShotBasketCanvas({ready, empty, hasBasket, flowName, workflowName, onCreated}) {
  const host = C.useRef(null), controller = C.useRef(null), latest = C.useRef(null);
  latest.current = { ready, empty, hasBasket, flowName, workflowName, epoch: hmbNativeStudioFlowEpoch, onCreated };
  C.useLayoutEffect(() => {
    if (!host.current || typeof window.__hmbMountShotBasket !== "function") return;
    controller.current = window.__hmbMountShotBasket({host:host.current, context:latest.current,
      request: async (action, payload = {}) => {
        const origin = latest.current;
        if (!origin.ready || origin.epoch !== hmbNativeStudioFlowEpoch) throw Error("작업공간 연결을 확인해 주세요.");
        const result = await Id.request("HMBShotBasketRequest", {
          action, payload: {...payload, flow_name:payload.flow_name || origin.flowName || "",
            workflow_name:origin.workflowName || ""}
        }, {timeoutMs:action === "create" || action === "prepare" ? 90000 : 30000});
        const value = result?.data;
        if (!value || typeof value !== "object") throw Error("샷 바구니 응답을 확인할 수 없습니다.");
        if (origin.epoch !== hmbNativeStudioFlowEpoch ||
            (origin.workflowName && origin.workflowName !== latest.current.workflowName)) {
          throw Error("작업공간이 변경되었습니다. 다시 열어 주세요.");
        }
        if (value.ok !== false && (action === "create" || action === "prepare") && value.flow_name) {
          if (value.changed === true) hmbNativeConnectionDirty();
          if (value.bound !== true) await latest.current.onCreated(value.flow_name, origin.epoch);
        }
        if (action === "apply" && (value.changed === true || value.accepted_pending === true)) hmbNativeConnectionDirty();
        return value;
      }});
    const openQueued = () => hmbOpenQueuedRodongMartBasket(controller.current, latest.current);
    window.addEventListener("hmb-rodong-mart-workflow-ready", openQueued);
    return () => {
      window.removeEventListener("hmb-rodong-mart-workflow-ready", openQueued);
      controller.current?.destroy(); controller.current = null;
    };
  }, []);
  C.useLayoutEffect(() => {
    controller.current?.setContext(latest.current);
    hmbOpenQueuedRodongMartBasket(controller.current, latest.current);
  });
  return (0,z.jsx)("div", {ref:host, style:{position:"absolute",inset:0,zIndex:20,pointerEvents:"none"}});
}
'''
    source = one(source, 'hmbHostRestoreView,v,hmbMetadata);let{settings:w}=h$()',
                 'hmbHostRestoreView,v,hmbMetadata);hmbUseRodongMartHeaderArtwork(hmbLibrary,e,hmbNativeHeader,v);let{settings:w}=h$()')
    source = one(source, 'style:hmbNativeHeader.active?{display:`none`}:VJ(t)?Ee:ee,',
                 'style:hmbNativeHeader.active?{display:`none`}:VJ(t)?Ee:ee,'
                 '"data-hmb-mart-native-header":hmbLibrary===`HMB_GP_Production`?``:void 0,')
    source = one(source, '(0,z.jsx)(f$,{icon:R}),(0,z.jsxs)(`span`,{className:`flex overflow-hidden flex-row gap-2 mr-4 h-full text-sm`,',
                 'hmbLibrary===`HMB_GP_Production`?(0,z.jsx)(`span`,{"data-hmb-mart-node-icon":true,children:(0,z.jsx)(f$,{icon:R})}):(0,z.jsx)(f$,{icon:R}),(0,z.jsxs)(`span`,{className:`flex overflow-hidden flex-row gap-2 mr-4 h-full text-sm`,')
    source = one(source, 'el("header", { style: { display: "flex", alignItems: "center", gap: 12, padding: 18, borderBottom: "1px solid #313c50" } },',
                 'el("header", { ref: header => { if (header) window.__hmbStylePopupHeader?.(header, header.parentElement); }, style: { display: "flex", alignItems: "center", gap: 12, padding: 18, borderBottom: "1px solid #313c50" } },')
    source = one(source, 'P9i();let l=e.hash||c||``,{isOpen:u,close:d,open:f}=N8(),{isOpen:p',
                 'P9i();hmbUseRodongMartReadAhead(a);let l=e.hash||c||``,{isOpen:u,close:d,open:f}=N8(),hmbStartup=hmbUseRodongMartStartup(f),{isOpen:p')
    source = one(source, 'else x(!1),f()}catch(e){console.error(`Failed to check workflow context:`,e),x(!1),f()}})()},[t,a,l,r,f]);',
                 'else x(!1),!LX.getState().workflowName&&hmbStartup.show()}catch(e){console.error(`Failed to check workflow context:`,e),x(!1),!LX.getState().workflowName&&f()}})()},[t,a,l,r,f,hmbStartup.show]);')
    source = one(source, 'Se=(0,C.useCallback)(async()=>{try{let e=await bY(),t=K3n(Object.keys(e.workflows));',
                 'Se=(0,C.useCallback)(async hmbBeforeOpen=>{try{let e=await bY(),t=K3n(Object.keys(e.workflows));')
    source = one(source, 'r(c,{isSaved:!1})}catch(e){console.error(`Failed to create workflow:`,e),',
                 'typeof hmbBeforeOpen===`function`&&hmbBeforeOpen(c),r(c,{isSaved:!1});return c}catch(e){console.error(`Failed to create workflow:`,e),')
    source = one(source, '});return(0,z.jsx)(W3n,{initialWorkflowName:t||``,children:(0,z.jsx)($X,{children:(0,z.jsxs)(xyi,',
                 '});return(0,z.jsxs)(z.Fragment,{children:[(0,z.jsx)(W3n,{initialWorkflowName:t||``,children:(0,z.jsx)($X,{children:(0,z.jsxs)(xyi,')
    source = one(source, 'g&&s&&(0,z.jsx)(M9i,{isOpen:g,onClose:_})]})},t)})}var vna=',
                 'g&&s&&(0,z.jsx)(M9i,{isOpen:g,onClose:_})]})},t)}),hmbStartup.visible&&(hmbStartup.entering||(!t&&!u&&a===`connected`))?(0,z.jsx)(hmbRodongMartStartup,{onDismiss:hmbStartup.dismiss,onEnter:()=>hmbStartup.enter(Se)}):null]})}var vna=')
    source = one(source, 'function Xui(){hmbUseNativeDeletionGuardHost();',
                 ui + '\n' + component + '\nfunction Xui(){hmbUseNativeDeletionGuardHost();')
    return one(source, 'children:[hmbConnectionManager,(0,z.jsx)(Dui,{isLoading:Ut||!e,workflowReady:e,',
               'children:[hmbConnectionManager,(0,z.jsx)(hmbShotBasketCanvas,{ready:e&&!Ut,empty:!b.length,'
               'hasBasket:b.some(node=>Boolean(node.data?.metadata?.hmb_shot_basket_v1)),'
               'flowName:y,workflowName:LX.getState().workflowName,onCreated:async(flow,epoch)=>{'
               'const graph=await p(flow);if(epoch!==hmbNativeStudioFlowEpoch)return;'
               'x(current=>Array.from(new Map([...current,...graph.nodes].map(node=>[node.id,node])).values()));'
               'O(current=>Array.from(new Map([...current,...graph.connections].map(edge=>[edge.id,edge])).values()));'
               'await v();}}),(0,z.jsx)(Dui,{isLoading:Ut||!e,workflowReady:e,')


def build_candidate(source: str, helper: str) -> str:
    """Add the launcher only to the exact reviewed modern canvas."""
    import base64
    import hashlib
    from pathlib import Path

    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    current_art_revisions = (_SHOT_BASKET_FLICKER_PREVIOUS_CANDIDATE, _SHOT_BASKET_HEADER_FADE_PREVIOUS_CANDIDATE)
    previous_headers = (_SHOT_BASKET_HEADER_PREVIOUS_CANDIDATE, _SHOT_BASKET_SPRITE_PREVIOUS_CANDIDATE,
                        _SHOT_BASKET_COMPACT_PREVIOUS_CANDIDATE, _SHOT_BASKET_STARTUP_PREVIOUS_CANDIDATE,
                        *current_art_revisions)
    previous = (_SHOT_BASKET_PREVIOUS_CANDIDATE, *previous_headers)
    if digest in (_SHOT_BASKET_CANDIDATE, *previous) and hashlib.sha256(helper.encode("utf-8")).hexdigest() != approval_evidence()["helper_sha256"]:
        raise ValueError("HMB Shot Basket requires the reviewed native helper.")
    if digest == _SHOT_BASKET_CANDIDATE:
        return source
    if digest in current_art_revisions:
        base = source
    elif digest in previous:
        # The previous exact install already contains the reviewed base. Remove
        # only its launcher script and JSX before checking that base's identity.
        script = source.index('(() => {\n  const media = [\n    { type: "image", label: "이미지" },')
        editor = source.index('function Xui(){hmbUseNativeDeletionGuardHost();', script)
        base = source[:script] + source[editor:]
        children = 'children:[hmbConnectionManager,'
        launcher = base.index(children + '(0,z.jsx)(hmbShotBasketCanvas,') + len(children)
        empty = base.index('(0,z.jsx)(Dui,{isLoading:Ut||!e,workflowReady:e,', launcher)
        base = base[:launcher] + base[empty:]
        if digest in previous_headers:
            base = one(base, 'hmbUseRodongMartHeaderArtwork(hmbLibrary,e,hmbNativeHeader,v);', '')
            base = one(base, '"data-hmb-mart-native-header":hmbLibrary===`HMB_GP_Production`?``:void 0,', '')
        if digest == _SHOT_BASKET_STARTUP_PREVIOUS_CANDIDATE:
            reversals = (
                ('hmbLibrary===`HMB_GP_Production`?(0,z.jsx)(`span`,{"data-hmb-mart-node-icon":true,children:(0,z.jsx)(f$,{icon:R})}):(0,z.jsx)(f$,{icon:R})', '(0,z.jsx)(f$,{icon:R})'),
                ('ref: header => { if (header) window.__hmbStylePopupHeader?.(header, header.parentElement); }, ', ''),
                ('hmbStartup=hmbUseRodongMartStartup(f),', ''),
                ('else x(!1),!LX.getState().workflowName&&hmbStartup.show()}catch(e){console.error(`Failed to check workflow context:`,e),x(!1),!LX.getState().workflowName&&f()}})()},[t,a,l,r,f,hmbStartup.show]);',
                 'else x(!1),f()}catch(e){console.error(`Failed to check workflow context:`,e),x(!1),f()}})()},[t,a,l,r,f]);'),
                ('Se=(0,C.useCallback)(async hmbBeforeOpen=>{try{let e=await bY(),t=K3n(Object.keys(e.workflows));',
                 'Se=(0,C.useCallback)(async()=>{try{let e=await bY(),t=K3n(Object.keys(e.workflows));'),
                ('typeof hmbBeforeOpen===`function`&&hmbBeforeOpen(c),r(c,{isSaved:!1});return c}catch(e){console.error(`Failed to create workflow:`,e),',
                 'r(c,{isSaved:!1})}catch(e){console.error(`Failed to create workflow:`,e),'),
                ('hmbStartup.visible&&!t&&!u&&a===`connected`?(0,z.jsx)(hmbRodongMartStartup,{onDismiss:hmbStartup.dismiss,onEnter:async()=>{const key=await Se(hmbQueueRodongMartBasket);if(key)hmbStartup.complete();return Boolean(key)}}):null,', ''),
            )
            for old, new in reversals:
                base = one(base, old, new)
    else:
        base = _build_base_candidate(source, helper)
    if digest not in current_art_revisions and hashlib.sha256(base.encode("utf-8")).hexdigest() != _SHOT_BASKET_BASE:
        raise ValueError("HMB Shot Basket requires the reviewed modern canvas.")
    ui_path = Path(__file__).resolve().parents[1] / "resources/editor/hmb-shot-basket.js"
    ui = ui_path.read_bytes()
    if hashlib.sha256(ui).hexdigest() != _SHOT_BASKET_UI_SHA256:
        raise ValueError("HMB Shot Basket UI differs from the reviewed local build.")
    script = ui.decode("utf-8")
    for filename, artwork_digest, placeholder in (
        ("hmb-rodong-mart-launcher.webp", _SHOT_BASKET_ARTWORK_SHA256, "__HMB_RODONG_MART_ARTWORK__"),
        ("hmb-rodong-mart-launcher-extra.webp", _SHOT_BASKET_EXTRA_ARTWORK_SHA256, "__HMB_RODONG_MART_EXTRA_ARTWORK__"),
        ("hmb-rodong-mart-header.webp", _SHOT_BASKET_HEADER_ARTWORK_SHA256, "__HMB_RODONG_MART_HEADER_ARTWORK__"),
    ):
        artwork = ui_path.with_name(filename).read_bytes()
        if hashlib.sha256(artwork).hexdigest() != artwork_digest:
            raise ValueError("HMB Rodong Mart artwork differs from the approved launcher.")
        artwork_url = 'data:image/webp;base64,' + base64.b64encode(artwork).decode('ascii')
        script = one(script, placeholder, artwork_url)
    if digest in current_art_revisions:
        # This exact revision has the current startup/read-ahead integration.
        # Replace the art script and mount anchor without rewinding that integration.
        start = source.index('(() => {\n  const media = [\n    { type: "image", label: "이미지" },')
        end = source.index('\nfunction hmbUseRodongMartHeaderArtwork(', start)
        source = source[:start] + script + '\n' + source[end:]
        candidate = one(source, 'hmbStartup.visible&&(!t||hmbStartup.entering)&&!u&&a===`connected`?',
                        'hmbStartup.visible&&(hmbStartup.entering||(!t&&!u&&a===`connected`))?')
        if digest == _SHOT_BASKET_FLICKER_PREVIOUS_CANDIDATE:
            candidate = one(candidate, '    const leading = header?.querySelector("[data-hmb-mart-node-icon],[data-hmb-capsule-disc]");\n    const target = leading || header;\n', '')
            candidate = one(candidate, '    if (entry.header === target) return;\n    entry.cleanup?.();\n    entry.header = target;\n    entry.cleanup = artwork.mount(target, entry.index, Boolean(leading));',
                            '    if (entry.header === header) return;\n    entry.cleanup?.();\n    entry.header = header;\n    entry.cleanup = artwork.mount(header, entry.index, true);')
    else:
        candidate = _shot_basket_canvas(base, script)
    if digest != _SHOT_BASKET_HEADER_FADE_PREVIOUS_CANDIDATE:
        passive_types = 'const hmbNativePassiveHeaderTypes = new Set([\n'
        candidate = one(candidate, passive_types, passive_types + '  "HMBFinishLookLibrary", "HMBColorLUTLibrary",\n')
    # The Image Bash editor is shared with stock nodes. Key the header cache
    # on HMB ownership so a reused stock modal also removes the decoration.
    header = 'let c;t[117]===a?c=t[118]:(c=(0,z.jsxs)(`div`,{className:`flex flex-row justify-between items-start px-8 pt-6 pb-4 w-full border-b border-gray-200 dark:border-gray-700`,children:[o,(0,z.jsx)(wG,{className:`mt-1 ml-4`,onClick:a,size:`icon`,variant:`ghost`,children:s})]}),t[117]=a,t[118]=c);let l;'
    styled_header = header.replace('let c;t[117]===a?', 'const hmbPopupOwned=Boolean(hmbUiScope);let c;t[117]?.[0]===a&&t[117]?.[1]===hmbPopupOwned?')
    styled_header = styled_header.replace('{className:', '{ref:header=>{if(header)window.__hmbStylePopupHeader?.(header,header.parentElement,{artworkOnly:true,enabled:hmbPopupOwned})},className:', 1)
    return one(candidate, header, styled_header.replace('t[117]=a,', 't[117]=[a,hmbPopupOwned],'))

def approval_evidence() -> dict:
    """Exact reviewed capability evidence; Desktop and team release are separate."""
    return {'status': 'approved',
     'structural_anchors': 'matched',
     'live_renderer_verified': True,
     'deletion_verified': True,
     'desktop_verified': False,
     'team_release_approved': False,
     'renderer_scope': 'The reviewed native controls plus the exact HMB Shot Basket canvas entry. '
                       'The Local overlay requires separate launcher, request, and saved-workflow verification.',
     'source_sha256': '157e06c446d68d77bab30cba4578f5a71289da74d62c44c95b0b6ddd046edde6',
     'candidate_sha256': _SHOT_BASKET_CANDIDATE,
     'helper_sha256': '67612a63afe072a654c2b2ce7c0ae98ffdce10f580799595c5542560c1c942bf',
     'verification_sha256': {
         'reports/sound-readonly-sync-local862-20261105/native/BUILD.json': 'a112f931f5449726b15d52b448cbe5defaf66d4761078c1ee53693bae571e747',
         'reports/sound-readonly-sync-local862-20261105/widget/browser-current-v2.log': '422cba7e4f06ad3189fd6d2bb1281fe844f0d57bc8600b895da03866812993b6',
         'reports/sound-readonly-sync-local862-20261105/native/native-connections.log': 'fbb747cdd5b3eb0420e3f3fe1571674e469abbeaed36f92787bdac6e38aa1341',
         'reports/sound-readonly-sync-local862-20261105/native/native-deletion.log': 'fa7cb599e0f7fef422da7e0cd41c42832c12867deb5852d34341a437f64ed4ac',
         'reports/sound-readonly-sync-local862-20261105/sdk/case-final/RESULT.json': '691a5b94e954525d92b049a2196768375ae4a57d867b475b4aeecc03d95c996b',
     }}


def patch_editor_source(source: str, helper: str) -> tuple[str, dict]:
    """Transform only known structures; admit only the independently tested bytes."""
    import hashlib
    result = build_candidate(source, helper)
    evidence = approval_evidence()
    observed = tuple(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in (source, result, helper))
    reviewed = tuple(evidence[key] for key in ("source_sha256", "candidate_sha256", "helper_sha256"))
    previous = (*_REVIEWED_PREVIOUS_CANDIDATES, _SHOT_BASKET_BASE, _SHOT_BASKET_PREVIOUS_CANDIDATE,
                _SHOT_BASKET_HEADER_PREVIOUS_CANDIDATE, _SHOT_BASKET_SPRITE_PREVIOUS_CANDIDATE,
                _SHOT_BASKET_COMPACT_PREVIOUS_CANDIDATE, _SHOT_BASKET_STARTUP_PREVIOUS_CANDIDATE,
                _SHOT_BASKET_FLICKER_PREVIOUS_CANDIDATE, _SHOT_BASKET_HEADER_FADE_PREVIOUS_CANDIDATE)
    if observed != reviewed and not (observed[0] in (*previous, reviewed[1]) and observed[1:] == reviewed[1:]):
        evidence = {"status":"unvalidated", "structural_anchors":"matched", "live_renderer_verified":False, "deletion_verified":False}
    return result, evidence
