"""Explicit legacy rebinding preserves authoring and rolls back failed confirms."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import socket
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
import HMBPromptLibrary as prompt
import _hmb_workflow_migration as migration

CHANNEL = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ROWS = [dict(shot_uuid=f"cccccccc-cccc-4ccc-8ccc-{n:012d}", number=n,
    name=f"Current Asset {n}", revision=1) for n in range(1, 6)]
document = dict(channel_uuid=CHANNEL, generation=1, shots=ROWS)
CATALOG = dict(schema=prompt.SHOT_ROUTING_CATALOG_SCHEMA, version=1,
    publisher_instance_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", **document,
    metadata_sha256=prompt._canonical_sha256(document))


def create():
    node = prompt.HMBPromptLibrary(name="Legacy authored Prompt")
    state = prompt._normalize_state(prompt._default_widget_state())
    state["shot"] = dict(channel_uuid="old-channel", shot_uuid="old-shot", number=4,
        name="Original authored slot", selected_source_uids=[])
    state["text"][next(iter(prompt.TEXT_FIELD_DEFAULTS))] = "Keep exact literal {SIGN} / 0 / OFF"
    state["images"][0].update(label="Original actor", surface_2d=False)
    node._hmb_write_merged_prompt_state(prompt._json_dumps(state))
    prompt.set_output(node, "PROMPT_OUT", "Original compiled result")
    exported = node._hmb_prompt_merge_snapshot()
    info = dict(required=True, reason="Needs explicit confirmation", backup_path="private-backup.json",
        source_node_name=node.name, publisher_node_name="Current publisher",
        expected_source_digest=exported["state_sha256"])
    return node, state, info


def request(node, number=2):
    state = deepcopy(node._current_state())
    state["shot"] = {**ROWS[number - 1], "channel_uuid": CHANNEL}
    state["manual_rebind"]["confirmation"] = dict(channel_uuid=CHANNEL, shot_uuid=ROWS[number - 1]["shot_uuid"])
    state[prompt.UI_EDIT_REVISION_KEY] += 1
    return state


def send(node, state):
    node.set_parameter_value(prompt.WIDGET_PARAMETER_NAME, prompt._json_dumps(state))


def public_outputs(node):
    return {key: deepcopy(node.parameter_output_values.get(key)) for key in
        ("PROMPT_OUT", prompt.SHOT_IMAGE_OUTPUT_PARAMETER_NAME, prompt.SHOT_VIDEO_OUTPUT_PARAMETER_NAME)}

def difference(left, right, path=""):
    if type(left) is not type(right): return path, type(left).__name__, type(right).__name__
    if isinstance(left, dict):
        if left.keys() != right.keys(): return path, list(left), list(right)
        for key in left:
            if left[key] != right[key]: return difference(left[key], right[key], path+"/"+key)
    elif isinstance(left, list):
        if len(left) != len(right): return path, len(left), len(right)
        for index, item in enumerate(left):
            if item != right[index]: return difference(item, right[index], path+"/"+str(index))
    return path, left, right


def exercise():
    notification, state, info = create()
    original_outputs = public_outputs(notification)
    with mock.patch.object(notification, "publish_update_to_parameter", side_effect=ConnectionResetError(10054, "Synthetic editor disconnect")):
        assert notification._hmb_prepare_manual_rebind(CATALOG, info) is True
    assert notification._hmb_manual_rebind_pending()
    assert notification._hmb_manual_rebind["info"]["expected_source_digest"] == info["expected_source_digest"]
    assert public_outputs(notification) == original_outputs
    fast = prompt.HMBPromptLibrary(name="Unchanged pending fast path")
    raw = fast._hmb_prompt_merge_snapshot()["state"]
    fast._hmb_write_merged_prompt_state(prompt._json_dumps(raw))
    with mock.patch.object(fast, "_current_state", side_effect=AssertionError("Unchanged native state was parsed again")):
        assert fast._hmb_manual_rebind_pending() is False
    original_current = fast._current_state
    changed = deepcopy(raw)
    changed["manual_rebind"] = dict(required=True, expected_source_digest="a" * 64)
    with mock.patch.object(prompt, "_get_parameter_raw", return_value=prompt._json_dumps(changed)), \
            mock.patch.object(fast, "_current_state", wraps=original_current) as current:
        assert fast._hmb_manual_rebind_pending() is True
        current.assert_called_once()
    node, original, info = create()
    outputs = public_outputs(node)
    assert node._hmb_prepare_manual_rebind(CATALOG, info) is True
    current = node._current_state()
    assert current["shot"] == original["shot"]
    assert node._hmb_manual_rebind_authored(current) == node._hmb_manual_rebind_authored(original)
    assert public_outputs(node) == outputs
    assert len(current["image_asset"]["shot_catalog"]) == 5
    assert node._hmb_shot_channel_subscription()["enabled"] is False
    assert "private-backup.json" not in prompt._json_dumps(current)
    try:
        node.process()
    except RuntimeError as error:
        assert "rebind" in str(error)
    else:
        raise AssertionError("Unconfirmed legacy Prompt executed")
    absent = request(node)
    absent["manual_rebind"].pop("confirmation")
    send(node, absent)
    assert node._current_state()["shot"] == original["shot"]
    assert public_outputs(node) == outputs
    forged = request(node)
    forged["text"][next(iter(prompt.TEXT_FIELD_DEFAULTS))] = "Overwritten by a stale browser"
    with mock.patch.object(migration, "validate_manual_rebind", side_effect=AssertionError("CAS must reject first")):
        send(node, forged)
    assert node._current_state()["text"] == original["text"]
    assert public_outputs(node) == outputs

    def validate(owner, digest, **target):
        assert owner is node and digest == info["expected_source_digest"]
        assert owner._current_state()["shot"] == original["shot"]
        assert public_outputs(owner) == outputs
        assert target == dict(channel_uuid=CHANNEL, shot_uuid=ROWS[1]["shot_uuid"])
        return {"ok": True}

    def failed_confirm(owner, digest):
        assert owner._hmb_shot_channel_subscription()["shot_uuid"] == ROWS[1]["shot_uuid"]
        assert owner._hmb_shot_channel_subscription()["enabled"] is True
        assert owner.parameter_output_values["PROMPT_OUT"] == ""
        assert owner._hmb_manual_rebind_authored(owner._current_state()) == node._hmb_manual_rebind_authored(original)
        return {"ok": False}

    with mock.patch.object(migration, "validate_manual_rebind", side_effect=validate), \
            mock.patch.object(migration, "confirm_manual_rebind", side_effect=failed_confirm):
        send(node, request(node))
    assert node._current_state()["shot"] == original["shot"]
    assert public_outputs(node) == outputs
    assert node._hmb_manual_rebind_pending()
    assert node._hmb_manual_rebind_authored(node._current_state()) == node._hmb_manual_rebind_authored(original), {
        key: (value, node._hmb_manual_rebind_authored(node._current_state())[key])
        for key, value in node._hmb_manual_rebind_authored(original).items()
        if value != node._hmb_manual_rebind_authored(node._current_state())[key]}
    with mock.patch.object(migration, "validate_manual_rebind", side_effect=validate), \
            mock.patch.object(migration, "confirm_manual_rebind", return_value={"ok": True}):
        incoming = request(node)
        comparable = prompt._normalize_state(incoming)
        assert node._hmb_manual_rebind_authored(comparable) == node._hmb_manual_rebind_authored(original), difference(
            node._hmb_manual_rebind_authored(comparable), node._hmb_manual_rebind_authored(original))
        send(node, incoming)
    final = node._current_state()
    assert final["shot"]["shot_uuid"] == ROWS[1]["shot_uuid"], final.get("manual_rebind")
    assert node._hmb_manual_rebind_authored(final) == node._hmb_manual_rebind_authored(original)
    assert "manual_rebind" not in final and not node._hmb_manual_rebind_pending()
    assert node.parameter_output_values["PROMPT_OUT"] == ""
    assert node.parameter_output_values[prompt.SHOT_IMAGE_OUTPUT_PARAMETER_NAME] == []
    assert node.parameter_output_values[prompt.SHOT_VIDEO_OUTPUT_PARAMETER_NAME] == []
    assert node._hmb_apply_manual_rebind(request_data := {"shot": final["shot"]}) is False
    manager, state, info = create()
    state["multi_shot_enabled"] = True
    manager._hmb_write_merged_prompt_state(prompt._json_dumps(state))
    info["expected_source_digest"] = manager._hmb_prompt_merge_snapshot()["state_sha256"]
    assert manager._hmb_prepare_manual_rebind(CATALOG, info) is False
    print("PASS no guessed UUID; old slots/literals/results preserved; explicit legacy selection only; CAS/preflight rejection; failed confirm rollback; successful old-output invalidation; manager tabs excluded")


if __name__ == "__main__":
    with mock.patch.object(socket, "create_connection", side_effect=AssertionError("No network permitted")):
        exercise()
