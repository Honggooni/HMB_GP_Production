from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "HMBFinishLookLibrary.py"
spec = importlib.util.spec_from_file_location("_hmb_finish_look_regression_target", MODULE_PATH)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


def contains_forbidden_key(value):
    if isinstance(value, dict):
        return any(
            "grain" in str(key).casefold() or contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_forbidden_key(item) for item in value)
    return False


state = target.default_finish_look_state()
assert state["schema_version"] == 2
assert set(state) == {"schema_version", "beauty"}
assert state["beauty"]["enabled"] is False
assert state["beauty"]["soften_shadows"] == 0.11
assert state["beauty"]["shadow_threshold"] == 0.27
assert state["beauty"]["saturation"] == 1.0
assert state["beauty"]["brightness"] == 1.0
assert not contains_forbidden_key(state)
default_output = target.compile_finish_look_prompt(state)
assert default_output == target.EXPECTED_DEFAULT_FINISH_LOOK_OUT == ""
enabled_state = copy.deepcopy(state)
enabled_state["beauty"]["enabled"] = True
beauty_output = target.compile_finish_look_prompt(enabled_state)
assert beauty_output.startswith("CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE\n")
for text in (
    "Apply Character Beauty exclusively inside each visible character's matte and silhouette",
    "Exclude the background and environment completely",
    "must not alter their pixels, lighting, color, contrast, detail, or material response",
    "must not spill, feather, or propagate beyond the character matte",
    "character-surface brightness",
):
    assert text in beauty_output
for text in ("FILTER APPLICATION", "Kodak", "grain", "gamma", "printer-light", "vignette"):
    assert text not in beauty_output
assert target.compile_finish_look_prompt(copy.deepcopy(enabled_state)) == beauty_output
legacy = copy.deepcopy(enabled_state)
legacy["schema_version"] = 1
legacy["film"] = {"enabled": True, "negative_film": "Kodak 5245", "extra": "obsolete"}
assert target.validate_finish_look_state(legacy) == enabled_state
assert target.compile_finish_look_prompt(legacy) == beauty_output
legacy_widget = target.default_widget_state()
legacy_widget["finish_look"] = legacy
legacy_widget["catalog"] = {"negative": ["retired"]}
migrated = target.validate_widget_state(legacy_widget)
assert "catalog" not in migrated
assert migrated["finish_look"] == enabled_state
assert migrated["shot"] == legacy_widget["shot"]
for invalid_version in (True, 0, 3, "2"):
    invalid = copy.deepcopy(state)
    invalid["schema_version"] = invalid_version
    try:
        target.validate_finish_look_state(invalid)
    except target.FinishLookValidationError:
        pass
    else:
        raise AssertionError("Invalid version accepted")
invalid = copy.deepcopy(state)
invalid["film"] = {"enabled": True}
try:
    target.validate_finish_look_state(invalid)
except target.FinishLookValidationError:
    pass
else:
    raise AssertionError("New state reintroduced retired film")
# Explicit authoring tests use the opted-in state; new nodes below stay disabled.
state = enabled_state

negative_saturation = copy.deepcopy(state)
negative_saturation["beauty"]["saturation"] = -0.5
assert "restrained inverted-chroma response" in target.compile_finish_look_prompt(negative_saturation)

advanced_without_glow = copy.deepcopy(state)
advanced_without_glow["beauty"]["glow_threshold"] = 0.75
advanced_without_glow["beauty"]["glow_width"] = 48
advanced_without_glow["beauty"]["soft_focus"] = 0.2
advanced_output = target.compile_finish_look_prompt(advanced_without_glow)
assert "threshold 0.75" not in advanced_output
assert "glow width" not in advanced_output
assert "subtle character-surface soft-focus diffusion at value 0.2" in advanced_output

shadow_off = copy.deepcopy(state)
shadow_off["beauty"]["soften_shadows"] = 0
shadow_off_prompt = target.compile_finish_look_prompt(shadow_off)
shadow_off["beauty"]["shadow_threshold"] = 1
assert target.compile_finish_look_prompt(shadow_off) == shadow_off_prompt

retired_remote = {
    "schema": target.REMOTE_SCHEMA, "version": 1, "request_id": "retired-film",
    "base_revision": 0, "changes": {"film": {"enabled": True}},
}
try:
    target.apply_finish_look_remote_request(state, retired_remote)
except target.FinishLookValidationError:
    pass
else:
    raise AssertionError("Remote patch restored retired film")

beauty_glow = copy.deepcopy(state)
beauty_glow["beauty"]["glow_brightness"] = 0.2
beauty_glow["beauty"]["glow_threshold"] = 0.4
beauty_glow["beauty"]["glow_width"] = 22
beauty_glow_output = target.compile_finish_look_prompt(beauty_glow)
beauty_glow_index = beauty_glow_output.index("beauty glow")
assert beauty_glow_output.index("threshold 0.4", beauty_glow_index) > beauty_glow_index
assert beauty_glow_output.index("glow width of 22", beauty_glow_index) > beauty_glow_index
assert "beauty glow" in beauty_glow_output

invalid = copy.deepcopy(state)
invalid["beauty"]["preset"] = "Custom"
try:
    target.validate_finish_look_state(invalid)
except target.FinishLookValidationError as exc:
    assert "unsupported keys" in str(exc)
else:
    raise AssertionError("Beauty preset field was accepted")

for field, value in (
    (("beauty", "saturation"), float("nan")),
    (("beauty", "soften_shadows"), 1.01),
    (("beauty", "brightness"), -1),
    (("beauty", "reduce_shine"), 1.01),
    (("beauty", "glow_width"), -1),
    (("beauty", "enabled"), 1),
):
    invalid = copy.deepcopy(state)
    invalid[field[0]][field[1]] = value
    try:
        target.validate_finish_look_state(invalid)
    except target.FinishLookValidationError:
        pass
    else:
        raise AssertionError(f"Invalid field accepted: {field}")

remote_request = {
    "schema": target.REMOTE_SCHEMA,
    "version": 1,
    "request_id": "remote-1",
    "base_revision": 0,
    "changes": {"beauty": {"enabled": False}},
}
remote_state, remote_status = target.apply_finish_look_remote_request(state, remote_request, current_revision=0)
assert remote_state["beauty"]["enabled"] is False
assert remote_status["status"] == "accepted"
assert remote_status["revision"] == 1
stale_state, stale_status = target.apply_finish_look_remote_request(remote_state, remote_request, current_revision=1)
assert stale_state == remote_state
assert stale_status["code"] == "stale_revision"
try:
    target.normalize_remote_request('{"schema":"hmb-finish-look-remote-patch"}')
except target.FinishLookValidationError as exc:
    assert "dict object" in str(exc)
else:
    raise AssertionError("A JSON string bypassed strict dict-only remote ingress")
string_changes = copy.deepcopy(remote_request)
string_changes["changes"] = '{"beauty":{"enabled":false}}'
try:
    target.normalize_remote_request(string_changes)
except target.FinishLookValidationError as exc:
    assert "dict object" in str(exc)
else:
    raise AssertionError("A JSON string bypassed strict dict-only remote changes")

state = target.default_finish_look_state()
node = target.HMBFinishLookLibrary(name="Finish Look Regression")


def parameter_map(test_node):
    """Normalize fallback-dict and real Griptape list parameter stores."""

    parameters = test_node.parameters
    if isinstance(parameters, dict):
        return parameters
    return {parameter.name: parameter for parameter in parameters}


parameters = parameter_map(node)
required_parameters = {
    target.WIDGET_PARAMETER_NAME,
    target.REMOTE_INPUT_PARAMETER_NAME,
    target.FINISH_LOOK_OUTPUT_PARAMETER_NAME,
    target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
    target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME,
    target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME,
}
assert required_parameters.issubset(parameters)
assert not any("VIDEO_TOOL" in name or name in {"SHOT_PICKER_IN", "CROP_VIDEO_IN", "HMB_FINISH_LOOK_TOOL_COMMAND"} for name in parameters)
assert not any(key.startswith("video_") or key in {"picker_source", "command"} for key in node._widget_state)
assert parameters[target.REMOTE_INPUT_PARAMETER_NAME].input_types == ["dict"]
assert node.ui_options["width"] == target.FINISH_LOOK_NODE_WIDTH == 980
assert node.ui_options["height"] == target.FINISH_LOOK_NODE_HEIGHT == 1040
assert node.ui_options["node_size"] == {"width": 980, "height": 1040}
widget_parameter = parameters[target.WIDGET_PARAMETER_NAME]
widget_ui = widget_parameter.ui_options
assert widget_ui["height"] == target.FINISH_LOOK_WIDGET_HEIGHT == 940
assert widget_ui["min_height"] == target.FINISH_LOOK_WIDGET_MIN_HEIGHT == 720
assert widget_ui["width"] == target.FINISH_LOOK_NODE_WIDTH
assert widget_ui["preferred_height"] == target.FINISH_LOOK_WIDGET_HEIGHT
assert widget_ui["node_size"] == {"width": 980, "height": 1040}
assert widget_ui["expandable"] is True
assert widget_ui["compact"] is False
assert getattr(widget_parameter, "hide", False) is False
for hidden_name in (
    target.REMOTE_INPUT_PARAMETER_NAME,
    target.FINISH_LOOK_OUTPUT_PARAMETER_NAME,
    target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME,
    target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME,
    target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME,
):
    hidden_parameter = parameters[hidden_name]
    assert getattr(hidden_parameter, "hide", False) is True
    assert getattr(hidden_parameter, "hide_property", False) is True
    assert hidden_parameter.ui_options["hide"] is True
    assert hidden_parameter.ui_options["hide_handles"] is True
    assert hidden_parameter.ui_options["height"] == 1
    assert hidden_parameter.ui_options["expandable"] is False
# A serialized workflow may replay stale allocator hints. Hydration must repair
# the surface without altering the saved Finish Look values.
saved_finish_before_ui_repair = copy.deepcopy(node._last_valid_state)
parameters[target.WIDGET_PARAMETER_NAME].ui_options["expandable"] = False
parameters[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME].hide = False
parameters[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME].ui_options = {
    "display_name": target.FINISH_LOOK_OUTPUT_PARAMETER_NAME,
    "height": 40,
}
node.after_deserialize()
assert parameters[target.WIDGET_PARAMETER_NAME].ui_options["expandable"] is True
assert parameters[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME].hide is True
assert parameters[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME].ui_options["hide_handles"] is True
assert node._last_valid_state == saved_finish_before_ui_repair
assert node.parameter_output_values[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME] == default_output
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == state
assert node.parameter_output_values[target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME] == {}
assert node._hmb_shot_channel_subscription() == {
    "schema": target.SHOT_SUBSCRIPTION_SCHEMA,
    "version": target.SHOT_SUBSCRIPTION_VERSION,
    "participant_kind": "finish_look",
    "enabled": False,
    "channel_uuid": "",
    "shot_uuid": "",
    "shot_number": 1,
    "shot_name": "Only",
}


def shot_catalog(*, generation=1):
    shots = [
        {"shot_uuid": "shot-one", "number": 1, "name": "Opening", "revision": 2},
        {"shot_uuid": "shot-two", "number": 2, "name": "Bridge", "revision": 3},
        {"shot_uuid": "shot-three", "number": 3, "name": "Forest", "revision": 4},
        {"shot_uuid": "shot-four", "number": 4, "name": "Flight", "revision": 6},
        {"shot_uuid": "shot-five", "number": 5, "name": "Finale", "revision": 8},
    ]
    document = {
        "channel_uuid": "finish-channel",
        "generation": generation,
        "shots": shots,
    }
    return {
        "schema": target.SHOT_ROUTING_CATALOG_SCHEMA,
        "version": target.SHOT_ROUTING_CATALOG_VERSION,
        "publisher_instance_uuid": "image-publisher",
        **document,
        "metadata_sha256": hashlib.sha256(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


# Finish Look is the sixth UUID-bound library. Its local selector projection
# may be sparse (1/3/5 here because peer Finish nodes own 2/4), adopts the
# router-proven initial UUID, and publishes one atomic hidden sidecar without
# mutating any authored Beauty or Film value. The authenticated
# ImageAsset source catalog itself remains contiguous by protocol.
import _hmb_shot_routing as shot_routing

original_same_flow_nodes = shot_routing._same_flow_nodes


class ClaimedFinishShot:
    def __init__(self, shot_uuid, number, name):
        self._shot_uuid = shot_uuid
        self._number = number
        self._name = name

    def _hmb_shot_channel_subscription(self):
        return {
            "participant_kind": "finish_look",
            "enabled": True,
            "channel_uuid": "finish-channel",
            "shot_uuid": self._shot_uuid,
            "shot_number": self._number,
            "shot_name": self._name,
        }


claimed_two = ClaimedFinishShot("shot-two", 2, "Bridge")
claimed_four = ClaimedFinishShot("shot-four", 4, "Flight")
shot_routing._same_flow_nodes = lambda _node: (
    "FinishRegressionFlow",
    [node, claimed_two, claimed_four],
)
before_shot_finish = copy.deepcopy(
    node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME]
)
node._hmb_prepare_initial_shot_selection("shot-three")
node._hmb_reconcile_shot_routing(shot_catalog())
subscription = node._hmb_shot_channel_subscription()
assert subscription["enabled"] is True
assert subscription["channel_uuid"] == "finish-channel"
assert subscription["shot_uuid"] == "shot-three"
assert subscription["shot_number"] == 3
assert subscription["shot_name"] == "Forest"
assert [item["number"] for item in node._widget_state["shot_catalog"]["shots"]] == [1, 3, 5]
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == before_shot_finish

# A user-driven Shot selector change clears Shot-owned video selections before
# the newly selected Picker snapshot hydrates, preventing cross-Shot media use.
shot_change_widget = copy.deepcopy(node._widget_state)
shot_change_widget["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-one",
    "number": 1,
    "name": "Opening",
}
node._hmb_shot_catalog_syncing = True
try:
    node._apply_widget_value(shot_change_widget)
finally:
    node._hmb_shot_catalog_syncing = False
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-one"
shot_restore_widget = copy.deepcopy(node._widget_state)
shot_restore_widget["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-three",
    "number": 3,
    "name": "Forest",
}
node._hmb_shot_catalog_syncing = True
try:
    node._apply_widget_value(shot_restore_widget)
finally:
    node._hmb_shot_catalog_syncing = False
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-three"


finish_snapshot = node.parameter_output_values[target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME]
assert finish_snapshot == node._hmb_finish_look_shot_snapshot(finish_snapshot)
assert finish_snapshot["schema"] == target.FINISH_LOOK_SHOT_SNAPSHOT_SCHEMA
assert finish_snapshot["version"] == target.FINISH_LOOK_SHOT_SNAPSHOT_VERSION == 2
assert finish_snapshot["finish_look_state"] == node._last_valid_state
assert finish_snapshot["state_sha256"] == target._canonical_sha256(finish_snapshot["finish_look_state"])
assert finish_snapshot["shot_uuid"] == "shot-three"
assert finish_snapshot["finish_look_out"] == default_output
assert finish_snapshot["finish_look_sha256"] == hashlib.sha256(
    default_output.encode("utf-8")
).hexdigest()
assert finish_snapshot["state_sha256"] == hashlib.sha256(
    json.dumps(
        before_shot_finish,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
first_snapshot_generation = finish_snapshot["generation"]

# Hidden Shot publication is retryable. A transient host publication failure
# must not advance the live fingerprint or mark the route ready, otherwise the
# same exact snapshot would be suppressed forever.
publish_attempts = []


def flaky_finish_publish(name, value):
    if name == target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME:
        publish_attempts.append(copy.deepcopy(value))
        if len(publish_attempts) == 1:
            raise RuntimeError("transient publish failure")


node.publish_update_to_parameter = flaky_finish_publish
assert node._hmb_publish_routed_finish_snapshot(force=True) is False
assert node._hmb_finish_route_ready is False
assert node._hmb_finish_snapshot_live_fingerprint != node._hmb_finish_snapshot_fingerprint
assert node._hmb_publish_routed_finish_snapshot() is True
assert len(publish_attempts) == 2
assert node._hmb_finish_route_ready is True
assert node._hmb_finish_snapshot_live_fingerprint == node._hmb_finish_snapshot_fingerprint

# A newer catalog generation keeps selection by UUID even if display metadata
# changes; the snapshot advances once and carries the renamed Shot identity.
renamed_catalog = shot_catalog(generation=2)
renamed_catalog["shots"][2]["name"] = "Forest Dawn"
renamed_document = {
    "channel_uuid": renamed_catalog["channel_uuid"],
    "generation": renamed_catalog["generation"],
    "shots": renamed_catalog["shots"],
}
renamed_catalog["metadata_sha256"] = hashlib.sha256(
    json.dumps(
        renamed_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
node._hmb_reconcile_shot_routing(renamed_catalog)
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-three"
assert node._hmb_shot_channel_subscription()["shot_name"] == "Forest Dawn"
persisted_round_trip = target.validate_widget_state(copy.deepcopy(node._widget_state))
assert persisted_round_trip["shot"] == {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-three",
    "number": 3,
    "name": "Forest Dawn",
}
assert [
    item["number"] for item in persisted_round_trip["shot_catalog"]["shots"]
] == [1, 3, 5]
renamed_snapshot = node.parameter_output_values[target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME]
assert renamed_snapshot["generation"] == first_snapshot_generation + 1
assert renamed_snapshot["finish_look_out"] == default_output

# A Shot selection change stages its new snapshot before routing. If rerouting
# is temporarily unavailable, ordinary live UI publication must not leak the
# new Shot snapshot through the prior Shot's retained hidden edge. Once the
# router proves/attaches the exact edge, a forced publication hydrates it.
hidden_after_failed_reroute = []
node.publish_update_to_parameter = lambda name, value: (
    hidden_after_failed_reroute.append(copy.deepcopy(value))
    if name == target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME
    else None
)
node._reconcile_shared_shot_routing = lambda **_kwargs: {
    "ok": False,
    "code": "unavailable",
    "changed": 0,
}
shot_five_edit = copy.deepcopy(node._widget_state)
shot_five_edit["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-five",
    "number": 5,
    "name": "Finale",
}
node._apply_widget_value(shot_five_edit)
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-five"
assert node._hmb_finish_route_ready is False
assert hidden_after_failed_reroute == []
assert node._hmb_publish_routed_finish_snapshot(force=True) is True
assert len(hidden_after_failed_reroute) == 1
assert hidden_after_failed_reroute[0]["shot_uuid"] == "shot-five"

# Return to the renamed Shot for the remaining persistence checks.
del node._reconcile_shared_shot_routing
restore_shot_three = copy.deepcopy(node._widget_state)
restore_shot_three["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-three",
    "number": 3,
    "name": "Forest Dawn",
}
node._hmb_shot_catalog_syncing = True
try:
    node._apply_widget_value(restore_shot_three)
finally:
    node._hmb_shot_catalog_syncing = False
assert node._hmb_publish_routed_finish_snapshot(force=True) is True

try:
    node._hmb_finish_look_shot_snapshot({"stale": True})
except RuntimeError as exc:
    assert "does not match" in str(exc)
else:
    raise AssertionError("Seedance could request a mismatched Finish Look snapshot")

# Only and duplicate rejection release the UUID but preserve all authored
# values. Re-selecting from the persisted sparse catalog reconstructs the exact
# same finish instruction and state.
preserved_finish = copy.deepcopy(node._last_valid_state)
duplicate_subscription = node._hmb_reject_duplicate_shot_selection()
assert duplicate_subscription["enabled"] is False
assert duplicate_subscription["shot_name"] == "Only"
assert node._last_valid_state == preserved_finish
assert node.parameter_output_values[target.SHOT_FINISH_LOOK_OUTPUT_PARAMETER_NAME] == {}

persisted_widget = copy.deepcopy(node._widget_state)
persisted_widget["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-five",
    "number": 5,
    "name": "Finale",
}
node._hmb_shot_catalog_syncing = True
try:
    node._apply_widget_value(persisted_widget)
finally:
    node._hmb_shot_catalog_syncing = False
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-five"
assert node._last_valid_state == preserved_finish
node._hmb_clear_shot_routing_catalog("publisher_unavailable")
assert node._hmb_shot_channel_subscription()["enabled"] is False
assert node._last_valid_state == preserved_finish
shot_routing._same_flow_nodes = original_same_flow_nodes

widget_state = target.default_widget_state()
widget_state["language"] = "en"
widget_state["finish_look"]["beauty"]["enabled"] = False
node.after_value_set(parameters[target.WIDGET_PARAMETER_NAME], widget_state)
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME]["beauty"]["enabled"] is False
assert node.parameter_output_values[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME] == ""
local_revision = node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["revision"]
assert local_revision == 0  # New default OFF; language-only edits do not author a look.

node_remote = {
    "schema": target.REMOTE_SCHEMA,
    "version": 1,
    "request_id": "node-remote-1",
    "base_revision": local_revision,
    "changes": {"beauty": {"enabled": True}},
}
node.after_value_set(parameters[target.REMOTE_INPUT_PARAMETER_NAME], node_remote)
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME]["beauty"]["enabled"] is True
first_status = copy.deepcopy(node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME])
assert first_status["status"] == "accepted"
node.after_value_set(parameters[target.REMOTE_INPUT_PARAMETER_NAME], node_remote)
assert node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["code"] == "duplicate_request"

malformed_remote = {"schema": "wrong", "version": 1}
assert (
    node.before_value_set(parameters[target.REMOTE_INPUT_PARAMETER_NAME], malformed_remote)
    == malformed_remote
)
node.after_value_set(parameters[target.REMOTE_INPUT_PARAMETER_NAME], malformed_remote)
assert node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["status"] == "rejected"
assert node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["code"] == "invalid_request"
# An actual remote cable locks only Finish authoring. Language
# remains locally usable, and disconnect preserves the last
# canonical Finish state.
node.after_incoming_connection(None, None, parameters[target.REMOTE_INPUT_PARAMETER_NAME])
assert node._widget_state["remote_connected"] is True
locked_before = copy.deepcopy(node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME])
locked_edit = copy.deepcopy(node._widget_state)
locked_edit["finish_look"]["beauty"]["brightness"] = 2.0
locked_edit["language"] = "ko"
node.after_value_set(parameters[target.WIDGET_PARAMETER_NAME], locked_edit)
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == locked_before
assert node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["code"] == "remote_locked"
assert node._widget_state["language"] == "ko"

# REMOTE is an authoring lock, not Shot ownership. A UUID-only selector change
# remains available and does not rewrite the remotely controlled Finish values.
node._hmb_shot_catalog_snapshot = copy.deepcopy(renamed_catalog)
remote_shot_edit = copy.deepcopy(node._widget_state)
remote_shot_edit["shot_catalog"] = node._hmb_available_finish_shot_catalog(
    renamed_catalog,
    {},
)
remote_shot_edit["shot"] = {
    "channel_uuid": "finish-channel",
    "shot_uuid": "shot-one",
    "number": 1,
    "name": "Opening",
}
node._hmb_shot_catalog_syncing = True
try:
    node.after_value_set(parameters[target.WIDGET_PARAMETER_NAME], remote_shot_edit)
finally:
    node._hmb_shot_catalog_syncing = False
assert node._hmb_shot_channel_subscription()["shot_uuid"] == "shot-one"
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == locked_before
node.after_incoming_connection_removed(None, None, parameters[target.REMOTE_INPUT_PARAMETER_NAME])
assert node._widget_state["remote_connected"] is False
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == locked_before

before_invalid = copy.deepcopy(node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME])
invalid_widget = target.default_widget_state()
invalid_widget["finish_look"]["beauty"]["brightness"] = -1
node.after_value_set(parameters[target.WIDGET_PARAMETER_NAME], invalid_widget)
assert node.parameter_output_values[target.FINISH_LOOK_STATE_OUTPUT_PARAMETER_NAME] == before_invalid
assert node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["code"] == "invalid_ui_state"

print(
    "HMB Finish Look regression: PASS "
    "(character-matte-only opt-in Beauty, retired-film migration, deterministic compiler, "
    "strict remote patch, "
    "UUID Shot routing and finishing-only surface)"
)
