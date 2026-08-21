import fs from "node:fs";


const widgetPath = new URL(
  "../../widgets/HMBVideoPickerLibraryWidget_v032.js",
  import.meta.url,
);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const picker = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);

// Exact compact markup contract:
//   root border (2) + fixed header (58) + summary vertical padding (12)
//   + N full Shot rows (180 each) + N-1 summary gaps (6 each).
const COMPACT_FIXED_HEIGHT = 72;
const COMPACT_SHOT_HEIGHT = 180;
const COMPACT_SHOT_GAP = 6;
const COMPACT_SHOT_STRIDE = COMPACT_SHOT_HEIGHT + COMPACT_SHOT_GAP;
const compactContentHeight = (shotCount) => (
  COMPACT_FIXED_HEIGHT
  + Math.max(1, shotCount) * COMPACT_SHOT_HEIGHT
  + Math.max(0, Math.max(1, shotCount) - 1) * COMPACT_SHOT_GAP
);
const ONE_SHOT_COMPACT_HEIGHT = compactContentHeight(1);
const COMPACT_OUTER_MIN_HEIGHT = 360;
const COMPACT_OUTER_CHROME_RESERVE = COMPACT_OUTER_MIN_HEIGHT - ONE_SHOT_COMPACT_HEIGHT;
const COMPACT_ALLOCATOR_SAFE_RESERVE = 32;
const workspaceUuid = "00000000-0000-4000-8000-000000000001";
const secondWorkspaceUuid = "a79ca5de-3d50-52c9-b3b7-fb88dea8fc49";
const publisherUuid = "11111111-1111-4111-8111-111111111111";
const channelUuid = "22222222-2222-4222-8222-222222222222";
const firstShotUuid = "33333333-3333-4333-8333-333333333333";
const secondShotUuid = "44444444-4444-4444-8444-444444444444";

const emptyState = {
  picker_shots: [{
    workspace_uuid: workspaceUuid,
    number: 1,
    name: "Shot 1",
    video_asset_uids: [],
    selected_video_uids: [],
  }],
  active_picker_shot_uuid: workspaceUuid,
  videos: [],
};
const populatedState = {
  picker_shots: [{
    workspace_uuid: workspaceUuid,
    number: 1,
    name: "Shot 1",
    video_asset_uids: ["video-1"],
    selected_video_uids: ["video-1"],
  }],
  active_picker_shot_uuid: workspaceUuid,
  videos: [{
    video_uid: "video-1",
    video_path: "C:/media/one.mp4",
    label: "one.mp4",
  }],
};
const twoPopulatedShotsState = {
  shot_publisher_instance_uuid: publisherUuid,
  channel_uuid: channelUuid,
  shot_uuid: firstShotUuid,
  shot_number: 1,
  shot_name: "Shot 1",
  shot_selections: [
    { shot_uuid: firstShotUuid, number: 1, name: "Shot 1" },
    { shot_uuid: secondShotUuid, number: 2, name: "Shot 2" },
  ],
  picker_shots: [
    {
      workspace_uuid: workspaceUuid,
      bound_shot_uuid: firstShotUuid,
      number: 1,
      name: "Shot 1",
      video_asset_uids: ["video-1"],
      selected_video_uids: ["video-1"],
    },
    {
      workspace_uuid: secondWorkspaceUuid,
      bound_shot_uuid: secondShotUuid,
      number: 2,
      name: "Shot 2",
      video_asset_uids: ["video-2"],
      selected_video_uids: ["video-2"],
    },
  ],
  active_picker_shot_uuid: workspaceUuid,
  videos: [
    { video_uid: "video-1", video_path: "C:/media/one.mp4", label: "one.mp4" },
    { video_uid: "video-2", video_path: "C:/media/two.mp4", label: "two.mp4" },
  ],
};

function emptyShotsState(count) {
  const shotSelections = Array.from({ length: count }, (_unused, index) => ({
    shot_uuid: `60000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    number: index + 1,
    name: `Shot ${index + 1}`,
    revision: 1,
  }));
  const rows = Array.from({ length: count }, (_unused, index) => ({
    workspace_uuid: `50000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    bound_shot_uuid: shotSelections[index].shot_uuid,
    number: index + 1,
    name: `Shot ${index + 1}`,
    video_asset_uids: [],
    selected_video_uids: [],
  }));
  return {
    shot_publisher_instance_uuid: publisherUuid,
    channel_uuid: channelUuid,
    shot_uuid: shotSelections[0]?.shot_uuid || "",
    shot_number: 1,
    shot_name: "Shot 1",
    shot_selections: shotSelections,
    picker_shots: rows,
    active_picker_shot_uuid: rows[0]?.workspace_uuid || "",
    videos: [],
  };
}

function fakeStyle() {
  const values = new Map();
  return {
    setProperty(name, value) { values.set(String(name), String(value)); },
    getPropertyValue(name) { return values.get(String(name)) || ""; },
    getPropertyPriority() { return ""; },
    removeProperty(name) {
      const previous = values.get(String(name)) || "";
      values.delete(String(name));
      return previous;
    },
  };
}

function compactSizingHarness() {
  const clip = { style: fakeStyle() };
  const root = {
    style: fakeStyle(),
    getAttribute(name) { return name === "data-picker-view" ? "compact" : ""; },
    getBoundingClientRect() { return { height: 0 }; },
    offsetHeight: 0,
    scrollHeight: 0,
  };
  const container = {
    style: fakeStyle(),
    dataset: {},
    parentElement: null,
    querySelector(selector) {
      if (selector === ".hmbvp") return root;
      if (selector === ".hmbvp-clip") return clip;
      return null;
    },
  };
  return { container, clip, root };
}

function compactOuterHarness(topInset) {
  const shell = {
    className: "react-flow__node",
    classList: { contains: (name) => name === "react-flow__node" },
    style: fakeStyle(),
    offsetHeight: 1200,
    getBoundingClientRect() {
      return { top: 100, height: 1200, bottom: 1300, width: 1400 };
    },
  };
  const container = {
    closest(selector) { return selector === ".react-flow__node" ? shell : null; },
    getBoundingClientRect() {
      return { top: 100 + topInset, height: 0, bottom: 100 + topInset, width: 1400 };
    },
  };
  return { container, shell };
}

function sourceInteger(source, name) {
  const match = source.match(new RegExp(`^${name}\\s*=\\s*(\\d+)`, "m"));
  return match ? Number(match[1]) : NaN;
}

const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };

const emptyMeasured = picker.hmbVideoPickerCompactMeasurementHeight(emptyState);
const populatedMeasured = picker.hmbVideoPickerCompactMeasurementHeight(populatedState);
const twoMeasured = picker.hmbVideoPickerCompactMeasurementHeight(twoPopulatedShotsState);
check(
  emptyMeasured === ONE_SHOT_COMPACT_HEIGHT,
  `empty Shot keeps one full row: expected ${ONE_SHOT_COMPACT_HEIGHT}px, received ${emptyMeasured}px`,
);
check(
  populatedMeasured === ONE_SHOT_COMPACT_HEIGHT,
  `one populated Shot compact height: expected ${ONE_SHOT_COMPACT_HEIGHT}px, received ${populatedMeasured}px`,
);
check(
  twoMeasured === compactContentHeight(2),
  `two Shots must add one complete row without a height cap: expected ${compactContentHeight(2)}px, received ${twoMeasured}px`,
);
for (let shotCount = 1; shotCount <= 5; shotCount += 1) {
  const measured = picker.hmbVideoPickerCompactMeasurementHeight(emptyShotsState(shotCount));
  const expected = compactContentHeight(shotCount);
  check(
    measured === expected,
    `${shotCount} empty Shot compact height: expected ${expected}px, received ${measured}px`,
  );
  if (shotCount > 1) {
    const previous = picker.hmbVideoPickerCompactMeasurementHeight(emptyShotsState(shotCount - 1));
    check(
      measured - previous === COMPACT_SHOT_STRIDE,
      `Shot ${shotCount} must grow compact content by exactly ${COMPACT_SHOT_STRIDE}px; received ${measured - previous}px`,
    );
  }
}

const harness = compactSizingHarness();
const appliedHeight = picker.hmbApplyVideoPickerCompactHostSizing(
  harness.container,
  emptyState,
);
check(
  appliedHeight === ONE_SHOT_COMPACT_HEIGHT,
  `live compact sizing: expected ${ONE_SHOT_COMPACT_HEIGHT}px, received ${appliedHeight}px`,
);
check(
  harness.clip.style.getPropertyValue("height") === `${ONE_SHOT_COMPACT_HEIGHT}px`,
  "compact clip must reserve one full Shot row even while empty",
);
check(
  harness.root.style.getPropertyValue("height") === `${ONE_SHOT_COMPACT_HEIGHT}px`,
  "compact root and clip must use the same content-derived height",
);
check(
  harness.root.style.getPropertyValue("overflow-y") === "visible",
  `compact root must not create an internal vertical scroller; received overflow-y=${harness.root.style.getPropertyValue("overflow-y") || "<unset>"}`,
);

// This geometry-only harness intentionally has no recognized Editor state-row
// signature. It must therefore keep the allocator-safe bootstrap reserve. The
// exact recognized-host reclaim is covered by the Editor tail regression.
for (const topInset of [72, COMPACT_OUTER_CHROME_RESERVE, 120]) {
  const outerHeights = [];
  for (let shotCount = 1; shotCount <= 3; shotCount += 1) {
    const outer = compactOuterHarness(topInset);
    outerHeights.push(picker.hmbApplyVideoPickerCompactGeometry(
      outer.container,
      compactContentHeight(shotCount),
    ));
    const expected = Math.max(
      COMPACT_OUTER_CHROME_RESERVE,
      topInset + COMPACT_ALLOCATOR_SAFE_RESERVE,
    )
      + compactContentHeight(shotCount);
    check(
      outerHeights.at(-1) === expected,
      `outer compact height at ${topInset}px host inset / ${shotCount} Shot(s): expected ${expected}px, received ${outerHeights.at(-1)}px`,
    );
    check(
      outer.shell.style.getPropertyValue("height") === `${expected}px`,
      `outer shell must publish the exact compact height ${expected}px`,
    );
  }
  check(
    outerHeights[1] - outerHeights[0] === COMPACT_SHOT_STRIDE,
    `outer Shot 2 growth at ${topInset}px inset must be ${COMPACT_SHOT_STRIDE}px; received ${outerHeights[1] - outerHeights[0]}px`,
  );
  check(
    outerHeights[2] - outerHeights[1] === COMPACT_SHOT_STRIDE,
    `outer Shot 3 growth at ${topInset}px inset must be ${COMPACT_SHOT_STRIDE}px; received ${outerHeights[2] - outerHeights[1]}px`,
  );
}

// An off-DOM measurement has no usable inset. Only that cold-mount case keeps
// the 108px bootstrap reserve until the connected host can be measured.
const unmeasuredOuter = compactOuterHarness(0);
check(
  picker.hmbApplyVideoPickerCompactGeometry(
    unmeasuredOuter.container,
    ONE_SHOT_COMPACT_HEIGHT,
  ) === COMPACT_OUTER_MIN_HEIGHT,
  "unmeasured compact host must retain the safe 360px cold-mount fallback",
);

const pythonSource = fs.readFileSync(
  new URL("../../HMBVideoPickerLibrary.py", import.meta.url),
  "utf8",
);
const pythonRowHeight = sourceInteger(pythonSource, "PICKER_WIDGET_COMPACT_MOUNT_HEIGHT");
const pythonOuterHeight = sourceInteger(pythonSource, "PICKER_COMPACT_NATIVE_HEIGHT");
const pythonExpandedRowHeight = sourceInteger(pythonSource, "PICKER_WIDGET_MIN_HEIGHT");
const pythonExpandedOuterHeight = sourceInteger(pythonSource, "PICKER_START_HEIGHT");
check(
  pythonRowHeight === ONE_SHOT_COMPACT_HEIGHT,
  `Python compact parameter-row floor: expected ${ONE_SHOT_COMPACT_HEIGHT}px, received ${pythonRowHeight}px`,
);
check(
  pythonOuterHeight === COMPACT_OUTER_MIN_HEIGHT,
  `Python compact outer minimum: expected ${COMPACT_OUTER_MIN_HEIGHT}px, received ${pythonOuterHeight}px`,
);
check(
  pythonOuterHeight - pythonRowHeight === COMPACT_OUTER_CHROME_RESERVE,
  `Python compact outer/widget reserve: expected ${COMPACT_OUTER_CHROME_RESERVE}px, received ${pythonOuterHeight - pythonRowHeight}px`,
);
check(
  pythonExpandedRowHeight === 1151 && pythonExpandedOuterHeight === 1200,
  `Python expanded initial relationship: expected row/outer 1151/1200, received ${pythonExpandedRowHeight}/${pythonExpandedOuterHeight}`,
);
check(
  /^PICKER_WIDGET_START_HEIGHT\s*=\s*PICKER_WIDGET_MIN_HEIGHT$/m.test(pythonSource),
  "Python parameter-row initial/default height must remain the expanded 1151px contract",
);

const manifest = JSON.parse(fs.readFileSync(
  new URL("../../griptape-nodes-library.json", import.meta.url),
  "utf8",
));
const manifestPicker = manifest.nodes?.find?.((entry) => entry?.class_name === "HMBVideoPickerLibrary")?.metadata;
check(!!manifestPicker, "manifest must register HMBVideoPickerLibrary metadata");
for (const key of ["height", "default_height", "preferred_height", "initial_height"]) {
  check(
    manifestPicker?.[key] === pythonExpandedOuterHeight,
    `manifest outer ${key}: expected expanded ${pythonExpandedOuterHeight}px, received ${manifestPicker?.[key]}`,
  );
  check(
    manifestPicker?.ui_options?.[key] === pythonExpandedOuterHeight,
    `manifest ui_options.${key}: expected expanded ${pythonExpandedOuterHeight}px, received ${manifestPicker?.ui_options?.[key]}`,
  );
}
check(
  manifestPicker?.min_height === pythonOuterHeight
    && manifestPicker?.ui_options?.min_height === pythonOuterHeight,
  `manifest compact outer floor must be ${pythonOuterHeight}px at both metadata levels`,
);

const measurementFunctionSource = widgetSource.slice(
  widgetSource.indexOf("function hmbVideoPickerCompactMeasurementHeightFromNormalizedState"),
  widgetSource.indexOf("export function hmbVideoPickerCompactMeasurementHeight", widgetSource.indexOf("function hmbVideoPickerCompactMeasurementHeightFromNormalizedState")),
);
check(
  !/Math\.min|COMPACT_BOOTSTRAP_HEIGHT|COMPACT_EMPTY_SHOT_HEIGHT/.test(measurementFunctionSource),
  "compact content measurement must not use a 360px cap or a shorter empty-Shot branch",
);
check(
  /\.compact-shot-row\.empty\{height:180px;min-height:180px\}/.test(widgetSource),
  "compact CSS must reserve the populated 180px row height for an empty Shot",
);
check(
  /video-picker-compact-summary[^}]*overflow-y:visible!important/.test(widgetSource),
  "compact Shot summary must grow vertically without an internal scrollbar",
);

if (failures.length) {
  throw new Error(
    `HMB VideoPicker compact black-tail regression failed:\n- ${failures.join("\n- ")}`,
  );
}

console.log("HMB VideoPicker compact black-tail regression: PASS");
