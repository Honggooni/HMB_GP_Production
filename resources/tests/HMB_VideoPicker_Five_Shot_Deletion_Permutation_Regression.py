from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import pickle
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str) -> Any:
    path = ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {filename}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load_module(
    "HMBVideoPickerLibrary_five_shot_deletion_permutation",
    "HMBVideoPickerLibrary.py",
)


PUBLISHER_UUID = "10000000-0000-4000-8000-000000000001"
CHANNEL_UUID = "20000000-0000-4000-8000-000000000002"
SHOT_UUIDS = tuple(
    f"30000000-0000-4000-8000-{number:012d}"
    for number in range(1, 6)
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def first_difference(left: Any, right: Any, path: str = "$") -> str:
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys {sorted(set(left) ^ set(right))}"
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return ""
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            difference = first_difference(
                left_item,
                right_item,
                f"{path}[{index}]",
            )
            if difference:
                return difference
        return ""
    return "" if left == right else f"{path}: {left!r} != {right!r}"


def shot_catalog(shot_uuids: list[str], generation: int) -> dict[str, Any]:
    shots = [
        {
            "shot_uuid": shot_uuid,
            "number": number,
            "name": f"Shot {number}",
            "revision": generation,
        }
        for number, shot_uuid in enumerate(shot_uuids, start=1)
    ]
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
        "metadata_sha256": hashlib.sha256(canonical_bytes(document)).hexdigest(),
    }


def configure_memory_node(node: Any, state: Any | None = None) -> Any:
    normalized = picker._parse_state(
        state if state is not None else node._picker_state()
    )
    node.parameter_values = {
        picker.WIDGET_STATE_PARAMETER: copy.deepcopy(normalized),
    }
    node.get_parameter_value = lambda name: node.parameter_values.get(name)
    node._hmb_authoritative_state = copy.deepcopy(normalized)
    node._hmb_latest_widget_state = copy.deepcopy(normalized)
    node._sync_outputs_from_state = lambda _state: None
    node._ensure_parameters = lambda: None
    node._schedule_post_hydration_shot_reconcile = lambda: None

    def write_state(next_state: Any) -> None:
        parsed = picker._parse_state(next_state)
        node.parameter_values[picker.WIDGET_STATE_PARAMETER] = copy.deepcopy(parsed)
        node._hmb_authoritative_state = copy.deepcopy(parsed)
        node._hmb_latest_widget_state = copy.deepcopy(parsed)

    node._write_state = write_state
    return node


def state_rows(state: Any) -> list[dict[str, Any]]:
    return sorted(
        [
            row
            for row in picker._parse_state(state).get("picker_shots", [])
            if isinstance(row, dict)
        ],
        key=lambda row: int(row.get("number") or 0),
    )


def video_uids_for_shot(number: int) -> list[str]:
    return [f"shot-{number}-video-{index}" for index in range(1, number + 1)]


def append_shot_videos(
    state: Any,
    shot_number: int,
    media_root: Path,
) -> dict[str, Any]:
    normalized = picker._parse_state(state)
    row = next(
        row
        for row in state_rows(normalized)
        if int(row.get("number") or 0) == shot_number
    )
    for index, uid in enumerate(video_uids_for_shot(shot_number), start=1):
        media_path = media_root / f"{uid}.mp4"
        media_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + uid.encode("ascii"))
        normalized = picker._append_video_asset(
            normalized,
            {
                "video_uid": uid,
                "source_uid": uid,
                "label": uid.replace("-", " ").title(),
                "generation_role": "imported",
                "media_kind": "maya_preview",
                "source_type": "Maya Preview",
                "source_subtype": f"Shot {shot_number}",
                "video_path": str(media_path.resolve()),
                "project_video_path": str(media_path.resolve()),
                "import_source_path": str(media_path.resolve()),
                "video_url": (
                    f"http://127.0.0.1:8787/external/{media_path.name}"
                ),
                "created_at_ms": shot_number * 1000 + index,
                "camera": f"camera{shot_number}",
                "decoded_fps": float(24 + shot_number),
                "output_fps": float(24 + shot_number),
                "decoded_frame_count": 100 + shot_number,
                "output_frame_count": 100 + shot_number,
                "output_width": 1280,
                "output_height": 720,
                "has_maya_frame_range": True,
                "maya_start_frame": 101,
                "maya_end_frame": 200 + shot_number,
            },
            picker_shot_uuid=row["workspace_uuid"],
        )
    return normalized


def install_distinct_authoring_contexts(state: Any) -> dict[str, Any]:
    normalized = picker._parse_state(state)
    videos_by_uid = {
        str(item.get("video_uid") or item.get("source_uid") or ""): item
        for item in normalized.get("videos", [])
        if isinstance(item, dict)
    }
    rows = sorted(
        [
            row
            for row in normalized.get("picker_shots", [])
            if isinstance(row, dict)
        ],
        key=lambda row: int(row.get("number") or 0),
    )
    for number, row in enumerate(rows, start=1):
        preview_item = videos_by_uid[row["preview_video_uid"]]
        context = picker._empty_picker_authoring_context()
        context.update({
            "scene_request_status": f"SHOT_{number}_READY",
            "native_read_ready": True,
            "native_read_mode": f"shot-{number}-mode",
            "camera": f"camera{number}",
            "selected_camera": f"camera{number}",
            "cameras": [{
                "name": f"camera{number}",
                "full_path": f"|camera{number}",
                "default_camera": False,
            }],
            "source_fps": float(20 + number),
            "output_fps": float(24 + number),
            "output_frame_count": float(100 + number),
            "decoded_frame_count": float(100 + number),
            "current_frame": float(number * 10),
            "frame_metadata": picker._video_frame_metadata(
                preview_item,
                number,
            ),
            "workspace_view": "outliner",
            "selected_outliner_path": f"|shot{number}|character",
            "selected_outliner_name": f"character{number}",
            "selected_color": f"color-{number}",
            "slot_assignments": [
                {
                    "video_slot": slot,
                    "bindings": [{
                        "group_name": f"character{number}",
                        "full_dag_path": f"|shot{number}|slot{slot}",
                        "maya_uuid": "",
                        "reference_node": "",
                        "reference_file": "",
                        "proxy_manager": "",
                        "proxy_tag": "",
                        "color": "Red",
                        "enabled": True,
                        "video_slot": slot,
                        "picker_order": 1,
                    }],
                }
                for slot in range(1, number + 1)
            ],
            "slot_visibility": [
                {"video_slot": slot, "hidden_paths": []}
                for slot in range(1, number + 1)
            ],
            "status": "READY",
            "message": f"Shot {number} authoring context",
        })
        row["authoring_context"] = picker._normalize_picker_authoring_context(
            context
        )
        row["current_frame"] = float(number * 10)
        row["selected_video_slot"] = number
    normalized["picker_shots"] = rows
    return normalized


def row_durable_semantics(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(row.get(key))
        for key in (
            "workspace_uuid",
            "bound_shot_uuid",
            "video_asset_uids",
            "selected_video_uids",
            "preview_video_uid",
            "scene_draft_path",
            "current_frame",
            "viewport_mode",
            "active_snapshot_uid",
            "selected_video_slot",
            "authoring_context",
        )
    }


def media_semantics(
    state: dict[str, Any],
    owned_uids: set[str],
) -> dict[str, dict[str, Any]]:
    fields = (
        "video_uid",
        "source_uid",
        "label",
        "generation_role",
        "media_kind",
        "source_type",
        "source_subtype",
        "video_path",
        "project_video_path",
        "import_source_path",
        "video_url",
        "created_at_ms",
        "picker_shot_uuid",
    )
    result: dict[str, dict[str, Any]] = {}
    for raw in state.get("videos", []):
        if not isinstance(raw, dict):
            continue
        uid = str(raw.get("video_uid") or raw.get("source_uid") or "")
        if uid in owned_uids:
            result[uid] = {
                key: copy.deepcopy(raw.get(key))
                for key in fields
            }
    return result


def active_bound_uuid(state: dict[str, Any]) -> str:
    active_workspace_uuid = str(state.get("active_picker_shot_uuid") or "")
    return next(
        str(row.get("bound_shot_uuid") or "")
        for row in state_rows(state)
        if str(row.get("workspace_uuid") or "") == active_workspace_uuid
    )


def assert_serializable(state: dict[str, Any]) -> None:
    encoded = canonical_bytes(state)
    assert json.loads(encoded.decode("utf-8")) == state
    pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)


permutation_count = 0
deletion_transition_count = 0
active_deletion_count = 0
non_active_deletion_count = 0

with tempfile.TemporaryDirectory(
    prefix="hmb-picker-five-shot-delete-permutations-"
) as temporary:
    media_root = Path(temporary)
    original_request_parameter_value = picker._request_parameter_value
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        for deletion_order in itertools.permutations(SHOT_UUIDS):
            generation = 1
            node = configure_memory_node(
                picker.HMBVideoPickerLibrary(
                    name=f"picker_delete_permutation_{permutation_count + 1}"
                )
            )
            full_catalog = shot_catalog(list(SHOT_UUIDS), generation)
            node._hmb_reconcile_shot_routing_commit(full_catalog)
            state = node._picker_state()
            for shot_number in range(1, 6):
                state = append_shot_videos(state, shot_number, media_root)
            state = install_distinct_authoring_contexts(state)

            # Every permutation begins by deleting its current active Shot.
            # Later transitions naturally cover both active and non-active
            # deletion as the ImageAsset positional fallback advances.
            initial_active = next(
                row
                for row in state_rows(state)
                if row["bound_shot_uuid"] == deletion_order[0]
            )
            picker._restore_picker_workspace_projection(state, initial_active)
            state["shot_uuid"] = deletion_order[0]
            configure_memory_node(node, state)
            node._hmb_shot_catalog_snapshot = copy.deepcopy(full_catalog)

            remaining = list(SHOT_UUIDS)
            # ImageAsset intentionally keeps one Shot. Four deletions across
            # all 5! orders produce the complete 480-transition matrix.
            for deleted_shot_uuid in deletion_order[:-1]:
                before = node._picker_state()
                before_rows = {
                    row["bound_shot_uuid"]: copy.deepcopy(row)
                    for row in state_rows(before)
                }
                previous_active = active_bound_uuid(before)
                survivor_uuids = [
                    shot_uuid
                    for shot_uuid in remaining
                    if shot_uuid != deleted_shot_uuid
                ]
                survivor_video_uids = {
                    uid
                    for shot_uuid in survivor_uuids
                    for uid in before_rows[shot_uuid]["video_asset_uids"]
                }
                before_media = media_semantics(before, survivor_video_uids)
                deleted_video_uids = set(
                    before_rows[deleted_shot_uuid]["video_asset_uids"]
                )

                generation += 1
                node._hmb_reconcile_shot_routing_commit(
                    shot_catalog(survivor_uuids, generation)
                )
                after = node._picker_state()
                after_rows = state_rows(after)
                after_by_shot = {
                    row["bound_shot_uuid"]: row
                    for row in after_rows
                }

                assert [
                    row["bound_shot_uuid"] for row in after_rows
                ] == survivor_uuids
                assert deleted_shot_uuid not in after_by_shot
                for survivor_uuid in survivor_uuids:
                    after_semantics = row_durable_semantics(
                        after_by_shot[survivor_uuid]
                    )
                    before_semantics = row_durable_semantics(
                        before_rows[survivor_uuid]
                    )
                    differing_fields = [
                        key
                        for key in before_semantics
                        if canonical_bytes(before_semantics[key])
                        != canonical_bytes(after_semantics[key])
                    ]
                    assert not differing_fields, (
                        "Surviving Picker workspace changed during Shot deletion",
                        deletion_order,
                        deleted_shot_uuid,
                        survivor_uuid,
                        differing_fields,
                        first_difference(before_semantics, after_semantics),
                        before_semantics.get("authoring_context", {}).get(
                            "slot_assignments"
                        ),
                        after_semantics.get("authoring_context", {}).get(
                            "slot_assignments"
                        ),
                    )

                after_video_uids = {
                    str(item.get("video_uid") or item.get("source_uid") or "")
                    for item in after.get("videos", [])
                    if isinstance(item, dict)
                }
                assert not (deleted_video_uids & after_video_uids)
                assert media_semantics(after, survivor_video_uids) == before_media

                next_active = active_bound_uuid(after)
                if deleted_shot_uuid == previous_active:
                    active_deletion_count += 1
                    deleted_index = list(before_rows).index(
                        deleted_shot_uuid
                    )
                    expected_active = survivor_uuids[
                        min(deleted_index, len(survivor_uuids) - 1)
                    ]
                    assert next_active == expected_active
                else:
                    non_active_deletion_count += 1
                    assert next_active == previous_active

                assert_serializable(after)
                remaining = survivor_uuids
                deletion_transition_count += 1

            permutation_count += 1
    finally:
        picker._request_parameter_value = original_request_parameter_value


assert permutation_count == 120
assert deletion_transition_count == 480
assert active_deletion_count > 0
assert non_active_deletion_count > 0

print(
    "HMB VideoPicker five-Shot deletion permutation regression: PASS "
    f"({permutation_count} permutations, "
    f"{deletion_transition_count} transitions, "
    f"{active_deletion_count} active deletions, "
    f"{non_active_deletion_count} non-active deletions)"
)
