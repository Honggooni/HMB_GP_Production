import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const sourcePath = path.join(root, "widgets", "HMBAgentLibraryWidget.js");
const source = fs.readFileSync(sourcePath, "utf8");
const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const widget = await import(moduleUrl);

for (const phase of ["authorizing", "preparing", "running"]) {
  const state = widget.hmbAgentState({ value: { execution_phase: phase } });
  assert.equal(state.execution_phase, phase);
}
assert.equal(
  widget.hmbAgentState({ value: { execution_phase: "private-policy-text" } }).execution_phase,
  "",
  "only bounded public phase codes may reach the Agent widget",
);
assert.match(source, /정책 확인 중…/u);
assert.match(source, /프롬프트 준비 중…/u);
assert.match(source, /Agent 실행 중…/u);
assert.match(source, /select\.disabled = Boolean\(state\.execution_phase\)/u);
assert.match(source, /data-execution-phase=/u);

console.log("HMB Agent execution phase UI regression: PASS");
