import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const catalog = JSON.parse(fs.readFileSync(new URL("../picker/HMB_Marker_Catalog.json", import.meta.url), "utf8"));
const actor = ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink", "Cyan"];
const ghost = ["Sky Blue", "Mint", "Beige", "Lavender"];
const object = ["Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"];
const expected = { actor, ghost, object };
assert.deepEqual(picker.hmbPickerPaletteGroups(catalog), expected);
assert.deepEqual(picker.hmbPickerPaletteGroups(null), expected);

const legacy = structuredClone(catalog);
legacy.version = 4;
legacy.character = legacy.character.filter(row => row.name !== "Cyan");
legacy.background = legacy.background.filter(row => row.name !== "Lavender");
const oldRows = structuredClone([...legacy.character, ...legacy.background]);
const upgraded = picker.hmbNormalizePickerMarkerCatalog(legacy);
assert.equal(upgraded.version, 5);
assert.deepEqual(picker.hmbPickerPaletteGroups(upgraded), expected);
assert.deepEqual(upgraded.options, [...actor, ...ghost, ...object]);
for (const row of oldRows) {
  assert.deepEqual([...upgraded.character, ...upgraded.background].find(item => item.name === row.name), row);
}
assert.deepEqual(picker.hmbNormalizePickerMarkerCatalog(upgraded), upgraded, "Saved-state palette migration is idempotent.");
assert.equal(legacy.character.length, 7, "Never mutate the incoming saved state.");
assert.equal(legacy.background.length, 7);
for (const [group, index, name] of [["background", 0, "Cyan"], ["character", 0, "Lavender"]]) {
  const malformed = structuredClone(legacy);
  malformed[group][index].name = name;
  const repaired = picker.hmbNormalizePickerMarkerCatalog(malformed);
  assert.deepEqual(picker.hmbPickerPaletteGroups(repaired), expected);
  assert.deepEqual(picker.hmbNormalizePickerMarkerCatalog(repaired), repaired, "Conflicting legacy names must not create a non-idempotent 15-choice catalog.");
}
assert.match(picker.hmbPickerColorStyle("Cyan", legacy), /rgb\(0,\s*217,\s*217\)/);
assert.match(picker.hmbPickerColorStyle("Lavender", legacy), /rgb\(184,\s*166,\s*217\)/);

let state = {
  marker_catalog: legacy,
  marker_catalog_version: 4,
  active_slot_count: 1,
  selected_video_slot: 1,
  selected_outliner_path: "|Actor",
  selected_outliner_paths: ["|Actor"],
  outliner_nodes: [
    { full_path: "|Actor", asset_id: "Actor", node_type: "transform", maya_uuid: "actor-uuid" },
    { full_path: "|Ghost", asset_id: "Ghost", node_type: "transform", maya_uuid: "ghost-uuid" },
  ],
  slot_assignments: [{ video_slot: 1, bindings: [] }],
};
// The public compatibility binding helper is inert except for normalizing the
// same saved state used by the widget; it does not create or switch a Shot.
state = picker.hmbBindActivePickerShot(state);
state = picker.hmbPickerApplyColorToSelection(state, "Cyan");
assert.equal(state.selected_color, "Cyan");
assert.equal(state.slot_assignments[0].bindings[0].color, "Cyan");
state = picker.hmbPickerSelectOutlinerPath(state, "|Ghost");
state = picker.hmbPickerApplyColorToSelection(state, "Lavender");
assert.equal(state.selected_color, "Lavender");
assert.deepEqual(state.slot_assignments[0].bindings.map(row => row.color), ["Cyan", "Lavender"]);
const reopened = picker.hmbBindActivePickerShot(JSON.parse(JSON.stringify(state)));
assert.equal(reopened.selected_color, "Lavender");
assert.deepEqual(reopened.slot_assignments[0].bindings.map(row => row.color), ["Cyan", "Lavender"]);
assert.deepEqual(picker.hmbPickerPaletteGroups(reopened.marker_catalog), expected);
assert.equal(picker.hmbPickerClearOutlinerColor(reopened, "|Actor").slot_assignments[0].bindings[0].color, "Lavender");

// Every solid is globally unique, including across Actor/Ghost groups; none
// takes a reserved exact-RGB screen-space Pattern ID.
const solidRows = [...catalog.character, ...catalog.background.filter(row => row.kind === "solid")];
const key = row => row.rgb.map(channel => Math.round(channel * 255)).join(",");
assert.equal(new Set(solidRows.map(key)).size, 12);
const reserved = new Set(catalog.background.filter(row => row.kind === "pattern").map(row => row.screen_space_id_rgb.join(",")));
assert.ok(solidRows.every(row => !reserved.has(key(row))));
console.log("PASS: extended 8/4/4 palette, legacy migration, exact color styles, selection/save/reload/clear, and Actor/Ghost/Pattern non-overlap.");
