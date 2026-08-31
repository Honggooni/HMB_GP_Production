from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(filename: str, alias: str):
    path = ROOT / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


image_library = load(
    "HMBImageAssetLibrary",
    "hmb_fx_timing_range_image_asset",
)
picker = load(
    "HMBVideoPickerLibrary",
    "hmb_fx_timing_range_video_picker",
)
prompt = load(
    "HMBPromptLibrary",
    "hmb_fx_timing_range_prompt",
)


# Image Asset publishes only typed source/binding evidence. Prompt owns whether
# Range is ON and the concrete video/frame interval for that image source.
asset = image_library._normalize_asset(
    {
        "asset_library_id": "library:fx-smoke",
        "source_uid": "project:library:fx-smoke",
        "source_kind": "project",
        "asset_project_uid": "project:test",
        "asset_id": "FXSmoke",
        "image_name": "FX Smoke Shape",
        "path": "C:/project/FX/FXSmoke.png",
        "relative_path": "FX/FXSmoke.png",
        "source_type": "Custom",
        "custom_source_type": "FX shape reference",
        "scope_candidate": "Custom scope",
        "registered": True,
        "selected": True,
        "selection_order": 1,
    }
)
assert asset is not None
image_state = image_library._default_state()
image_state.update(
    {
        "project_id": "test",
        "project_uid": "project:test",
        "project_root": "C:/project",
        "assets": [asset],
    }
)
selection = {
    "state": image_library._normalize_state(image_state),
    "selected_count": 1,
    "resolved": [
        {
            "asset": asset,
            "media": "C:/project/FX/FXSmoke.png",
            "source_uid": asset["source_uid"],
            "requested_selection_order": 1,
            "selection_order": 1,
            "relative_path": "FX/FXSmoke.png",
        }
    ],
    "unresolved": [],
    "warnings": [],
}
image_payload = image_library._build_output_payload(
    image_state,
    resolved_selection=selection,
)
assert image_payload["binding_contract"] == {
    "schema": "hmb-image-source-binding-capabilities",
    "version": 1,
    "source_identity_fields": ["source_uid", "order_key"],
    "image_source_frame_range": {
        "supported": True,
        "enabled_by_default": False,
    },
}
assert image_payload["verified_assets"][0]["binding_capabilities"][
    "image_source_frame_range"
] is True
assert "authority" not in image_payload
assert "authority_scope" not in image_payload


# Distinct Maya instances of one reusable asset remain distinct. Picker may
# still publish exact typed cues as transport evidence; Prompt does not turn
# those facts into a semantic validity or authority decision.
markers = [
    {
        "color": "Red",
        "asset_id": "JettMini",
        "subject_root": "|shot|JettMini_A",
        "maya_uuid": "UUID-A",
    },
    {
        "color": "Green",
        "asset_id": "JettMini",
        "subject_root": "|shot|JettMini_B",
        "maya_uuid": "UUID-B",
    },
]
video_state = picker._default_widget_state()
video_state["videos"] = [
    {
        "video_uid": "video-fx-reference",
        "selected": True,
        "selection_order": 1,
        "video_url": "https://example.com/fx-reference.mp4",
        "decoded_frame_count": 62,
        "source_fps": 24.0,
        "start_frame": 101,
        "end_frame": 162,
        "has_maya_frame_range": True,
        "markers": markers,
        "timing_cues": [
            {
                "frame": 118,
                "phase": "onset",
                "emitter": {"maya_uuid": "UUID-B"},
                "local_point": {
                    "kind": "coordinates",
                    "space": "object",
                    "unit": "cm",
                    "xyz": [0.25, 1.5, -0.75],
                },
                "description": "Emitter ignition point",
            },
            {
                "frame": 130,
                "phase": "peak",
                "emitter": {"marker_color": "Red"},
                "local_point": {
                    "kind": "locator",
                    "locator_id": "FX_Nozzle_LOC",
                    "locator_path": "|shot|JettMini_A|FX_Nozzle_LOC",
                },
            },
        ],
    }
]
picker_payload, media = picker._build_synchronized_video_outputs(video_state)
assert media == ["https://example.com/fx-reference.mp4"]
video = picker_payload["videos"][0]
assert [marker["maya_uuid"] for marker in video["markers"]] == [
    "UUID-A",
    "UUID-B",
]
assert video["frame_domain"] == {
    "schema": "hmb-video-frame-domain",
    "version": 1,
    "timebase": "24/1",
    "start_frame": 101,
    "end_frame": 162,
    "frame_count": 62,
    "range_addressable": True,
}
assert len(video["timing_cues"]) == 2
assert all(isinstance(item["frame"], int) for item in video["timing_cues"])
cue = video["timing_cues"][0]
assert cue["frame"] == 118
assert cue["cue_phase"] == "onset"
assert cue["emitter"]["maya_uuid"] == "UUID-B"
assert cue["local_point"] == {
    "kind": "coordinates",
    "space": "object",
    "unit": "centimeter",
    "xyz": [0.25, 1.5, -0.75],
}
locator_cue = video["timing_cues"][1]
assert locator_cue["local_point"] == {
    "kind": "locator",
    "locator_id": "FX_Nozzle_LOC",
    "locator_path": "|shot|JettMini_A|FX_Nozzle_LOC",
}
assert video["reference_capabilities"] == {
    "schema": "hmb-video-reference-capabilities",
    "version": 1,
    "frame_addressable": True,
    "exact_emitter_cues": True,
    "image_source_frame_ranges": True,
    "marker_instance_identity_fields": ["maya_uuid", "full_dag_path"],
}
for forbidden in (
    "source_type",
    "fx_behavior_only",
    "appearance_authority",
    "color_authority",
):
    assert forbidden not in video["reference_capabilities"]


# Prompt serializes authored timing/control data neutrally. A semantically
# free-form cue and incomplete control lines survive ordinary field
# normalization instead of being rejected, inferred, or converted to policy.
prompt_state = prompt._default_widget_state()
prompt_video = prompt._default_video_item(1)
prompt_video.update(
    {
        "present": True,
        "label": "fx-reference.mp4",
        "video_uid": "video-fx-reference",
        "video_main_type": "FX Reference",
        "video_sub_type": "FX Effect Only",
        "custom_source_type": "Authored smoke timing reference",
        "custom_control_role": "Use only where explicitly directed",
        "keep_out": "Do not invent extra smoke emitters",
        "timing_cues": [
            cue,
            {
                "cue_id": "authored-freeform-cue",
                "cue_type": "artist_note",
                "cue_phase": "afterglow",
                "frame": 999,
                "description": "Preserve this authored timing note literally",
            },
        ],
    }
)
prompt_state["videos"] = [prompt_video]
prompt_state["images"] = []
prompt_state["text"]["SCENE_CONTEXT"] = "\n".join(
    [
        "CONTROL_ONLY_BINDING: authored free text without a video",
        "VFX_CONTROL_BINDING: @video1 | Target = JettMini_B | Function = emitter",
    ]
)

normalized_prompt = prompt._normalize_state(prompt_state)
machine = prompt._build_data_only_prompt_package(prompt_state)
lines = [line for line in machine.splitlines() if line.strip()]
assert len(lines) == 7
job = json.loads(lines[2])
fx_contract = json.loads(lines[4])

assert job["control_only_bindings"] == [
    {
        "source_field": "SCENE_CONTEXT",
        "line": 1,
        "raw": "authored free text without a video",
        "video": "",
        "target_id": "",
        "function": "",
        "marker_color": "",
        "boundary": "",
    },
    {
        "source_field": "SCENE_CONTEXT",
        "line": 2,
        "raw": "@video1 | Target = JettMini_B | Function = emitter",
        "video": "@video1",
        "target_id": "JettMini_B",
        "function": "emitter",
        "marker_color": "",
        "boundary": "",
    },
]
assert fx_contract["schema"] == "hmb-fx-timing-source-facts"
assert fx_contract["version"] == 3
assert set(fx_contract) == {"schema", "version", "sources", "control_bindings"}
source = fx_contract["sources"][0]
assert source == {
    "video": "@video1",
    "video_main_type": "FX Reference",
    "video_sub_type": "FX Effect Only",
    "custom_source_type": "Authored smoke timing reference",
    "role": "FX Effect Only",
    "custom_role": "Use only where explicitly directed",
    "keep_out": "Do not invent extra smoke emitters",
    "range_segments": [],
    "authored_timing_cues": normalized_prompt["videos"][0]["timing_cues"],
    "video_uid": "video-fx-reference",
}
assert source["authored_timing_cues"][1]["cue_type"] == "artist_note"
assert source["authored_timing_cues"][1]["cue_phase"] == "afterglow"
assert source["authored_timing_cues"][1]["frame"] == 999
for forbidden in (
    "valid",
    "errors",
    "validation_codes",
    "role_selected",
    "emitter_binding_declared",
    "range_on",
):
    assert forbidden not in fx_contract
    assert forbidden not in source
assert fx_contract["control_bindings"] == [
    {
        "field": "SCENE_CONTEXT",
        "line": 1,
        "raw": "authored free text without a video",
        "video": 0,
        "target": "",
        "function": "",
        "marker": "",
        "boundary": "",
    },
    {
        "field": "SCENE_CONTEXT",
        "line": 2,
        "raw": "@video1 | Target = JettMini_B | Function = emitter",
        "video": 1,
        "target": "JettMini_B",
        "function": "emitter",
        "marker": "",
        "boundary": "",
    },
]


print("HMB FX/Timing/Range neutral pass-through contract regression: PASS")
