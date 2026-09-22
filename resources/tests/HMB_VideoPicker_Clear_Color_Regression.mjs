import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source + '\nexport { outlinerHtml };').toString('base64')}`);
const binding = (path, color) => ({ full_dag_path: path, maya_uuid: `uuid-${path}`, color, enabled: true, group_name: path, video_slot: 1 });
const initial = {
  scene_path: "C:/scene.mb", active_picker_shot_uuid: "shot-1", active_slot_count: 1,
  outliner_nodes: [
    { name: "A", full_path: "|A", maya_uuid: "uuid-|A", depth_meshes: [{name: "Mesh", full_path: "|A|Mesh", maya_uuid: "uuid-|A|Mesh"}] },
    { name: "B", full_path: "|B", maya_uuid: "uuid-|B" },
    { name: "Unassigned", full_path: "|C", maya_uuid: "uuid-|C" },
  ],
  outliner_expanded: [], outliner_search: "", depth_settings: { range: "close", expanded_roots: ["|A"] },
  slot_visibility: [{ video_slot: 1, hidden_paths: ["|A"] }],
  slot_assignments: [{ video_slot: 1, bindings: [binding("|A", "Red"), binding("|B", "Red"), binding("|A|Mesh", "Mint")] },
    { video_slot: 2, bindings: [binding("|other", "Blue")] }],
  picker_shots: [{ workspace_uuid: "shot-1" }, { workspace_uuid: "shot-2", selected_video_uids: ["keep"] }],
  videos: [{ video_uid: "keep", video_path: "C:/saved.mp4", markers: [binding("|A", "Red")] }],
  snapshots: [{ file_path: "C:/saved.png", frame: 101 }],
};
let state = picker.hmbPickerSelectOutlinerPath(initial, "|B");
state = picker.hmbPickerSelectOutlinerPath(state, "|A", { ctrlKey: true });
const before = structuredClone(state);
const cleared = picker.hmbPickerClearOutlinerColor(state, "|A");
assert.deepEqual(state, before, "Clear must not mutate its input snapshot");
assert.deepEqual(cleared.slot_assignments[0].bindings.map(b => b.full_dag_path), ["|B", "|A|Mesh"]);
assert.equal(cleared.slot_assignments[0].bindings[0].color, "Red", "Same-color peer is independent");
assert.equal(cleared.slot_assignments[0].bindings[1].color, "Mint", "Explicit child color survives root clear");
assert.equal(cleared.selected_color, "");
for (const key of ["outliner_nodes", "slot_visibility", "depth_settings", "picker_shots", "videos", "snapshots", "selected_outliner_paths"]) {
  assert.deepEqual(cleared[key], before[key], key);
}
assert.deepEqual(cleared.slot_assignments[1], before.slot_assignments[1]);
assert.equal(picker.hmbPickerClearOutlinerColor(cleared, "|A"), cleared, "Repeated clear is a no-op");
assert.equal(picker.hmbPickerClearOutlinerColor(cleared, "|unknown"), cleared);
assert.equal(picker.hmbPickerClearOutlinerColor(cleared, "|C"), cleared);
const childOnly = picker.hmbPickerClearOutlinerColor(state, "|A|Mesh");
assert.deepEqual(childOnly.slot_assignments[0].bindings.map(b => b.full_dag_path), ["|A", "|B"]);
const empty = picker.hmbPickerClearOutlinerColor(picker.hmbPickerClearOutlinerColor(cleared, "|B"), "|A|Mesh");
assert.deepEqual(empty.slot_assignments[0], { video_slot: 1, bindings: [] });
assert.deepEqual(JSON.parse(JSON.stringify(empty)).slot_assignments, empty.slot_assignments);
const legacy = structuredClone(state);
delete legacy.slot_assignments[0].bindings[0].maya_uuid;
assert.equal(picker.hmbPickerClearOutlinerColor(legacy, "|A").slot_assignments[0].bindings.length, 2);

const tr = { outliner: "Outliner", depthPass: "Mesh", outputOn: "On", outputOff: "Off", clearOutlinerColor: "컬러 해제 (오브젝트 유지)" };
const html = picker.outlinerHtml(state, state.slot_assignments[0].bindings, tr);
assert.equal((html.match(/data-clear-color-path=/g) || []).length, 4);
assert.match(html, /data-visibility-path="\|A"[^]*?<\/button>\s*<button[^>]*data-clear-color-path="\|A"/);
assert.match(html, /data-clear-color-path="\|C"[^>]* disabled/);
assert.doesNotMatch(html, /data-clear-color-path="\|A\|Mesh"[^>]* disabled/, "Inherited eye-off must not prevent color cleanup");
const lockedHtml = picker.outlinerHtml(state, state.slot_assignments[0].bindings, tr, true);
assert.equal((lockedHtml.match(/data-clear-color-path="[^"]+"[^>]* disabled/g) || []).length, 4);

const clearButtons = [true, false].map(assigned => ({
  disabled: false, attrs: { "data-has-assigned-color": String(assigned) },
  getAttribute(name) { return this.attrs[name]; }, setAttribute(name, value) { this.attrs[name] = value; },
}));
const busyDom = { querySelectorAll: selector => selector === "[data-clear-color-path]" ? clearButtons : [] };
picker.hmbSetPickerVisibilityBusy(busyDom, true);
assert.ok(clearButtons.every(button => button.disabled));
picker.hmbSetPickerVisibilityBusy(busyDom, false);
assert.deepEqual(clearButtons.map(button => button.disabled), [false, true]);

// Execute the actual paint-first handler: no Maya command, no selection change,
// one state publication, and a live lock check for a stale enabled button.
const handlerText = source.slice(source.indexOf("  const clearOutlinerColor = (path) => {"), source.indexOf('  on(outlinerScroll, "pointerdown",'));
let live = state, locked = false;
const order = [];
const handler = new Function("currentWidgetState", "pickerLocalInteractionLocked", "hmbPickerClearOutlinerColor",
  "hmbRenderPickerOutlinerLocal", "hmbApplyPickerPaletteSelectionToDom", "schedulePickerStatePublicationAfterPaint", "container", "tr",
  handlerText + "\nreturn clearOutlinerColor;")(
  () => live, () => locked, picker.hmbPickerClearOutlinerColor,
  (_container, next) => { order.push("paint"); assert.equal(next.selected_color, ""); return true; },
  () => order.push("palette"), next => { order.push("publish"); live = next; }, {}, tr,
);
locked = true; handler("|A"); assert.deepEqual(order, []);
locked = false; handler("|A"); assert.deepEqual(order, ["paint", "palette", "publish"]);
handler("|A"); assert.equal(order.length, 3);
assert.deepEqual(live.videos, state.videos);

const delegation = source.slice(source.indexOf('on(outlinerScroll, "click",'), source.indexOf('on(outlinerScroll, "keydown",'));
let click, count = 0, selections = 0;
new Function("on", "outlinerScroll", "clearOutlinerColor", "clean", "currentWidgetState", "hmbNormalizeDepthSettings",
  "publishDepthSettings", "toggleOutlinerVisibility", "toggleOutlinerPath", "selectOutlinerPath", delegation)(
  (_root, _type, callback) => { click = callback; }, {}, path => { assert.equal(path, "|A"); count++; }, String,
  () => state, picker.hmbNormalizeDepthSettings, () => {}, () => {}, () => {}, () => { selections++; },
);
const button = { disabled: false, getAttribute: () => "|A" };
const event = { preventDefault() {}, stopPropagation() {}, target: { closest: selector =>
  ["[data-clear-color-path]", "[data-group-path]"].includes(selector) ? button : null } };
click(event); assert.equal(count, 1); assert.equal(selections, 0);
button.disabled = true; click(event); assert.equal(count, 1); assert.equal(selections, 0);
console.log("HMB Picker color clear: PASS (row-only, duplicate colors, child/root, busy, paint-first, saved media preserved)");
