// Small HMB companion header. The stock bash_image button owns the editor.
export const HMB_IMAGE_BASH_HEADER_SCHEMA = "hmb-image-bash-header-v1";
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
    locked: raw.locked === true, route: hmbImageBashHeaderRoute(valid ? raw.route : {}) };
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
</style><div class="hmb-image-bash-header nodrag" data-hmb-image-bash-header>
  <div class="hmb-image-bash-header__row"><span class="hmb-image-bash-header__mark" aria-hidden="true">IB</span>
    <div class="hmb-image-bash-header__identity"><div data-hmb-native-identity></div><div class="hmb-image-bash-header__title">HMBImageBash</div>
      <div class="hmb-image-bash-header__status" data-bash-status role="status" aria-live="polite">${escape(state.status)}</div></div>
    <div data-hmb-native-actions class="nodrag"></div><span class="hmb-image-bash-header__count" data-bash-count>이미지 ${state.image_count}</span>
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
    status.textContent = message || state.status || (state.bound_source ? "이미지 라이브러리 연결됨" : "이미지 라이브러리를 연결하세요");
    status.title = status.textContent; count.textContent = `이미지 ${state.image_count}`;
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
      ...(["bind", "unbind"].includes(operation) ? {source_instance_id: source?.source_instance_id || ""} : {}),
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
      const title = doc.createElement("strong"); title.textContent = "HMB 업데이트 상태 확인이 필요합니다";
      const text = doc.createElement("p");
      text.textContent = "Override 업데이트 로그에서 current/applied 확인 → 작업 저장 → Griptape 완전 종료 → 재시작 후 다시 확인하세요. current/applied는 디스크 파일 상태이며 현재 화면의 통합 상태를 보장하지 않습니다. 실패 또는 상태 확인 불가 시 HMB 업데이트 로그의 원인을 확인하세요. 최신 UI와 엔진 보호가 확인되기 전까지 HMB 노드 삭제를 일시 중단하며, 연결된 노드는 계속 보호됩니다.";
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
      badge.setAttribute("aria-label", "HMB Override 업데이트 및 재시작 안내");
      badge.textContent = "HMB 업데이트 확인 · 안전 삭제 보호 중";
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

export default function HMBImageBashWidget(container, props) {
  return hmbNativeStockSafetyContract(container, props, hmbNativeStockSafetyImplementation);
}
