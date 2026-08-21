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
from typing import Any, Iterable


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
    "HMBVideoPickerLibrary_five_shot_recursive_roundtrip",
    "HMBVideoPickerLibrary.py",
)
prompt = load_module(
    "HMBPromptLibrary_five_shot_recursive_roundtrip",
    "HMBPromptLibrary.py",
)


PUBLISHER_UUID = "10000000-0000-4000-8000-000000000001"
CHANNEL_UUID = "20000000-0000-4000-8000-000000000002"
SHOT_UUIDS = [
    f"30000000-0000-4000-8000-{number:012d}"
    for number in range(1, 6)
]
HOOKS = ("after_deserialize", "after_load", "on_loaded")
VOLATILE_STATE_KEYS = {
    "frontend_seen_revision",
    "python_core_loaded",
    "python_core_path",
    "runtime_instance_id",
    "saved_video_restore_count",
    "state_published_at_ms",
    "state_revision",
    "state_writer",
    "writer_lifecycle_generation",
    "writer_runtime_instance_id",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
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
            difference = first_difference(left_item, right_item, f"{path}[{index}]")
            if difference:
                return difference
        return ""
    return "" if left == right else f"{path}: {left!r} != {right!r}"


def recursive_semantic_copy(value: Any, *, key: str = "") -> Any:
    """Copy the complete durable tree while excluding runtime transport clocks."""

    if isinstance(value, dict):
        return {
            name: recursive_semantic_copy(child, key=name)
            for name, child in sorted(value.items())
            if name not in VOLATILE_STATE_KEYS
        }
    if isinstance(value, list):
        return [recursive_semantic_copy(child, key=key) for child in value]
    if isinstance(value, tuple):
        return [recursive_semantic_copy(child, key=key) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise AssertionError(f"Non-serializable Picker value at {key!r}: {type(value)!r}")


def semantic_bytes(state: Any) -> bytes:
    return canonical_bytes(recursive_semantic_copy(picker._parse_state(state)))


def shot_records(count: int) -> list[dict[str, Any]]:
    return [
        {
            "shot_uuid": SHOT_UUIDS[index - 1],
            "number": index,
            "name": f"Shot {index}",
            "revision": index,
        }
        for index in range(1, count + 1)
    ]


def shot_catalog(count: int, generation: int) -> dict[str, Any]:
    shots = shot_records(count)
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
    normalized = picker._parse_state(state if state is not None else node._picker_state())
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


def selected_uids_for_shot(number: int) -> list[str]:
    return [f"shot-{number}-video-{index}" for index in range(1, number + 1)]


def assert_recursive_five_shot_invariants(state: Any) -> None:
    normalized = picker._parse_state(state)
    # This recursively rejects cycles, unserializable host objects, NaN and
    # changes in JSON-compatible scalar meaning before any focused assertions.
    semantic = recursive_semantic_copy(normalized)
    encoded = canonical_bytes(semantic)
    assert json.loads(encoded.decode("utf-8")) == semantic
    pickle.dumps(normalized, protocol=pickle.HIGHEST_PROTOCOL)

    rows = state_rows(normalized)
    assert [int(row["number"]) for row in rows] == [1, 2, 3, 4, 5]
    videos = {
        str(item.get("video_uid") or item.get("source_uid")): item
        for item in normalized.get("videos", [])
        if isinstance(item, dict)
    }
    assert len(videos) == 15
    all_owned: list[str] = []
    for number, row in enumerate(rows, start=1):
        expected = selected_uids_for_shot(number)
        assert row["bound_shot_uuid"] == SHOT_UUIDS[number - 1]
        assert row["video_asset_uids"] == expected
        assert row["selected_video_uids"] == expected
        assert row["preview_video_uid"] == expected[-1]
        assert len(row["selected_video_uids"]) == number
        assert set(row["selected_video_uids"]).issubset(row["video_asset_uids"])
        for uid in expected:
            assert uid in videos
            assert videos[uid]["picker_shot_uuid"] == row["workspace_uuid"]
            assert videos[uid]["label"] == uid.replace("-", " ").title()
        all_owned.extend(row["video_asset_uids"])
    assert len(all_owned) == len(set(all_owned)) == 15
    assert set(all_owned) == set(videos)


def first_n_shot_semantics(state: Any, count: int) -> bytes:
    normalized = picker._parse_state(state)
    rows = [row for row in state_rows(normalized) if int(row["number"]) <= count]
    loader_rows = [
        {
            key: copy.deepcopy(row.get(key))
            for key in (
                "workspace_uuid",
                "number",
                "name",
                "custom_name",
                "revision",
                "bound_shot_uuid",
                "video_asset_uids",
                "selected_video_uids",
                "preview_video_uid",
                "selected_video_slot",
            )
        }
        for row in rows
    ]
    owned = {
        uid
        for row in rows
        for uid in row.get("video_asset_uids", [])
    }
    videos = [
        item
        for item in normalized.get("videos", [])
        if isinstance(item, dict)
        and str(item.get("video_uid") or item.get("source_uid")) in owned
    ]
    return canonical_bytes(recursive_semantic_copy({
        "picker_shots": loader_rows,
        "videos": videos,
    }))


def append_shot_videos(
    state: Any,
    number: int,
    media_root: Path,
    media_url: Any,
) -> dict[str, Any]:
    normalized = picker._parse_state(state)
    row = next(row for row in state_rows(normalized) if int(row["number"]) == number)
    for index in range(1, number + 1):
        uid = f"shot-{number}-video-{index}"
        path = media_root / f"{uid}.mp4"
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + uid.encode("ascii"))
        normalized = picker._append_video_asset(
            normalized,
            {
                "video_uid": uid,
                "source_uid": uid,
                "label": uid.replace("-", " ").title(),
                "generation_role": "imported",
                "media_kind": "maya_preview",
                "source_type": "Maya Preview",
                "source_subtype": f"Shot {number}",
                "video_path": str(path.resolve()),
                "project_video_path": str(path.resolve()),
                "import_source_path": str(path.resolve()),
                "video_url": media_url(path),
                "created_at_ms": number * 1000 + index,
            },
            picker_shot_uuid=row["workspace_uuid"],
        )
    return normalized


def prompt_consumer_read_without_picker_mutation(node: Any) -> None:
    before = canonical_bytes(copy.deepcopy(node._picker_state()))
    raw_snapshot = node._hmb_shot_routing_snapshot(
        expected_channel_uuid=CHANNEL_UUID,
    )
    validated = prompt._validate_picker_shot_routing_snapshot(
        raw_snapshot,
        expected_channel_uuid=CHANNEL_UUID,
    )
    assert [shot["number"] for shot in validated["shots"]] == [1, 2, 3, 4, 5]
    for number, shot in enumerate(validated["shots"], start=1):
        expected = selected_uids_for_shot(number)
        assert shot["selected_source_uids"] == expected
        projected = prompt._apply_picker_payload(
            prompt._default_widget_state(),
            copy.deepcopy(shot["picker_payload"]),
            connected=True,
        )
        assert projected["picker"]["ordered_video_uids"] == expected
        routed_media = [
            validated["media_by_source_uid"][uid]
            for uid in shot["selected_source_uids"]
        ]
        assert len(routed_media) == number
        assert all(
            str(media).replace("\\", "/").endswith(f"/{uid}.mp4")
            for uid, media in zip(expected, routed_media)
        )
    after = canonical_bytes(copy.deepcopy(node._picker_state()))
    assert after == before, "Prompt consumer read mutated the Picker source state."


def restored_node(serialized: Any, catalog: dict[str, Any]) -> Any:
    node = picker.HMBVideoPickerLibrary(name="picker_five_shot_restored")
    node._sync_outputs_from_state = lambda _state: None
    node._ensure_parameters = lambda: None
    node._schedule_post_hydration_shot_reconcile = lambda: None
    node.set_parameter_value(
        picker.WIDGET_STATE_PARAMETER,
        copy.deepcopy(serialized),
        initial_setup=True,
    )
    # The ImageAsset callback normally republishes this live, non-serialized
    # cache after hydration. Reinstall it so the Prompt consumer path can also
    # be exercised after every independent save/load round-trip.
    node._hmb_shot_catalog_snapshot = copy.deepcopy(catalog)
    node._hmb_shot_route_status = {
        "schema": "hmb-shot-routing-status",
        "version": 1,
        "ok": True,
        "code": "ready",
        "details": "",
    }
    return node


def run_hook_order_round_trips(
    serialized: Any,
    catalog: dict[str, Any],
    hook_order: Iterable[str],
    baseline_semantics: bytes,
) -> None:
    payload = copy.deepcopy(serialized)
    for round_number in range(1, 4):
        node = restored_node(payload, catalog)
        for hook_name in hook_order:
            getattr(node, hook_name)()
            current = node._picker_state()
            assert_recursive_five_shot_invariants(current)
            assert semantic_bytes(current) == baseline_semantics, (
                f"Durable state changed at round {round_number}, hook {hook_name}, "
                f"order {tuple(hook_order)}."
            )
        prompt_consumer_read_without_picker_mutation(node)
        payload = copy.deepcopy(node._picker_state())


with tempfile.TemporaryDirectory(prefix="hmb-picker-five-shot-recursive-") as temporary:
    media_root = Path(temporary)
    stable_url = lambda path: f"http://127.0.0.1:8787/external/{Path(path).name}"
    original_external_media_url = picker._external_media_url
    original_request_parameter_value = picker._request_parameter_value
    picker._external_media_url = stable_url
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        source = configure_memory_node(
            picker.HMBVideoPickerLibrary(name="picker_five_shot_source")
        )

        # Populate Shots 1..4, then simulate ImageAsset adding and deleting one
        # empty Shot. Existing Loader rows must be exact byte-semantic echoes.
        catalog_4 = shot_catalog(4, 1)
        source._hmb_reconcile_shot_routing_commit(catalog_4)
        state = source._picker_state()
        for shot_number in range(1, 5):
            state = append_shot_videos(state, shot_number, media_root, stable_url)
        configure_memory_node(source, state)
        first_four = first_n_shot_semantics(source._picker_state(), 4)

        added_catalog = shot_catalog(5, 2)
        source._hmb_reconcile_shot_routing_commit(added_catalog)
        added = source._picker_state()
        added_first_four = first_n_shot_semantics(added, 4)
        assert added_first_four == first_four, "Adding empty ImageAsset Shot changed Shots 1..4: " + first_difference(
            json.loads(first_four), json.loads(added_first_four)
        )
        assert state_rows(added)[4]["video_asset_uids"] == []

        deleted_catalog = shot_catalog(4, 3)
        source._hmb_reconcile_shot_routing_commit(deleted_catalog)
        deleted = source._picker_state()
        deleted_first_four = first_n_shot_semantics(deleted, 4)
        assert deleted_first_four == first_four, "Deleting empty ImageAsset Shot changed Shots 1..4: " + first_difference(
            json.loads(first_four), json.loads(deleted_first_four)
        )
        assert len(state_rows(deleted)) == 4

        final_catalog = shot_catalog(5, 4)
        source._hmb_reconcile_shot_routing_commit(final_catalog)
        final_state = append_shot_videos(
            source._picker_state(),
            5,
            media_root,
            stable_url,
        )
        configure_memory_node(source, final_state)
        # Reinstall the accepted catalog cache after the in-memory writer swap.
        source._hmb_shot_catalog_snapshot = copy.deepcopy(final_catalog)
        source._hmb_shot_route_status = {
            "schema": "hmb-shot-routing-status",
            "version": 1,
            "ok": True,
            "code": "ready",
            "details": "",
        }

        assert_recursive_five_shot_invariants(source._picker_state())
        prompt_consumer_read_without_picker_mutation(source)
        serialized = copy.deepcopy(source._picker_state())
        baseline_semantics = semantic_bytes(serialized)

        # Six deserialize-hook orders x three independent new-instance
        # round-trips. Each of the 54 post-hook states is recursively checked.
        for hook_order in itertools.permutations(HOOKS):
            run_hook_order_round_trips(
                serialized,
                final_catalog,
                hook_order,
                baseline_semantics,
            )
    finally:
        picker._external_media_url = original_external_media_url
        picker._request_parameter_value = original_request_parameter_value


print(
    "HMB VideoPicker five-Shot recursive save/load round-trip regression: PASS "
    "(6 hook orders x 3 rounds x 3 hooks; 15 Shot-local videos)"
)
