"""Snapshot cursor ordering uses accepted Shot revisions, including native hooks."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hmb_snapshot_navigation_revision", ROOT / "HMBVideoPickerLibrary.py"
)
assert spec is not None and spec.loader is not None
picker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = picker
spec.loader.exec_module(picker)

SHOT_A = "00000000-0000-4000-8000-000000000001"
SHOT_B = "00000000-0000-4000-8000-000000000002"

def snapshot(uid, frame, role):
    return {
        "snapshot_uid": uid, "frame": frame, "artifact_type": role,
        "snapshot_batch_uid": "batch-immutable",
        "path": f"C:/snapshot/{uid}.png",
        "url": f"http://127.0.0.1/snapshot/{uid}.png",
        "sha256": ("a" if uid == "snapshot-a" else "b") * 64,
        "created_at_ms": int(frame),
    }

base = picker._default_widget_state()
row_a = deepcopy(base["picker_shots"][0])
row_a.update({
    "workspace_uuid": SHOT_A, "bound_shot_uuid": SHOT_A, "number": 1,
    "revision": 2,
    "active_snapshot_uid": "snapshot-b", "viewport_mode": "snapshot",
})
row_b = deepcopy(row_a)
row_b.update({
    "workspace_uuid": SHOT_B, "bound_shot_uuid": SHOT_B, "number": 2,
    "revision": 4,
    "active_snapshot_uid": "snapshot-a", "viewport_mode": "video",
})
authoritative = picker._parse_state({
    **base, "state_revision": 11,
    "active_picker_shot_uuid": SHOT_A, "picker_shots": [row_a, row_b],
    "snapshots": [
        snapshot("snapshot-a", 101.0, "mask"),
        snapshot("snapshot-b", 202.0, "depth"),
    ],
    "active_snapshot_uid": "snapshot-b", "viewport_mode": "snapshot",
})
history = deepcopy(authoritative["snapshots"])
assert authoritative["picker_shots"][0]["active_snapshot_uid"] == "snapshot-b"

def stale_echo(global_revision=11, row_revision=1):
    incoming = deepcopy(authoritative)
    incoming.update({
        "state_writer": "widget", "state_revision": global_revision,
        "active_snapshot_uid": "snapshot-a", "viewport_mode": "video",
        "snapshot_path": "C:/snapshot/snapshot-a.png",
        "snapshot_url": "http://127.0.0.1/snapshot/snapshot-a.png",
        "snapshot_frame": 101.0,
    })
    incoming["picker_shots"][0].update({
        "revision": row_revision, "active_snapshot_uid": "snapshot-a",
        "viewport_mode": "video",
    })
    return incoming

def assert_cursor(state, uid, mode):
    assert state["active_snapshot_uid"] == uid
    assert state["viewport_mode"] == mode
    assert state["snapshots"] == history, "Browser echo changed immutable history"
    record = next(item for item in history if item["snapshot_uid"] == uid)
    assert state["snapshot_path"] == record["path"]
    assert state["snapshot_url"] == record["url"]
    assert state["snapshot_frame"] == record["frame"]
    active_row = next(
        row for row in state["picker_shots"]
        if row["workspace_uuid"] == state["active_picker_shot_uuid"]
    )
    assert active_row["active_snapshot_uid"] == uid
    assert active_row["viewport_mode"] == mode

# Delayed same-global edits are distinct from stale backend revision responses.
# An equal row token is an acknowledgement; a higher global token alone cannot
# roll a Shot cursor or view mode back.
for global_revision in (9, 10, 11, 12):
    for row_revision in (1, 2):
        echo = stale_echo(global_revision, row_revision)
        original_echo = deepcopy(echo)
        merged = picker.HMBVideoPickerLibrary._merge_widget_state(
            authoritative, echo
        )
        assert_cursor(merged, "snapshot-b", "snapshot")
        assert echo == original_echo
        assert_cursor(
            picker._parse_state(json.dumps(merged)), "snapshot-b", "snapshot"
        )
        assert_cursor(
            picker.HMBVideoPickerLibrary._merge_widget_state(
                authoritative, json.dumps(echo)
            ), "snapshot-b", "snapshot",
        )

# Genuine navigation increments its Shot token while the backend global token
# can stay unchanged. Its row cursor remains authority even when old scalars
# accompany the widget transaction.
newer = stale_echo(11, 3)
newer["picker_shots"][0]["viewport_mode"] = "snapshot"
newer["viewport_mode"] = "video"
assert_cursor(
    picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, newer),
    "snapshot-a", "snapshot",
)
newer["picker_shots"][0]["viewport_mode"] = "video"
assert_cursor(
    picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, newer),
    "snapshot-a", "video",
)

# Switching Shots restores the destination's committed pointer and mode;
# a global pointer from the source Shot cannot replace equal-token destination.
switch = stale_echo(12, 1)
switch["active_picker_shot_uuid"] = SHOT_B
switch["active_snapshot_uid"] = "snapshot-b"
switch["viewport_mode"] = "snapshot"
assert_cursor(
    picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, switch),
    "snapshot-a", "video",
)

# Empty/malformed modern row payloads cannot downgrade to legacy cursor writes.
for rows in ([], None, {}):
    echo = stale_echo()
    echo["picker_shots"] = rows
    assert_cursor(
        picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, echo),
        "snapshot-b", "snapshot",
    )

# Clients predating Shot rows still author global navigation at current backend
# revisions. Rowless JSON and dict transports have identical compatibility.
legacy = stale_echo()
legacy.pop("picker_shots")
for payload in (legacy, json.dumps(legacy)):
    assert_cursor(
        picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, payload),
        "snapshot-a", "video",
    )
legacy["state_revision"] = 10
assert_cursor(
    picker.HMBVideoPickerLibrary._merge_widget_state(authoritative, legacy),
    "snapshot-b", "snapshot",
)

# Verify the native parameter before/store/after lifecycle too, where early
# normalization previously erased the distinction between rowless and modern.
picker._request_parameter_value = lambda *_args, **_kwargs: False
node = picker.HMBVideoPickerLibrary(name="Snapshot cursor revision regression")
node._sync_outputs_from_state = lambda _state: ""
node._hmb_authoritative_state = deepcopy(authoritative)
node._hmb_latest_widget_state = deepcopy(authoritative)
parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
modern = stale_echo(11, 1)
value = node.before_value_set(parameter, json.dumps(modern))
assert_cursor(value, "snapshot-b", "snapshot")
node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, value)
node.after_value_set(parameter, value)
assert_cursor(node._hmb_authoritative_state, "snapshot-b", "snapshot")

legacy["state_revision"] = 11
value = node.before_value_set(parameter, json.dumps(legacy))
assert_cursor(value, "snapshot-a", "video")
node.set_parameter_value(picker.WIDGET_STATE_PARAMETER, value)
node.after_value_set(parameter, value)
assert_cursor(node._hmb_authoritative_state, "snapshot-a", "video")

print("PASS: Snapshot Shot revision races, canonical media, Shot switching, legacy transport and native lifecycle")
