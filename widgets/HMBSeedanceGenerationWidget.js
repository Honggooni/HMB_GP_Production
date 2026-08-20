const HMB_SHOT_ONLY_KEY = "__hmb_shot_only__";

export const HMB_SEEDANCE_JEWEL_NIGHT_PALETTE = Object.freeze({
  1: "#F472B6",
  2: "#3B82F6",
  3: "#10B981",
  4: "#8B5CF6",
  5: "#EAB308",
});

const SHOT_THEME = Object.freeze({
  1: Object.freeze({ rgb: "244,114,182", soft: "#FBCFE8" }),
  2: Object.freeze({ rgb: "59,130,246", soft: "#DBEAFE" }),
  3: Object.freeze({ rgb: "16,185,129", soft: "#D1FAE5" }),
  4: Object.freeze({ rgb: "139,92,246", soft: "#EDE9FE" }),
  5: Object.freeze({ rgb: "234,179,8", soft: "#FEF3C7" }),
});

function text(value, limit = 128) {
  return String(value ?? "").trim().replace(/\s+/g, " ").slice(0, limit);
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
}

export function hmbSeedanceNextChangeOwner(container) {
  const next = Math.max(0, Number(container?.__hmbSeedanceChangeOwner) || 0) + 1;
  if (container) container.__hmbSeedanceChangeOwner = next;
  return next;
}

export function hmbSeedanceOwnsChange(container, owner) {
  return Math.max(0, Number(container?.__hmbSeedanceChangeOwner) || 0) === owner;
}

function uuid(value) {
  const normalized = text(value).toLowerCase();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(normalized)
    ? normalized : "";
}

export function hmbSeedanceShotCatalog(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  if (JSON.stringify(Object.keys(source).sort()) !== JSON.stringify([
    "channel_uuid", "generation", "metadata_sha256", "publisher_instance_uuid",
    "schema", "shots", "version",
  ])) return {};
  const publisher = uuid(source.publisher_instance_uuid);
  const channel = uuid(source.channel_uuid);
  const generation = Number(source.generation);
  const metadataSha256 = text(source.metadata_sha256, 64).toLowerCase();
  if (
    source.schema !== "hmb-shot-routing-catalog"
    || source.version !== 1
    || !publisher
    || !channel
    || !Number.isSafeInteger(generation)
    || generation < 1
    || !/^[0-9a-f]{64}$/.test(metadataSha256)
    || !Array.isArray(source.shots)
    || source.shots.length < 1
    || source.shots.length > 5
  ) return {};
  const shotIds = new Set();
  const numbers = new Set();
  const shots = [];
  for (const raw of source.shots) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    if (JSON.stringify(Object.keys(raw).sort()) !== JSON.stringify([
      "name", "number", "revision", "shot_uuid",
    ])) return {};
    const shotUuid = uuid(raw.shot_uuid);
    const number = Number(raw.number);
    const name = text(raw.name);
    const revision = Number(raw.revision);
    if (
      !shotUuid
      || shotIds.has(shotUuid)
      || !Number.isInteger(number)
      || number < 1
      || number > 5
      || numbers.has(number)
      || !name
      || name !== raw.name
      || !Number.isSafeInteger(revision)
      || revision < 0
    ) return {};
    shotIds.add(shotUuid);
    numbers.add(number);
    shots.push({ shot_uuid: shotUuid, number, name, revision });
  }
  shots.sort((left, right) => left.number - right.number || left.shot_uuid.localeCompare(right.shot_uuid));
  return {
    schema: "hmb-shot-routing-catalog",
    version: 1,
    publisher_instance_uuid: publisher,
    channel_uuid: channel,
    generation,
    metadata_sha256: metadataSha256,
    shots,
  };
}

export function hmbSeedanceShotState(props) {
  const candidate = props?.value ?? props?.parameterValue ?? props?.defaultValue;
  let raw = candidate;
  if (typeof candidate === "string") {
    try { raw = JSON.parse(candidate); } catch { raw = {}; }
  }
  const source = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const catalog = hmbSeedanceShotCatalog(source.shot_catalog);
  const requested = source.shot && typeof source.shot === "object" ? source.shot : {};
  const requestedChannel = uuid(requested.channel_uuid);
  const requestedUuid = uuid(requested.shot_uuid);
  const requestedSelection = catalog.channel_uuid === requestedChannel
    ? catalog.shots?.find((shot) => shot.shot_uuid === requestedUuid) || null
    : null;
  const selected = requestedSelection || null;
  return {
    schema: "hmb-seedance-shot-ui",
    schema_version: 1,
    shot_catalog: catalog,
    shot: selected ? {
      channel_uuid: catalog.channel_uuid,
      shot_uuid: selected.shot_uuid,
      number: selected.number,
      name: selected.name,
    } : {
      channel_uuid: "",
      shot_uuid: "",
      number: 1,
      name: "Only",
    },
  };
}

export function hmbSeedanceShotOptions(state) {
  const catalog = state?.shot_catalog;
  const options = [{
    key: HMB_SHOT_ONLY_KEY,
    channel_uuid: "",
    shot_uuid: "",
    number: 1,
    name: "Only",
    only: true,
    waiting: false,
  }];
  if (!catalog?.channel_uuid || !Array.isArray(catalog.shots) || !catalog.shots.length) {
    return options;
  }
  for (const shot of catalog.shots) {
    options.push({
      key: `${catalog.channel_uuid}\u001f${shot.shot_uuid}`,
      channel_uuid: catalog.channel_uuid,
      ...shot,
      waiting: false,
    });
  }
  return options;
}

export function hmbSeedancePaletteShotNumber(state) {
  const shot = state?.shot && typeof state.shot === "object" ? state.shot : {};
  const catalog = state?.shot_catalog && typeof state.shot_catalog === "object"
    ? state.shot_catalog : {};
  if (!shot.channel_uuid || !shot.shot_uuid || catalog.channel_uuid !== shot.channel_uuid) return 1;
  const selected = (catalog.shots || []).find((item) => item.shot_uuid === shot.shot_uuid);
  return selected && HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[selected.number] ? selected.number : 1;
}

export function hmbSeedanceShotAccent(state) {
  return HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[hmbSeedancePaletteShotNumber(state)];
}

function optionLabel(item) {
  if (item.only) return "Only";
  return `${String(item.number).padStart(2, "0")} · ${item.name}`;
}

function optionMarkup(state) {
  const currentKey = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}` : HMB_SHOT_ONLY_KEY;
  return hmbSeedanceShotOptions(state).map((item) => {
    const label = optionLabel(item);
    return `<option value="${escapeHtml(item.key)}"${item.key === currentKey ? " selected" : ""}${item.waiting ? " disabled" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

export function hmbSeedanceSyncShotSelect(select, state) {
  if (!select) return false;
  const desired = hmbSeedanceShotOptions(state).map((item) => ({
    value: item.key,
    label: optionLabel(item),
  }));
  const current = Array.from(select.options || []);
  const optionsChanged = current.length !== desired.length || desired.some((item, index) => {
    const option = current[index];
    return !option
      || String(option.value) !== item.value
      || String(option.textContent ?? option.text ?? "") !== item.label;
  });
  if (optionsChanged) select.innerHTML = optionMarkup(state);
  const expected = state.shot.channel_uuid && state.shot.shot_uuid
    ? `${state.shot.channel_uuid}\u001f${state.shot.shot_uuid}`
    : HMB_SHOT_ONLY_KEY;
  if (String(select.value || "") !== expected) select.value = expected;
  select.disabled = false;
  return optionsChanged;
}

function hmbSeedanceSetStatus(container, message = "", detail = "") {
  const status = container?.querySelector?.(".hmb-seedance-shot__status");
  if (!status) return false;
  status.textContent = String(message || "");
  status.setAttribute?.("title", message ? String(detail?.message || detail || message) : "");
  return true;
}

function render(state) {
  const number = hmbSeedancePaletteShotNumber(state);
  const accent = HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[number];
  const theme = SHOT_THEME[number];
  return `
    <style>
      .hmb-seedance-shot{--shot-accent:${accent};--shot-rgb:${theme.rgb};--shot-soft:${theme.soft};position:relative;width:100%;height:64px;overflow:hidden;box-sizing:border-box;border:1px solid rgba(var(--shot-rgb),.5);border-radius:11px;background:radial-gradient(circle at 8% -45%,rgba(var(--shot-rgb),.25),transparent 54%),linear-gradient(90deg,rgba(var(--shot-rgb),.2),rgba(14,23,38,.96) 46%,#060912);color:#e6edf7;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 24px rgba(0,0,0,.24),0 0 18px rgba(var(--shot-rgb),.18);font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none}
      .hmb-seedance-shot *{box-sizing:border-box;min-width:0}.hmb-seedance-shot__row{height:100%;display:flex;align-items:center;gap:11px;padding:8px 13px}.hmb-seedance-shot__mark{flex:0 0 35px;width:35px;height:35px;display:grid;place-items:center;border:1px solid rgba(var(--shot-rgb),.52);border-radius:8px;background:linear-gradient(145deg,rgba(var(--shot-rgb),.14),rgba(5,9,16,.86));color:var(--shot-accent);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px rgba(var(--shot-rgb),.19);font-size:9px;font-weight:950;letter-spacing:.06em}.hmb-seedance-shot__title{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e6edf7;font-size:14px;font-weight:850}.hmb-seedance-shot__status{flex:0 1 190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fb7185;font-size:8px;font-weight:800;text-align:right}.hmb-seedance-shot__status:empty{display:none}.hmb-seedance-shot__select{flex:0 1 210px;width:210px;height:29px;margin-left:auto;padding:0 28px 0 10px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;outline:none;background:linear-gradient(180deg,rgba(255,255,255,.04),transparent),rgba(var(--shot-rgb),.16);color:var(--shot-soft);box-shadow:inset 0 1px 0 rgba(255,255,255,.045),0 0 12px rgba(var(--shot-rgb),.18);font:inherit;font-size:10px;font-weight:850;letter-spacing:.035em}.hmb-seedance-shot__select:focus{border-color:var(--shot-accent);box-shadow:0 0 0 2px rgba(var(--shot-rgb),.18)}.hmb-seedance-shot__select option{background:#0b1020;color:#e6edf7}@container(max-width:360px){.hmb-seedance-shot__status{display:none}.hmb-seedance-shot__select{flex-basis:120px;width:120px}.hmb-seedance-shot__title{font-size:12px}}
      /* Match the Prompt header while preserving the existing selector position and responsive width. */
      .hmb-seedance-shot__title{font-size:15px;font-weight:800;letter-spacing:.01em;line-height:normal}
      .hmb-seedance-shot__select{height:44px;font-size:13px;font-weight:800;line-height:normal}
      .hmb-seedance-shot__number{flex:0 0 auto;min-width:34px;padding:5px 7px;border:1px solid rgba(var(--shot-rgb),.52);border-radius:7px;color:var(--shot-soft);font-size:11px;font-weight:900;text-align:center}
    </style>
    <div class="hmb-seedance-shot nodrag" data-shot-number="${number}">
      <div class="hmb-seedance-shot__row">
        <div class="hmb-seedance-shot__mark" aria-hidden="true">SD</div>
        <div class="hmb-seedance-shot__title">HMBSeedanceGeneration</div>
        <span class="hmb-seedance-shot__status" role="status" aria-live="polite" aria-atomic="true"></span>
        <span class="hmb-seedance-shot__number" data-seedance-shot-number>${state.shot.shot_uuid ? String(state.shot.number).padStart(2, "0") : "Only"}</span>
        <select class="hmb-seedance-shot__select nodrag" aria-label="Shot">${optionMarkup(state)}</select>
      </div>
    </div>`;
}

function compactHost(container) {
  if (!container?.style) return;
  for (const [name, value] of [
    ["height", "64px"], ["min-height", "64px"], ["max-height", "64px"],
    ["flex", "0 0 64px"], ["flex-basis", "64px"], ["overflow", "hidden"],
    ["box-sizing", "border-box"],
  ]) container.style.setProperty(name, value, "important");
  container.classList?.remove("nopan", "nowheel");
  container.classList?.add("nodrag");
}

function hmbSeedanceNodeRoot(container) {
  let current = container?.parentElement || null;
  for (let depth = 0; current && depth < 16; depth += 1, current = current.parentElement) {
    const className = String(current.className || "").toLowerCase();
    const testId = String(current.getAttribute?.("data-testid") || "").toLowerCase();
    if (className.includes("react-flow__node") || testId === "node") return current;
    if (className.includes("react-flow__pane") || className.includes("react-flow__viewport")) return null;
  }
  return null;
}

function hmbSeedanceNodeSelected(root) {
  if (!root) return false;
  return root.classList?.contains("selected")
    || String(root.getAttribute?.("aria-selected") || "").toLowerCase() === "true"
    || String(root.getAttribute?.("data-selected") || "").toLowerCase() === "true"
    || Boolean(root.querySelector?.(
      ".react-flow__resize-control,.react-flow__node-resizer,[class*='node-resizer']",
    ));
}

export function hmbGuardSelectedNodeKeyboardDelete(container, event) {
  if (!["Backspace", "Delete"].includes(event?.key)) return false;
  if (event?.target?.closest?.("[data-hmb-node-delete-protected='true']")) return false;
  if (event?.target?.closest?.(
    "input,textarea,select,[contenteditable='true'],[contenteditable=''],[role='textbox'],.CodeMirror,.cm-editor",
  )) return false;
  if (!hmbSeedanceNodeSelected(hmbSeedanceNodeRoot(container))) return false;
  event.preventDefault?.();
  event.stopPropagation?.();
  event.stopImmediatePropagation?.();
  return true;
}

function refresh(container, props) {
  const root = container?.querySelector?.(".hmb-seedance-shot");
  if (!root) return false;
  compactHost(container);
  const state = hmbSeedanceShotState(props);
  const number = hmbSeedancePaletteShotNumber(state);
  const theme = SHOT_THEME[number];
  root.dataset.shotNumber = String(number);
  root.style.setProperty("--shot-accent", HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[number]);
  root.style.setProperty("--shot-rgb", theme.rgb);
  root.style.setProperty("--shot-soft", theme.soft);
  const select = root.querySelector?.(".hmb-seedance-shot__select");
  if (select) hmbSeedanceSyncShotSelect(select, state);
  const numberBadge = root.querySelector?.("[data-seedance-shot-number]");
  if (numberBadge) {
    numberBadge.textContent = state.shot.shot_uuid
      ? String(state.shot.number).padStart(2, "0")
      : "Only";
  }
  const error = container.__hmbSeedanceShotChangeError || "";
  hmbSeedanceSetStatus(
    container,
    error ? "Save failed · previous Shot restored" : "",
    error,
  );
  return true;
}

export default function HMBSeedanceGenerationWidget(container, props) {
  if (!container) return { cleanup() {}, update() {} };
  const latest = props || container.__hmbSeedanceLatestProps || {};
  container.__hmbSeedanceLatestProps = latest;
  const previousCleanup = container.__hmbSeedanceCleanup;
  // A factory call with new props is an authoritative lifecycle refresh, just
  // like update(). Invalidate any optimistic promise before accepting it so a
  // late rejection cannot roll the refreshed selector back.
  if (typeof previousCleanup === "function") hmbSeedanceNextChangeOwner(container);
  if (typeof previousCleanup === "function" && refresh(container, latest)) {
    return {
      cleanup: container.__hmbSeedanceCleanupProxy,
      update(nextProps) {
        hmbSeedanceNextChangeOwner(container);
        container.__hmbSeedanceLatestProps = nextProps || container.__hmbSeedanceLatestProps || {};
        if (!refresh(container, container.__hmbSeedanceLatestProps)) {
          HMBSeedanceGenerationWidget(container, container.__hmbSeedanceLatestProps);
        }
      },
    };
  }
  if (typeof previousCleanup === "function") previousCleanup();
  if (typeof container.__hmbSeedanceCleanupProxy !== "function") {
    container.__hmbSeedanceCleanupProxy = () => {
      const cleanup = container.__hmbSeedanceCleanup;
      if (typeof cleanup === "function") cleanup();
    };
  }
  compactHost(container);
  container.innerHTML = render(hmbSeedanceShotState(latest));
  const select = container.querySelector?.(".hmb-seedance-shot__select");
  const onShotChange = () => {
    const liveProps = container.__hmbSeedanceLatestProps || {};
    const previousProps = liveProps;
    const previousState = hmbSeedanceShotState(liveProps);
    const selected = hmbSeedanceShotOptions(previousState).find((item) => item.key === select?.value);
    if (!selected || typeof liveProps.onChange !== "function") {
      refresh(container, liveProps);
      return;
    }
    const next = hmbSeedanceShotState(liveProps);
    if (selected.waiting) {
      refresh(container, liveProps);
      return;
    }
    next.shot = {
      channel_uuid: selected.channel_uuid,
      shot_uuid: selected.shot_uuid,
      number: selected.number,
      name: selected.name,
    };
    const owner = hmbSeedanceNextChangeOwner(container);
    const optimisticProps = { ...liveProps, value: next, parameterValue: next, defaultValue: next };
    const accept = () => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      container.__hmbSeedanceLatestProps = optimisticProps;
      delete container.__hmbSeedanceShotChangeError;
      refresh(container, optimisticProps);
    };
    const rollback = (error) => {
      if (!hmbSeedanceOwnsChange(container, owner)) return;
      container.__hmbSeedanceLatestProps = previousProps;
      container.__hmbSeedanceShotChangeError = String(
        error?.message || error || "Shot selection publication failed",
      );
      refresh(container, previousProps);
    };
    let result;
    try { result = liveProps.onChange(next); } catch (error) { rollback(error); return; }
    accept();
    if (result && typeof result.then === "function") Promise.resolve(result).catch(rollback);
  };
  select?.addEventListener?.("change", onShotChange);
  const guardDelete = (event) => hmbGuardSelectedNodeKeyboardDelete(container, event);
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("keydown", guardDelete, true);
  }
  const stopInteriorDelete = (event) => {
    if (["Backspace", "Delete"].includes(event?.key)) event.stopPropagation?.();
  };
  const stopInteriorSelection = (event) => event.stopPropagation?.();
  container.addEventListener?.("keydown", stopInteriorDelete);
  container.addEventListener?.("pointerdown", stopInteriorSelection);
  const cleanup = () => {
    if (typeof window !== "undefined" && typeof window.removeEventListener === "function") {
      window.removeEventListener("keydown", guardDelete, true);
    }
    container.removeEventListener?.("keydown", stopInteriorDelete);
    container.removeEventListener?.("pointerdown", stopInteriorSelection);
    select?.removeEventListener?.("change", onShotChange);
    if (container.__hmbSeedanceCleanup === cleanup) delete container.__hmbSeedanceCleanup;
    delete container.__hmbSeedanceLatestProps;
    delete container.__hmbSeedanceShotChangeError;
    // Invalidate promise callbacks from this lifecycle without resetting the
    // monotonic token. A remount can otherwise reuse owner=1 and let an old
    // rejection roll the new selector back.
    hmbSeedanceNextChangeOwner(container);
    container.innerHTML = "";
  };
  container.__hmbSeedanceCleanup = cleanup;
  return {
    cleanup: container.__hmbSeedanceCleanupProxy,
    update(nextProps) {
      hmbSeedanceNextChangeOwner(container);
      container.__hmbSeedanceLatestProps = nextProps || container.__hmbSeedanceLatestProps || {};
      if (!refresh(container, container.__hmbSeedanceLatestProps)) {
        HMBSeedanceGenerationWidget(container, container.__hmbSeedanceLatestProps);
      }
    },
  };
}
