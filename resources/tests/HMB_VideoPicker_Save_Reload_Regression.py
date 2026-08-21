from __future__ import annotations

import copy
import importlib.util
import inspect
import pickle
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def load_picker():
    path = ROOT / "HMBVideoPickerLibrary.py"
    spec = importlib.util.spec_from_file_location("HMBVideoPickerLibrary", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


picker = load_picker()


def video_by_uid(state, uid):
    return next(
        item
        for item in state.get("videos", [])
        if isinstance(item, dict) and item.get("video_uid") == uid
    )


with tempfile.TemporaryDirectory(prefix="hmb-picker-save-") as temporary:
    media_path = Path(temporary) / "한글_플레이블라스트.mp4"
    media_path.write_bytes(b"\x00\x00\x00\x18ftypmp42saved-video")

    node = picker.HMBVideoPickerLibrary(name="picker_save_source")
    parameter = picker._get_parameter_obj(node, picker.WIDGET_STATE_PARAMETER)
    assert parameter is not None
    assert getattr(parameter, "serializable", False) is True
    assert getattr(parameter, "hide", True) is False
    assert getattr(parameter, "hide_property", True) is False
    assert parameter.ui_options["hide"] is False
    assert parameter.ui_options["hide_property"] is False
    assert parameter.ui_options["expandable"] is True
    # The fallback node used by public CI stores defaults on Parameter objects;
    # production Griptape exposes this dict and SaveWorkflow reads it directly.
    node.parameter_values = {
        picker.WIDGET_STATE_PARAMETER: copy.deepcopy(node._picker_state())
    }

    state = picker._append_video_asset(
        node._picker_state(),
        {
            "video_uid": "saved-video-uid",
            "source_uid": "saved-video-uid",
            "label": "한글 플레이블라스트",
            "generation_role": "imported",
            "video_path": str(media_path.resolve()),
            "project_video_path": str(media_path.resolve()),
            "import_source_path": str(media_path.resolve()),
            "video_url": "http://127.0.0.1:1/external/stale.mp4",
        },
    )
    workspace = state["picker_shots"][0]
    assert workspace["video_asset_uids"] == ["saved-video-uid"]
    assert workspace["selected_video_uids"] == ["saved-video-uid"]

    # A retained-mode request may acknowledge before its browser echo updates
    # the node. SaveWorkflow must nevertheless see the completed import now.
    original_request = picker._request_parameter_value
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        node._write_state(state)
    finally:
        picker._request_parameter_value = original_request

    serialized = copy.deepcopy(
        node.parameter_values[picker.WIDGET_STATE_PARAMETER]
    )
    assert video_by_uid(serialized, "saved-video-uid")["label"] == (
        "한글 플레이블라스트"
    )
    assert serialized["picker_shots"][0]["video_asset_uids"] == [
        "saved-video-uid"
    ]
    assert serialized["picker_shots"][0]["selected_video_uids"] == [
        "saved-video-uid"
    ]
    pickle.dumps(serialized, protocol=pickle.HIGHEST_PROTOCOL)

    # A new engine process must preserve Shot membership and replace only the
    # stale localhost media URL with its current static-server URL.
    restored = picker.HMBVideoPickerLibrary(name="picker_save_restored")
    restored.parameter_values = {}
    restored.get_parameter_value = (
        lambda name: restored.parameter_values.get(name)
    )
    restored._store_initial_parameter_value(
        picker.WIDGET_STATE_PARAMETER,
        serialized,
    )
    restored._ensure_parameters = lambda: None
    restored._sync_outputs_from_state = lambda _state: None
    original_url = picker._external_media_url
    original_request = picker._request_parameter_value
    picker._external_media_url = (
        lambda path: f"http://127.0.0.1:7777/external/{Path(path).name}"
    )
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        restored._restore_dynamic_state(adopt_serialized=True)
    finally:
        picker._external_media_url = original_url
        picker._request_parameter_value = original_request

    restored_state = copy.deepcopy(
        restored.parameter_values[picker.WIDGET_STATE_PARAMETER]
    )
    restored_video = video_by_uid(restored_state, "saved-video-uid")
    assert restored_video["video_url"].startswith(
        "http://127.0.0.1:7777/external/"
    ), restored_video
    assert restored_state["picker_shots"][0]["video_asset_uids"] == [
        "saved-video-uid"
    ]
    assert restored_state["picker_shots"][0]["selected_video_uids"] == [
        "saved-video-uid"
    ]
    assert restored_state["saved_video_restore_count"] == 1

    # Reproduce Griptape's real saved-workflow sequence. SaveWorkflow supplies
    # the value through initial_setup, then may call all three hydration hooks.
    # Every hook must adopt the serialized catalog idempotently; none may
    # replace the saved video with the constructor's empty default.
    lifecycle = picker.HMBVideoPickerLibrary(name="picker_saved_lifecycle")
    lifecycle._sync_outputs_from_state = lambda _state: None
    lifecycle._ensure_parameters = lambda: None
    original_url = picker._external_media_url
    original_request = picker._request_parameter_value
    picker._external_media_url = (
        lambda path: f"http://127.0.0.1:7788/external/{Path(path).name}"
    )
    picker._request_parameter_value = lambda *_args, **_kwargs: True
    try:
        lifecycle.set_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            copy.deepcopy(serialized),
            initial_setup=True,
        )
        for hook_name in ("after_deserialize", "after_load", "on_loaded"):
            getattr(lifecycle, hook_name)()
            hydrated = copy.deepcopy(lifecycle._picker_state())
            assert video_by_uid(hydrated, "saved-video-uid")
            assert hydrated["picker_shots"][0]["video_asset_uids"] == [
                "saved-video-uid"
            ]
            assert hydrated["picker_shots"][0]["selected_video_uids"] == [
                "saved-video-uid"
            ]
            assert hydrated["saved_video_restore_count"] == 1
    finally:
        picker._external_media_url = original_url
        picker._request_parameter_value = original_request

    # Adding an ImageAsset Shot is a catalog growth, never a deletion event.
    # The existing Shot's imported videos, selection, ordering, and Prompt
    # routing membership must survive byte-for-byte while the new Shot starts
    # empty.
    shot_one_uuid = "11111111-1111-4111-8111-111111111111"
    shot_two_uuid = "22222222-2222-4222-8222-222222222222"
    publisher_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    channel_uuid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    remote_saved = copy.deepcopy(serialized)
    remote_saved["picker_shots"][0]["bound_shot_uuid"] = shot_one_uuid
    remote_saved.update({
        "shot_publisher_instance_uuid": publisher_uuid,
        "channel_uuid": channel_uuid,
        "shot_uuid": shot_one_uuid,
        "shot_number": 1,
        "shot_name": "Shot 1",
        "shot_selections": [{
            "shot_uuid": shot_one_uuid,
            "number": 1,
            "name": "Shot 1",
            "revision": 1,
            # Exercise migration from the real saved-file defect: workspace
            # membership exists, while this compact row was empty.
            "selected_video_uids": [],
        }],
    })
    initial_shots = [{
        "shot_uuid": shot_one_uuid,
        "number": 1,
        "name": "Shot 1",
        "revision": 1,
    }]
    initial_generation = 1
    initial_hash = picker._sha256_canonical({
        "channel_uuid": channel_uuid,
        "generation": initial_generation,
        "shots": initial_shots,
    })
    remote_saved.update({
        "accepted_shot_catalog_publisher_instance_uuid": publisher_uuid,
        "accepted_shot_catalog_channel_uuid": channel_uuid,
        "accepted_shot_catalog_generation": initial_generation,
        "accepted_shot_catalog_metadata_sha256": initial_hash,
    })
    remote_saved = picker._parse_state(remote_saved)
    assert remote_saved["shot_selections"][0]["selected_video_uids"] == [
        "saved-video-uid"
    ]

    growth_node = picker.HMBVideoPickerLibrary(name="picker_shot_growth")
    growth_node.parameter_values = {
        picker.WIDGET_STATE_PARAMETER: copy.deepcopy(remote_saved)
    }
    growth_node.get_parameter_value = (
        lambda name: growth_node.parameter_values.get(name)
    )
    growth_node._sync_outputs_from_state = lambda _state: None
    growth_node._write_state = lambda next_state: growth_node.parameter_values.__setitem__(
        picker.WIDGET_STATE_PARAMETER,
        copy.deepcopy(next_state),
    )
    grown_shots = [
        initial_shots[0],
        {
            "shot_uuid": shot_two_uuid,
            "number": 2,
            "name": "Shot 2",
            "revision": 0,
        },
    ]
    grown_generation = 2
    grown_snapshot = {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher_uuid,
        "channel_uuid": channel_uuid,
        "generation": grown_generation,
        "metadata_sha256": picker._sha256_canonical({
            "channel_uuid": channel_uuid,
            "generation": grown_generation,
            "shots": grown_shots,
        }),
        "shots": grown_shots,
    }
    before_growth_videos = copy.deepcopy(remote_saved["videos"])
    before_growth_workspace = copy.deepcopy(remote_saved["picker_shots"][0])
    growth_node._hmb_reconcile_shot_routing_commit(grown_snapshot)
    grown_state = growth_node.parameter_values[picker.WIDGET_STATE_PARAMETER]
    assert grown_state["videos"] == before_growth_videos
    assert grown_state["picker_shots"][0] == before_growth_workspace
    assert grown_state["picker_shots"][1]["bound_shot_uuid"] == shot_two_uuid
    assert grown_state["picker_shots"][1]["video_asset_uids"] == []
    assert grown_state["shot_selections"][0]["selected_video_uids"] == [
        "saved-video-uid"
    ]

    # Commands travel through the one visible serializable STATE row. The
    # retired hidden custom row is no longer required to mount, so a cold host
    # cannot hide all three parameters before saved media is displayed.
    command_node = picker.HMBVideoPickerLibrary(name="picker_state_command")
    command_parameter = picker._get_parameter_obj(
        command_node,
        picker.WIDGET_STATE_PARAMETER,
    )
    command_transport = copy.deepcopy(serialized)
    command_transport["runtime_instance_id"] = command_node._hmb_runtime_instance_id
    command_transport["state_writer"] = "widget"
    command_node._hmb_authoritative_state = copy.deepcopy(command_transport)
    command_node.parameter_values = {}
    command_node.parameter_values[picker.WIDGET_STATE_PARAMETER] = copy.deepcopy(
        command_transport
    )
    command_transport[picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD] = {
        "schema": "hmb-picker-command",
        "version": 1,
        "runtime_instance_id": command_node._hmb_runtime_instance_id,
        "action": "set_language",
        "action_id": "saved-state-command-1",
        "issued_at_ms": 1,
        "payload": {"language": "ko"},
    }
    stored_transport = command_node.before_value_set(
        command_parameter,
        command_transport,
    )
    assert picker.WIDGET_STATE_EMBEDDED_COMMAND_FIELD not in stored_transport
    assert video_by_uid(stored_transport, "saved-video-uid")
    scheduled = []
    command_node._schedule_action_worker = (
        lambda action, action_id, target: scheduled.append((action, action_id, target))
    )
    command_node.after_value_set(command_parameter, stored_transport)
    assert [(action, action_id) for action, action_id, _target in scheduled] == [
        ("set_language", "saved-state-command-1")
    ]

    # A missing media file is diagnosed but its card and exact Shot ownership
    # are retained, allowing the user to restore the file without data loss.
    missing = copy.deepcopy(serialized)
    missing_video = video_by_uid(missing, "saved-video-uid")
    missing_path = Path(temporary) / "missing.mp4"
    missing_video.update({
        "video_path": str(missing_path),
        "project_video_path": str(missing_path),
        "import_source_path": str(missing_path),
    })
    refreshed_missing, changed = picker._refresh_saved_video_media_urls(missing)
    assert changed is True
    assert video_by_uid(refreshed_missing, "saved-video-uid")
    assert refreshed_missing["picker_shots"][0]["video_asset_uids"] == [
        "saved-video-uid"
    ]
    assert any(
        "Saved video is unavailable" in warning
        for warning in refreshed_missing["warnings"]
    )


# Windows dialogs must never use subprocess text readers whose implicit UTF-8
# decoding can terminate on Korean legacy-console bytes.
chooser_source = inspect.getsource(picker._choose_video_asset_files)
assert "[Console]::OutputEncoding" in chooser_source
assert "text=False" in chooser_source
assert "_decode_maya_text" in chooser_source

print("HMB VideoPicker save/reload regression: PASS")
