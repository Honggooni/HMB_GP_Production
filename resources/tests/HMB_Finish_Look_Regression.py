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
assert state["schema_version"] == 1
assert state["beauty"]["enabled"] is True
assert "preset" not in state["beauty"]
assert state["beauty"]["soften_shadows"] == 0.11
assert state["beauty"]["shadow_threshold"] == 0.27
assert state["beauty"]["saturation"] == 1.0
assert state["beauty"]["brightness"] == 1.0
assert state["film"]["negative_film"] == "Kodak 5245"
assert state["film"]["print_film"] == "Kodak 2383"
assert state["film"]["scale_cc"] == 0.3
assert (
    state["film"]["printer_light_r"],
    state["film"]["printer_light_g"],
    state["film"]["printer_light_b"],
) == (26, 25, 24)
assert state["film"]["negative_exposure"] == 0.0
assert state["film"]["print_exposure"] == 0.0
assert state["film"]["glow_brightness"] == 0.1
assert not contains_forbidden_key(state)

default_output = target.compile_finish_look_prompt(state)
assert default_output == target.EXPECTED_DEFAULT_FINISH_LOOK_OUT
assert target.compile_finish_look_prompt(copy.deepcopy(state)) == default_output
assert default_output == default_output.strip()
assert "\r" not in default_output
assert not default_output.endswith("\n")
character_beauty_block, filter_application_block = default_output.split("\n\n", 1)
assert character_beauty_block.startswith("CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE\n")
assert filter_application_block.startswith("FILTER APPLICATION — FULL-FRAME SCOPE\n")
assert default_output.count("CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE") == 1
assert default_output.count("FILTER APPLICATION — FULL-FRAME SCOPE") == 1
assert "Apply Character Beauty exclusively inside each visible character's matte and silhouette" in character_beauty_block
assert "Exclude the background and environment completely" in character_beauty_block
assert "must not alter their pixels, lighting, color, contrast, detail, or material response" in character_beauty_block
assert "must not spill, feather, or propagate beyond the character matte" in character_beauty_block
assert "complete already-resolved final frame as one post-process" in filter_application_block
assert "all characters, the complete background and environment, and resolved FX" in filter_application_block
assert "This full-frame filter may change only the final image response" in filter_application_block
assert "do not change character identity or design" in filter_application_block
assert "established lighting direction" in filter_application_block
assert "overall brightness" not in character_beauty_block
assert "character-surface brightness" in character_beauty_block
assert "exposure" not in default_output.casefold()
assert "Kodak 5245" in default_output
assert "Kodak 2383" in default_output
assert "cyan-blue" in default_output
assert "warm printer-light" not in default_output
assert "red over blue" not in default_output
assert default_output.endswith("Do not introduce or simulate any film grain.")

beauty_off = copy.deepcopy(state)
beauty_off["beauty"]["enabled"] = False
beauty_off_output = target.compile_finish_look_prompt(beauty_off)
assert "CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE" not in beauty_off_output
assert beauty_off_output.startswith("FILTER APPLICATION — FULL-FRAME SCOPE")
assert "Apply a clean Kodak 5245" in beauty_off_output
assert "\n\n" not in beauty_off_output

film_off = copy.deepcopy(state)
film_off["film"]["enabled"] = False
film_off_output = target.compile_finish_look_prompt(film_off)
assert film_off_output.startswith("CHARACTER BEAUTY — CHARACTER-MATTE-ONLY SCOPE")
assert "FILTER APPLICATION — FULL-FRAME SCOPE" not in film_off_output
assert "Kodak" not in film_off_output
assert "film grain" not in film_off_output.casefold()

both_off = copy.deepcopy(state)
both_off["beauty"]["enabled"] = False
both_off["film"]["enabled"] = False
assert target.compile_finish_look_prompt(both_off) == ""

changed_stock = copy.deepcopy(state)
changed_stock["film"]["negative_film"] = "Kodak 5218"
assert changed_stock["film"]["print_film"] == "Kodak 2383"
assert "Kodak 5218" in target.compile_finish_look_prompt(changed_stock)

reversal = copy.deepcopy(state)
reversal["film"]["print_film"] = "Kodak 5285 Rev"
reversal_output = target.compile_finish_look_prompt(reversal)
assert "a clean Kodak 5285 Rev reversal-film response" in reversal_output
assert "Kodak 5245" not in reversal_output

no_stocks = copy.deepcopy(state)
no_stocks["film"]["negative_film"] = "None"
no_stocks["film"]["print_film"] = "None"
no_stocks_output = target.compile_finish_look_prompt(no_stocks)
for omitted in ("Kodak", "gamma", "printer-light", "exposure"):
    assert omitted not in no_stocks_output.casefold()
assert "highlight glow" in no_stocks_output
assert no_stocks_output.endswith("Do not introduce or simulate any film grain.")

scale_off = copy.deepcopy(state)
scale_off["film"]["scale_cc"] = 0.0
scale_off_output = target.compile_finish_look_prompt(scale_off)
for omitted in ("Kodak", "gamma", "printer-light", "exposure"):
    assert omitted not in scale_off_output.casefold()
assert "highlight glow" in scale_off_output

neutral_printer = copy.deepcopy(state["film"])
neutral_printer.update(printer_light_r=25, printer_light_g=25, printer_light_b=25)
assert target.compile_printer_lights_prompt(neutral_printer) == "Use a neutral printer-light balance."

density_printer = copy.deepcopy(state["film"])
density_printer.update(printer_light_r=26, printer_light_g=26, printer_light_b=26)
density_phrase = target.compile_printer_lights_prompt(density_printer)
assert "very subtle darker printer-light density" in density_phrase
assert "no color bias" in density_phrase

default_analysis = target.analyze_printer_lights(26, 25, 24)
assert default_analysis["colors"] == ["cyan", "blue"]
assert default_analysis["temperature"] == "cool"
assert math.isclose(default_analysis["common_density"], 0.0)

for field, value, expected in (
    ("negative_exposure", 0.5, "brighter negative response"),
    ("negative_exposure", -0.5, "darker negative response"),
    ("print_exposure", 0.5, "darker print response"),
    ("print_exposure", -0.5, "lighter print response"),
):
    film = copy.deepcopy(state["film"])
    film[field] = value
    assert expected in target.compile_exposure_prompt(film)

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

beauty_glow = copy.deepcopy(state)
beauty_glow["beauty"]["glow_brightness"] = 0.2
beauty_glow["beauty"]["glow_threshold"] = 0.4
beauty_glow["beauty"]["glow_width"] = 22
beauty_glow_output = target.compile_finish_look_prompt(beauty_glow)
beauty_glow_index = beauty_glow_output.index("beauty glow")
assert beauty_glow_output.index("threshold 0.4", beauty_glow_index) > beauty_glow_index
assert beauty_glow_output.index("glow width of 22", beauty_glow_index) > beauty_glow_index
assert "highlight glow" in beauty_glow_output

film_advanced = copy.deepcopy(state)
film_advanced["film"]["soft_focus"] = 0.2
film_advanced["film"]["vignette"] = 0.4
film_advanced_output = target.compile_finish_look_prompt(film_advanced)
assert "subtle soft-focus response at value 0.2" in film_advanced_output
assert "moderate corner vignette at value 0.4" in film_advanced_output

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
    (("film", "scale_cc"), 5.01),
    (("film", "input_gamma"), 0.09),
    (("film", "vignette"), 1.01),
    (("film", "printer_light_r"), 25.5),
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
assert finish_snapshot["version"] == target.FINISH_LOOK_SHOT_SNAPSHOT_VERSION
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
assert node.parameter_output_values[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME].startswith(
    "FILTER APPLICATION — FULL-FRAME SCOPE"
)
assert "Apply a clean Kodak 5245" in node.parameter_output_values[target.FINISH_LOOK_OUTPUT_PARAMETER_NAME]
local_revision = node.parameter_output_values[target.REMOTE_STATUS_OUTPUT_PARAMETER_NAME]["revision"]
assert local_revision == 1

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
locked_edit["finish_look"]["film"]["enabled"] = False
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
    "(character-matte-only Character Beauty, full-frame Filter Application, deterministic compiler, "
    "strict remote patch, "
    "UUID Shot routing and finishing-only surface)"
)
