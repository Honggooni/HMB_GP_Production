"""Exact image ownership: missing own media fails, foreign media stays local.

Uses only opaque .invalid URL strings and detached state. No engine, workflow,
filesystem media, provider, network or paid request is used.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import HMBImageAssetLibrary as images
import HMBPromptLibrary as prompts


def asset(label, order, path=""):
    return dict(asset_library_id=f"import:{label}", source_uid=f"import:{label}",
        source_kind="user", asset_id=label, image_name=label, path=path,
        selected=True, selection_order=order, import_index=order,
        connected=True, registered=False, media_ref_kind="url" if path else "bytes")


state = images._default_state()
state["assets"] = [asset("a",1,"https://media.invalid/a.png"), asset("missing",2),
    asset("c",3,"https://media.invalid/c.png"), asset("d",4,"https://media.invalid/d.png"),
    asset("e",5,"https://media.invalid/e.png")]
channel = "11111111-1111-4111-8111-111111111111"
members = [["import:c","import:a"], ["import:missing"], [], ["import:d"], ["import:e"]]
shots = [dict(shot_uuid=f"22222222-2222-4222-8222-{number:012d}", number=number,
    name=f"Exact {number}", name_is_custom=True, revision=1, selected_source_uids=uids)
    for number, uids in enumerate(members,1)]
state["shot_routing"].update(channel_uuid=channel, publisher_instance_uuid="33333333-3333-4333-8333-333333333333",
    generation=10, active_shot_uuid=shots[0]["shot_uuid"], shots=shots)
state = images._normalize_state(state)
node = images.HMBImageAssetLibrary.__new__(images.HMBImageAssetLibrary)
node._current_state = lambda: deepcopy(state)
node._hmb_import_media_by_uid = {}
node._hmb_resolution_cache = OrderedDict()
baseline = json.dumps(state,sort_keys=True)


def exact(number, *, cached_only=False):
    result = node._hmb_shot_routing_snapshot_for(channel_uuid=channel,
        shot_uuid=shots[number-1]["shot_uuid"], cached_only=cached_only)
    prompts._validate_shot_routing_snapshot(result, expected_channel_uuid=channel)
    assert result["shots"][0]["selected_source_uids"] == members[number-1]
    assert [row["source_uid"] for row in result["ordered_assets"]] == members[number-1]
    assert list(result["media_by_source_uid"]) == members[number-1]
    return result


with mock.patch.object(images,"_resolved_media_value", wraps=images._resolved_media_value) as resolve:
    first = exact(1)
    assert [call.args[0] for call in resolve.call_args_list] == ["https://media.invalid/c.png", "https://media.invalid/a.png"]
    resolve.reset_mock()
    cached = exact(1,cached_only=True)
    assert cached == first
    resolve.assert_not_called()
    empty = exact(3,cached_only=True)
    assert empty["ordered_assets"] == [] and empty["media_by_source_uid"] == {}
    resolve.assert_not_called()
    try:
        exact(2,cached_only=True)
    except images._ImageAssetSelectionPreparing:
        pass
    else:
        raise AssertionError("Unknown selected media was accepted by a cache-only read")
    resolve.assert_not_called()
    try:
        exact(2)
    except ValueError as exc:
        assert "import:missing" in str(exc)
        assert not getattr(exc,"hmb_image_asset_selection_preparing",False)
    else:
        raise AssertionError("Missing owned image became an empty/partial successful snapshot")
    # A known negative cache is a concrete failure, never another preparation
    # cycle or a successful empty image list.
    try:
        exact(2,cached_only=True)
    except ValueError as exc:
        assert "import:missing" in str(exc)
    else:
        raise AssertionError("Known missing image was accepted by cached read")
    exact(4);exact(5)

assert json.dumps(state,sort_keys=True) == baseline
catalog = node._hmb_shot_routing_catalog()
assert len(catalog["shots"]) == 5
catalog_before = deepcopy(catalog)
full = node._hmb_shot_routing_snapshot(channel)
first = exact(1)
assert first["generation"] > full["generation"]
assert exact(1) == first
fourth = exact(4)
assert fourth["generation"] > first["generation"]
again = exact(1)
assert again["generation"] > fourth["generation"]
full_again = node._hmb_shot_routing_snapshot(channel,cached_only=True)
assert full_again["generation"] > again["generation"]
assert full_again["metadata_sha256"] != full["metadata_sha256"]
assert node._hmb_shot_routing_catalog() == catalog_before

# First scoped read on an upgraded saved source must also be newer than that
# source's persisted full-generation floor, even without an in-process full
# read to initialize the private view clock.
fresh = images.HMBImageAssetLibrary.__new__(images.HMBImageAssetLibrary)
fresh._current_state = lambda:deepcopy(state)
fresh._hmb_import_media_by_uid = {}
fresh._hmb_shot_routing_generation = 30
upgraded = fresh._hmb_shot_routing_snapshot_for(channel_uuid=channel,shot_uuid=shots[0]["shot_uuid"])
assert upgraded["generation"] > 30

for bad_channel,bad_shot in [("99999999-9999-4999-8999-999999999999",shots[0]["shot_uuid"]),
        (channel,"99999999-9999-4999-8999-999999999999")]:
    try:
        node._hmb_shot_routing_snapshot_for(channel_uuid=bad_channel,shot_uuid=bad_shot)
    except ValueError:
        pass
    else:
        raise AssertionError("Foreign or deleted exact Shot was accepted")

# Routing reads a scalar quartet. A large accepted image catalog must not be
# normalized again for every subscriber, while an in-flight/native raw value
# that differs from the accepted baseline still takes the original path.
large = deepcopy(state)
large["assets"].extend(asset(f"unused-{index}",0) for index in range(995))
for row in large["assets"][5:]:
    row["selected"] = False
large = images._normalize_state(large)
assert len(large["assets"]) == 1000
hot = images.HMBImageAssetLibrary.__new__(images.HMBImageAssetLibrary)
hot.name = "ImageAssetExactShotHotFixture"
hot._accept_normalized_widget_state_baseline(large)
native = {"value": hot._hmb_last_accepted_widget_state}
with mock.patch.object(images,"_get_parameter_raw",side_effect=lambda _node,_name:native["value"]):
    with mock.patch.object(images,"_normalize_state",wraps=images._normalize_state) as normalize:
        started = time.perf_counter()
        for _ in range(100):
            value = hot._hmb_shot_channel_subscription()
            assert value["shot_uuid"] == shots[0]["shot_uuid"]
        hot_ms = (time.perf_counter()-started)*1000
        normalize.assert_not_called()
    value["shot_uuid"] = "caller-mutation"
    assert hot._hmb_shot_channel_subscription()["shot_uuid"] == shots[0]["shot_uuid"]
    changed = deepcopy(large)
    changed["shot_routing"]["active_shot_uuid"] = shots[3]["shot_uuid"]
    native["value"] = images._json_text(changed)
    with mock.patch.object(images,"_normalize_state",wraps=images._normalize_state) as normalize:
        assert hot._hmb_shot_channel_subscription()["shot_uuid"] == shots[3]["shot_uuid"]
        assert normalize.call_count == 1
    # New baseline reserved before a host setter commits cannot leak to the
    # still-current older raw value.
    hot._accept_normalized_widget_state_baseline(changed)
    native["value"] = images._json_text(large)
    assert hot._hmb_shot_channel_subscription()["shot_uuid"] == shots[0]["shot_uuid"]

print("IMAGEASSET_SCALAR_SUBSCRIPTION "+json.dumps(dict(catalog_rows=1000,reads=100,
    accepted_baseline_normalizations=0,read_total_ms=round(hot_ms,3),partial_native_fallback=True)))

print("HMB_IMAGEASSET_EXACT_SHOT_MEDIA=PASS (five UUIDs, explicit empty, own failure, foreign isolation, cache-only and monotonic full/scoped hashes)")
