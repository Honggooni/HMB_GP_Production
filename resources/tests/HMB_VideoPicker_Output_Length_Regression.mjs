import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const video = (uid, frames, fps) => ({
  video_uid: uid, video_path: `C:/clips/${uid}.mp4`, label: uid,
  decoded_frame_count: frames, source_fps: fps,
  start_frame: 101, end_frame: 100 + frames,
});
const original = {
  language: "ko", active_picker_shot_uuid: a, videos: [video("a", 100, 24), video("b", 100, 24), video("c", 100, 24), video("d", 100, 24)],
  preview_video_uid: "a", selected_video_uid: "a",
  // Unrelated Maya timing must not be used for imported/tool input videos.
  native_read_ready: true, source_fps: 60, start_frame: 1001, end_frame: 2000,
  picker_shots: [
    { workspace_uuid: a, video_asset_uids: ["a", "b"], selected_video_uids: ["a"], preview_video_uid: "a" },
    { workspace_uuid: b, video_asset_uids: ["c", "d"], selected_video_uids: ["c"], preview_video_uid: "c" },
  ],
};
let state = picker.hmbUpdatePickerVideoTools(original, (tools) => {
  tools.active_tool = "concatenate";
  tools.concatenate.inputs = original.videos.map((item) => item.video_path);
  tools.concatenate.input_uids = original.videos.map((item) => item.video_uid);
});
const saved = JSON.stringify(state);
assert.equal(picker.hmbPickerOutputLengthText(state), "≈ 400프레임 / 16.67초");
assert.equal(JSON.stringify(state), saved, "Length calculation must not mutate Shot selection, queue, or source metadata.");
assert.equal(picker.hmbPickerOutputLengthText({ ...state, language: "en" }), "≈ 400 frames / 16.67 s");

const removed = picker.hmbUpdatePickerVideoTools(state, (tools) => {
  tools.concatenate.inputs.pop(); tools.concatenate.input_uids.pop();
});
assert.equal(picker.hmbPickerOutputLength(removed).frames, 300);
assert.equal(picker.hmbPickerOutputLength(picker.hmbMovePickerToolQueue(state, 0, 3)).frames, 400);
assert.equal(picker.hmbPickerOutputLengthText({ ...state, active_picker_shot_uuid: b }), "100프레임 / 4.17초");
const crop = picker.hmbUpdatePickerVideoTools(state, (tools) => {
  tools.active_tool = "crop"; tools.crop.input = original.videos[2].video_path; tools.crop.source_uid = "c";
});
assert.equal(picker.hmbPickerOutputLengthText(crop), "100프레임 / 4.17초", "Crop must not sum the independent concatenate queue.");
assert.equal(picker.hmbPickerOutputLengthText(picker.hmbUpdatePickerVideoTools(crop, (tools) => {
  tools.crop.input = ""; tools.crop.source_uid = "";
})), "0프레임 / 0초");

// auto follows the FIRST edit input, so reordering mixed-FPS sources changes
// the expected frame count, not their combined duration or Loader ordering.
const mixed = { ...state, videos: [video("a", 48, 24), video("b", 90, 30), ...state.videos.slice(2)] };
const pair = picker.hmbUpdatePickerVideoTools(mixed, (tools) => {
  tools.concatenate.inputs = tools.concatenate.inputs.slice(0, 2);
  tools.concatenate.input_uids = tools.concatenate.input_uids.slice(0, 2);
});
assert.equal(picker.hmbPickerOutputLengthText(pair), "≈ 120프레임 / 5초");
assert.equal(picker.hmbPickerOutputLengthText(picker.hmbMovePickerToolQueue(pair, 1, 0)), "≈ 150프레임 / 5초");
const rate60 = picker.hmbUpdatePickerVideoTools(pair, (tools) => { tools.concatenate.output_frame_rate = "60"; });
assert.equal(picker.hmbPickerOutputLengthText(rate60), "≈ 300프레임 / 5초");

// Imports already carry the stock Griptape player's measured FPS/duration.
const imported = { ...pair, videos: [
  { ...video("a", 0, 0), video_metadata: { frame_rate: 24, duration_seconds: 2 } },
  { ...video("b", 0, 0), video_metadata: { frame_rate: 30, duration_seconds: 3 } },
] };
assert.equal(picker.hmbPickerOutputLengthText(imported), "≈ 120프레임 / 5초");
const missing = { ...imported, videos: [imported.videos[0]] };
assert.equal(picker.hmbPickerOutputLengthText(missing), "정보 대기 1/2", "Never publish a partial sum as the full output length.");
assert.equal(picker.hmbPickerOutputLengthText({ ...missing, language: "en" }), "Metadata pending 1/2");
const unknownFps = { ...imported, videos: imported.videos.map((item) => ({ ...item, video_metadata: { duration_seconds: 2 } })) };
assert.equal(picker.hmbPickerOutputLengthText(unknownFps), "≈ —프레임 / 4초", "Do not invent 24 FPS or use the unrelated Maya FPS.");
const fractional = { ...pair, videos: [video("a", 300, 30000 / 1001), video("b", 300, 30000 / 1001)] };
assert.equal(picker.hmbPickerOutputLengthText(fractional), "≈ 600프레임 / 20.02초");
assert.equal(picker.hmbPickerOutputLengthText({ language: "ko", videos: [], native_read_ready: true,
  start_frame: 101, end_frame: 200, source_fps: 24 }), "100프레임 / 4.17초", "Maya output range is inclusive, not end-start.");
assert.equal(picker.hmbPickerOutputLengthText({ language: "ko", videos: [] }), "0프레임 / 0초");
assert.doesNotMatch(source, /id="frame-info-range"/);
assert.match(source, /data-picker-maya-frame-start/);
assert.match(source, /id="frame-info-total"/);
console.log("HMB VideoPicker output-length regression: PASS (cross-Shot sum, order/delete, crop isolation, auto/mixed/fractional FPS, imported metadata, missing metadata, Maya inclusive range, no state mutation)");
