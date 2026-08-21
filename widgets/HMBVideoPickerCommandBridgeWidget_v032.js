// HMB VideoPicker command bridge cache version v040-state-row-isolation.
// This hidden transport never traverses or mutates a Griptape/React Flow host.

const HMB_VIDEO_PICKER_COMMAND_REGISTRY_KEY = "__HMB_VIDEO_PICKER_COMMAND_BRIDGES_V1__";

function clean(value) {
  return String(value == null ? "" : value).trim();
}

function commandRegistry() {
  const root = typeof globalThis !== "undefined" ? globalThis : null;
  if (!root) return null;
  if (!(root[HMB_VIDEO_PICKER_COMMAND_REGISTRY_KEY] instanceof Map)) {
    root[HMB_VIDEO_PICKER_COMMAND_REGISTRY_KEY] = new Map();
  }
  return root[HMB_VIDEO_PICKER_COMMAND_REGISTRY_KEY];
}

export function hmbVideoPickerCommandBridgeRegistry() {
  return commandRegistry();
}

// Compatibility exports are deliberately inert. Older host bundles may keep
// these function references cached, but no bridge is allowed to touch a row,
// branch, or React Flow shell anymore.
export function hmbVideoPickerCommandBridgeIsHostMeasurementClone(_container) {
  return false;
}

export function hmbCollapseCommandBridgeLayoutRow(container) {
  makeContainerInert(container);
  return 0;
}

function makeContainerInert(container) {
  if (!container?.style) return;
  container.setAttribute?.("aria-hidden", "true");
  for (const [property, value] of [
    ["height", "0px"],
    ["min-height", "0px"],
    ["max-height", "0px"],
    ["margin", "0"],
    ["padding", "0"],
    ["border", "0"],
    ["overflow", "hidden"],
    ["opacity", "0"],
    ["pointer-events", "none"],
  ]) container.style.setProperty?.(property, value, "important");
}

function bridgeValue(props) {
  const value = props?.value;
  return value && typeof value === "object" ? value : {};
}

export default function HMBVideoPickerCommandBridgeWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  if (typeof container.__hmbVideoPickerCommandBridgeCleanupProxy !== "function") {
    container.__hmbVideoPickerCommandBridgeCleanupProxy = () => {
      container.__hmbVideoPickerCommandBridgeCleanup?.();
    };
  }
  container.__hmbVideoPickerCommandBridgeCleanup?.();
  makeContainerInert(container);

  let latestProps = props || {};
  let runtimeId = "";
  const token = `hmb-command-bridge-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const registry = commandRegistry();

  const dispatch = (rawCommand) => {
    if (!latestProps || typeof latestProps.onChange !== "function") {
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
    return latestProps.onChange(command);
  };

  const register = (nextRuntimeId) => {
    const nextId = clean(nextRuntimeId);
    if (runtimeId && registry?.get(runtimeId)?.token === token) registry.delete(runtimeId);
    runtimeId = nextId;
    if (runtimeId && registry) registry.set(runtimeId, { token, dispatch });
  };
  register(bridgeValue(latestProps).runtime_instance_id);

  const cleanup = () => {
    if (runtimeId && registry?.get(runtimeId)?.token === token) registry.delete(runtimeId);
    if (container.__hmbVideoPickerCommandBridgeCleanup === cleanup) {
      delete container.__hmbVideoPickerCommandBridgeCleanup;
    }
  };
  container.__hmbVideoPickerCommandBridgeCleanup = cleanup;

  return {
    cleanup: container.__hmbVideoPickerCommandBridgeCleanupProxy,
    update(nextProps) {
      latestProps = nextProps || {};
      register(bridgeValue(latestProps).runtime_instance_id);
      makeContainerInert(container);
    },
  };
}
