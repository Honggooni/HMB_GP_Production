/** Static HMB header. Native SDK parameters own all image controls and state. */
const mountedHeaders = new WeakMap();
const headerHostStyles = [
  ["height", "64px"], ["min-height", "64px"], ["max-height", "64px"],
  ["flex-grow", "0"], ["flex-shrink", "0"], ["flex-basis", "64px"], ["box-sizing", "border-box"],
];

function compactHeaderHost(element) {
  if (!element.style) return;
  for (const [name, value] of headerHostStyles) {
    if (element.style.getPropertyValue(name) !== value || element.style.getPropertyPriority(name) !== "important") {
      element.style.setProperty(name, value, "important");
    }
  }
}

export default function HMBImageGenerationWidget(element, _context) {
  if (!element?.ownerDocument) return { update() {}, cleanup() {} };
  const current = mountedHeaders.get(element);
  if (current?.active && current.header.parentNode === element) {
    compactHeaderHost(element);
    return current.handle;
  }
  current?.handle.cleanup();

  // The editor's widget carrier reserves its own minimum height. Sizing only
  // the painted header leaves that reservation below it (the blank strip).
  // Compact only our carrier; do not resize the node, its parents or controls.
  const originalHostStyles = headerHostStyles.map(([name]) => [
    name, element.style?.getPropertyValue(name) || "", element.style?.getPropertyPriority(name) || "",
  ]);
  compactHeaderHost(element);

  const header = element.ownerDocument.createElement("div");
  header.className = "hmb-image-generation-header";
  header.setAttribute("aria-label", "HMBImageGeneration");
  header.innerHTML = `
    <style>
      .hmb-image-generation-header{
        position:relative;box-sizing:border-box;width:100%;min-width:0;
        height:64px;min-height:64px;max-height:64px;overflow:hidden;
        border:1px solid rgba(244,114,182,.5);border-radius:11px;
        background:radial-gradient(circle at 8% -45%,rgba(244,114,182,.25),transparent 54%),linear-gradient(90deg,rgba(244,114,182,.2),rgba(14,23,38,.96) 46%,#060912);
        color:#e6edf7;box-shadow:inset 0 1px 0 rgba(255,255,255,.04),0 8px 24px rgba(0,0,0,.24),0 0 18px rgba(244,114,182,.18);
        font-family:"Pretendard Variable",Pretendard,Inter,"Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;
        user-select:none;pointer-events:none;
      }
      .hmb-image-generation-header__row{
        box-sizing:border-box;height:100%;min-width:0;display:flex;
        align-items:center;gap:11px;padding:8px 13px;
      }
      .hmb-image-generation-header__badge{
        box-sizing:border-box;flex:0 0 35px;width:35px;height:35px;
        display:grid;place-items:center;border:1px solid rgba(244,114,182,.52);
        border-radius:8px;background:linear-gradient(145deg,rgba(244,114,182,.14),rgba(5,9,16,.86));
        color:#F472B6;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 0 12px rgba(244,114,182,.19);
        font-size:9px;font-weight:950;letter-spacing:.06em;
      }
      .hmb-image-generation-header__title{
        box-sizing:border-box;flex:1 1 auto;min-width:0;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap;color:#e6edf7;font-size:14px;font-weight:850;
      }
    </style>
    <div class="hmb-image-generation-header__row">
      <span class="hmb-image-generation-header__badge" aria-hidden="true">IG</span>
      <span class="hmb-image-generation-header__title">HMBImageGeneration</span>
    </div>`;
  element.appendChild(header);

  const state = { active: true, header, handle: null };
  const handle = {
    // The header is deliberately independent of task/provider/lock changes.
    update() { if (state.active) compactHeaderHost(element); },
    cleanup() {
      if (!state.active) return;
      state.active = false;
      if (header.parentNode === element) header.remove();
      if (mountedHeaders.get(element) === state) {
        mountedHeaders.delete(element);
        for (const [name, value, priority] of originalHostStyles) {
          const owned = headerHostStyles.find(([property]) => property === name)?.[1];
          if (element.style?.getPropertyValue(name) !== owned || element.style?.getPropertyPriority(name) !== "important") continue;
          if (value) element.style.setProperty(name, value, priority);
          else element.style.removeProperty(name);
        }
      }
    },
  };
  state.handle = handle;
  mountedHeaders.set(element, state);
  return handle;
}
