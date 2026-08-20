// HMB VideoPicker command bridge cache version v032.
function clean(value) {
  return String(value == null ? "" : value).trim();
}

function composedParent(node) {
  if (!node) return null;
  if (node.parentElement) return node.parentElement;
  try {
    const root = node.getRootNode?.();
    if (root?.host) return root.host;
  } catch (_error) {}
  return null;
}

function findReactFlowNode(container) {
  let current = composedParent(container);
  let fallback = null;
  for (let depth = 0; current && depth < 48; depth += 1, current = composedParent(current)) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (!fallback && (
      current.hasAttribute?.("data-node-id")
      || current.hasAttribute?.("data-nodeid")
      || current.hasAttribute?.("data-id")
    )) fallback = current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) break;
  }
  return fallback || container?.parentElement || container || null;
}

export function hmbVideoPickerCommandBridgeIsHostMeasurementClone(container) {
  let current = composedParent(container);
  for (let depth = 0; current && depth < 48; depth += 1, current = composedParent(current)) {
    const classList = current.classList;
    const exactMeasurementWrapper = !!(
      classList?.contains?.("absolute")
      && classList?.contains?.("left-0")
      && classList?.contains?.("right-0")
      && classList?.contains?.("pointer-events-none")
    );
    let hidden = false;
    try {
      hidden = String(current.style?.visibility || "").toLowerCase() === "hidden";
    } catch (_error) {}
    if (exactMeasurementWrapper && hidden) return true;
    const className = String(current.className || "").toLowerCase();
    if (className.includes("react-flow__node")) break;
  }
  return false;
}

function branchContainsVideoOutputs(branch) {
  if (!branch?.querySelector) return false;
  try {
    return Boolean(branch.querySelector(
      '[data-parameter-name="PICKER_OUT"], '
      + '[data-parameter-name^="VIDEO"][data-parameter-name$="_OUT"], '
      + '.react-flow__handle[data-handleid="PICKER_OUT"], '
      + '.react-flow__handle[data-handleid^="VIDEO"][data-handleid$="_OUT"]',
    ));
  } catch (_error) {
    return false;
  }
}

function collapseBridgeHost(container) {
  if (!container?.style) return;
  container.setAttribute?.("aria-hidden", "true");
  container.style.setProperty("height", "0px", "important");
  container.style.setProperty("min-height", "0px", "important");
  container.style.setProperty("max-height", "0px", "important");
  container.style.setProperty("margin", "0", "important");
  container.style.setProperty("padding", "0", "important");
  container.style.setProperty("border", "0", "important");
  container.style.setProperty("overflow", "hidden", "important");
  container.style.setProperty("opacity", "0", "important");
  container.style.setProperty("pointer-events", "none", "important");
}

function commandBridgeLayoutRow(container) {
  if (!container) return null;
  let parameterRow = null;
  try {
    parameterRow = container.closest?.('[data-parameter-name="HMB_PICKER_COMMAND"]') || null;
  } catch (_error) {}
  if (!parameterRow) {
    let current = container.parentElement || null;
    for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
      if (String(current.getAttribute?.("data-parameter-name") || "") === "HMB_PICKER_COMMAND") {
        parameterRow = current;
        break;
      }
    }
  }
  if (!parameterRow?.style) return null;
  // Editor 0.122 mounts a visibility:hidden measurement copy of the complete
  // adaptive parameter stack.  Climbing from that copy to a branch that does
  // not contain the first (visible) STATE match can select the measurement
  // wrapper itself and collapse its height to zero.  That makes contentRef
  // report stackHeight=0 and the host auto-hides MAYA, COMMAND and STATE.
  // Inside the measurement copy, collapse only this exact command row.
  if (hmbVideoPickerCommandBridgeIsHostMeasurementClone(container)) return parameterRow;
  const shell = findReactFlowNode(container);
  let stateRow = null;
  try {
    stateRow = shell?.querySelector?.('[data-parameter-name="HMB_PICKER_STATE"]') || null;
  } catch (_error) {}
  let layoutRow = parameterRow;
  // Collapse the complete command-only branch, stopping immediately below the
  // first common ancestor shared with the visible Picker row. Griptape v119
  // inserts an extra wrapper around custom parameters; collapsing only
  // parameterRow.parentElement can leave that wrapper's 40px track behind.
  if (stateRow) {
    while (
      layoutRow.parentElement
      && layoutRow.parentElement !== shell
      && !layoutRow.parentElement.contains?.(stateRow)
      && !branchContainsVideoOutputs(layoutRow.parentElement)
    ) {
      layoutRow = layoutRow.parentElement;
    }
  } else if (
    parameterRow.parentElement
    && !branchContainsVideoOutputs(parameterRow.parentElement)
  ) {
    layoutRow = parameterRow.parentElement;
  }
  return layoutRow?.style ? layoutRow : null;
}

export function hmbCollapseCommandBridgeLayoutRow(container) {
  const layoutRow = commandBridgeLayoutRow(container);
  if (!layoutRow?.style) return 0;
  const storedHeight = Number(layoutRow.dataset?.hmbPickerCommandOriginalHeight || 0);
  const observedHeight = parseFloat(layoutRow.style.height || "") || Number(layoutRow.offsetHeight || 0);
  const reclaimedHeight = storedHeight > 0
    ? storedHeight
    : Math.max(0, Math.min(96, Math.round(observedHeight || 40)));
  if (!(reclaimedHeight > 0)) return 0;

  layoutRow.dataset.hmbPickerCommandOriginalHeight = String(reclaimedHeight);
  const parameterRow = container.closest?.('[data-parameter-name="HMB_PICKER_COMMAND"]') || null;
  if (parameterRow?.style && parameterRow !== layoutRow) {
    parameterRow.style.setProperty("height", "0px", "important");
    parameterRow.style.setProperty("min-height", "0px", "important");
    parameterRow.style.setProperty("max-height", "0px", "important");
    parameterRow.style.setProperty("margin", "0", "important");
    parameterRow.style.setProperty("padding", "0", "important");
    parameterRow.style.setProperty("overflow", "hidden", "important");
  }
  layoutRow.style.setProperty("height", "0px", "important");
  layoutRow.style.setProperty("min-height", "0px", "important");
  layoutRow.style.setProperty("max-height", "0px", "important");
  layoutRow.style.setProperty("flex", "0 0 0px", "important");
  layoutRow.style.setProperty("margin", "0", "important");
  layoutRow.style.setProperty("padding", "0", "important");
  layoutRow.style.setProperty("border", "0", "important");
  layoutRow.style.setProperty("overflow", "hidden", "important");
  const shell = findReactFlowNode(container);
  if (shell) shell.__hmbPickerCommandRowReclaim = reclaimedHeight;
  return reclaimedHeight;
}

export default function HMBVideoPickerCommandBridgeWidget(container, props) {
  if (!container) {
    return { cleanup() {}, update() {} };
  }
  if (typeof container.__hmbVideoPickerCommandBridgeCleanupProxy !== "function") {
    container.__hmbVideoPickerCommandBridgeCleanupProxy = () => {
      const cleanup = container.__hmbVideoPickerCommandBridgeCleanup;
      if (typeof cleanup === "function") cleanup();
    };
  }
  const previousCleanup = container.__hmbVideoPickerCommandBridgeCleanup;
  if (typeof previousCleanup === "function") previousCleanup();

  collapseBridgeHost(container);
  hmbCollapseCommandBridgeLayoutRow(container);
  const shell = findReactFlowNode(container);
  if (shell?.style && shell?.dataset?.hmbPickerBootstrapRecovered === "1") {
    // v022 used this hidden bridge to force the outer node size on timers.
    // Release those locks; leave width/height intact as the current native size.
    shell.style.removeProperty("min-width");
    shell.style.removeProperty("min-height");
    shell.style.removeProperty("max-width");
    shell.style.removeProperty("max-height");
    shell.style.removeProperty("overflow");
    shell.style.removeProperty("box-sizing");
    delete shell.dataset.hmbPickerBootstrapRecovered;
  }
  const token = `hmb-command-bridge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const dispatch = (rawCommand) => {
    if (!props || typeof props.onChange !== "function") {
      throw new Error("HMB_PICKER_COMMAND did not receive Griptape props.onChange.");
    }
    const source = rawCommand && typeof rawCommand === "object" ? rawCommand : {};
    const command = {
      schema: "hmb-picker-command",
      version: 1,
      runtime_instance_id: clean(source.runtime_instance_id),
      action: clean(source.action),
      action_id: clean(source.action_id),
      issued_at_ms: Math.max(0, Math.floor(Number(source.issued_at_ms || Date.now()))),
      payload: source.payload && typeof source.payload === "object"
        ? JSON.parse(JSON.stringify(source.payload))
        : {},
    };
    if (!command.runtime_instance_id || !command.action || !command.action_id) {
      throw new Error("HMB_PICKER_COMMAND requires runtime_instance_id, action, and action_id.");
    }
    return props.onChange(command);
  };

  if (shell) {
    shell.__hmbPickerCommandBridge = { token, dispatch };
  }
  container.__hmbVideoPickerCommandBridgeCleanup = () => {
    if (shell?.__hmbPickerCommandBridge?.token === token) {
      delete shell.__hmbPickerCommandBridge;
    }
    if (container.__hmbVideoPickerCommandBridgeCleanup) {
      delete container.__hmbVideoPickerCommandBridgeCleanup;
    }
  };

  return {
    cleanup: container.__hmbVideoPickerCommandBridgeCleanupProxy,
    update(nextProps) {
      HMBVideoPickerCommandBridgeWidget(container, nextProps || {});
    },
  };
}
