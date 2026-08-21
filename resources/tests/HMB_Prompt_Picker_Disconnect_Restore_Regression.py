from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "HMBPromptLibrary.py"
spec = importlib.util.spec_from_file_location(
    "_hmb_prompt_picker_disconnect_restore_regression",
    PROMPT_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load {PROMPT_PATH}")
prompt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prompt
spec.loader.exec_module(prompt)


def uid_payload(
    ordered_uids: tuple[str, ...],
    *,
    marker_asset_id: str = "",
    marker_color: str = "Red",
) -> dict[str, Any]:
    videos = []
    markers = []
    for slot, uid in enumerate(ordered_uids, start=1):
        row_markers = []
        if marker_asset_id and slot == 1:
            marker = {
                "asset_id": marker_asset_id,
                "group_name": marker_asset_id,
                "subject_root": f"|{marker_asset_id}",
                "full_dag_path": f"|{marker_asset_id}",
                "maya_uuid": f"{marker_asset_id}-uuid",
                "color": marker_color,
                "video_uid": uid,
                "source_uid": uid,
                "video_slot": slot,
                "picker_order": 1,
            }
            row_markers.append(marker)
            markers.append(copy.deepcopy(marker))
        videos.append(
            {
                "video_uid": uid,
                "source_uid": uid,
                "order_key": uid,
                "selected": True,
                "selection_order": slot,
                "video_slot": slot,
                "video_path": f"https://example.test/{uid}.mp4",
                "markers": row_markers,
            }
        )
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": bool(videos),
        "active_slot_count": len(videos),
        "selected_video_count": len(videos),
        "selection_id": "selection-" + "-".join(ordered_uids),
        "ordered_video_uids": list(ordered_uids),
        "videos": videos,
        "markers": markers,
    }


def empty_uid_payload() -> dict[str, Any]:
    return {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": False,
        "active_slot_count": 0,
        "selected_video_count": 0,
        "selection_id": "selection-empty",
        "ordered_video_uids": [],
        "videos": [],
        "markers": [],
    }


def legacy_payload(*, media: bool, marker: bool = False) -> dict[str, Any]:
    video = (
        {
            "video_slot": 1,
            "video_path": "https://example.test/legacy.mp4",
            "selected": True,
        }
        if media
        else {}
    )
    markers = (
        [
            {
                "asset_id": "legacy-asset",
                "group_name": "legacy-asset",
                "color": "Red",
                "video_slot": 1,
            }
        ]
        if marker
        else []
    )
    result = {
        "schema": "hmb-prompt-library-picker-binding",
        "schema_version": 5,
        "mode": "maya",
        "media_ready": media,
        "videos": [video],
        "markers": markers,
    }
    if media:
        result["active_slot_count"] = 1
        result["selected_video_count"] = 1
    return result


# Python and widget transport reject the same non-integral/bool context versions.
snapshot = prompt._manual_video_context_snapshot(prompt._default_widget_state())
valid_context = {
    "version": 1,
    "before": snapshot,
    "after": snapshot,
}
assert prompt._normalize_manual_video_context(valid_context)["version"] == 1
for invalid_version in ("1", True, 1.0, None, 2):
    malformed = copy.deepcopy(valid_context)
    malformed["version"] = invalid_version
    assert prompt._normalize_manual_video_context(malformed) == {}


# Picker-authored marker fields are part of the automatic baseline and return
# to the exact pre-connection values on a true disconnect.
marker_base = prompt._default_widget_state()
marker_base["images"][0].update(
    {
        "present": True,
        "label": "hero.png",
        "asset_id": "hero",
        "asset_source_uid": "hero-source",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "color_picks": [""],
        "binding_video_slots": [1],
    }
)
marker_original = copy.deepcopy(prompt._normalize_state(marker_base)["images"][0])
marker_live = prompt._apply_picker_payload(
    marker_base,
    uid_payload(("marker-video",), marker_asset_id="hero"),
    connected=True,
)
context_after = marker_live["picker"][prompt.MANUAL_VIDEO_CONTEXT_KEY]["after"]
context_record = prompt._manual_video_context_image_records(context_after)[
    ("identity", "uid:hero-source")
]
for field in (
    "color_picks",
    "binding_video_slots",
    "marker_video",
    "picker_auto_video",
    "picker_auto_color",
    "picker_auto_source",
):
    assert context_record["fields"][field] == marker_live["images"][0][field]
marker_disconnected = prompt._apply_picker_payload(
    copy.deepcopy(marker_live),
    {},
    connected=False,
)
for field in prompt._MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS:
    assert marker_disconnected["images"][0][field] == marker_original[field]

# A tracked field changed by the user while connected is not rolled back, while
# untouched Picker provenance still returns to its pre-connection value.
user_marker_edit = copy.deepcopy(marker_live)
user_marker_edit["images"][0]["color_picks"] = ["Blue"]
user_marker_disconnected = prompt._apply_picker_payload(
    user_marker_edit,
    {},
    connected=False,
)
assert user_marker_disconnected["images"][0]["color_picks"] == ["Blue"]
assert user_marker_disconnected["images"][0]["picker_auto_color"] == ""
assert user_marker_disconnected["images"][0]["picker_auto_video"] == 0


# selected=0 produces only a transient visible placeholder. It never joins the
# immutable manual cache, including a TEMP edit that cannot occur through the
# locked connected UI.
default_empty = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    empty_uid_payload(),
    connected=True,
)
assert default_empty["picker"]["dormant_manual_rows"] == []
default_selected = prompt._apply_picker_payload(
    copy.deepcopy(default_empty),
    uid_payload(("selected-after-empty",)),
    connected=True,
)
assert default_selected["picker"]["dormant_manual_rows"] == []
default_disconnect = prompt._apply_picker_payload(
    copy.deepcopy(default_selected),
    {},
    connected=False,
)
expected_default_videos = prompt._normalize_state(
    prompt._default_widget_state()
)["videos"]
assert default_disconnect["videos"] == expected_default_videos, (
    default_disconnect["videos"],
    expected_default_videos,
)

old_manual = prompt._default_widget_state()
old_manual["videos"][0]["keep_out"] = "OLD"
old_empty = prompt._apply_picker_payload(
    old_manual,
    empty_uid_payload(),
    connected=True,
)
old_empty["videos"][0]["keep_out"] = "TEMP"
old_selected = prompt._apply_picker_payload(
    copy.deepcopy(old_empty),
    uid_payload(("selected-after-old",)),
    connected=True,
)
assert len(old_selected["picker"]["dormant_manual_rows"]) == 1
old_disconnect = prompt._apply_picker_payload(
    copy.deepcopy(old_selected),
    {},
    connected=False,
)
assert len(old_disconnect["videos"]) == 1
assert old_disconnect["videos"][0]["keep_out"] == "OLD"


# Stable image identity, not list index, owns three-way restoration when both
# ImageAsset and Picker reorder while connected.
reorder_base = prompt._default_widget_state()
reorder_base["videos"] = [
    {
        **prompt._default_video_item(1),
        "present": True,
        "label": "old-one.mp4",
    },
    {
        **prompt._default_video_item(2),
        "present": True,
        "label": "old-two.mp4",
        "manual": True,
    },
]
reorder_base["images"] = [
    {
        **prompt._default_image_item(1),
        "present": True,
        "asset_id": "asset-a",
        "asset_source_uid": "source-a",
        "color_picks": ["Red"],
        "binding_video_slots": [1],
    },
    {
        **prompt._default_image_item(2),
        "present": True,
        "asset_id": "asset-b",
        "asset_source_uid": "source-b",
        "color_picks": ["Green"],
        "binding_video_slots": [2],
    },
]
reorder_live = prompt._apply_picker_payload(
    reorder_base,
    uid_payload(("uid-a", "uid-b")),
    connected=True,
)
reorder_live["images"] = list(reversed(reorder_live["images"]))
reorder_live = prompt._apply_picker_payload(
    reorder_live,
    uid_payload(("uid-b", "uid-a")),
    connected=True,
)
reorder_disconnect = prompt._apply_picker_payload(
    reorder_live,
    {},
    connected=False,
)
bindings_by_source = {
    item["asset_source_uid"]: item["binding_video_slots"]
    for item in reorder_disconnect["images"]
}
assert bindings_by_source == {"source-a": [1], "source-b": [2]}


# Dormant UID rows retain their prior transient order solely to remap their own
# text on reconnect; the restored manual rows must not map those references to
# zero and replace them with a deselected diagnostic.
reconnect_base = prompt._default_widget_state()
reconnect_base["videos"] = [
    {
        **prompt._default_video_item(1),
        "present": True,
        "label": "manual-one.mp4",
    },
    {
        **prompt._default_video_item(2),
        "present": True,
        "label": "manual-two.mp4",
        "manual": True,
    },
]
reconnect_live = prompt._apply_picker_payload(
    reconnect_base,
    uid_payload(("reconnect-u1", "reconnect-u2")),
    connected=True,
)
reconnect_live["videos"][0]["keep_out"] = "Use @video2 only"
reconnect_disconnected = prompt._apply_picker_payload(
    reconnect_live,
    {},
    connected=False,
)
reconnect_same = prompt._apply_picker_payload(
    reconnect_disconnected,
    uid_payload(("reconnect-u1", "reconnect-u2")),
    connected=True,
)
assert reconnect_same["videos"][0]["keep_out"] == "Use @video2 only"


# A readable but empty legacy placeholder may mark the edge enabled before the
# first real no-UID media payload. Snapshot on first real media, not on enabled.
legacy_base = prompt._default_widget_state()
legacy_base["images"][0].update(
    {
        "present": True,
        "asset_id": "legacy-asset",
        "asset_source_uid": "legacy-source",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "color_picks": [""],
    }
)
legacy_placeholder = prompt._apply_picker_payload(
    legacy_base,
    legacy_payload(media=False),
    connected=True,
)
assert legacy_placeholder["picker"][prompt.MANUAL_VIDEO_CONTEXT_KEY] == {}
legacy_live = prompt._apply_picker_payload(
    legacy_placeholder,
    legacy_payload(media=True, marker=True),
    connected=True,
)
assert legacy_live["images"][0]["color_picks"] == ["Red"]
assert legacy_live["picker"][prompt.MANUAL_VIDEO_CONTEXT_KEY]
legacy_disconnect = prompt._apply_picker_payload(
    legacy_live,
    {},
    connected=False,
)
assert legacy_disconnect["images"][0]["color_picks"] == [""]
assert legacy_disconnect["images"][0]["picker_auto_color"] == ""


print("HMB Prompt Picker disconnect/manual restore regression: PASS")
