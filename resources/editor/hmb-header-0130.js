const hmb130PassiveHeaders = new Set([
  "HMBColorLUTLibrary", "HMBFinishLookLibrary", "HMBImageAssetLibrary",
  "HMBSoundLibrary", "HMBVideoPickerLibrary",
]);

function hmb130HeaderItems(nodeType, library, nativeItems) {
  if (library !== "HMB_GP_Production") return nativeItems || ["lock", "run", "startFlow"];
  return hmb130PassiveHeaders.has(nodeType) ? ["lock", "reset"] : ["lock", "reset", "run"];
}

const hmb130PendingRefreshes = new Map();
async function hmb130RefreshConnections(nodeName) {
  const epoch = hmbNativeStudioFlowEpoch;
  if (hmb130PendingRefreshes.get(nodeName) === epoch) return;
  hmb130PendingRefreshes.set(nodeName, epoch);
  try {
    const node = {node_name: nodeName};
    const status = hmbNativeConnectionSnapshot(await hmb130ConnectionRequest(
      "HMBGetNodeConnectionsRequest", node, {timeoutMs:10000}), nodeName);
    if (epoch !== hmbNativeStudioFlowEpoch) return;
    if (status.detached || !status.can_refresh) {
      hmbNativeOpenConnections(nodeName);
      return;
    }
    const refreshed = hmbNativeConnectionSnapshot(await hmb130ConnectionRequest(
      "HMBManageNodeConnectionsRequest", {...node, operation:"refresh", expected_state_token:status.state_token},
      {timeoutMs:10000}), nodeName);
    if (epoch !== hmbNativeStudioFlowEpoch) return;
    if (refreshed.altered_workflow_state === true) hmbNativeConnectionDirty();
    if (refreshed.refresh_confirmed === true) z.success("연결 다시 적용 완료");
    else hmbNativeOpenConnections(nodeName);
  } catch (error) {
    if (epoch === hmbNativeStudioFlowEpoch) z.error("연결을 다시 적용하지 못했습니다", {description:hmb130ConnectionError(error)});
  } finally {
    if (hmb130PendingRefreshes.get(nodeName) === epoch) hmb130PendingRefreshes.delete(nodeName);
  }
}

const hmb130HeaderWidget = "[data-hmb-color-lut-widget]";
const hmb130HeaderSlots = "[data-hmb-native-identity],[data-hmb-native-actions]";

function hmb130ReadHeaderSlots(container, node, nodeType) {
  if (!container?.matches(hmb130HeaderWidget) || container.closest(".react-flow__node") !== node) return null;
  const declared = container.getAttribute("data-hmb-native-node-type");
  if (declared !== nodeType && !(declared === null && nodeType === "HMBColorLUTLibrary")) return null;
  const identity = container.querySelector("[data-hmb-native-identity]");
  const actions = container.querySelector("[data-hmb-native-actions]");
  if (!identity || !actions || !container.getClientRects().length) return null;
  const view = node.ownerDocument.defaultView;
  for (let parent = container; parent && parent !== node; parent = parent.parentElement) {
    const style = view.getComputedStyle(parent);
    if (style.display === "none" || style.visibility !== "visible" || Number(style.opacity) === 0) return null;
  }
  let surface = identity.parentElement;
  while (surface && !surface.contains(actions)) surface = surface.parentElement;
  return {container, identity, actions, surface, node};
}

function hmbUse130IntegratedHeader(host, nodeName, nodeType, library, collapsed, artwork) {
  const [slots, setSlots] = Y.useState(null);
  Y.useLayoutEffect(() => {
    const node = host.current?.closest(".react-flow__node");
    if (library !== "HMB_GP_Production" || collapsed || node?.getAttribute("data-id") !== nodeName) return;
    const doc = node.ownerDocument, view = doc.defaultView;
    let active, frame = null, retired = null;
    const discover = () => {
      frame = null;
      const candidate = [...node.querySelectorAll(hmb130HeaderWidget)]
        .filter(container => container !== retired)
        .map(container => hmb130ReadHeaderSlots(container, node, nodeType)).find(Boolean) || null;
      if (candidate === active || (candidate && active && candidate.container === active.container
          && candidate.identity === active.identity && candidate.actions === active.actions)) return;
      active = candidate;
      setSlots(candidate);
    };
    const schedule = () => { if (frame === null) frame = view.requestAnimationFrame(discover); };
    const ready = event => {
      const container = event.detail?.container;
      if (container?.closest?.(".react-flow__node") !== node) return;
      if (retired === container) retired = null;
      schedule();
    };
    const retire = event => {
      if (event.detail?.container !== active?.container || !active) return;
      retired = active.container; active = null; setSlots(null); schedule();
    };
    const selector = `${hmb130HeaderWidget},${hmb130HeaderSlots}`;
    const containsSlot = element => element.nodeType === 1 && (element.matches(selector) || element.querySelector(selector));
    const observer = new view.MutationObserver(changes => {
      if (changes.some(change => change.type === "attributes"
        ? change.target === node || (active?.container && change.target.contains(active.container))
        : [...change.addedNodes, ...change.removedNodes].some(containsSlot))) schedule();
    });
    observer.observe(node, {childList:true, subtree:true, attributes:true,
      attributeFilter:["hidden", "style", "class", "data-hmb-color-lut-widget", "data-hmb-native-node-type"]});
    doc.addEventListener("hmb-color-lut-header-ready", ready);
    doc.addEventListener("hmb-color-lut-header-retire", retire);
    discover();
    return () => {
      observer.disconnect(); if (frame !== null) view.cancelAnimationFrame(frame);
      doc.removeEventListener("hmb-color-lut-header-ready", ready);
      doc.removeEventListener("hmb-color-lut-header-retire", retire);
    };
  }, [host, nodeName, nodeType, library, collapsed]);

  const current = library === "HMB_GP_Production" && !collapsed && slots?.node.isConnected
    && slots.node.getAttribute("data-id") === nodeName && slots.container.isConnected
    && slots.identity.isConnected && slots.actions.isConnected ? slots : null;
  Y.useLayoutEffect(() => {
    if (!current) {
      const clearArt = artwork?.(host.current);
      return typeof clearArt === "function" ? clearArt : undefined;
    }
    const {container, surface, node} = current, view = node.ownerDocument.defaultView;
    const notify = active => container.dispatchEvent(new view.CustomEvent("hmb-color-lut-header-state", {detail:{active}}));
    notify(true);
    node.setAttribute("data-hmb-0130-integrated-header", "true");
    const clearArt = surface && artwork?.(surface);
    return () => {
      notify(false);
      node.removeAttribute("data-hmb-0130-integrated-header");
      if (typeof clearArt === "function") clearArt();
    };
  }, [current, artwork, host]);
  return current;
}

function hmb130IntegratedHeader(slots, header) {
  if (!slots) return header;
  const [identity, actions] = header.props.children;
  const style = Object.fromEntries(Object.entries(header.props.style || {}).filter(([key]) => key.startsWith("--")));
  return Y.cloneElement(header, {hidden:true, "aria-hidden":true, style:{display:"none"}, onDoubleClick:undefined,
    children:[
      Cm.createPortal(Z.jsx("div", {className:"flex items-center min-w-0 group", style, children:identity}), slots.identity, "hmb-identity"),
      Cm.createPortal(Z.jsx("div", {className:"flex items-center nodrag", style, children:actions}), slots.actions, "hmb-actions"),
    ]});
}
