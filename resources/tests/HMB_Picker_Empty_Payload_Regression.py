from pathlib import Path
import importlib.util
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


# An empty catalog has an authoritative zero-selection contract. It does not
# manufacture ten placeholder media rows for Prompt.
picker_node = picker.HMBVideoPickerLibrary(name="empty_picker_payload_regression")
empty_picker_state = picker._default_widget_state()
empty_picker_state.update({
    "active_slot_count": 5,
    "selected_video_slot": 5,
    "videos": [],
})
empty_payload = picker_node._build_picker_payload(empty_picker_state)
assert empty_payload["media_ready"] is False
assert empty_payload["schema_version"] == 5
assert empty_payload["active_slot_count"] == 0
assert empty_payload["selected_video_count"] == 0
assert empty_payload["max_selected_videos"] == 10
assert empty_payload["ordered_video_uids"] == []
assert empty_payload["videos"] == []


# Connecting that semantic payload preserves Prompt's single inactive editor
# row. Because v5 explicitly selected zero videos, this is complete data rather
# than a producer that is still waiting to publish.
base_prompt_state = prompt._default_widget_state()
connected_empty = prompt._apply_picker_payload(
    base_prompt_state,
    empty_payload,
    connected=True,
)
assert len(connected_empty["videos"]) == 1
assert connected_empty["videos"][0]["slot"] == 1
assert connected_empty["videos"][0]["present"] is False
assert connected_empty["picker"]["enabled"] is True
assert connected_empty["picker"]["awaiting_data"] is False
assert connected_empty["picker"]["order_managed"] is True
assert connected_empty["picker"]["selected_video_count"] == 0
assert connected_empty["picker"]["ordered_video_uids"] == []


# A legacy/malformed producer may still publish five placeholder rows and an
# active count of five.  Rows without concrete media paths fail closed too.
placeholder_payload = {
    "schema": "hmb-prompt-library-picker-binding",
    "schema_version": 4,
    "mode": "maya",
    "run_id": "placeholder-only",
    "active_slot_count": 5,
    "videos": [{"video_slot": slot} for slot in range(1, 6)],
    "markers": [{"video_slot": 1, "color": "Red", "asset_id": "Hero"}],
}
connected_placeholders = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    placeholder_payload,
    connected=True,
)
assert len(connected_placeholders["videos"]) == 1
assert connected_placeholders["videos"][0]["present"] is False
assert connected_placeholders["picker"]["awaiting_data"] is True
assert connected_placeholders["picker"]["markers"] == []


# media_ready=False is authoritative and cannot be contradicted by a stale
# path left in the payload.
not_ready_with_stale_path = {
    **placeholder_payload,
    "run_id": "stale-not-ready",
    "media_ready": False,
    "videos": [{"video_slot": 1, "video_path": "C:/stale/never-published.mp4"}],
}
connected_stale = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    not_ready_with_stale_path,
    connected=True,
)
assert len(connected_stale["videos"]) == 1
assert connected_stale["videos"][0]["present"] is False
assert connected_stale["picker"]["awaiting_data"] is True


# Concrete media remains authoritative and preserves the existing five-slot
# lifecycle behavior when five real playblasts were actually produced.
ready_payload = {
    **placeholder_payload,
    "run_id": "five-real-videos",
    "media_ready": True,
    "videos": [
        {
            "video_slot": slot,
            "video_path": f"C:/shots/shot_playblast_{slot}.mp4",
            "camera": "|shotCam",
        }
        for slot in range(1, 6)
    ],
    "markers": [],
}
connected_ready = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    ready_payload,
    connected=True,
)
assert len(connected_ready["videos"]) == 5
assert all(item["present"] for item in connected_ready["videos"])
assert connected_ready["picker"]["awaiting_data"] is False


# Legacy single-video payloads without media_ready remain supported.
legacy_ready = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    {
        "mode": "maya",
        "run_id": "legacy-single",
        "video_slot": 1,
        "video_path": "C:/shots/legacy_playblast.mp4",
        "camera": "|shotCam",
    },
    connected=True,
)
assert len(legacy_ready["videos"]) == 1
assert legacy_ready["videos"][0]["present"] is True
assert legacy_ready["videos"][0]["label"] == "legacy_playblast"


print("HMB Picker empty/placeholder payload fail-closed regression: PASS")
