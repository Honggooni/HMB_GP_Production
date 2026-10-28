"""HMB native editor adapter with an exact reviewed capability profile.

Every critical structural anchor is required exactly once. Only the exact
compiled-renderer and SDK-tested source/helper/candidate combination is eligible
for local application. Unknown bytes remain unvalidated. Desktop validation and
team release approval are separate from this source-level eligibility.
"""
from __future__ import annotations
import re

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


_REVIEWED_PREVIOUS_CANDIDATES = (
    "ccabfc9bfddb67896231e0e75b067e659287f19fca143b2355f2c295d5da5251",
    "bcb4ea1649a78258c87b795cb73762e09c96575b0f811cb8ec34f609e21c3e17",
)


def _upgrade_reviewed_candidate(source: str, helper: str) -> str:
    """Replace only our helper in an exact previously reviewed compiled bundle."""
    import hashlib
    if hashlib.sha256(source.encode("utf-8")).hexdigest() not in _REVIEWED_PREVIOUS_CANDIDATES:
        raise ValueError("unknown previous HMB editor candidate; existing bytes preserved")
    marker = "/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1"
    boundary = "\nvar k8t=({node_name:"
    if source.count(marker) != 1 or source.count(boundary) != 1:
        raise ValueError("ambiguous HMB helper boundaries")
    start = source.index(marker)
    end = source.index(boundary, start)
    return _bash_live_input_bridge(_port_retention_notice_bridge(source[:start] + _compiled_helper(helper) + source[end:]))


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
    return src


def _port_retention_notice_bridge(source: str) -> str:
    """Classify only the explicit successful port-retention guard as information."""
    return one(source,
        'i===`failure`&&(o===`PermissionDeniedResult`?Cra(t,r):w_r({result:t,request:r}))',
        'i===`failure`&&!hmbNativePortRetainedNotice(t,r)&&(o===`PermissionDeniedResult`?Cra(t,r):w_r({result:t,request:r}))')


def build_candidate(source: str, helper: str) -> str:
    """Return an uninstalled candidate or raise when required shape is absent."""
    if not isinstance(source, str) or not isinstance(helper, str):
        raise TypeError('editor source and HMB helper must be text')
    if 'HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1' in source:
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
    return _bash_live_input_bridge(_port_retention_notice_bridge(source))

def approval_evidence() -> dict:
    """Exact independently verified local candidate; desktop confirmation separate."""
    return {'status': 'approved', 'structural_anchors': 'matched', 'live_renderer_verified': True, 'deletion_verified': True, 'desktop_verified': False, 'team_release_approved': False, 'renderer_scope': 'Exact compiled local candidate/private SDK, live Bash sources/Apply/cold browser and native reconnect; stock/store contracts scoped independently', 'source_sha256': '157e06c446d68d77bab30cba4578f5a71289da74d62c44c95b0b6ddd046edde6', 'candidate_sha256': '72dc87c51089c65554a9fcb44f80e38872338bb5a9c1ca4c9058d582e981f6e5', 'helper_sha256': '03137c19feb8f4fa4d5e371eb52bae3aaaccf4afb6a29f0098e815bccf65ee25', 'verification_sha256': {'reports\\usability-latency-20261028\\bash\\FINAL-MODAL-EVIDENCE.json': '7567474a07e271cad449887631d6a183b2660573f31981306002a575b3f69bfc', 'reports\\usability-latency-20261028\\bash\\modal-live-alias-staged.json': 'b4d3a41ac7ec84d757c2de8f752cb322afc7aa8f666065df172857c370aafaa3', 'reports\\usability-latency-20261028\\bash\\modal-live-delete-staged.json': 'c37f93ba9ab0c735390dc161393b76f669e5f40012855e796ddd68136adbe1ce', 'reports\\usability-latency-20261028\\bash\\modal-live-rapid-staged.json': '98fa882f59602dbf4825802b293b6fb5cc2596899ddd19207847a26786fa2d77', 'reports\\usability-latency-20261028\\bash\\modal-live-stale-staged.json': '4411fe533e8b29747f978f4626528acc3b488b259b7a84101129c2d96faddd4c', 'reports\\usability-latency-20261028\\bash\\modal-live-conflict-staged.json': 'dca9ed0cbaf26d517b8ace61e5adb59f8c1b2e903f1d85f88b55fcf36b291fb3', 'reports\\usability-latency-20261028\\bash\\modal-apply-race-staged.json': 'ef952f3d306bd792c293b5c0b7aabea47f4b65308dcd53be96595b298fde52bd', 'reports\\usability-latency-20261028\\bash\\modal-live-stock-staged.json': '7cd418dc2c78e11169dbd6a51a5f80078d59aadf88e962047303848ffdc25d48', 'reports\\usability-latency-20261028\\bash\\modal-live-cold-browser-staged.json': '919f512e6bf0ca305ed37b6d9ddc2386422be7a434164a5070e230fba21f915d', 'reports\\usability-latency-20261028\\native-controls\\native-cold-controls-final.json': '3179ca9259800c359b0ec28102fed0f9498a580f76915b0f993971bd09d57cf1', 'reports\\usability-latency-20261028\\bash\\backend-apply-fence\\final-frozen-payload\\HOST-REGRESSIONS.json': '18bb0ef9f37f22922c26c63c6ffc747ff6f49039dbdfa0996dc97dfa2bf48633', 'reports\\usability-latency-20261028\\native-controls\\NATIVE-EQUIVALENCE-FINAL.json': '0f7db45492bfffb3ff1c994db4c16561c4ba987673a10aab49247d87b880f361'}}

def patch_editor_source(source: str, helper: str) -> tuple[str, dict]:
    """Transform only known structures; admit only the independently tested bytes."""
    import hashlib
    result = build_candidate(source, helper)
    evidence = approval_evidence()
    observed = tuple(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in (source, result, helper))
    reviewed = tuple(evidence[key] for key in ("source_sha256", "candidate_sha256", "helper_sha256"))
    if observed != reviewed and not (observed[0] in _REVIEWED_PREVIOUS_CANDIDATES and observed[1:] == reviewed[1:]):
        evidence = {"status":"unvalidated", "structural_anchors":"matched", "live_renderer_verified":False, "deletion_verified":False}
    return result, evidence
