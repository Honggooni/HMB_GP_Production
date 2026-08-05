from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
import types


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")


# Simulate Griptape's load order: construct a fresh node, then assign the
# serialized property value from the saved workflow.
picker_node = picker.HMBVideoPickerLibrary(name="picker_state_restore")
assert picker_node.width == 1400
assert picker_node.height == 1200
assert picker_node.metadata["size"] == {"width": 1400, "height": 1200}
assert picker_node.metadata["hmb_picker_native_size_version"] == 2

# Updating the library's new-node default must not migrate a serialized manual
# resize from an existing workflow.
saved_picker_metadata = {
    "size": {"width": 1234, "height": 1188},
    "hmb_picker_native_size_version": 2,
}
resized_picker_node = picker.HMBVideoPickerLibrary(
    name="picker_manual_size_restore",
    metadata=copy.deepcopy(saved_picker_metadata),
)
assert resized_picker_node.metadata["size"] == saved_picker_metadata["size"]
assert resized_picker_node.metadata["hmb_picker_native_size_version"] == 2
saved_picker_state = copy.deepcopy(picker_node._picker_state())
saved_picker_state.update({
    "runtime_instance_id": "saved-workflow-runtime",
    "state_writer": "widget",
    "state_revision": 41,
    "active_slot_count": 3,
    "selected_video_slot": 2,
    "selected_video_uid": "persist-video-2",
    "preview_video_uid": "persist-video-2",
    "workspace_view": "playblast",
    "lower_panel_ratio": 0.51,
    "main_split_ratio": 0.73,
    "right_split_ratio": 0.36,
    "node_width": 2175,
    "node_height": 1440,
    "outliner_panel_height": 690,
    "viewport_panel_height": 820,
    "right_section_heights": {"settings": 230, "color": 510, "log": 270},
    "ui_theme": "T",
    "outliner_search": "hero",
    "selected_outliner_path": "|SET|Hero_GRP",
    "selected_outliner_name": "Hero_GRP",
    "selected_color": "Red",
    "videos": [
        {
            "video_uid": "persist-video-1",
            "source_uid": "persist-video-1",
            "catalog_order": 1,
            "selected": True,
            "selection_order": 1,
            "video_slot": 1,
            "video_path": "C:/project/inputs/videos/shot_playblast_1.mp4",
            "camera": "|shotCam",
            "markers": [],
        },
        {
            "video_uid": "persist-video-2",
            "source_uid": "persist-video-2",
            "catalog_order": 2,
            "selected": True,
            "selection_order": 2,
            "video_slot": 2,
            "video_path": "C:/project/inputs/videos/shot_playblast_2.mp4",
            "camera": "|shotCam",
            "markers": [],
        },
        {
            "video_uid": "persist-video-3",
            "source_uid": "persist-video-3",
            "catalog_order": 3,
            "selected": True,
            "selection_order": 3,
            "video_slot": 3,
            "video_path": "C:/project/inputs/videos/shot_playblast_3.mp4",
            "camera": "|shotCam",
            "markers": [],
        },
    ],
    "slot_assignments": [
        {"video_slot": 1, "bindings": []},
        {"video_slot": 2, "bindings": [
            {
                "group_name": "BackgroundA",
                "full_dag_path": "|SET|BackgroundA",
                "maya_uuid": "background-a",
                "color": "Sky Blue",
                "enabled": True,
                "video_slot": 2,
                "picker_order": 1,
            },
            {
                "group_name": "BackgroundB",
                "full_dag_path": "|SET|BackgroundB",
                "maya_uuid": "background-b",
                "color": "Sky Blue",
                "enabled": True,
                "video_slot": 2,
                "picker_order": 2,
            },
        ]},
        {"video_slot": 3, "bindings": []},
    ],
    "slot_visibility": [
        {"video_slot": 1, "hidden_paths": []},
        {"video_slot": 2, "hidden_paths": ["|SET|Hidden_GRP"]},
        {"video_slot": 3, "hidden_paths": []},
    ],
})

picker_parameter = picker._get_parameter_obj(picker_node, picker.WIDGET_STATE_PARAMETER)
hydrated_picker_state = picker_node.before_value_set(picker_parameter, saved_picker_state)
picker_node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, hydrated_picker_state)
picker_node.after_value_set(picker_parameter, hydrated_picker_state)

restored_picker_state = picker_node._picker_state()
for key in (
    "active_slot_count",
    "selected_video_slot",
    "workspace_view",
    "lower_panel_ratio",
    "main_split_ratio",
    "right_split_ratio",
    "node_width",
    "node_height",
    "outliner_panel_height",
    "viewport_panel_height",
    "right_section_heights",
    "ui_theme",
    "outliner_search",
    "selected_outliner_path",
    "selected_outliner_name",
    "selected_color",
):
    assert restored_picker_state[key] == saved_picker_state[key], key
assert restored_picker_state["videos"][1]["video_path"].endswith("shot_playblast_2.mp4")
assert [
    item["selection_order"] for item in restored_picker_state["videos"]
] == [1, 2, 3]
assert restored_picker_state["preview_video_uid"] == "persist-video-2"
assert restored_picker_state["slot_visibility"][1]["hidden_paths"] == ["|SET|Hidden_GRP"]
restored_background_bindings = restored_picker_state["slot_assignments"][1]["bindings"]
assert [item["color"] for item in restored_background_bindings] == ["Sky Blue", "Sky Blue"]
assert [item["full_dag_path"] for item in restored_background_bindings] == [
    "|SET|BackgroundA", "|SET|BackgroundB",
]
assert picker.parameter_exists(picker_node, picker.VIDEO_OUTPUT_PARAMETER)
assert not any(
    picker.parameter_exists(picker_node, f"VIDEO{slot}_OUT")
    for slot in range(1, picker.MAX_VIDEO_SLOTS + 1)
)
assert picker.parameter_exists(picker_node, picker.WIDGET_COMMAND_PARAMETER)
command_parameter = picker._get_parameter_obj(picker_node, picker.WIDGET_COMMAND_PARAMETER)
boot_command = picker._parse_picker_command(picker_node.get_parameter_value(picker.WIDGET_COMMAND_PARAMETER))
assert boot_command["runtime_instance_id"] == picker_node._hmb_runtime_instance_id
assert boot_command["action"] == ""

# A command retained in a serialized workflow must not replay in a new runtime.
stale_command = picker._default_picker_command("saved-workflow-runtime")
stale_command.update({
    "action": "set_language",
    "action_id": "stale-restored-command",
    "issued_at_ms": int(time.time() * 1000),
    "payload": {"language": "ko"},
})
final_stale_command = picker_node.before_value_set(command_parameter, stale_command)
picker_node.set_parameter_value(picker.WIDGET_COMMAND_PARAMETER, final_stale_command)
picker_node.after_value_set(command_parameter, final_stale_command)
time.sleep(0.05)
assert picker_node._picker_state()["backend_ack_action_id"] != "stale-restored-command"
assert picker_node._picker_state()["runtime_instance_id"] == picker_node._hmb_runtime_instance_id


# Node Run is output synchronization only. It must not invoke Maya/playblast and
# must not alter the remembered dashboard shape.
def forbidden_playblast(*_args, **_kwargs):
    raise AssertionError("process() attempted to generate a playblast")


picker_node._maya_mode = forbidden_playblast
before_run = copy.deepcopy(picker_node._picker_state())
run_result = picker_node.process()
after_run = picker_node._picker_state()
assert run_result["action"] == "sync_outputs"
assert run_result["active_slot_count"] == 3
assert run_result["selected_video_slot"] == 2
assert run_result["video_count"] == 3
assert after_run["workspace_view"] == before_run["workspace_view"]
assert after_run["node_width"] == before_run["node_width"]
assert after_run["node_height"] == before_run["node_height"]
assert after_run["videos"] == before_run["videos"]


# Prompt state (rows, text, and manually resized UI groups/textareas) survives
# the same construct-then-assign workflow load sequence.
prompt_node = prompt.HMBPromptLibrary(name="prompt_state_restore")
saved_prompt_state = prompt._default_widget_state()
saved_prompt_state["images"][0].update({
    "present": True,
    "label": "Hero",
    "source_type": "Character Appearance",
    "owner": "Hero",
})
saved_prompt_state["videos"][0].update({
    "present": True,
    "label": "shot_playblast_1",
    "source_type": "Primary Shot / Unified Control",
})
saved_prompt_state["text"]["SCENE_CONTEXT"] = "Night exterior continuity."
saved_prompt_state["ui"] = {
    "group_heights": {
        "imageSources": 710,
        "imageText": 260,
        "videoSources": 530,
        "videoText": 220,
    },
    "textarea_heights": {"video:1:keep_out": 188},
    "resize_mode": prompt.UI_RESIZE_MODE,
    "language": "ko",
    "theme": "T",
}
saved_prompt_state = prompt._normalize_state(saved_prompt_state)
saved_prompt_text = json.dumps(saved_prompt_state, ensure_ascii=False, separators=(",", ":"))
prompt_parameter = prompt._get_parameter_obj(prompt_node, prompt.WIDGET_PARAMETER_NAME)

# Model the retained-mode event loop and prove after_value_set only schedules
# work; it must not call set_parameter_value again inside the same transaction.
module_names = [
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.griptape_nodes",
]
saved_modules = {name: sys.modules.get(name) for name in module_names}
scheduled_callbacks = []

class _FakeEventLoop:
    @staticmethod
    def is_running():
        return True

    @staticmethod
    def call_soon_threadsafe(callback):
        scheduled_callbacks.append(callback)

class _FakeEventManager:
    event_loop = _FakeEventLoop()

    @staticmethod
    def put_event(_event):
        return None

class _FakeGriptapeNodes:
    @staticmethod
    def EventManager():
        return _FakeEventManager()

for package_name in module_names[:2]:
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
engine_module = types.ModuleType(module_names[2])
engine_module.GriptapeNodes = _FakeGriptapeNodes
sys.modules[module_names[2]] = engine_module

raw_prompt_set = prompt_node.set_parameter_value
raw_prompt_get = prompt_node.get_parameter_value
nested_prompt_writes = []
prompt_widget_writes = []
prompt_widget_value = [saved_prompt_text]
in_after_value_set = False

def guarded_prompt_set(name, value):
    if in_after_value_set:
        nested_prompt_writes.append(name)
    if name == prompt.WIDGET_PARAMETER_NAME:
        prompt_widget_writes.append(value)
        prompt_widget_value[0] = value
        return None
    return raw_prompt_set(name, value)

def guarded_prompt_get(name):
    if name == prompt.WIDGET_PARAMETER_NAME:
        return prompt_widget_value[0]
    return raw_prompt_get(name)

prompt_node.set_parameter_value = guarded_prompt_set
prompt_node.get_parameter_value = guarded_prompt_get
try:
    # Model the host's already-committed property value without emitting a
    # second retained-mode lifecycle event from this unregistered test node.
    in_after_value_set = True
    prompt_node.after_value_set(prompt_parameter, saved_prompt_text)
    in_after_value_set = False
    assert nested_prompt_writes == []
    assert len(scheduled_callbacks) == 1
    scheduled_callbacks.pop()()
    assert len(prompt_widget_writes) == 0, (
        "An already-canonical widget edit must not be written back a second time; "
        "that duplicate host echo remounts the Prompt dashboard."
    )
finally:
    in_after_value_set = False
    for module_name, original_module in saved_modules.items():
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module

restored_prompt_state = prompt_node._current_state()
assert restored_prompt_state["images"][0]["label"] == "Hero"
assert restored_prompt_state["videos"][0]["label"] == "shot_playblast_1"
assert restored_prompt_state["text"]["SCENE_CONTEXT"] == "Night exterior continuity."
assert restored_prompt_state["ui"]["group_heights"]["imageSources"] == 710
assert restored_prompt_state["ui"]["textarea_heights"]["video:1:keep_out"] == 188
assert restored_prompt_state["ui"]["language"] == "ko"
assert restored_prompt_state["ui"]["theme"] == "T"
assert prompt_node.parameter_output_values["PROMPT_OUT"] == prompt._build_prompt_package(restored_prompt_state)

prompt_before_run = copy.deepcopy(restored_prompt_state)
prompt_node.process()
prompt_after_run = prompt_node._current_state()
assert prompt_after_run["images"] == prompt_before_run["images"]
assert prompt_after_run["videos"] == prompt_before_run["videos"]
assert prompt_after_run["text"] == prompt_before_run["text"]
assert prompt_after_run["ui"] == prompt_before_run["ui"]


# Griptape Reset Node replaces the node with a newly constructed instance.
# Fresh instances alone return to each library's minimum/default state.
reset_picker = picker.HMBVideoPickerLibrary(name="picker_reset_default")
reset_picker_state = reset_picker._picker_state()
assert reset_picker_state["active_slot_count"] == 1
assert reset_picker_state["selected_video_slot"] == 1
assert reset_picker_state["videos"] == []
assert reset_picker_state["workspace_view"] == "outliner"
assert reset_picker_state["node_width"] == 0
assert reset_picker_state["node_height"] == 0
assert reset_picker_state["outliner_panel_height"] == 0
assert reset_picker_state["viewport_panel_height"] == 0
assert reset_picker_state["right_section_heights"] == {"settings": 285, "color": 628, "log": 208}
assert reset_picker_state["ui_layout_version"] == 5
assert reset_picker_state["ui_theme"] == "P"

legacy_picker_state = picker._default_widget_state()
legacy_picker_state.pop("ui_layout_version", None)
legacy_picker_state["viewport_panel_height"] = 900
legacy_picker_state["right_section_heights"] = {"settings": 190, "color": 412, "log": 208}
migrated_picker_state = picker._parse_state(legacy_picker_state)
assert migrated_picker_state["ui_layout_version"] == 5
assert migrated_picker_state["viewport_panel_height"] == 684
assert migrated_picker_state["right_section_heights"]["color"] == 628

reset_prompt = prompt.HMBPromptLibrary(name="prompt_reset_default")
reset_prompt_state = reset_prompt._current_state()
assert not any(item.get("label") for item in reset_prompt_state["images"])
assert not any(item.get("label") for item in reset_prompt_state["videos"])
assert not any(str(value or "").strip() for value in reset_prompt_state["text"].values())
assert reset_prompt_state["ui"]["group_heights"] == {}
assert reset_prompt_state["ui"]["textarea_heights"] == {}
assert reset_prompt_state["ui"]["theme"] == "P"

# The idempotent local-echo guard must not suppress an authoritative external
# Picker payload. A changed PICKER_IN value still rewrites the dashboard once.
external_prompt = prompt.HMBPromptLibrary(name="prompt_external_picker_update")
external_prompt_parameter_writes = []
external_prompt_raw_set = external_prompt.set_parameter_value

def track_external_prompt_set(name, value):
    if name == prompt.WIDGET_PARAMETER_NAME:
        external_prompt_parameter_writes.append(value)
    return external_prompt_raw_set(name, value)

external_prompt.set_parameter_value = track_external_prompt_set
external_prompt._hmb_picker_connected = True
external_prompt_raw_set(
    prompt.PICKER_INPUT_PARAMETER_NAME,
    json.dumps(
        {
            "mode": "maya",
            "run_id": "external-picker-regression",
            "active_slot_count": 1,
            "videos": [
                {
                    "video_slot": 1,
                    "video_path": "P:/show/shot/external_picker_regression.mp4",
                    "camera": "|shotCam",
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ),
)
external_state = external_prompt._write_dashboard_state()
assert len(external_prompt_parameter_writes) == 1
assert external_state["picker"]["run_id"] == "external-picker-regression"
assert external_state["videos"][0]["label"] == "external_picker_regression"

# Legacy/custom runtimes may restore a canonical dict even though the widget
# transport is string-typed. A permissive runtime must publish one string
# migration; a strict host may coerce the dict to a string immediately, in which
# case the idempotent writer correctly emits no duplicate update.
dict_prompt = prompt.HMBPromptLibrary(name="prompt_dict_transport_migration")
dict_prompt_state = prompt._normalize_state(dict_prompt._current_state())
dict_prompt.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, dict_prompt_state)
dict_prompt_raw_set = dict_prompt.set_parameter_value
dict_prompt_writes = []

def track_dict_prompt_set(name, value):
    if name == prompt.WIDGET_PARAMETER_NAME:
        dict_prompt_writes.append(value)
    return dict_prompt_raw_set(name, value)

dict_prompt.set_parameter_value = track_dict_prompt_set
dict_prompt._write_dashboard_state()
assert len(dict_prompt_writes) <= 1
if dict_prompt_writes:
    assert isinstance(dict_prompt_writes[0], str)
else:
    assert isinstance(
        prompt._get_parameter_raw(dict_prompt, prompt.WIDGET_PARAMETER_NAME),
        str,
    )

print("HMB Picker/Prompt run and persistent UI-state regression: PASS")
