/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1
 * Inserted into the pinned editor bundle by the guarded local prototype tool.
 * React owns every portalled element; no native element is cloned or proxied.
 */
const hmbNativeStudioTypes = new Set([
  "HMBColorLUTLibrary", "HMBAgentLibrary", "HMBFinishLookLibrary",
  "HMBImageAssetLibrary", "HMBImageBash", "HMBImageGeneration",
  "HMBSeedanceGeneration", "HMBPromptLibrary", "HMBVideoPickerLibrary",
]);
const hmbNativeStudioWidgets = new Set([
  "HMBColorLUTLibraryWidget", "HMBAgentLibraryWidget", "HMBFinishLookLibraryWidget",
  "HMBImageAssetLibraryWidget", "HMBImageBashWidget", "HMBImageGenerationWidget",
  "HMBSeedanceGenerationWidget", "HMBPromptLibraryScopedBindingWidget", "HMBVideoPickerLibraryWidget",
]);
// Existing widgets retain their known UI behavior. New tools must explicitly
// opt in with metadata owned by this library; a name prefix alone is not proof
// that a third-party node supports this host UI contract. A new widget also
// supplies [data-hmb-color-lut-widget], its node-type marker, the identity/action
// slots and the existing header-ready/header-retire lifecycle events.
function hmbNativeStudioDeclaredContract(metadata) {
  const contract = metadata?.hmb_native_studio_ui;
  return metadata?.library === "HMB_GP_Production" && contract?.schema === "hmb-native-studio-ui"
    && contract?.version === 1 && typeof contract.node_type === "string" && !!contract.node_type
    && typeof contract.widget === "string" && !!contract.widget ? contract : null;
}
const hmbIsNativeStudioType = (nodeType, metadata = null) => typeof nodeType === "string"
  && (hmbNativeStudioTypes.has(nodeType) || hmbNativeStudioDeclaredContract(metadata)?.node_type === nodeType);
const hmbIsNativeStudioWidget = (widgetName, metadata = null) => typeof widgetName === "string"
  && (hmbNativeStudioWidgets.has(widgetName) || hmbNativeStudioDeclaredContract(metadata)?.widget === widgetName);
const hmbNativeStudioCollapsedWidth = 320;
const hmbNativeStudioCollapsedHeight = 64;
const hmbNativeStudioViewMemory = new WeakMap();
const hmbNativeStudioRestoredViews = new WeakSet();
const hmbNativeStudioCompactDispatching = new WeakSet();
const hmbNativeStudioCollapseControllers = new WeakMap();
let hmbNativeStudioFlowEpoch = 0;
const hmbNativeDeletionPending = new Map();
const hmbNativeConnectionLibrary = "HMB_GP_Production";
const hmbNativeConnectionNotices = new Map();
function hmbNativeConnectionManaged(library) { return library === hmbNativeConnectionLibrary; }
function hmbNativeOpenConnections(nodeNames) {
  const names = [...new Set((Array.isArray(nodeNames) ? nodeNames : [nodeNames])
    .filter(name => typeof name === "string" && name.trim()))];
  if (!names.length || typeof document === "undefined") return;
  document.dispatchEvent(new CustomEvent("hmb-native-open-connections", {
    detail: { names, epoch: hmbNativeStudioFlowEpoch },
  }));
}
function hmbNativeOpenBlockedConnections(nodeNames) {
  const epoch = hmbNativeStudioFlowEpoch;
  Promise.resolve().then(() => Xd.request("HMBCheckNodeDeletionRequest", { node_names: nodeNames }))
    .then(result => {
      if (epoch !== hmbNativeStudioFlowEpoch) return;
      const names = Object.keys(result?.blocked || {});
      // A refused standard group may own HMB children. Only the engine's
      // actual blocked HMB keys are connection-manager targets.
      if (names.length) hmbNativeOpenConnections(names);
      else ig.warning("연결 상태가 변경되었습니다", { description: "현재 연결을 다시 확인해 주세요." });
    }).catch(reason => {
      if (epoch === hmbNativeStudioFlowEpoch) ig.error("연결을 확인할 수 없습니다", { description: vg(reason) });
    });
}
function hmbNativeConnectionDeletionNotice(request, message) {
  if (typeof message !== "string" || !message.includes("HMB_DELETE_CONNECTED")) return false;
  const names = typeof request?.node_name === "string" ? [request.node_name]
    : Array.isArray(request?.node_names) ? request.node_names : [];
  if (!names.length) return false;
  const epoch = hmbNativeStudioFlowEpoch;
  const key = `${epoch}:${names.join("\n")}:${message}`;
  if ((hmbNativeConnectionNotices.get(key) || 0) + 1000 < Date.now()) {
    hmbNativeConnectionNotices.clear(); hmbNativeConnectionNotices.set(key, Date.now());
    ig.warning(request?.request_type === "ResetNodeToDefaultsRequest" ? "초기화할 수 없습니다" : "삭제할 수 없습니다", { description: message, duration: 6000,
      action: { label: "연결 관리", onClick: () => {
        if (epoch === hmbNativeStudioFlowEpoch) hmbNativeOpenBlockedConnections(names);
      } } });
  }
  return true;
}
function hmbNativeConnectionActions(nodeName, library, actions, className, style) {
  if (!hmbNativeConnectionManaged(library) || !actions) return actions;
  const stop = event => event.stopPropagation();
  const button = (0, R.jsx)("button", { type: "button", "data-hmb-connection-manager-button": nodeName,
    className: `${className || ""} nodrag`, title: "연결 관리", "aria-label": `연결 관리 · ${nodeName}`,
    onPointerDown: stop, onDoubleClick: stop,
    onClick: event => { event.preventDefault(); event.stopPropagation(); hmbNativeOpenConnections(nodeName); },
    style: { ...style, width: 24, height: 24, padding: 3, display: "inline-flex", alignItems: "center",
      justifyContent: "center", flexShrink: 0, alignSelf: "center", cursor: "pointer" },
    children: (0, R.jsxs)("svg", { viewBox: "0 0 24 24", width: 17, height: 17, fill: "none",
      stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
      children: [(0, R.jsx)("path", { d: "M10 13a5 5 0 0 0 7.1 0l3-3a5 5 0 0 0-7.1-7.1l-1.7 1.7" }),
        (0, R.jsx)("path", { d: "M14 11a5 5 0 0 0-7.1 0l-3 3a5 5 0 0 0 7.1 7.1l1.7-1.7" })] }) }, "hmb-manage-connections");
  return (0, S.cloneElement)(actions, { children: [button, actions.props.children] });
}
function hmbNativeConnectionMenu(props, nativeItems) {
  const node = props.hmbConnectionNode;
  if (!hmbNativeConnectionManaged(node?.data?.metadata?.library)) return nativeItems;
  return (0, R.jsxs)(R.Fragment, { children: [(0, R.jsxs)("button", {
    type: "button", className: H8, "data-hmb-context-connections": node.id,
    onClick: event => { event.preventDefault(); event.stopPropagation();
      props.hmbClose?.(); hmbNativeOpenConnections(node.id); },
    children: [(0, R.jsx)("span", { className: U8, "aria-hidden": true, children: "↔" }),
      (0, R.jsx)("span", { className: W8, children: "연결 관리" })],
  }, "hmb-context-connections"), nativeItems] });
}
function hmbNativeConnectionSnapshot(value, nodeName) {
  if (!value || value.node_name !== nodeName || typeof value.state_token !== "string" || !value.state_token
    || typeof value.detached !== "boolean" || typeof value.can_disconnect !== "boolean"
    || typeof value.can_reconnect !== "boolean" || !Array.isArray(value.connections)
    || (value.can_forget_missing !== undefined && typeof value.can_forget_missing !== "boolean")) {
    throw Error("연결 목록을 확인할 수 없습니다. 새로고침해 주세요.");
  }
  for (const row of value.connections) {
    if (!row || !["wire", "remote"].includes(row.kind)
      || ["peer_name", "source_node_name", "target_node_name"].some(key => typeof row[key] !== "string")
      || !Array.isArray(row.shots)) throw Error("연결 목록 형식이 올바르지 않습니다.");
    for (const shot of row.shots) {
      if (!shot || typeof shot.name !== "string" || typeof shot.shot_uuid !== "string"
        || typeof shot.channel_uuid !== "string") throw Error("샷 연결 목록 형식이 올바르지 않습니다.");
    }
  }
  return value;
}
const hmbNativeConnectionElement = (tag, props, ...children) =>
  (0, R.jsx)(tag, { ...props, children: children.length === 1 ? children[0] : children });
function hmbUseNativeConnectionManager() {
  const [view, setView] = (0, S.useState)(null);
  const [snapshot, setSnapshot] = (0, S.useState)(null);
  const [busy, setBusy] = (0, S.useState)(false);
  const [error, setError] = (0, S.useState)("");
  const sequence = (0, S.useRef)(0), pending = (0, S.useRef)(false), dialog = (0, S.useRef)(null);
  const close = () => { sequence.current += 1; pending.current = false; setView(null); };
  (0, S.useEffect)(() => {
    const open = event => {
      const detail = event.detail;
      if (detail?.epoch !== hmbNativeStudioFlowEpoch || !Array.isArray(detail.names) || !detail.names.length) return;
      const names = detail.names.filter(name => typeof name === "string" && name.trim());
      if (!names.length) return;
      setView(previous => previous?.epoch === detail.epoch && previous.nodeName === names[0]
        && previous.names.join("\n") === names.join("\n") ? previous
        : { names, nodeName: names[0], epoch: detail.epoch, nonce: 0, returnFocus: document.activeElement });
    };
    const reset = () => { sequence.current += 1; pending.current = false; setView(null); };
    document.addEventListener("hmb-native-open-connections", open);
    document.addEventListener("hmb-native-connection-context-reset", reset);
    return () => { sequence.current += 1; pending.current = false;
      document.removeEventListener("hmb-native-open-connections", open);
      document.removeEventListener("hmb-native-connection-context-reset", reset); };
  }, []);
  (0, S.useEffect)(() => {
    if (!view) { setSnapshot(null); setBusy(false); setError(""); return; }
    const current = ++sequence.current; let cancelled = false;
    pending.current = true; setBusy(true); setError(""); setSnapshot(null);
    Promise.resolve().then(() => Xd.request("HMBGetNodeConnectionsRequest", { node_name: view.nodeName }))
      .then(value => {
        if (cancelled || current !== sequence.current || view.epoch !== hmbNativeStudioFlowEpoch) return;
        setSnapshot(hmbNativeConnectionSnapshot(value, view.nodeName));
      }).catch(reason => {
        if (!cancelled && current === sequence.current && view.epoch === hmbNativeStudioFlowEpoch) setError(vg(reason));
      }).finally(() => {
        if (!cancelled && current === sequence.current) { pending.current = false; setBusy(false); }
      });
    return () => { cancelled = true;
      if (current === sequence.current) { sequence.current += 1; pending.current = false; } };
  }, [view]);
  (0, S.useLayoutEffect)(() => {
    if (!view) return;
    dialog.current?.focus();
    const target = view.returnFocus;
    return () => { if (target?.isConnected) target.focus?.({ preventScroll: true }); };
  }, [view?.nodeName]);
  (0, S.useLayoutEffect)(() => {
    if (!view || !dialog.current) return;
    const focused = document.activeElement;
    // A capability-only action may disappear after a successful reply.
    // Keep Escape/Tab in this modal when its removed button lost focus.
    if (!focused || focused === document.body || !focused.isConnected) dialog.current.focus();
  }, [view?.nodeName, snapshot, busy]);
  const manage = operation => {
    if (!view || !snapshot || pending.current || busy || view.epoch !== hmbNativeStudioFlowEpoch
      || !(operation === "disconnect" ? snapshot.can_disconnect : operation === "reconnect" ? snapshot.can_reconnect
        : operation === "forget_missing" && snapshot.can_forget_missing === true)) return;
    const current = ++sequence.current; pending.current = true; setBusy(true); setError("");
    Promise.resolve().then(() => Xd.request("HMBManageNodeConnectionsRequest", {
      node_name: view.nodeName, operation, expected_state_token: snapshot.state_token,
    })).then(value => {
      if (view.epoch !== hmbNativeStudioFlowEpoch) return;
      const accepted = hmbNativeConnectionSnapshot(value, view.nodeName);
      // A committed action still needs saving when its dialog was dismissed
      // while awaiting the engine. It never reopens that dismissed dialog.
      if (typeof kq !== "undefined") kq.getState().setDirty(true);
      if (current === sequence.current) setSnapshot(accepted);
    }).catch(reason => {
      if (current === sequence.current && view.epoch === hmbNativeStudioFlowEpoch) {
        setError(vg(reason)); setSnapshot(null);
      }
    }).finally(() => {
      if (current === sequence.current) { pending.current = false; setBusy(false); }
    });
  };
  if (!view || view.epoch !== hmbNativeStudioFlowEpoch) return null;
  const el = hmbNativeConnectionElement;
  const button = { border: "1px solid #465166", borderRadius: 7, padding: "7px 12px", color: "inherit",
    background: "#202938", font: "inherit", cursor: "pointer", whiteSpace: "nowrap" };
  const actionStyle = disabled => ({ ...button, opacity: disabled ? 0.45 : 1, cursor: disabled ? "default" : "pointer" });
  const onKeyDown = event => {
    event.stopPropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key === "Tab") {
      const controls = [...(dialog.current?.querySelectorAll("button:not(:disabled),select:not(:disabled),[tabindex='0']") || [])];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  };
  return (0, T.createPortal)(el("div", {
    "data-hmb-connection-manager-overlay": true, className: "nodrag nopan nowheel",
    onPointerDown: event => event.stopPropagation(), onWheel: event => event.stopPropagation(), onKeyDown,
    onClick: event => { if (event.target === event.currentTarget) close(); },
    style: { position: "fixed", inset: 0, zIndex: 10000, background: "#020611aa", display: "grid", placeItems: "center", padding: 24 },
  }, el("section", { ref: dialog, role: "dialog", "aria-modal": true, "aria-labelledby": "hmb-connection-manager-title", tabIndex: -1,
    "data-hmb-connection-manager": view.nodeName,
    style: { width: "min(760px,calc(100vw - 48px))", maxHeight: "calc(100vh - 48px)", boxSizing: "border-box", display: "flex", flexDirection: "column",
      background: "#101725", color: "#e3e8f0", border: "1px solid #52617b", borderRadius: 14,
      boxShadow: "0 20px 90px #0009", font: '14px "Segoe UI",sans-serif', overflow: "hidden", outline: "none" },
  }, el("header", { style: { display: "flex", alignItems: "center", gap: 12, padding: 18, borderBottom: "1px solid #313c50" } },
    el("strong", { id: "hmb-connection-manager-title", style: { flex: 1, minWidth: 0, overflowWrap: "anywhere", fontSize: 17 } }, `연결 관리 · ${view.nodeName}`),
    el("button", { type: "button", style: button, onClick: close, "aria-label": "연결 관리 닫기" }, "닫기")),
  view.names.length > 1 ? el("select", { value: view.nodeName, disabled: busy,
    style: { ...button, margin: "14px 18px 0" },
    onChange: event => setView(previous => previous ? { ...previous, nodeName: event.target.value } : previous),
    "aria-label": "연결을 확인할 노드" }, view.names.map(name => el("option", { key: name, value: name }, name))) : null,
  el("div", { style: { padding: 18, overflowY: "auto", minHeight: 120 }, "aria-busy": busy },
    error ? el("p", { role: "alert", style: { color: "#f6b3b3", margin: "0 0 12px" } }, error) : null,
    busy ? el("p", { role: "status" }, "연결 확인 중…") : null,
    snapshot ? el("p", { role: "status", "data-hmb-connections-detached": String(snapshot.detached),
      style: { color: "#bfcbdc", margin: "0 0 12px" } },
      typeof snapshot.details === "string" && snapshot.details
        ? snapshot.details : snapshot.detached ? "연결 해제됨 · 샷과 결과 보존" : "현재 연결 상태") : null,
    snapshot?.can_forget_missing === true ? el("p", { "data-hmb-forget-missing-description": true,
      style: { color: "#bfcbdc", fontSize: 12, lineHeight: 1.5, margin: "0 0 12px" } },
      "삭제된 상대의 복구 기록을 정리합니다. 이후 기존 샷 설정에 따른 연결 검색이 다시 허용됩니다. 입력·결과는 유지되며 새 실행은 하지 않습니다.") : null,
    snapshot && !snapshot.connections.length ? el("p", {}, snapshot.detached ? "연결이 해제되어 있습니다." : "연결된 항목이 없습니다.") : null,
    ...(snapshot?.connections || []).map((row, index) => el("article", { key: `${row.kind}:${row.peer_name}:${index}`,
      style: { border: "1px solid #354157", borderRadius: 8, padding: 12, marginBottom: 9 } },
      el("div", { style: { display: "flex", gap: 10, alignItems: "center" } },
        el("span", { style: { color: row.kind === "remote" ? "#d3b3ec" : "#a7ccec", fontSize: 12, minWidth: 64 } }, row.kind === "remote" ? "REMOTE" : "선 연결"),
        el("strong", { style: { overflowWrap: "anywhere" } }, row.peer_name)),
      el("div", { style: { color: "#aeb9ca", fontSize: 12, paddingTop: 6, overflowWrap: "anywhere" } },
        `${row.source_node_name}${row.source_parameter_name ? ` · ${row.source_parameter_name}` : ""} → ${row.target_node_name}${row.target_parameter_name ? ` · ${row.target_parameter_name}` : ""}`),
      row.shots.length ? el("div", { style: { paddingTop: 6, color: "#c9d2df", fontSize: 12, overflowWrap: "anywhere" } },
        row.shots.map(shot => `${shot.number == null ? "" : `${String(shot.number).padStart(2, "0")} · `}${typeof shot.name === "string" ? shot.name : ""}`).join(" / ")) : null))),
  el("footer", { style: { display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "flex-end", padding: 18, borderTop: "1px solid #313c50" } },
    el("button", { type: "button", style: actionStyle(busy), disabled: busy,
      onClick: () => setView(previous => previous ? { ...previous, nonce: previous.nonce + 1 } : previous) }, "새로고침"),
    el("button", { type: "button", style: actionStyle(busy || !snapshot?.can_disconnect), disabled: busy || !snapshot?.can_disconnect, onClick: () => manage("disconnect") }, "연결 해제"),
    el("button", { type: "button", style: actionStyle(busy || !snapshot?.can_reconnect), disabled: busy || !snapshot?.can_reconnect, onClick: () => manage("reconnect") }, "다시 연결"),
    snapshot?.can_forget_missing === true ? el("button", { type: "button", style: actionStyle(busy), disabled: busy,
      onClick: () => manage("forget_missing") }, "삭제된 연결 기록 정리") : null))), document.body, "hmb-native-connection-manager");
}
let hmbNativeDeletionHostCount = 0;
function hmbUseNativeDeletionGuardHost() {
  (0, S.useLayoutEffect)(() => {
    const root = typeof document === "undefined" ? null : document.documentElement;
    if (!root) return;
    hmbNativeDeletionHostCount += 1;
    root.setAttribute("data-hmb-native-deletion-guard", "engine-preflight");
    root.setAttribute("data-hmb-native-deletion-protection-version", "2");
    return () => {
      hmbNativeDeletionHostCount -= 1;
      if (!hmbNativeDeletionHostCount
        && root.getAttribute("data-hmb-native-deletion-guard") === "engine-preflight") {
        root.removeAttribute("data-hmb-native-deletion-guard");
      }
      if (!hmbNativeDeletionHostCount
        && root.getAttribute("data-hmb-native-deletion-protection-version") === "2") {
        root.removeAttribute("data-hmb-native-deletion-protection-version");
      }
    };
  }, []);
}
function hmbNativeStudioResetCollapseIntents() {
  hmbNativeStudioFlowEpoch += 1;
  hmbNativeDeletionPending.clear();
  hmbNativeConnectionNotices.clear();
  if (typeof document !== "undefined" && typeof CustomEvent === "function") {
    document.dispatchEvent?.(new CustomEvent("hmb-native-connection-context-reset"));
  }
}
function hmbNativeDeletionFinished(nodeName) {
  if (typeof nodeName === "string") hmbNativeDeletionPending.delete(nodeName);
}
// Every deletion entry point eventually reaches the controlled canvas change
// handler. Ask the engine to identify HMB library ownership (including future
// node types); never infer ownership from a node's display name or type prefix.
function hmbNativeGuardNodeDeletion(changes, nodes, apply) {
  const removals = changes.filter(change => change.type === "remove");
  if (!removals.length) { apply(changes); return; }
  const otherChanges = changes.filter(change => change.type !== "remove");
  if (otherChanges.length) apply(otherChanges);
  const names = [...new Set(removals.map(change => change.id))];
  const epoch = hmbNativeStudioFlowEpoch;
  const now = Date.now();
  if (names.some(name => (hmbNativeDeletionPending.get(name)?.until || 0) > now)) return;
  const operation = { epoch, until: now + 30000 };
  names.forEach(name => hmbNativeDeletionPending.set(name, operation));
  const release = () => names.forEach(name => {
    if (hmbNativeDeletionPending.get(name) === operation) hmbNativeDeletionPending.delete(name);
  });
  Promise.resolve().then(() => Xd.request("HMBCheckNodeDeletionRequest", { node_names: names }))
    .then(result => {
      if (epoch !== hmbNativeStudioFlowEpoch) { release(); return; }
      if (result?.protection_ready !== true || result?.protection_version !== 2) {
        release();
        ig.warning("삭제 보호를 다시 시작해야 합니다", {
          description: result?.readiness_error || "HMB 삭제 보호 코드가 현재 엔진과 일치하지 않습니다. Override 업데이트 로그를 확인하고 작업을 저장한 뒤 Griptape를 완전히 종료하고 다시 시작하세요. 자동 적용 실패 또는 상태 확인 불가 시 HMB 업데이트 로그의 원인을 확인하세요. 노드와 결과는 유지됩니다.",
          duration: 8000,
        });
        return;
      }
      if (result?.can_delete !== true) {
        release();
        ig.warning("삭제할 수 없습니다", {
          description: result?.message || "연결을 해제한 뒤 삭제해 주세요.", duration: 6000,
          action: { label: "연결 관리", onClick: () => {
            if (epoch === hmbNativeStudioFlowEpoch) hmbNativeOpenConnections(
              Object.keys(result?.blocked || {}).length ? Object.keys(result.blocked) : names);
          } },
        });
        return;
      }
      // Older guarded engines may omit ownership details. In that case defer
      // every node's removal until its successful engine acknowledgement.
      const hmbNames = new Set(Array.isArray(result.hmb_node_names) ? result.hmb_node_names : names);
      const liveNames = new Set(nodes.map(node => node.id));
      if (!names.every(name => liveNames.has(name))) { release(); return; }
      apply(removals.map(change => hmbNames.has(change.id)
        ? { ...change, hmbGuardedDelete: true } : change));
      names.filter(name => !hmbNames.has(name)).forEach(hmbNativeDeletionFinished);
    })
    .catch(error => {
      release();
      if (epoch !== hmbNativeStudioFlowEpoch) return;
      ig.error("삭제를 확인할 수 없습니다", {
        description: typeof vg === "function" ? vg(error) : String(error), duration: 6000,
      });
    });
}
function hmbNativeStudioCurrentController(node) {
  const current = node && hmbNativeStudioCollapseControllers.get(node);
  return current?.epoch === hmbNativeStudioFlowEpoch ? current : null;
}
function hmbNativeStudioSavedSize(value) {
  return value?.version === 1 && Number.isFinite(value.width) && Number.isFinite(value.height)
    && value.width > 72 && value.height > 72
    && value.width <= 100000 && value.height <= 100000 ? value : null;
}
function hmbNativeStudioAccent(value) {
  const color = typeof value === "string" ? value.trim() : "";
  return /^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(color)
    || /^rgba?\([0-9.,%\s/]+\)$/i.test(color) ? color : null;
}
function hmbNativeStudioCaptureFoldedStyles(node, current) {
  if (!node || !current || current.foldedStyles) return;
  current.foldedStyles = Object.fromEntries(["width", "height", "min-width", "min-height"].map(key =>
    [key, { value: node.style.getPropertyValue(key), priority: node.style.getPropertyPriority(key) }]));
  const selector = hmbNativeStudioCompactSurfaces[current.nodeType] || hmbNativeStudioHeaderSurfaces[current.nodeType];
  for (const surface of selector ? node.querySelectorAll(selector) : []) {
    if (!hmbNativeStudioVisible(surface, node)) continue;
    const style = node.ownerDocument.defaultView.getComputedStyle(surface);
    for (const variable of ["--shot-accent", "--hmb-shot-accent", "--active-shot-accent", "--ib-accent", "--ig-accent", "--cl-accent", "--hmb-accent", "--accent"]) {
      const accent = hmbNativeStudioAccent(style.getPropertyValue(variable));
      if (!accent) continue;
      current.accent = accent; node.style.setProperty("--hmb-native-capsule-accent", accent); break;
    }
    if (current.accent) break;
  }
}
function hmbNativeStudioRestoreFoldedStyles(node, current) {
  if (!node || !current?.foldedStyles) return;
  for (const [key, original] of Object.entries(current.foldedStyles)) {
    const value = node.style.getPropertyValue(key);
    const ownedValues = key.endsWith("width") ? [`${hmbNativeStudioCollapsedWidth}px`]
      : [`${hmbNativeStudioCollapsedHeight}px`, "48px"];
    if (node.style.getPropertyPriority(key) !== "important" || !ownedValues.includes(value)) continue;
    if (key.startsWith("min-") || original.priority === "important") {
      if (original.value) node.style.setProperty(key, original.value, original.priority);
      else node.style.removeProperty(key);
    } else node.style.setProperty(key, value);
  }
  current.foldedStyles = null;
}
const hmbNativeStudioCompactSurfaces = {
  HMBImageAssetLibrary: "[data-library-toggle-surface=header]",
  HMBVideoPickerLibrary: "[data-picker-toggle-surface=header]",
};
const hmbNativeStudioHeaderSurfaces = {
  HMBColorLUTLibrary: ".cl-head", HMBAgentLibrary: ".agent-topbar",
  HMBFinishLookLibrary: ".hmb-finish-look__topbar", HMBImageBash: ".hmb-image-bash-header__row",
  HMBImageGeneration: ".hmb-image-generation-header__row", HMBSeedanceGeneration: ".hmb-seedance-shot__row",
  HMBPromptLibrary: ".topbar",
};

function hmbNativeStudioNode(nodeName) {
  return typeof document === "undefined" ? null
    : document.querySelector(`.react-flow__node[data-id="${CSS.escape(nodeName)}"]`);
}
function hmbNativeStudioRecordCollapsed(nodeType, nodeName, collapsed, metadata = null) {
  if (!hmbIsNativeStudioType(nodeType, metadata)) return;
  const node = hmbNativeStudioNode(nodeName);
  if (!node) return;
  const current = hmbNativeStudioCurrentController(node);
  if (current) current.intent = collapsed;
}
// Repair only the legacy impossible combination of an expanded HMB node and
// the exact capsule dimensions, with a recorded expanded size. The node and
// live geometry are checked immediately before the partial metadata update.
function hmbNativeStudioRepairLegacySize(data, getNodes, updateNode) {
  const metadata = data?.metadata, size = metadata?.size, expanded = hmbNativeStudioSavedSize(metadata?.hmb_native_studio_expanded_size);
  if (!hmbIsNativeStudioType(data?.node_type, metadata) || data?.collapsed !== false || metadata?.rolledUp === true
    || size?.width !== hmbNativeStudioCollapsedWidth || size?.height !== hmbNativeStudioCollapsedHeight || !expanded
    || typeof getNodes !== "function" || typeof updateNode !== "function") return () => {};
  let cancelled = false, frame = null, attempts = 0; const epoch = hmbNativeStudioFlowEpoch;
  const same = live => !!live && live.id === data.node_name && live.data?.node_type === data.node_type && live.data?.collapsed === false
    && live.data?.metadata?.size?.width === hmbNativeStudioCollapsedWidth && live.data?.metadata?.size?.height === hmbNativeStudioCollapsedHeight
    && live.data?.metadata?.hmb_native_studio_expanded_size?.width === expanded.width
    && live.data?.metadata?.hmb_native_studio_expanded_size?.height === expanded.height && !live.resizing;
  const attempt = () => {
    if (cancelled || epoch !== hmbNativeStudioFlowEpoch) return;
    const live = getNodes().find(item => item.id === data.node_name);
    if (!same(live)) return;
    if (Number(live.width) !== expanded.width || Number(live.height) !== expanded.height) {
      if (++attempts < 6) frame = requestAnimationFrame(attempt); return;
    }
    Xd.request("SetNodeMetadataRequest", { node_name: data.node_name, metadata: { size: { width: expanded.width, height: expanded.height } } })
      .then(result => {
        if (cancelled || epoch !== hmbNativeStudioFlowEpoch || result?.succeeded === false) return;
        updateNode(data.node_name, latest => same(latest) && Number(latest.width) === expanded.width && Number(latest.height) === expanded.height
          ? { ...latest, data: { ...latest.data, metadata: { ...latest.data.metadata, size: { width: expanded.width, height: expanded.height } } } } : latest);
      }).catch(() => {});
  };
  frame = requestAnimationFrame(attempt);
  return () => { cancelled = true; if (frame !== null) cancelAnimationFrame(frame); };
}
function hmbUseNativeStudioCollapseState(data, collapsed, setCollapsed, rolledUp = false, animatedSize = null) {
  const owner = (0, S.useRef)({});
  const { updateNode, getNodes } = Nu();
  const epoch = hmbNativeStudioFlowEpoch;
  (0, S.useLayoutEffect)(() => hmbNativeStudioRepairLegacySize(data, getNodes, updateNode),
    [data.node_name, data.node_type, data.collapsed, data.metadata?.rolledUp, data.metadata?.size?.width, data.metadata?.size?.height,
      data.metadata?.hmb_native_studio_expanded_size?.width, data.metadata?.hmb_native_studio_expanded_size?.height, getNodes, updateNode, epoch]);
  (0, S.useLayoutEffect)(() => {
    if (!hmbIsNativeStudioType(data.node_type, data.metadata)) return;
    const node = hmbNativeStudioNode(data.node_name);
    if (!node) return;
    // Shell styling belongs to the HMB node, not to asynchronous widget slots.
    // Layout effects run before paint; a retiring/reloading portal may fall
    // back to native controls without revealing the stock rectangular frame.
    node.setAttribute("data-hmb-native-studio-shell", "active");
    hmbInstallColorLUTUnifiedFrame(node.ownerDocument);
    if (collapsed) node.setAttribute("data-hmb-native-icon-layout", "active");
    else node.removeAttribute("data-hmb-native-icon-layout");
    if (animatedSize) node.setAttribute("data-hmb-native-fold-transition", "active");
    else node.removeAttribute("data-hmb-native-fold-transition");
    if (!collapsed && rolledUp) node.setAttribute("data-hmb-native-rollup-layout", "active");
    else node.removeAttribute("data-hmb-native-rollup-layout");
    let current = hmbNativeStudioCollapseControllers.get(node);
    if (!current || current.owner !== owner.current || current.epoch !== epoch) {
      current = { owner: owner.current, epoch, nodeType: data.node_type, metadata: data.metadata, intent: null,
        accent: hmbNativeStudioAccent(data.metadata?.hmb_native_studio_capsule_accent),
        expandedSize: data.collapsed ? hmbNativeStudioSavedSize(data.metadata?.hmb_native_studio_expanded_size) : null,
        rolledUp: !!data.metadata?.rolledUp,
        rollupSize: data.metadata?.rolledUp ? hmbNativeStudioSavedSize(data.metadata?.hmb_native_studio_rollup_size) : null };
      hmbNativeStudioCollapseControllers.set(node, current);
    }
    current.metadata = data.metadata;
    current.animating = !!animatedSize;
    node.style.setProperty("--hmb-native-capsule-accent", current.accent || "#73517e");
    const wanted = typeof current.intent === "boolean" ? current.intent : data.collapsed;
    if (typeof wanted === "boolean" && wanted !== collapsed) setCollapsed(wanted);
    // A late native reconstruct must not undo this mounted node's explicit
    // arrow selection. Match only the native presentation flag, preserving
    // every parameter, result, binding and metadata field in the live node.
    if (typeof current.intent === "boolean" && data.collapsed !== wanted) {
      updateNode(data.node_name, live => hmbNativeStudioFlowEpoch === epoch && node.isConnected
        && hmbNativeStudioCollapseControllers.get(node) === current && current.intent === wanted
        && live.id === data.node_name && live.data?.node_type === data.node_type
        && live.data.collapsed !== wanted ? { ...live, data: { ...live.data, collapsed: wanted } } : live);
    }
    if (data.metadata?.synthetic_diagnostic === true) {
      node.setAttribute("data-hmb-native-collapse-local", String(collapsed));
      node.setAttribute("data-hmb-native-collapse-prop", String(data.collapsed));
      node.setAttribute("data-hmb-native-collapse-metadata", String(data.metadata?.collapsed));
      node.setAttribute("data-hmb-native-collapse-intent", String(current.intent));
    }
  }, [data.node_type, data.metadata?.library, data.metadata?.hmb_native_studio_ui, data.node_name, data.collapsed, data.metadata?.collapsed,
    data.metadata?.synthetic_diagnostic, collapsed, rolledUp, animatedSize, setCollapsed, updateNode, epoch]);
  (0, S.useEffect)(() => {
    if (!hmbIsNativeStudioType(data.node_type, data.metadata) && data.collapsed !== void 0 && data.collapsed !== collapsed) setCollapsed(data.collapsed);
  }, [data.node_type, data.metadata?.library, data.metadata?.hmb_native_studio_ui, data.collapsed]);
  (0, S.useLayoutEffect)(() => {
    if (!hmbIsNativeStudioType(data.node_type, data.metadata)) return;
    const node = hmbNativeStudioNode(data.node_name), current = hmbNativeStudioCurrentController(node);
    if (!node || !current) return;
    if (!collapsed && !rolledUp) { hmbNativeStudioRestoreFoldedStyles(node, current); return; }
    hmbNativeStudioCaptureFoldedStyles(node, current);
    const force = () => {
      // Native MAr owns interpolated dimensions until its completion callback.
      // A fixed width/height here would oppose each native animation frame and
      // feed a second size back through ReactFlow's controlled node store.
      const dimensions = collapsed ? { ...(!animatedSize ? { width: `${hmbNativeStudioCollapsedWidth}px`, height: `${hmbNativeStudioCollapsedHeight}px` } : {}),
        "min-width": `${hmbNativeStudioCollapsedWidth}px`, "min-height": `${hmbNativeStudioCollapsedHeight}px` }
        : { ...(!animatedSize ? { height: "48px" } : {}), "min-height": "48px" };
      for (const [key, value] of Object.entries(dimensions)) {
        if (node.style.getPropertyValue(key) !== value || node.style.getPropertyPriority(key) !== "important") node.style.setProperty(key, value, "important");
      }
    };
    force();
    // Passive raw-widget cleanup may restore an old inline !important compact
    // size after native layout. Enforce only this mounted folded presentation.
    const observer = new MutationObserver(force);
    observer.observe(node, { attributes: true, attributeFilter: ["style"] });
    return () => observer.disconnect();
  }, [data.node_type, data.metadata?.library, data.metadata?.hmb_native_studio_ui, data.node_name, collapsed, rolledUp, animatedSize, epoch]);
  (0, S.useLayoutEffect)(() => () => {
    if (!hmbIsNativeStudioType(data.node_type, data.metadata)) return;
    const node = hmbNativeStudioNode(data.node_name);
    if (node && hmbNativeStudioCollapseControllers.get(node)?.owner === owner.current) {
      hmbNativeStudioRestoreFoldedStyles(node, hmbNativeStudioCollapseControllers.get(node));
      node.removeAttribute("data-hmb-native-icon-layout");
      node.removeAttribute("data-hmb-native-rollup-layout");
      node.removeAttribute("data-hmb-native-fold-transition");
      node.removeAttribute("data-hmb-native-studio-shell");
      node.style.removeProperty("--hmb-native-capsule-accent");
      hmbNativeStudioCollapseControllers.delete(node);
      for (const suffix of ["local", "prop", "metadata", "intent"]) node.removeAttribute(`data-hmb-native-collapse-${suffix}`);
    }
  }, [data.node_type, data.metadata?.library, data.metadata?.hmb_native_studio_ui, data.node_name]);
}
function hmbNativeStudioVisible(element, node) {
  if (!element?.isConnected || !element.getClientRects().length) return false;
  const view = element.ownerDocument.defaultView;
  for (let current = element; current && current !== node; current = current.parentElement) {
    const style = view.getComputedStyle(current);
    if (style.display === "none" || style.visibility !== "visible" || Number(style.opacity) === 0) return false;
  }
  return true;
}
function hmbNativeStudioView(nodeType, node) {
  const selector = hmbNativeStudioCompactSurfaces[nodeType];
  if (!selector || !node) return null;
  for (const surface of node.querySelectorAll(selector)) {
    if (!hmbNativeStudioVisible(surface, node)) continue;
    const root = surface.closest(nodeType === "HMBImageAssetLibrary" ? ".hmb-image-assets" : ".hmbvp");
    const compact = nodeType === "HMBImageAssetLibrary" ? root?.dataset.libraryCompact === "true" : root?.dataset.pickerView === "compact";
    return { surface, view: compact ? "compact" : "expanded" };
  }
  return null;
}
function hmbNativeStudioToggleCompact(nodeType, nodeName, fallback) {
  return () => {
    const node = hmbNativeStudioNode(nodeName), current = hmbNativeStudioView(nodeType, node);
    if (!current) { fallback?.(); return; }
    if (hmbNativeStudioCompactDispatching.has(node)) return;
    hmbNativeStudioCompactDispatching.add(node);
    try {
      current.surface.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, cancelable: true }));
    } finally { hmbNativeStudioCompactDispatching.delete(node); }
  };
}
function hmbNativeStudioDoubleClick(nodeType, nodeName, fallback, metadata = null) {
  if (!hmbIsNativeStudioType(nodeType, metadata)) return fallback;
  // Only existing product compact views toggle from a header double click.
  // A HMB node without that view must not expose native rollup as a substitute.
  return hmbNativeStudioCompactSurfaces[nodeType]
    ? hmbNativeStudioToggleCompact(nodeType, nodeName) : undefined;
}
function hmbNativeStudioCollapseMetadata(node, collapsed, maintainWidth) {
  const nodeType = node?.data?.node_type;
  if (!hmbIsNativeStudioType(nodeType, node?.data?.metadata)) return {};
  const root = hmbNativeStudioNode(node.id), controller = hmbNativeStudioCurrentController(root);
  if (maintainWidth) return { hmb_native_studio_rollup_size: controller?.rollupSize || null };
  const savedSize = node?.data?.metadata?.size, expanded = controller?.expandedSize, target = controller?.geometryTarget;
  // A restore can otherwise persist collapsed:false alongside the old capsule
  // size. Correct only a known capsule-to-expanded transition; a manual size
  // or a width-preserving rollup remains owned by the native editor.
  const restoringCapsule = !collapsed && !maintainWidth && savedSize?.width === hmbNativeStudioCollapsedWidth
    && savedSize?.height === hmbNativeStudioCollapsedHeight && expanded && target
    && target.newWidth === expanded.width && target.newHeight === expanded.height;
  const result = { hmb_native_studio_expanded_size: expanded || null,
    hmb_native_studio_rollup_size: controller?.rollupSize || null,
    ...(restoringCapsule ? { size: { width: expanded.width, height: expanded.height } } : {}),
    ...(controller?.accent ? { hmb_native_studio_capsule_accent: controller.accent } : {}) };
  if (!hmbNativeStudioCompactSurfaces[nodeType]) return result;
  if (!collapsed) return { ...result, hmb_native_studio_view: null };
  const current = hmbNativeStudioView(nodeType, root);
  if (!current) return result;
  const record = { version: 1, view: current.view };
  hmbNativeStudioViewMemory.set(root, { ...record, pending: true });
  return { ...result, hmb_native_studio_view: record };
}
function hmbNativeStudioRestoreView(nodeType, node, hint) {
  if (!hmbNativeStudioCompactSurfaces[nodeType] || !node) return;
  const memory = hmbNativeStudioViewMemory.get(node);
  const wanted = memory?.pending ? memory : !hmbNativeStudioRestoredViews.has(node) && hint;
  if (wanted?.version !== 1 || !["compact", "expanded"].includes(wanted.view)) return;
  const current = hmbNativeStudioView(nodeType, node);
  if (!current) return;
  hmbNativeStudioRestoredViews.add(node);
  hmbNativeStudioViewMemory.set(node, { ...wanted, pending: false });
  if (current.view !== wanted.view) hmbNativeStudioToggleCompact(nodeType, node.getAttribute("data-id"))();
}
function hmbNativeStudioConstructedNode(node) {
  if (!hmbIsNativeStudioType(node?.data?.node_type, node?.data?.metadata) || node.type === "GroupNode") return node;
  const metadata = node.data.metadata || {};
  if (node.data.collapsed) return { ...node, width: hmbNativeStudioCollapsedWidth, height: hmbNativeStudioCollapsedHeight,
    data: { ...node.data, hmb_native_studio_restore_view: metadata.hmb_native_studio_view || null } };
  const expanded = hmbNativeStudioSavedSize(metadata.hmb_native_studio_expanded_size);
  if (metadata.collapsed === false && metadata.rolledUp !== true && expanded
    && metadata.size?.width === hmbNativeStudioCollapsedWidth && metadata.size?.height === hmbNativeStudioCollapsedHeight) {
    return { ...node, width: expanded.width, height: expanded.height };
  }
  return node;
}
function hmbNativeStudioDimensions(nodeType, collapsed, maintainWidth, width, height, metadataSize, restoreHeight, nodeName, metadata = null) {
  if (!hmbIsNativeStudioType(nodeType, metadata)) return Tjr(collapsed, maintainWidth, width, height, metadataSize, restoreHeight);
  const node = hmbNativeStudioNode(nodeName), current = hmbNativeStudioCurrentController(node);
  const size = hmbNativeStudioSavedSize({ version: 1, width: Number(width), height: Number(height) });
  if (maintainWidth) {
    if (current) {
      if (collapsed) hmbNativeStudioCaptureFoldedStyles(node, current);
      current.rolledUp = collapsed;
      if (collapsed && size) current.rollupSize = size;
    }
    const restored = restoreHeight ?? current?.rollupSize?.height;
    const target = Tjr(collapsed, true, width, height, metadataSize, restored);
    if (current && !collapsed) current.geometryTarget = target;
    return target;
  }
  if (collapsed) {
    if (current) {
      hmbNativeStudioCaptureFoldedStyles(node, current);
      if (size) current.expandedSize = size;
      else if (current.rollupSize) current.expandedSize = current.rollupSize;
      current.rolledUp = false;
    }
    return { newWidth: hmbNativeStudioCollapsedWidth, newHeight: hmbNativeStudioCollapsedHeight };
  }
  const target = current?.expandedSize ? { newWidth: current.expandedSize.width, newHeight: current.expandedSize.height }
    : Tjr(collapsed, maintainWidth, width, height, metadataSize, restoreHeight);
  if (current) current.geometryTarget = target;
  return target;
}
function hmbNativeStudioFolded(node) {
  if (!hmbIsNativeStudioType(node?.data?.node_type, node?.data?.metadata)) return false;
  const root = hmbNativeStudioNode(node.id), current = hmbNativeStudioCurrentController(root);
  return !!(node.data.collapsed || node.data.metadata?.rolledUp || current?.intent === true || current?.rolledUp);
}
function hmbNativeStudioSuppressInitialSize(node, dimensions) {
  if (!hmbIsNativeStudioType(node?.data?.node_type, node?.data?.metadata)) return false;
  if (hmbNativeStudioFolded(node)) return true;
  const root = hmbNativeStudioNode(node.id), current = hmbNativeStudioCurrentController(root);
  if (!current?.geometryTarget) return false;
  if (Math.abs(Number(dimensions?.width) - current.geometryTarget.newWidth) > 1
    || Math.abs(Number(dimensions?.height) - current.geometryTarget.newHeight) > 1) return true;
  current.geometryTarget = null;
  return false;
}
function hmbNativeStudioCollapsedMeasuredNode(node) {
  const hmb = hmbIsNativeStudioType(node?.data?.node_type, node?.data?.metadata);
  const current = hmb ? hmbNativeStudioCurrentController(hmbNativeStudioNode(node.id)) : null;
  if (current?.animating) return node;
  const size = hmb ? hmbNativeStudioCollapsedWidth : 300;
  const height = hmb ? hmbNativeStudioCollapsedHeight : 48;
  if (hmb && node.width === size && node.height === height
    && node.measured?.width === size && node.measured?.height === height) return node;
  return { ...node, width: size, height, measured: { width: size, height } };
}
function hmbNativeStudioCollapsedMeasuredNodes(nodes, ids) {
  let changed = false;
  const next = nodes.map(node => {
    const result = ids.has(node.id) && node.data?.collapsed === true ? hmbNativeStudioCollapsedMeasuredNode(node) : node;
    if (result !== node) changed = true;
    return result;
  });
  return changed ? next : nodes;
}
function hmbNativeStudioOutgoingMetadata(nodeName, metadata) {
  const current = hmbNativeStudioCurrentController(hmbNativeStudioNode(nodeName));
  if (!current || !hmbIsNativeStudioType(current.nodeType, current.metadata)) return metadata;
  // Native geometry/position persistence spreads an older metadata snapshot.
  // Its dimensions remain original, but it cannot undo the latest view action.
  return { ...metadata,
    ...(typeof current.intent === "boolean" ? { collapsed: current.intent } : {}),
    ...(typeof current.rolledUp === "boolean" ? { rolledUp: current.rolledUp } : {}),
    ...(current.expandedSize ? { hmb_native_studio_expanded_size: current.expandedSize } : {}),
    ...(current.rollupSize ? { hmb_native_studio_rollup_size: current.rollupSize } : {}),
    ...(current.accent ? { hmb_native_studio_capsule_accent: current.accent } : {}) };
}
function hmbNativeStudioNodeStyle(nodeType, animatedSize, collapsed, minHeight, minWidth, locked, rolledUp, metadata = null) {
  const original = Sjr(animatedSize, collapsed, minHeight, minWidth, locked, rolledUp);
  if (!hmbIsNativeStudioType(nodeType, metadata)) return original;
  if (collapsed && !animatedSize) return { ...original, width: hmbNativeStudioCollapsedWidth, height: hmbNativeStudioCollapsedHeight,
    minWidth: hmbNativeStudioCollapsedWidth, minHeight: hmbNativeStudioCollapsedHeight, overflow: "visible" };
  // Keep native dimensions, animation overflow, locked opacity and error state.
  // These visual defaults are present in the first React commit, before a
  // widget mounts or a header-ready/retire event can change portal ownership.
  return { ...original, background: "#0b111b", borderRadius: 24, boxShadow: "none" };
}
function hmbNativeStudioCollapsedHeader(nodeName, icon, headerStyle, expand, locked, error) {
  const restore = event => { event.preventDefault(); event.stopPropagation(); expand?.(); };
  return (0, R.jsxs)("div", { "data-hmb-native-icon-header": true, "data-hmb-native-capsule": "soft-link-02",
    className: "hmb-native-capsule", role: "button", tabIndex: 0, "aria-label": `Expand ${nodeName}`,
    "aria-description": "Double Click to Unlock. Enter or Space also restores this view.",
    title: `${nodeName}${locked ? " · Locked" : ""}${error ? " · Error" : ""}`,
    onDoubleClick: restore,
    onKeyDown: event => { if (!event.repeat && ["Enter", " "].includes(event.key)) restore(event); },
    style: { width: hmbNativeStudioCollapsedWidth, height: hmbNativeStudioCollapsedHeight,
      boxSizing: "border-box", position: "relative", isolation: "isolate", display: "flex", alignItems: "center",
      gap: 10, padding: 5, borderRadius: 999, overflow: "hidden", userSelect: "none", cursor: "grab",
      background: "linear-gradient(125deg,color-mix(in srgb,var(--hmb-native-capsule-accent,#73517e) 29%,#243040),#394253 53%,#303e50)",
      border: "1px solid #e1d6ed45", boxShadow: "inset 0 1px 1px #ffffff25,inset 0 -1px 1px #00000028,0 8px 20px #02060c44" },
    children: [(0, R.jsx)("span", { "data-hmb-capsule-disc": true, "aria-hidden": true,
      style: { flex: "0 0 52px", width: 52, height: 52, borderRadius: "50%", boxSizing: "border-box",
        display: "grid", placeItems: "center", pointerEvents: "none", color: "var(--hmb-native-capsule-accent,#73517e)",
        background: "linear-gradient(150deg,#fff,#ebedf3 65%,#cbd1dd)", border: "1px solid #ffffffbf",
        boxShadow: "0 3px 10px #0609173d,inset 0 1px 2px white" },
      children: (0, R.jsx)("svg", { "data-hmb-soft-link-icon": "02", viewBox: "0 0 64 64", fill: "none", stroke: "currentColor",
        strokeWidth: 3.4, strokeLinecap: "round", strokeLinejoin: "round", width: 36, height: 36,
        children: (0, R.jsxs)("g", { transform: "rotate(-36 32 32)", children: [
          (0, R.jsx)("rect", { x: 8, y: 22, width: 30, height: 20, rx: 10 }),
          (0, R.jsx)("rect", { x: 26, y: 22, width: 30, height: 20, rx: 10 })] }) }) }),
    (0, R.jsx)("span", { "data-hmb-capsule-label": true,
      style: { flex: 1, minWidth: 0, paddingRight: 12, whiteSpace: "nowrap", pointerEvents: "none",
        textAlign: "center", fontFamily: '"Segoe UI",sans-serif', fontSize: 17, fontWeight: 300,
        letterSpacing: ".15px", lineHeight: 1.2, color: "#f2ecf7e8", textShadow: "0 1px 2px #00000025" },
      children: "Double Click to Unlock" })] });
}

function hmbUseColorLUTNativeHeader(nodeType, nodeName, hostExpanded, doubleClick, restoreView, collapsed = false, metadata = null) {
  const [slots, setSlots] = (0, S.useState)(null);
  const current = (0, S.useRef)(null);
  const refreshNodeGeometry = FEr();
  const eligible = hmbIsNativeStudioType(nodeType, metadata) && hostExpanded;
  const valid = (candidate) => {
    if (!candidate?.container?.isConnected || !candidate.identity?.isConnected || !candidate.actions?.isConnected) return false;
    const node = candidate.container.closest?.(".react-flow__node");
    // Every HMB header receives the document-wide ready event. Reject another
    // node's slots before style/rect reads so mounting N nodes does not measure
    // every header N times. Do not cache visibility: measurement copies can be
    // promoted into the visible widget after a native fold/restore.
    if (node?.getAttribute("data-id") !== nodeName
      || !candidate.container.matches?.("[data-hmb-color-lut-widget]")
      || (!candidate.container.hasAttribute("data-hmb-native-node-type")
        ? nodeType !== "HMBColorLUTLibrary" : candidate.container.getAttribute("data-hmb-native-node-type") !== nodeType)
      || !candidate.container.contains(candidate.identity) || !candidate.container.contains(candidate.actions)) return false;
    const view = candidate.container.ownerDocument.defaultView;
    // The native collapsed-parameter footer also mounts a live YTr under
    // opacity:0. Visibility/getClientRects alone accepts that measurement copy
    // and moves the only native controls into an unclickable footer.
    for (let element = candidate.container; element && element !== node; element = element.parentElement) {
      const style = view.getComputedStyle(element);
      if (style.visibility !== "visible" || style.display === "none" || Number(style.opacity) === 0) return false;
    }
    return !!candidate.container.getClientRects().length;
  };
  const notify = (container, active) => {
    container?.dispatchEvent?.(new CustomEvent("hmb-color-lut-header-state", { detail: { active } }));
  };
  (0, S.useLayoutEffect)(() => {
    if (!hmbIsNativeStudioType(nodeType, metadata)) return;
    let cancelled = false, frame = null, attempts = 0;
    const discover = (container) => {
      if (cancelled || !container) return false;
      const candidate = { container,
        identity: container.querySelector?.("[data-hmb-native-identity]"),
        actions: container.querySelector?.("[data-hmb-native-actions]") };
      if (!valid(candidate)) return false;
      if (current.current?.container !== container) notify(current.current?.container, false);
      current.current = candidate;
      setSlots(previous => previous?.container === container && previous.identity === candidate.identity
        && previous.actions === candidate.actions ? previous : candidate);
      return true;
    };
    const ready = (event) => discover(event.detail?.container);
    const retire = (event) => {
      if (event.detail?.container !== current.current?.container) return;
      notify(current.current.container, false); current.current = null; setSlots(null);
    };
    const initial = () => {
      if (cancelled) return;
      const node = document.querySelector(`.react-flow__node[data-id="${CSS.escape(nodeName)}"]`);
      for (const container of node?.querySelectorAll("[data-hmb-color-lut-widget]") || []) {
        if (discover(container)) break;
      }
      if (!valid(current.current) && ++attempts < 6) frame = requestAnimationFrame(initial);
    };
    document.addEventListener("hmb-color-lut-header-ready", ready);
    document.addEventListener("hmb-color-lut-header-retire", retire);
    initial();
    return () => {
      cancelled = true;
      if (frame !== null) cancelAnimationFrame(frame);
      document.removeEventListener("hmb-color-lut-header-ready", ready);
      document.removeEventListener("hmb-color-lut-header-retire", retire);
      notify(current.current?.container, false); current.current = null;
    };
  }, [nodeType, nodeName, metadata?.library, metadata?.hmb_native_studio_ui?.schema,
    metadata?.hmb_native_studio_ui?.version, metadata?.hmb_native_studio_ui?.node_type, metadata?.hmb_native_studio_ui?.widget]);
  const active = !!eligible && valid(slots);
  (0, S.useLayoutEffect)(() => {
    // ReactFlow may reuse a node DOM shell while opening a saved Workflow.
    // Re-arm only a real icon-collapse cycle, never a normal props refresh or
    // native width-preserving rollup. A freshly captured current view wins.
    if (!collapsed || !hmbNativeStudioCompactSurfaces[nodeType]) return;
    const node = hmbNativeStudioNode(nodeName);
    if (!node) return;
    hmbNativeStudioRestoredViews.delete(node);
    if (!hmbNativeStudioViewMemory.get(node)?.pending && restoreView?.version === 1
      && ["compact", "expanded"].includes(restoreView.view)) {
      hmbNativeStudioViewMemory.set(node, { ...restoreView, pending: true });
    }
  }, [nodeType, nodeName, collapsed, restoreView]);
  (0, S.useLayoutEffect)(() => {
    if (!active || !slots?.container) return;
    const container = slots.container, node = container.closest(".react-flow__node");
    hmbNativeStudioRestoreView(nodeType, node, restoreView);
    const selector = hmbNativeStudioHeaderSurfaces[nodeType];
    if (!selector || !doubleClick || !hmbNativeStudioCompactSurfaces[nodeType]) return;
    const onDoubleClick = event => {
      const target = event.target;
      if (target?.closest?.("[data-hmb-native-identity],[data-hmb-native-actions],button,input,select,textarea,label,a,[contenteditable=true]")) return;
      if (!target?.closest?.(selector)) return;
      event.preventDefault(); event.stopPropagation(); doubleClick();
    };
    container.addEventListener("dblclick", onDoubleClick);
    return () => container.removeEventListener("dblclick", onDoubleClick);
  }, [slots, active, nodeType, doubleClick, restoreView]);
  (0, S.useLayoutEffect)(() => {
    if (!slots?.container) return;
    notify(slots.container, active);
    return () => notify(slots.container, false);
  }, [slots, active]);
  (0, S.useLayoutEffect)(() => {
    const node = slots?.container?.closest?.(".react-flow__node");
    if (!active || !node) return;
    hmbInstallColorLUTUnifiedFrame(node.ownerDocument);
    node.setAttribute("data-hmb-color-lut-native-layout", "active");
    // Use the editor's own coalesced ReactFlow geometry refresh. Handle IDs,
    // contexts, drag/reconnect callbacks and engine connections stay native.
    refreshNodeGeometry(nodeName);
    return () => {
      node.removeAttribute("data-hmb-color-lut-native-layout");
      refreshNodeGeometry(nodeName);
    };
  }, [slots, active, nodeName, refreshNodeGeometry]);
  return { ...slots, active };
}

function hmbInstallColorLUTUnifiedFrame(doc) {
  if (doc.getElementById("hmb-color-lut-unified-frame-v1")) return;
  const style = doc.createElement("style");
  style.id = "hmb-color-lut-unified-frame-v1";
  style.textContent = `
.react-flow__node[data-hmb-native-icon-layout=active]{min-width:${hmbNativeStudioCollapsedWidth}px!important;min-height:${hmbNativeStudioCollapsedHeight}px!important}
.react-flow__node[data-hmb-native-icon-layout=active]:not([data-hmb-native-fold-transition]){width:${hmbNativeStudioCollapsedWidth}px!important;height:${hmbNativeStudioCollapsedHeight}px!important}
.react-flow__node[data-hmb-native-rollup-layout=active]{min-height:48px!important}
.react-flow__node[data-hmb-native-rollup-layout=active]:not([data-hmb-native-fold-transition]){height:48px!important}
.hmb-native-capsule:focus-visible{outline:2px solid var(--hmb-native-capsule-accent,#c9a8d4);outline-offset:4px}
.react-flow__node[data-hmb-native-studio-shell=active]:not([data-hmb-native-icon-layout=active])>div{background:#0b111b!important;border-radius:24px!important;box-shadow:none!important}
.react-flow__node[data-hmb-native-studio-shell=active]:not([data-hmb-native-icon-layout=active])>div .group[class~="h-[48px]"]{background:#0b111b!important;border-radius:22px 22px 0 0!important;box-shadow:none!important}
.react-flow__node[data-hmb-color-lut-native-layout=active]>div{background:#0b111b!important;border:1px solid #273241;border-radius:24px!important;box-shadow:none!important;overflow:visible!important}
.react-flow__node[data-hmb-color-lut-native-layout=active].selected>div{border-color:#51637d}
.react-flow__node[data-hmb-color-lut-native-layout=active] .bg-card{background:transparent!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] .hmb-color-lut{border:0!important;border-radius:0!important;box-shadow:none!important;background:transparent!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] [data-handleid=exec_in]{left:12px!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] [data-handleid=exec_out]{right:12px!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] [data-handleid=video_url]{right:10px!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__handle-left:not([data-handleid=exec_in]){left:10px!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__handle-right:not([data-handleid=exec_out]){right:10px!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__handle{z-index:8!important}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__resize-control{opacity:0!important;background:transparent!important;border-color:transparent!important;box-shadow:none!important;z-index:6}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__resize-control.line:is(.left,.right){width:10px}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__resize-control.line:is(.top,.bottom){height:10px}
.react-flow__node[data-hmb-color-lut-native-layout=active] .react-flow__resize-control.handle{width:16px;height:16px}
`;
  doc.head.appendChild(style);
}

function hmbUseColorLUTFrameActive(nodeType, nodeName, metadata = null) {
  const [active, setActive] = (0, S.useState)(false);
  (0, S.useLayoutEffect)(() => {
    if (!hmbIsNativeStudioType(nodeType, metadata)) { setActive(false); return; }
    const node = document.querySelector(`.react-flow__node[data-id="${CSS.escape(nodeName)}"]`);
    if (!node) return;
    const sync = () => {
      const next = node.getAttribute("data-hmb-color-lut-native-layout") === "active";
      setActive(previous => previous === next ? previous : next);
    };
    const observer = new MutationObserver(sync);
    observer.observe(node, { attributes: true, attributeFilter: ["data-hmb-color-lut-native-layout"] });
    sync();
    return () => observer.disconnect();
  }, [nodeType, nodeName, metadata?.library, metadata?.hmb_native_studio_ui?.schema,
    metadata?.hmb_native_studio_ui?.version, metadata?.hmb_native_studio_ui?.node_type, metadata?.hmb_native_studio_ui?.widget]);
  return active;
}

function hmbColorLUTHeaderPortals(slots, identity, actions, headerStyle) {
  const variables = Object.fromEntries(Object.entries(headerStyle || {}).filter(([key]) => key.startsWith("--")));
  const nativeIdentity = (0, R.jsx)("div", {
    className: "hmb-native-header-identity flex items-center min-w-0 group",
    style: variables, children: identity,
  });
  const nativeActions = (0, R.jsx)("div", {
    className: "hmb-native-header-actions flex items-center nodrag",
    style: variables, children: actions,
  });
  // This helper's global T is ReactDOM. D$t has a local T for openModal.
  return [(0, T.createPortal)(nativeIdentity, slots.identity, "hmb-native-identity"),
    (0, T.createPortal)(nativeActions, slots.actions, "hmb-native-actions")];
}
/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */

// Only the two native, interactive placement paths call this decorator. SDK
// workflow deserialization and duplication retain their original metadata.
function hmbColorLUTCreateMetadata(nodeType, metadata, initialSetup = false) {
  if (initialSetup || nodeType !== "HMBColorLUTLibrary" || !metadata || typeof metadata !== "object"
    || Object.keys(metadata).some(key => !["position", "tempId"].includes(key))
    || typeof metadata.tempId !== "string" || !metadata.tempId || metadata.tempId.length > 160) return metadata;
  return { ...metadata, hmb_color_lut_native_factory_request: {
    schema: "hmb-color-lut-native-factory-request-v1", temp_id: metadata.tempId,
  } };
}

const hmbColorLUTInitialGeometryAttempts = new Set();
function hmbColorLUTGeometrySizeMatches(size, width, height) {
  return Number(size?.width) === width && Number(size?.height) === height;
}

function hmbApplyColorLUTInitialGeometry(data, active, getNodes, setNodes, persist, refresh) {
  const key = "hmb_color_lut_native_initial_geometry", hint = data?.metadata?.[key];
  if (!active || data?.node_type !== "HMBColorLUTLibrary" || !hint
    || hint.schema !== "hmb-color-lut-native-initial-geometry-v1" || hint.version !== 1
    || hint.status !== "pending" || typeof hint.token !== "string" || !/^[a-f0-9]{32}$/.test(hint.token)
    || hint.width !== 1225 || hint.height !== 1057 || hint.factory_width !== 1220 || hint.factory_height !== 1160
    || hmbColorLUTInitialGeometryAttempts.has(hint.token)) return null;
  const name = data.node_name, original = getNodes().find(node => node.id === name);
  if (!original || original.data?.node_type !== data.node_type || original.data?.metadata?.[key]?.token !== hint.token) return null;
  hmbColorLUTInitialGeometryAttempts.add(hint.token);
  const isFactorySize = node => hmbColorLUTGeometrySizeMatches(node.data?.metadata?.size, hint.factory_width, hint.factory_height)
    && !node.resizing && !node.data?.collapsed && !node.data?.metadata?.rolledUp && !node.data?.metadata?.expanded_dimensions
    && [node.style, node.measured, node].every(size => (!size || size.width == null || Number(size.width) === hint.factory_width)
      && (!size || size.height == null || Number(size.height) === hint.factory_height));
  const resize = isFactorySize(original), consumed = { ...hint, status: resize ? "applied" : "skipped" };
  const owned = node => node?.id === name && node.data?.node_type === data.node_type
    && node.data?.metadata?.[key]?.token === hint.token;
  const target = { width: hint.width, height: hint.height };
  let finishCommit;
  const committed = new Promise(resolve => { finishCommit = resolve; });
  setNodes(nodes => {
    const current = nodes.find(owned);
    if (!current || current.data.metadata[key].status !== "pending" || resize && !isFactorySize(current)) {
      finishCommit(false); return nodes;
    }
    const resized = resize ? wjr(nodes, name, target.width, target.height) : nodes;
    finishCommit(true);
    return resized.map(node => owned(node) ? { ...node, data: { ...node.data,
      metadata: { ...node.data.metadata, ...(resize ? { size: target } : {}), [key]: consumed } } } : node);
  });
  const rollback = () => {
    setNodes(nodes => {
      const current = nodes.find(owned);
      if (!current || current.data.metadata[key].status !== consumed.status) return nodes;
      // A later manual resize, deletion/recreation, or metadata edit owns its
      // current dimensions. Never replay an old factory snapshot over it.
      const restore = resize && !current.resizing
        && hmbColorLUTGeometrySizeMatches(current.data.metadata.size, target.width, target.height)
        && hmbColorLUTGeometrySizeMatches(current.style, target.width, target.height)
        && hmbColorLUTGeometrySizeMatches(current.measured, target.width, target.height);
      return nodes.map(node => owned(node) ? { ...node,
        ...(restore ? { width: original.width, height: original.height,
          style: { ...node.style, width: original.style?.width, height: original.style?.height },
          measured: original.measured ? { ...original.measured } : undefined } : {}),
        data: { ...node.data, metadata: { ...node.data.metadata,
          ...(restore ? { size: { ...original.data.metadata.size } } : {}), [key]: { ...consumed, status: "rejected" } } } } : node);
    });
    refresh(name);
  };
  // Nu().setNodes queues functional updates in ReactFlow's native nodeQueue.
  // Resolve after that updater runs; never assume it completed synchronously.
  return committed.then(applied => {
    if (!applied) return null;
    const current = getNodes().find(owned);
    if (!current || current.data.metadata[key].status !== consumed.status) return null;
    refresh(name);
    const stillTarget = resize && !current.resizing
      && hmbColorLUTGeometrySizeMatches(current.data.metadata.size, target.width, target.height)
      && hmbColorLUTGeometrySizeMatches(current.style, target.width, target.height)
      && hmbColorLUTGeometrySizeMatches(current.measured, target.width, target.height);
    // The editor's original SDK client handles this partial metadata update.
    // A resize committed between queue flush and dispatch also wins.
    return Promise.resolve(persist(name, { ...(stillTarget ? { size: target } : {}), [key]: consumed }))
      .then(result => { if (result?.succeeded === false) throw new Error("Native metadata update was rejected"); return result; })
      .catch(error => { rollback(); return { rejected: true, error }; });
  }).catch(error => {
    rollback(); return Promise.resolve({ rejected: true, error });
  });
}

function hmbUseColorLUTInitialGeometry(data, active, getNodes, setNodes) {
  const refresh = FEr();
  (0, S.useLayoutEffect)(() => {
    hmbApplyColorLUTInitialGeometry(data, active, getNodes, setNodes, mq, refresh);
  }, [data.node_name, data.node_type, data.metadata?.hmb_color_lut_native_initial_geometry?.token,
    data.metadata?.hmb_color_lut_native_initial_geometry?.status, active, getNodes, setNodes, refresh]);
}
