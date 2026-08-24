import assert from "node:assert/strict";
import fs from "node:fs";

const widgetSource = fs.readFileSync(
  new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url),
  "utf8",
);
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

// Expanded mode has one resize owner: the native React Flow outer box. The
// former red viewport/activity splitter could change only the authored inner
// panel and expose the clip's black background, so no markup, cursor styling,
// event binding, or saved viewport height may remain active.
assert.doesNotMatch(widgetSource, /data-resize-panel(?:=|\])/);
assert.doesNotMatch(widgetSource, /\.panel-resize-handle/);
assert.doesNotMatch(widgetSource, /hmbFlexPanelHeightStyle\(state\.viewport_panel_height/);
assert.doesNotMatch(widgetSource, /const stateField = ["']viewport_panel_height["']/);
const viewportPanelOpening = widgetSource.match(
  /<section class="panel viewport-panel"[^>]*>/,
)?.[0] || "";
assert.ok(viewportPanelOpening, "expanded viewport panel markup must remain present");
assert.doesNotMatch(
  viewportPanelOpening,
  /(?:viewport_panel_height|data-resize-panel|\sstyle=)/,
  "legacy saved viewport_panel_height values must not create an inline panel height or splitter",
);
assert.match(
  widgetSource,
  /data-resize-section="color"/,
  "the separate video-assets section resize contract is outside this removal and must remain",
);

assert.match(
  widgetSource,
  /const HMB_RIGHT_SECTION_DEFAULT_HEIGHTS = \{ settings: 217, color: 628, log: 208 \};/,
);
assert.match(
  widgetSource,
  /\.center-stack>\.viewport-panel\{[^\r\n]*height:auto;[^\r\n]*min-height:(?:636|\$\{HMB_PICKER_VIEWPORT_PANEL_MIN_HEIGHT\})px;[^\r\n]*flex:1 1 0[^\r\n]*\}/,
  "the viewport must automatically absorb outer-height changes",
);
assert.match(
  widgetSource,
  /\.center-stack>\.activity-section\{[^\r\n]*height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;[^\r\n]*flex:0 0 \$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;[^\r\n]*min-height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px;[^\r\n]*max-height:\$\{HMB_RIGHT_SECTION_DEFAULT_HEIGHTS\.log\}px[^\r\n]*\}/,
  "Activity Log must remain fixed at 208px",
);

function fakeStyle(initial = {}) {
  const values = new Map();
  const priorities = new Map();
  for (const [name, value] of Object.entries(initial)) values.set(name, String(value));
  return {
    getPropertyValue(name) { return values.get(String(name)) || ""; },
    getPropertyPriority(name) { return priorities.get(String(name)) || ""; },
    setProperty(name, value, priority = "") {
      values.set(String(name), String(value));
      if (priority) priorities.set(String(name), String(priority));
      else priorities.delete(String(name));
    },
    removeProperty(name) {
      const prior = values.get(String(name)) || "";
      values.delete(String(name));
      priorities.delete(String(name));
      return prior;
    },
  };
}

function number(style, property, fallback = 0) {
  const parsed = Number.parseFloat(style.getPropertyValue(property));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function makeCssMinimumMaskedShell({ width, height }) {
  const style = fakeStyle({
    width: `${width}px`,
    height: `${height}px`,
    "min-width": "1400px",
    "min-height": "1200px",
  });
  const renderedWidth = () => Math.max(
    number(style, "width"),
    number(style, "min-width"),
  );
  const renderedHeight = () => Math.max(
    number(style, "height"),
    number(style, "min-height"),
  );
  const shell = {
    style,
    classList: { contains: (name) => name === "react-flow__node" },
    getBoundingClientRect() {
      return {
        top: 0,
        left: 0,
        right: renderedWidth(),
        bottom: renderedHeight(),
        width: renderedWidth(),
        height: renderedHeight(),
      };
    },
  };
  Object.defineProperties(shell, {
    offsetWidth: { get: renderedWidth },
    offsetHeight: { get: renderedHeight },
  });
  const container = {
    __hmbVideoPickerExpanded: true,
    closest(selector) {
      return selector === ".react-flow__node" ? shell : null;
    },
  };
  return { container, shell };
}

// React Flow's native resizer may continue writing an undersized inline
// width/height while an !important CSS minimum keeps the visible border box at
// 1400x1200. offsetWidth/offsetHeight and getBoundingClientRect therefore look
// valid even though the host allocator still owns the bad inline dimensions.
// The floor repair must inspect and normalize both representations.
const masked = makeCssMinimumMaskedShell({ width: 820, height: 610 });
assert.equal(masked.shell.offsetWidth, 1400);
assert.equal(masked.shell.offsetHeight, 1200);
assert.equal(masked.shell.style.getPropertyValue("width"), "820px");
assert.equal(masked.shell.style.getPropertyValue("height"), "610px");

const repaired = picker.hmbApplyVideoPickerExpandedGeometryFloor(masked.container);
assert.ok(repaired);
assert.equal(
  masked.shell.style.getPropertyValue("width"),
  "1400px",
  "a CSS min-width-masked native resize must repair the React Flow inline width",
);
assert.equal(
  masked.shell.style.getPropertyValue("height"),
  "1200px",
  "a CSS min-height-masked native resize must repair the React Flow inline height",
);
assert.equal(masked.shell.style.getPropertyValue("min-width"), "1400px");
assert.equal(masked.shell.style.getPropertyValue("min-height"), "1200px");
assert.equal(masked.shell.style.getPropertyPriority("min-width"), "important");
assert.equal(masked.shell.style.getPropertyPriority("min-height"), "important");
assert.equal(
  picker.hmbVideoPickerExpandedRenderedResizeDelta(1200, 610),
  0,
  "an inward drag at the 1200px rendered floor must apply zero inner-height delta",
);
assert.equal(picker.hmbVideoPickerExpandedRenderedResizeDelta(1480, 1100), -280);
assert.equal(picker.hmbVideoPickerExpandedRenderedResizeDelta(1200, 1480), 280);
assert.match(
  widgetSource,
  /window\.addEventListener\("pointermove", repairDuringNativePointer, true\)/,
  "native drag must repair the masked inline size in RAF before the next paint",
);
assert.match(
  widgetSource,
  /const renderedDelta = hmbVideoPickerExpandedRenderedResizeDelta\([\s\S]*?session\.availableHeight \|\| 0\) \+ renderedDelta/,
  "the Picker-owned root must consume the exact rendered outer-height delta",
);

// A legitimate expansion must remain untouched after the same check.
masked.shell.style.setProperty("width", "1760px");
masked.shell.style.setProperty("height", "1480px");
picker.hmbApplyVideoPickerExpandedGeometryFloor(masked.container);
assert.equal(masked.shell.style.getPropertyValue("width"), "1760px");
assert.equal(masked.shell.style.getPropertyValue("height"), "1480px");

console.log("HMB VideoPicker CSS-minimum masked resize regression checks passed.");
