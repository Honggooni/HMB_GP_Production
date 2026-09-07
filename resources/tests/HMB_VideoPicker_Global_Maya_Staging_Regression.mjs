import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shotA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const shotB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const asset = (uid, path, camera) => ({ video_uid: uid, video_path: path, camera, width: 320, height: 180, source_fps: 12, frame_metadata: { fps: 12, start_frame: 1, end_frame: 12, frame_count: 12 }, markers: [{ maya_uuid: "old-root", full_dag_path: "|OldSceneRoot", color: "Red" }] });
const ready = {
  runtime_instance_id: "staging-test", language: "en", status: "READY", scene_stage: "OUTLINER_READY",
  shot_publisher_instance_uuid: "11111111-1111-4111-8111-111111111111", channel_uuid: "22222222-2222-4222-8222-222222222222",
  shot_uuid: shotA, shot_number: 1, shot_name: "Shot 1",
  shot_selections: [{ shot_uuid: shotA, number: 1, name: "Shot 1" }, { shot_uuid: shotB, number: 2, name: "Shot 2" }],
  active_picker_shot_uuid: shotA,
  picker_shots: [
    { workspace_uuid: shotA, bound_shot_uuid: shotA, number: 1, video_asset_uids: ["old-a"], selected_video_uids: ["old-a"], preview_video_uid: "old-a", preview_frame: 5 },
    { workspace_uuid: shotB, bound_shot_uuid: shotB, number: 2, video_asset_uids: ["old-b"], selected_video_uids: ["old-b"], preview_video_uid: "old-b", preview_frame: 9 },
  ],
  videos: [asset("old-a", "C:/render/A.mp4", "|oldCamA"), asset("old-b", "C:/render/B.mp4", "|oldCamB")],
  preview_video_uid: "old-a", selected_video_uid: "old-a", preview_frame: 5,
  maya_available: true, maya_executable: "C:/Maya/bin/mayabatch.exe", native_read_ready: true,
  scene_path: "C:/maya/current.ma", scene_request_path: "C:/maya/current.ma", scene_draft_path: "C:/maya/current.ma",
  native_metadata: { scene_path: "C:/maya/current.ma", marker: "READ result" },
  selected_camera: "|currentCamera", cameras: [{ full_path: "|currentCamera" }],
  outliner_nodes: [{ full_path: "|CurrentRoot", maya_uuid: "current-root", name: "CurrentRoot" }],
  selected_outliner_path: "|CurrentRoot", selected_outliner_uuid: "current-root", selected_color: "Green",
  slot_assignments: [{ video_slot: 1, bindings: [{ full_dag_path: "|CurrentRoot", maya_uuid: "current-root", color: "Green" }] }],
  slot_visibility: [{ video_slot: 1, hidden_paths: ["|CurrentHidden"] }],
  start_frame: 1001, end_frame: 1048, current_frame: 1024, source_fps: 24, output_fps: 24, output_width: 1280, output_height: 720,
  original_enabled: true, mask_enabled: true, depth_enabled: false, motion_guide_enabled: false,
};

let navigated = picker.hmbSwitchLocalPickerShot(ready, shotB);
for (const key of ["scene_path", "scene_request_path", "scene_draft_path", "native_metadata", "native_read_ready", "selected_camera", "cameras", "outliner_nodes", "start_frame", "end_frame", "current_frame", "source_fps", "output_fps", "output_width", "output_height", "original_enabled", "mask_enabled", "depth_enabled", "motion_guide_enabled"]) {
  assert.deepEqual(navigated[key], ready[key], `${key} is shared Maya staging, not selected media metadata.`);
}
assert.equal(navigated.active_picker_shot_uuid, shotB);
assert.equal(navigated.preview_video_uid, "old-b");
assert.equal(navigated.preview_frame, 9);
assert.equal(navigated.slot_assignments.length, 1);
assert.equal(navigated.slot_assignments[0].bindings[0].maya_uuid, "current-root");
assert.deepEqual(navigated.slot_visibility, ready.slot_visibility);
assert.equal(picker.pickerButtonAvailability(navigated).playblastEnabled, true, "READ once allows generation to a different Shot.");
assert.ok(navigated.picker_shots.every((row) => !Object.hasOwn(row, "authoring_context") && !Object.hasOwn(row, "scene_draft_path") && !Object.hasOwn(row, "current_frame")));

// Reading a different source replaces the single input. Returning to A cannot
// resurrect A's previous scene or infer old color bindings from A's media.
navigated = { ...navigated, scene_path: "C:/maya/replacement.mb", scene_request_path: "C:/maya/replacement.mb", scene_draft_path: "C:/maya/replacement.mb", slot_assignments: [{ video_slot: 1, bindings: [] }], selected_color: "", slot_visibility: [{ video_slot: 1, hidden_paths: [] }] };
const replaced = picker.hmbSwitchLocalPickerShot(navigated, shotA);
assert.equal(replaced.scene_path, "C:/maya/replacement.mb");
assert.deepEqual(replaced.slot_assignments, [{ video_slot: 1, bindings: [] }]);
assert.deepEqual(replaced.slot_visibility, [{ video_slot: 1, hidden_paths: [] }]);
assert.equal(replaced.selected_color, "");
assert.equal(replaced.current_frame, 1024);
assert.equal(replaced.preview_frame, 5);
assert.deepEqual(replaced.videos.map((v) => v.video_uid), ["old-a", "old-b"]);
assert.match(picker.hmbPickerGenerateCaption(replaced), /replacement\.mb → Shot 1/);
const mayaLabels = new Map(["[data-picker-maya-frame-start]", "[data-picker-maya-frame-end]", "[data-picker-maya-fps]"].map((selector) => [selector, {}]));
picker.hmbPatchPickerMayaSettingsMetadata({ querySelector(selector) { return mayaLabels.get(selector); } }, replaced);
assert.equal(mayaLabels.get("[data-picker-maya-frame-start]").textContent, "1001");
assert.equal(mayaLabels.get("[data-picker-maya-frame-end]").textContent, "1048");
assert.equal(mayaLabels.get("[data-picker-maya-fps]").textContent, "24", "Maya settings cannot display the older clip's 12 fps.");

// A user draft remains visible while its original staging echo is current.
// A newer authoritative scene invalidates any old runtime-global cache.
const draftContainer = {};
picker.hmbRememberMayaSceneDraft(draftContainer, ready, "C:/maya/draft.ma");
assert.equal(picker.hmbResolveMayaSceneDraftPath(draftContainer, ready), "C:/maya/draft.ma");
assert.equal(picker.hmbResolveMayaSceneDraftPath(draftContainer, { ...ready, active_picker_shot_uuid: shotB }), "C:/maya/draft.ma");
assert.equal(picker.hmbResolveMayaSceneDraftPath(draftContainer, replaced), "C:/maya/replacement.mb");
assert.equal(draftContainer.__hmbMayaSceneDraftPath, undefined);
draftContainer.__hmbMayaSceneDraftPath = "C:/maya/old.ma";
assert.equal(picker.hmbResolveMayaSceneDraftPath(draftContainer, replaced), "C:/maya/replacement.mb");

// Navigation does not end an in-flight operation or change its captured
// destination. Real Maya edits and READ remain locked until it finishes.
const running = { ...ready, status: "RUNNING", operation_kind: "run_video", operation_picker_shot_uuid: shotA, operation_started_at_ms: 100, operation_finished_at_ms: 0, active_process_pid: 123 };
const whileRunning = picker.hmbSwitchLocalPickerShot(running, shotB);
assert.equal(whileRunning.status, "RUNNING");
assert.equal(whileRunning.active_process_pid, 123);
assert.equal(whileRunning.operation_picker_shot_uuid, shotA);
assert.equal(whileRunning.active_picker_shot_uuid, shotB);
const availability = picker.pickerButtonAvailability(whileRunning);
assert.equal(availability.operationBusy, true);
assert.equal(availability.readEnabled, false);
assert.equal(availability.playblastEnabled, false);
assert.match(picker.hmbPickerGenerateCaption(whileRunning), /Processing.*→ Shot 1/);
assert.equal(picker.hmbPickerCommandPayload(whileRunning, { picker_shot_uuid: shotA }).picker_shot_uuid, shotA);
assert.equal(picker.hmbPickerCommandPayload(whileRunning, {}).picker_shot_uuid, shotB);
for (const mode of ["compact", "expanded"]) {
  const markup = picker.hmbRenderVideoPickerShotWorkspace(whileRunning, undefined, true, mode).tabs;
  const navigation = [...markup.matchAll(/<button\b[^>]*data-picker-shot-activate="[^"]+"[^>]*>/g)].map((match) => match[0]);
  assert.equal(navigation.length, 2);
  assert.ok(navigation.every((button) => !/\bdisabled\b/.test(button)), `${mode}: destination navigation stays available during generation.`);
}
for (let index = 0, state = whileRunning; index < 20; index += 1) {
  state = picker.hmbSwitchLocalPickerShot(state, index % 2 ? shotA : shotB);
  assert.equal(state.scene_path, ready.scene_path);
  assert.equal(state.current_frame, 1024);
  assert.equal(state.operation_picker_shot_uuid, shotA);
  assert.equal(state.slot_assignments[0].bindings[0].maya_uuid, "current-root");
}

// A previous Shot's scalar Snapshot projection must not become synthetic
// history or a preview pointer on a destination that has no Snapshot.
const snapshotA = { snapshot_uid: "snapshot-a", video_uid: "old-a", frame: 1024, render_video_slot: 1, path: "C:/snapshots/a.png", url: "/snapshots/a.png", created_at_ms: 1 };
const snapshotB = { snapshot_uid: "snapshot-b", video_uid: "old-b", frame: 1030, render_video_slot: 1, path: "C:/snapshots/b.png", url: "/snapshots/b.png", created_at_ms: 2 };
const withSnapshot = structuredClone(ready);
Object.assign(withSnapshot, { snapshots: [snapshotA], active_snapshot_uid: snapshotA.snapshot_uid, viewport_mode: "snapshot", snapshot_active: true, snapshot_frame: snapshotA.frame, snapshot_video_slot: 1, snapshot_path: snapshotA.path, snapshot_url: snapshotA.url });
Object.assign(withSnapshot.picker_shots[0], { active_snapshot_uid: snapshotA.snapshot_uid, viewport_mode: "snapshot" });
Object.assign(withSnapshot.picker_shots[1], { active_snapshot_uid: "", viewport_mode: "video" });
const blankSnapshotShot = picker.hmbSwitchLocalPickerShot(withSnapshot, shotB);
assert.equal(blankSnapshotShot.active_snapshot_uid, "");
assert.equal(blankSnapshotShot.viewport_mode, "video");
assert.equal(blankSnapshotShot.snapshot_active, false);
assert.equal(blankSnapshotShot.snapshot_path, "");
assert.equal(blankSnapshotShot.snapshot_url, "");
assert.deepEqual(blankSnapshotShot.snapshots.map((item) => item.snapshot_uid), ["snapshot-a"]);
assert.equal(blankSnapshotShot.picker_shots.find((row) => row.workspace_uuid === shotB).active_snapshot_uid, "");
const returnToSnapshotA = picker.hmbSwitchLocalPickerShot(blankSnapshotShot, shotA);
assert.equal(returnToSnapshotA.active_snapshot_uid, "snapshot-a");
assert.equal(returnToSnapshotA.snapshot_path, snapshotA.path);
assert.equal(returnToSnapshotA.viewport_mode, "snapshot");

withSnapshot.snapshots.push(snapshotB);
Object.assign(withSnapshot.picker_shots[1], { active_snapshot_uid: snapshotB.snapshot_uid, viewport_mode: "snapshot" });
const anotherSnapshotShot = picker.hmbSwitchLocalPickerShot(withSnapshot, shotB);
assert.equal(anotherSnapshotShot.active_snapshot_uid, "snapshot-b");
assert.equal(anotherSnapshotShot.snapshot_path, snapshotB.path);
assert.equal(anotherSnapshotShot.snapshot_frame, snapshotB.frame);
assert.equal(anotherSnapshotShot.current_frame, ready.current_frame);
assert.deepEqual(anotherSnapshotShot.snapshots.map((item) => [item.snapshot_uid, item.path]), [["snapshot-a", snapshotA.path], ["snapshot-b", snapshotB.path]]);
const pendingSnapshot = picker.hmbSwitchLocalPickerShot({ ...withSnapshot, operation_kind: "render_snapshot", snapshot_request_frame: 1024 }, shotB);
assert.equal(pendingSnapshot.snapshot_request_frame, 1024, "The captured render frame is independent of the displayed Snapshot frame.");
console.log("PASS: shared Maya staging, Shot preview/destination, scene replacement, stale drafts, in-flight navigation, and isolated Snapshot projection.");
