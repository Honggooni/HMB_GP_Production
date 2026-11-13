(() => {
  // Full approved card bounds in sheet pixels, including the antialiased edge.
  const launcherSheets = [
    { url: "__HMB_RODONG_MART_ARTWORK__", sheetWidth: 1199, sheetHeight: 1312, cards: [
      [24, 68, 568, 210], [607, 68, 569, 210],
      [25, 317, 567, 212], [607, 317, 569, 212],
      [25, 568, 568, 205], [607, 568, 569, 205],
      [25, 812, 568, 197], [607, 812, 569, 197],
      [25, 1048, 568, 221], [607, 1048, 569, 221],
    ] },
    { url: "__HMB_RODONG_MART_EXTRA_ARTWORK__", sheetWidth: 930, sheetHeight: 1692, cards: [
      [11, 48, 908, 297], [11, 387, 909, 290], [11, 721, 909, 293],
      [11, 1055, 909, 274], [11, 1370, 909, 299],
    ] },
  ];
  const launcherCards = launcherSheets.flatMap(({ cards, ...sheet }, sheetIndex) => cards.map(rect => ({ ...sheet, sheetIndex, rect })));
  const headerArtwork = "__HMB_RODONG_MART_HEADER_ARTWORK__";
  // The separate header sheet has fifteen 160px-wide illustrations in padded cells.
  const headerHeights = [112, 112, 114, 113, 106, 105, 101, 101, 114, 114, 92, 90, 91, 85, 92];
  let previousLauncherCard = -1;
  let previousHeaderCard = -1;
  const popupHeaders = new WeakMap();
  function nextArtwork(previous) {
    const draw = Math.floor(Math.random() * (launcherCards.length - Number(previous >= 0)));
    return draw + Number(previous >= 0 && draw >= previous);
  }
  function setArtworkCrop(node, { sheetWidth, sheetHeight, rect: [x, y, width, height] }) {
    node.style.setProperty("--hmb-mart-ratio", `${width} / ${height}`);
    node.style.setProperty("--hmb-mart-size", `${sheetWidth / width * 100}% ${sheetHeight / height * 100}%`);
    node.style.setProperty("--hmb-mart-position", `${x / (sheetWidth - width) * 100}% ${y / (sheetHeight - height) * 100}%`);
  }
  function applyLauncherArtwork(node, index) {
    const artwork = launcherCards[index];
    const { url, sheetIndex } = artwork;
    setArtworkCrop(node, artwork);
    // Clip the atlas background outside the illustrated rounded card. Keep the
    // button and its hover label unclipped, including on small viewports.
    const [, , width, height] = artwork.rect;
    const inset = sheetIndex === 0 ? 2 : 3;
    const radius = sheetIndex === 0 ? 28 : 40;
    node.style.setProperty("--hmb-mart-radius", `calc(var(--hmb-mart-width) * ${radius / width})`);
    node.style.setProperty("--hmb-mart-clip", `inset(${inset / height * 100}% ${inset / width * 100}% round ${radius / width * 100}% / ${radius / height * 100}%)`);
    if (!url.startsWith("data:image/webp;base64,")) return;
    const doc = node.ownerDocument;
    const styleId = `hmb-mart-launcher-art-${sheetIndex}`;
    if (!doc.getElementById(styleId)) {
      const style = doc.createElement("style");
      style.id = styleId;
      style.textContent = `[data-hmb-mart-sheet="${sheetIndex}"]{--hmb-mart-sheet:url("${url}")}`;
      doc.head.append(style);
    }
    node.dataset.hmbMartSheet = String(sheetIndex);
  }
  function mountHeaderArtwork(header, index, native = false) {
    const height = headerHeights[index];
    if (!header || !height || !headerArtwork.startsWith("data:image/webp;base64,")) return;
    const doc = header.ownerDocument;
    if (!doc.getElementById("hmb-mart-header-art-style")) {
      const style = doc.createElement("style");
      style.id = "hmb-mart-header-art-style";
      style.textContent = `
        [data-hmb-mart-header-position]{position:relative}
        :has(> .hmb-mart-header-art){isolation:isolate}
        .hmb-mart-header-art{--hmb-mart-sheet:url("${headerArtwork}");position:absolute;z-index:-1;inset:0 auto 0 0;width:min(320px,76%);display:block;overflow:hidden;border-radius:inherit;pointer-events:none;user-select:none;
          mask-image:linear-gradient(90deg,#000 0%,#000 24%,rgba(0,0,0,.64) 58%,rgba(0,0,0,.21) 83%,transparent 100%)}
        .hmb-mart-header-art::before{content:"";position:absolute;inset:50% 0 auto;width:100%;aspect-ratio:var(--hmb-mart-ratio);transform:translateY(-44%);opacity:.9;
          background-image:var(--hmb-mart-sheet);background-size:var(--hmb-mart-size);background-position:var(--hmb-mart-position)}
        .hmb-mart-header-art::after{content:"";position:absolute;inset:0;
          background:linear-gradient(90deg,rgba(10,13,24,.26),rgba(10,13,24,.54) 25%,rgba(10,13,24,.36) 72%,transparent)}
        [data-hmb-mart-node-icon]{display:inline-flex;align-items:center;flex:none}
        [data-hmb-popup-header].hmb-mart-popup-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:8px 16px;background:linear-gradient(105deg,#20283c,#131b2b);border-bottom:1px solid #45516c;color:#edf1f9}
        .hmb-mart-popup-header :is(h2,h3,strong){margin:0;font-size:15px;font-weight:650}
        .hmb-mart-popup-header>button:last-child{display:grid;place-items:center;flex:none;width:30px;height:30px;min-height:0;padding:0;border:1px solid #53617b;border-radius:6px;background:#222b3e;color:#edf1f9;font-size:0;cursor:pointer}
        .hmb-mart-popup-header>button:last-child::after{content:"×";font:20px/1 system-ui,sans-serif}
        .hmb-mart-popup-header>button:last-child:hover:not(:disabled){background:#394761}
      `;
      doc.head.append(style);
    }
    const art = doc.createElement("span");
    art.className = "hmb-mart-header-art";
    if (native) art.dataset.hmbMartNative = "";
    art.dataset.hmbMartHeaderArtwork = String(index + 1);
    art.setAttribute("aria-hidden", "true");
    setArtworkCrop(art, { sheetWidth: 840, sheetHeight: 372,
      rect: [4 + index % 5 * 168, 4 + Math.floor(index / 5) * 124, 160, height] });
    const positioned = doc.defaultView.getComputedStyle(header).position === "static";
    const positionMarker = "data-hmb-mart-header-position";
    const retain = () => {
      if (positioned && !header.hasAttribute(positionMarker)) header.setAttribute(positionMarker, "");
      if (art.parentNode !== header) header.append(art);
    };
    retain();
    // Some widgets reconcile the contents of their existing header in place.
    // Reattach only the decoration, without reselecting art or moving controls.
    const observer = new doc.defaultView.MutationObserver(retain);
    observer.observe(header, { childList: true, ...(positioned ? { attributeFilter: [positionMarker] } : {}) });
    return () => {
      observer.disconnect();
      art.remove();
      if (positioned) header.removeAttribute(positionMarker);
    };
  }
  function stylePopupHeader(header, dialog, { artworkOnly = false, enabled = true } = {}) {
    if (!header || !dialog) return;
    let entry = popupHeaders.get(dialog);
    if (!enabled) {
      entry?.cleanup?.();
      popupHeaders.delete(dialog);
      return;
    }
    if (!entry) {
      previousHeaderCard = nextArtwork(previousHeaderCard);
      entry = { index: previousHeaderCard };
      popupHeaders.set(dialog, entry);
    }
    if (!artworkOnly) {
      header.dataset.hmbPopupHeader = "";
      header.classList.add("hmb-mart-popup-header");
    }
    if (entry.header === header) return;
    entry.cleanup?.();
    entry.header = header;
    entry.cleanup = mountHeaderArtwork(header, entry.index);
  }
  const styles = `
.hmb-shot-basket{--hmb-mart-width:min(545px,calc(100vw - 40px),72vh);position:absolute;top:16px;left:16px;z-index:10;pointer-events:none;color:#e9edf5;font:13px/1.45 system-ui,sans-serif}
.hmb-shot-basket *{box-sizing:border-box}
.hmb-shot-basket [hidden]{display:none!important}
.hmb-shot-basket[data-empty-canvas=true]{top:50%;left:50%;transform:translate(-50%,-50%)}
.hmb-shot-basket-launcher,.hmb-shot-basket dialog{pointer-events:auto;background:#151a25;border:1px solid #42465c;border-radius:14px;color:inherit}
.hmb-shot-basket-launcher{display:flex;align-items:center;gap:14px;padding:9px 10px 9px 14px;box-shadow:0 5px 20px #05081188}
.hmb-shot-basket[data-empty-canvas=true] .hmb-shot-basket-launcher{display:grid;justify-items:center;gap:12px;padding:18px 30px}
.hmb-shot-basket[data-empty-canvas=true] .hmb-shot-basket-launcher button{font-size:17px;font-weight:650}
.hmb-shot-basket button,.hmb-shot-basket input,.hmb-shot-basket select{font:inherit;color:inherit;border:1px solid #46516a;border-radius:7px;background:#212838;padding:7px 10px}
.hmb-shot-basket button{cursor:pointer}
.hmb-shot-basket button:hover:not(:disabled){background:#313d53}
.hmb-shot-basket button:disabled{opacity:.55;cursor:default}
.hmb-shot-basket :is(button,input,select):focus-visible{outline:2px solid #d9a5e8;outline-offset:2px}
.hmb-shot-basket .hmb-basket-primary{background:#493453;border-color:#9968a2}
.hmb-shot-basket .hmb-basket-primary:hover:not(:disabled){background:#604169}
.hmb-shot-basket[data-empty-canvas=true] .hmb-shot-basket-launcher:has(.hmb-mart-artwork){padding:0;border:none;background:none;box-shadow:none}
.hmb-shot-basket[data-empty-canvas=true] button.hmb-mart-artwork{display:block;position:relative;isolation:isolate;width:var(--hmb-mart-width);aspect-ratio:var(--hmb-mart-ratio);padding:0;border:0;border-radius:9px;font-size:0;background:none}
.hmb-shot-basket[data-empty-canvas=true] button.hmb-mart-artwork:hover:not(:disabled){background:none}
.hmb-shot-basket button.hmb-mart-artwork::before{content:"";position:absolute;inset:0;background-image:var(--hmb-mart-sheet);background-size:var(--hmb-mart-size);background-position:var(--hmb-mart-position);background-repeat:no-repeat;clip-path:var(--hmb-mart-clip)}
.hmb-shot-basket .hmb-mart-entry-label{position:absolute;bottom:3px;left:78%;transform:translate(-50%,5px) scale(1.3);transform-origin:50% 100%;opacity:0;pointer-events:none;display:inline-flex;align-items:center;gap:7px;min-height:22px;padding:2px 12px;border:1px solid #fff5;border-radius:6px;background:#1f1727;color:#fff;font-size:11px;line-height:1.2;font-weight:700;white-space:nowrap;box-shadow:0 2px 6px #21152b4d;transition:opacity 120ms ease,transform 120ms ease}
.hmb-shot-basket button.hmb-mart-artwork:is(:hover,:focus-visible):not(:disabled) .hmb-mart-entry-label{opacity:1;transform:translate(-50%,0) scale(1.3)}
@media(max-width:560px),(max-height:695px){.hmb-shot-basket .hmb-mart-entry-label{bottom:-28px}}
@media(prefers-reduced-motion:reduce){.hmb-shot-basket .hmb-mart-entry-label{transition:none}}
.hmb-shot-basket .hmb-mart-startup-dialog{width:min(700px,calc(100vw - 24px));max-height:calc(100vh - 24px);padding:0;border:0;background:transparent;box-shadow:none;overflow:visible}
.hmb-shot-basket .hmb-mart-startup-dialog::backdrop{background:#10151f radial-gradient(ellipse at 50% 52%,#242d43,transparent 72%)}
.hmb-mart-startup-choices{display:flex;align-items:stretch;gap:12px}
.hmb-mart-startup-choices .hmb-shot-basket-launcher{min-width:0}
.hmb-shot-basket .hmb-mart-continue{min-width:144px;font-weight:650}
@media(max-width:580px){.hmb-mart-startup-choices{flex-direction:column}.hmb-shot-basket .hmb-mart-continue{min-height:44px}}
.hmb-mart-startup-status{position:absolute;right:12px;bottom:calc(100% + 12px);left:12px;margin:0;text-align:center;color:#ffd7e2}
.hmb-shot-basket dialog{width:min(700px,calc(100vw - 32px));max-height:calc(100vh - 32px);margin:auto;padding:0;box-shadow:0 20px 80px #0009;color-scheme:dark}
.hmb-shot-basket dialog::backdrop{background:#090b13ad}
.hmb-basket-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px}
.hmb-basket-header{border-bottom:1px solid #343d51;background:#1c2232}
.hmb-basket-header h2{font-size:17px;margin:0}
.hmb-basket-main{padding:16px 18px;display:grid;gap:12px}
.hmb-basket-message{padding:0 18px;color:#ffb9c0;overflow-wrap:anywhere}
.hmb-basket-message:empty{display:none}
.hmb-basket-field{display:grid;gap:5px;color:#d9ddec}
.hmb-basket-field select{width:100%;background:#101622}
.hmb-basket-help{color:#b5bfd4;margin:0}
@media(max-width:520px){.hmb-shot-basket{top:10px;left:10px}.hmb-basket-header,.hmb-basket-main{padding-inline:12px}}
`;

  function launcherControl(doc, onOpen) {
    const button = doc.createElement("button");
    button.type = "button";
    button.className = "hmb-basket-primary";
    button.setAttribute("aria-haspopup", "dialog");
    button.addEventListener("click", onOpen);
    const title = doc.createElement("span");
    const action = doc.createElement("span");
    action.className = "hmb-mart-entry-label";
    action.setAttribute("aria-hidden", "true");
    action.textContent = "들어가기 →";
    button.append(title, action);
    let current = -1;
    return { button, update(index, empty) {
      if (index >= 0 && current !== index) applyLauncherArtwork(button, index);
      current = index;
      if (index >= 0) button.dataset.hmbLauncherArtwork = String(index + 1);
      else delete button.dataset.hmbLauncherArtwork;
      const art = empty && launcherCards[index]?.url.startsWith("data:image/webp;base64,") === true;
      button.classList.toggle("hmb-mart-artwork", art);
      action.hidden = !art;
      const label = empty ? "HMB 로동마트" : "샷 바구니 열기";
      if (title.textContent !== label) title.textContent = label;
      const accessibleLabel = art ? `${label} 들어가기` : label;
      if (button.getAttribute("aria-label") !== accessibleLabel) button.setAttribute("aria-label", accessibleLabel);
    } };
  }

  function mountStartup({ host, onDismiss, onEnter }) {
    const doc = host.ownerDocument;
    const root = doc.createElement("div");
    root.className = "hmb-shot-basket";
    root.dataset.emptyCanvas = "true";
    const style = doc.createElement("style");
    style.textContent = styles;
    const dialog = doc.createElement("dialog");
    dialog.className = "hmb-mart-startup-dialog";
    dialog.dataset.hmbRodongStartup = "";
    dialog.setAttribute("aria-label", "HMB 로동마트");
    const close = doc.createElement("button");
    close.type = "button";
    close.className = "hmb-mart-continue";
    close.textContent = "로동 작업 계속";
    const entry = doc.createElement("div");
    entry.className = "hmb-shot-basket-launcher";
    const status = doc.createElement("p");
    status.className = "hmb-mart-startup-status";
    status.setAttribute("role", "status");
    status.hidden = true;
    let busy = false, disposed = false;
    const dismiss = () => { if (!busy && !disposed) onDismiss(); };
    const launcher = launcherControl(doc, async () => {
      if (busy || disposed) return;
      busy = true;
      close.disabled = launcher.button.disabled = true;
      status.hidden = false;
      status.textContent = "새 작업공간을 준비하고 있습니다…";
      try { if (await onEnter()) return; } catch { /* Retry on the same startup card. */ }
      if (disposed) return;
      busy = false;
      close.disabled = launcher.button.disabled = false;
      status.textContent = "작업공간을 열 수 없습니다. 다시 시도하거나 닫아 주세요.";
      launcher.button.focus();
    });
    previousLauncherCard = nextArtwork(previousLauncherCard);
    launcher.update(previousLauncherCard, true);
    close.addEventListener("click", dismiss);
    dialog.addEventListener("cancel", event => { event.preventDefault(); dismiss(); });
    const closeForHandoff = () => { if (busy && dialog.open) dialog.close(); };
    doc.defaultView.addEventListener("hmb-rodong-mart-basket-opened", closeForHandoff);
    entry.append(launcher.button);
    const choices = doc.createElement("div");
    choices.className = "hmb-mart-startup-choices";
    // Share the illustrated launcher's actual curve, including responsive sizing.
    choices.style.setProperty("--hmb-mart-radius", launcher.button.style.getPropertyValue("--hmb-mart-radius"));
    choices.append(entry, close);
    dialog.append(choices, status);
    root.append(style, dialog);
    host.append(root);
    dialog.showModal();
    launcher.button.focus({ preventScroll: true });
    return () => {
      disposed = true;
      doc.defaultView.removeEventListener("hmb-rodong-mart-basket-opened", closeForHandoff);
      if (dialog.open) dialog.close();
      root.remove();
    };
  }

  function mount({ host, request, context: initialContext = {} }) {
    if (!host?.ownerDocument || typeof request !== "function") return { destroy() {}, setContext() {} };
    const doc = host.ownerDocument;
    const root = doc.createElement("div");
    root.className = "hmb-shot-basket nodrag nopan nowheel";
    root.dataset.hmbShotBasket = "";

    function element(tag, attrs = {}, children = []) {
      const node = doc.createElement(tag);
      for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
      node.append(...children);
      return node;
    }

    function button(label, click, attrs = {}) {
      const node = element("button", { type: "button", ...attrs }, [label]);
      node.addEventListener("click", click);
      return node;
    }

    const { button: launcher, update: updateLauncher } = launcherControl(doc, open);
    const close = button("닫기", () => dialog.close(), { "aria-label": "샷 바구니 닫기" });
    const heading = element("h2", {}, ["샷 바구니"]);
    const main = element("div", { class: "hmb-basket-main" });
    const error = element("div", { class: "hmb-basket-message", role: "alert" });
    const dialog = element("dialog", { "aria-label": "샷 바구니" }, [
      element("header", { class: "hmb-basket-header" }, [heading, close]), main, error,
    ]);
    const entry = element("div", { class: "hmb-shot-basket-launcher" }, [launcher]);
    root.append(element("style", {}, [styles]), entry, dialog);
    host.append(root);

    let state;
    let pending;
    let destroyed = false;
    let context = {};
    let launcherCard = -1;
    let statusTimer;
    let statusRetries = 0;
    let visibleView;
    let project = "";
    let imagePicker;
    let imagePickerTimer;
    let imagePickerRetries = 0;
    function setText(node, text) {
      if (node.textContent !== text) node.textContent = text;
    }

    function syncOptions(select, values, current) {
      const signature = JSON.stringify(values);
      if (select.basketOptions !== signature) {
        select.replaceChildren(...values.map(([value, label]) => element("option", { value }, [label])));
        select.basketOptions = signature;
      }
      if (select.value !== current) select.value = current;
    }

    function showView(view, body) {
      if (view === visibleView) return;
      visibleView = view;
      dialog.dataset.basketView = view;
      main.replaceChildren(...body);
    }

    function resetImagePicker() {
      clearTimeout(imagePickerTimer);
      imagePicker = undefined;
      imagePickerRetries = 0;
    }

    function openImageShotPicker() {
      const image = state?.nodes?.image;
      if (!image || pending || imagePicker || destroyed || !dialog.open) return false;
      const imageNodes = [...doc.querySelectorAll(".react-flow__node[data-id]")]
        .filter(node => node.getAttribute("data-id") === image);
      if (imageNodes.length !== 1) return false;
      const trigger = imageNodes[0].querySelector("[data-shot-add]");
      if (!trigger || trigger.disabled) return false;
      const operation = {};
      imagePicker = operation;
      const event = new doc.defaultView.CustomEvent("hmb-basket-open-shot-hierarchy", {
        cancelable: true,
        detail: { onClose() {
          if (imagePicker !== operation) return;
          imagePicker = undefined;
          if (!destroyed && dialog.open) {
            statusRetries = 0;
            void run("status");
          }
        } },
      });
      trigger.dispatchEvent(event);
      if (!event.defaultPrevented && imagePicker === operation) imagePicker = undefined;
      return event.defaultPrevented;
    }

    function tryImageShotPicker() {
      clearTimeout(imagePickerTimer);
      if (!imagePickerRetries) return;
      imagePickerTimer = setTimeout(() => {
        if (destroyed || !dialog.open || state?.status !== "ready"
          || state.cgt_required !== true || state.cgt_bound === true) return;
        imagePickerRetries -= 1;
        if (openImageShotPicker()) imagePickerRetries = 0;
        else tryImageShotPicker();
      }, 250);
    }

    function open(projectsHint = [], prepare = false) {
      if (!context.ready || dialog.open || pending || destroyed) return false;
      if (context.empty && !state && Array.isArray(projectsHint) && projectsHint.length) {
        state = { status: "empty", projects: projectsHint, flow_name: context.flowName, shots: [] };
      }
      if (!context.empty) entry.hidden = true;
      stylePopupHeader(dialog.querySelector(".hmb-basket-header"), dialog);
      dialog.showModal();
      statusRetries = 0;
      void run(prepare ? "prepare" : "status");
      return true;
    }

    function resetView() {
      pending = undefined;
      state = undefined;
      project = "";
      clearTimeout(statusTimer);
      statusTimer = undefined;
      resetImagePicker();
      if (dialog.open) dialog.close();
    }

    function setContext(next) {
      if (destroyed) return;
      const switched = context.flowName !== next.flowName || context.workflowName !== next.workflowName || context.epoch !== next.epoch;
      if (switched) {
        const createInNewFlow = ["create", "prepare"].includes(pending?.action) && !pending.flowName && !!next.flowName
          && (!pending.transitioned || pending.transitioned === next.flowName);
        const createdFlow = !context.flowName && !!next.flowName && state?.flow_name === next.flowName;
        if (createInNewFlow) pending.transitioned = next.flowName;
        else if (!createdFlow) resetView();
      }
      if (switched || !next.empty) launcherCard = -1;
      if (next.empty && next.ready && launcherCard < 0) {
        launcherCard = nextArtwork(previousLauncherCard);
        previousLauncherCard = launcherCard;
      }
      updateLauncher(next.empty ? launcherCard : -1, next.empty);
      context = { ...next };
      root.dataset.emptyCanvas = String(Boolean(next.empty));
      syncEntry();
    }

    function syncEntry() {
      entry.hidden = context.ready !== true || context.empty !== true;
    }

    function retryStatusWhenReady() {
      if (statusRetries >= 18 || !dialog.open) return false;
      statusTimer = setTimeout(() => { if (dialog.open) void run("status"); }, Math.min(650 + statusRetries * 350, 2500));
      statusRetries += 1;
      return true;
    }

    async function run(action, payload = {}) {
      if (pending || destroyed) return;
      clearTimeout(statusTimer);
      statusTimer = undefined;
      if (action === "create" || action === "prepare") statusRetries = 0;
      const operation = { action, flowName: context.flowName };
      pending = operation;
      error.textContent = "";
      render();
      try {
        const flowName = state?.flow_name || operation.flowName || "";
        const result = await request(action, { flow_name: flowName, ...payload });
        if (!result || result.ok === false) throw new Error(result?.message || "요청을 완료하지 못했습니다.");
        if (pending !== operation || destroyed) return;
        if (context.flowName && (operation.transitioned || result.flow_name) && result.flow_name !== context.flowName) {
          resetView();
          return;
        }
        if (!Array.isArray(result.projects) || !Array.isArray(result.shots)) throw new Error("샷 응답을 확인할 수 없습니다.");
        state = result.status === "discovering" && !result.projects.length && state?.projects.length
          ? { ...result, projects: state.projects } : result;
        if (action === "create" && state.cgt_required === true && state.cgt_bound !== true) imagePickerRetries = 12;
        if (["discovering", "preparing"].includes(state.status) && !shotCreated() && !retryStatusWhenReady() && dialog.open) {
          error.textContent = "준비 응답이 지연되고 있습니다. 다시 확인하면 현재 상태를 조회합니다.";
        }
      } catch (failure) {
        if (pending === operation && !destroyed) {
          if (action !== "status" || !retryStatusWhenReady()) error.textContent = failure.message || "샷 준비 상태를 확인하지 못했습니다.";
        }
      } finally {
        if (pending === operation) {
          pending = undefined;
          syncEntry();
          if (!destroyed && dialog.open) render();
        }
      }
    }

    function form() {
      const choose = element("select", { required: "", "aria-label": "프로젝트" });
      const submit = element("button", { type: "submit", class: "hmb-basket-primary" }, ["샷 바구니 들기"]);
      const update = () => { submit.disabled = !!pending || state?.status !== "empty" || !choose.value; };
      choose.addEventListener("change", () => { project = choose.value; update(); });
      const fields = element("form", { class: "hmb-basket-field" }, [
        element("label", { class: "hmb-basket-field" }, ["프로젝트", choose]),
        element("p", { class: "hmb-basket-help" }, ["프로젝트를 정한 뒤 ImageAsset의 CGT 샷 선택에서 본인의 에피소드와 컷을 지정하세요."]),
        submit,
      ]);
      fields.addEventListener("submit", event => {
        event.preventDefault();
        if (!submit.disabled) void run("create", { project_id: project, cgt_setup: true });
      });
      return { fields, paint() {
        const projects = state.projects;
        if (!projects.some(item => item.project_id === project)) project = "";
        syncOptions(choose, [["", "프로젝트 선택"], ...projects.map(item => [item.project_id, item.name || item.project_id])], project);
        choose.disabled = !!pending || state.status !== "empty";
        setText(submit, pending?.action === "create" || pending?.action === "prepare" || state.status !== "empty"
          ? "프로젝트와 샷을 준비 중입니다…" : "샷 바구니 들기");
        update();
      } };
    }

    const projectForm = form();
    const cgtNotice = element("p", { class: "hmb-basket-help", role: "status" });
    const openCgt = button("CGT 샷 선택", () => {
      imagePickerRetries = 0;
      if (!openImageShotPicker()) setText(cgtNotice, "ImageAsset의 샷 선택을 준비 중입니다. 잠시 뒤 다시 눌러 주세요.");
    }, { class: "hmb-basket-primary" });
    const statusNotice = element("p", { role: "status" });
    const retryStatus = button("다시 확인", () => {
      statusRetries = 0;
      void run("status");
    });

    function shotCreated() {
      return state?.shots.length > 0 && (state.cgt_required !== true || state.cgt_bound === true)
        && ["ready", "preparing"].includes(state.status);
    }

    function render() {
      if (!pending && shotCreated()) {
        dialog.close();
        return;
      }
      const requiresCgt = state?.cgt_required === true && state.cgt_bound !== true;
      if (state?.status === "empty" || (state?.status === "discovering" && state.projects.length)) {
        projectForm.paint();
        showView("project", [projectForm.fields]);
      } else if (requiresCgt && state.status === "ready") {
        if (visibleView !== "cgt") setText(cgtNotice, "ImageAsset에서 본인에게 배정된 CGT 에피소드와 컷을 선택하세요.");
        openCgt.disabled = !!pending;
        showView("cgt", [cgtNotice, openCgt]);
        if (!pending) tryImageShotPicker();
      } else {
        const notices = {
          discovering: "프로젝트 목록을 확인하고 있습니다.",
          preparing: "프로젝트와 샷을 준비 중입니다.",
          unavailable: "프로젝트에 연결할 수 없습니다.",
          occupied: "새 빈 작업공간에서 로동마트를 시작하세요.",
        };
        const waiting = ["discovering", "preparing"].includes(state?.status);
        statusNotice.hidden = waiting && !!error.textContent;
        setText(statusNotice, state?.message || notices[state?.status]
          || (pending ? "샷 바구니를 확인하고 있습니다…" : "샷 바구니 상태를 확인하세요."));
        retryStatus.hidden = !!pending || statusTimer !== undefined || (waiting && !error.textContent);
        retryStatus.disabled = !!pending;
        showView("status", [statusNotice, retryStatus]);
      }
    }

    dialog.addEventListener("close", () => {
      if (dialog.open) return;
      syncEntry();
      clearTimeout(statusTimer);
      statusTimer = undefined;
      resetImagePicker();
      if (!destroyed && !entry.hidden) launcher.focus();
    });
    for (const event of ["pointerdown", "mousedown", "click", "dblclick", "wheel", "keydown", "keyup"]) {
      root.addEventListener(event, value => value.stopPropagation());
    }

    setContext(initialContext);
    return {
      setContext, open,
      destroy() {
        destroyed = true;
        resetView();
        root.remove();
      },
    };
  }

  if (typeof window !== "undefined") {
    window.__hmbMountShotBasket = mount;
    window.__hmbMountRodongMartStartup = mountStartup;
    window.__hmbStylePopupHeader = stylePopupHeader;
    window.__hmbRodongMartHeaderArt = { mount: mountHeaderArtwork, next() {
      previousHeaderCard = nextArtwork(previousHeaderCard);
      return previousHeaderCard;
    } };
  }
})();
