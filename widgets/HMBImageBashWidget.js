// HMB header and retained scene editor. Both mount through the SDK widget API.
export const HMB_IMAGE_BASH_HEADER_SCHEMA = "hmb-image-bash-header-v1";
export const HMB_IMAGE_BASH_PREPARATION_SCHEMA = "hmb-image-bash-preparation-v1";
const NODE_SCOPES = new WeakMap();
const EDGE_LAYERS = new WeakMap();
const TOPOLOGY_LAYERS = new WeakMap();
const IMAGE_EDGE = "data-hmb-image-bash-image-edge";
const CONTEXT_EDGE = "data-hmb-image-bash-context-edge";
let nextRequest = 0;
const record = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const clean = (value, max = 256) => typeof value === "string" ? value.slice(0, max) : "";
const escape = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));

function projection(input) {
  const wrapper = record(input);
  let value = wrapper.value ?? wrapper.parameterValue ?? wrapper.defaultValue ?? input;
  if (typeof value === "string") { try { value = JSON.parse(value); } catch { value = {}; } }
  return record(value);
}

export function hmbImageBashHeaderState(input = {}) {
  const raw = projection(input), valid = raw.schema === HMB_IMAGE_BASH_HEADER_SCHEMA;
  const seen = new Set(), sources = [];
  if (valid && Array.isArray(raw.sources)) for (const value of raw.sources.slice(0, 100)) {
    const source = record(value), id = clean(source.id), workspace = clean(source.workspace_id);
    if (!id || /[\u0000-\u001f]/.test(id) || !workspace || seen.has(id)) continue;
    seen.add(id); sources.push({ id, label: clean(source.label) || id, workspace_id: workspace,
      source_instance_id: clean(source.source_instance_id || record(raw.source_instances)[id], 128) });
  }
  const count = Number(raw.image_count);
  return { schema: HMB_IMAGE_BASH_HEADER_SCHEMA, sources,
    bound_source: valid ? clean(raw.bound_source) : "",
    image_count: valid && Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0,
    status: valid ? clean(typeof raw.status === "string" ? raw.status : record(raw.status).message, 1024) : "이미지 라이브러리를 연결하세요",
    locked: raw.locked === true, preparation: hmbImageBashPreparation(valid ? raw.preparation : {}),
    route: hmbImageBashHeaderRoute(valid ? raw.route : {}) };
}

export function hmbImageBashPreparation(value = {}) {
  const raw = record(value), valid = raw.schema === HMB_IMAGE_BASH_PREPARATION_SCHEMA;
  const integer = value => Number.isInteger(value) && value >= 0 ? value : null;
  const phase = valid && ["idle", "preparing", "ready", "error"].includes(raw.phase) ? raw.phase : "idle";
  return {schema:HMB_IMAGE_BASH_PREPARATION_SCHEMA,phase,ready:["idle","ready"].includes(phase) && (!valid || raw.ready === true),
    workspace_id:valid?clean(raw.workspace_id,128):"", workspace_revision:valid?integer(raw.workspace_revision)??0:0,
    channel_uuid:valid?clean(raw.channel_uuid,128):"", node_instance_uuid:valid?clean(raw.node_instance_uuid,128):"",
    requested_count:valid?integer(raw.requested_count):null,prepared_count:valid?integer(raw.prepared_count)??0:0,
    error:valid?clean(raw.error,1024):""};
}

export function hmbImageBashHeaderRoute(value = {}) {
  const raw = record(value), source = clean(raw.source_node_name), target = clean(raw.target_node_name);
  return raw.connected === true && source && target && !/[\u0000-\u001f]/.test(source + target)
    && raw.source_parameter === "IMAGE_BASH_IMAGES_OUT" && raw.context_source_parameter === "IMAGE_BASH_CONTEXT_OUT"
    ? { connected: true, source_node_name: source, target_node_name: target,
      source_parameter: "IMAGE_BASH_IMAGES_OUT", context_source_parameter: "IMAGE_BASH_CONTEXT_OUT" }
    : { connected: false, source_node_name: "", target_node_name: "",
      source_parameter: "IMAGE_BASH_IMAGES_OUT", context_source_parameter: "IMAGE_BASH_CONTEXT_OUT" };
}

export function hmbImageBashEdgeMatches(element, value, kind = "images") {
  const route = hmbImageBashHeaderRoute(value);
  if (!route.connected || !element?.getAttribute || !["images", "context"].includes(kind)) return false;
  const output = kind === "images" ? "IMAGE_BASH_IMAGES_OUT" : "IMAGE_BASH_CONTEXT_OUT";
  const input = kind === "images" ? "input_images" : "image_bash_context";
  const prefix = `${route.source_node_name}-${output}-${route.target_node_name}-${input}-`;
  const id = String(element.getAttribute("data-id") || "");
  return id.startsWith(prefix) && id.length > prefix.length
    && element.getAttribute("aria-label") === `Edge from ${route.source_node_name} to ${route.target_node_name}`;
}

function optionMarkup(state) {
  const missing = state.bound_source && !state.sources.some(source => source.id === state.bound_source)
    ? `<option value="${escape(state.bound_source)}" disabled>${escape(state.bound_source)} · 원본 확인 필요</option>` : "";
  return `<option value="">이미지 라이브러리 연결</option>${missing}` + state.sources.map(source =>
    `<option value="${escape(source.id)}">${escape(source.label)}</option>`).join("");
}

export function hmbRenderImageBashHeader(input = {}) {
  const state = hmbImageBashHeaderState(input);
  return `<style>
.hmb-image-bash-header{--ib-accent:#F472B6;--ib-rgb:244,114,182;width:100%;height:64px;min-height:64px;max-height:64px;box-sizing:border-box;overflow:hidden;border:1px solid rgba(var(--ib-rgb),.32);border-radius:16px;background:linear-gradient(100deg,rgba(var(--ib-rgb),.1),#101521 68%);color:#e8eef7;font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;color-scheme:dark}
.hmb-image-bash-header *{box-sizing:border-box;min-width:0}.hmb-image-bash-header__row{height:100%;display:flex;align-items:center;gap:10px;padding:8px 13px}.hmb-image-bash-header__mark{flex:0 0 32px;width:32px;height:32px;display:grid;place-items:center;border:1px solid rgba(var(--ib-rgb),.25);border-radius:50%;background:rgba(var(--ib-rgb),.09);color:var(--ib-accent);font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-image-bash-header__identity{flex:1;min-width:110px}.hmb-image-bash-header__title{font-size:15px;font-weight:800;letter-spacing:.01em;white-space:nowrap}.hmb-image-bash-header__status{margin-top:3px;color:#a7b3c6;font-size:9px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.hmb-image-bash-header__count{flex:0 0 auto;color:#fbcfe8;border:1px solid rgba(var(--ib-rgb),.25);border-radius:999px;background:rgba(var(--ib-rgb),.08);padding:5px 8px;font-size:10px;font-weight:800;white-space:nowrap}.hmb-image-bash-header__source{flex:0 1 230px;width:230px;height:38px;padding:0 26px 0 10px;border:1px solid rgba(var(--ib-rgb),.32);border-radius:12px;background:#080d15;color:#fbcfe8;font:inherit;font-size:11px;font-weight:750;outline:none}.hmb-image-bash-header__source option{background:#0b111b;color:#e8eef7}.hmb-image-bash-header__refresh{flex:0 0 34px;width:34px;height:34px;border:1px solid #344057;border-radius:50%;background:#1b2533;color:#fbcfe8;font:inherit;font-size:20px;cursor:pointer}.hmb-image-bash-header :is(button,select):focus-visible:not([data-hmb-native-identity] *):not([data-hmb-native-actions] *){outline:2px solid var(--ib-accent);outline-offset:2px}.hmb-image-bash-header :disabled:not([data-hmb-native-identity] *):not([data-hmb-native-actions] *){opacity:.5;cursor:default}
.react-flow__node[data-hmb-image-bash="true"] .react-flow__handle[data-handleid="input_images"]{background:#ef4444!important;border-color:#f87171!important}
.react-flow__node[data-hmb-image-bash="true"] .react-flow__handle[data-handleid="input_images"] svg circle{fill:#ef4444!important;stroke:#ef4444!important}
.hmb-image-bash-header__remote{flex:0 0 auto;color:#a7b3c6;font-size:8px;font-weight:850;letter-spacing:.08em}
.react-flow__edge[${IMAGE_EDGE}="true"] .react-flow__edge-path{stroke:#ef4444!important}
.react-flow__edge[${CONTEXT_EDGE}="true"]{display:none!important}
@container(max-width:520px){.hmb-image-bash-header__row{gap:7px;padding:8px}.hmb-image-bash-header__source{flex-basis:140px;width:140px}.hmb-image-bash-header__count{padding:5px}.hmb-image-bash-header__identity{min-width:95px}.hmb-image-bash-header__title{font-size:12px}.hmb-image-bash-header__mark{display:none}}
.hmb-image-bash-header [data-hmb-native-identity],.hmb-image-bash-header [data-hmb-native-actions]{display:none;min-width:0}
.hmb-image-bash-header[data-hmb-native-header=active]{border:0;border-radius:0;overflow:visible}
.hmb-image-bash-header[data-hmb-native-header=active] :is(.hmb-image-bash-header__mark,.hmb-image-bash-header__title){display:none}
.hmb-image-bash-header[data-hmb-native-header=active] [data-hmb-native-identity]{display:flex;align-items:center;overflow:hidden}
.hmb-image-bash-header[data-hmb-native-header=active] [data-hmb-native-actions]{display:flex;align-items:center;flex:0 0 auto}
.hmb-image-bash-header[data-hmb-native-header=active] .hmb-image-bash-header__source{flex-basis:170px;width:170px}
.hmb-image-bash-header [data-hmb-native-identity] :is(span,div){min-width:0}
.hmb-image-bash-header__count[data-loading=true]::before{content:"";display:inline-block;width:9px;height:9px;margin-right:5px;vertical-align:-1px;border:1.5px solid currentColor;border-right-color:transparent;border-radius:50%;animation:hmb-bash-ready-spin .9s linear infinite}.hmb-image-bash-header__retry{flex:0 0 auto;padding:5px 8px;border:1px solid rgba(var(--ib-rgb),.4);border-radius:999px;background:#1b2533;color:#fbcfe8;font:inherit;font-size:10px;cursor:pointer}.hmb-image-bash-header__retry[hidden]{display:none}@keyframes hmb-bash-ready-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.hmb-image-bash-header__count[data-loading=true]::before{animation:none}}
</style><div class="hmb-image-bash-header nodrag" data-hmb-image-bash-header>
  <div class="hmb-image-bash-header__row"><span class="hmb-image-bash-header__mark" aria-hidden="true">IB</span>
    <div class="hmb-image-bash-header__identity"><div data-hmb-native-identity></div><div class="hmb-image-bash-header__title">HMBImageBash</div>
      <div class="hmb-image-bash-header__status" data-bash-status role="status" aria-live="polite">${escape(state.status)}</div></div>
    <div data-hmb-native-actions class="nodrag"></div><span class="hmb-image-bash-header__count" data-bash-count>이미지 ${state.image_count}</span><button class="hmb-image-bash-header__retry nodrag" data-bash-retry type="button" hidden>다시 시도</button>
    <select class="hmb-image-bash-header__source nodrag" data-bash-source aria-label="REMOTE Image Bash 이미지 라이브러리">${optionMarkup(state)}</select>
  </div></div>`;
}

function scopeNode(container) {
  const node = container.closest?.(".react-flow__node");
  if (!node) return () => {};
  let scope = NODE_SCOPES.get(node);
  if (!scope) {
    scope = { owners: new Set(), prior: node.getAttribute("data-hmb-image-bash") };
    NODE_SCOPES.set(node, scope);
  }
  const owner = {};
  scope.owners.add(owner); node.setAttribute("data-hmb-image-bash", "true");
  return () => {
    scope.owners.delete(owner);
    if (scope.owners.size) return;
    if (node.getAttribute("data-hmb-image-bash") === "true") {
      if (scope.prior === null) node.removeAttribute("data-hmb-image-bash");
      else node.setAttribute("data-hmb-image-bash", scope.prior);
    }
    NODE_SCOPES.delete(node);
  };
}

function requestId(container) {
  const crypto = container.ownerDocument?.defaultView?.crypto || globalThis.crypto;
  if (typeof crypto?.randomUUID === "function") return crypto.randomUUID();
  return `hmb-image-bash-${Date.now().toString(36)}-${++nextRequest}-${Math.random().toString(36).slice(2)}`;
}

function visibleCarrier(container) {
  if (container.isConnected === false || container.ownerDocument?.hidden || !container.getClientRects().length) return false;
  const win = container.ownerDocument.defaultView;
  for (let current = container; current; current = current.parentElement) {
    const style = win.getComputedStyle(current);
    if (style.visibility !== "visible" || style.display === "none" || Number(style.opacity) === 0) return false;
    if (current.classList?.contains("react-flow__node")) break;
  }
  return true;
}

// One observer per visible graph, not one observer per source or frame. It
// watches topology/workspace membership only; ordinary shot/input/thumbnail
// updates must never trigger a source refresh or re-read the scene.
function watchTopology(container, notify) {
  const node = container.closest?.(".react-flow__node"), layer = node?.parentElement;
  const win = container.ownerDocument?.defaultView;
  if (!layer || typeof win?.MutationObserver !== "function") return () => {};
  let shared = TOPOLOGY_LAYERS.get(layer);
  if (!shared) {
    shared = { layer, win, entries: new Map(), active: true, scheduled: null, nodes: [], assetNodes: new Set() };
    const snapshot = () => {
      const rows = Array.from(layer.children).filter(element => element.matches?.(".react-flow__node[data-id]"))
      .map(element => ({ element, id: element.getAttribute("data-id"),
        asset: Boolean(element.querySelector('[data-hmb-native-node-type="HMBImageAssetLibrary"]')),
        workspaces: Array.from(new Set(Array.from(element.querySelectorAll("[data-image-bash-panel]"),
          row => row.getAttribute("data-image-bash-panel")))).sort().join("\u001f") }));
      shared.assetNodes = new Set(rows.filter(row => row.asset || row.workspaces).map(row => row.element));
      return rows;
    };
    shared.nodes = snapshot();
    const schedule = () => {
      if (!shared.active || shared.scheduled !== null) return;
      shared.scheduled = win.requestAnimationFrame(() => {
        shared.scheduled = null;
        if (!shared.active) return;
        const next = snapshot(), before = shared.nodes;
        if (next.length === before.length && next.every((row, index) => row.element === before[index].element
          && row.id === before[index].id && row.asset === before[index].asset && row.workspaces === before[index].workspaces)) return;
        shared.nodes = next;
        // Measurement/footer clones may share this native node. Only its one
        // visible surviving owner may send a metadata-only Refresh.
        const owners = new Map();
        for (const [carrier, entry] of shared.entries) if (visibleCarrier(carrier) && !owners.has(entry.node)) owners.set(entry.node, [carrier, entry]);
        for (const [carrier, entry] of owners.values()) if (shared.entries.get(carrier) === entry && visibleCarrier(carrier)) entry.notify();
      });
    };
    shared.observer = new win.MutationObserver(records => {
      if (records.some(record => {
        if (record.type === "attributes") return record.oldValue !== record.target.getAttribute(record.attributeName)
          && (record.attributeName !== "data-hmb-native-node-type"
            || record.oldValue === "HMBImageAssetLibrary" || record.target.getAttribute(record.attributeName) === "HMBImageAssetLibrary");
        if (record.target === layer) return true;
        const owner = record.target.closest?.(".react-flow__node");
        return shared.assetNodes.has(owner);
      })) schedule();
    });
    shared.observer.observe(layer, { childList: true, subtree: true, attributes: true, attributeOldValue: true,
      attributeFilter: ["data-id", "data-image-bash-panel", "data-hmb-native-node-type"] });
    TOPOLOGY_LAYERS.set(layer, shared);
  }
  const entry = { node, notify }; shared.entries.set(container, entry);
  return () => {
    if (shared.entries.get(container) === entry) shared.entries.delete(container);
    if (shared.entries.size) return;
    shared.active = false; shared.observer.disconnect();
    if (shared.scheduled !== null) win.cancelAnimationFrame(shared.scheduled);
    shared.scheduled = null; TOPOLOGY_LAYERS.delete(layer);
  };
}

function edgeLayer(container) {
  let current = container.closest?.(".react-flow__node")?.parentElement;
  for (let depth = 0; current && depth < 16; depth++, current = current.parentElement) {
    const layer = current.querySelector?.(".react-flow__edges");
    if (layer) return layer;
  }
  return null;
}

function restoreEdge(edge, owned) {
  if (edge.getAttribute(owned.attribute) !== "true") return;
  if (owned.prior === null) edge.removeAttribute(owned.attribute);
  else edge.setAttribute(owned.attribute, owned.prior);
}

function scanEdges(controller) {
  if (!controller.active) return;
  const wanted = new Map(), routes = Array.from(controller.entries.values());
  for (const edge of controller.layer.querySelectorAll(".react-flow__edge[data-id][aria-label]")) {
    if (routes.some(route => hmbImageBashEdgeMatches(edge, route, "images"))) wanted.set(edge, IMAGE_EDGE);
    else if (routes.some(route => hmbImageBashEdgeMatches(edge, route, "context"))) wanted.set(edge, CONTEXT_EDGE);
  }
  for (const [edge, owned] of controller.marked) if (wanted.get(edge) !== owned.attribute) {
    restoreEdge(edge, owned); controller.marked.delete(edge);
  }
  for (const [edge, attribute] of wanted) {
    if (!controller.marked.has(edge)) controller.marked.set(edge, { attribute, prior: edge.getAttribute(attribute) });
    if (edge.getAttribute(attribute) !== "true") edge.setAttribute(attribute, "true");
  }
}

function scheduleEdges(controller) {
  if (!controller.active || controller.scheduled !== null) return;
  const run = () => { controller.scheduled = null; scanEdges(controller); };
  controller.scheduled = controller.win.requestAnimationFrame(run);
}

function releaseEdges(container) {
  const layer = container.__hmbImageBashEdgeLayer;
  delete container.__hmbImageBashEdgeLayer;
  const controller = layer && EDGE_LAYERS.get(layer);
  if (!controller) return;
  controller.entries.delete(container);
  if (controller.entries.size) { scanEdges(controller); return; }
  controller.active = false; controller.observer?.disconnect();
  if (controller.scheduled !== null) controller.win.cancelAnimationFrame(controller.scheduled);
  for (const [edge, owned] of controller.marked) restoreEdge(edge, owned);
  controller.marked.clear(); EDGE_LAYERS.delete(layer);
}

function syncEdges(container, value) {
  const route = hmbImageBashHeaderRoute(value), node = container.closest?.(".react-flow__node");
  const layer = route.connected && node?.getAttribute("data-id") === route.target_node_name ? edgeLayer(container) : null;
  if (container.__hmbImageBashEdgeLayer !== layer) releaseEdges(container);
  if (!layer) return;
  let controller = EDGE_LAYERS.get(layer);
  if (!controller) {
    const win = layer.ownerDocument.defaultView;
    controller = { layer, win, entries: new Map(), marked: new Map(), scheduled: null, observer: null, active: true };
    if (typeof win.MutationObserver === "function") {
      controller.observer = new win.MutationObserver(() => scheduleEdges(controller));
      controller.observer.observe(layer, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-id", "aria-label"] });
    }
    EDGE_LAYERS.set(layer, controller);
  }
  const old = controller.entries.get(container);
  controller.entries.set(container, route); container.__hmbImageBashEdgeLayer = layer;
  if (!old || JSON.stringify(old) !== JSON.stringify(route)) scanEdges(controller);
}

function hmbNativeStockSafetyImplementation(container, props = {}) {
  if (!container) return { update() {}, cleanup() {} };
  if (props.parameterName === "bash_image") return mountEditor(container, props);
  const previous = container.__hmbImageBashController;
  if (previous) { previous.update(props); return previous; }
  let latestProps = props, state = hmbImageBashHeaderState(props), disposed = false;
  let pending = false, refreshPending = false, message = "", epoch = 0, lastOptions = "";
  let initialRefreshAttempted = false, initialRefreshFrame = null, focusRefreshFrame = null;
  let topologyRefreshNeeded = false, topologyRefreshFrame = null;
  const win = container.ownerDocument?.defaultView;
  const ownedStyles = new Map(), hadNoDrag = container.classList?.contains("nodrag");
  for (const [name, value] of [["height", "64px"], ["min-height", "64px"], ["max-height", "64px"],
    ["flex", "0 0 64px"], ["flex-basis", "64px"], ["box-sizing", "border-box"]]) {
    ownedStyles.set(name, { value, old: container.style?.getPropertyValue(name) || "", priority: container.style?.getPropertyPriority(name) || "" });
    container.style?.setProperty(name, value, "important");
  }
  container.classList?.add("nodrag"); container.innerHTML = hmbRenderImageBashHeader(state);
  const releaseNode = scopeNode(container), select = container.querySelector("[data-bash-source]");
  const header = container.querySelector("[data-hmb-image-bash-header]"), status = container.querySelector("[data-bash-status]");
  const count = container.querySelector("[data-bash-count]");
  const retry = container.querySelector("[data-bash-retry]");
  container.setAttribute("data-hmb-color-lut-widget", "");
  container.setAttribute("data-hmb-native-node-type", "HMBImageBash");
  const nativeTarget = target => target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions]");
  const announceHeader = kind => container.ownerDocument.dispatchEvent(new win.CustomEvent(`hmb-color-lut-header-${kind}`, {detail:{container}}));
  const nativeState = event => {
    const active = event.detail?.active === true;
    header.setAttribute("data-hmb-native-header", active ? "active" : "fallback");
    header.classList.toggle("nodrag", !active);
    if(active) container.classList.remove("nodrag"); else container.classList.toggle("nodrag", Boolean(hadNoDrag));
  };
  container.addEventListener("hmb-color-lut-header-state", nativeState);
  const disabled = () => latestProps.disabled === true || state.locked || pending;
  const sync = () => {
    if (disposed) return;
    const options = optionMarkup(state);
    if (options !== lastOptions) { select.innerHTML = options; lastOptions = options; }
    if (select.value !== state.bound_source) select.value = state.bound_source;
    if (select.disabled !== disabled()) select.disabled = disabled();
    const preparation=state.preparation,busy=preparation.phase==="preparing";
    status.textContent = message || (busy?"작업 준비 중 · 이미지 원본을 확인합니다":preparation.phase==="error"?preparation.error||"소스 확인 필요 · 다시 시도하세요":state.status) || (state.bound_source ? "이미지 라이브러리 연결됨" : "이미지 라이브러리를 연결하세요");
    status.title = status.textContent;
    count.textContent = `이미지 ${preparation.requested_count??state.image_count}${busy?" · 준비 중":""}`;
    count.setAttribute("data-loading",String(busy));
    header.setAttribute("aria-busy",String(busy));header.setAttribute("data-bash-preparation",preparation.phase);
    retry.hidden=preparation.phase!=="error";retry.disabled=disabled()||!state.route.connected;
    syncEdges(container, state.route);
  };
  const dispatch = (operation, source) => {
    const background = operation === "refresh";
    if (disposed || disabled() || background && refreshPending) { sync(); return; }
    if (typeof latestProps.onChange !== "function") { message = "노드의 UI 전달 경로를 확인하세요"; sync(); return; }
    const raw = JSON.parse(JSON.stringify(projection(latestProps)));
    delete raw.hmb_image_bash_command;
    const payload = { ...raw, schema: HMB_IMAGE_BASH_HEADER_SCHEMA, hmb_image_bash_command: {
      operation, source_node_name: operation === "unbind" ? "" : source?.id || "", workspace_id: source?.workspace_id || "", request_id: requestId(container),
      ...(["bind", "unbind", "retry_inputs"].includes(operation) ? {source_instance_id: source?.source_instance_id || ""} : {}),
    } };
    const ticket = ++epoch;
    if(background) refreshPending = true;
    else { pending = true; message = "연결 변경 중…"; }
    sync();
    const finish = error => {
      if (disposed || epoch !== ticket) return;
      pending = false; refreshPending = false; message = error ? `연결 요청 실패: ${String(error?.message || error)}` : "";
      sync(); scheduleTopologyRefresh();
    };
    try {
      const result = latestProps.onChange(payload);
      if (result && typeof result.then === "function") Promise.resolve(result).then(() => finish(), finish);
      else finish();
    } catch (error) { finish(error); }
  };
  const change = () => {
    const source = state.sources.find(row => row.id === select.value);
    if (select.value && !source) { sync(); return; }
    dispatch(source ? "bind" : "unbind", source || state.sources.find(row => row.id === state.bound_source));
  };
  const reload = () => dispatch("refresh", state.sources.find(row => row.id === state.bound_source));
  const retryInputs = event => {event.preventDefault();event.stopPropagation();dispatch("retry_inputs",state.sources.find(row=>row.id===state.bound_source));};
  const scheduleTopologyRefresh = () => {
    if (disposed || !topologyRefreshNeeded || topologyRefreshFrame !== null || refreshPending || disabled()) return;
    topologyRefreshFrame = win.requestAnimationFrame(() => {
      topologyRefreshFrame = null;
      if (disposed || !topologyRefreshNeeded || refreshPending || disabled() || !visibleCarrier(container)) return;
      topologyRefreshNeeded = false; reload();
    });
  };
  const releaseTopology = watchTopology(container, () => { topologyRefreshNeeded = true; scheduleTopologyRefresh(); });
  const scheduleFocusRefresh = () => {
    if(disposed || focusRefreshFrame !== null || disabled() || refreshPending) return;
    focusRefreshFrame = win.requestAnimationFrame(() => {
      focusRefreshFrame = null;
      if(disposed || disabled() || !visibleCarrier(container)) return;
      reload();
    });
  };
  // The header projection is intentionally not serialized. Native workflow
  // hydration can skip after_value_set, so request one fresh projection after
  // the visible carrier mounts. Measurement copies must never issue commands.
  const scheduleInitialRefresh = () => {
    if (disposed || initialRefreshAttempted || initialRefreshFrame !== null || !win?.requestAnimationFrame) return;
    initialRefreshFrame = win.requestAnimationFrame(() => {
      initialRefreshFrame = null;
      if (disposed || initialRefreshAttempted || disabled() || typeof latestProps.onChange !== "function"
        || !visibleCarrier(container)) return;
      // Mark before dispatch: a synchronous authoritative echo may call update
      // while onChange is still on the stack. Rejections get no automatic retry.
      initialRefreshAttempted = true;
      reload();
    });
  };
  const stop = event => { if (!nativeTarget(event.target) && ["Delete", "Backspace"].includes(event.key)) event.stopPropagation(); };
  select.addEventListener("change", change); select.addEventListener("focus", scheduleFocusRefresh); select.addEventListener("pointerdown", scheduleFocusRefresh);
  retry.addEventListener("click",retryInputs);
  container.addEventListener("keydown", stop);
  const controller = {
    update(nextProps) {
      if (disposed) return;
      ++epoch; latestProps = nextProps || {}; state = hmbImageBashHeaderState(latestProps);
      pending = false; refreshPending = false; message = ""; sync(); scheduleInitialRefresh(); scheduleTopologyRefresh();
    },
    cleanup() {
      if (disposed) return;
      announceHeader("retire");
      disposed = true; ++epoch;
      if (initialRefreshFrame !== null) win.cancelAnimationFrame(initialRefreshFrame);
      initialRefreshFrame = null;
      if(focusRefreshFrame !== null) win.cancelAnimationFrame(focusRefreshFrame);
      if(topologyRefreshFrame !== null) win.cancelAnimationFrame(topologyRefreshFrame);
      topologyRefreshFrame = null; topologyRefreshNeeded = false;
      select.removeEventListener("change", change); select.removeEventListener("focus", scheduleFocusRefresh); select.removeEventListener("pointerdown", scheduleFocusRefresh);
      retry.removeEventListener("click",retryInputs);
      container.removeEventListener("hmb-color-lut-header-state", nativeState);
      container.removeAttribute("data-hmb-color-lut-widget");container.removeAttribute("data-hmb-native-node-type");
      container.removeEventListener("keydown", stop); releaseTopology(); releaseNode(); releaseEdges(container);
      for (const [name, saved] of ownedStyles) if (container.style?.getPropertyValue(name) === saved.value
        && container.style?.getPropertyPriority(name) === "important") {
        if (saved.old) container.style.setProperty(name, saved.old, saved.priority);
        else container.style.removeProperty(name);
      }
      if (!hadNoDrag) container.classList?.remove("nodrag");
      if (container.__hmbImageBashController === controller) delete container.__hmbImageBashController;
      container.innerHTML = "";
    },
  };
  container.__hmbImageBashController = controller; sync(); scheduleInitialRefresh(); announceHeader("ready"); return controller;
}

const EDITOR_SCHEMA = "hmb-image-bash-editor-v1";
const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const ordered = layers => layers.slice().sort((first, second) => finite(first.order) - finite(second.order));

function editorDocument(input) {
  const value = record(projection(input));
  // The widget receives the JSON artifact itself, or an SDK property envelope.
  const project = record(input?.meta).konva_json ? input : value;
  if (!record(project.meta).konva_json) return null;
  const {HMB_IMAGE_BASH_UI: _header, ...document} = project;
  return document;
}

function mountEditor(container, props = {}) {
  const doc = container.ownerDocument, win = doc.defaultView;
  const button = doc.createElement("button");
  button.type = "button"; button.className = "nodrag";
  button.textContent = "HMB Image Bash 편집기 열기";
  button.style.cssText = "width:100%;height:36px;border:1px solid #394358;border-radius:8px;background:#192131;color:#f5e7f2;cursor:pointer";
  container.replaceChildren(button);
  let latest = props, dialog = null, reconcile = null;

  function update(next) {
    latest = next;
    const project = editorDocument(next.value);
    const snapshot = project?.meta?.hmb_image_bash?.editor_snapshot_id;
    const authority = record(projection(record(next.value).HMB_IMAGE_BASH_UI));
    const ready = authority.schema !== HMB_IMAGE_BASH_HEADER_SCHEMA
      || (authority.preparation?.phase === "ready" && authority.preparation?.editor_snapshot_id === snapshot && !authority.locked);
    button.disabled = !!next.disabled || !snapshot || !ready;
    if (dialog) reconcile?.(project, authority);
  }

  function open() {
    const initial = editorDocument(latest.value);
    let snapshot = initial?.meta?.hmb_image_bash?.editor_snapshot_id;
    if (dialog || button.disabled || !snapshot) return;
    let draft = structuredClone(initial), meta = draft.meta;
    let scene = structuredClone(meta.konva_json), selection = "", gesture = null, zoom = 1, epoch = 0;
    let pending = "", stale = false, closed = false;
    let frame = null, saveDeadline = null;
    const history = [], redo = [], rasters = new Map();
    const width = finite(meta.hmb_canvas?.width ?? meta.canvas_size?.width, 1920);
    const height = finite(meta.hmb_canvas?.height ?? meta.canvas_size?.height, 1080);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width * height > 100_000_000) return;

    const modal = doc.createElement("dialog");
    modal.className = "hmb-owned-bash"; modal.setAttribute("aria-labelledby", "hmb-owned-bash-title");
    modal.innerHTML = `<style>
.hmb-owned-bash{width:min(1240px,95vw);height:min(850px,92vh);max-width:none;max-height:none;margin:auto;padding:0;overflow:hidden;border:1px solid #45435a;border-radius:16px;background:#101622;color:#e8edf6;color-scheme:dark;font:14px system-ui}
.hmb-owned-bash::backdrop{background:#050810be}.hmb-owned-bash *{box-sizing:border-box}.hmb-owned-bash article{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto}.hmb-owned-bash header,.hmb-owned-bash footer,.hmb-owned-bash .tools{display:flex;align-items:center;gap:8px;padding:10px 14px}.hmb-owned-bash header{border-bottom:1px solid #33394e}.hmb-owned-bash header strong,.hmb-owned-bash footer output{flex:1}.hmb-owned-bash footer{border-top:1px solid #33394e}.hmb-owned-bash .body{display:grid;grid-template-columns:minmax(0,1fr) 265px;min-height:0}.hmb-owned-bash .stage{display:grid;grid-template-rows:auto minmax(0,1fr);min-width:0}.hmb-owned-bash .tools{flex-wrap:wrap}.hmb-owned-bash .view{overflow:auto;background:#090d15;display:grid;place-items:safe center;padding:14px}.hmb-owned-bash canvas{display:block;background:#fff;max-width:none;touch-action:none;box-shadow:0 0 0 1px #45435a}.hmb-owned-bash aside{border-left:1px solid #33394e;overflow:auto;padding:12px}.hmb-owned-bash [data-layers]{display:grid;gap:4px;margin:8px 0}.hmb-owned-bash [data-layer]{text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hmb-owned-bash [aria-pressed=true]{border-color:#ed82ba;background:#592c48}.hmb-owned-bash .fields{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:12px}.hmb-owned-bash label{display:grid;gap:3px}.hmb-owned-bash button,.hmb-owned-bash select,.hmb-owned-bash input{font:inherit;color:inherit;min-width:0;padding:5px 8px;border:1px solid #43485d;border-radius:6px;background:#20283a}.hmb-owned-bash button{cursor:pointer}.hmb-owned-bash button:disabled{opacity:.46;cursor:default}.hmb-owned-bash button:focus-visible,.hmb-owned-bash input:focus-visible{outline:2px solid #f59acb;outline-offset:1px}.hmb-owned-bash .primary{background:#733f62;border-color:#b86c9a;font-weight:700}.hmb-owned-bash output{color:#bdc6d8}.hmb-owned-bash output[data-error=true]{color:#ffb6c3}.hmb-owned-bash input[type=color]{width:38px;height:29px;padding:3px}
</style><article><header><strong id="hmb-owned-bash-title">HMB Image Bash</strong><span data-size></span><button type="button" data-close aria-label="닫기">✕</button></header>
<div class="body"><div class="stage"><div class="tools"><button type="button" data-undo>실행 취소</button><button type="button" data-redo>다시 실행</button>
<label><select aria-label="도구" data-tool><option value="move">이동</option><option value="brush">브러시</option><option value="erase">지우개</option></select></label>
<input type="color" aria-label="브러시 색" data-color value="#ff428a"><input type="number" aria-label="브러시 크기" data-brush-size min="1" max="300" value="18" style="width:66px">
<button type="button" data-zoom-out aria-label="축소">−</button><button type="button" data-zoom-fit>맞춤</button><button type="button" data-zoom-in aria-label="확대">+</button></div><div class="view"><canvas aria-label="합성 미리보기"></canvas></div></div>
<aside aria-label="레이어"><strong>레이어</strong><div data-layers></div><div class="tools" style="padding:0"><button type="button" data-up aria-label="레이어 위로">↑</button><button type="button" data-down aria-label="레이어 아래로">↓</button><button type="button" data-copy>복제</button><button type="button" data-delete>삭제</button></div>
<div class="fields"><label>X<input type="number" data-field="x" step="1"></label><label>Y<input type="number" data-field="y" step="1"></label><label>회전<input type="number" data-field="rotation" step="1"></label><label>불투명도 %<input type="number" data-field="opacity" min="0" max="100" step="1"></label><label>가로 배율<input type="number" data-field="scaleX" step=".01"></label><label>세로 배율<input type="number" data-field="scaleY" step=".01"></label><label>표시<input type="checkbox" data-field="visible"></label></div></aside></div>
<footer><output aria-live="polite"></output><button type="button" data-close>닫기</button><button type="button" class="primary" data-apply>Apply PNG</button></footer></article>`;
    const $ = selector => modal.querySelector(selector);
    const canvas = $("canvas"), view = $(".view"), ctx = canvas.getContext("2d");
    const apply = $("[data-apply]"), status = $("output"), fields = [...modal.querySelectorAll("[data-field]")];
    const ink = doc.createElement("canvas");
    canvas.width = ink.width = width; canvas.height = ink.height = height;
    const inkContext = ink.getContext("2d");
    if (!ctx || !inkContext) return;
    $("[data-size]").textContent = `${width} × ${height}`;

    const images = () => Array.isArray(scene.images) ? scene.images : [];
    const selected = () => images().find(layer => layer.id === selection);
    function message(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
    function fit() {
      const scale = Math.min((view.clientWidth - 28) / width, (view.clientHeight - 28) / height, 1) * zoom;
      canvas.style.width = `${Math.max(1, width * scale)}px`;
      canvas.style.height = `${Math.max(1, height * scale)}px`;
    }
    function raster(source) {
      if (!rasters.has(source)) {
        const url = new URL(source, win.location.href);
        if (!['http:', 'https:', 'data:', 'blob:'].includes(url.protocol)) throw Error("브라우저에 원본 주소가 준비되지 않았습니다.");
        const image = new win.Image(); image.crossOrigin = "anonymous";
        rasters.set(source, new Promise((resolve, reject) => {
          image.onload = () => resolve(image);
          image.onerror = () => reject(Error("레이어의 원본 이미지를 열 수 없습니다. ImageAsset 연결을 확인하세요."));
          image.src = url.href;
        }).catch(error => { rasters.delete(source); throw error; }));
      }
      return rasters.get(source);
    }
    async function paint() {
      const id = ++epoch;
      apply.disabled = true;
      try {
        const layers = ordered(images()).filter(layer => layer.visible !== false);
        const decoded = await Promise.all(layers.map(layer => {
          if (!["image", "brush", undefined].includes(layer.type) || typeof layer.src !== "string" || !layer.src)
            throw Error("저장된 레이어의 원본 또는 유형을 확인할 수 없습니다.");
          return raster(layer.src);
        }));
        if (closed || id !== epoch) return false;
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = meta.hmb_canvas?.background_color || "#ffffff"; ctx.fillRect(0, 0, width, height);
        layers.forEach((layer, index) => {
          const bitmap = decoded[index], w = finite(layer.width, bitmap.width), h = finite(layer.height, bitmap.height);
          ctx.save(); ctx.globalAlpha = finite(layer.opacity, 1);
          ctx.translate(finite(layer.x), finite(layer.y)); ctx.rotate(finite(layer.rotation) * Math.PI / 180);
          ctx.scale(finite(layer.scaleX, 1), finite(layer.scaleY, 1)); ctx.drawImage(bitmap, -w / 2, -h / 2, w, h); ctx.restore();
        });
        inkContext.clearRect(0, 0, width, height);
        for (const line of scene.lines || []) {
          const points = line.points;
          if (!Array.isArray(points) || points.length < 2 || points.length % 2 || !points.every(Number.isFinite))
            throw Error("저장된 브러시 경로를 읽을 수 없습니다.");
          inkContext.save(); inkContext.lineWidth = finite(line.strokeWidth, 1); inkContext.lineCap = "round"; inkContext.lineJoin = "round";
          inkContext.strokeStyle = line.stroke || "#000000";
          inkContext.globalCompositeOperation = line.globalCompositeOperation === "destination-out" ? "destination-out" : "source-over";
          inkContext.beginPath(); inkContext.moveTo(points[0], points[1]);
          if (points.length === 2) inkContext.lineTo(points[0] + .01, points[1]);
          for (let index = 2; index < points.length; index += 2) inkContext.lineTo(points[index], points[index + 1]);
          inkContext.stroke(); inkContext.restore();
        }
        ctx.drawImage(ink, 0, 0);
        apply.disabled = stale || !!pending || !!gesture;
        return true;
      } catch (error) {
        if (!closed && id === epoch && !stale) message(error.message, true);
        return false;
      }
    }
    function syncControls() {
      const group = $("[data-layers]"), layer = selected();
      group.replaceChildren(...ordered(images()).reverse().map((item, index) => {
        const row = doc.createElement("button"); row.type = "button"; row.dataset.layer = item.id;
        row.setAttribute("aria-pressed", String(item.id === selection));
        row.textContent = `${item.visible === false ? "숨김 · " : ""}${item.name || `레이어 ${index + 1}`}`;
        return row;
      }));
      for (const field of fields) {
        const key = field.dataset.field;
        field.disabled = !layer || stale || !!pending;
        if (key === "visible") field.checked = !!layer && layer.visible !== false;
        else field.value = layer ? finite(layer[key], ["scaleX", "scaleY", "opacity"].includes(key) ? 1 : 0) * (key === "opacity" ? 100 : 1) : "";
      }
      for (const name of ["up", "down", "copy", "delete"]) $(`[data-${name}]`).disabled = !layer || stale || !!pending;
      $("[data-undo]").disabled = !history.length || stale || !!pending;
      $("[data-redo]").disabled = !redo.length || stale || !!pending;
    }
    function redraw() {
      if (frame !== null) return;
      frame = win.requestAnimationFrame(() => { frame = null; void paint(); });
    }
    function checkpoint() {
      history.push(structuredClone(scene)); if (history.length > 24) history.shift(); redo.length = 0;
    }
    function mutate(change) {
      if (stale || pending) return;
      checkpoint(); change(); syncControls(); redraw();
    }
    function reorder(direction) {
      const layers = ordered(images()), index = layers.findIndex(layer => layer.id === selection), target = index + direction;
      if (index < 0 || target < 0 || target >= layers.length) return;
      mutate(() => { [layers[index], layers[target]] = [layers[target], layers[index]];
        layers.forEach((layer, position) => { layer.order = position + 1; }); scene.images = layers; });
    }
    function restore(stack, destination) {
      if (!stack.length || stale || pending) return;
      destination.push(scene); scene = stack.pop(); syncControls(); redraw();
    }
    $("[data-layers]").addEventListener("click", event => {
      const row = event.target.closest("[data-layer]"); if (row) { selection = row.dataset.layer; syncControls(); }
    });
    for (const field of fields) field.addEventListener("change", () => {
      const layer = selected(), key = field.dataset.field;
      if (!layer || (key !== "visible" && !Number.isFinite(field.valueAsNumber))) return;
      mutate(() => { layer[key] = key === "visible" ? field.checked : key === "opacity"
        ? Math.min(1, Math.max(0, field.valueAsNumber / 100)) : field.valueAsNumber; });
    });
    $("[data-up]").onclick = () => reorder(1); $("[data-down]").onclick = () => reorder(-1);
    $("[data-delete]").onclick = () => mutate(() => { scene.images = images().filter(layer => layer.id !== selection); selection = ""; });
    $("[data-copy]").onclick = () => mutate(() => {
      const layer = structuredClone(selected()); layer.id = requestId(container); layer.order = Math.max(0, ...images().map(item => finite(item.order))) + 1;
      scene.images.push(layer); selection = layer.id;
    });
    $("[data-undo]").onclick = () => restore(history, redo); $("[data-redo]").onclick = () => restore(redo, history);
    modal.addEventListener("keydown", event => {
      event.stopPropagation();
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.target.matches("input")) {
        event.preventDefault();
        if (event.shiftKey) restore(redo, history); else restore(history, redo);
      }
    });
    $("[data-zoom-in]").onclick = () => { zoom = Math.min(zoom * 1.25, 5); fit(); };
    $("[data-zoom-out]").onclick = () => { zoom = Math.max(zoom / 1.25, .25); fit(); };
    $("[data-zoom-fit]").onclick = () => { zoom = 1; fit(); };
    function point(event) {
      const rect = canvas.getBoundingClientRect();
      return [(event.clientX - rect.left) * width / rect.width, (event.clientY - rect.top) * height / rect.height];
    }
    function hit(x, y) {
      return ordered(images()).reverse().find(layer => {
        const angle = -finite(layer.rotation) * Math.PI / 180, dx = x - finite(layer.x), dy = y - finite(layer.y);
        const u = (dx * Math.cos(angle) - dy * Math.sin(angle)) / finite(layer.scaleX, 1);
        const v = (dx * Math.sin(angle) + dy * Math.cos(angle)) / finite(layer.scaleY, 1);
        return layer.visible !== false && Math.abs(u) <= finite(layer.width) / 2 && Math.abs(v) <= finite(layer.height) / 2;
      });
    }
    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0 || stale || pending) return;
      const [x, y] = point(event), tool = $("[data-tool]").value;
      const layer = tool === "move" ? hit(x, y) : null;
      if (tool === "move" && !layer) return;
      checkpoint();
      if (layer) { selection = layer.id; gesture = {x, y, layer, startX: finite(layer.x), startY: finite(layer.y)}; }
      else {
        const line = {points:[x, y], stroke:$("[data-color]").value, strokeWidth:Math.max(1, Math.min(300, finite($("[data-brush-size]").value, 18))),
          globalCompositeOperation: tool === "erase" ? "destination-out" : "source-over"};
        (scene.lines ??= []).push(line); gesture = {line};
      }
      canvas.setPointerCapture(event.pointerId); syncControls(); redraw();
    });
    canvas.addEventListener("pointermove", event => {
      if (!gesture || stale || !canvas.hasPointerCapture(event.pointerId)) return;
      const [x, y] = point(event);
      if (gesture.layer) { gesture.layer.x = gesture.startX + x - gesture.x; gesture.layer.y = gesture.startY + y - gesture.y; }
      else gesture.line.points.push(x, y);
      redraw();
    });
    canvas.addEventListener("lostpointercapture", () => { gesture = null; syncControls(); redraw(); });
    apply.onclick = async () => {
      if (stale || pending || gesture || latest.disabled) return;
      const commit = new Date().toISOString(); pending = commit; syncControls(); message("PNG 저장 확인 중…");
      try {
        if (frame !== null) { win.cancelAnimationFrame(frame); frame = null; }
        if (!(await paint()) || closed || stale) throw Error("현재 장면을 출력할 수 없습니다.");
        const png = canvas.toDataURL("image/png");
        if (!png.startsWith("data:image/png;base64,")) throw Error("PNG를 만들 수 없습니다.");
        const payload = {...draft, value:png, meta:{...meta, hmb_editor:EDITOR_SCHEMA,
          konva_json:structuredClone(scene), created_at:commit, preview_url:png}};
        saveDeadline = win.setTimeout(() => {
          if (pending !== commit || closed) return;
          stale = true; syncControls(); message("저장 응답을 받지 못했습니다. 노드의 Apply 상태를 확인하세요.", true);
        }, 60_000);
        const response = await latest.onChange(payload);
        if (response?.success === false || response?.succeeded === false) throw Error("엔진에서 Apply 요청을 받지 못했습니다.");
      } catch (error) {
        if (!closed && pending === commit) {
          win.clearTimeout(saveDeadline); pending = ""; syncControls(); redraw(); message(error.message || "Apply 요청을 전송할 수 없습니다.", true);
        }
      }
    };
    reconcile = (project, authority) => {
      const next = project?.meta;
      if (pending && next?.hmb_image_bash?.apply?.editor_commit === pending && next.hmb_image_bash.apply.output_path) {
        win.clearTimeout(saveDeadline); pending = ""; stale = false;
        draft = structuredClone(project); meta = draft.meta; snapshot = meta.hmb_image_bash.editor_snapshot_id;
        scene = structuredClone(meta.konva_json); syncControls(); redraw(); message("PNG 저장 완료"); return;
      }
      if (next?.hmb_image_bash?.editor_snapshot_id !== snapshot && !(pending && next?.created_at === pending)) {
        stale = true; apply.disabled = true; syncControls(); message("연결 또는 장면이 바뀌었습니다. 편집기를 다시 열어 주세요.", true);
      } else if (pending && authority.preparation?.phase === "error") {
        win.clearTimeout(saveDeadline); stale = true; apply.disabled = true; syncControls();
        message(authority.preparation.error || "PNG 저장에 실패했습니다. 노드 상태를 확인하세요.", true);
      }
    };
    const observer = new win.ResizeObserver(fit); observer.observe(view);
    modal.querySelectorAll("[data-close]").forEach(close => { close.onclick = () => modal.close(); });
    modal.addEventListener("close", () => {
      closed = true; observer.disconnect(); win.clearTimeout(saveDeadline);
      if (frame !== null) win.cancelAnimationFrame(frame);
      modal.remove(); if (dialog === modal) { dialog = null; reconcile = null; }
    }, {once:true});
    doc.body.append(modal); dialog = modal; modal.showModal();
    selection = ordered(images()).at(-1)?.id || "";
    fit(); syncControls(); void paint();
  }

  button.onclick = open; update(props);
  return {update, cleanup() { dialog?.close(); button.remove(); }};
}

// HMB_NATIVE_STOCK_SAFETY_V1_BEGIN
// Public DOM capture only. Never inspect React internals, replay Delete, or
// pretend a disk/Git update installed the native editor safety contract.
function hmbAcquireNativeStockSafety(container) {
  const doc = container?.ownerDocument, win = doc?.defaultView;
  if (!doc?.documentElement || !win?.addEventListener || !doc.createElement) return null;
  const key = "__HMB_NATIVE_STOCK_SAFETY_V1__";
  let shared = doc[key];
  if (!shared) {
    const owners = new Set(), identities = new Map();
    let contextNode = null, notice = null, noticeTimer = null, disposed = false;
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

export default function HMBImageBashWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
