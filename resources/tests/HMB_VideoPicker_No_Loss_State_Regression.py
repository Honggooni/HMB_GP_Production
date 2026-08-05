from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker  # noqa: E402


binding_node = object.__new__(picker.HMBVideoPickerLibrary)
assert binding_node._selected_slot_job_bindings({
    "active_slot_count": 1,
    "slot_assignments": [{
        "video_slot": 1,
        "bindings": [{
            "group_name": "ReadableButUnassigned",
            "full_dag_path": "|ReadableButUnassigned",
            "color": "",
            "enabled": True,
        }],
    }],
}, 1) == []


expanded = picker._parse_state({
    "active_slot_count": 1,
    "videos": [
        {"video_slot": 1, "video_path": "C:/media/manual-color.mp4"},
        {"video_slot": 2, "video_path": "C:/media/manual-depth.mp4"},
    ],
    "slot_assignments": [{
        "video_slot": 3,
        "bindings": [{
            "group_name": "Actor",
            "full_dag_path": "|Actor",
            "color": "Red",
        }],
    }],
    "slot_visibility": [{
        "video_slot": 4,
        "hidden_paths": ["|HiddenA"],
    }],
    "snapshots": [{
        "video_slot": 5,
        "frame": 101,
        "data_uri": "data:image/png;base64,AA==",
        "path": "C:/media/snapshot.png",
    }],
})
# Snapshot render slots are immutable authoring metadata, not current catalog
# positions. They therefore never expand or reorder selected video cards.
assert expanded["active_slot_count"] == 2
assert [(item["video_slot"], item["video_path"]) for item in expanded["videos"]] == [
    (1, "C:/media/manual-color.mp4"),
    (2, "C:/media/manual-depth.mp4"),
]
assert expanded["slot_assignments"][1]["bindings"][0]["full_dag_path"] == "|Actor"
assert expanded["slot_visibility"][1]["hidden_paths"] == ["|HiddenA"]
assert expanded["snapshots"][0]["video_slot"] == 5
assert expanded["snapshots"][0]["snapshot_uid"].startswith("snapshot-legacy-")


duplicate_videos = picker._parse_state({
    "active_slot_count": 1,
    "videos": [
        {"video_slot": 1, "video_path": "C:/media/first.mp4"},
        {"video_slot": 1, "video_path": "C:/media/second.mp4"},
    ],
})
assert duplicate_videos["active_slot_count"] == 2
assert [(item["video_slot"], item["video_path"]) for item in duplicate_videos["videos"]] == [
    (1, "C:/media/first.mp4"),
    (2, "C:/media/second.mp4"),
]
assert len({item["video_uid"] for item in duplicate_videos["videos"]}) == 2
assert all(item["legacy_video_slot"] == 1 for item in duplicate_videos["videos"])


duplicate_with_authored_control = picker._parse_state({
    "active_slot_count": 2,
    "videos": [
        {"video_slot": 1, "video_path": "C:/media/first.mp4"},
        {"video_slot": 1, "video_path": "C:/media/second.mp4"},
    ],
    "slot_assignments": [{
        "video_slot": 2,
        "bindings": [{"group_name": "Reserved", "color": "Red"}],
    }],
})
assert duplicate_with_authored_control["active_slot_count"] == 2
assert [item["video_slot"] for item in duplicate_with_authored_control["videos"]] == [1, 2]
assert duplicate_with_authored_control["slot_assignments"][1]["bindings"][0]["group_name"] == "Reserved"


merged_controls = picker._parse_state({
    "active_slot_count": 1,
    "slot_assignments": [
        {"video_slot": 1, "bindings": [{"group_name": "A", "color": "Red"}]},
        {"video_slot": 1, "bindings": [{"group_name": "B", "color": "Green"}]},
    ],
    "slot_visibility": [
        {"video_slot": 1, "hidden_paths": ["|A"]},
        {"video_slot": 1, "hidden_paths": ["|B", "|A"]},
    ],
    "snapshots": [
        {"video_slot": 1, "frame": 1, "data_uri": "data:image/png;base64,AA=="},
        {"video_slot": 1, "frame": 2, "data_uri": "data:image/png;base64,BB=="},
    ],
})
assert [item["group_name"] for item in merged_controls["slot_assignments"][0]["bindings"]] == ["A", "B"]
assert merged_controls["slot_visibility"][0]["hidden_paths"] == ["|A", "|B"]
assert [item["frame"] for item in merged_controls["snapshots"]] == [1, 2]
assert len({item["snapshot_uid"] for item in merged_controls["snapshots"]}) == 2
assert all(
    item["snapshot_uid"].startswith("snapshot-legacy-")
    for item in merged_controls["snapshots"]
)


overflow = picker._parse_state({
    "active_slot_count": 1,
    "videos": [
        {"video_slot": 1, "video_path": f"C:/media/duplicate-{index}.mp4"}
        for index in range(1, 7)
    ],
})
assert overflow["active_slot_count"] == 6
assert len(overflow["videos"]) == 6
assert {item["video_slot"] for item in overflow["videos"]} == {1, 2, 3, 4, 5, 6}


project_only_payload = picker.HMBVideoPickerLibrary._build_picker_payload(None, {
    "active_slot_count": 1,
    "videos": [{
        "video_slot": 1,
        "project_video_path": "projects/shot/media/project-only.mp4",
    }],
})
assert project_only_payload["media_ready"] is True
assert project_only_payload["videos"][0]["video_path"] == "projects/shot/media/project-only.mp4"
assert project_only_payload["videos"][0]["project_video_path"] == "projects/shot/media/project-only.mp4"

local_path_wins = picker.HMBVideoPickerLibrary._build_picker_payload(None, {
    "active_slot_count": 1,
    "videos": [{
        "video_slot": 1,
        "video_path": "C:/media/local.mp4",
        "project_video_path": "projects/shot/media/project.mp4",
    }],
})
assert local_path_wins["videos"][0]["video_path"] == "projects/shot/media/project.mp4"
assert local_path_wins["videos"][0]["local_video_path"] == "C:/media/local.mp4"
assert local_path_wins["videos"][0]["project_video_path"] == "projects/shot/media/project.mp4"


print("HMB VideoPicker no-loss state recovery regression: PASS")
