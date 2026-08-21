import assert from "node:assert/strict";
import fs from "node:fs";


const pythonSource = fs.readFileSync(
  new URL("../../HMBVideoPickerLibrary.py", import.meta.url),
  "utf8",
);

function topLevelFunctionSource(name) {
  const startToken = `\ndef ${name}(`;
  const start = pythonSource.indexOf(startToken);
  assert.notEqual(start, -1, `Missing Python function: ${name}`);
  const next = pythonSource.indexOf("\ndef ", start + startToken.length);
  return pythonSource.slice(start + 1, next === -1 ? pythonSource.length : next);
}

function assertExplicitExpandable(functionName, expected) {
  const body = topLevelFunctionSource(functionName);
  const literal = expected ? "True" : "False";
  const opposite = expected ? "False" : "True";
  assert.match(
    body,
    new RegExp(`["]expandable["]\\s*:\\s*${literal}`),
    `${functionName} must explicitly declare expandable=${literal}.`,
  );
  assert.doesNotMatch(
    body,
    new RegExp(`["]expandable["]\\s*:\\s*${opposite}`),
    `${functionName} must not contain the opposite allocator policy.`,
  );
}

// Griptape Editor 0.123.1 classifies a custom widget as expandable unless
// ui_options.expandable is explicitly false. Hidden rows are removed before
// allocation. This is the distilled contract of mHn/yUn in the installed
// editor bundle, not a Picker-owned sizing algorithm.
function classifyEditorRow(element) {
  if (element.uiOptions.hide === true) return null;
  if (element.uiOptions.widget && element.uiOptions.expandable !== false) {
    return { ...element, kind: "expandable", weight: 4 };
  }
  return { ...element, kind: "fill", weight: 1 };
}

function allocateEditorStack(elements, {
  stackHeight,
  fallbackMeasuredHeight = 40,
  bottomReserve = 16,
  rowSpacing = 4,
} = {}) {
  const rows = elements.map(classifyEditorRow).filter(Boolean);
  const heights = new Map(rows.map((row) => [
    row.id,
    Number.isFinite(row.measuredHeight) ? row.measuredHeight : fallbackMeasuredHeight,
  ]));
  const gaps = Math.max(0, rows.length - 1) * rowSpacing;
  const baseHeight = [...heights.values()].reduce((total, height) => total + height, 0);
  let distributable = Math.max(0, stackHeight - baseHeight - gaps - bottomReserve);
  const expandable = rows.filter((row) => row.kind === "expandable");

  for (const [index, row] of expandable.entries()) {
    const remainingWeight = expandable
      .slice(index)
      .reduce((total, candidate) => total + candidate.weight, 0);
    const addition = index === expandable.length - 1
      ? distributable
      : Math.floor(distributable * row.weight / remainingWeight);
    heights.set(row.id, heights.get(row.id) + addition);
    distributable -= addition;
  }

  const allocatedHeight = [...heights.values()].reduce((total, height) => total + height, 0) + gaps;
  return {
    rows,
    heights,
    trailingSpacerHeight: Math.max(0, stackHeight - allocatedHeight),
  };
}

function pickerRows(expandable) {
  return [
    {
      id: "MAYA_SCENE",
      uiOptions: { widget: true, hide: true, expandable: false },
    },
    {
      id: "HMB_PICKER_COMMAND",
      uiOptions: { widget: true, hide: true, expandable: false },
    },
    {
      id: "HMB_PICKER_STATE",
      uiOptions: { widget: true, hide: false, expandable },
    },
  ];
}

// Live CDP evidence from the failing two-node workflow:
// - React Flow node: 1200px
// - mounted Picker root: 960px
// - HMB_PICKER_STATE host row/clip: 40px
// - elementFromPoint below the header: trailing grow/shrink/basis-0 spacer
// The editor keeps 16px as a bottom layout reserve, so a 960px authored root
// needs a 976px adaptive stack inside the 1200px node chrome.
const LIVE_CDP = Object.freeze({
  nodeHeight: 1200,
  authoredRootHeight: 960,
  observedStateRowHeight: 40,
  bottomReserve: 16,
  stackHeight: 976,
});

const broken = allocateEditorStack(pickerRows(false), LIVE_CDP);
assert.equal(broken.rows.length, 1, "Hidden Maya/command transports cannot consume allocator height.");
assert.equal(broken.rows[0].kind, "fill");
assert.equal(broken.heights.get("HMB_PICKER_STATE"), LIVE_CDP.observedStateRowHeight);
assert.equal(
  LIVE_CDP.authoredRootHeight - broken.heights.get("HMB_PICKER_STATE"),
  920,
  "expandable=False reproduces the live 920px body clip below the 40px header row.",
);
assert.equal(
  broken.trailingSpacerHeight,
  936,
  "The allocator gives the unused node body to its trailing grow spacer.",
);

for (const instanceId of ["picker-a", "picker-b"]) {
  const repaired = allocateEditorStack(pickerRows(true), LIVE_CDP);
  assert.equal(repaired.rows.length, 1, `${instanceId}: only the visible state row participates.`);
  assert.equal(repaired.rows[0].kind, "expandable", `${instanceId}: state row must receive spare height.`);
  assert.equal(
    repaired.heights.get("HMB_PICKER_STATE"),
    LIVE_CDP.authoredRootHeight,
    `${instanceId}: the 960px Picker root must fit without clipping.`,
  );
  assert.equal(
    repaired.trailingSpacerHeight,
    LIVE_CDP.bottomReserve,
    `${instanceId}: only the editor's intentional bottom reserve may remain.`,
  );
}

// Both creation and rehydration must restore the visible row contract. The two
// durable-but-hidden transports remain non-expandable so they never compete
// with the dashboard if an older workflow briefly exposes their metadata.
assertExplicitExpandable("_configure_picker_widget_parameter", true);
assertExplicitExpandable("_add_picker_widget", true);
assertExplicitExpandable("_configure_picker_command_parameter", false);
assertExplicitExpandable("_add_picker_command_bridge", false);
assertExplicitExpandable("_configure_hidden_maya_scene_parameter", false);

console.log("HMB VideoPicker editor allocator contract regression: PASS");
