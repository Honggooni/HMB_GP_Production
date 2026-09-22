import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const root = (name, meshes = []) => ({
  name, full_path: `|${name}`, maya_uuid: `uuid-${name}`,
  depth_meshes: meshes.map(child => ({ name: child, full_path: `|${name}|${child}`, maya_uuid: `uuid-${child}` })),
});
const initial = {
  scene_path: "C:/shot/test.mb", scene_request_path: "C:/shot/test.mb",
  active_picker_shot_uuid: "shot-1", active_slot_count: 1,
  native_read_ready: true, scene_stage: "OUTLINER_READY", status: "OUTLINER_READY",
  outliner_nodes: [root("A", ["Mesh1", "Mesh2"]), root("B"), root("C"), root("D")],
  depth_settings: { range: "close", expanded_roots: ["|A"] },
  outliner_expanded: [], outliner_search: "",
  slot_assignments: [{ video_slot: 1, bindings: [{
    group_name: "D", full_dag_path: "|D", maya_uuid: "uuid-D", color: "Red", picker_order: 1,
  }] }],
  slot_visibility: [{ video_slot: 1, hidden_paths: ["|C"] }],
  picker_shots: [{ workspace_uuid: "shot-1" }, { workspace_uuid: "shot-2", selected_video_uids: ["keep"] }],
  videos: [{ video_uid: "keep", video_path: "C:/unchanged.mp4", selected: true }],
};
const paths = state => picker.hmbPickerSelectedOutlinerNodes(state).map(node => node.full_path);
const colorPaths = (state, color) => state.slot_assignments[0].bindings.filter(binding => binding.color === color).map(binding => binding.full_dag_path);
let state = picker.hmbPickerSelectOutlinerPath(initial, "|A");
assert.deepEqual(paths(state), ["|A"]);
state = picker.hmbPickerSelectOutlinerPath(state, "|B", { ctrlKey: true });
state = picker.hmbPickerSelectOutlinerPath(state, "|A|Mesh1", { metaKey: true });
assert.deepEqual(paths(state), ["|A", "|A|Mesh1", "|B"]);
assert.equal(state.selected_outliner_path, "|A|Mesh1");
state = picker.hmbPickerSelectOutlinerPath(state, "|A", { ctrlKey: true });
assert.deepEqual(paths(state), ["|A|Mesh1", "|B"]);

// Shift follows all visible rows, not just the virtualized DOM page. Root and
// individual child meshes both participate; collapsed/filtered children do not.
state = picker.hmbPickerSelectOutlinerPath(state, "|A|Mesh1");
state = picker.hmbPickerSelectOutlinerPath(state, "|C", { shiftKey: true });
assert.deepEqual(paths(state), ["|A|Mesh1", "|A|Mesh2", "|B", "|C"]);
state = picker.hmbPickerSelectOutlinerPath(state, "|A|Mesh2", { shiftKey: true });
assert.deepEqual(paths(state), ["|A|Mesh1", "|A|Mesh2"]);
state = picker.hmbPickerSelectOutlinerPath(state, "|D", { ctrlKey: true });
state = picker.hmbPickerSelectOutlinerPath(state, "|C", { ctrlKey: true, shiftKey: true });
assert.deepEqual(paths(state), ["|A|Mesh1", "|A|Mesh2", "|C", "|D"]);
const collapsed = picker.hmbPickerSelectOutlinerPath({ ...initial, depth_settings: { expanded_roots: [] } }, "|A");
assert.deepEqual(paths(picker.hmbPickerSelectOutlinerPath(collapsed, "|C", { shiftKey: true })), ["|A", "|B", "|C"]);
const filtered = picker.hmbPickerSelectOutlinerPath({ ...initial, outliner_search: "Mesh" }, "|A|Mesh1");
assert.deepEqual(paths(picker.hmbPickerSelectOutlinerPath(filtered, "|A|Mesh2", { shiftKey: true })), ["|A|Mesh1", "|A|Mesh2"]);

// All selected objects receive one atomic mutation. Reusing Red must not steal
// it from D, and changing those objects again must preserve unrelated records.
state = picker.hmbPickerSelectOutlinerPath(initial, "|A|Mesh1");
state = picker.hmbPickerSelectOutlinerPath(state, "|B", { ctrlKey: true });
const before = structuredClone(state);
const assigned = picker.hmbPickerApplyColorToSelection(state, "Red");
assert.deepEqual(colorPaths(assigned, "Red"), ["|D", "|A|Mesh1", "|B"]);
assert.deepEqual(state, before, "A palette action must not mutate the input snapshot.");
assert.deepEqual(assigned.videos, initial.videos);
assert.deepEqual(assigned.picker_shots, initial.picker_shots);
assert.deepEqual(assigned.slot_visibility, initial.slot_visibility);
const reassigned = picker.hmbPickerApplyColorToSelection(assigned, "Blue");
assert.deepEqual(colorPaths(reassigned, "Red"), ["|D"]);
assert.deepEqual(colorPaths(reassigned, "Blue"), ["|A|Mesh1", "|B"]);
assert.equal(reassigned.slot_assignments[0].bindings.length, 3);
assert.deepEqual(reassigned.slot_assignments[0].bindings.map(item => item.picker_order), [1, 2, 3]);
assert.equal(picker.hmbPickerMarkerAllowsRepeat("Red", {}), true);

// Ctrl-click the only row to clear selection. Palette remains disabled and no
// hidden fallback is allowed to recolor the first root.
let none = picker.hmbPickerSelectOutlinerPath(initial, "|A");
none = picker.hmbPickerSelectOutlinerPath(none, "|A", { ctrlKey: true });
assert.deepEqual(paths(none), []);
assert.equal(picker.hmbPickerSelectedOutlinerNode(none), null);
assert.deepEqual(picker.hmbPickerApplyColorToSelection(none, "Blue").slot_assignments, initial.slot_assignments);

// Scene/shot ownership changes retire stale multi-selection rather than
// applying an old batch to newly loaded objects or another shot.
const otherShot = picker.hmbEnsurePickerOutlinerSelection({ ...assigned, active_picker_shot_uuid: "shot-2" });
assert.equal(paths(otherShot).length, 1);
assert.notEqual(otherShot.outliner_selection_scope, assigned.outliner_selection_scope);
const otherScene = picker.hmbEnsurePickerOutlinerSelection({
  ...assigned, scene_path: "C:/other.mb", scene_request_path: "C:/other.mb",
  outliner_nodes: [root("Other")],
});
assert.deepEqual(paths(otherScene), ["|Other"]);

// Thousands of off-screen rows are selectable through visible-list range logic
// without depending on a DOM window or starting background Maya work.
const many = { ...initial, outliner_nodes: Array.from({ length: 300 }, (_, index) => root(`N${index}`)) };
const head = picker.hmbPickerSelectOutlinerPath(many, "|N2");
assert.equal(paths(picker.hmbPickerSelectOutlinerPath(head, "|N250", { shiftKey: true })).length, 249);
assert.match(source, /aria-multiselectable="true"/);
assert.match(source, /selectOutlinerPath\(clean\(row\.getAttribute\?\.\("data-group-path"\)\), event\)/);

// Execute row routing too: eye/expand controls must never also select the row.
const rowHandlerSource = source.slice(
  source.indexOf('on(outlinerScroll, "click",'),
  source.indexOf('on(outlinerScroll, "keydown",'),
);
let rowClick;
const rowSelectionCalls = [];
const visibilityCalls = [];
const expansionCalls = [];
const depthChanges = [];
new Function("on", "outlinerScroll", "currentWidgetState", "hmbNormalizeDepthSettings", "clean",
  "publishDepthSettings", "toggleOutlinerVisibility", "toggleOutlinerPath", "selectOutlinerPath", rowHandlerSource)(
  (_root, event, callback) => { assert.equal(event, "click"); rowClick = callback; }, {}, () => initial,
  picker.hmbNormalizeDepthSettings, value => String(value ?? "").trim(),
  next => depthChanges.push(next), path => visibilityCalls.push(path), path => expansionCalls.push(path),
  (path, modifiers) => rowSelectionCalls.push({ path, ctrl: !!modifiers.ctrlKey, shift: !!modifiers.shiftKey }),
);
function rowEvent(kind, modifiers = {}) {
  const selectors = { eye: "[data-visibility-path]", expand: "[data-toggle-path]", depth: "[data-depth-toggle-path]" };
  return { ...modifiers, preventDefault() {}, stopPropagation() {}, target: {
    closest(selector) {
      if (selector === selectors[kind] || selector === "[data-group-path]") return { getAttribute: () => "|A" };
      return null;
    },
  } };
}
for (const kind of ["eye", "expand", "depth"]) rowClick(rowEvent(kind, { ctrlKey: true }));
assert.deepEqual(rowSelectionCalls, []);
assert.deepEqual(visibilityCalls, ["|A"]);
assert.deepEqual(expansionCalls, ["|A"]);
assert.equal(depthChanges.length, 1);
rowClick(rowEvent("row", { ctrlKey: true, shiftKey: true }));
assert.deepEqual(rowSelectionCalls, [{ path: "|A", ctrl: true, shift: true }]);

// Snapshot retries use retained valid READ metadata after capture errors, not
// the preceding capture's FAILED status; invalid READ and busy states stay off.
const ready = {
  ...initial, maya_available: true, maya_executable: "C:/Maya/mayabatch.exe",
  cameras: [{ full_path: "|cam" }], selected_camera: "|cam", camera: "|cam",
  start_frame: 101, end_frame: 173, source_fps: 24, output_fps: 24,
  output_width: 1280, output_height: 720,
};
for (const stage of ["OUTLINER_READY", "VIDEO_READY", "FAILED", "CANCELLED"]) {
  assert.equal(picker.pickerButtonAvailability({ ...ready, scene_stage: stage, status: stage }).snapshotEnabled, true, stage);
}
for (const changes of [
  { native_read_ready: false, scene_stage: "FAILED", status: "FAILED" },
  { scene_stage: "LOAD_FAILED", status: "FAILED" },
  { scene_stage: "STALE_RESULT_DISCARDED", status: "FAILED" },
  { status: "SNAPSHOT_RENDERING", scene_stage: "SNAPSHOT_RENDERING" },
  { cameras: [] }, { selected_camera: "", camera: "" }, { source_fps: 0 },
  { output_width: 0 }, { scene_request_path: "C:/new.mb" },
]) {
  assert.equal(picker.pickerButtonAvailability({ ...ready, ...changes }).snapshotEnabled, false, JSON.stringify(changes));
}
const snapshotHandler = source.slice(source.indexOf('on(container.querySelector("#create-snapshot")'), source.indexOf('on(container.querySelector("#delete-snapshot")'));
assert.match(snapshotHandler, /authoring_state:/);
assert.match(snapshotHandler, /slot_assignments: Array\.isArray\(currentLocal\.slot_assignments\)/);
assert.match(snapshotHandler, /selected_camera: clean\(currentLocal\.selected_camera \|\| currentLocal\.camera\)/);

// Execute the real handler, rather than merely matching its source. The former
// undefined `viewportVideo` variable threw before dispatch even for an enabled
// Snapshot button immediately after READ. The media controller owns pausing.
const snapshotButton = {};
const liveFrameInput = { value: "117" };
const dom = {
  querySelector(selector) {
    if (selector === "#create-snapshot") return snapshotButton;
    if (selector === "#video-frame-number") return liveFrameInput;
    return null;
  },
};
let click;
let pauses = 0;
const commands = [];
const logs = [];
let liveState = { ...ready, slot_assignments: assigned.slot_assignments, selected_camera: "|latestCamera" };
const installHandler = new Function(
  "on", "container", "currentWidgetState", "pickerButtonAvailability", "clean",
  "appendImmediateLogLine", "mediaController", "clamp", "dispatchCommand", "hmbNormalizeDepthSettings",
  snapshotHandler,
);
installHandler(
  (button, event, callback) => { assert.equal(button, snapshotButton); assert.equal(event, "click"); click = callback; },
  dom, () => liveState, picker.pickerButtonAvailability, value => String(value ?? "").trim(),
  (level, message) => logs.push({ level, message }), { pause: () => { pauses++; } },
  (value, min, max) => Math.max(min, Math.min(max, value)),
  (action, payload, id, options) => { commands.push({ action, payload, id, options }); return { delivered: true }; },
  picker.hmbNormalizeDepthSettings,
);
assert.equal(typeof click, "function");
assert.doesNotThrow(() => click({ preventDefault() {}, stopPropagation() {} }));
assert.equal(pauses, 1);
assert.equal(commands.length, 1);
assert.equal(commands[0].action, "render_snapshot");
assert.equal(commands[0].payload.snapshot_frame, 117);
assert.equal(commands[0].payload.authoring_state.selected_camera, "|latestCamera");
assert.deepEqual(commands[0].payload.authoring_state.slot_assignments, assigned.slot_assignments);
assert.equal(commands[0].options.reserveVisibility, true);
liveState = { ...liveState, status: "SNAPSHOT_RENDERING", scene_stage: "SNAPSHOT_RENDERING" };
click({ preventDefault() {}, stopPropagation() {} });
assert.equal(commands.length, 1, "A running capture must remain guarded.");
assert.equal(pauses, 1);

console.log("HMB VideoPicker multi-selection, repeat color, snapshot retry regression: PASS");
