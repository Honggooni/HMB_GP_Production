// Local-only decoration: no workflow routing, geometry or binding changes.
(() => {
  const sheets = ["__HMB_CONTINUE_WORK_01_10__", "__HMB_CONTINUE_WORK_11_20__", "__HMB_CONTINUE_WORK_21_30__"];
  // Approved original bounds, excluding only numbering and gutters.
  const cards = [
    { id: 3, sheet: 0, rect: [680, 55, 317, 409] },
    { id: 6, sheet: 0, rect: [12, 522, 328, 405] },
    { id: 9, sheet: 0, rect: [1008, 522, 316, 405] },
    { id: 12, sheet: 1, rect: [359, 56, 311, 405] },
    { id: 14, sheet: 1, rect: [1010, 56, 309, 405] },
    { id: 16, sheet: 1, rect: [23, 519, 321, 402] },
    { id: 21, sheet: 2, rect: [16, 57, 324, 397] },
    { id: 22, sheet: 2, rect: [355, 57, 313, 397] },
    { id: 27, sheet: 2, rect: [356, 518, 313, 405] },
    { id: 29, sheet: 2, rect: [1012, 518, 313, 405] },
  ];
  let sessionCard;
  let serial = 0;
  function pick(win) {
    if (sessionCard) return sessionCard;
    let previous = -1;
    try {
      const id = Number(win.localStorage.getItem("hmb-continue-work-last-art"));
      previous = cards.findIndex(card => card.id === id);
    } catch { /* Storage restrictions cannot block the entry. */ }
    const draw = Math.floor(Math.random() * (cards.length - Number(previous >= 0)));
    sessionCard = cards[draw + Number(previous >= 0 && draw >= previous)];
    try { win.localStorage.setItem("hmb-continue-work-last-art", String(sessionCard.id)); } catch {}
    return sessionCard;
  }
  window.__hmbDecorateContinueWork = button => {
    if (!button || button.dataset.hmbContinueArtwork) return;
    const doc = button.ownerDocument;
    const card = pick(doc.defaultView);
    const url = sheets[card.sheet];
    if (!url.startsWith("data:image/webp;base64,")) return;
    if (!doc.getElementById("hmb-continue-work-art-style")) {
      const style = doc.createElement("style");
      style.id = "hmb-continue-work-art-style";
      style.textContent = `
        .hmb-shot-basket .hmb-mart-continue[data-hmb-continue-artwork]{position:relative;isolation:isolate;background:#151a25;border-radius:var(--hmb-mart-radius,26px)}
        .hmb-continue-picture{position:absolute;inset:0;display:block;overflow:hidden;border-radius:max(0px,calc(var(--hmb-mart-radius,26px) - 1px));pointer-events:none}
        .hmb-continue-picture svg{display:block;width:100%;height:100%;pointer-events:none}
        .hmb-continue-label{position:absolute;bottom:5px;left:50%;transform:translate(-50%,5px);opacity:0;display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:3px 8px;border:1px solid #fff5;border-radius:6px;background:#111827ed;color:#fff;font-size:12px;font-weight:700;line-height:1.3;white-space:nowrap;pointer-events:none;box-shadow:0 2px 6px #0005;transition:opacity 120ms ease,transform 120ms ease}
        .hmb-mart-continue:is(:hover,:focus-visible):not(:disabled) .hmb-continue-label,.hmb-mart-continue[data-hmb-continue-art-failed] .hmb-continue-label{opacity:1;transform:translate(-50%,0)}
        .hmb-shot-basket .hmb-mart-continue[data-hmb-continue-artwork]:hover:not(:disabled){border-color:#d9a5e8;background:#202a3d}
        @media(prefers-reduced-motion:reduce){.hmb-continue-label{transition:none}}
      `;
      doc.head.append(style);
    }
    const label = doc.createElement("span");
    label.className = "hmb-continue-label";
    label.textContent = `${button.textContent} →`;
    label.setAttribute("aria-hidden", "true");
    button.setAttribute("aria-label", button.textContent);
    // Keep the original in-flow text metrics before and after image decoding.
    const sizing = doc.createElement("span");
    sizing.textContent = button.textContent;
    sizing.style.visibility = "hidden";
    sizing.setAttribute("aria-hidden", "true");
    const art = doc.createElement("span");
    art.className = "hmb-continue-picture";
    art.setAttribute("aria-hidden", "true");
    const ns = "http://www.w3.org/2000/svg";
    const svg = doc.createElementNS(ns, "svg");
    const [x, y, width, height] = card.rect;
    svg.setAttribute("viewBox", card.rect.join(" "));
    svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
    const clip = doc.createElementNS(ns, "clipPath");
    clip.id = `hmb-continue-art-clip-${++serial}`;
    const rect = doc.createElementNS(ns, "rect");
    for (const [key, value] of Object.entries({x, y, width, height})) rect.setAttribute(key, value);
    clip.append(rect);
    const defs = doc.createElementNS(ns, "defs");
    defs.append(clip);
    const image = doc.createElementNS(ns, "image");
    image.setAttribute("width", "1672");
    image.setAttribute("height", "941");
    image.setAttribute("clip-path", `url(#${clip.id})`);
    image.addEventListener("error", () => { button.dataset.hmbContinueArtFailed = "true"; }, {once:true});
    image.setAttribute("href", url);
    svg.append(defs, image);
    art.append(svg);
    button.replaceChildren(sizing, art, label);
    button.dataset.hmbContinueArtwork = String(card.id);
  };
})();
