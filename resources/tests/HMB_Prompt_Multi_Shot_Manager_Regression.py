"""Five authored Prompt documents retain UUID ownership through execution reads."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location("prompt_multi_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("HMBPromptLibrary")
asset = load("HMBImageAssetLibrary")
picker = load("HMBVideoPickerLibrary")
channel = "11111111-1111-4111-8111-111111111111"
shots = [{"shot_uuid": f"22222222-2222-4222-8222-{number:012d}", "channel_uuid": channel,
          "number": number, "name": f"asset_custom_{number}", "selected_source_uids": []}
         for number in range(1, 6)]
state = prompt._normalize_state({**prompt._default_widget_state(), "multi_shot_enabled": True,
    "shot": shots[0], "image_asset": {"project_id": "superwings12", "shot_catalog": shots,
        "shot_catalog_routing": {"publisher_instance_uuid": channel, "channel_uuid": channel,
            "generation": 1, "metadata_sha256": "a" * 64}}})
assert prompt._normalize_state(prompt._default_widget_state())["multi_shot_enabled"] is False

for shot in shots:
    state = prompt._select_prompt_shot_document(state, shot)
    state["text"]["context"] = ""  # Unknown keys remain outside the authored contract.
    text_key = next(iter(prompt.TEXT_FIELD_DEFAULTS))
    state["text"][text_key] = f"literal_{shot['number']} {{keep_exact}}"
    state["images"][0]["label"] = f"manual_image_{shot['number']}"
    state["images"][0]["color_picks"] = ["Red" if shot["number"] % 2 else "Blue"]
    state["videos"][0]["keep_out"] = f"keep_out_{shot['number']}"
    state["ui"]["textarea_heights"] = {"video:1:keep_out": 80 + shot["number"]}
    state[prompt.UI_EDIT_REVISION_KEY] += 1
    state = prompt._store_prompt_shot_document(state)

for shot in reversed(shots):
    state = prompt._select_prompt_shot_document(state, shot)
    assert state["text"][text_key] == f"literal_{shot['number']} {{keep_exact}}"
    assert state["images"][0]["label"] == f"manual_image_{shot['number']}"
    assert state["videos"][0]["keep_out"] == f"keep_out_{shot['number']}"
    assert state["ui"]["textarea_heights"]["video:1:keep_out"] == 80 + shot["number"]

encoded = json.dumps(state, ensure_ascii=False)
state = prompt._normalize_state(json.loads(encoded))
assert len(state["shot_documents"]) == 5
assert all(isinstance(value, str) for value in state["shot_documents"].values())
assert all("shot_documents" not in json.loads(value) for value in state["shot_documents"].values())

asset_state = asset._default_state()
asset_state["project_id"] = "superwings12"
asset_state["shot_routing"]["channel_uuid"] = channel
asset_state["shot_routing"]["shots"] = [{**shot, "revision": 1} for shot in shots]
asset_state["shot_routing"]["active_shot_uuid"] = shots[0]["shot_uuid"]
snapshot = asset._build_shot_routing_snapshot(asset_state, normalized=True)
catalog = prompt._compact_catalog_from_snapshot(snapshot)
state["image_asset"]["shot_catalog_routing"] = prompt._catalog_routing_projection(catalog)
state["image_asset"]["shot_catalog"] = shots
node = prompt.HMBPromptLibrary(name="PromptManagerTest")
node._current_state = lambda: copy.deepcopy(state)
node._hmb_connected_source_nodes = {prompt.SHOT_ASSET_INPUT_PARAMETER_NAME: SimpleNamespace(
    _hmb_shot_routing_snapshot=lambda **_kwargs: copy.deepcopy(snapshot),
    _hmb_project_identity=lambda: {"project_id": "superwings12", "project_name": "슈퍼윙즈12"})}
before = copy.deepcopy(state)
outputs_before = copy.deepcopy(getattr(node, "parameter_output_values", {}))
raw_before = node.get_parameter_value(prompt.WIDGET_PARAMETER_NAME)
cache_before = {key: copy.deepcopy(value) for key, value in vars(node).items()
    if key.startswith("_hmb_last_") or key in {"_hmb_current_shot_images", "_hmb_current_shot_videos", "_hmb_shot_route_status", "_hmb_source_input_fingerprints"}}
assert node._hmb_shot_manager_enabled() is True
assert [item["shot_name"] for item in node._hmb_prompt_shot_subscriptions()] == [shot["name"] for shot in shots]

documents = [node._hmb_prompt_shot_document(channel_uuid=channel, shot_uuid=shot["shot_uuid"]) for shot in shots]
for number, document in enumerate(documents, 1):
    assert document["schema"] == "hmb-prompt-shot-document" and document["version"] == 1
    assert document["shot"]["shot_uuid"] == shots[number - 1]["shot_uuid"]
    assert f"literal_{number} {{keep_exact}}" in document["machine_prompt"]
    assert document["context"] == document["shot_context"]
    assert document["context"]["shot_number"] == number
    assert document["paired_snapshot"]["machine_prompt"] == document["machine_prompt"]
    assert document["image_media"] == [] and document["video_media"] == []
    assert document["project_identity"] == {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}
assert len({document["fingerprint"] for document in documents}) == 5
assert state == before and getattr(node, "parameter_output_values", {}) == outputs_before
assert node.get_parameter_value(prompt.WIDGET_PARAMETER_NAME) == raw_before
assert {key: value for key, value in vars(node).items() if key in cache_before} == cache_before
asset_owner = node._hmb_connected_source_nodes[prompt.SHOT_ASSET_INPUT_PARAMETER_NAME]
asset_owner._hmb_project_identity = lambda: {"project_id": "katuri8", "project_name": "까투리8"}
try:
    node._hmb_prompt_shot_document(channel_uuid=channel, shot_uuid=shots[0]["shot_uuid"])
except RuntimeError:
    pass
else:
    raise AssertionError("A project switch during a snapshot was accepted")
asset_owner._hmb_project_identity = lambda: {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}
documents[0]["shot"]["name"] = "caller mutation"
assert node._hmb_prompt_shot_document(channel_uuid=channel, shot_uuid=shots[0]["shot_uuid"])["shot"]["name"] == shots[0]["name"]

for kwargs in ({"channel_uuid": "wrong", "shot_uuid": shots[0]["shot_uuid"]},
               {"channel_uuid": channel, "shot_uuid": "deleted-shot"}):
    try:
        node._hmb_prompt_shot_document(**kwargs)
    except RuntimeError:
        pass
    else:
        raise AssertionError("A foreign/deleted Shot document was accepted")

# Source/UI clocks may cross while the visible Shot changes. The latest
# dormant document must survive; the older source body cannot overwrite it.
source = copy.deepcopy(state)
ui = prompt._select_prompt_shot_document(copy.deepcopy(state), shots[1])
ui["text"][text_key] = "new_ui_second"
ui[prompt.UI_EDIT_REVISION_KEY] += 3
ui = prompt._store_prompt_shot_document(ui)
source[prompt.SOURCE_SYNC_REVISION_KEY] += 1
merged = prompt._merge_prompt_revision_axes(source, ui)
assert merged["shot"]["shot_uuid"] == shots[1]["shot_uuid"]
assert merged["text"][text_key] == "new_ui_second"
assert prompt._select_prompt_shot_document(merged, shots[0])["text"][text_key] == "literal_1 {keep_exact}"

# Exercise the same source projection with nonempty media in all five Shots.
# The media strings are never opened: the real Picker payload builder and both
# Prompt snapshot validators operate only on these bounded metadata fixtures.
image_media = {f"image-{number}-{suffix}": f"https://media.invalid/image-{number}-{suffix}.png"
               for number in range(1, 6) for suffix in ("a", "b")}
video_media = {f"video-{number}-{suffix}": f"https://media.invalid/video-{number}-{suffix}.mp4"
               for number in range(1, 6) for suffix in ("a", "b")}
image_shots = [{key: value for key, value in shot.items() if key != "channel_uuid"}
               for shot in shots]
picker_shots = copy.deepcopy(image_shots)
for number, image_shot in enumerate(image_shots, 1):
    image_shot.update(revision=2, selected_source_uids=[f"image-{number}-b", f"image-{number}-a"])
    selected_video_uids = [f"video-{number}-b", f"video-{number}-a"]
    picker_state = picker._default_widget_state()
    picker_state["videos"] = [{"video_uid": uid, "source_uid": uid,
        "video_url": video_media[uid], "label": uid, "selected": True,
        "selection_order": index, "video_slot": index}
        for index, uid in enumerate(selected_video_uids, 1)]
    payload, resolved_media = picker._build_synchronized_video_outputs(picker_state)
    assert resolved_media == [video_media[uid] for uid in selected_video_uids]
    picker_shots[number - 1].update(revision=2, selected_source_uids=selected_video_uids, picker_payload=payload)


def media_snapshot(kind, records_key, selected_shots, media):
    document = {"channel_uuid": channel, "generation": 20, "shots": selected_shots,
        records_key: [{"source_uid": uid, "metadata": {"label": uid, "asset_id": uid,
            "source_kind": "import", "source_uid": uid}} for uid in media]}
    if kind == "image":
        document["project_id"] = "superwings12"
    return {"schema": prompt.SHOT_ROUTING_SNAPSHOT_SCHEMA if kind == "image" else prompt.PICKER_SHOT_ROUTING_SNAPSHOT_SCHEMA,
        "version": 1, "publisher_instance_uuid": "33333333-3333-4333-8333-333333333333",
        **document, "metadata_sha256": prompt._canonical_sha256(document),
        "media_sha256": prompt._canonical_sha256({"media_descriptors": [{"source_uid": uid,
            "media_value_sha256": hashlib.sha256(value.encode()).hexdigest()} for uid, value in media.items()]}),
        "media_by_source_uid": dict(media)}


image_snapshot = media_snapshot("image", "ordered_assets", image_shots, image_media)
picker_snapshot = media_snapshot("video", "ordered_videos", picker_shots, video_media)
prompt._validate_shot_routing_snapshot(image_snapshot)
prompt._validate_picker_shot_routing_snapshot(picker_snapshot, expected_channel_uuid=channel)
asset_owner._hmb_shot_routing_snapshot = lambda **_kwargs: copy.deepcopy(image_snapshot)
node._hmb_connected_source_nodes[prompt.SHOT_PICKER_INPUT_PARAMETER_NAME] = SimpleNamespace(
    _hmb_shot_routing_snapshot=lambda **_kwargs: copy.deepcopy(picker_snapshot),
    _hmb_shot_channel_subscription=lambda: {"participant_kind": "video_picker", "enabled": True, "channel_uuid": channel})
state["image_asset"]["shot_catalog_routing"] = prompt._catalog_routing_projection(prompt._compact_catalog_from_snapshot(image_snapshot))
state_before_media_reads = copy.deepcopy(state)
for number, shot in enumerate(shots, 1):
    document = node._hmb_prompt_shot_document(channel_uuid=channel, shot_uuid=shot["shot_uuid"])
    expected_images = [image_media[f"image-{number}-{suffix}"] for suffix in ("b", "a")]
    expected_videos = [video_media[f"video-{number}-{suffix}"] for suffix in ("b", "a")]
    assert document["image_media"] == expected_images
    assert document["video_media"] == expected_videos
    assert document["context"]["image_media_sha256"] == prompt._media_list_sha256(expected_images)
    assert document["context"]["video_media_sha256"] == prompt._media_list_sha256(expected_videos)
    assert [item["source"] for item in document["reference_media"]["images"]] == expected_images
    assert [item["source"] for item in document["reference_media"]["videos"]] == expected_videos
assert state == state_before_media_reads
assert getattr(node, "parameter_output_values", {}) == outputs_before
assert node.get_parameter_value(prompt.WIDGET_PARAMETER_NAME) == raw_before
assert {key: value for key, value in vars(node).items() if key in cache_before} == cache_before

# Folding/resizing changes only the editor presentation. It must not resolve
# publishers or recompile/notify the Agent chain, including direct host hooks
# which bypass the node's normal setter.
ui_node = prompt.HMBPromptLibrary(name="PresentationOnlyPrompt")
schedule_calls = []
ui_node._schedule_prompt_sync = lambda **kwargs: schedule_calls.append(kwargs)
ui_state = prompt._normalize_state(ui_node._current_state())
for expanded in (False, True, False, True):
    ui_state = copy.deepcopy(ui_state)
    ui_state["ui"]["shot_editor_expanded"] = expanded
    ui_state["ui"]["group_heights"]["imageSources"] = 550 if expanded else 560
    ui_state[prompt.UI_EDIT_REVISION_KEY] += 1
    ui_node.after_value_set(SimpleNamespace(name=prompt.WIDGET_PARAMETER_NAME), prompt._json_dumps(ui_state))
assert schedule_calls == []
ui_state["text"][text_key] = "A real authored change still synchronizes immediately."
ui_state[prompt.UI_EDIT_REVISION_KEY] += 1
ui_node.after_value_set(SimpleNamespace(name=prompt.WIDGET_PARAMETER_NAME), prompt._json_dumps(ui_state))
assert len(schedule_calls) == 1

merge_node = prompt.HMBPromptLibrary(name="MergePrompt")
legacy_state = prompt._select_prompt_shot_document(copy.deepcopy(state), shots[0])
legacy_state["multi_shot_enabled"] = False
legacy_state["shot_documents"] = {}
merge_node._hmb_write_merged_prompt_state(prompt._json_dumps(legacy_state))
merge_node._schedule_prompt_sync = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("Migration scheduled a render-chain update"))
merge_node._reconcile_shared_shot_edges = lambda: (_ for _ in ()).throw(AssertionError("Migration changed graph routing"))
original = merge_node._hmb_prompt_merge_snapshot()
assert original["state"]["multi_shot_enabled"] is False
imported = merge_node._hmb_import_prompt_documents(state["shot_documents"], expected_state_sha256=original["state_sha256"])
assert imported["state"]["multi_shot_enabled"] is True
assert len(imported["state"]["shot_documents"]) == 5
assert imported["outputs"] == original["outputs"]
assert imported["state"]["text"] == original["state"]["text"]
try:
    merge_node._hmb_import_prompt_documents({}, expected_state_sha256=original["state_sha256"])
except RuntimeError:
    pass
else:
    raise AssertionError("A stale migration overwrote a newer document store")
conflict = copy.deepcopy(state["shot_documents"])
key = prompt._prompt_document_key(shots[1])
conflicting_document = json.loads(conflict[key])
conflicting_document["text"][text_key] = "Conflicting source must remain in its original node."
conflict[key] = json.dumps(conflicting_document)
try:
    merge_node._hmb_import_prompt_documents(conflict, expected_state_sha256=imported["state_sha256"])
except ValueError:
    pass
else:
    raise AssertionError("Conflicting authored documents were silently merged")
assert merge_node._hmb_prompt_merge_snapshot() == imported
restored = merge_node._hmb_restore_prompt_merge_snapshot(original, expected_state_sha256=imported["state_sha256"])
assert restored == original
print("HMB Prompt multi Shot manager: PASS (5 UUID documents, exact-source snapshots, no UI mutation, reload and crossed revisions)")
