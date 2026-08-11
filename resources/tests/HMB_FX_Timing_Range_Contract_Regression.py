from __future__ import annotations

import importlib.util
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
assert image_payload["authority_scope"]["schema"] == (
    "hmb-image-source-authority-scope"
)


# Distinct Maya instances of one reusable asset remain distinct. Timing cues
# are accepted only when both an exact frame and emitter instance are valid.
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
            {
                "frame": 999,
                "phase": "peak",
                "emitter": {"maya_uuid": "UUID-A"},
                "local_point": {
                    "kind": "coordinates",
                    "space": "local",
                    "unit": "scene_unit",
                    "xyz": [0, 0, 0],
                },
            },
            {
                "frame": 120,
                "phase": "point",
                "description": "No emitter identity",
                "local_point": {
                    "kind": "coordinates",
                    "space": "local",
                    "unit": "scene_unit",
                    "xyz": [0, 0, 0],
                },
            },
            {
                "frame": 121,
                "phase": "point",
                "emitter": {"maya_uuid": "UUID-A"},
                "description": "Emitter identity without an exact local point",
            },
            {
                "frame": 122,
                "phase": "point",
                "emitter": {"maya_uuid": "UUID-A"},
                "local_point": {
                    "kind": "coordinates",
                    "space": "world",
                    "unit": "scene_unit",
                    "xyz": [0, 0, 0],
                },
            },
            {
                "frame": 123,
                "phase": "point",
                "emitter": {"maya_uuid": "UUID-A"},
                "local_point": {
                    "kind": "coordinates",
                    "space": "local",
                    "xyz": [0, 0, 0],
                },
            },
            {
                "frame": 124.5,
                "phase": "point",
                "emitter": {"maya_uuid": "UUID-A"},
                "local_point": {
                    "kind": "coordinates",
                    "space": "local",
                    "unit": "scene_unit",
                    "xyz": [0, 0, 0],
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
unresolved_cues = picker._normalize_timing_cues(
    [
        {
            "frame": 140,
            "phase": "point",
            "emitter": {"maya_uuid": "UUID-A"},
        }
    ],
    video["markers"],
    video["frame_domain"],
)
assert unresolved_cues == []
assert picker._video_reference_capabilities(
    video["frame_domain"],
    unresolved_cues,
)["exact_emitter_cues"] is False
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


print("HMB FX/Timing/Range typed upstream contract regression: PASS")
