"""Project switches bind the exact Shot snapshot, including Shots with no images."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location("project_snapshot_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


asset = load("HMBImageAssetLibrary")
prompt = load("HMBPromptLibrary")
state = asset._default_state()
state["project_id"] = "superwings12"
before = copy.deepcopy(state)
snapshot = asset._build_shot_routing_snapshot(state, normalized=True)
assert state == before
validated = prompt._validate_shot_routing_snapshot(snapshot)
payload, media = prompt._shot_image_payload_from_snapshot(validated, validated["shots"][0])
assert payload["project_id"] == "superwings12" and media == []

changed = copy.deepcopy(state)
changed["project_id"] = "Katuri8"
changed_snapshot = asset._build_shot_routing_snapshot(changed, normalized=True)
assert changed_snapshot["metadata_sha256"] != snapshot["metadata_sha256"]
assert changed_snapshot["media_sha256"] == snapshot["media_sha256"]
assert prompt._validate_shot_routing_snapshot(changed_snapshot)["project_id"] == "Katuri8"
tampered = copy.deepcopy(snapshot)
tampered["project_id"] = "Dinoster5"
try:
    prompt._validate_shot_routing_snapshot(tampered)
    raise AssertionError("A project switch with a stale metadata hash was accepted")
except prompt._ShotRoutingContractError:
    pass

# Saved v79 publishers omit project_id. Their original hash contract still works.
legacy = copy.deepcopy(snapshot)
legacy.pop("project_id")
legacy["metadata_sha256"] = prompt._canonical_sha256({
    key: legacy[key] for key in ("channel_uuid", "generation", "shots", "ordered_assets")
})
assert "project_id" not in prompt._validate_shot_routing_snapshot(legacy)

# A source change must expire the readiness-only cache without scanning a share.
publisher = SimpleNamespace()
first = asset.HMBImageAssetLibrary._cache_shot_routing_snapshot(publisher, state, normalized=True)
try:
    asset.HMBImageAssetLibrary._cache_shot_routing_snapshot(publisher, changed, normalized=True, cached_only=True)
    raise AssertionError("Project change reused cached readiness")
except ValueError:
    pass
second = asset.HMBImageAssetLibrary._cache_shot_routing_snapshot(publisher, changed, normalized=True)
assert second["generation"] > first["generation"]
assert second["project_id"] == "Katuri8"
assert state["project_id"] == "superwings12"
print("Project Shot snapshot, empty selection, cache fencing, legacy v79: PASS")
