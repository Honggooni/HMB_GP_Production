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
assert.equal(only.remote_prompt_route.connected, false);
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

const connectedRoute = {
  schema: "hmb-seedance-remote-prompt-route",
  version: 1,
  connected: true,
  source_node_name: "HMBAgentLibrary_4",
  target_node_name: "HMB Seedance Generation_4",
  source_parameter: "output",
  target_parameter: "prompt",
};
const routed = widget.hmbSeedanceShotState({ value: {
  ...selectedValue,
  remote_prompt_route: connectedRoute,
} });
assert.equal(routed.remote_prompt_route.connected, true);
assert.equal(routed.remote_prompt_route.source_node_name, "HMBAgentLibrary_4");
assert.equal(routed.remote_prompt_route.previous_target_node_name, "");
assert.equal(widget.hmbSeedanceRemotePromptRoute({
  ...connectedRoute,
  previous_target_node_name: "x".repeat(513),
}).connected, false, "Reset target aliases remain bounded node names.");

const edge = (id, ariaLabel) => ({
  getAttribute(name) {
    if (name === "data-id") return id;
    if (name === "aria-label") return ariaLabel;
    return "";
  },
});
const exactEdgeId = (
  "HMBAgentLibrary_4-output-HMB Seedance Generation_4-prompt-1700000000000"
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(exactEdgeId, "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4"),
    connectedRoute,
  ),
  true,
  "Only the exact Agent.output -> Seedance.prompt DOM edge may be hidden.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4-agent-HMB Seedance Generation_4-prompt-1700000000000",
      "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4",
    ),
    connectedRoute,
  ),
  false,
  "A different Agent handle must remain visible.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMB Seedance Generation_4-VIDEO_OUT-HMB Seedance Generation_5-VIDEO_REFERENCES-1700000000000",
      "Edge from HMB Seedance Generation_4 to HMB Seedance Generation_5",
    ),
    connectedRoute,
  ),
  false,
  "Generator VIDEO_OUT cables must remain visible while only the managed prompt cable is hidden.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(exactEdgeId, "Edge from HMBAgentLibrary_4 to Another Generator"),
    connectedRoute,
  ),
  false,
  "DOM format or endpoint disagreement must fail visible.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(edge(exactEdgeId, ""), only),
  false,
  "Only mode never hides or lights a prompt edge.",
);
const replacementRoute = {
  ...connectedRoute,
  source_node_name: "HMBAgentLibrary_4",
  previous_source_node_name: "HMBAgentLibrary_3",
};
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_3-output-HMB Seedance Generation_4-prompt-1699999999999",
      "Edge from HMBAgentLibrary_3 to HMB Seedance Generation_4",
    ),
    replacementRoute,
  ),
  true,
  "The old exact cable stays hidden until Shot replacement is committed.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(exactEdgeId, "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4"),
    replacementRoute,
  ),
  true,
  "The next exact cable is pre-armed before retained mode creates it.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4_temp-output-HMB Seedance Generation_4-prompt-1700000000001",
      "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4",
    ),
    {
      ...replacementRoute,
      source_node_name: "HMBAgentLibrary_4_temp",
      previous_source_node_name: "HMBAgentLibrary_4",
    },
  ),
  true,
  "Reset Node may retain the temporary name in the edge id after its aria label uses the final name.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "ForeignAgent-output-HMB Seedance Generation_4-prompt-1700000000002",
      "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4",
    ),
    replacementRoute,
  ),
  false,
  "A mixed reset alias must still reject an unproven source endpoint.",
);
const fullResetRoute = {
  ...connectedRoute,
  source_node_name: "HMBAgentLibrary_4_temp",
  previous_source_node_name: "HMBAgentLibrary_4",
  target_node_name: "HMB Seedance Generation_4_temp",
  previous_target_node_name: "HMB Seedance Generation_4",
};
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4_temp-output-HMB Seedance Generation_4_temp-prompt-1700000000003",
      "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4",
    ),
    fullResetRoute,
  ),
  true,
  "Source and target Reset aliases may transition independently between edge id and aria label.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4-output-HMB Seedance Generation_4_temp-prompt-1700000000004",
      "Edge from HMBAgentLibrary_4_temp to HMB Seedance Generation_4",
    ),
    fullResetRoute,
  ),
  true,
  "Every proven source/target alias combination remains hidden during Reset.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4_temp-output-Foreign Generator-prompt-1700000000005",
      "Edge from HMBAgentLibrary_4 to HMB Seedance Generation_4",
    ),
    fullResetRoute,
  ),
  false,
  "An unproven target endpoint in the edge id must remain visible.",
);
assert.equal(
  widget.hmbSeedanceRemotePromptEdgeMatches(
    edge(
      "HMBAgentLibrary_4_temp-output-HMB Seedance Generation_4_temp-prompt-1700000000006",
      "Edge from HMBAgentLibrary_4 to Foreign Generator",
    ),
    fullResetRoute,
  ),
  false,
  "An unproven target endpoint in the aria label must remain visible.",
);

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
assert.match(widgetSource, /data-hmb-seedance-prompt-edge/);
assert.match(
  widgetSource,
  /attributes:\s*true,[\s\S]*attributeFilter:\s*\["data-id", "aria-label"\]/,
  "Reset Node endpoint renames must trigger an exact edge rescan.",
);
assert.doesNotMatch(
  widgetSource,
  /attributeFilter:\s*\[[^\]]*data-hmb-seedance-prompt-edge/,
  "The observer must not watch its own hiding marker.",
);
assert.doesNotMatch(
  widgetSource,
  /next\.remote_prompt_route\s*=/,
  "Optimistic Shot changes must keep the old cable hidden until retained mode mutates it.",
);
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
