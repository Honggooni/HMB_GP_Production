import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import {readPatchedNativeEditor} from './_hmb_native_editor_fixture.mjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1")), "../..");
const helper = fs.readFileSync(path.join(root, "resources/editor/hmb-color-lut-native-header.js"), "utf8");
const candidate=readPatchedNativeEditor(root,process.env.HMB_NATIVE_DELETE_CANDIDATE);
const callbackStart = candidate.indexOf("bn=(0,S.useCallback)(e=>hmbNativeGuardNodeDeletion(");
const callbackEnd = candidate.indexOf(",xn=(0,S.useCallback)", callbackStart);
assert.ok(callbackStart > 0 && callbackEnd > callbackStart, "Use the exact patched native canvas handler.");
const callback = candidate.slice(callbackStart + 3, callbackEnd);
let checks = 0;
const check = (value, message) => { assert.ok(value, message); checks++; };
const tick = () => new Promise(resolve => setImmediate(resolve));

function harness(names = ["HMB_A", "ordinary"]) {
  const calls = [], notices = [], applied = [], cleared = [];
  const nodes = names.map(id => ({ id, type: "CustomNode", data: { node_type: id === "ordinary" ? "Ordinary" : "FutureTool", metadata: {} } }));
  let response = { can_delete: true, hmb_node_names: names.filter(name => name !== "ordinary") };
  const ctx = vm.createContext({
    console, Map, Set, WeakMap, WeakSet, Promise, Date,
    Xd: {
      request: async (name, args) => { calls.push(["request", name, args]); if (response instanceof Error) throw response; return typeof response === "function" ? response() : response; },
      send: (name, args) => calls.push(["send", name, args]),
    },
    ig: { warning: (title, options) => notices.push([title, options]), error: (title, options) => notices.push([title, options]) },
    vg: error => error.message, S: { useCallback: fn => fn },
    E: { current: null }, w: { current: nodes }, b: nodes,
    N: { showHelperLines: false }, Ct: { current: {} },
    C: changes => { applied.push(changes); for (const change of changes) if (change.type === "remove") {
      const index = nodes.findIndex(node => node.id === change.id); if (index >= 0) nodes.splice(index, 1);
    } },
    Dt: name => cleared.push(name), Et: () => cleared.push("all-parameter-updates"),
    x: fn => { const next = typeof fn === "function" ? fn(nodes) : fn; nodes.splice(0, nodes.length, ...next); },
    O: () => {}, yn: () => {}, on: () => {}, Zt: () => {}, A: () => {}, Ve: () => {}, Ue: () => {},
    ze: () => { throw Error("Unexpected group branch"); }, ut: () => { throw Error("Unexpected dot branch"); },
  });
  vm.runInContext(helper, ctx);
  const handler = vm.runInContext(callback, ctx);
  return { ctx, handler, calls, notices, applied, cleared, nodes, setResponse: next => { response = next; } };
}

for (const reason of ["visible wire", "remote binding"]) {
  const h = harness();
  h.setResponse({ can_delete: false, blocked: { HMB_A: [reason] }, hmb_node_names: ["HMB_A"], message: reason });
  h.handler([{ type: "remove", id: "HMB_A" }, { type: "remove", id: "ordinary" }]);
  await tick();
  check(h.calls.length === 1 && h.calls[0][1] === "HMBCheckNodeDeletionRequest", `${reason}: one whole-batch preflight`);
  assert.deepEqual(Array.from(h.calls[0][2].node_names), ["HMB_A", "ordinary"]); checks++;
  check(h.nodes.length === 2 && !h.applied.length && !h.cleared.length, `${reason}: all-or-none keeps UI and pending edits`);
  check(h.notices.length === 1 && h.notices[0][1].description === reason, `${reason}: engine reason is visible`);
}

{
  const h = harness();
  h.handler([{ type: "remove", id: "HMB_A" }]); await tick();
  check(h.calls.some(call => call[0] === "send" && call[1] === "DeleteNodeRequest"), "Allowed HMB issues the original engine deletion");
  check(h.nodes.some(node => node.id === "HMB_A"), "HMB UI remains until engine success");
  check(!h.cleared.length, "No output/edit cache is discarded before success");
  check(h.applied.every(changes => changes.every(change => change.type !== "remove")), "Controlled UI never optimistically removes HMB");
  const start = candidate.indexOf("o=m(`DeleteNodeResultFailure`,(e,t)=>");
  const end = candidate.indexOf(",s=m(`DeleteConnectionResultSuccess`", start);
  check(start > 0 && end > start, "Exact original failure listener remains registered");
  h.ctx.m = (_event, listener) => listener;
  const failure = vm.runInContext(candidate.slice(start + 2, end), h.ctx);
  failure({ message: "connection changed before deletion" }, { node_name: "HMB_A" });
  check(h.nodes.length === 2 && !h.cleared.length, "Late SDK rejection leaves the existing node/results intact");
  const successStart = candidate.indexOf("a=m(`DeleteNodeResultSuccess`,");
  const successEnd = candidate.indexOf(",o=m(`DeleteNodeResultFailure`", successStart);
  const success = vm.runInContext(candidate.slice(successStart + 2, successEnd), h.ctx);
  success({ node_name: "HMB_A" }, { node_name: "HMB_A" });
  check(h.nodes.length === 1 && h.nodes[0].id === "ordinary", "Engine success finalizes node removal");
  check(h.cleared.includes("HMB_A"), "Cache cleanup occurs after success");
}
{
  const h = harness(); h.setResponse({ can_delete: true, hmb_node_names: [] });
  h.handler([{ type: "remove", id: "ordinary" }]); await tick();
  check(!h.nodes.some(node => node.id === "ordinary"), "Standard-only deletion retains native optimistic behavior after preflight");
  check(h.cleared.includes("ordinary"), "Standard-only native cleanup remains");
}
{
  const h = harness(["not-an-HMB-type-prefix"]);
  h.setResponse({ can_delete: true, hmb_node_names: ["not-an-HMB-type-prefix"] });
  h.handler([{ type: "remove", id: "not-an-HMB-type-prefix" }]); await tick();
  check(h.nodes.length === 1, "Engine library identity protects future HMB tool names");
}
for (const result of [new Error("timeout"), null, { can_delete: "true" }]) {
  const h = harness(); h.setResponse(result);
  h.handler([{ type: "remove", id: "HMB_A" }]); await tick();
  check(h.nodes.length === 2 && h.calls.length === 1, "Transport or malformed acknowledgement fails closed");
  check(h.notices.length === 1, "Failed verification displays an explanation");
}
{
  const h = harness(); let resolve;
  h.setResponse(() => new Promise(done => { resolve = done; }));
  h.handler([{ type: "remove", id: "HMB_A" }]);
  h.handler([{ type: "remove", id: "HMB_A" }]); await tick();
  check(h.calls.length === 1, "Repeated Delete cannot create duplicate pending requests");
  vm.runInContext("hmbNativeStudioResetCollapseIntents()", h.ctx);
  resolve({ can_delete: true, hmb_node_names: ["HMB_A"] }); await tick();
  check(h.calls.length === 1 && h.nodes.length === 2, "An old flow acknowledgement cannot delete a new workflow");
}
{
  const h = harness(); let resolve;
  h.setResponse(() => new Promise(done => { resolve = done; }));
  h.handler([{ type: "remove", id: "HMB_A" }]); await tick();
  const prefix = "se=m(`ClearAllObjectStateResultSuccess`,";
  const start = candidate.indexOf(prefix), end = candidate.indexOf(");return()=>{t(),r(),i(),a()", start);
  check(start > 0 && end > start, "Exact native ClearAll success listener remains registered");
  for (const name of ["lt", "mt", "ke", "je", "Ne", "Fe"]) h.ctx[name] = () => {};
  h.ctx.m = (_event, listener) => listener;
  const clear = vm.runInContext(candidate.slice(start + 3, end + 1), h.ctx);
  clear(); h.nodes.push({ id: "HMB_A", type: "CustomNode", data: {} });
  resolve({ can_delete: true, hmb_node_names: ["HMB_A"] }); await tick();
  check(h.calls.length === 1 && h.nodes.length === 1, "ClearAll invalidates an old check before a replacement graph is constructed");
}
{
  const h = harness(); h.setResponse({ can_delete: false, message: "connected" });
  h.handler([{ type: "position", id: "ordinary", position: { x: 1, y: 2 } }, { type: "remove", id: "HMB_A" }]);
  check(h.applied.length === 1 && h.applied[0][0].type === "position", "Non-destructive changes are not delayed by deletion checks");
  await tick(); check(h.nodes.length === 2, "Denied removal is not replayed after non-destructive updates");
}
assert.match(candidate, /uUt=\(\)=>Xd\.request\(`HMBPrepareWorkflowTransitionRequest`,\{\}\)/); checks++;
assert.match(candidate, /let r=e\.filter\(e=>e\.selected\);return r\.length>0\?\{nodes:r,edges:\[\]\}/); checks++;
assert.match(candidate, /i===`failure`&&\(o===`PermissionDeniedResult`\?GGi\(t,r\):Whe\(\{result:t,request:r\}\)\)/); checks++;
{
  const attributes = new Map(), cleanups = [];
  const ctx = vm.createContext({ console, Map, Set, WeakMap, WeakSet,
    document: { documentElement: {
      setAttribute: (key, value) => attributes.set(key, value),
      getAttribute: key => attributes.get(key), removeAttribute: key => attributes.delete(key),
    } }, S: { useLayoutEffect: setup => cleanups.push(setup()) },
  });
  vm.runInContext(helper, ctx);
  vm.runInContext("hmbUseNativeDeletionGuardHost();hmbUseNativeDeletionGuardHost()", ctx);
  check(attributes.get("data-hmb-native-deletion-guard") === "engine-preflight", "Patched native host exposes the public deletion contract");
  cleanups[0](); check(attributes.has("data-hmb-native-deletion-guard"), "One mounted owner cannot remove another host's marker");
  cleanups[1](); check(!attributes.has("data-hmb-native-deletion-guard"), "The marker is removed with its final native owner");
}
for (const name of ["HMBAgentLibraryWidget.js", "HMBFinishLookLibraryWidget.js", "HMBImageAssetLibraryWidget.js",
  "HMBPromptLibraryScopedBindingWidget.js", "HMBSeedanceGenerationWidget.js", "HMBVideoPickerLibraryWidget_v032.js"]) {
  const source = fs.readFileSync(path.join(root, "widgets", name), "utf8");
  const start = source.indexOf("export function hmbGuardSelectedNodeKeyboardDelete(container, event) {");
  const end = source.indexOf("\n}", start) + 2;
  check(start >= 0 && end > start, `${name}: exact keyboard guard is present`);
  const selected = { classList: { contains: () => true } };
  const scope = { hmbAgentDeleteEditingTarget: () => false, hmbAgentNodeIsSelected: () => true, hmbAgentNodeRoot: () => selected,
    hmbEditingTarget: () => false, hmbNodeSelected: () => true, hmbNodeRoot: () => selected,
    hmbImageAssetDeleteEditingTarget: () => false, isSelectedNodeRoot: () => true, findNodeRoot: () => selected,
    hmbPromptDeleteEditingTarget: () => false, hmbPromptNodeIsSelected: () => true, hmbFindSafeReactFlowNode: () => selected,
    hmbSeedanceNodeSelected: () => true, hmbSeedanceNodeRoot: () => selected,
    hmbPickerDeleteEditingTarget: () => false, hmbPickerNodeIsSelected: () => true, findReactFlowNode: () => selected, videoPickerNodeRoot: () => selected };
  const guard = vm.runInNewContext(`(${source.slice(start + "export ".length, end)})`, scope);
  let stops = 0;
  const event = { key: "Delete", target: { closest: () => null }, preventDefault: () => stops++, stopPropagation: () => stops++, stopImmediatePropagation: () => stops++ };
  check(guard({}, event) === true && stops === 3, `${name}: older hosts retain their existing selected-node guard`);
  const container = { ownerDocument: { documentElement: { getAttribute: () => "engine-preflight" } } };
  stops = 0;
  check(guard(container, event) === false && stops === 0, `${name}: connected/native deletion policy handles the shortcut on the patched host`);
  check(guard(container, { ...event, target: { closest: () => ({ tagName: "INPUT" }) } }) === false && stops === 0,
    `${name}: text editing is never prevented by the node deletion gate`);
}
console.log(`HMB native connected-deletion guard regression: PASS (${checks} checks)`);
