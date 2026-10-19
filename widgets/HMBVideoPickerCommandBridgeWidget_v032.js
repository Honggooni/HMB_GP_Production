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

function hmbNativeUiImplementation(container, props) {
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


// HMB_NATIVE_DISABLED_ADAPTER_V1_BEGIN -- identical module-local adapter.
const HMB_NATIVE_UI_CALLBACKS = new WeakMap();
function hmbNativeUiReadCommand(value, kind) {
  let v = value;
  if (typeof v === "string") { try { v = JSON.parse(v); } catch { return false; } }
  if (!v || typeof v !== "object") return false;
  if (kind === "thumbnail") return v.schema === "hmb-image-asset-thumbnail-bridge"
    && ["hydrate", "catalog_probe", "catalog_page"].includes(v.operation);
  if (kind === "seedance") return (v.schema === "hmb-seedance-refresh-command"
    && ["refresh_existing", "cancel_draft_final", "open_gallery"].includes(v.action))
    || (v.schema === "hmb-seedance-render-preflight" && ["inspect", "cancel"].includes(v.action))
    || (v.schema === "hmb-seedance-shot-ui" && v.request?.action === "refresh_existing");
  if (kind === "agent") return v.schema === "hmb-agent-shot-row"
    && ["refresh", "cancel_selected"].includes(v.action?.kind);
  if (kind === "finish") return v.ui_transport?.schema === "hmb-finish-ui-transport"
    && v.ui_transport.operation === "refresh";
  if (kind === "lut") return (v.__hmb_color_lut_command__ || v).action === "cancel";
  const command = v.__hmb_picker_command__ || v;
  return ["picker", "picker-bridge"].includes(kind) && command.schema === "hmb-picker-command"
    && (["stop_read", "cancel_pending", "cancel_video_import"].includes(command.action)
      || (command.action === "video_tools" && command.payload?.op === "cancel"));
}
function hmbNativeUiContract(container, props, mount, policy) {
  if (!container) return mount(container, props);
  let c = container.__hmbNativeUiContract;
  if (c && c.kind !== policy.kind) { c.proxy.cleanup(); c = null; }
  if (!c) {
    c = { kind: policy.kind, active: true, props: {}, handle: null, originals: new Map(), observer: null, listening: false };
    const events = ["pointerdown", "mousedown", "click", "dblclick", "keydown", "beforeinput", "input", "change", "paste", "drop", "dragstart", "submit"];
    c.allowed = target => Boolean(target?.matches?.("video,audio")) || Boolean(policy.allowControl?.(target, c.props, container));
    c.guard = event => {
      if (!c.active || !c.props.disabled || c.allowed(event.target)) return;
      event.preventDefault?.(); event.stopImmediatePropagation?.(); event.stopPropagation?.();
    };
    c.restore = () => {
      c.observer?.disconnect?.();
      if (c.listening) { for (const name of events) container.removeEventListener?.(name, c.guard, true); c.listening = false; }
      for (const [el, old] of c.originals) {
        if ("disabled" in el && el.disabled !== old.disabled) el.disabled = old.disabled;
        if (old.editable !== null && el.getAttribute?.("contenteditable") !== old.editable) el.setAttribute?.("contenteditable", old.editable);
      }
      c.originals.clear();
    };
    c.sync = () => {
      // The normal enabled path adds no observers, DOM queries/writes or timers.
      if (!c.active || !c.props.disabled) return;
      if (!c.listening) { for (const name of events) container.addEventListener?.(name, c.guard, true); c.listening = true; }
      for (const [el] of c.originals) if (container.contains && !container.contains(el)) c.originals.delete(el);
      for (const el of container.querySelectorAll?.("button,input,select,textarea,[contenteditable='true']") || []) {
        if (c.allowed(el)) continue;
        if (!c.originals.has(el)) c.originals.set(el, { disabled: Boolean(el.disabled), editable: el.getAttribute?.("contenteditable") ?? null });
        if ("disabled" in el && !el.disabled) el.disabled = true;
        if (el.getAttribute?.("contenteditable") === "true") el.setAttribute?.("contenteditable", "false");
      }
      if (!c.observer) {
        const Observer = container.ownerDocument?.defaultView?.MutationObserver;
        if (Observer) c.observer = new Observer(() => c.sync());
      }
      c.observer?.observe?.(container, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "contenteditable"] });
    };
    c.wrap = () => {
      const p = { ...c.props };
      for (const name of ["onChange", "onCommand"]) if (typeof p[name] === "function") {
        const callback = HMB_NATIVE_UI_CALLBACKS.get(p[name]) || p[name];
        const fn = (...args) => {
          if (!c.active) throw new Error("This widget is no longer mounted.");
          if (c.props.disabled && !hmbNativeUiReadCommand(args[0], c.kind)) throw new Error("This control is disabled by Griptape.");
          return callback?.(...args);
        };
        HMB_NATIVE_UI_CALLBACKS.set(fn, HMB_NATIVE_UI_CALLBACKS.get(p[name]) || p[name]); p[name] = fn;
      }
      return p;
    };
    c.proxy = {
      update(nextProps) {
        if (!c.active || c.closing) return;
        c.restore(); c.props = nextProps || {}; const next = c.wrap();
        if (typeof c.handle?.update === "function") c.handle.update(next);
        else c.handle = mount(container, next);
        c.sync();
      },
      cleanup() {
        if (!c.active || c.closing) return; c.closing = true; c.restore();
        try {
          // Preserve the implementation's synchronous final authored-value flush.
          if (typeof c.handle === "function") c.handle(); else c.handle?.cleanup?.();
        } finally {
          c.active = false;
          if (container.__hmbNativeUiContract === c) delete container.__hmbNativeUiContract;
        }
      },
    };
    container.__hmbNativeUiContract = c;
  }
  c.restore(); c.props = props || c.props || {}; c.handle = mount(container, c.wrap()); c.sync(); return c.proxy;
}
// HMB_NATIVE_DISABLED_ADAPTER_V1_END

export default function HMBVideoPickerCommandBridgeWidget(container, props) {
  return hmbNativeUiContract(container, props, hmbNativeUiImplementation, { kind: "picker-bridge", allowControl: null });
}
