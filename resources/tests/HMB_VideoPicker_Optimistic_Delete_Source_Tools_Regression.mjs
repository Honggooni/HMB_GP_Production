import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shots = Array.from({ length: 5 }, (_, index) => `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`);
const assets = ["a", "b", "c", "d", "e"].map((uid, index) => ({ video_uid: uid, source_uid: uid, video_path: `C:/source/${uid === "b" ? "a" : uid}.mp4`, picker_shot_uuid: shots[index], width: index === 0 ? 96 : 192, height: index === 0 ? 64 : 128, selected: index === 3, selection_order: index === 3 ? 1 : 0 }));
const initial = {
  runtime_instance_id: "delete-source-test", state_writer: "python", state_revision: 10,
  active_picker_shot_uuid: shots[3], preview_video_uid: "d", selected_video_uid: "d", preview_frame: 7,
  shot_publisher_instance_uuid: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", channel_uuid: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  shot_selections: shots.map((uuid, index) => ({ shot_uuid: uuid, number: index + 1, name: `Shot ${index + 1}` })),
  picker_shots: shots.map((uuid, index) => ({ workspace_uuid: uuid, bound_shot_uuid: uuid, number: index + 1, name: `Shot ${index + 1}`, video_asset_uids: [assets[index].video_uid], selected_video_uids: [assets[index].video_uid], preview_video_uid: assets[index].video_uid, revision: 0 })),
  videos: assets, scene_path: "C:/maya/current.ma", current_frame: 125, selected_camera: "cameraCurrent", slot_assignments: [{ video_slot: 1, bindings: [{ maya_uuid: "current-root", color: "Red" }] }],
};
let state = picker.hmbUpdatePickerVideoTools(initial, (tools) => {
  tools.active_tool = "concatenate";
  tools.external_sources = [{ source_uid: "external-a", local_path: "C:/source/a.mp4", label: "Independent external source" }];
});
for (const uid of ["a", "b", "a", "external-a", "c"]) state = picker.hmbApplyPickerToolSource(state, uid, "concatenate");
const queue = (value) => value.video_tools_by_shot[shots[3]].concatenate;
assert.deepEqual(queue(state).input_uids, ["a", "b", "a", "external-a", "c"]);
assert.equal(state.active_picker_shot_uuid, shots[3]);
assert.equal(state.picker_shots, initial.picker_shots, "All-Shot source copy never navigates or changes @video selections.");
assert.equal(picker.hmbPickerToolsSourceAssets(state).length, 6);
state = picker.hmbMovePickerToolQueue(state, 4, 0);
assert.deepEqual(queue(state).input_uids, ["c", "a", "b", "a", "external-a"]);
assert.equal(queue(state).inputs[0], "C:/source/c.mp4");
state = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.crop.manual_output_enabled = true; tools.crop.output_path = "C:/manual/crop.mp4"; });
state = picker.hmbApplyPickerToolSource(state, "a", "crop");
assert.equal(state.video_tools_by_shot[shots[3]].crop.custom_width, 96);
state = picker.hmbApplyPickerToolSource(state, "b", "crop");
assert.equal(state.video_tools_by_shot[shots[3]].crop.custom_width, 192);
assert.equal(state.video_tools_by_shot[shots[3]].crop.output_path, "C:/manual/crop.mp4");
assert.equal(state.video_tools_by_shot[shots[3]].crop.manual_output_enabled, true);
state = picker.hmbApplyPickerToolSource(state, "a", "crop");
// Tool-card removal owns only that tool's explicit reference. Repeated concat
// occurrences, the other tool, hidden metadata, and original Picker cards survive.
const toolRemoved = picker.hmbRemovePickerToolInput(state, "concatenate", 1);
assert.deepEqual(queue(toolRemoved).input_uids, ["c", "b", "a", "external-a"]);
assert.equal(toolRemoved.video_tools_by_shot[shots[3]].crop.source_uid, "a");
assert.equal(toolRemoved.videos, state.videos);
assert.equal(toolRemoved.picker_shots, state.picker_shots);
assert.deepEqual(toolRemoved.video_tools_by_shot[shots[3]].external_sources, state.video_tools_by_shot[shots[3]].external_sources);
const cropRemoved = picker.hmbRemovePickerToolInput(toolRemoved, "crop");
assert.deepEqual(queue(cropRemoved), queue(toolRemoved));
assert.equal(cropRemoved.video_tools_by_shot[shots[3]].crop.source_uid, "");
assert.equal(cropRemoved.video_tools_by_shot[shots[3]].crop.input, "");
assert.equal(cropRemoved.video_tools_by_shot[shots[3]].crop.output_path, "C:/manual/crop.mp4");
assert.equal(cropRemoved.video_tools_by_shot[shots[3]].crop.manual_output_enabled, true);
assert.equal(cropRemoved.video_tools_by_shot[shots[3]].crop_by_source.a.custom_width, 96);
assert.equal(cropRemoved.videos, state.videos);
assert.equal(cropRemoved.active_picker_shot_uuid, shots[3]);
const beforeDelete = structuredClone(state), container = {};
const first = picker.hmbBeginOptimisticPickerVideoDeletion(container, state, "a", "delete-a");
assert.equal(first.state.videos.some((asset) => asset.video_uid === "a"), false);
assert.deepEqual(queue(first.state).input_uids, ["c", "b", "external-a"]);
assert.equal(first.state.video_tools_by_shot[shots[3]].crop.source_uid, "");
assert.equal(first.state.preview_video_uid, "d");
assert.equal(first.state.current_frame, 125);
assert.deepEqual(first.state.slot_assignments, initial.slot_assignments);
const second = picker.hmbBeginOptimisticPickerVideoDeletion(container, first.state, "c", "delete-c");
container.__hmbPendingPickerState = second.state;
assert.deepEqual(queue(second.state).input_uids, ["b", "external-a"]);

// An import and old/crossed Python echoes arrive while both commands remain
// unresolved. Keep the new UID and every unrelated source, not either tombstone.
const imported = { ...beforeDelete, videos: [...beforeDelete.videos, { ...assets[0], video_uid: "new-a", source_uid: "new-a" }], picker_shots: beforeDelete.picker_shots.map((row, index) => index ? row : { ...row, video_asset_uids: [...row.video_asset_uids, "new-a"] }) };
const echoed = picker.hmbApplyOptimisticPickerVideoDeletions(container, imported);
assert.deepEqual(picker.hmbApplyOptimisticPickerVideoDeletions(container, JSON.stringify(imported)).videos.map((asset) => asset.video_uid), ["b", "d", "e", "new-a"], "Serialized host props use the same tombstones.");
assert.deepEqual(echoed.videos.map((asset) => asset.video_uid), ["b", "d", "e", "new-a"]);
assert.deepEqual(queue(echoed).input_uids, ["b", "external-a"]);
assert.equal(echoed.preview_video_uid, "d");
const ack = { ...echoed, state_writer: "python", video_delete_results: { "delete-a": { status: "removed" }, "delete-c": { status: "removed" } } };
picker.hmbApplyOptimisticPickerVideoDeletions(container, ack);
let reusedPath = picker.hmbApplyPickerToolSource(ack, "new-a", "concatenate");
reusedPath = picker.hmbApplyPickerToolSource(reusedPath, "new-a", "crop");
reusedPath = picker.hmbApplyOptimisticPickerVideoDeletions(container, reusedPath);
assert.deepEqual(queue(reusedPath).input_uids, ["b", "external-a", "new-a"]);
assert.equal(reusedPath.video_tools_by_shot[shots[3]].crop.source_uid, "new-a");
assert.deepEqual(picker.hmbApplyOptimisticPickerVideoDeletions(container, { ...beforeDelete, runtime_instance_id: "replacement-runtime" }).videos, beforeDelete.videos);
assert.equal(container.__hmbPickerVideoDeletions.size, 0);

const failedContainer = {};
const failed = picker.hmbBeginOptimisticPickerVideoDeletion(failedContainer, beforeDelete, "a", "failed-a");
failedContainer.__hmbPendingPickerState = failed.state;
const rejection = picker.hmbApplyOptimisticPickerVideoDeletions(failedContainer, { ...beforeDelete, video_delete_results: { "failed-a": { status: "rejected", reason: "Busy" } } });
assert.ok(picker.hmbProtectVideoPickerWorkspaceFromStaleEcho(rejection, failed.state).state.videos.some((asset) => asset.video_uid === "a"));
const restoredAckDraft = picker.hmbPreservePickerToolDrafts(rejection, failed.state);
assert.deepEqual(queue(restoredAckDraft).input_uids, queue(beforeDelete).input_uids, "Rejected ACK restores every unchanged cross-Shot draft, not only the source owner.");
assert.equal(restoredAckDraft.video_tools_by_shot[shots[3]].crop.source_uid, "a");
assert.equal(failedContainer.__hmbPickerVideoDeletions.size, 0);
const transportContainer = {};
const transportPending = picker.hmbBeginOptimisticPickerVideoDeletion(transportContainer, beforeDelete, "a", "transport-a");
const transportRestored = picker.hmbRejectOptimisticPickerVideoDeletion(transportContainer, transportPending.state, "transport-a");
assert.deepEqual(queue(transportRestored).input_uids, queue(beforeDelete).input_uids);
assert.equal(transportRestored.video_tools_by_shot[shots[3]].crop.source_uid, "a");
const editedContainer = {};
const editedPending = picker.hmbBeginOptimisticPickerVideoDeletion(editedContainer, beforeDelete, "a", "edited-a");
const newerDraft = picker.hmbUpdatePickerVideoTools(editedPending.state, (tools) => { tools.concatenate.output_path = "C:/manual/newer.mp4"; });
const guardedRestore = picker.hmbRejectOptimisticPickerVideoDeletion(editedContainer, newerDraft, "edited-a");
assert.equal(queue(guardedRestore).output_path, "C:/manual/newer.mp4", "Rollback cannot overwrite a later tool edit.");

const defaults = picker.hmbNormalizePickerVideoTools();
assert.equal(defaults.concatenate.manual_output_enabled, false);
assert.equal(defaults.crop.manual_output_enabled, false);
assert.equal(picker.hmbNormalizePickerVideoTools({ external_sources: Array.from({ length: 100 }, (_, index) => ({ source_uid: `external-${index}`, local_path: `C:/external/${index}.mp4` })) }).external_sources.length, 100);
assert.doesNotMatch(source, /data-picker-tool-action="copy"/);
assert.match(source, /preview: "영상출력", concatenate: "이어붙이기", crop: "영상크롭"/);
console.log("PASS: immediate multi-delete, stale import echoes, exact cross-Shot source UIDs, same-path reimport, manual output drafts, and drag-only tools.");
