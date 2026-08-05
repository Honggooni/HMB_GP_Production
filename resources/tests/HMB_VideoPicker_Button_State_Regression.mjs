import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const widgetModule = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);
const buttons = widgetModule.pickerButtonAvailability;

function asset(uid, order, role = "mask", selected = true) {
  const mediaKinds = {
    mask: "maya_color_assignment_mask",
    depth: "maya_depth_playblast",
    motion_guide: "maya_motion_guide",
    manual: "uploaded_video",
  };
  return {
    video_uid: uid,
    source_uid: uid,
    video_path: `C:/shots/catalog/${uid}.mp4`,
    generation_role: role,
    media_kind: mediaKinds[role],
    selected,
    selection_order: selected ? order : 0,
    video_slot: selected ? order : 0,
  };
}

// The asset catalog is unlimited, while only ten stable UIDs can be selected
// for the transient Prompt/Generator order.
const catalogState = {
  mask_authoring_slot: 1,
  selected_video_uid: "asset-01",
  preview_video_uid: "asset-01",
  slot_assignments: [
    { video_slot: 1, bindings: [{ full_dag_path: "|Hero", color: "Red" }] },
    { video_slot: 2, bindings: [{ full_dag_path: "|Prop", color: "Blue" }] },
  ],
  slot_visibility: [
    { video_slot: 1, hidden_paths: ["|Hero|MouthCard"] },
    { video_slot: 2, hidden_paths: ["|Set|Proxy"] },
  ],
  videos: Array.from({ length: 12 }, (_item, index) => (
    asset(`asset-${String(index + 1).padStart(2, "0")}`, index + 1, "manual", index < 10)
  )),
};
catalogState.videos[0] = {
  ...asset("asset-01", 1, "mask"),
  video_role: "maya_color_assignment_mask",
};
catalogState.videos[1] = {
  ...asset("asset-02", 2, "depth"),
  video_role: "maya_depth_companion",
  depth_profile: "hmb_camera_space_depth_v7",
  source_video_uid: "asset-01",
  companion_video_uid: "asset-01",
  source_video_slot: 1,
  companion_of_video_slot: 1,
};
catalogState.videos[2] = {
  ...asset("asset-03", 3, "motion_guide"),
  video_role: "maya_motion_guide_companion",
  motion_guide_profile: "hmb_target_neutral_motion_guide_v5",
  source_video_uid: "asset-01",
  companion_video_uid: "asset-01",
  source_video_slot: 1,
  companion_of_video_slot: 1,
};

assert.deepEqual(
  widgetModule.hmbSelectedVideoAssets(catalogState).map((item) => item.video_uid),
  catalogState.videos.slice(0, 10).map((item) => item.video_uid),
);

const authoringBefore = {
  assignments: structuredClone(catalogState.slot_assignments),
  visibility: structuredClone(catalogState.slot_visibility),
};
const reordered = widgetModule.hmbMoveSelectedVideoAsset(catalogState, "asset-03", 0);
assert.deepEqual(
  widgetModule.hmbSelectedVideoAssets(reordered).map((item) => item.video_uid).slice(0, 3),
  ["asset-03", "asset-01", "asset-02"],
);
const reorderedDepth = reordered.videos.find((item) => item.video_uid === "asset-02");
const reorderedMotion = reordered.videos.find((item) => item.video_uid === "asset-03");
assert.equal(reorderedDepth.source_video_uid, "asset-01");
assert.equal(reorderedMotion.source_video_uid, "asset-01");
assert.equal(reordered.mask_authoring_slot, 1);
assert.deepEqual(reordered.slot_assignments, authoringBefore.assignments);
assert.deepEqual(reordered.slot_visibility, authoringBefore.visibility);

// Full selection rejects an eleventh card. Deselecting one makes exactly one
// position available and preserves every unrelated stable UID.
const fullToggle = widgetModule.hmbToggleVideoAssetSelection(catalogState, "asset-11");
assert.equal(widgetModule.hmbSelectedVideoAssets(fullToggle).length, 10);
assert.equal(fullToggle.videos.find((item) => item.video_uid === "asset-11").selected, false);
const nineSelected = widgetModule.hmbToggleVideoAssetSelection(catalogState, "asset-04");
assert.equal(widgetModule.hmbSelectedVideoAssets(nineSelected).length, 9);
const refilled = widgetModule.hmbToggleVideoAssetSelection(nineSelected, "asset-11");
assert.equal(widgetModule.hmbSelectedVideoAssets(refilled).length, 10);
assert.equal(widgetModule.hmbSelectedVideoAssets(refilled).at(-1).video_uid, "asset-11");

// Preview may target an unselected asset without changing generator order.
const previewed = widgetModule.hmbPreviewVideoAsset(catalogState, "asset-12");
assert.equal(previewed.preview_video_uid, "asset-12");
assert.equal(previewed.selected_video_path, "C:/shots/catalog/asset-12.mp4");
assert.deepEqual(
  widgetModule.hmbSelectedVideoAssets(previewed).map((item) => item.video_uid),
  widgetModule.hmbSelectedVideoAssets(catalogState).map((item) => item.video_uid),
);

// Delete removes only that metadata record. Remaining selected UIDs keep their
// relative order; there is no fixed-slot shift or role rewrite.
const deleted = widgetModule.hmbDeleteVideoAsset(catalogState, "asset-04");
assert.equal(deleted.videos.some((item) => item.video_uid === "asset-04"), false);
assert.deepEqual(
  widgetModule.hmbSelectedVideoAssets(deleted).map((item) => item.video_uid),
  ["asset-01", "asset-02", "asset-03", "asset-05", "asset-06", "asset-07", "asset-08", "asset-09", "asset-10"],
);
assert.equal(deleted.videos.find((item) => item.video_uid === "asset-02").source_video_uid, "asset-01");


// READ/STOP/Generate controls remain governed by the Maya operation state,
// not by catalog slot occupancy.
const selectedPath = "C:/shots/shot01.mb";
const base = {
  status: "READY",
  scene_stage: "LOAD_READY",
  scene_path: "",
  scene_draft_path: selectedPath,
  scene_request_path: selectedPath,
  native_read_ready: false,
  maya_available: true,
  maya_executable: "C:/Program Files/Autodesk/Maya2026/bin/mayabatch.exe",
  operation_kind: "",
  selected_video_slot: 1,
  outliner_nodes: [],
  cameras: [],
  selected_camera: "",
  start_frame: 0,
  end_frame: 0,
  source_fps: 0,
  output_fps: 24,
  output_width: 1920,
  output_height: 1080,
  original_enabled: false,
  mask_enabled: true,
  depth_enabled: false,
  motion_guide_enabled: false,
  snapshots: [],
};

let result = buttons(base, selectedPath);
assert.equal(result.readEnabled, true);
assert.equal(result.playblastEnabled, false);
assert.equal(result.stopEnabled, false);

const readComplete = {
  ...base,
  status: "OUTLINER_READY",
  scene_stage: "OUTLINER_READY",
  scene_path: selectedPath,
  native_read_ready: true,
  outliner_nodes: [{ full_path: "|Actor" }],
  cameras: [{ full_path: "|shotCam", name: "shotCam" }],
  selected_camera: "|shotCam",
  camera: "|shotCam",
  start_frame: 101,
  end_frame: 173,
  source_fps: 24,
};
result = buttons(readComplete, selectedPath);
assert.equal(result.readEnabled, false);
assert.equal(result.playblastEnabled, true);
assert.equal(result.snapshotEnabled, true);
assert.equal(result.originalPreviewToggleEnabled, true);

result = buttons({
  ...readComplete,
  original_enabled: false,
  mask_enabled: false,
  depth_enabled: false,
  motion_guide_enabled: false,
}, selectedPath);
assert.equal(result.playblastEnabled, false);

result = buttons({
  ...readComplete,
  status: "RUNNING",
  operation_kind: "run_video",
  active_process_pid: 5522,
}, selectedPath);
assert.equal(result.readEnabled, false);
assert.equal(result.stopEnabled, true);
assert.equal(result.playblastEnabled, false);
assert.equal(result.snapshotEnabled, false);

result = buttons({
  ...readComplete,
  snapshot_active: true,
  snapshot_video_slot: 1,
  snapshot_data_uri: "data:image/png;base64,AA==",
}, selectedPath);
assert.equal(result.snapshotDeleteEnabled, true);

result = buttons(readComplete, "C:/shots/shot02.ma");
assert.equal(result.readEnabled, true);
assert.equal(result.playblastEnabled, false);
assert.equal(result.originalPreviewToggleEnabled, false);

console.log("HMB VideoPicker UID catalog selection/reorder/delete and button-state regression: PASS");
