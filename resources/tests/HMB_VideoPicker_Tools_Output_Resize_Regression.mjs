import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url), "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const shot = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", otherShot = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
let state = { runtime_instance_id: "resize", active_picker_shot_uuid: shot, language: "en", videos: [
  { video_uid: "a", video_path: "{inputs}/a.mp4", import_source_path: "D:/source-a/a.mp4" },
  { video_uid: "b", video_path: "{inputs}/b.mp4", import_source_path: "E:/source-b/b.mp4" },
], picker_shots: [{ workspace_uuid: shot, video_asset_uids: ["a", "b"] }] };
state = picker.hmbApplyPickerToolSource(state, "a", "concatenate");
state = picker.hmbApplyPickerToolSource(state, "b", "concatenate");
state = picker.hmbApplyPickerToolSource(state, "b", "crop");
state = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.active_tool = "concatenate"; });
assert.equal(picker.hmbPickerToolOutputDirectory(state, "concatenate"), "D:/source-a");
assert.equal(picker.hmbPickerToolOutputDirectory(state, "crop"), "E:/source-b");
const reordered = picker.hmbMovePickerToolQueue(state, 1, 0);
assert.equal(picker.hmbPickerToolOutputDirectory(reordered, "concatenate"), "E:/source-b");
assert.equal(picker.hmbPickerToolOutputDirectory(reordered, "crop"), "E:/source-b");
const macroState = { ...state, videos: state.videos.map((v) => ({ ...v, import_source_path: "" })), video_tools_default_output_directory: "C:/resolved", video_tools_default_output_context: { picker_shot_uuid: shot, tool: "concatenate", source_uid: "a", reference: "{inputs}/a.mp4" } };
assert.equal(picker.hmbPickerToolOutputDirectory(macroState, "concatenate"), "C:/resolved");
assert.equal(picker.hmbPickerToolOutputDirectory(macroState, "crop"), "");
assert.equal(picker.hmbPickerToolOutputDirectory(picker.hmbMovePickerToolQueue(macroState, 1, 0), "concatenate"), "");
assert.doesNotMatch(source, /Without a Maya scene, enable manual output|Maya 씬 없이 사용하려면 출력 경로 직접/);

class Element {
  constructor(attributes = {}) { this.attributes = { ...attributes }; this.listeners = new Map(); this.hidden = false; this.style = { setProperty: (key, value) => { this.style[key] = value; } }; this.classList = { add() {}, remove() {} }; }
  hasAttribute(key) { return Object.hasOwn(this.attributes, key); }
  getAttribute(key) { return this.attributes[key] ?? null; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  removeAttribute(key) { delete this.attributes[key]; }
  closest(selector) { return selector.includes("data-picker-tools-resize") && this.hasAttribute("data-picker-tools-resize") ? this : null; }
  addEventListener(key, fn) { this.listeners.set(key, [...(this.listeners.get(key) || []), fn]); }
  removeEventListener(key, fn) { this.listeners.set(key, (this.listeners.get(key) || []).filter((item) => item !== fn)); }
  emit(key, extra = {}) { for (const fn of this.listeners.get(key) || []) fn({ target: this, preventDefault() {}, stopImmediatePropagation() {}, ...extra }); }
  querySelector() { return null; }
}

const manual = new Element({ "data-picker-tool-field": "concatenate.manual_output_enabled" }); manual.checked = true;
const destination = new Element({ "data-picker-tool-field": "concatenate.output_path" }); destination.value = "D:/just-typed.mp4";
const unrelated = new Element({ "data-picker-tool-field": "crop.output_path" }); unrelated.value = "E:/do-not-copy.mp4";
const fields = { querySelectorAll: () => [manual, destination, unrelated] };
assert.equal(state.video_tools_by_shot[shot].concatenate.manual_output_enabled, false);
const captured = picker.hmbCapturePickerToolSettings(state, "concatenate", fields);
assert.equal(captured.manual_output_enabled, true, "Checked DOM state wins without change/host echo.");
assert.equal(captured.output_path, "D:/just-typed.mp4", "Latest typed path belongs only to the clicked tool.");
assert.deepEqual(captured.inputs, ["{inputs}/a.mp4", "{inputs}/b.mp4"]);
destination.disabled = true; manual.checked = false;
assert.equal(picker.hmbCapturePickerToolSettings(state, "concatenate", fields).output_path, "");

const root = new Element(); root.__hmbVideoPickerExpanded = true;
const handle = new Element({ "data-picker-tools-resize": "" }), panel = new Element(), viewport = new Element(), stage = new Element();
panel.offsetHeight = 330; panel.getBoundingClientRect = () => ({ height: panel.offsetHeight * .5 }); stage.clientHeight = 470;
const window = new Element(), document = new Element(); document.defaultView = window; root.ownerDocument = document;
const elements = { "[data-picker-tools-resize]": handle, "[data-picker-tools-panel]": panel, ".viewport-panel": viewport, ".viewport-stage": stage };
root.querySelector = (selector) => elements[selector] || null;
let commits = 0;
const resizer = picker.hmbInstallPickerToolsPanelResizer(root, { currentState: () => state, save(height) { commits += 1; state = picker.hmbUpdatePickerVideoTools(state, (tools) => { tools.panel_height = height; }); resizer.refresh(); } });
resizer.refresh();
assert.equal(handle.hidden, false);
assert.equal(handle.getAttribute("aria-valuenow"), "330");
const gesture = (type, y, pointerId = 1) => root.emit(type, { target: handle, button: 0, pointerId, clientY: y });
gesture("pointerdown", 500);
gesture("pointermove", 450); gesture("pointermove", 400);
assert.equal(commits, 0, "Pointer moves never commit or send backend work.");
assert.equal(panel.style["--hmb-picker-tools-height"], "530px", "Upward drag accounts for a 50% canvas scale.");
gesture("pointerup", 400);
assert.equal(commits, 1);
assert.equal(state.video_tools_by_shot[shot].panel_height, 530);
assert.equal(picker.hmbNormalizePickerVideoTools(JSON.parse(JSON.stringify(state.video_tools_by_shot[shot]))).panel_height, 530);
gesture("pointerdown", 500); gesture("pointermove", 400); gesture("pointercancel", 400);
assert.equal(commits, 1);
gesture("pointerdown", 500); window.emit("blur"); gesture("pointerup", 400);
assert.equal(commits, 1);
gesture("pointerdown", 500);
state = { ...state, active_picker_shot_uuid: otherShot }; resizer.refresh(); gesture("pointerup", 400);
assert.equal(commits, 1, "Shot changes cancel rather than commit to the new Shot.");
assert.equal(handle.hidden, true, "New Shot defaults to Video Output mode.");
state = { ...state, active_picker_shot_uuid: shot }; resizer.refresh();
assert.equal(handle.getAttribute("aria-valuenow"), "530");
root.emit("keydown", { target: handle, key: "ArrowUp" });
assert.equal(state.video_tools_by_shot[shot].panel_height, 554);
assert.equal(picker.hmbPickerToolsPanelHeight(900, 500), 380, "A viewport keeps at least 120px when available.");
assert.equal(picker.hmbPickerToolsPanelHeight(10, 800), 160);
gesture("pointerdown", 500); const savedCommits = commits; resizer.cleanup(); gesture("pointerup", 100);
assert.equal(commits, savedCommits);
assert.equal([...root.listeners.values()].flat().length, 0);
assert.equal([...window.listeners.values()].flat().length, 0);
assert.equal([...document.listeners.values()].flat().length, 0);
assert.match(source, /data-picker-tools-resize role="separator" aria-orientation="horizontal" tabindex="0"/);
console.log("PASS: Tool output source ownership, current DOM settings, scale-aware resize, one commit, Shot isolation and cleanup.");
