let hmbQueuedBasket = null;

function hmbWaitForBasket(workflow, timeoutMs = 30000) {
  if (hmbQueuedBasket !== workflow) return Promise.resolve(true);
  return new Promise(resolve => {
    const finish = opened => {
      clearTimeout(timeout);
      window.removeEventListener("hmb-rodong-mart-basket-opened", onOpened);
      resolve(opened);
    };
    const onOpened = () => {
      if (hmbQueuedBasket !== workflow) finish(true);
    };
    const timeout = setTimeout(() => finish(false), timeoutMs);
    window.addEventListener("hmb-rodong-mart-basket-opened", onOpened);
  });
}

function hmbMartStartup({onDismiss, onEnter}) {
  const host = Y.useRef(null), latest = Y.useRef(null);
  latest.current = {onDismiss, onEnter};
  Y.useLayoutEffect(() => window.__hmbMountRodongMartStartup({
    host: host.current,
    onDismiss: () => latest.current.onDismiss(),
    onEnter: () => latest.current.onEnter(),
  }), []);
  return Z.jsx("div", {ref:host});
}

function hmbUseMartStartup(openWorkflows, connection, workflowsOpen, workflow, closeWorkflows) {
  const phase = Y.useRef("fresh");
  const [visible, setVisible] = Y.useState(false);
  const [entering, setEntering] = Y.useState(false);
  const createdWorkflow = Y.useRef(null);
  const show = Y.useCallback(() => {
    if (phase.current !== "fresh") return;
    phase.current = "visible";
    setVisible(true);
  }, []);
  Y.useEffect(() => {
    if (connection === "connected" && workflowsOpen && !workflow) show();
  }, [connection, workflowsOpen, workflow, show]);
  const complete = Y.useCallback(() => {
    phase.current = "done";
    createdWorkflow.current = null;
    setEntering(false);
    setVisible(false);
  }, []);
  const dismiss = () => {
    if (hmbQueuedBasket === createdWorkflow.current) hmbQueuedBasket = null;
    complete();
    openWorkflows();
  };
  const enter = async create => {
    setEntering(true);
    try {
      let name = createdWorkflow.current;
      if (!name) {
        name = await create(created => {
          createdWorkflow.current = created;
          hmbQueuedBasket = created;
          closeWorkflows();
        });
      }
      return Boolean(name && await hmbWaitForBasket(name));
    } finally {
      setEntering(false);
    }
  };
  Y.useEffect(() => {
    window.addEventListener("hmb-rodong-mart-basket-opened", complete);
    return () => window.removeEventListener("hmb-rodong-mart-basket-opened", complete);
  }, [complete]);
  Y.useEffect(() => {
    if (connection !== "connected") return;
    void yn.request("HMBShotBasketRequest", {
      action:"status", payload:{flow_name:"", workflow_name:"", prewarm:true},
    }, {timeoutMs:5000}).catch(() => {});
  }, [connection]);
  const reopen = () => {
    phase.current = "fresh";
    show();
  };
  return {visible, entering, awaitingWorkflow: createdWorkflow.current === workflow && Boolean(workflow), show, dismiss, enter, reopen};
}

let hmbNativeStudioFlowEpoch = 0;
let hmb130CanvasScope = null;

function hmb130SoundScope() {
  return hmb130CanvasScope?.workflow_name === fO.getState().workflowName ? hmb130CanvasScope : null;
}

function hmb130HeaderArtwork(nodeName, library) {
  return Y.useMemo(() => {
    if (library !== "HMB_GP_Production") return undefined;
    let card;
    return header => {
      if (!header) return;
      const artwork = window.__hmbRodongMartHeaderArt;
      if (!artwork) return;
      card ??= artwork.next();
      return artwork.mount(header, card, true);
    };
  }, [nodeName, library]);
}

function hmb130ConnectionRequest(type, payload, options) {
  return yn.request(type, payload, options);
}

function hmb130SessionId() {
  return yn.getSessionId?.();
}

window.__hmbReadImageAssetAuthority0130 = async (nodeName, value, timeoutMs) => {
  const result = await yn.request("SetParameterValueRequest", {
    node_name: nodeName,
    parameter_name: "HMB_IMAGE_ASSET_THUMBNAIL_PATCH",
    value,
  }, {timeoutMs});
  return result.finalized_value;
};

function hmb130ConnectionError(reason) {
  return reason?.result_details || reason?.message || String(reason);
}

const hmb130NodeTypes = new Set([
  "HMBAgentLibrary", "HMBAnalysisAgent", "HMBColorLUTLibrary", "HMBFinishLookLibrary",
  "HMBImageAssetLibrary", "HMBImageBash", "HMBImageGeneration", "HMBPromptLibrary",
  "HMBSeedanceGeneration", "HMBSoundLibrary", "HMBVideoPickerLibrary",
]);

function hmb130Library(node) {
  if (node?.metadata?.library === "HMB_GP_Production" || node?.node_category === "HMB_GP_Production"
      || hmb130NodeTypes.has(node?.node_type)) return "HMB_GP_Production";
  return "";
}

const hmb130PendingDeletes = new Map();

function hmb130GuardRemovals(changes, nodes, apply) {
  const removals = changes.filter(change => change.type === "remove");
  if (!removals.length) {
    apply(changes);
    return;
  }
  const byName = new Map(nodes.map(node => [node.id, node]));
  const containsHmb = nodes.some(node => hmb130Library(node.data));
  if (!removals.some(change => {
    const node = byName.get(change.id);
    return node && (hmb130Library(node.data) || (containsHmb && $D(node)));
  })) {
    apply(changes);
    return;
  }
  const other = changes.filter(change => change.type !== "remove");
  if (other.length) apply(other);
  const names = [...new Set(removals.map(change => change.id))];
  if (names.some(name => hmb130PendingDeletes.has(name))) return;
  const epoch = hmbNativeStudioFlowEpoch, operation = {};
  names.forEach(name => hmb130PendingDeletes.set(name, operation));
  void (async () => {
    try {
      const result = await yn.request("HMBCheckNodeDeletionRequest", {node_names: names}, {timeoutMs: 10000});
      if (epoch !== hmbNativeStudioFlowEpoch) return;
      if (result.protection_ready !== true || result.protection_version !== 2) {
        throw new Error(result.readiness_error || "현재 엔진에서 연결 상태를 확인할 수 없습니다.");
      }
      if (result.can_delete !== true) {
        z.warning("연결된 노드를 삭제할 수 없습니다", {
          description: result.message || "연결 상태를 확인하세요.",
          action: {label: "연결 관리", onClick: () => {
            if (epoch === hmbNativeStudioFlowEpoch) hmbNativeOpenConnections(Object.keys(result.blocked || {}));
          }},
        });
        return;
      }
      if (!Array.isArray(result.hmb_node_names) || !result.check_token) {
        throw new Error("삭제 확인 응답이 올바르지 않습니다.");
      }
      const guarded = new Set(result.hmb_node_names);
      for (const name of names) {
        if (hmb130Library(byName.get(name)?.data)) guarded.add(name);
      }
      for (const name of names) {
        if (epoch !== hmbNativeStudioFlowEpoch) return;
        if (guarded.has(name)) {
          // The native success event removes the node and its edges. Keep the
          // editor state intact if a new connection blocks the final delete.
          await yn.request("HMBDeleteCheckedNodeRequest", {
            node_name: name, check_token: result.check_token,
          }, {timeoutMs: 10000});
        }
      }
      if (epoch === hmbNativeStudioFlowEpoch) {
        const ordinary = removals.filter(change => !guarded.has(change.id));
        if (ordinary.length) apply(ordinary);
      }
    } catch (error) {
      if (epoch === hmbNativeStudioFlowEpoch) {
        z.warning("노드 삭제를 확인할 수 없습니다", {description: hmb130ConnectionError(error)});
      }
    } finally {
      names.forEach(name => {
        if (hmb130PendingDeletes.get(name) === operation) hmb130PendingDeletes.delete(name);
      });
    }
  })();
}

function Hmb130ConnectionManager({flowName, workflowName}) {
  Y.useLayoutEffect(() => {
    hmbNativeStudioFlowEpoch += 1;
    const scope = workflowName && flowName ? {workflow_name:workflowName, flow_name:flowName} : null;
    hmb130CanvasScope = scope;
    hmb130PendingDeletes.clear();
    document.dispatchEvent(new Event("hmb-native-connection-context-reset"));
    return () => {
      if (hmb130CanvasScope === scope) hmb130CanvasScope = null;
      hmbNativeStudioFlowEpoch += 1;
    };
  }, [flowName, workflowName]);
  Y.useLayoutEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-hmb-native-deletion-guard", "engine-preflight");
    root.setAttribute("data-hmb-native-deletion-protection-version", "2");
    return () => {
      root.removeAttribute("data-hmb-native-deletion-guard");
      root.removeAttribute("data-hmb-native-deletion-protection-version");
    };
  }, []);
  return hmbUseNativeConnectionManager();
}

function hmbMartCanvas({ready, empty, hasBasket, flowName, workflowName, onCreated}) {
  const host = Y.useRef(null), controller = Y.useRef(null), latest = Y.useRef(null);
  latest.current = {ready, empty, hasBasket, flowName, workflowName, onCreated};
  Y.useLayoutEffect(() => {
    controller.current = window.__hmbMountShotBasket({
      host:host.current, context:latest.current,
      request:async (action, payload) => {
        const origin = latest.current;
        const {workflowName, flowName} = origin;
        if (!origin.ready || !workflowName || !flowName) throw Error("작업공간 연결을 확인해 주세요.");
        const result = await yn.request("HMBShotBasketRequest", {
          action, payload:{...payload, flow_name:flowName, workflow_name:workflowName},
        }, {timeoutMs:action === "prepare" || action === "create" ? 90000 : 30000});
        const isCurrent = () => controller.current && fO.getState().workflowName === workflowName
          && latest.current.flowName === flowName;
        if (!isCurrent()) throw Error("작업공간이 변경되었습니다.");
        const data = result?.data;
        if (!data || typeof data !== "object") throw Error("샷 바구니 응답을 확인할 수 없습니다.");
        if (data.changed || data.accepted_pending) fO.getState().setIsSaved(false);
        if (data.created && data.flow_name === flowName) await origin.onCreated(flowName, isCurrent);
        return data;
      },
    });
    return () => { controller.current?.destroy(); controller.current = null; };
  }, []);
  Y.useLayoutEffect(() => {
    controller.current?.setContext(latest.current);
    if (ready && empty && flowName && workflowName && workflowName === hmbQueuedBasket
        && controller.current?.open([], true)) {
      hmbQueuedBasket = null;
      window.dispatchEvent(new Event("hmb-rodong-mart-basket-opened"));
    }
  });
  return Z.jsxs(Z.Fragment, {children:[
    Z.jsx("div", {ref:host, style:{position:"absolute",inset:0,zIndex:20,pointerEvents:"none"}}),
    Z.jsx(Hmb130ConnectionManager, {flowName, workflowName}),
  ]});
}
