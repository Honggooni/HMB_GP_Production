"""Cold saved ImageAsset catalog revisions remain monotonic for Picker.

Detached SDK objects only; no workflow, project scan, media, provider, or write.
"""

from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import HMBImageAssetLibrary as images
import HMBVideoPickerLibrary as picker


def node_for(state, token=None):
    node = images.HMBImageAssetLibrary.__new__(images.HMBImageAssetLibrary)
    node._hmb_import_media_by_uid = {}
    node._hmb_resolution_cache = OrderedDict()
    node.parameter_output_values = (
        {images.SHOT_ASSET_OUTPUT_PARAMETER: token} if token else {}
    )
    return node


saved = images._default_state()
saved["shot_routing"]["generation"] = 2
saved = images._normalize_state(saved)
first_node = node_for(saved)
first = first_node._cache_shot_routing_snapshot(deepcopy(saved), normalized=True)
token = first_node._shot_asset_dependency_token(first)
assert first["generation"] == 2
assert json.loads(token)["metadata_sha256"] == first["metadata_sha256"]

# An unchanged cold restore must not churn the generation or the strict
# recipient's saved accepted hash.
unchanged_node = node_for(saved, token)
unchanged = unchanged_node._cache_shot_routing_snapshot(deepcopy(saved), normalized=True)
assert unchanged["generation"] == first["generation"]
assert unchanged["metadata_sha256"] == first["metadata_sha256"]

# A saved output token can be newer than the property generation if a save
# happened between the two writes. Keep the durable source cursor.
newer_token_node = node_for(saved)
newer_state = deepcopy(saved)
newer_state["shot_routing"]["generation"] = 3
newer_snapshot = newer_token_node._cache_shot_routing_snapshot(
    newer_state, normalized=True
)
newer_token = newer_token_node._shot_asset_dependency_token(newer_snapshot)
lagging_property_node = node_for(saved, newer_token)
lagging_property_snapshot = lagging_property_node._cache_shot_routing_snapshot(
    deepcopy(saved), normalized=True
)
assert lagging_property_snapshot["generation"] == 3
assert lagging_property_snapshot["metadata_sha256"] == newer_snapshot["metadata_sha256"]

# Before the first rich snapshot the private identity is empty. A project/Shot
# change still must publish a new generation; Picker rejects equal-generation
# different-hash catalogs by design.
changed = deepcopy(saved)
changed["shot_routing"]["shots"][0]["name"] = "Changed after reopen"
changed["shot_routing"]["shots"][0]["name_is_custom"] = True
changed = images._normalize_state(changed)
changed_node = node_for(changed, token)
revised = changed_node._cache_shot_routing_snapshot(deepcopy(changed), normalized=True)
assert revised["generation"] > first["generation"]
assert revised["metadata_sha256"] != first["metadata_sha256"]
assert changed_node._cache_shot_routing_snapshot(deepcopy(changed), normalized=True) == revised

project_changed = deepcopy(saved)
project_changed["project_id"] = "Katuri8"
project_changed = images._normalize_state(project_changed)
project_node = node_for(project_changed, token)
project_snapshot = project_node._cache_shot_routing_snapshot(
    deepcopy(project_changed), normalized=True
)
assert project_snapshot["project_id"] == "Katuri8"
assert project_snapshot["generation"] > first["generation"]
assert project_snapshot["metadata_sha256"] != first["metadata_sha256"]

# Validate the actual bounded catalog passed to VideoPicker, rather than only
# the richer source snapshot. The strict recipient must see the new generation.
changed_node._current_state = lambda: deepcopy(changed)
catalog = changed_node._hmb_shot_routing_catalog()
accepted = picker.HMBVideoPickerLibrary._validate_image_shot_catalog_snapshot(
    catalog, expected_channel_uuid=first["channel_uuid"]
)
assert accepted["generation"] > first["generation"]
assert accepted["publisher_instance_uuid"] == first["publisher_instance_uuid"]

print("PASS cold unchanged catalog stable; changed Shot/project monotonic for strict Picker")
