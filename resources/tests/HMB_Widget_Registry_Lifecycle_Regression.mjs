import assert from "node:assert/strict";
import fs from "node:fs";

async function importWidget(relativePath) {
  const source = fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

function classList(...names) {
  const values = new Set(names);
  return {
    contains(name) { return values.has(name); },
    add(...items) { items.forEach((item) => values.add(item)); },
    remove(...items) { items.forEach((item) => values.delete(item)); },
  };
}

function makeShell(nodeId, runtimeId = "runtime-a") {
  const attributes = new Map([["data-id", nodeId]]);
  const shell = {
    className: "react-flow__node",
    classList: classList("react-flow__node"),
    parentElement: null,
    getAttribute(name) { return attributes.get(name) || ""; },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    hasAttribute(name) { return attributes.has(name); },
  };
  const container = {
    parentElement: shell,
    __hmbVideoPickerRuntimeInstanceId: runtimeId,
    closest(selector) { return selector === ".react-flow__node" ? shell : null; },
  };
  return { shell, container };
}

const imageAsset = await importWidget("../../widgets/HMBImageAssetLibraryWidget.js");
const picker = await importWidget("../../widgets/HMBVideoPickerLibraryWidget_v032.js");

for (const exportedName of [
  "hmbAttachImageAssetRegistryContainer",
  "hmbDetachImageAssetRegistryContainer",
  "hmbImageAssetCompactRegistryHas",
  "hmbImageAssetRecordedNodeIdentity",
  "hmbRememberImageAssetCompactRegistry",
]) {
  assert.equal(typeof imageAsset[exportedName], "function", `${exportedName} must remain exported.`);
}

// ImageAsset records the mount identity before React Flow mutates data-id.
// Only the exact `_temp` -> final transition carries compact state.
const temporaryAsset = makeShell("HMBImageAssetLibrary_temp");
assert.equal(
  imageAsset.hmbAttachImageAssetRegistryContainer(temporaryAsset.container),
  temporaryAsset.shell,
  "A recyclable temporary id must use its exact node shell as registry identity.",
);
temporaryAsset.container.__hmbImageAssetCompact = true;
assert.equal(
  imageAsset.hmbRememberImageAssetCompactRegistry(temporaryAsset.container, true),
  true,
);
const concurrentTemporaryAsset = makeShell("HMBImageAssetLibrary_temp");
imageAsset.hmbAttachImageAssetRegistryContainer(concurrentTemporaryAsset.container);
assert.equal(
  imageAsset.hmbImageAssetCompactRegistryHas(concurrentTemporaryAsset.container),
  false,
  "A recyclable temporary label cannot share state before final-id migration is observed.",
);
temporaryAsset.shell.setAttribute("data-id", "HMBImageAssetLibrary");
assert.equal(
  imageAsset.hmbImageAssetRecordedNodeIdentity(temporaryAsset.container),
  "id:HMBImageAssetLibrary",
);
assert.equal(imageAsset.hmbImageAssetCompactRegistryHas(temporaryAsset.container), true);

const reusedTemporaryAsset = makeShell("HMBImageAssetLibrary_temp");
imageAsset.hmbAttachImageAssetRegistryContainer(reusedTemporaryAsset.container);
assert.equal(
  imageAsset.hmbImageAssetCompactRegistryHas(reusedTemporaryAsset.container),
  false,
  "A different node reusing the old temporary id cannot inherit compact state.",
);
assert.equal(imageAsset.hmbDetachImageAssetRegistryContainer(temporaryAsset.container), true);
assert.equal(imageAsset.hmbDetachImageAssetRegistryContainer(temporaryAsset.container), false);
const reusedFinalAsset = makeShell("HMBImageAssetLibrary");
imageAsset.hmbAttachImageAssetRegistryContainer(reusedFinalAsset.container);
assert.equal(
  imageAsset.hmbImageAssetCompactRegistryHas(reusedFinalAsset.container),
  false,
  "Final identity state must be released when its last mounted owner detaches.",
);
imageAsset.hmbDetachImageAssetRegistryContainer(reusedTemporaryAsset.container);
imageAsset.hmbDetachImageAssetRegistryContainer(reusedFinalAsset.container);
imageAsset.hmbDetachImageAssetRegistryContainer(concurrentTemporaryAsset.container);

// Multiple parameter-row mounts for one node share one compact identity. The
// strong mounted Set must release it only after the last compact owner leaves.
const sharedAsset = makeShell("shared-image-asset");
const sharedAssetMirror = {
  ...sharedAsset.container,
  parentElement: sharedAsset.shell,
};
imageAsset.hmbAttachImageAssetRegistryContainer(sharedAsset.container);
imageAsset.hmbAttachImageAssetRegistryContainer(sharedAssetMirror);
sharedAsset.container.__hmbImageAssetCompact = true;
sharedAssetMirror.__hmbImageAssetCompact = true;
imageAsset.hmbRememberImageAssetCompactRegistry(sharedAsset.container, true);
assert.equal(imageAsset.hmbDetachImageAssetRegistryContainer(sharedAsset.container), true);
assert.equal(imageAsset.hmbImageAssetCompactRegistryHas(sharedAssetMirror), true);
assert.equal(imageAsset.hmbDetachImageAssetRegistryContainer(sharedAssetMirror), true);
const sharedAssetReplacement = makeShell("shared-image-asset");
imageAsset.hmbAttachImageAssetRegistryContainer(sharedAssetReplacement.container);
assert.equal(imageAsset.hmbImageAssetCompactRegistryHas(sharedAssetReplacement.container), false);
imageAsset.hmbDetachImageAssetRegistryContainer(sharedAssetReplacement.container);

// VideoPicker keeps same-runtime remount memory while safely migrating the
// temporary node id and deleting the superseded strong key.
const temporaryPicker = makeShell("HMBVideoPickerLibrary_temp", "picker-runtime-a");
picker.hmbRememberVideoPickerViewMode(temporaryPicker.container, true);
picker.hmbRememberVideoPickerExpandedGeometry(temporaryPicker.container, {
  properties: { height: { value: "1337px", priority: "important" } },
  actualHeight: 1337,
  measuredHeight: 1337,
});
const concurrentTemporaryPicker = makeShell(
  "HMBVideoPickerLibrary_temp",
  "picker-runtime-a",
);
assert.equal(
  picker.hmbVideoPickerStoredViewMode(concurrentTemporaryPicker.container),
  null,
  "A recyclable temporary Picker id cannot collide before final-id migration is observed.",
);
temporaryPicker.shell.setAttribute("data-id", "HMBVideoPickerLibrary");
assert.equal(picker.hmbVideoPickerStoredViewMode(temporaryPicker.container), true);
const renamedGeometry = picker.hmbVideoPickerRememberedExpandedGeometry(temporaryPicker.container);
assert.equal(renamedGeometry?.properties?.height?.value, "1337px");
const staleTemporaryPicker = makeShell("HMBVideoPickerLibrary_temp", "picker-runtime-a");
assert.equal(
  picker.hmbVideoPickerStoredViewMode(staleTemporaryPicker.container),
  null,
  "The retired temporary Picker key cannot be inherited by another node.",
);

const sameRuntimeRemount = makeShell("HMBVideoPickerLibrary", "picker-runtime-a");
assert.equal(
  picker.hmbVideoPickerStoredViewMode(sameRuntimeRemount.container),
  true,
  "Same-node, same-runtime remount memory must remain available.",
);
assert.equal(
  picker.hmbVideoPickerRememberedExpandedGeometry(sameRuntimeRemount.container)
    ?.properties?.height?.value,
  "1337px",
);

assert.deepEqual(
  picker.hmbBindVideoPickerRuntimeIdentity(temporaryPicker.container, "picker-runtime-b"),
  { changed: true, hydrationReset: true },
);
const retiredRuntime = makeShell("HMBVideoPickerLibrary", "picker-runtime-a");
assert.equal(
  picker.hmbVideoPickerStoredViewMode(retiredRuntime.container),
  null,
  "Runtime replacement must purge the previous view-mode identity.",
);
assert.equal(
  picker.hmbVideoPickerRememberedExpandedGeometry(retiredRuntime.container),
  null,
  "Runtime replacement must purge the previous expanded geometry identity.",
);
assert.equal(picker.hmbVideoPickerStoredViewMode(temporaryPicker.container), false);

// Strong registries are bounded LRU maps. Churn beyond the limit evicts the
// oldest inactive identity while retaining recently written nodes.
const churn = [];
for (let index = 0; index < picker.HMB_VIDEO_PICKER_STRONG_REGISTRY_LIMIT + 3; index += 1) {
  const instance = makeShell(`bounded-picker-${index}`, `bounded-runtime-${index}`);
  churn.push(instance);
  picker.hmbRememberVideoPickerViewMode(instance.container, index % 2 === 0);
  picker.hmbRememberVideoPickerExpandedGeometry(instance.container, {
    properties: { height: { value: `${1200 + index}px`, priority: "" } },
    actualHeight: 1200 + index,
    measuredHeight: 1200 + index,
  });
}
assert.equal(picker.hmbVideoPickerStoredViewMode(churn[0].container), null);
assert.equal(picker.hmbVideoPickerRememberedExpandedGeometry(churn[0].container), null);
assert.equal(
  picker.hmbVideoPickerStoredViewMode(churn.at(-1).container),
  (churn.length - 1) % 2 === 0,
);
assert.equal(
  picker.hmbVideoPickerRememberedExpandedGeometry(churn.at(-1).container)
    ?.properties?.height?.value,
  `${1200 + churn.length - 1}px`,
);

console.log("HMB widget registry lifecycle regression: PASS");
