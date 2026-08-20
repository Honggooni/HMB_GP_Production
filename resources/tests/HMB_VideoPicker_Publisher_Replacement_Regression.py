from __future__ import annotations

import copy
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker  # noqa: E402


def video(uid: str, order: int) -> dict:
    return {
        "video_uid": uid,
        "source_uid": uid,
        "label": uid,
        "video_url": f"https://example.test/{uid}.mp4",
        "catalog_order": order,
        "selected": False,
        "selection_order": 0,
        "video_slot": 0,
        "source_fps": 24.0,
        "decoded_frame_count": 24,
        "source_duration_seconds": 1.0,
    }


def catalog(channel: str, publisher: str, shots: list[str]) -> dict:
    rows = [
        {
            "shot_uuid": shot_uuid,
            "number": number,
            "name": f"Shot {number}",
            "revision": 1,
        }
        for number, shot_uuid in enumerate(shots, start=1)
    ]
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": 1,
        "metadata_sha256": picker._sha256_canonical(
            {
                "channel_uuid": channel,
                "generation": 1,
                "shots": rows,
            }
        ),
        "shots": rows,
    }


node = picker.HMBVideoPickerLibrary(name="VideoPicker Publisher Replacement")


def write_local(value: dict) -> None:
    normalized = picker._parse_state(value)
    node._hmb_authoritative_state = copy.deepcopy(normalized)
    node._hmb_latest_widget_state = copy.deepcopy(normalized)
    node._hmb_state_revision = int(normalized.get("state_revision") or 0)


node._write_state = write_local
node._sync_outputs_from_state = lambda _value: None

old_channel = str(uuid.uuid4())
old_publisher = str(uuid.uuid4())
old_shots = [str(uuid.uuid4()) for _ in range(3)]
new_channel = str(uuid.uuid4())
new_publisher = str(uuid.uuid4())
new_shots = [str(uuid.uuid4()) for _ in range(3)]

node._hmb_authoritative_state = picker._parse_state(
    {
        **node._picker_state(),
        "videos": [video(f"video-{number}", number) for number in range(1, 4)],
        "channel_uuid": "",
        "shot_uuid": "",
        "shot_selections": [],
    }
)
node._hmb_reconcile_shot_routing(catalog(old_channel, old_publisher, old_shots))

owned = copy.deepcopy(node._picker_state())
for number, row in enumerate(owned["picker_shots"], start=1):
    uid = f"video-{number}"
    row["video_asset_uids"] = [uid]
    row["selected_video_uids"] = [uid]
    row["preview_video_uid"] = uid
    item = next(value for value in owned["videos"] if value["video_uid"] == uid)
    item["picker_shot_uuid"] = row["workspace_uuid"]
node._write_state(owned)

before = copy.deepcopy(node._picker_state())
workspace_ids = [row["workspace_uuid"] for row in before["picker_shots"]]
memberships = [list(row["selected_video_uids"]) for row in before["picker_shots"]]
# The host can reconcile the deletion before the replacement node is dragged.
# Only the remote quartet is cleared; the accepted watermark and authored
# workspaces remain the exact replacement evidence.
node._hmb_clear_shot_routing_catalog("publisher_unavailable")
cleared = node._picker_state()
assert [row["workspace_uuid"] for row in cleared["picker_shots"]] == workspace_ids
assert [item["video_uid"] for item in cleared["videos"]] == [
    "video-1",
    "video-2",
    "video-3",
]
node._hmb_reconcile_replacement_shot_routing(
    catalog(new_channel, new_publisher, new_shots)
)
after = node._picker_state()

assert after["channel_uuid"] == new_channel
assert after["shot_publisher_instance_uuid"] == new_publisher
assert [row["bound_shot_uuid"] for row in after["picker_shots"]] == new_shots
assert [row["workspace_uuid"] for row in after["picker_shots"]] == workspace_ids
assert [row["selected_video_uids"] for row in after["picker_shots"]] == memberships
assert [item["video_uid"] for item in after["videos"]] == [
    "video-1",
    "video-2",
    "video-3",
]

# A replacement with a different shape is not a license to map by a coincident
# display number.  It fails closed while every authored workspace/media record
# remains recoverable.
mismatch_channel = str(uuid.uuid4())
mismatch_publisher = str(uuid.uuid4())
mismatch_shots = [str(uuid.uuid4()) for _ in range(2)]
try:
    node._hmb_reconcile_replacement_shot_routing(
        catalog(mismatch_channel, mismatch_publisher, mismatch_shots)
    )
except ValueError as exc:
    assert "ambiguous" in str(exc)
else:
    raise AssertionError("Ambiguous replacement shape was accepted.")

preserved = node._picker_state()
assert [row["workspace_uuid"] for row in preserved["picker_shots"]] == workspace_ids
assert [row["selected_video_uids"] for row in preserved["picker_shots"]] == memberships
assert [item["video_uid"] for item in preserved["videos"]] == [
    "video-1",
    "video-2",
    "video-3",
]

print(
    "HMB VideoPicker publisher replacement regression: PASS "
    "(exact-shape migration preserves workspaces/media; ambiguous shape fails closed)"
)
