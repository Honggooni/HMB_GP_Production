import assert from "node:assert/strict";
import fs from "node:fs";


const widgetPath = new URL("../../widgets/HMBSeedanceGenerationWidget.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widget = await import(
  `data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`
);
const clone = (value) => JSON.parse(JSON.stringify(value));

const channelUuid = "11111111-1111-4111-8111-111111111111";
const publisherUuid = "22222222-2222-4222-8222-222222222222";
const shot1Uuid = "33333333-3333-4333-8333-333333333333";
const shot4Uuid = "44444444-4444-4444-8444-444444444444";
const catalog = {
  schema: "hmb-shot-routing-catalog",
  version: 1,
  publisher_instance_uuid: publisherUuid,
  channel_uuid: channelUuid,
  generation: 7,
  metadata_sha256: "a".repeat(64),
  shots: [
    { shot_uuid: shot1Uuid, number: 1, name: "Opening", revision: 1 },
    { shot_uuid: shot4Uuid, number: 4, name: "Hero", revision: 2 },
  ],
};

const only = widget.hmbSeedanceShotState({ value: {
  schema: "hmb-seedance-shot-ui",
  schema_version: 1,
  shot_catalog: catalog,
  shot: { channel_uuid: "", shot_uuid: "", number: 1, name: "Only" },
} });
assert.equal(only.shot.name, "Only");
assert.equal(only.shot.shot_uuid, "");
assert.deepEqual(
  widget.hmbSeedanceShotOptions(only).map((item) => item.name),
  ["Only", "Opening", "Hero"],
  "Seedance must always prepend prompt-only mode to every available Shot.",
);

const disconnected = widget.hmbSeedanceShotState({ value: {
  schema: "hmb-seedance-shot-ui", schema_version: 1, shot_catalog: {}, shot: {},
} });
assert.equal(disconnected.shot.name, "Only");
assert.deepEqual(
  widget.hmbSeedanceShotOptions(disconnected).map((item) => item.name),
  ["Only"],
  "A Seedance without media libraries remains independently usable.",
);

const selectedValue = {
  ...only,
  shot: { channel_uuid: channelUuid, shot_uuid: shot4Uuid, number: 4, name: "Hero" },
};
const selected = widget.hmbSeedanceShotState({ value: selectedValue });
assert.equal(selected.shot.shot_uuid, shot4Uuid);
assert.equal(selected.shot.number, 4);
assert.equal(widget.hmbSeedanceShotAccent(selected), "#8B5CF6");

const serialized = widget.hmbSeedanceShotState({ value: JSON.stringify(selectedValue) });
assert.equal(serialized.shot.shot_uuid, shot4Uuid, "Serialized dict props must retain Shot identity.");

const renumberCatalog = clone(catalog);
renumberCatalog.generation = 8;
renumberCatalog.shots[1] = {
  ...renumberCatalog.shots[1], number: 3, name: "Hero Revised", revision: 3,
};
const renumbered = widget.hmbSeedanceShotState({ value: {
  ...selected,
  shot_catalog: renumberCatalog,
} });
assert.equal(renumbered.shot.shot_uuid, shot4Uuid);
assert.equal(renumbered.shot.number, 3);
assert.equal(renumbered.shot.name, "Hero Revised");
assert.equal(widget.hmbSeedanceShotAccent(renumbered), "#10B981");

const deletedCatalog = clone(renumberCatalog);
deletedCatalog.generation = 9;
deletedCatalog.shots = deletedCatalog.shots.slice(0, 1);
const deleted = widget.hmbSeedanceShotState({ value: {
  ...renumbered,
  shot_catalog: deletedCatalog,
} });
assert.equal(deleted.shot.shot_uuid, "");
assert.equal(deleted.shot.name, "Only");

for (const [number, accent] of Object.entries({
  1: "#F472B6", 2: "#3B82F6", 3: "#10B981", 4: "#8B5CF6", 5: "#EAB308",
})) {
  assert.equal(widget.HMB_SEEDANCE_JEWEL_NIGHT_PALETTE[number], accent);
}
assert.match(widgetSource, /data-seedance-shot-number/);
assert.match(widgetSource, /String\(state\.shot\.number\)\.padStart\(2, "0"\)/);
assert.match(widgetSource, /height:64px/);
assert.match(widgetSource, /HMBSeedanceGeneration/);
assert.doesNotMatch(widgetSource, /addEventListener\([^\n]*hmb-shot-routing-catalog-v1/);
assert.doesNotMatch(widgetSource, /__hmbShotRoutingCatalogs/);
assert.equal(typeof widget.hmbGuardSelectedNodeKeyboardDelete, "function");

const lifecycleContainer = {};
const oldPendingOwner = widget.hmbSeedanceNextChangeOwner(lifecycleContainer);
widget.hmbSeedanceNextChangeOwner(lifecycleContainer);
const remountedOwner = widget.hmbSeedanceNextChangeOwner(lifecycleContainer);
assert.equal(widget.hmbSeedanceOwnsChange(lifecycleContainer, oldPendingOwner), false);
assert.equal(widget.hmbSeedanceOwnsChange(lifecycleContainer, remountedOwner), true);

console.log(
  "HMB Seedance Shot routing UI regression: PASS "
  + "(Only + Shot catalog, visible number, serialized props, UUID rename/delete)",
);
