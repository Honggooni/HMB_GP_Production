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

const HMB_VIDEO_PICKER_COMMAND_BRIDGE_REGISTRY_KEY = "__hmbVideoPickerCommandBridgeRegistryV1";

function commandBridgeRegistry() {
  const owner = typeof globalThis !== "undefined" ? globalThis : null;
  if (!owner) return null;
  if (!(owner[HMB_VIDEO_PICKER_COMMAND_BRIDGE_REGISTRY_KEY] instanceof Map)) {
    owner[HMB_VIDEO_PICKER_COMMAND_BRIDGE_REGISTRY_KEY] = new Map();
  }
  return owner[HMB_VIDEO_PICKER_COMMAND_BRIDGE_REGISTRY_KEY];
}

function commandValueFromProps(props) {
  const raw = props?.value ?? props?.defaultValue ?? {};
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
  try {
    const parsed = JSON.parse(String(raw || "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (_error) {
    return {};
  }
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
  }
  return false;
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

export function hmbCollapseCommandBridgeLayoutRow(container) {
  // The parameter's Python ui_options own its one-pixel hidden row. Never
  // collapse a Griptape layout ancestor from the browser widget.
  void container;
  return 0;
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

  const runtimeInstanceId = clean(commandValueFromProps(props).runtime_instance_id);
  const registry = commandBridgeRegistry();
  if (runtimeInstanceId && !hmbVideoPickerCommandBridgeIsHostMeasurementClone(container)) {
    registry?.set(runtimeInstanceId, { token, dispatch });
  }
  container.__hmbVideoPickerCommandBridgeCleanup = () => {
    if (runtimeInstanceId && registry?.get(runtimeInstanceId)?.token === token) {
      registry.delete(runtimeInstanceId);
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
