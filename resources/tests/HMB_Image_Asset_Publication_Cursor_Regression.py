"""Offline real-node regression for saved publication cursors; no provider calls."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
with tempfile.TemporaryDirectory(prefix="hmb_cursor_") as root:
    os.environ["HMB_IMAGE_PROJECTS_ROOT"] = root
    spec = importlib.util.spec_from_file_location("asset_cursor_test", ROOT / "HMBImageAssetLibrary.py")
    asset = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = asset
    spec.loader.exec_module(asset)
    node = asset.HMBImageAssetLibrary(name="cursor_source")
    state = node._current_state()
    shot = state["shot_routing"]["shots"][0]
    state["shot_routing"]["shots"] = [dict(copy.deepcopy(shot), shot_uuid=str(uuid.uuid4()),
        number=i, name=f"preserved-shot-{i}", name_is_custom=True) for i in range(1, 6)]
    state["shot_routing"]["active_shot_uuid"] = state["shot_routing"]["shots"][1]["shot_uuid"]
    node._publish_state(state)
    observations = []
    original_stage = asset._stage_and_notify_image_output_pair
    def stage(owner, metadata, media, token, **kwargs):
        document = json.loads(token)
        observations.append((owner._current_state()["shot_routing"]["generation"], document["generation"]))
        assert observations[-1][0] == observations[-1][1], "Durable cursor must precede peer notification"
        return original_stage(owner, metadata, media, token, **kwargs)
    asset._stage_and_notify_image_output_pair = stage
    # A normal UI name edit calls _sync_output directly, not _publish_state.
    updated = node._current_state()
    updated["shot_routing"]["shots"][1]["name"] = "literal 0 OFF blank preserved"
    updated[asset.UI_EDIT_REVISION_KEY] += 1
    updated = asset._normalize_state(updated)
    node._hmb_state_syncing = True
    asset._set_parameter_value(node, asset.WIDGET_STATE_PARAMETER, asset._json_text(updated))
    node._hmb_state_syncing = False
    node._accept_normalized_widget_state_baseline(updated)
    result = node._sync_output(updated, normalized=True)
    saved = node._current_state()
    assert saved["shot_routing"] == result["shot_routing"]
    assert observations and all(a == b for a, b in observations)
    assert len(saved["shot_routing"]["shots"]) == 5
    assert saved["shot_routing"]["active_shot_uuid"] == state["shot_routing"]["active_shot_uuid"]
    revision = saved[asset.UI_EDIT_REVISION_KEY]
    generation = saved["shot_routing"]["generation"]
    for _ in range(10):
        node._sync_output(node._current_state(), normalized=True)
    assert node._current_state()["shot_routing"]["generation"] == generation
    assert node._current_state()[asset.UI_EDIT_REVISION_KEY] == revision
    # Old completion cannot replace a newer authored shot or its selection.
    stale = copy.deepcopy(saved)
    stale["shot_routing"]["shots"][0]["name"] = "old worker"
    snapshot = copy.deepcopy(node._hmb_shot_routing_cache)
    snapshot["generation"] = generation + 5
    node._persist_shot_routing_facts(stale, snapshot)
    assert node._current_state() == saved
    # A refused retained-state write must stop publication, not claim durability.
    real_set = asset._set_parameter_value
    asset._set_parameter_value = lambda *_args: None
    try:
        try:
            node._persist_shot_routing_facts(saved, snapshot)
        except ValueError as error:
            assert "persist" in str(error)
        else:
            raise AssertionError("Rejected durable writes must fail closed")
        assert node._current_state() == saved
    finally:
        asset._set_parameter_value = real_set
    # Unchanged publication takes the scalar/raw fast path, no full-state copy.
    real_current = node._current_state
    node._current_state = lambda: (_ for _ in ()).throw(AssertionError("No normalization on warm no-op"))
    try:
        node._persist_shot_routing_facts(saved, node._hmb_shot_routing_cache)
    finally:
        node._current_state = real_current
    # Save/reopen reconstructs from the durable state, not serialized output.
    restored = asset.HMBImageAssetLibrary(name="cursor_restored")
    restored._hmb_state_syncing = True
    asset._set_parameter_value(restored, asset.WIDGET_STATE_PARAMETER, asset._json_text(saved))
    restored._hmb_state_syncing = False
    restored._hmb_shot_routing_identity = ""
    restored._hmb_shot_routing_input_identity = ""
    reopened = restored._sync_output(restored._current_state(), normalized=True)
    assert reopened["shot_routing"]["generation"] >= generation
    assert reopened["shot_routing"]["shots"] == saved["shot_routing"]["shots"]
    print("PASS: durable cursor before publication; five shots; idempotent echoes; stale worker; save/reopen")
