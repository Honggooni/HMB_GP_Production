from __future__ import annotations

import copy
import importlib.util
import itertools
import json
import pickle
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


picker = load_module(
    "hmb_video_picker_five_shot_recursive_save_reload",
    "HMBVideoPickerLibrary.py",
)
prompt = load_module(
    "hmb_prompt_five_shot_recursive_save_reload",
    "HMBPromptLibrary.py",
)


PUBLISHER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CHANNEL_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SHOT_UUIDS = [
    f"10000000-0000-4000-8000-{index:012d}"
    for index in range(1, 6)
]


def catalog_snapshot(count: int, generation: int):
    shots = [
        {
            "shot_uuid": SHOT_UUIDS[index - 1],
            "number": index,
            "name": f"Shot {index}",
            "revision": generation,
        }
        for index in range(1, count + 1)
    ]
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": PUBLISHER_UUID,
        "channel_uuid": CHANNEL_UUID,
        "generation": generation,
        "metadata_sha256": picker._sha256_canonical(
            {
                "channel_uuid": CHANNEL_UUID,
                "generation": generation,
                "shots": shots,
            }
        ),
        "shots": shots,
    }


def workspace_rows(state):
    return sorted(
        (
            row
            for row in state.get("picker_shots", [])
            if isinstance(row, dict)
        ),
        key=lambda row: int(row.get("number") or 0),
    )


def durable_signature(state):
    normalized = picker._parse_state(copy.deepcopy(state))
    rows = workspace_rows(normalized)
    videos = sorted(
        (
            item
            for item in normalized.get("videos", [])
            if isinstance(item, dict)
        ),
        key=lambda item: str(item.get("video_uid") or ""),
    )
    return {
        "active_picker_shot_uuid": normalized["active_picker_shot_uuid"],
        "rows": [
            {
                "workspace_uuid": row["workspace_uuid"],
                "bound_shot_uuid": row["bound_shot_uuid"],
                "number": row["number"],
                "name": row["name"],
                "video_asset_uids": list(row["video_asset_uids"]),
                "selected_video_uids": list(row["selected_video_uids"]),
                "preview_video_uid": row["preview_video_uid"],
                "selected_video_slot": row["selected_video_slot"],
            }
            for row in rows
        ],
        "videos": [
            {
                "video_uid": item["video_uid"],
                "source_uid": item["source_uid"],
                "picker_shot_uuid": item["picker_shot_uuid"],
                "catalog_order": item["catalog_order"],
                "label": item.get("label", ""),
                "video_path": item.get("video_path", ""),
                "project_video_path": item.get("project_video_path", ""),
                "import_source_path": item.get("import_source_path", ""),
            }
            for item in videos
        ],
    }


def assert_prompt_read_is_lossless(state):
    before = durable_signature(state)
    for row in workspace_rows(state):
        projected = picker._activate_picker_workspace_projection(
            state,
            row["workspace_uuid"],
        )
        assert projected is not None
        projected_before = durable_signature(projected)
        payload = picker._build_synchronized_video_outputs(
            projected,
            enforce_media_availability=False,
        )[0]
        assert payload["ordered_video_uids"] == row["selected_video_uids"]
        prompt_state = prompt._default_widget_state()
        prompt._apply_picker_payload(prompt_state, payload, connected=True)
        assert durable_signature(projected) == projected_before
    assert durable_signature(state) == before


with tempfile.TemporaryDirectory(prefix="hmb-picker-five-shot-") as temporary:
    media_root = Path(temporary)
    media_counts = {1: 3, 2: 0, 3: 2, 4: 1, 5: 3}

    node = picker.HMBVideoPickerLibrary(name="five_shot_recursive_source")
    node.parameter_values = {
        picker.WIDGET_STATE_PARAMETER: copy.deepcopy(node._picker_state())
    }
    node.get_parameter_value = lambda name: node.parameter_values.get(name)
    node._sync_outputs_from_state = lambda _state: None

    original_request = picker._request_parameter_value
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        previous_signature = None
        for count in range(1, 6):
            node._hmb_reconcile_shot_routing_commit(
                catalog_snapshot(count, count)
            )
            grown = node._picker_state()
            assert [row["number"] for row in workspace_rows(grown)] == list(
                range(1, count + 1)
            )
            if previous_signature is not None:
                assert durable_signature(grown)["rows"][:-1] == (
                    previous_signature["rows"]
                )
                assert workspace_rows(grown)[-1]["video_asset_uids"] == []

            target = workspace_rows(grown)[-1]
            for asset_number in range(1, media_counts[count] + 1):
                uid = f"shot-{count}-video-{asset_number}"
                media_path = media_root / f"{uid}.mp4"
                media_path.write_bytes(
                    b"\x00\x00\x00\x18ftypmp42" + uid.encode("ascii")
                )
                grown = picker._append_video_asset(
                    grown,
                    {
                        "video_uid": uid,
                        "source_uid": uid,
                        "label": f"Shot {count} Video {asset_number}",
                        "generation_role": "imported",
                        "video_path": str(media_path.resolve()),
                        "project_video_path": str(media_path.resolve()),
                        "import_source_path": str(media_path.resolve()),
                        "video_url": f"http://127.0.0.1:1/{uid}.mp4",
                    },
                    picker_shot_uuid=target["workspace_uuid"],
                )
            node._write_state(grown)
            previous_signature = durable_signature(node._picker_state())

        authored = copy.deepcopy(node._picker_state())
        rows = workspace_rows(authored)
        requested_orders = {
            1: ["shot-1-video-3", "shot-1-video-1"],
            2: [],
            3: ["shot-3-video-2", "shot-3-video-1"],
            4: ["shot-4-video-1"],
            5: ["shot-5-video-2", "shot-5-video-3", "shot-5-video-1"],
        }
        for row in rows:
            order = requested_orders[row["number"]]
            row["selected_video_uids"] = order
            row["preview_video_uid"] = order[-1] if order else ""
            row["selected_video_slot"] = len(order) if order else 1
            row["revision"] = int(row.get("revision") or 0) + 1
        authored["picker_shots"] = rows
        authored["active_picker_shot_uuid"] = rows[-1]["workspace_uuid"]
        authored = picker._activate_picker_workspace_projection(
            authored,
            rows[-1]["workspace_uuid"],
        )
        assert authored is not None
        node._write_state(authored)

        serialized = copy.deepcopy(
            node.parameter_values[picker.WIDGET_STATE_PARAMETER]
        )
        expected = durable_signature(serialized)
        assert [row["number"] for row in expected["rows"]] == [1, 2, 3, 4, 5]
        assert [row["selected_video_uids"] for row in expected["rows"]] == [
            requested_orders[number] for number in range(1, 6)
        ]
        assert expected["rows"][1]["video_asset_uids"] == []
        json.dumps(serialized, ensure_ascii=False)
        pickle.dumps(serialized, protocol=pickle.HIGHEST_PROTOCOL)
        assert_prompt_read_is_lossless(serialized)

        # A delayed browser echo may omit the Python-owned global catalog and
        # every non-active Shot. Equal-revision UI edits may change only the
        # addressed workspace selection; stale echoes may not change any Shot.
        active_row = expected["rows"][-1]
        delayed_equal_echo = copy.deepcopy(serialized)
        delayed_equal_echo["videos"] = []
        delayed_equal_echo["picker_shots"] = [
            {
                **copy.deepcopy(active_row),
                "selected_video_uids": ["shot-5-video-1"],
                "preview_video_uid": "shot-5-video-1",
            }
        ]
        delayed_equal_echo["active_picker_shot_uuid"] = active_row[
            "workspace_uuid"
        ]
        delayed_equal_echo["state_revision"] = serialized["state_revision"]
        delayed_equal_merged = (
            picker.HMBVideoPickerLibrary._merge_widget_state(
                serialized,
                delayed_equal_echo,
            )
        )
        assert durable_signature(delayed_equal_merged) == expected

        equal_echo = copy.deepcopy(delayed_equal_echo)
        serialized_active_row = next(
            row
            for row in serialized["picker_shots"]
            if row["workspace_uuid"] == active_row["workspace_uuid"]
        )
        equal_echo["picker_shots"][0]["revision"] = (
            int(serialized_active_row.get("revision") or 0) + 1
        )
        equal_merged = picker.HMBVideoPickerLibrary._merge_widget_state(
            serialized,
            equal_echo,
        )
        equal_signature = durable_signature(equal_merged)
        assert equal_signature["videos"] == expected["videos"]
        assert equal_signature["rows"][:-1] == expected["rows"][:-1]
        assert equal_signature["rows"][-1]["video_asset_uids"] == (
            expected["rows"][-1]["video_asset_uids"]
        )
        assert equal_signature["rows"][-1]["selected_video_uids"] == [
            "shot-5-video-1"
        ]

        stale_echo = copy.deepcopy(equal_echo)
        stale_echo["state_revision"] = max(
            0,
            int(serialized["state_revision"]) - 1,
        )
        stale_merged = picker.HMBVideoPickerLibrary._merge_widget_state(
            serialized,
            stale_echo,
        )
        assert durable_signature(stale_merged) == expected

        hooks = ("after_deserialize", "after_load", "on_loaded")
        for permutation in itertools.permutations(hooks):
            restored = picker.HMBVideoPickerLibrary(
                name="five_shot_" + "_".join(permutation)
            )
            restored._ensure_parameters = lambda: None
            restored._sync_outputs_from_state = lambda _state: None
            restored._schedule_post_hydration_shot_reconcile = lambda: False
            state_parameter = picker._get_parameter_obj(
                restored,
                picker.WIDGET_STATE_PARAMETER,
            )
            # Reproduce the production NodeManager sequence. It calls the
            # hook even for initial_setup, then passes the transformed value to
            # the node setter with skip_before_value_set=True.
            replay_candidate = restored.before_value_set(
                state_parameter,
                copy.deepcopy(serialized),
            )
            assert durable_signature(replay_candidate) == expected
            restored.set_parameter_value(
                picker.WIDGET_STATE_PARAMETER,
                replay_candidate,
                initial_setup=True,
                skip_before_value_set=True,
            )
            restored_signature = durable_signature(restored._picker_state())
            assert restored_signature == expected, json.dumps(
                {
                    "permutation": permutation,
                    "restored": restored_signature,
                    "expected": expected,
                },
                ensure_ascii=False,
                indent=2,
            )
            for hook_name in permutation:
                getattr(restored, hook_name)()
                restored._hmb_reconcile_shot_routing_commit(
                    catalog_snapshot(5, 5)
                )
                assert durable_signature(restored._picker_state()) == expected

            # Repeated normalization, publication, reload, and Prompt reads
            # exercise the same saved snapshot recursively. No pass may
            # transfer a UID/path/order to a neighboring Shot or erase an
            # intentionally empty Shot.
            for _pass in range(12):
                current = picker._parse_state(restored._picker_state())
                assert durable_signature(current) == expected
                assert_prompt_read_is_lossless(current)
                restored._write_state(current)
                restored._restore_dynamic_state(adopt_serialized=True)
                assert durable_signature(restored._picker_state()) == expected
    finally:
        picker._request_parameter_value = original_request


print("HMB VideoPicker five-Shot recursive save/reload regression: PASS")
