from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "HMBVideoPickerLibrary.py"
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_media_availability_regression",
    TARGET,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load regression target: {TARGET}")
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


def selected_item(uid: str, order: int, **values: str) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "label": values.pop("label", uid),
        "selected": True,
        "selection_order": order,
        "source_fps": 24.0,
        "decoded_frame_count": 24,
        **values,
    }


with tempfile.TemporaryDirectory() as temporary:
    temporary_path = Path(temporary)
    local_video = temporary_path / "verified-local.mp4"
    local_video.write_bytes(b"\x00\x00\x00\x18ftypmp42verified-local")

    # Explicit filesystem paths are authorities in their own right and must
    # not be reinterpreted as active-project-relative paths.
    resolved_absolute = picker._resolve_readable_video_reference(str(local_video))
    assert resolved_absolute is not None
    assert resolved_absolute.resolve() == local_video.resolve()

    # A valid project macro remains the emitted authority, not its expanded
    # machine-specific path.
    project_macro = "inputs/videos/verified-project.mp4"
    original_resolver = picker._resolve_readable_video_reference
    try:
        picker._resolve_readable_video_reference = (
            lambda value: local_video if value == project_macro else None
        )
        project_payload, project_media = picker._build_synchronized_video_outputs(
            {
                "videos": [
                    selected_item(
                        "project-video",
                        1,
                        project_video_path=project_macro,
                        video_path=str(local_video),
                    )
                ]
            },
            enforce_media_availability=True,
        )
    finally:
        picker._resolve_readable_video_reference = original_resolver
    assert project_media == [project_macro]
    assert project_payload["videos"][0]["video_path"] == project_macro

    # If only the project copy is stale, the verified source file takes over
    # and stale project metadata is not exposed downstream.
    original_resolver = picker._resolve_readable_video_reference
    try:
        picker._resolve_readable_video_reference = (
            lambda value: local_video if value == str(local_video) else None
        )
        fallback_payload, fallback_media = picker._build_synchronized_video_outputs(
            {
                "videos": [
                    selected_item(
                        "fallback-video",
                        1,
                        project_video_path="inputs/videos/missing-project-copy.mp4",
                        video_path=str(local_video),
                        video_url="http://127.0.0.1:8123/external/stale-preview.mp4",
                    )
                ]
            },
            enforce_media_availability=True,
        )
    finally:
        picker._resolve_readable_video_reference = original_resolver
    assert len(fallback_media) == 1
    assert Path(fallback_media[0]).resolve() == local_video.resolve()
    assert fallback_payload["videos"][0]["video_path"] == fallback_media[0]
    assert "project_video_path" not in fallback_payload["videos"][0]

    # One missing member blocks the entire ordered selection. Valid members
    # cannot be silently renumbered into a materially different generation.
    blocked_state = {
        "videos": [
            selected_item(
                "valid-url",
                1,
                video_url="https://cdn.example/valid-reference.mp4",
            ),
            selected_item(
                "missing-local",
                2,
                label="Missing Playblast",
                project_video_path="inputs/videos/missing-project.mp4",
                video_path=str(temporary_path / "missing-local.mp4"),
                video_url="http://127.0.0.1:8123/external/missing-local.mp4",
            ),
        ]
    }
    blocked_payload, blocked_media = picker._build_synchronized_video_outputs(
        blocked_state,
        enforce_media_availability=True,
    )
    assert blocked_media == []
    assert blocked_payload["media_ready"] is False
    assert blocked_payload["media_blocked"] is True
    assert blocked_payload["videos"] == []
    assert blocked_payload["unavailable_video_uids"] == ["missing-local"]
    assert blocked_payload["blocking_error_code"] == "LOCAL_REFERENCE_MISSING"
    assert "Missing Playblast" in blocked_payload["blocking_error"]

    node = picker.HMBVideoPickerLibrary(
        name="video_picker_media_availability_regression"
    )
    try:
        node._sync_outputs_from_state(blocked_state)
    except RuntimeError as exc:
        assert "Missing Playblast" in str(exc)
        assert "Re-import the MP4" in str(exc)
    else:
        raise AssertionError("Missing selected media was published")
    assert node.parameter_output_values[picker.VIDEO_OUTPUT_PARAMETER] == []
    published_block = json.loads(node.parameter_output_values["PICKER_OUT"])
    assert published_block["media_blocked"] is True
    assert published_block["videos"] == []

    # URL-only references do not depend on the active project's filesystem.
    remote_payload, remote_media = picker._build_synchronized_video_outputs(
        {
            "videos": [
                selected_item(
                    "https-video",
                    1,
                    video_url="https://cdn.example/reference.mp4",
                ),
                selected_item(
                    "asset-video",
                    2,
                    video_url="asset://volcengine/reference-id",
                ),
            ]
        },
        enforce_media_availability=True,
    )
    assert remote_media == [
        "https://cdn.example/reference.mp4",
        "asset://volcengine/reference-id",
    ]
    assert remote_payload.get("media_blocked") is None

empty_payload, empty_media = picker._build_synchronized_video_outputs(
    {"videos": []},
    enforce_media_availability=True,
)
assert empty_media == []
assert empty_payload["media_ready"] is False
assert empty_payload.get("media_blocked") is None

print("HMB VideoPicker media availability fail-closed regression: PASS")
