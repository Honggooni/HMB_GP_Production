import assert from "node:assert/strict";
import fs from "node:fs";

const widgetPath = new URL("../../widgets/HMBVideoPickerLibraryWidget_v032.js", import.meta.url);
const widgetSource = fs.readFileSync(widgetPath, "utf8");
const picker = await import(`data:text/javascript;base64,${Buffer.from(widgetSource).toString("base64")}`);

const emittedState = {
  schema: "maya-video-picker-state",
  state_revision: 17,
  state_writer: "widget",
  state_published_at_ms: 1722222000123,
  frontend_seen_revision: 16,
  runtime_instance_id: "runtime-echo-test",
  status: "READY",
  scene_stage: "OUTLINER_READY",
  backend_ack_action_id: "read-ack-existing",
  pending_action: "",
  pending_action_id: "",
  original_preview_enabled: false,
  original_video_path: "C:/shots/shot01/cached-original.mp4",
  original_video_url: "file:///C:/shots/shot01/cached-original.mp4",
  selected_video_slot: 1,
  active_slot_count: 1,
  selected_outliner_path: "|Character",
  selected_outliner_name: "Character",
  selected_outliner_uuid: "maya-uuid-1",
  outliner_nodes: [{ full_path: "|Character", name: "Character", maya_uuid: "maya-uuid-1" }],
  slot_assignments: [{ video_slot: 1, bindings: [] }],
  slot_visibility: [{ video_slot: 1, hidden_paths: [] }],
};

function pendingContainer(disabled = false) {
  const container = {};
  picker.hmbRememberPendingPickerStateEcho(container, emittedState, { disabled });
  return container;
}

let container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    { value: structuredClone(emittedState), disabled: false },
  ),
  true,
  "The exact widget-owned optimistic echo is consumed without a full widget update.",
);
assert.equal(container.__hmbPendingPickerStateEchoes, undefined);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    { parameterValue: structuredClone(emittedState), disabled: false },
  ),
  true,
  "The Griptape parameterValue transport shape uses the same exact-echo guard.",
);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    { value: structuredClone(emittedState), disabled: true },
  ),
  false,
  "A disabled-prop change must always reach the normal update path.",
);
picker.hmbClearPendingPickerStateEcho(container);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        state_writer: "python",
        original_preview_enabled: true,
      },
      disabled: false,
    },
  ),
  false,
  "An authoritative Original checkbox change must reach the morph path so checked state is updated.",
);
picker.hmbClearPendingPickerStateEcho(container);

const enabledOriginalEcho = {
  ...emittedState,
  state_revision: emittedState.state_revision + 1,
  state_published_at_ms: emittedState.state_published_at_ms + 1,
  original_preview_enabled: true,
};
container = {};
picker.hmbRememberPendingPickerStateEcho(container, enabledOriginalEcho, { disabled: false });
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    { value: structuredClone(enabledOriginalEcho), disabled: false },
  ),
  true,
  "An exact widget-owned Original checkbox echo is disposable without remounting.",
);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        state_writer: "python",
        frontend_seen_revision: emittedState.frontend_seen_revision + 1,
      },
      disabled: false,
    },
  ),
  true,
  "A backend transport echo may change writer/seen metadata while preserving the exact functional state.",
);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        state_writer: "python",
        state_revision: emittedState.state_revision + 1,
        state_published_at_ms: emittedState.state_published_at_ms + 1,
      },
      disabled: false,
    },
  ),
  false,
  "A newer Python revision must never be consumed as an optimistic echo.",
);
picker.hmbClearPendingPickerStateEcho(container);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        state_writer: "python",
        backend_ack_action_id: "read-ack-new",
      },
      disabled: false,
    },
  ),
  false,
  "A backend command acknowledgement must always update the dashboard.",
);
picker.hmbClearPendingPickerStateEcho(container);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        state_writer: "python",
        status: "READING_SCENE",
        scene_stage: "MAYA_READING",
        operation_kind: "read_scene",
        active_process_pid: 4821,
      },
      disabled: false,
    },
  ),
  false,
  "Backend operation progress must always update the dashboard.",
);
picker.hmbClearPendingPickerStateEcho(container);

container = pendingContainer(false);
assert.equal(
  picker.hmbConsumePendingPickerStateEcho(
    container,
    {
      value: {
        ...emittedState,
        pending_action: "read_scene",
        pending_action_id: "legacy-command",
      },
      disabled: false,
    },
  ),
  false,
  "Command-bearing state is never treated as a disposable selection echo.",
);
picker.hmbClearPendingPickerStateEcho(container);

const updateSource = widgetSource.slice(
  widgetSource.lastIndexOf("container.__hmbVideoPickerControllerUpdate = (nextProps) =>"),
  widgetSource.indexOf(
    "return container.__hmbVideoPickerControllerProxy",
    widgetSource.lastIndexOf("container.__hmbVideoPickerControllerUpdate = (nextProps) =>"),
  ),
);
assert.match(updateSource, /hmbConsumePendingPickerStateEcho\(container, nextProps \|\| \{\}\)/);
assert.match(updateSource, /hmbClearPendingPickerStateEcho\(container\);[\s\S]*patchMountedPicker\(nextProps \|\| \{\}\)/);

// Model the retained update boundary: an exact Shot echo returns before any
// regional DOM patch, while a functional backend mismatch crosses that boundary once.
let modeledPatchCount = 0;
const modeledUpdate = (target, nextProps) => {
  if (picker.hmbConsumePendingPickerStateEcho(target, nextProps)) return "echo";
  modeledPatchCount += 1;
  return "patch";
};
container = pendingContainer(false);
assert.equal(
  modeledUpdate(container, { value: structuredClone(emittedState), disabled: false }),
  "echo",
);
assert.equal(modeledPatchCount, 0, "An exact retained echo must cause zero regional patches.");
container = pendingContainer(false);
assert.equal(
  modeledUpdate(container, {
    value: { ...emittedState, status: "READING_SCENE", state_revision: 18 },
    disabled: false,
  }),
  "patch",
);
assert.equal(modeledPatchCount, 1, "A functional authoritative mismatch must reach one regional patch.");
picker.hmbClearPendingPickerStateEcho(container);

assert.doesNotMatch(
  widgetSource,
  /\.hmbvp button,.hmbvp input,.hmbvp select,.hmbvp \.panel/,
  "Structural panels are no longer animated during state synchronization.",
);
assert.match(
  widgetSource,
  /\.hmbvp button,.hmbvp input,.hmbvp select\{transition:border-color 80ms ease,color 80ms ease\}/,
);
assert.doesNotMatch(widgetSource, /\.hmbvp \.outliner-row\{transition:/);
assert.doesNotMatch(widgetSource, /transition:[^}\n]*background(?:-color)?/);
assert.doesNotMatch(
  widgetSource,
  /transition:[^}\n]*(?:opacity|transform)/,
  "Selection synchronization must not animate opacity or transforms.",
);

assert.match(
  widgetSource,
  /original_enabled:\s*false/,
  "Original generation selection must default OFF in a new widget state.",
);
assert.match(
  widgetSource,
  /state\.original_enabled\s*=\s*!!state\.original_enabled/,
  "Serialized Original generation selection must normalize to one boolean.",
);
assert.equal(
  (widgetSource.match(/id="original-preview-toggle"/g) || []).length,
  1,
  "The visible widget must render exactly one Original checkbox.",
);
assert.match(
  widgetSource,
  /id="original-preview-toggle"[\s\S]*?\$\{originalPreviewChecked\s*\?\s*"checked"\s*:\s*""\}/,
  "Original checkbox markup must restore the inert generation selection.",
);
assert.match(
  widgetSource,
  /on\(container\.querySelector\("#original-preview-toggle"\),\s*"change"/,
  "The Original checkbox must own one explicit change action path.",
);
const originalToggleHandler = widgetSource.slice(
  widgetSource.indexOf('on(container.querySelector("#original-preview-toggle")'),
  widgetSource.indexOf('on(container.querySelector("#mask-playblast-toggle")'),
);
assert.match(originalToggleHandler, /"original_enabled"/);
const outputChoiceHandler = widgetSource.slice(
  widgetSource.indexOf("const queueOutputChoice ="),
  widgetSource.indexOf('on(container.querySelector("#original-preview-toggle")'),
);
assert.match(
  outputChoiceHandler,
  /\[field\]:\s*enabled/,
  "All four output checkboxes must update the requested state field through one path.",
);
assert.match(
  outputChoiceHandler,
  /hmbApplyPickerOutputChoicesToDom\([\s\S]*?schedulePickerStatePublicationAfterPaint\([\s\S]*?commitOptions:\s*\{\s*suppressMatchingEcho:\s*true\s*\}/,
  "Output toggles must paint locally, then coalesce one exact-echo-suppressed publication.",
);
assert.doesNotMatch(
  `${outputChoiceHandler}\n${originalToggleHandler}`,
  /dispatchCommand\s*\(/,
  "Changing Original must never render or dispatch a backend command.",
);
assert.doesNotMatch(
  widgetSource,
  /__hmbOpenedVideo|clearOpenedVideo|Opened local viewport video|id="open-video"|id="open-video-file"|URL\.(?:create|revoke)ObjectURL/,
  "The retired Open-video override and object-URL lifecycle must be absent from the shared viewport.",
);
assert.match(
  widgetSource,
  /\["#original-preview-toggle",\s*!!state\?\.original_enabled\]/,
  "Immediate command UI must synchronize the live checkbox property.",
);
assert.match(
  widgetSource,
  /if \("checked" in current\) current\.checked = !!desired\.checked/,
  "Retained DOM morphing must synchronize checkbox properties, not attributes alone.",
);

assert.match(widgetSource, /mask_enabled:\s*true/,
  "Legacy-compatible Mask generation must default ON.");
assert.equal(
  (widgetSource.match(/id="mask-playblast-toggle"/g) || []).length,
  1,
  "The visible widget must render exactly one Mask checkbox.",
);
const maskToggleHandler = widgetSource.slice(
  widgetSource.indexOf('on(container.querySelector("#mask-playblast-toggle")'),
  widgetSource.indexOf('on(container.querySelector("#depth-playblast-toggle")'),
);
assert.match(maskToggleHandler, /"mask_enabled"/);
assert.doesNotMatch(maskToggleHandler, /dispatchCommand\s*\(/);

assert.match(
  widgetSource,
  /depth_enabled:\s*false/,
  "Depth Playblast must default OFF in a new widget state.",
);
assert.match(
  widgetSource,
  /state\.depth_enabled\s*=\s*!!state\.depth_enabled/,
  "Serialized Depth state must normalize to one boolean.",
);
assert.equal(
  (widgetSource.match(/id="depth-playblast-toggle"/g) || []).length,
  1,
  "The visible widget must render exactly one Depth checkbox.",
);
assert.match(
  widgetSource,
  /id="depth-playblast-toggle"[\s\S]*?\$\{depthChecked\s*\?\s*"checked"\s*:\s*""\}/,
  "Depth checkbox markup must restore the normalized saved state.",
);
assert.match(
  widgetSource,
  /\["#depth-playblast-toggle",\s*!!state\?\.depth_enabled\]/,
  "Immediate UI synchronization must retain the live Depth checkbox value.",
);
const depthToggleHandlerStart = widgetSource.indexOf('on(container.querySelector("#depth-playblast-toggle")');
const depthToggleHandler = widgetSource.slice(
  depthToggleHandlerStart,
  widgetSource.indexOf('on(container.querySelector("#motion-guide-toggle")', depthToggleHandlerStart),
);
assert.match(depthToggleHandler, /"depth_enabled"/);
assert.match(
  outputChoiceHandler,
  /schedulePickerStatePublicationAfterPaint\(next,[\s\S]*?commitOptions:\s*\{\s*suppressMatchingEcho:\s*true\s*\}/,
  "Depth changes must be coalesced local state commits whose exact echo performs no full morph.",
);

const snapshotHandler = widgetSource.slice(
  widgetSource.indexOf('on(container.querySelector("#create-snapshot")'),
  widgetSource.indexOf('on(container.querySelector("#delete-snapshot")'),
);
assert.match(snapshotHandler, /const liveSlot = 1;/);
assert.match(
  snapshotHandler,
  /video_uid:\s*clean\(currentLocal\.preview_video_uid \|\| currentLocal\.selected_video_uid\)/,
  "Snapshot creation must preserve the exact video UID represented by the captured frame.",
);
assert.doesNotMatch(
  snapshotHandler,
  /depth_enabled|include_depth|selection_order/,
  "Asset-card order must not redirect Maya Snapshot authoring away from slot 1.",
);

const generateHandler = widgetSource.slice(
  widgetSource.indexOf('on(container.querySelector("#run-video")'),
  widgetSource.indexOf('on(container.querySelector("#playblast-resolution")'),
);
assert.match(generateHandler, /const depthEnabled = !!currentLocal\.depth_enabled/);
assert.match(generateHandler, /const motionGuideEnabled = !!currentLocal\.motion_guide_enabled/);
assert.match(generateHandler, /const originalEnabled = !!currentLocal\.original_enabled/);
assert.match(generateHandler, /const maskEnabled = !!currentLocal\.mask_enabled/);
assert.match(
  generateHandler,
  /const liveSlot = 1;/,
  "Generate keeps one legacy internal render slot before packed publication.",
);
assert.match(generateHandler, /include_original:\s*originalEnabled/);
assert.match(generateHandler, /include_mask:\s*maskEnabled/);
assert.match(generateHandler, /include_depth:\s*depthEnabled/);
assert.match(generateHandler, /include_motion_guide:\s*motionGuideEnabled/);
assert.match(
  generateHandler,
  /Select at least one output: Original, Mask, Depth, or Motion Guide/,
  "Zero selected outputs must be rejected before command dispatch.",
);
assert.match(
  generateHandler,
  /Generate requested for new history assets:[\s\S]*Existing assets will be preserved/,
  "The Generate log must state that checked roles append immutable history assets.",
);
const previewVideoSource = widgetSource.slice(
  widgetSource.indexOf("function previewVideo"),
  widgetSource.indexOf("\nfunction ", widgetSource.indexOf("function previewVideo") + 1),
);
assert.match(previewVideoSource, /state\?\.preview_video_uid \|\| state\?\.selected_video_uid/);
assert.match(previewVideoSource, /hmbVideoAssetUid\(item, index\) === uid/);
assert.match(previewVideoSource, /return byUid \|\| selectedVideo/);

const forcedVideoPathSource = widgetSource.slice(
  widgetSource.indexOf("const forceVideoPreview"),
  widgetSource.indexOf("const selectedVideoUrl", widgetSource.indexOf("const selectedVideoPath")),
);
assert.match(
  forcedVideoPathSource,
  /const forceVideoPreview = viewportMode === "video"[\s\S]*?clean\(container\.__hmbForceVideoPreviewUid\) === previewUid/,
  "A centered catalog play button may explicitly replace a snapshot/original with that card in the main viewport.",
);
assert.match(
  forcedVideoPathSource,
  /const selectedVideoPath = clean\([\s\S]*?\(forceVideoPreview \? cardVideoPath : ""\)[\s\S]*?original_preview_enabled[\s\S]*?\|\| cardVideoPath/,
  "Forced card playback must win before the normal Original/card fallback without a retired Open-video override.",
);
assert.doesNotMatch(forcedVideoPathSource, /__hmbOpenedVideo|open-video|blob:/);
assert.match(
  forcedVideoPathSource,
  /\(state\.original_preview_enabled \? state\.original_video_url : ""\)/,
);
assert.match(
  forcedVideoPathSource,
  /\(state\.original_preview_enabled \? state\.original_video_path : ""\)/,
);
assert.doesNotMatch(
  forcedVideoPathSource,
  /\|\|\s*state\.original_video_(?:url|path)\b/,
  "Original OFF must never fall through to an unconditional cached-original viewport source.",
);

assert.match(forcedVideoPathSource, /\|\| cardVideoPath/);

const catalogPreviewHandlerStart = widgetSource.indexOf(
  "const playInPreview = (event, button) =>",
  widgetSource.indexOf('on(container.querySelector("#import-video-asset"), "change"'),
);
const catalogPreviewHandler = widgetSource.slice(
  catalogPreviewHandlerStart,
  widgetSource.indexOf(
    "const toggleVideoSelection = (event, selectionSurface) =>",
    catalogPreviewHandlerStart,
  ),
);
assert.match(catalogPreviewHandler, /container\.__hmbAutoplayVideoUid = uid/);
assert.match(catalogPreviewHandler, /container\.__hmbForceVideoPreviewUid = uid/);
assert.match(
  catalogPreviewHandler,
  /hmbPatchVideoPickerPreviewDom\(container, nextState, tr, \{[\s\S]*?autoplay: true,[\s\S]*?Video-card playback[\s\S]*?\}\)/,
);
assert.match(
  catalogPreviewHandler,
  /suppressMatchingEcho:\s*true/,
  "The exact preview region is updated before the optimistic host echo is suppressed.",
);
const autoplayStart = widgetSource.indexOf('const autoplayVideo = container.querySelector("#picker-video")');
const autoplaySource = widgetSource.slice(
  autoplayStart,
  widgetSource.indexOf(
    "const activityLogView",
    autoplayStart,
  ),
);
assert.match(autoplaySource, /const autoplayVideo = container\.querySelector\("#picker-video"\)/);
assert.match(autoplaySource, /Object\.prototype\.hasOwnProperty\.call\(container, "__hmbAutoplayVideoUid"\)/);
assert.match(autoplaySource, /autoplayVideo\?\.play\?\.\(\)/);
assert.doesNotMatch(autoplaySource, /video-asset-thumb-media/);

const controllerUpdateSource = widgetSource.slice(
  widgetSource.indexOf("container.__hmbVideoPickerControllerUpdate ="),
  widgetSource.indexOf("if (!desiredPickerExpanded)", widgetSource.indexOf("container.__hmbVideoPickerControllerUpdate =")),
);
assert.match(
  controllerUpdateSource,
  /hmbConsumePendingPickerStateEcho[\s\S]*?acceptMatchingPickerStateEchoWithoutDom/,
  "An exact optimistic echo must accept transport metadata without reparsing cards or interrupting media.",
);
assert.doesNotMatch(
  controllerUpdateSource.slice(
    controllerUpdateSource.indexOf("if (hmbConsumePendingPickerStateEcho"),
    controllerUpdateSource.indexOf("hmbClearPendingPickerStateEcho"),
  ),
  /patchMountedPicker\(/,
  "The exact-echo branch must not run the regional DOM/media patch.",
);

console.log("HMB VideoPicker exact local echo, forced main-preview autoplay, and no-blink regression: PASS");
