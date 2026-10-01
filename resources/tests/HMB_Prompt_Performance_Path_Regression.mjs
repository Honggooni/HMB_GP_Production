import assert from "node:assert/strict";
import fs from "node:fs";

import {
  hmbPatchPromptSourceSection,
  hmbClearImageDragIndicators,
  hmbUpdateImageDragIndicators,
  hmbScopeWidgetCss,
  hmbScopeWidgetStyleMarkup,
} from "../../widgets/HMBPromptLibraryScopedBindingWidget.js";

class FakeElement {
  constructor(classNames = "", attributes = {}, innerHTML = "") {
    this.classNames = new Set(String(classNames).split(/\s+/).filter(Boolean));
    this.attributeValues = { ...attributes };
    this.innerHTML = innerHTML;
    this.children = [];
    this.parentElement = null;
    this.ownerDocument = { activeElement: null };
    this.classList = { contains: (name) => this.classNames.has(name) };
  }

  get attributes() {
    return Object.entries(this.attributeValues).map(([name, value]) => ({ name, value }));
  }

  get firstChild() { return this.children[0] || null; }

  get nextSibling() {
    if (!this.parentElement) return null;
    const index = this.parentElement.children.indexOf(this);
    return index >= 0 ? this.parentElement.children[index + 1] || null : null;
  }

  getAttribute(name) { return this.attributeValues[name] ?? null; }
  setAttribute(name, value) { this.attributeValues[name] = String(value); }
  removeAttribute(name) { delete this.attributeValues[name]; }
  contains(candidate) { return candidate === this; }
  querySelector() { return null; }

  isEqualNode(other) {
    return Boolean(other)
      && JSON.stringify(this.attributeValues) === JSON.stringify(other.attributeValues)
      && this.innerHTML === other.innerHTML;
  }

  remove() {
    if (!this.parentElement) return;
    const index = this.parentElement.children.indexOf(this);
    if (index >= 0) this.parentElement.children.splice(index, 1);
    this.parentElement = null;
  }
}

class FakeScrollbox extends FakeElement {
  constructor(header, rows) {
    super("source-scrollbox");
    this.mutations = 0;
    this.children = [header, ...rows];
    this.children.forEach((child) => { child.parentElement = this; });
  }

  querySelector(selector) {
    if (selector === ".source-header") return this.children[0] || null;
    return null;
  }

  appendChild(row) { return this.insertBefore(row, null); }

  insertBefore(row, reference) {
    const oldParent = row.parentElement;
    if (oldParent) {
      const oldIndex = oldParent.children.indexOf(row);
      if (oldIndex >= 0) oldParent.children.splice(oldIndex, 1);
    }
    const index = reference ? this.children.indexOf(reference) : this.children.length;
    this.children.splice(index < 0 ? this.children.length : index, 0, row);
    row.parentElement = this;
    this.mutations += 1;
    return row;
  }
}

class FakeSection extends FakeElement {
  constructor(scrollbox) {
    super("group-card", { "data-group-id": "imageSources" });
    this.heading = new FakeElement("", {}, "IMAGE SOURCE BINDING <b>2 / 50</b>");
    this.scrollbox = scrollbox;
  }

  querySelector(selector) {
    if (selector === "h3") return this.heading;
    if (selector === ".source-scrollbox") return this.scrollbox;
    return null;
  }
}

const row = (key, body = key) => new FakeElement(
  "source-row image",
  { "data-source-key": key, "data-kind": "image" },
  body,
);
const header = () => new FakeElement("source-header image-header");

const currentA = row("a");
const currentB = row("b");
const currentScroll = new FakeScrollbox(header(), [currentA, currentB]);
const currentSection = new FakeSection(currentScroll);
const sameSection = new FakeSection(new FakeScrollbox(header(), [row("a"), row("b")]));

assert.equal(hmbPatchPromptSourceSection(currentSection, sameSection), true);
assert.equal(currentScroll.mutations, 0, "Unchanged source rows must not be detached and appended again.");
assert.deepEqual(currentScroll.children.slice(1), [currentA, currentB]);

const reorderedSection = new FakeSection(new FakeScrollbox(header(), [row("b"), row("a")]));
assert.equal(hmbPatchPromptSourceSection(currentSection, reorderedSection), true);
assert.deepEqual(currentScroll.children.slice(1), [currentB, currentA]);
assert.equal(currentScroll.mutations, 1, "A two-row reorder must perform only the required DOM move.");

function dragRow() {
  const names = new Set();
  const writes = { add: 0, remove: 0 };
  return {
    writes,
    names,
    classList: {
      add(name) { writes.add += 1; names.add(name); },
      remove(...values) { writes.remove += 1; values.forEach((name) => names.delete(name)); },
    },
  };
}
const dragSource = dragRow();
const dragHoverA = dragRow();
const dragHoverB = dragRow();
let dragSourceQueries = 0;
const dragContainer = {
  querySelector() { dragSourceQueries += 1; return dragSource; },
};
assert.equal(hmbUpdateImageDragIndicators(dragContainer, dragHoverA, 2, false), true);
for (let index = 0; index < 100; index += 1) {
  assert.equal(hmbUpdateImageDragIndicators(dragContainer, dragHoverA, 2, false), false);
}
assert.equal(dragSourceQueries, 1, "Repeated dragover must reuse the source row.");
assert.equal(dragHoverA.writes.add, 1, "The same hover position must not mutate DOM again.");
assert.equal(hmbUpdateImageDragIndicators(dragContainer, dragHoverA, 2, true), true);
assert.equal(hmbUpdateImageDragIndicators(dragContainer, dragHoverB, 2, false), true);
assert.equal(dragHoverA.names.size, 0);
assert.equal(dragHoverB.names.has("image-drop-before"), true);
hmbClearImageDragIndicators(dragContainer);
assert.equal(dragSource.names.size, 0);
assert.equal(dragHoverB.names.size, 0);
assert.equal(dragContainer.__hmbPromptImageDragIndicators, undefined);

const source = fs.readFileSync(
  new URL("../../widgets/HMBPromptLibraryScopedBindingWidget.js", import.meta.url),
  "utf8",
);
const instrumentedSource = source.replace(
  "export function normalizeState(input) {",
  "export function normalizeState(input) { globalThis.__hmbPromptNormalizeCalls += 1;",
);
assert.notEqual(instrumentedSource, source);
const instrumentedWidget = await import(
  `data:text/javascript;base64,${Buffer.from(instrumentedSource).toString("base64")}`
);
const largePropsValue = JSON.stringify({
  images: Array.from({ length: 50 }, (_unused, index) => ({
    slot: index + 1,
    label: `Image ${index + 1}`,
    present: true,
  })),
  videos: Array.from({ length: 10 }, (_unused, index) => ({
    slot: index + 1,
    label: `Video ${index + 1}`,
    present: true,
  })),
});
globalThis.__hmbPromptNormalizeCalls = 0;
assert.equal(
  instrumentedWidget.hmbConsumePendingPromptStateEcho(
    {}, { value: largePropsValue, disabled: false }, null,
  ),
  false,
);
assert.equal(
  globalThis.__hmbPromptNormalizeCalls,
  1,
  "One retained-mode echo must normalize a 50-image/10-video payload once.",
);
delete globalThis.__hmbPromptNormalizeCalls;
const cssMatch = source.match(/includeStyle \? `<style>\n([\s\S]*?)<\/style>` : ""/);
assert.ok(cssMatch, "Prompt widget CSS literal must remain byte-identical behind the full-mount guard.");
const css = cssMatch[1];
const markup = `<style>${css}</style><div class="hmb-dashboard"></div>`;
const expected = `<style>${hmbScopeWidgetCss(css, ".hmb-dashboard")}</style><div class="hmb-dashboard"></div>`;
assert.equal(
  hmbScopeWidgetStyleMarkup(markup, ".hmb-dashboard"),
  expected,
  "CSS memoization must preserve the exact scoped markup bytes.",
);
assert.equal(
  hmbScopeWidgetStyleMarkup(markup, ".hmb-dashboard"),
  expected,
  "A cache hit must remain byte-identical to the uncached scoping result.",
);
assert.match(
  source,
  /let HMB_PROMPT_SCOPED_STYLE_MARKUP = "";/,
  "The fully scoped Prompt style must have one module-local full-mount cache.",
);
assert.match(
  source,
  /return HMB_PROMPT_SCOPED_STYLE_MARKUP \+ render\(state, false\);/,
  "Later full mounts must reuse the exact cached style bytes.",
);
assert.match(
  source,
  /const dynamicMarkup = render\(state, false\);[\s\S]*hmbPatchPromptDashboard\(container, dynamicMarkup\)/,
  "Retained remounts must render and parse only dynamic dashboard markup.",
);
assert.doesNotMatch(
  source,
  /hmbPatchPromptDashboard\(container, hmbScopeWidgetStyleMarkup\(/,
  "Retained remounts must not scope or parse the fixed Prompt stylesheet.",
);

console.log("HMB Prompt five-node performance-path regression: PASS");
