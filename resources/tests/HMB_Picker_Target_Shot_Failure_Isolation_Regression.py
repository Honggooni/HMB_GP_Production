"""A missing Shot 5 video must not poison exact Prompt documents 1 through 4."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
import HMBVideoPickerLibrary as picker
import HMBPromptLibrary as prompt
import HMBSeedanceGeneration as seedance

CHANNEL = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PUBLISHER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
IDS = [f"cccccccc-cccc-4ccc-8ccc-{n:012d}" for n in range(1, 6)]
ROWS = [dict(shot_uuid=shot, number=n, name=f"Asset {n}", revision=1)
    for n, shot in enumerate(IDS, 1)]


def make_state():
    state = picker._default_widget_state()
    state.update(channel_uuid=CHANNEL, shot_publisher_instance_uuid=PUBLISHER,
        shot_uuid=IDS[0], shot_number=1, shot_name="Asset 1",
        shot_selections=deepcopy(ROWS), videos=[], picker_shots=[])
    for n, shot in enumerate(IDS, 1):
        uid = f"source-{n}"
        workspace = picker._new_picker_workspace_row(n, bound_shot_uuid=shot,
            video_asset_uids=[uid], selected_video_uids=[uid], preview_video_uid=uid)
        state["picker_shots"].append(workspace)
        state["videos"].append(dict(video_uid=uid, source_uid=uid, label=f"Video {n}",
            picker_shot_uuid=workspace["workspace_uuid"], video_url=f"https://media.invalid/{n}.mp4",
            selected=n == 1, selection_order=1 if n == 1 else 0, video_slot=1 if n == 1 else 0))
    state["active_picker_shot_uuid"] = state["picker_shots"][0]["workspace_uuid"]
    return picker._parse_state(state)


def must_fail(call, expected):
    try:
        call()
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError("Unavailable exact selection was accepted")


def exercise():
    document = dict(channel_uuid=CHANNEL, generation=1, shots=deepcopy(ROWS))
    catalog = dict(schema="hmb-shot-routing-catalog", version=1,
        publisher_instance_uuid=PUBLISHER, **document, metadata_sha256=picker._sha256_canonical(document))
    node = picker.HMBVideoPickerLibrary(name="Private target-scoped Picker")
    node._hmb_shot_catalog_snapshot = deepcopy(catalog)
    node._hmb_shot_route_status = dict(ok=True, code="ready")
    state = make_state()
    node._picker_state = lambda: deepcopy(state)
    node._hmb_shot_channel_subscription = lambda: dict(participant_kind="video_picker", enabled=True,
        channel_uuid=CHANNEL, shot_uuid=IDS[0])
    full = node._hmb_shot_routing_snapshot(probe_cache={})
    assert len(full["shots"]) == 5
    state["videos"][-1]["video_url"] = ""
    state["videos"][-1]["video_path"] = str(Path(os.environ.get("TEMP", ".")) / "hmb-definitely-missing-shot-5.mp4")
    assert not Path(state["videos"][-1]["video_path"]).exists()
    original = deepcopy(state)
    # Before this correction all exact consumers used this full reader and
    # failed here even when their own selected source was healthy.
    must_fail(lambda: node._hmb_shot_routing_snapshot(probe_cache={}), "source-5")
    generations = {}
    for n in [1, 4, 2, 3, 1, 2, 4, 3]:
        scoped = node._hmb_shot_routing_snapshot_for(channel_uuid=CHANNEL, shot_uuid=IDS[n - 1], probe_cache={})
        validated = prompt._validate_picker_shot_routing_snapshot(scoped, expected_channel_uuid=CHANNEL)
        assert len(validated["shots"]) == 1
        assert validated["shots"][0]["shot_uuid"] == IDS[n - 1]
        assert validated["shots"][0]["selected_source_uids"] == [f"source-{n}"]
        assert list(validated["media_by_source_uid"].values()) == [f"https://media.invalid/{n}.mp4"]
        identity = (scoped["publisher_instance_uuid"], scoped["generation"])
        hashes = (scoped["metadata_sha256"], scoped["media_sha256"])
        assert identity not in generations or generations[identity] == hashes
        generations[identity] = hashes
        assert scoped["generation"] > full["generation"]
    must_fail(lambda: node._hmb_shot_routing_snapshot_for(channel_uuid=CHANNEL, shot_uuid=IDS[4], probe_cache={}), "source-5")
    must_fail(lambda: node._hmb_shot_routing_snapshot_for(channel_uuid="", shot_uuid=IDS[0]), "identity")
    must_fail(lambda: node._hmb_shot_routing_snapshot_for(channel_uuid=CHANNEL,
        shot_uuid="dddddddd-dddd-4ddd-8ddd-dddddddddddd", probe_cache={}), "target Shot")
    must_fail(lambda: node._hmb_shot_routing_snapshot_for(channel_uuid="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        shot_uuid=IDS[0], probe_cache={}), "does not match")
    assert state == original

    image_rows = [{**row, "selected_source_uids": []} for row in ROWS]
    image_document = dict(channel_uuid=CHANNEL, generation=1, project_id="superwings12",
        shots=image_rows, ordered_assets=[])
    image = dict(schema=prompt.SHOT_ROUTING_SNAPSHOT_SCHEMA, version=1, publisher_instance_uuid=PUBLISHER,
        **image_document, metadata_sha256=prompt._canonical_sha256(image_document),
        media_sha256=prompt._canonical_sha256({"media_descriptors": []}), media_by_source_uid={})
    compact = prompt._compact_catalog_from_snapshot(image)
    prompt_state = prompt._normalize_state({**prompt._default_widget_state(), "multi_shot_enabled": True,
        "shot": {**image_rows[0], "channel_uuid": CHANNEL},
        "image_asset": {"project_id": "superwings12", "shot_catalog": [
            {**row, "channel_uuid": CHANNEL} for row in image_rows],
            "shot_catalog_routing": prompt._catalog_routing_projection(compact)}})
    text_field = next(iter(prompt.TEXT_FIELD_DEFAULTS))
    for row in image_rows:
        prompt_state = prompt._select_prompt_shot_document(prompt_state, {**row, "channel_uuid": CHANNEL})
        prompt_state["text"][text_field] = f"Exact authored Shot {row['number']} {{keep}}"
        prompt_state = prompt._store_prompt_shot_document(prompt_state)
    owner = prompt.HMBPromptLibrary(name="Private exact Prompt manager")
    owner._current_state = lambda: deepcopy(prompt_state)
    owner._hmb_connected_source_nodes = {
        prompt.SHOT_ASSET_INPUT_PARAMETER_NAME: SimpleNamespace(
            _hmb_shot_routing_snapshot=lambda **kwargs: deepcopy(image),
            _hmb_project_identity=lambda: {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}),
        prompt.SHOT_PICKER_INPUT_PARAMETER_NAME: node,
    }
    saved_state = deepcopy(prompt_state)
    for n in [4, 1, 3, 2, 1, 4]:
        record = owner._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=IDS[n - 1])
        assert record["shot"]["shot_uuid"] == IDS[n - 1]
        assert record["video_media"] == [f"https://media.invalid/{n}.mp4"]
        assert f"Exact authored Shot {n} {{keep}}" in record["machine_prompt"]
    selected_state = prompt._select_prompt_shot_document(deepcopy(prompt_state),
        {**image_rows[0], "channel_uuid": CHANNEL})
    projected, _images, _videos, _image_exact, _picker_exact = owner._apply_exact_shot_routes(selected_state)
    assert len(projected["image_asset"]["shot_catalog"]) == 5
    assert len(projected["picker"]["shot_catalog"]) == 5
    must_fail(lambda: owner._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=IDS[4]), "source-5")
    assert prompt_state == saved_state and state == original
    for failed in range(1, 6):
        state.clear(); state.update(make_state())
        state["videos"][failed - 1]["video_url"] = ""
        state["videos"][failed - 1]["video_path"] = str(Path(os.environ.get("TEMP", "."))
            / f"hmb-definitely-missing-owner-{failed}.mp4")
        for n in [5, 1, 4, 2, 3]:
            read = lambda: owner._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=IDS[n - 1])
            if n == failed:
                must_fail(read, f"source-{failed}")
            else:
                record = read()
                assert record["video_media"] == [f"https://media.invalid/{n}.mp4"]
            generator = object.__new__(seedance.HMBSeedanceGeneration)
            generator._hmb_seedance_execution_mode = lambda: "shot"
            generator._assert_only_mode_inputs = lambda: None
            generator._reconcile_shared_shot_routing = lambda **kwargs: {"ok": True}
            generator._capture_imageasset_project_selection = lambda: {"project": {
                "project_id": "superwings12", "project_name": "슈퍼윙즈12"}}
            generator._hmb_shot_channel_subscription = lambda: dict(enabled=True, channel_uuid=CHANNEL,
                shot_uuid=IDS[n - 1], shot_number=n, shot_name=f"Asset {n}")
            generator._exact_incoming_source = lambda target, source, **kwargs: (
                node if target == seedance.SHOT_PICKER_INPUT_PARAMETER else None)
            def resolve():
                return generator._resolve_exact_shot_generation_inputs(dict(
                    model_id=seedance.SEEDANCE_2_5_MODEL_ID, prompt=f"Literal final Shot {n}", duration=4))
            if n == failed:
                must_fail(resolve, f"source-{failed}")
            else:
                resolved = resolve()
                assert resolved["video_references"] == [f"https://media.invalid/{n}.mp4"]
                assert resolved["prompt"] == f"Literal final Shot {n}"
        # Repair the same durable UID: the current owner must recover its
        # media and still retain its own literal Prompt without another Shot.
        state["videos"][failed - 1]["video_path"] = ""
        state["videos"][failed - 1]["video_url"] = f"https://media.invalid/repaired-{failed}.mp4"
        record = owner._hmb_prompt_shot_document(channel_uuid=CHANNEL, shot_uuid=IDS[failed - 1])
        assert record["video_media"] == [f"https://media.invalid/repaired-{failed}.mp4"]
        assert f"Exact authored Shot {failed} {{keep}}" in record["machine_prompt"]
    assert prompt_state == saved_state
    print("PASS full snapshot remains strict; 1-4 exact media and Prompt documents survive Shot 5 failure; missing owner fails; channels/deleted UUIDs rejected; generation hashes unique; state unchanged")


if __name__ == "__main__":
    with mock.patch.object(socket, "create_connection", side_effect=AssertionError("No network permitted")):
        exercise()
