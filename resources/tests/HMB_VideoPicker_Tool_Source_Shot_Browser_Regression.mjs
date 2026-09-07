import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shots = Array.from({ length: 5 }, (_, i) => `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`);
const assets = shots.map((workspace, i) => ({ video_uid: `source-${i + 1}`, source_uid: `source-${i + 1}`,
  video_path: `C:/source/${i + 1}.mp4`, picker_shot_uuid: workspace, width: 96, height: 64 }));
const initial = { runtime_instance_id: "source-browse-runtime", state_writer: "python", state_revision: 12,
  active_picker_shot_uuid: shots[3], videos: assets, preview_video_uid: "source-4", selected_video_uid: "source-4",
  shot_publisher_instance_uuid: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", channel_uuid: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  shot_selections: shots.map((uuid, i) => ({ shot_uuid: uuid, number: i + 1, name: `Shot ${i + 1}` })),
  picker_shots: shots.map((uuid, i) => ({ workspace_uuid: uuid, bound_shot_uuid: uuid, number: i + 1, name: `Shot ${i + 1}`,
    video_asset_uids: [assets[i].video_uid], selected_video_uids: [assets[i].video_uid], preview_video_uid: assets[i].video_uid, revision: 0 })) };
let state = picker.hmbSwitchLocalPickerShot(initial, shots[3]);
state = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.active_tool = "concatenate"; });
const container = { __hmbVideoPickerExpanded: true };
const before = JSON.stringify(state);
for (let i = 0; i < shots.length; i++) {
  const displayed = picker.hmbPickerToolsBrowseSourceShot(container, state, shots[i]);
  assert.equal(displayed.active_picker_shot_uuid, shots[i]);
  assert.equal(state.active_picker_shot_uuid, shots[3]);
  assert.equal(JSON.stringify(state), before, "Browsing source tabs published/mutated the editing workspace");
  assert.deepEqual(picker.hmbSelectedVideoAssets(displayed).map((a) => a.video_uid), [assets[i].video_uid]);
}
for (const i of [0, 1, 2]) {
  picker.hmbPickerToolsBrowseSourceShot(container, state, shots[i]);
  state = picker.hmbApplyPickerToolSource(state, assets[i].video_uid, "concatenate");
}
assert.equal(state.active_picker_shot_uuid, shots[3]);
assert.deepEqual(state.video_tools_by_shot[shots[3]].concatenate.input_uids, ["source-1", "source-2", "source-3"]);
assert.equal(picker.hmbPickerConcatenateResultShot(state).workspace_uuid, shots[0]);
const reordered = picker.hmbMovePickerToolQueue(state, 1, 0);
assert.equal(picker.hmbPickerConcatenateResultShot(reordered).workspace_uuid, shots[1]);
assert.deepEqual(state.video_tools_by_shot[shots[2]]?.concatenate?.inputs || [], []);
const queue = structuredClone(state.video_tools_by_shot[shots[3]].concatenate);
const selected = picker.hmbTogglePickerSourceVideoSelection(state, shots[0], "source-1");
assert.equal(selected.active_picker_shot_uuid, shots[3]);
assert.deepEqual(selected.picker_shots[0].selected_video_uids, []);
assert.deepEqual(selected.picker_shots[3].selected_video_uids, ["source-4"]);
assert.deepEqual(selected.video_tools_by_shot[shots[3]].concatenate, queue);
assert.equal(selected.preview_video_uid, "source-4");
state = picker.hmbUpdatePickerVideoTools(selected, (tools) => { tools.active_tool = "crop"; });
picker.hmbPickerToolsBrowseSourceShot(container, state, shots[1]);
state = picker.hmbApplyPickerToolSource(state, "source-2", "crop");
picker.hmbPickerToolsBrowseSourceShot(container, state, shots[4]);
state = picker.hmbApplyPickerToolSource(state, "source-5", "crop");
assert.equal(state.video_tools_by_shot[shots[3]].crop.source_uid, "source-5");
assert.deepEqual(state.video_tools_by_shot[shots[3]].concatenate, queue);
assert.equal(state.active_picker_shot_uuid, shots[3]);
const inputBeforePreview = structuredClone(state.video_tools_by_shot[shots[3]]);
container.__hmbPickerToolsPreview = { picker_shot_uuid: shots[3], active_tool: "crop",
  source_preview: true, uid: "tool-source:source-1", asset: assets[0], path: assets[0].video_path };
assert.equal(picker.hmbVideoPickerPreviewDescriptor(state, container).uid, "tool-source:source-1");
assert.deepEqual(state.video_tools_by_shot[shots[3]], inputBeforePreview,
  "Previewing a source card must not assign it as the crop input");
delete container.__hmbPickerToolsPreview;
// A deleted browsed source Shot resets only the local browse cursor.
const withoutFifth = { ...state, picker_shots: state.picker_shots.slice(0, 4),
  shot_selections: state.shot_selections.slice(0, 4), videos: state.videos.slice(0, 4) };
assert.equal(picker.hmbPickerToolsSourceDisplayState(container, withoutFifth).active_picker_shot_uuid, shots[3]);
picker.hmbPickerToolsBrowseSourceShot(container, state, shots[0]);
const freshRuntime = { ...state, runtime_instance_id: "new-runtime" };
assert.equal(picker.hmbPickerToolsSourceDisplayState(container, freshRuntime).active_picker_shot_uuid, shots[3]);
// Video Output / compact mode keep their normal work-Shot navigation contract.
const output = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.active_tool = "preview"; });
assert.equal(picker.hmbPickerToolsSourceDisplayState(container, output).active_picker_shot_uuid, shots[3]);
assert.equal(container.__hmbPickerToolsSourceBrowser, undefined);
assert.equal(picker.hmbSwitchLocalPickerShot(output, shots[1]).active_picker_shot_uuid, shots[1]);
container.__hmbVideoPickerExpanded = false;
assert.equal(picker.hmbPickerToolsSourceDisplayState(container, state).active_picker_shot_uuid, shots[3]);
assert.equal(container.__hmbPickerToolsSourceBrowser, undefined);

assert.ok(source.includes('preserve_edit_workspace: sourceBrowsing'));
assert.ok(source.includes('preserve_edit_workspace: preserveEditWorkspace'));
console.log("Picker source Shot browser: five source tabs, fixed edit owner, cross-Shot concat/crop, source selection isolation, runtime/deletion/mode reset and explicit Load routing passed.");
