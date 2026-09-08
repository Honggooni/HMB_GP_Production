import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBImageAssetLibraryWidget.js", import.meta.url), "utf8");
const widget = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

function fixture(zoom = 1) {
  let serial = 0;
  const frames = new Map(), mutations = [], resizes = [];
  const view = {
    requestAnimationFrame(fn) { const id = ++serial; frames.set(id, fn); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
    MutationObserver: class {
      constructor(fn) { this.fn = fn; this.active = true; mutations.push(this); }
      observe() {}
      disconnect() { this.active = false; }
    },
    ResizeObserver: class {
      constructor(fn) { this.fn = fn; this.active = true; this.targets = new Set(); resizes.push(this); }
      observe(el) { this.targets.add(el); }
      unobserve(el) { this.targets.delete(el); }
      disconnect() { this.active = false; this.targets.clear(); }
    },
  };
  function element(name, parent = null, height = "auto") {
    const styles = new Map([["height", { value: height, priority: "" }]]);
    const el = {
      name, tagName: "DIV", className: name, parentElement: parent, children: [],
      ownerDocument: { defaultView: view }, attributes: new Map(), offsetWidth: 1500,
      // Several wrappers share the same positioned offsetParent in Griptape.
      offsetTop: 120, offsetParent: null, writes: 0,
      style: {
        getPropertyValue(key) { return styles.get(key)?.value || ""; },
        getPropertyPriority(key) { return styles.get(key)?.priority || ""; },
        setProperty(key, value, priority) { el.writes++; styles.set(key, { value, priority }); },
        removeProperty(key) { styles.delete(key); },
      },
      getAttribute(key) { return el.attributes.get(key) || ""; },
      hasAttribute(key) { return el.attributes.has(key); },
      contains(target) { return target === el || el.children.some(child => child.contains(target)); },
      getBoundingClientRect() { return { top: 20, width: 1500 * zoom, height: el.offsetHeight * zoom }; },
      querySelector() { return null; },
    };
    Object.defineProperty(el, "offsetHeight", { get() { return parseFloat(styles.get("height")?.value) || 0; } });
    parent?.children.push(el);
    return el;
  }
  const node = element("react-flow__node", null, "980px");
  node.attributes.set("data-id", "HMBImageAssetLibrary");
  node.style.setProperty("min-height", "560px", "");
  node.style.setProperty("width", "1500px", "");
  const body = element("body", node, "880px");
  const native = element("IMAGE_IMPORT_IN", body, "32px");
  const row = element("widget-row", body, "760px");
  const host = element("widget-container", row, "760px");
  const root = element("hmb-image-assets", host, "680px");
  const top = element("top", root, "58px");
  const summary = element("summary", root, "100px");
  summary.scrollHeight = 100;
  for (const el of [body, row, host, root]) el.offsetParent = node;
  let chrome = 120, updates = 0;
  root.getBoundingClientRect = () => ({ top: 20 + chrome * zoom, width: 1500 * zoom, height: root.offsetHeight * zoom });
  host.querySelector = selector => selector === ".hmb-image-assets" ? root
    : selector === "[data-library-compact-summary]" ? summary
      : selector === ".top[data-library-toggle-surface='header']" ? top : null;
  host.__hmbImageAssetCompact = true;
  host.__hmbImageAssetUpdateNodeInternals = () => updates++;
  const height = () => node.style.getPropertyValue("height");
  const fire = target => mutations.filter(m => m.active).forEach(m => m.fn([{ target }]));
  const resize = () => resizes.filter(r => r.active).forEach(r => r.fn([]));
  const flush = () => { const jobs = [...frames.values()]; frames.clear(); jobs.forEach(fn => fn()); };
  return { node, body, native, row, host, root, summary, height, fire, resize, flush, frames, mutations, resizes,
    element, setChrome(value) { chrome = value; }, updates: () => updates };
}

// The old implementation fixes chrome at compact entry, and also counts each
// ancestor's offsetTop even when the positioned offsetParent is the same node.
for (const zoom of [0.25, 0.5, 1, 1.5, 2]) {
  const f = fixture(zoom);
  widget.hmbSetImageAssetCompactShellGeometry(f.host, true);
  assert.equal(f.height(), "280px", `Correct compact height at canvas zoom ${zoom}`);
  assert.equal(f.updates(), 1);
  assert.equal(f.node.style.getPropertyValue("width"), "1500px");
  for (let round = 0; round < 20; round++) {
    f.setChrome(360); f.fire(f.native); f.fire(f.native); f.resize();
    assert.equal(f.frames.size, 1, "Native changes coalesce to one animation frame");
    f.flush(); assert.equal(f.height(), "520px", "Open import rows must fit above the compact widget");
    f.setChrome(120); f.fire(f.body); f.flush();
    assert.equal(f.height(), "280px", "Collapse must remove the unused black tail");
  }
  const before = f.updates(), writes = f.node.writes;
  f.fire(f.node); f.resize(); f.flush(); f.resize(); f.flush();
  assert.equal(f.updates(), before, "Stable measurements must not start a host update loop");
  assert.equal(f.node.writes, writes, "Unchanged CSS must not retrigger mutation observers");
  f.fire(f.root);
  assert.equal(f.frames.size, 0, "Thumbnail/widget DOM churn must not trigger host geometry work");
  f.summary.scrollHeight = 620; f.resize(); f.flush();
  assert.equal(f.height(), "800px", "All five compact Shot rows must fit");
  // A React row replacement gets its own geometry snapshot and observation.
  const replacement = f.element("new-row", f.body, "740px");
  f.row.children = []; replacement.children.push(f.host); f.host.parentElement = replacement;
  f.fire(f.body); f.flush();
  assert.equal(replacement.style.getPropertyValue("height"), "auto");
  assert.ok(f.resizes[0].targets.has(replacement));
  assert.ok(!f.resizes[0].targets.has(f.row) || f.body.children.includes(f.row));
  f.fire(f.native); assert.equal(f.frames.size, 1);
  widget.hmbSetImageAssetCompactShellGeometry(f.host, false);
  assert.equal(f.frames.size, 0, "Expand/unmount cancels pending callbacks");
  assert.ok(f.mutations.every(m => !m.active));
  assert.ok(f.resizes.every(r => !r.active));
  assert.equal(f.host.__hmbImageAssetCompactGeometryObserver, undefined);
  assert.equal(f.height(), "980px");
  assert.equal(f.node.style.getPropertyValue("min-height"), "560px");
  assert.equal(f.host.style.getPropertyValue("height"), "760px");
  assert.equal(replacement.style.getPropertyValue("height"), "740px");
}
console.log("PASS ImageAsset compact input layout: 5 zoom levels, 100 open/close cycles, five Shot rows, wrapper replacement, no update loop, exact cleanup.");
