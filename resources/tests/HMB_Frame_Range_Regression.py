from pathlib import Path
import importlib.util
import json
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")


def prompt_json_section(payload: str, header: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    return json.loads(lines[lines.index(header) + 1])


# Maya display frames and zero-based decoded indices remain distinct.
maya_metadata = picker._video_frame_metadata(
    {
        "decoded_frame_count": 73,
        "source_fps": 24,
        "start_frame": 101,
        "end_frame": 173,
        "has_maya_frame_range": True,
        "markers": [{"asset_id": "Hero", "color": "Green", "video_slot": 3}],
    },
    3,
)
assert maya_metadata["video_slot"] == "@video3"
assert maya_metadata["start_frame"] == 101
assert maya_metadata["end_frame"] == 173
assert maya_metadata["frame_index_start"] == 0
assert maya_metadata["frame_index_end"] == 72
assert maya_metadata["timebase"] == "24/1"
assert maya_metadata["available_color_picks"] == ["Green"]
assert maya_metadata["valid"] is True

mismatched_metadata = picker._video_frame_metadata(
    {
        "decoded_frame_count": 72,
        "source_fps": 24,
        "start_frame": 101,
        "end_frame": 173,
        "has_maya_frame_range": True,
    },
    3,
)
assert mismatched_metadata["conflict"] is True
assert mismatched_metadata["valid"] is False
assert mismatched_metadata["warnings"]

external_metadata = picker._video_frame_metadata(
    {
        "decoded_frame_count": 144,
        "source_fps": 24,
        "source_duration_seconds": 6,
    },
    2,
)
assert (external_metadata["start_frame"], external_metadata["end_frame"]) == (1, 144)
assert external_metadata["duration_seconds"] == 6

converted_metadata = picker._video_frame_metadata(
    {
        "decoded_frame_count": 139,
        "source_fps": 24,
        "output_fps": 16,
        "source_duration_seconds": 139 / 24,
        "output_duration_seconds": 139 / 16,
        "source_width": 1280,
        "source_height": 720,
        "output_width": 1024,
        "output_height": 576,
    },
    3,
)
assert converted_metadata["fps"] == 16
assert converted_metadata["duration_seconds"] == 139 / 16
assert (converted_metadata["width"], converted_metadata["height"]) == (1024, 576)
assert converted_metadata["timebase"] == "16/1"
assert converted_metadata["frame_count"] == 139
assert converted_metadata["resolution"] == {"width": 1024, "height": 576}
assert converted_metadata["valid"] is True


# PICKER_OUT derives transient @video slots from the current selected order
# while adding the frame contract both per video and as an aggregate list.
picker_node = picker.HMBVideoPickerLibrary(name="frame_range_regression")
picker_state = picker._default_widget_state()
picker_state.update(
    {
        "scene_path": "C:/shots/frame_range.mb",
        "active_slot_count": 3,
        "selected_video_slot": 3,
        "videos": [
            {
                "video_slot": 1,
                "video_path": "C:/shots/frame_range_playblast_1.mp4",
                "camera": "|shotCam",
                "source_fps": 24,
                "output_fps": 24,
                "source_frame_count": 144,
                "output_frame_count": 144,
                "decoded_frame_count": 144,
                "source_duration_seconds": 6,
                "output_width": 1280,
                "output_height": 720,
                "start_frame": 1,
                "end_frame": 144,
                "has_maya_frame_range": True,
                "markers": [],
            },
            {
                "video_slot": 3,
                "video_path": "C:/shots/frame_range_playblast_3.mp4",
                "camera": "|shotCam",
                "source_fps": 24,
                "output_fps": 24,
                "source_frame_count": 144,
                "output_frame_count": 144,
                "decoded_frame_count": 144,
                "source_duration_seconds": 6,
                "output_width": 1280,
                "output_height": 720,
                "start_frame": 1,
                "end_frame": 144,
                "has_maya_frame_range": True,
                "markers": [
                    {
                        "asset_id": "Hero",
                        "color": "Green",
                        "video_slot": 3,
                        "picker_order": 1,
                    }
                ],
            }
        ],
    }
)
picker_payload = picker_node._build_picker_payload(picker_state)
video2_payload = next(item for item in picker_payload["videos"] if item["video_slot"] == 2)
video2_metadata = next(item for item in picker_payload["frame_metadata"] if item["video_slot"] == "@video2")
assert picker_payload["schema_version"] == 5
assert video2_payload["video_slot"] == 2
assert video2_metadata["frame_count"] == 144
assert (video2_metadata["width"], video2_metadata["height"]) == (1280, 720)
assert (video2_payload["width"], video2_payload["height"]) == (1280, 720)
assert video2_payload["frame_metadata"] == video2_metadata

# A node-level playblast resolution is not evidence about an externally
# processed slot. Per-slot source raster must remain authoritative.
external_raster_state = picker._default_widget_state()
external_raster_state.update(
    {
        "output_width": 1920,
        "output_height": 1080,
        "active_slot_count": 1,
        "videos": [
            {
                "video_slot": 1,
                "video_path": "C:/shots/external_depth.mp4",
                "source_fps": 24,
                "decoded_frame_count": 120,
                "source_duration_seconds": 5,
                "source_width": 1024,
                "source_height": 576,
                "markers": [],
            }
        ],
    }
)
external_raster_payload = picker_node._build_picker_payload(external_raster_state)
external_raster_video = external_raster_payload["videos"][0]
assert (external_raster_video["width"], external_raster_video["height"]) == (
    1024,
    576,
)

# Output metadata wins over source metadata end-to-end, while the node-level
# playblast setting still cannot overwrite the processed slot contract.
converted_payload_state = picker._default_widget_state()
converted_payload_state.update(
    {
        "output_width": 1920,
        "output_height": 1080,
        "active_slot_count": 1,
        "videos": [
            {
                "video_slot": 1,
                "video_path": "C:/shots/converted_depth.mp4",
                "source_fps": 24,
                "output_fps": 16,
                "decoded_frame_count": 139,
                "source_duration_seconds": 139 / 24,
                "output_duration_seconds": 139 / 16,
                "source_width": 1280,
                "source_height": 720,
                "output_width": 1024,
                "output_height": 576,
                "markers": [],
            }
        ],
    }
)
converted_payload = picker_node._build_picker_payload(converted_payload_state)
converted_video = converted_payload["videos"][0]
assert converted_video["fps"] == 16
assert converted_video["duration_seconds"] == 139 / 16
assert (converted_video["width"], converted_video["height"]) == (1024, 576)


# An old/off state must compile byte-for-byte identically even when dormant
# range data exists.
legacy_state = prompt._default_widget_state()
legacy_state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "binding_scopes": ["Full body / full appearance"],
        "binding_custom_scopes": [""],
        "marker_video": 1,
        "binding_video_slots": [1],
        "color_picks": ["Green"],
    }
)
legacy_state["videos"][0].update(
    {
        "present": True,
        "label": "legacy.mp4",
        "source_type": "Maya Preview / Playblast",
        "control_role": "Primary Unified Shot Control",
    }
)
baseline_prompt = prompt._build_prompt_package(legacy_state)
dormant_state = json.loads(json.dumps(legacy_state))
dormant_state["images"][0]["frame_range_enabled"] = False
dormant_state["images"][0]["frame_range_bindings"] = {
    "@video1::Green": {
        "video_slot": "@video1",
        "color_pick": "Green",
        "origin": "manual",
        "ranges": [{"start": 1, "end": 48}],
    }
}
assert prompt._build_prompt_package(dormant_state) == baseline_prompt
normalized_dormant = prompt._normalize_state(dormant_state)["images"][0]
assert normalized_dormant["frame_range_bindings"] == {
    "@video1::Green": {
        "video_slot": "@video1",
        "color_pick": "Green",
        "origin": "manual",
        "start_frame": None,
        "end_frame": None,
        "ranges": [{"start": 1, "end": 48}],
    }
}
assert normalized_dormant["frame_range_binding"] == normalized_dormant[
    "frame_range_bindings"
]["@video1::Green"]
assert normalized_dormant["frame_range_selected_index"] == -1


# The Prompt library consumes frame metadata, restores sorted multi-ranges, and
# emits the section only for a complete valid binding.
prompt_state = prompt._default_widget_state()
prompt_state["images"][0].update(
    {
        "present": True,
        "label": "Hero",
        "source_type": "Character Appearance",
        "owner": "Hero",
        "binding_scopes": ["Full body / full appearance"],
        "binding_custom_scopes": [""],
        "marker_video": 2,
        "binding_video_slots": [2],
        "color_picks": ["Green"],
    }
)
prompt_state = prompt._apply_picker_payload(prompt_state, picker_payload, connected=True)
image = prompt_state["images"][0]
image["frame_range_enabled"] = True
image["frame_range_bindings"] = {
    "@video2::Green": {
        "video_slot": "@video2",
        "color_pick": "Green",
        "origin": "manual",
        "ranges": [
            {"start": 97, "end": 120},
            {"start": 121, "end": 144},
            {"start": 1, "end": 48},
        ],
    },
    "@video1::Green": {
        "video_slot": "@video1",
        "color_pick": "Green",
        "origin": "manual",
        "ranges": [{"start": 10, "end": 20}],
    },
    "@video3::Blue": {
        "video_slot": "@video3",
        "color_pick": "Blue",
        "origin": "manual",
        "ranges": [{"start": 30, "end": 40}],
    },
}
compiled = prompt._build_prompt_package(prompt_state)
compiled_job = prompt_json_section(compiled, "HMB JOB DATA (JSON):")
assert compiled_job["frame_ranges"] == [{
    "image": "@image1",
    "video": "@video2",
    "marker_color": "Green",
    "enabled": True,
    "origin": "manual",
    "domain": {
        "start_frame": 1,
        "end_frame": 144,
        "frame_count": 144,
        "timebase": "24/1",
        "fps": 24.0,
    },
    "segments": [
        {"start_frame": 1, "end_frame": 48},
        {"start_frame": 97, "end_frame": 144},
    ],
    "unresolved_segments": [],
    "valid": True,
    "error_codes": [],
}]

normalized_image = prompt._normalize_state(prompt_state)["images"][0]
assert normalized_image["frame_range_bindings"]["@video1::Green"]["ranges"] == [
    {"start": 10, "end": 20}
]
assert normalized_image["frame_range_bindings"]["@video3::Blue"]["ranges"] == [
    {"start": 30, "end": 40}
]

range_off_state = json.loads(json.dumps(prompt_state))
range_off_state["images"][0]["frame_range_enabled"] = False
assert prompt_json_section(
    prompt._build_prompt_package(range_off_state),
    "HMB JOB DATA (JSON):",
)["frame_ranges"] == []
normalized_range_off = prompt._normalize_state(range_off_state)["images"][0]
assert set(normalized_range_off["frame_range_bindings"]) == {
    "@video1::Green",
    "@video3::Blue",
    "@video2::Green",
}
assert normalized_range_off["frame_range_binding"] == normalized_range_off[
    "frame_range_bindings"
]["@video2::Green"]
assert normalized_range_off["frame_range_selected_index"] == -1

range_restarted_state = json.loads(json.dumps(prompt._normalize_state(range_off_state)))
range_restarted_state["images"][0]["frame_range_enabled"] = True
normalized_range_restarted = prompt._normalize_state(range_restarted_state)["images"][0]
assert set(normalized_range_restarted["frame_range_bindings"]) == {
    "@video1::Green",
    "@video3::Blue",
    "@video2::Green",
}
assert normalized_range_restarted["frame_range_bindings"]["@video2::Green"]["ranges"] == [
    {"start": 1, "end": 48},
    {"start": 97, "end": 144},
]
assert normalized_range_restarted["frame_range_binding"] == normalized_range_restarted[
    "frame_range_bindings"
]["@video2::Green"]
assert prompt_json_section(
    prompt._build_prompt_package(range_restarted_state),
    "HMB JOB DATA (JSON):",
)["frame_ranges"][0]["segments"] == [
    {"start_frame": 1, "end_frame": 48},
    {"start_frame": 97, "end_frame": 144},
]

image["frame_range_bindings"]["@video2::Green"]["ranges"] = [{"start": 1, "end": 145}]
invalid_range = prompt_json_section(
    prompt._build_prompt_package(prompt_state),
    "HMB JOB DATA (JSON):",
)["frame_ranges"][0]
assert invalid_range["segments"] == []
assert invalid_range["unresolved_segments"] == [{
    "start_frame": 1,
    "end_frame": 145,
    "error_code": "segment_out_of_domain",
}]
assert invalid_range["valid"] is False

missing_metadata_state = json.loads(json.dumps(prompt_state))
missing_metadata_state["picker"]["frame_metadata"] = []
missing_metadata_range = prompt_json_section(
    prompt._build_prompt_package(missing_metadata_state),
    "HMB JOB DATA (JSON):",
)["frame_ranges"][0]
assert missing_metadata_range["segments"] == []
assert missing_metadata_range["valid"] is False
assert missing_metadata_range["error_codes"] == [
    "domain_start_missing",
    "domain_end_missing",
]


# Picker metadata is optional when the user supplies an explicit manual frame
# domain. The domain controls the track bounds; ranges remain the actual
# image-replacement intervals.
manual_state = json.loads(json.dumps(prompt_state))
manual_state["picker"] = {
    "enabled": False,
    "awaiting_data": False,
    "suppressed": False,
    "frame_metadata": [],
}
manual_image = manual_state["images"][0]
manual_image["frame_range_enabled"] = True
manual_image["frame_range_bindings"]["@video2::Green"] = {
    "video_slot": "@video2",
    "color_pick": "Green",
    "origin": "manual",
    "start_frame": 1001,
    "end_frame": 1120,
    "ranges": [
        {"start": 1010, "end": 1020},
        {"start": 1100, "end": 1110},
    ],
}
manual_binding, manual_metadata, manual_errors = prompt._frame_range_binding_validation(
    manual_state,
    manual_image,
    {1, 2},
)
assert manual_errors == []
assert manual_binding is not None
assert manual_metadata is not None
assert manual_metadata["origin"] == "manual"
assert manual_metadata["fps"] == 0.0
assert (manual_metadata["start_frame"], manual_metadata["end_frame"]) == (1001, 1120)
manual_compiled = prompt._build_prompt_package(manual_state)
manual_range = prompt_json_section(
    manual_compiled,
    "HMB JOB DATA (JSON):",
)["frame_ranges"][0]
assert manual_range["domain"] == {
    "start_frame": 1001,
    "end_frame": 1120,
    "frame_count": 120,
    "fps": 0.0,
}
assert manual_range["segments"] == [
    {"start_frame": 1010, "end_frame": 1020},
    {"start_frame": 1100, "end_frame": 1110},
]
assert manual_range["valid"] is True

normalized_manual = prompt._normalize_state(manual_state)["images"][0]
normalized_manual_binding = normalized_manual["frame_range_bindings"]["@video2::Green"]
assert normalized_manual_binding["start_frame"] == 1001
assert normalized_manual_binding["end_frame"] == 1120

missing_manual_end = json.loads(json.dumps(manual_state))
missing_manual_end["images"][0]["frame_range_bindings"]["@video2::Green"]["end_frame"] = None
missing_manual_range = prompt_json_section(
    prompt._build_prompt_package(missing_manual_end),
    "HMB JOB DATA (JSON):",
)["frame_ranges"][0]
assert missing_manual_range["segments"] == []
assert missing_manual_range["valid"] is False
assert "domain_end_missing" in missing_manual_range["error_codes"]

print("HMB Picker frame metadata and Prompt multi-frame range regression: PASS")
