import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const catalog = JSON.parse(fs.readFileSync(new URL("../picker/HMB_Marker_Catalog.json", import.meta.url), "utf8"));
const actor = ["Red", "Green", "Blue", "Yellow", "Orange", "Purple", "Pink", "Cyan", "Teal", "Brown"];
const ghost = ["Sky Blue", "Mint", "Beige", "Lavender", "Olive"];
const object = ["Direction Checker", "Sky Grid", "Floor Grid", "Position Pattern"];
const expected = { actor, ghost, object };
assert.deepEqual(picker.hmbPickerPaletteGroups(catalog), expected);
assert.deepEqual(picker.hmbPickerPaletteGroups(null), expected);

const legacyCatalog = version => JSON.parse(fs.readFileSync(
  new URL(`./fixtures/marker_catalog_v${version}.json`, import.meta.url), "utf8",
));
assert.equal(catalog.version, 6);
const legacy = legacyCatalog(4);
for (const [version, oldSize] of [[4, 7], [5, 8]]) {
  const saved = legacyCatalog(version);
  assert.deepEqual([saved.version, saved.character.length, saved.background.length], [version, oldSize, oldSize]);
  const before = structuredClone(saved);
  const upgraded = picker.hmbNormalizePickerMarkerCatalog(saved);
  assert.equal(upgraded.version, 6);
  assert.deepEqual(picker.hmbPickerPaletteGroups(upgraded), expected);
  assert.deepEqual(upgraded.options, [...actor, ...ghost, ...object]);
  for (const category of ["character", "background"]) {
    for (const row of before[category]) {
      assert.deepEqual(upgraded[category].find(item => item.name === row.name), row);
    }
  }
  assert.deepEqual(picker.hmbNormalizePickerMarkerCatalog(upgraded), upgraded);
  assert.deepEqual(saved, before, "Never mutate an incoming saved catalog.");
}
for (const [group, index, name] of [["background", 0, "Cyan"], ["character", 0, "Lavender"]]) {
  const malformed = structuredClone(legacy);
  malformed[group][index].name = name;
  const repaired = picker.hmbNormalizePickerMarkerCatalog(malformed);
  assert.deepEqual(picker.hmbPickerPaletteGroups(repaired), expected);
  assert.deepEqual(picker.hmbNormalizePickerMarkerCatalog(repaired), repaired, "Repairing conflicting legacy names must be idempotent.");
}
assert.match(picker.hmbPickerColorStyle("Cyan", legacy), /rgb\(0,\s*217,\s*217\)/);
assert.match(picker.hmbPickerColorStyle("Lavender", legacy), /rgb\(184,\s*166,\s*217\)/);
for (const [name, rgb] of Object.entries({Teal: [0, 128, 128], Brown: [139, 69, 19], Olive: [128, 128, 0]})) {
  const row = [...catalog.character, ...catalog.background].find(item => item.name === name);
  assert.deepEqual(row.rgb, rgb.map(channel => channel / 255));
  assert.equal(picker.hmbPickerColorStyle(name, legacy).replace(/\s/g, ""), `background:rgb(${rgb.join(",")})`);
}

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

for (const version of [4, 5]) {
  const names = ["Teal", "Brown", "Olive", "Teal", "Brown", "Olive"];
  let authored = picker.hmbBindActivePickerShot({
    marker_catalog: legacyCatalog(version), marker_catalog_version: version,
    active_slot_count: 1, selected_video_slot: 1,
    slot_assignments: [{video_slot: 1, bindings: []}],
    outliner_nodes: names.map((_, i) => ({
      full_path: `|Target${i}`, asset_id: `Target${i}`, maya_uuid: `target-${i}`, node_type: "transform",
    })),
  });
  for (const [i, name] of names.entries()) {
    authored = picker.hmbPickerSelectOutlinerPath(authored, `|Target${i}`);
    authored = picker.hmbPickerApplyColorToSelection(authored, name);
  }
  const restored = picker.hmbBindActivePickerShot(JSON.parse(JSON.stringify(authored)));
  assert.deepEqual(restored.slot_assignments, authored.slot_assignments);
  assert.deepEqual(restored.slot_assignments[0].bindings.map(item => item.color), names);
  assert.deepEqual(restored.slot_assignments[0].bindings.map(item => item.full_dag_path), names.map((_, i) => `|Target${i}`));
  assert.equal(restored.selected_color, "Olive");
  assert.equal(restored.marker_catalog.version, 6);
}

// Every solid is globally unique, including across Actor/Ghost groups; none
// takes a reserved exact-RGB screen-space Pattern ID.
const solidRows = [...catalog.character, ...catalog.background.filter(row => row.kind === "solid")];
const key = row => row.rgb.map(channel => Math.round(channel * 255)).join(",");
assert.equal(new Set(solidRows.map(key)).size, 15);
const reserved = new Set(catalog.background.filter(row => row.kind === "pattern").map(row => row.screen_space_id_rgb.join(",")));
assert.ok(solidRows.every(row => !reserved.has(key(row))));
console.log("PASS: 10 Actor, 5 Ghost, 4 Pattern, archived v4/v5 migration, exact RGB, repeated assignments, save/reload/clear and non-overlap.");
