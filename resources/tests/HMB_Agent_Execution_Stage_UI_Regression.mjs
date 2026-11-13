import assert from "node:assert/strict";
import fs from "node:fs";
const source = fs.readFileSync(new URL("../../widgets/HMBAgentLibraryWidget.js", import.meta.url), "utf8");
const widget = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
for (const [stage, label] of Object.entries({policy_verify:"정책 검증 중…", policy_bootstrap:"최초 정책 준비 중…",
  native_prepare:"모델 요청 준비 중…", media_prepare:"참고 미디어 준비 중…", inference:"모델 응답 대기 중…", finalize:"결과 정리 중…"})) {
  const state = widget.hmbAgentState({value:{execution_phase:"running", execution_stage:stage, execution_elapsed_seconds:1.25}});
  assert.equal(state.execution_stage, stage);
  assert.equal(widget.hmbAgentProgressLabel(state), label);
  const row = widget.hmbAgentShotRowState({value:{schema:"hmb-agent-shot-row",version:1,
    shot:{channel_uuid:"flow",shot_uuid:"shot",number:1},status:"running",execution_stage:stage}});
  assert.equal(widget.hmbAgentProgressLabel(row), label);
}
const invalid = widget.hmbAgentState({value:{execution_stage:"private-policy-or-path",execution_elapsed_seconds:Infinity}});
assert.equal(invalid.execution_stage, "");
assert.equal(invalid.execution_elapsed_seconds, 0);
assert.equal(widget.hmbAgentProgressLabel({execution_stage:"complete"}, "완료"), "완료");
console.log("HMB Agent execution stage UI regression: PASS");
