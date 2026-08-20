import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";


const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
globalThis.document = globalThis.document || { body: {}, documentElement: {} };

async function loadWidget(relativePath) {
  const source = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
  const url = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
  return import(url);
}

function nodeRoot(selected = true) {
  return {
    className: "react-flow__node",
    parentElement: null,
    classList: { contains: (name) => selected && name === "selected" },
    getAttribute: () => null,
    querySelector: () => null,
  };
}

function eventTarget({ editable = false, protectedWidget = false } = {}) {
  return {
    closest(selector) {
      if (selector.includes("data-hmb-node-delete-protected")) return protectedWidget ? {} : null;
      if (selector.includes("input,textarea,select")) return editable ? {} : null;
      return null;
    },
  };
}

function keyboardEvent(key, target = eventTarget()) {
  const calls = { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 };
  return {
    calls,
    event: {
      key,
      target,
      preventDefault: () => { calls.preventDefault += 1; },
      stopPropagation: () => { calls.stopPropagation += 1; },
      stopImmediatePropagation: () => { calls.stopImmediatePropagation += 1; },
    },
  };
}

for (const relativePath of [
  "widgets/HMBAgentLibraryWidget.js",
  "widgets/HMBImageAssetLibraryWidget.js",
  "widgets/HMBPromptLibraryScopedBindingWidget.js",
  "widgets/HMBVideoPickerLibraryWidget_v032.js",
  "widgets/HMBSeedanceGenerationWidget.js",
]) {
  const module = await loadWidget(relativePath);
  const guard = module.hmbGuardSelectedNodeKeyboardDelete;
  assert.equal(typeof guard, "function", `${relativePath} must export its delete guard`);

  for (const key of ["Backspace", "Delete"]) {
    const sample = keyboardEvent(key);
    assert.equal(guard({ parentElement: nodeRoot(true) }, sample.event), true, `${relativePath}: ${key}`);
    assert.deepEqual(sample.calls, {
      preventDefault: 1,
      stopPropagation: 1,
      stopImmediatePropagation: 1,
    });
  }

  const unselected = keyboardEvent("Delete");
  assert.equal(guard({ parentElement: nodeRoot(false) }, unselected.event), false);
  assert.deepEqual(unselected.calls, { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 });

  const editing = keyboardEvent("Backspace", eventTarget({ editable: true }));
  assert.equal(guard({ parentElement: nodeRoot(true) }, editing.event), false);
  assert.deepEqual(editing.calls, { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 });

  const protectedInterior = keyboardEvent("Delete", eventTarget({ protectedWidget: true }));
  assert.equal(guard({ parentElement: nodeRoot(true) }, protectedInterior.event), false);
  assert.deepEqual(protectedInterior.calls, { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 });

  const ordinaryKey = keyboardEvent("Enter");
  assert.equal(guard({ parentElement: nodeRoot(true) }, ordinaryKey.event), false);
  assert.deepEqual(ordinaryKey.calls, { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 });

  const toolbarClick = keyboardEvent(undefined);
  assert.equal(guard({ parentElement: nodeRoot(true) }, toolbarClick.event), false);
  assert.deepEqual(toolbarClick.calls, { preventDefault: 0, stopPropagation: 0, stopImmediatePropagation: 0 });
}

console.log("HMB five-library keyboard delete guard regression: PASS");
