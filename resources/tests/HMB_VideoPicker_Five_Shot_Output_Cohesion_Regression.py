from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hmb_video_picker_five_shot_output_cohesion_regression",
    ROOT / "HMBVideoPickerLibrary.py",
)
assert SPEC is not None and SPEC.loader is not None
picker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = picker
SPEC.loader.exec_module(picker)


PUBLISHER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CHANNEL_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SHOT_UUIDS = [
    f"cccccccc-cccc-4ccc-8ccc-{number:012d}"
    for number in range(1, 6)
]


def build_catalog() -> dict[str, object]:
    shots = [
        {
            "shot_uuid": shot_uuid,
            "number": number,
            "name": f"Shot {number}",
            "revision": number,
        }
        for number, shot_uuid in enumerate(SHOT_UUIDS, start=1)
    ]
    generation = 5
    document = {
        "channel_uuid": CHANNEL_UUID,
        "generation": generation,
        "shots": shots,
    }
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": PUBLISHER_UUID,
        **document,
        "metadata_sha256": picker._sha256_canonical(document),
    }


def row_by_number(state: dict[str, object], number: int) -> dict[str, object]:
    return next(
        row
        for row in state["picker_shots"]
        if isinstance(row, dict) and int(row.get("number") or 0) == number
    )


catalog = build_catalog()
state = picker._default_widget_state()
state.update(
    {
        "shot_publisher_instance_uuid": PUBLISHER_UUID,
        "channel_uuid": CHANNEL_UUID,
        "shot_uuid": SHOT_UUIDS[-1],
        "shot_number": 5,
        "shot_name": "Shot 5",
        "shot_selections": copy.deepcopy(catalog["shots"]),
        "accepted_shot_catalog_publisher_instance_uuid": PUBLISHER_UUID,
        "accepted_shot_catalog_channel_uuid": CHANNEL_UUID,
        "accepted_shot_catalog_generation": catalog["generation"],
        "accepted_shot_catalog_metadata_sha256": catalog["metadata_sha256"],
        "picker_shots": [
            picker._new_picker_workspace_row(
                number,
                bound_shot_uuid=shot_uuid,
                workspace_uuid=picker._picker_workspace_uuid_for_bound_shot(
                    shot_uuid
                ),
            )
            for number, shot_uuid in enumerate(SHOT_UUIDS, start=1)
        ],
    }
)
state["active_picker_shot_uuid"] = state["picker_shots"][-1][
    "workspace_uuid"
]
state = picker._parse_state(state)


with tempfile.TemporaryDirectory(prefix="hmb-picker-output-cohesion-") as temp:
    media_root = Path(temp)
    expected_order_by_shot: dict[int, list[str]] = {}
    expected_media_by_uid: dict[str, str] = {}

    for number in range(1, 6):
        row = row_by_number(state, number)
        workspace_uuid = str(row["workspace_uuid"])
        local_uid = f"shot-{number}-local"
        remote_uid = f"shot-{number}-remote"
        local_path = media_root / f"{local_uid}.mp4"
        local_path.write_bytes(
            b"\x00\x00\x00\x18ftypmp42" + local_uid.encode("ascii")
        )
        stale_project_path = media_root / "missing-project-copy" / local_path.name
        remote_url = f"https://media.example/{remote_uid}.mp4"

        state = picker._append_video_asset(
            state,
            {
                "video_uid": local_uid,
                "source_uid": local_uid,
                "label": f"Shot {number} local fallback",
                "generation_role": "mask",
                "project_video_path": str(stale_project_path),
                "video_path": str(local_path),
                "video_url": f"http://127.0.0.1:1/{local_uid}.mp4",
            },
            picker_shot_uuid=workspace_uuid,
        )
        state = picker._append_video_asset(
            state,
            {
                "video_uid": remote_uid,
                "source_uid": remote_uid,
                "label": f"Shot {number} server media",
                "generation_role": "original",
                "video_url": remote_url,
            },
            picker_shot_uuid=workspace_uuid,
        )

        # Alternate the selected order so a positional or cross-Shot fallback
        # cannot accidentally satisfy every assertion.
        expected_order = (
            [remote_uid, local_uid]
            if number % 2
            else [local_uid, remote_uid]
        )
        target = row_by_number(state, number)
        target["selected_video_uids"] = expected_order
        target["preview_video_uid"] = expected_order[-1]
        target["selected_video_slot"] = len(expected_order)
        target["revision"] = int(target.get("revision") or 0) + 1
        expected_order_by_shot[number] = expected_order
        expected_media_by_uid[local_uid] = str(local_path)
        expected_media_by_uid[remote_uid] = remote_url

    state["active_picker_shot_uuid"] = row_by_number(state, 5)[
        "workspace_uuid"
    ]
    state = picker._activate_picker_workspace_projection(
        state,
        state["active_picker_shot_uuid"],
    )
    assert state is not None
    state["state_revision"] = 77

    # Reproduce a complete workflow serialization boundary before any output
    # is evaluated. UID ownership, order and lexical media values must survive.
    serialized = json.dumps(state, ensure_ascii=False, sort_keys=True)
    restored = picker._parse_state(json.loads(serialized))
    assert int(restored["state_revision"]) == 77
    for number in range(1, 6):
        row = row_by_number(restored, number)
        assert row["selected_video_uids"] == expected_order_by_shot[number]
        assert set(row["selected_video_uids"]).issubset(
            row["video_asset_uids"]
        )

    node = picker.HMBVideoPickerLibrary(
        name="five_shot_output_cohesion_regression"
    )
    node._hmb_shot_catalog_snapshot = copy.deepcopy(catalog)
    node._hmb_shot_route_status = {"ok": True, "code": "ready"}

    # Keep a deliberately conflicting committed state. The publication call's
    # explicit revision must own all three output ports; before the cohesion
    # fix SHOT_PICKER_OUT re-read this conflicting state while PICKER_OUT and
    # VIDEO_OUT used ``restored``.
    conflicting = copy.deepcopy(restored)
    conflicting_row = row_by_number(conflicting, 1)
    conflicting_row["selected_video_uids"] = [
        expected_order_by_shot[1][0]
    ]
    conflicting_row["preview_video_uid"] = expected_order_by_shot[1][0]
    conflicting["state_revision"] = 78
    node._hmb_authoritative_state = copy.deepcopy(conflicting)
    if not isinstance(getattr(node, "parameter_values", None), dict):
        node.parameter_values = {}
    node.parameter_values[picker.WIDGET_STATE_PARAMETER] = copy.deepcopy(
        conflicting
    )

    original_notify = picker._notify_parameter_update
    original_propagate = picker._propagate_parameter_update_to_connections
    original_retire = picker._retire_legacy_video_slot_outputs
    original_reorder = picker._reorder_video_picker_parameters
    try:
        picker._notify_parameter_update = lambda *_args, **_kwargs: None
        picker._propagate_parameter_update_to_connections = (
            lambda *_args, **_kwargs: None
        )
        picker._retire_legacy_video_slot_outputs = lambda _node: None
        picker._reorder_video_picker_parameters = lambda _node: None
        picker_text = node._sync_outputs_from_state(
            restored,
            enforce_media_availability=True,
        )
    finally:
        picker._notify_parameter_update = original_notify
        picker._propagate_parameter_update_to_connections = original_propagate
        picker._retire_legacy_video_slot_outputs = original_retire
        picker._reorder_video_picker_parameters = original_reorder

    active_uids = expected_order_by_shot[5]
    active_media = [expected_media_by_uid[uid] for uid in active_uids]
    assert node.parameter_output_values[picker.VIDEO_OUTPUT_PARAMETER] == active_media
    public_payload = json.loads(picker_text)
    assert public_payload["ordered_video_uids"] == active_uids
    assert [item["video_path"] for item in public_payload["videos"]] == active_media

    snapshot = node._hmb_shot_routing_snapshot(
        state_snapshot=restored,
        probe_cache={},
    )
    assert [shot["number"] for shot in snapshot["shots"]] == [1, 2, 3, 4, 5]
    for shot in snapshot["shots"]:
        number = int(shot["number"])
        expected_uids = expected_order_by_shot[number]
        expected_media = [expected_media_by_uid[uid] for uid in expected_uids]
        assert shot["selected_source_uids"] == expected_uids
        assert shot["picker_payload"]["ordered_video_uids"] == expected_uids
        assert [
            item["video_path"]
            for item in shot["picker_payload"]["videos"]
        ] == expected_media
        assert [
            snapshot["media_by_source_uid"][uid]
            for uid in expected_uids
        ] == expected_media

    expected_global_uid_order = [
        uid
        for number in range(1, 6)
        for uid in expected_order_by_shot[number]
    ]
    assert [
        item["source_uid"] for item in snapshot["ordered_videos"]
    ] == expected_global_uid_order
    assert list(snapshot["media_by_source_uid"]) == expected_global_uid_order
    assert len(snapshot["media_by_source_uid"]) == 10

    expected_descriptors = [
        {
            "source_uid": uid,
            "media_value_sha256": hashlib.sha256(
                expected_media_by_uid[uid].encode("utf-8")
            ).hexdigest(),
        }
        for uid in expected_global_uid_order
    ]
    assert snapshot["media_sha256"] == picker._sha256_canonical(
        {"media_descriptors": expected_descriptors}
    )

    dependency = node.parameter_output_values[
        picker.SHOT_PICKER_OUTPUT_PARAMETER
    ]
    assert dependency == {
        "schema": "hmb-picker-shot-routing-catalog",
        "version": 1,
        "channel_uuid": snapshot["channel_uuid"],
        "generation": snapshot["generation"],
        "metadata_sha256": snapshot["metadata_sha256"],
        "media_sha256": snapshot["media_sha256"],
        "shot_count": 5,
    }


print(
    "HMB VideoPicker five-Shot output cohesion regression: PASS "
    "(save/reload, UID order, local fallback, remote media, one-revision "
    "VIDEO_OUT/PICKER_OUT/SHOT_PICKER_OUT)"
)
