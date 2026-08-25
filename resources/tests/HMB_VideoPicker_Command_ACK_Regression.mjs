import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widgetModule = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);

const terminalState = {
  state_writer: "python",
  status: "OUTLINER_READY",
  scene_stage: "OUTLINER_READY",
  scene_path: "C:/show/shot.ma",
  scene_request_path: "C:/show/shot.ma",
  maya_available: true,
  maya_executable: "C:/Autodesk/mayabatch.exe",
  native_read_ready: true,
  active_process_pid: 0,
  operation_kind: "",
  operation_started_at_ms: 100,
  operation_finished_at_ms: 200,
  outliner_nodes: [{ full_path: "|Actor" }],
  cameras: [{ full_path: "|camera1", name: "camera1" }],
  selected_camera: "|camera1",
  start_frame: 101,
  end_frame: 162,
  source_fps: 24,
  output_fps: 24,
  output_width: 1280,
  output_height: 720,
  mask_enabled: true,
};

const staleAvailability = widgetModule.pickerButtonAvailability(
  terminalState,
  terminalState.scene_path,
  true,
  false,
);
assert.equal(staleAvailability.operationBusy, true);
assert.equal(staleAvailability.playblastEnabled, false);
assert.equal(staleAvailability.snapshotEnabled, false);
assert.equal(staleAvailability.originalPreviewToggleEnabled, false);

const readContainer = {
  __hmbReadCommandPending: true,
  __hmbReadActionId: "read-1",
  __hmbReadAckTimer: setTimeout(() => {}, 60_000),
};
const readResult = widgetModule.hmbReconcilePickerCommandAcknowledgements(readContainer, {
  ...terminalState,
  backend_ack_action_id: "read-1",
});
assert.equal(readResult.readReleased, true);
assert.equal(readContainer.__hmbReadCommandPending, false);
assert.equal(readContainer.__hmbReadActionId, "");
assert.equal("__hmbReadAckTimer" in readContainer, false);

const restoredAvailability = widgetModule.pickerButtonAvailability(
  terminalState,
  terminalState.scene_path,
  readContainer.__hmbReadCommandPending,
  false,
);
assert.equal(restoredAvailability.operationBusy, false);
assert.equal(restoredAvailability.playblastEnabled, true);
assert.equal(restoredAvailability.snapshotEnabled, true);
assert.equal(restoredAvailability.originalPreviewToggleEnabled, true);

const staleAckContainer = {
  __hmbReadCommandPending: true,
  __hmbReadActionId: "read-new",
};
assert.equal(widgetModule.hmbReconcilePickerCommandAcknowledgements(staleAckContainer, {
  ...terminalState,
  backend_ack_action_id: "read-old",
}).readReleased, false);
assert.equal(staleAckContainer.__hmbReadCommandPending, true);
assert.equal(widgetModule.hmbReconcilePickerCommandAcknowledgements(staleAckContainer, {
  ...terminalState,
  state_writer: "widget",
  backend_ack_action_id: "read-new",
}).readReleased, false);
assert.equal(staleAckContainer.__hmbReadCommandPending, true);

const operationContainer = {
  __hmbPickerOperationSubmissionPending: true,
  __hmbPickerOperationActionId: "run-1",
  __hmbPickerOperationAction: "run_video",
  __hmbPickerOperationGuardTimer: setTimeout(() => {}, 60_000),
};
const operationResult = widgetModule.hmbReconcilePickerCommandAcknowledgements(operationContainer, {
  ...terminalState,
  status: "RUNNING",
  scene_stage: "PYTHON_COMMAND_RECEIVED",
  operation_kind: "run_video",
  operation_started_at_ms: 300,
  operation_finished_at_ms: 200,
  backend_ack_action_id: "run-1",
});
assert.equal(operationResult.operationSubmissionReleased, true);
assert.equal("__hmbPickerOperationSubmissionPending" in operationContainer, false);
assert.equal("__hmbPickerOperationActionId" in operationContainer, false);
assert.equal("__hmbPickerOperationGuardTimer" in operationContainer, false);
assert.equal(widgetModule.pickerButtonAvailability({
  ...terminalState,
  status: "RUNNING",
  scene_stage: "PYTHON_COMMAND_RECEIVED",
  operation_kind: "run_video",
  operation_started_at_ms: 300,
  operation_finished_at_ms: 200,
}, terminalState.scene_path).operationBusy, true);

const originalContainer = {
  __hmbOriginalCommandPending: true,
  __hmbOriginalActionId: "original-1",
  __hmbOriginalRequestedEnabled: true,
  __hmbOriginalAckTimer: setTimeout(() => {}, 60_000),
};
const originalResult = widgetModule.hmbReconcilePickerCommandAcknowledgements(originalContainer, {
  ...terminalState,
  backend_ack_action_id: "original-1",
});
assert.equal(originalResult.originalReleased, true);
assert.equal(originalContainer.__hmbOriginalCommandPending, false);
assert.equal(originalContainer.__hmbOriginalActionId, "");
assert.equal("__hmbOriginalRequestedEnabled" in originalContainer, false);
assert.equal("__hmbOriginalAckTimer" in originalContainer, false);

const patchMountedStart = widgetSource.indexOf("const patchMountedPicker = (nextProps = {}) => {");
const regionalAck = widgetSource.indexOf("hmbReconcilePickerCommandAcknowledgements(container, nextState);", patchMountedStart);
const regionalLock = widgetSource.indexOf("const immediateMediaLocked = pickerLocalInteractionLocked(nextState);", patchMountedStart);
assert.ok(patchMountedStart >= 0 && regionalAck > patchMountedStart && regionalAck < regionalLock);
assert.match(
  widgetSource,
  /const acknowledgement = hmbReconcilePickerCommandAcknowledgements\(container, latest\);\s*if \(acknowledgement\.readReleased\)/,
);

console.log("HMB VideoPicker command acknowledgement regression: PASS");
