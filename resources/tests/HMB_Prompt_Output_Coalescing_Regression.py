from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
from types import MethodType, SimpleNamespace
import sys
import types


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    module_name = f"_hmb_prompt_output_coalescing_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def assert_paired_snapshot(node, visible: str, machine: str, generation: int):
    snapshot = node._hmb_agent_prompt_snapshot(visible)
    assert snapshot == {
        "schema": "hmb-prompt-paired-snapshot",
        "version": 1,
        "generation": generation,
        "visible_sha256": digest(visible),
        "machine_sha256": digest(machine),
        "machine_prompt": machine,
    }
    return snapshot


prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")


# Prompt -> Agent keeps one exact native edge and its compact geometry. The
# visible value is human-readable; the exact typed envelope is retrieved from
# the source node's generation-paired private snapshot.
output_kwargs = prompt._prompt_output_kwargs()
assert output_kwargs["name"] == agent._HMB_PROMPT_OUTPUT_PARAMETER == "PROMPT_OUT"
assert agent._AGENT_PROMPT_INPUT_PARAMETER == "prompt"
assert output_kwargs["allow_input"] is False
assert output_kwargs["allow_output"] is True
assert output_kwargs["allow_property"] is False
assert output_kwargs["ui_options"]["display_name"] == ""
assert output_kwargs["ui_options"]["compact"] is True
assert output_kwargs["ui_options"]["height"] == 1
assert output_kwargs["ui_options"]["hide"] is True
assert output_kwargs["ui_options"]["hide_handles"] is True


node = prompt.HMBPromptLibrary(name="prompt_output_coalescing")
assert node.width == 1800
assert node.height == prompt.PROMPT_START_HEIGHT
assert node.ui_options["node_size"] == {
    "width": 1800,
    "height": prompt.PROMPT_START_HEIGHT,
}
assert node.ui_options["min_width"] == 760
assert node.ui_options["min_height"] == prompt.PROMPT_MIN_HEIGHT

base_state = prompt._normalize_state(prompt._default_widget_state())
base_visible = prompt._build_prompt_package(base_state)
base_machine = prompt._build_data_only_prompt_package(base_state)
node._hmb_last_prompt_semantic_fingerprint = prompt._prompt_semantic_fingerprint(
    base_state,
    public_prompt=base_visible,
    machine_prompt=base_machine,
)
node._hmb_last_prompt_output = base_visible
node._hmb_last_machine_prompt_output = base_machine
node._hmb_prompt_snapshot_generation = 1
node.parameter_output_values["PROMPT_OUT"] = base_visible
assert_paired_snapshot(node, base_visible, base_machine, 1)


def install_dashboard_state(state):
    """Mirror the real writer: persist state before compiling/publishing it."""

    encoded = prompt._json_dumps(state)
    parameter_values = getattr(node, "parameter_values", None)
    if isinstance(parameter_values, dict):
        parameter_values[prompt.WIDGET_PARAMETER_NAME] = encoded
    else:
        parameter = prompt._get_parameter_obj(
            node, prompt.WIDGET_PARAMETER_NAME
        )
        if parameter is None:
            raise AssertionError("Prompt widget state parameter is missing")
        parameter.default_value = encoded
    node._write_dashboard_state = lambda: copy.deepcopy(state)

try:
    node._hmb_agent_prompt_snapshot(base_visible + "stale")
except RuntimeError as error:
    assert "paired snapshot is unavailable" in str(error)
else:
    raise AssertionError("A visible value from another generation was accepted.")


visible_build_calls = []
machine_build_calls = []
set_calls = []
notify_calls = []
original_visible_build = prompt._build_prompt_package
original_machine_build = prompt._build_data_only_prompt_package
original_set_output = prompt.set_output


def counting_visible_build(state):
    visible_build_calls.append(copy.deepcopy(state))
    return original_visible_build(state)


def counting_machine_build(state):
    machine_build_calls.append(copy.deepcopy(state))
    return original_machine_build(state)


def counting_set_output(target, name, value):
    set_calls.append((name, value))
    return original_set_output(target, name, value)


def counting_notify(name, value):
    assert name == "PROMPT_OUT"
    assert node.parameter_output_values["PROMPT_OUT"] == value, (
        "PROMPT_OUT must be staged before a connected Agent is notified."
    )
    assert node._hmb_last_prompt_output == value
    snapshot = assert_paired_snapshot(
        node,
        value,
        node._hmb_last_machine_prompt_output,
        node._hmb_prompt_snapshot_generation,
    )
    notify_calls.append((name, value, snapshot))


try:
    prompt._build_prompt_package = counting_visible_build
    prompt._build_data_only_prompt_package = counting_machine_build
    prompt.set_output = counting_set_output
    node.publish_update_to_parameter = counting_notify

    # A UI-only mutation compiles to the same visible/machine pair. It must not
    # advance the paired generation or touch/notify the native output port.
    ui_only_state = copy.deepcopy(base_state)
    ui_only_state["ui"]["theme"] = "T"
    ui_only_state["ui"]["language"] = "en"
    ui_only_state["ui"]["group_heights"]["imageSources"] = 777
    install_dashboard_state(ui_only_state)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 1
    assert node._hmb_last_prompt_output == base_visible
    assert node._hmb_last_machine_prompt_output == base_machine
    assert set_calls == []
    assert notify_calls == []
    assert_paired_snapshot(node, base_visible, base_machine, 1)

    # USER DESCRIPTION DATA is private machine input, not part of the visible
    # five-section document. A text edit must still create a new atomic snapshot
    # generation even though the native PROMPT_OUT bytes are unchanged. The
    # same visible value is republished without another native set so the
    # connected Agent wakes and retrieves the newer private snapshot.
    text_state = copy.deepcopy(base_state)
    text_state["text"]["SCENE_CONTEXT"] = "User-authored scene description."
    install_dashboard_state(text_state)
    node._sync_prompt_output_from_state()
    text_visible = node._hmb_last_prompt_output
    text_machine = node._hmb_last_machine_prompt_output
    assert text_visible == base_visible
    assert text_machine != base_machine
    assert "User-authored scene description." in text_machine
    assert node._hmb_prompt_snapshot_generation == 2
    assert node.parameter_output_values["PROMPT_OUT"] == base_visible
    assert [name for name, _value in set_calls] == [
        prompt.SHOT_IMAGE_OUTPUT_PARAMETER_NAME,
        prompt.SHOT_VIDEO_OUTPUT_PARAMETER_NAME,
    ]
    assert len(notify_calls) == 1
    assert notify_calls[-1][:2] == ("PROMPT_OUT", base_visible)
    assert notify_calls[-1][2]["machine_prompt"] == text_machine
    assert notify_calls[-1][2]["generation"] == 2
    assert_paired_snapshot(node, text_visible, text_machine, 2)

    # Local connector diagnostics affect neither representation and therefore
    # remain coalesced with the current paired generation.
    local_only_state = copy.deepcopy(text_state)
    local_only_state["source_intent_fallbacks"] = [
        {"source": "PICKER_IN", "reason": "diagnostic", "text": "local only"}
    ]
    install_dashboard_state(local_only_state)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 2
    assert node._hmb_last_prompt_output == text_visible
    assert node._hmb_last_machine_prompt_output == text_machine
    assert len(set_calls) == 2
    assert len(notify_calls) == 1

    # A visible semantic mutation updates both cache members before synchronous
    # publication. The callback reads exactly the newly paired machine envelope.
    semantic_state = copy.deepcopy(local_only_state)
    semantic_state["images"][0].update(
        {
            "present": True,
            "label": "CoalescingHero",
            "asset_id": "CoalescingHeroAsset",
            "asset_source_uid": "coalescing-image-source-uid",
            "source_type": "Character Appearance",
            "owner": "CoalescingHero",
        }
    )
    install_dashboard_state(semantic_state)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 3
    assert [name for name, _value in set_calls[-3:]] == [
        prompt.SHOT_IMAGE_OUTPUT_PARAMETER_NAME,
        prompt.SHOT_VIDEO_OUTPUT_PARAMETER_NAME,
        "PROMPT_OUT",
    ]
    assert len(set_calls) == 5
    assert len(notify_calls) == 2
    assert set_calls[-1] == notify_calls[-1][:2]
    semantic_visible = node._hmb_last_prompt_output
    semantic_machine = node._hmb_last_machine_prompt_output
    assert semantic_visible != text_visible
    assert semantic_machine != text_machine
    assert notify_calls[-1][2]["machine_prompt"] == semantic_machine
    assert notify_calls[-1][2]["generation"] == 3

    semantic_ui_only = copy.deepcopy(semantic_state)
    semantic_ui_only["ui"]["theme"] = "T"
    semantic_ui_only["ui"]["group_heights"]["imageSources"] = 888
    install_dashboard_state(semantic_ui_only)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 3
    assert len(set_calls) == 5
    assert len(notify_calls) == 2
    assert_paired_snapshot(node, semantic_visible, semantic_machine, 3)

    # If an external host clears the visible output, the cached paired snapshot
    # repairs it without advancing the generation.
    node.parameter_output_values["PROMPT_OUT"] = ""
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 3
    assert set_calls[-1] == ("PROMPT_OUT", semantic_visible)
    assert notify_calls[-1][:2] == ("PROMPT_OUT", semantic_visible)
    assert notify_calls[-1][2]["machine_prompt"] == semantic_machine
    assert len(set_calls) == 6
    assert len(notify_calls) == 3

    # A transport failure occurs only after both snapshot members and the
    # generation have advanced. Retrying republishes that same pair.
    failed_notifications = []

    def failing_notify(name, value):
        assert node.parameter_output_values[name] == value
        assert node._hmb_last_prompt_output == value
        snapshot = assert_paired_snapshot(
            node,
            value,
            node._hmb_last_machine_prompt_output,
            node._hmb_prompt_snapshot_generation,
        )
        failed_notifications.append((name, value, snapshot))
        raise ValueError("simulated Agent notification failure")

    failure_state = copy.deepcopy(semantic_ui_only)
    failure_state["images"][0]["label"] = "NotificationFailureHero"
    install_dashboard_state(failure_state)
    node.publish_update_to_parameter = failing_notify
    try:
        node._sync_prompt_output_from_state()
    except ValueError as error:
        assert "simulated Agent notification failure" in str(error)
    else:
        raise AssertionError("A connected Agent notification failure must propagate.")
    assert len(failed_notifications) == 1
    assert node._hmb_prompt_snapshot_generation == 4
    assert node.parameter_output_values["PROMPT_OUT"] == node._hmb_last_prompt_output
    failed_visible = node._hmb_last_prompt_output
    failed_machine = node._hmb_last_machine_prompt_output
    assert failed_notifications[0][2]["machine_prompt"] == failed_machine
    failed_set_count = len(set_calls)
    notify_count_before_retry = len(notify_calls)

    node.publish_update_to_parameter = counting_notify
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 4
    assert len(set_calls) == failed_set_count
    assert len(notify_calls) == notify_count_before_retry + 1
    assert notify_calls[-1][:2] == ("PROMPT_OUT", failed_visible)
    assert notify_calls[-1][2]["machine_prompt"] == failed_machine
    assert node._hmb_pending_prompt_notification is None

    # A subscriber may synchronously publish G2 from inside G1 and then throw.
    # Once superseded, G1's callback error is stale and must not escape or
    # restore its pending notification over the newer successful output.
    reentrant_node = SimpleNamespace(
        parameter_output_values={},
        _hmb_prompt_notification_generation=0,
        _hmb_pending_prompt_notification=None,
    )
    reentrant_events = []

    def publish_g2(name, value):
        reentrant_events.append(("g2", name, value))

    def publish_g1(name, value):
        reentrant_events.append(("g1", name, value))
        reentrant_node.publish_update_to_parameter = publish_g2
        prompt._stage_and_notify_prompt_output(reentrant_node, "g2-prompt")
        raise ValueError("superseded g1 callback failure")

    reentrant_node.publish_update_to_parameter = publish_g1
    prompt._stage_and_notify_prompt_output(reentrant_node, "g1-prompt")
    assert reentrant_node.parameter_output_values["PROMPT_OUT"] == "g2-prompt"
    assert reentrant_events == [
        ("g1", "PROMPT_OUT", "g1-prompt"),
        ("g2", "PROMPT_OUT", "g2-prompt"),
    ]
    assert reentrant_node._hmb_pending_prompt_notification is None
finally:
    prompt._build_prompt_package = original_visible_build
    prompt._build_data_only_prompt_package = original_machine_build
    prompt.set_output = original_set_output


# Reproduce a connection value write that schedules a host-loop callback. The
# connection hook's immediate authoritative sync invalidates that callback, so
# immediate + scheduled paths produce one synchronization.
module_names = [
    "griptape_nodes",
    "griptape_nodes.retained_mode",
    "griptape_nodes.retained_mode.griptape_nodes",
]
saved_modules = {name: sys.modules.get(name) for name in module_names}
scheduled_callbacks = []


class _FakeEventLoop:
    @staticmethod
    def is_running():
        return True

    @staticmethod
    def call_soon_threadsafe(callback):
        scheduled_callbacks.append(callback)


class _FakeEventManager:
    event_loop = _FakeEventLoop()

    @staticmethod
    def put_event(_event):
        return None


class _FakeGriptapeNodes:
    @staticmethod
    def EventManager():
        return _FakeEventManager()


for package_name in module_names[:2]:
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
engine_module = types.ModuleType(module_names[2])
engine_module.GriptapeNodes = _FakeGriptapeNodes
sys.modules[module_names[2]] = engine_module

if not hasattr(prompt.DataNode, "after_incoming_connection"):
    setattr(
        prompt.DataNode,
        "after_incoming_connection",
        lambda _self, _source_node, _source_parameter, _target_parameter: None,
    )

sync_node = prompt.HMBPromptLibrary(name="prompt_connection_sync_coalescing")
sync_calls = []
sync_node._sync_prompt_output_from_state = MethodType(
    lambda self: (sync_calls.append(self._hmb_sync_generation) or {}),
    sync_node,
)
# A real Griptape DataNode may queue constructor/lifecycle callbacks through
# the same host loop. This assertion targets only the connection transaction.
scheduled_callbacks.clear()
original_set_parameter_value = prompt._set_parameter_value


def scheduling_parameter_write(target, name, value):
    callbacks_before_write = len(scheduled_callbacks)
    original_set_parameter_value(target, name, value)
    # The real Griptape host invokes after_value_set during the write; the
    # lightweight fallback does not. Inject only the callback the host omitted.
    if target is sync_node and len(scheduled_callbacks) == callbacks_before_write:
        target._schedule_prompt_sync()


try:
    prompt._set_parameter_value = scheduling_parameter_write
    source = SimpleNamespace(
        parameter_output_values={"PICKER_OUT": "{}"},
        parameter_values={},
    )
    sync_node.after_incoming_connection(
        source,
        SimpleNamespace(name="PICKER_OUT"),
        SimpleNamespace(name=prompt.PICKER_INPUT_PARAMETER_NAME),
    )
    assert len(scheduled_callbacks) == 1, [
        getattr(callback, "__qualname__", repr(callback))
        for callback in scheduled_callbacks
    ]
    assert len(sync_calls) == 1, "The connection hook must perform one immediate synchronization."
    scheduled_callbacks.pop()()
    assert len(sync_calls) == 1, "The stale scheduled connection callback must be coalesced."

    # Five expanded Prompt nodes can each receive a burst of retained-mode
    # updates. One node must enqueue one callback for the entire loop tick,
    # while that callback still compiles the latest state exactly once.
    scheduled_callbacks.clear()
    sync_calls.clear()
    for _ in range(20):
        sync_node._schedule_prompt_sync()
    assert len(scheduled_callbacks) == 1, "A Prompt sync burst must own one host-loop callback."
    scheduled_callbacks.pop()()
    assert len(sync_calls) == 1, "A coalesced Prompt sync burst must compile exactly once."
finally:
    prompt._set_parameter_value = original_set_parameter_value
    for module_name, original_module in saved_modules.items():
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module


# Connected-source updates carry a monotonic internal revision. This lets the
# widget reject a delayed pre-connection local echo without confusing an actual
# later Picker disconnect with that old value.
revision_node = prompt.HMBPromptLibrary(name="prompt_source_revision")
revision_base = prompt._normalize_state(prompt._default_widget_state())
assert revision_base[prompt.UI_EDIT_REVISION_KEY] == 0
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_base),
)
revision_node._hmb_picker_connected = True
revision_picker_payload = {
    "media_ready": True,
    "run_id": "first-picker-ready",
    "selection_id": "selection-one",
    "active_slot_count": 1,
    "selected_video_count": 1,
    "ordered_video_uids": ["video-source-one"],
    "videos": [
        {
            "video_uid": "video-source-one",
            "source_uid": "video-source-one",
            "selection_order": 1,
            "video_slot": 1,
            "video_path": "C:/synthetic/first-picker-shot.mp4",
            "reference_capabilities": {
                "schema": "hmb-video-reference-capabilities",
                "version": 1,
                "frame_addressable": True,
                "exact_emitter_cues": False,
                "image_source_frame_ranges": True,
                "marker_instance_identity_fields": [
                    "maya_uuid",
                    "full_dag_path",
                ],
            },
            "frame_domain": {
                "schema": "hmb-video-frame-domain",
                "version": 1,
                "timebase": "24/1",
                "start_frame": 101,
                "end_frame": 162,
                "frame_count": 62,
                "range_addressable": True,
            },
            "timing_cues": [],
        }
    ],
}
prompt._set_parameter_value(
    revision_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(revision_picker_payload),
)
revision_connected = revision_node._write_dashboard_state()
assert revision_connected[prompt.SOURCE_SYNC_REVISION_KEY] == 1
assert revision_connected["picker"]["enabled"] is True
assert revision_connected["videos"][0]["reference_capabilities"][
    "frame_addressable"
] is True

# Loading a workflow whose dashboard already contains the exact applied source
# must establish the in-memory fingerprint without fabricating another source
# revision. A blank hydrated state above may advance once; an already-applied
# persisted state remains unchanged, and every repeated compile is idempotent.
hydrated_node = prompt.HMBPromptLibrary(name="prompt_hydrated_source_revision")
hydrated_state = prompt._apply_picker_payload(
    prompt._normalize_state(prompt._default_widget_state()),
    revision_picker_payload,
    connected=True,
)
hydrated_state[prompt.SOURCE_SYNC_REVISION_KEY] = 27
prompt._set_parameter_value(
    hydrated_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(hydrated_state),
)
# Real Griptape invokes the widget setter hook synchronously while source input
# caches may still be later in the hydration stream. That eager compile must
# retain the persisted connected identity instead of treating the not-yet-read
# input as an authoritative disconnect.
hydrated_pending = hydrated_node._sync_prompt_output_now()
assert hydrated_pending[prompt.SOURCE_SYNC_REVISION_KEY] == 27
assert hydrated_pending["picker"]["enabled"] is True
hydrated_node._hmb_picker_connected = True
prompt._set_parameter_value(
    hydrated_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(revision_picker_payload),
)
hydrated_first = hydrated_node._write_dashboard_state()
assert hydrated_first[prompt.SOURCE_SYNC_REVISION_KEY] == 27
assert hydrated_node._write_dashboard_state()[prompt.SOURCE_SYNC_REVISION_KEY] == 27

# The real widget persists only dashboard-authored fields. Establishing a
# fingerprint from that frontend-normalized version may restore source helper
# metadata, but it is still the exact already-applied Picker generation and
# must not fabricate revision 28 during the first reconcile.
hydrated_frontend_node = prompt.HMBPromptLibrary(
    name="prompt_hydrated_frontend_source_revision"
)
hydrated_frontend_state = copy.deepcopy(hydrated_state)
for image in hydrated_frontend_state["images"]:
    for field in ("source_type_choices", "owner_choices", "scope_choices"):
        image.pop(field, None)
for video in hydrated_frontend_state["videos"]:
    for field in (
        "video_main_type_choices",
        "video_sub_type_choices",
        "source_type_choices",
        "control_role_choices",
        "reference_capabilities",
        "frame_domain",
        "timing_cues",
    ):
        video.pop(field, None)
prompt._set_parameter_value(
    hydrated_frontend_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(hydrated_frontend_state),
)
hydrated_frontend_node._hmb_picker_connected = True
prompt._set_parameter_value(
    hydrated_frontend_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(revision_picker_payload),
)
hydrated_frontend_first = hydrated_frontend_node._write_dashboard_state()
assert hydrated_frontend_first[prompt.SOURCE_SYNC_REVISION_KEY] == 27
assert hydrated_frontend_first["videos"][0]["reference_capabilities"][
    "frame_addressable"
] is True

# Baseline suppression is limited to that first disconnected in-memory
# fingerprint. A later semantic payload update remains authoritative even when
# the Picker intentionally keeps its run/selection addresses stable.
same_identity_transport_update = copy.deepcopy(revision_picker_payload)
same_identity_transport_update["videos"][0]["reference_capabilities"][
    "exact_emitter_cues"
] = True
prompt._set_parameter_value(
    hydrated_frontend_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(same_identity_transport_update),
)
hydrated_transport_updated = hydrated_frontend_node._write_dashboard_state()
assert hydrated_transport_updated[prompt.SOURCE_SYNC_REVISION_KEY] == 28
assert hydrated_transport_updated["videos"][0]["reference_capabilities"][
    "exact_emitter_cues"
] is True

# A frontend select transaction intentionally carries only dashboard-authored
# fields. Python restores Picker-only transport metadata while compiling the
# prompt, but an unchanged upstream payload is not a new source generation.
# Keeping the revision stable lets the frontend recognize the canonical echo as
# equivalent instead of remounting and closing the user's next open dropdown.
local_select_state = copy.deepcopy(revision_connected)
for image in local_select_state["images"]:
    for field in ("source_type_choices", "owner_choices", "scope_choices"):
        image.pop(field, None)
for video in local_select_state["videos"]:
    for field in (
        "video_main_type_choices",
        "video_sub_type_choices",
        "source_type_choices",
        "control_role_choices",
        "reference_capabilities",
        "frame_domain",
        "timing_cues",
    ):
        video.pop(field, None)
local_select_state["videos"][0]["video_main_type"] = "Maya Preview / Playblast"
local_select_state["videos"][0]["video_sub_type"] = "Timing / Edit"
local_select_state["videos"][0]["source_type"] = "Timing / Edit Reference"
local_select_state["videos"][0]["control_role"] = "Timing Only"
local_select_state[prompt.UI_EDIT_REVISION_KEY] = 11
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(local_select_state),
)
revision_reenriched = revision_node._write_dashboard_state()
assert revision_reenriched[prompt.SOURCE_SYNC_REVISION_KEY] == 1
assert revision_reenriched[prompt.UI_EDIT_REVISION_KEY] == 11
assert revision_reenriched["videos"][0]["video_main_type"] == "Maya Preview / Playblast"
assert revision_reenriched["videos"][0]["video_sub_type"] == "Timing / Edit"
assert revision_reenriched["videos"][0]["source_type"] == "Timing / Edit Reference"
assert revision_reenriched["videos"][0]["control_role"] == "Timing Only"
assert revision_reenriched["videos"][0]["reference_capabilities"][
    "frame_addressable"
] is True


def frontend_prompt_projection(state):
    """Remove Python-only row enrichment exactly as the widget projection does."""

    projected = copy.deepcopy(state)
    for image in projected["images"]:
        for field in ("source_type_choices", "owner_choices", "scope_choices"):
            image.pop(field, None)
    for video in projected["videos"]:
        for field in (
            "video_main_type_choices",
            "video_sub_type_choices",
            "source_type_choices",
            "control_role_choices",
            "reference_capabilities",
            "frame_domain",
            "timing_cues",
        ):
            video.pop(field, None)
    return projected


assert frontend_prompt_projection(revision_reenriched) == local_select_state

# A genuinely new Picker payload still advances the revision and remains
# authoritative even when it arrives immediately after local dropdown edits.
second_picker_payload = copy.deepcopy(revision_picker_payload)
second_picker_payload["run_id"] = "second-picker-ready"
second_picker_payload["selection_id"] = "selection-two"
second_picker_payload["videos"][0]["video_path"] = (
    "C:/synthetic/second-picker-shot.mp4"
)
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_reenriched),
)
prompt._set_parameter_value(
    revision_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(second_picker_payload),
)
revision_updated = revision_node._write_dashboard_state()
assert revision_updated[prompt.SOURCE_SYNC_REVISION_KEY] == 2
assert revision_updated[prompt.UI_EDIT_REVISION_KEY] == 11
assert revision_updated["picker"]["run_id"] == "second-picker-ready"

# Transport-only Picker diagnostics can change without changing the applied
# Prompt state. Consume that fingerprint once so a later local edit cannot
# misclassify the already-observed payload as a new upstream generation.
picker_diagnostic_payload = copy.deepcopy(second_picker_payload)
picker_diagnostic_payload["catalog_video_count"] = 99
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_updated),
)
prompt._set_parameter_value(
    revision_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(picker_diagnostic_payload),
)
revision_diagnostic = revision_node._write_dashboard_state()
assert revision_diagnostic[prompt.SOURCE_SYNC_REVISION_KEY] == 2
assert revision_diagnostic[prompt.UI_EDIT_REVISION_KEY] == 11
assert revision_node._write_dashboard_state()[prompt.SOURCE_SYNC_REVISION_KEY] == 2

prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_diagnostic),
)
revision_node._hmb_picker_connected = False
prompt._set_parameter_value(revision_node, prompt.PICKER_INPUT_PARAMETER_NAME, "")
revision_disconnected = revision_node._write_dashboard_state()
assert revision_disconnected[prompt.SOURCE_SYNC_REVISION_KEY] == 3
assert revision_disconnected[prompt.UI_EDIT_REVISION_KEY] == 11
assert revision_disconnected["picker"]["enabled"] is False

# Reconnecting the same source is an authoritative connection transition and
# advances once; repeated compile/write calls remain stable.
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_disconnected),
)
revision_node._hmb_picker_connected = True
prompt._set_parameter_value(
    revision_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(picker_diagnostic_payload),
)
revision_reconnected = revision_node._write_dashboard_state()
assert revision_reconnected[prompt.SOURCE_SYNC_REVISION_KEY] == 4
assert revision_reconnected[prompt.UI_EDIT_REVISION_KEY] == 11
assert revision_reconnected["picker"]["enabled"] is True
assert revision_node._write_dashboard_state()[prompt.SOURCE_SYNC_REVISION_KEY] == 4


# Image Asset has the same revision contract as Picker: local Target/Sub Type
# edits do not create an upstream generation, while source selection changes,
# disconnect, and reconnect each advance exactly once.
asset_node = prompt.HMBPromptLibrary(name="prompt_asset_source_revision")
asset_base = prompt._normalize_state(prompt._default_widget_state())
prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_base),
)
first_asset_payload = {
    "schema": "hmb-image-asset-library-binding",
    "version": 4,
    "mode": "image_asset",
    "project_id": "synthetic-project",
    "project_uid": "synthetic-project-uid",
    "selection_id": "asset-selection-one",
    "ordered_images": [
        {
            "selected": True,
            "order_key": "project:hero-one",
            "source_uid": "project:hero-one",
            "image_name": "HeroOne",
            "selection_order": 1,
        }
    ],
    "verified_assets": [
        {
            "verified_asset": True,
            "binding_mode": "verified_asset",
            "order_key": "project:hero-one",
            "source_uid": "project:hero-one",
            "source_kind": "project",
            "asset_library_id": "hero-library-one",
            "asset_id": "HeroOne",
            "image_name": "HeroOne",
            "image_main_type": "Character",
            "image_sub_type": "Full Appearance",
            "source_type": "Character Appearance",
            "scope_candidate": "Full body / full appearance",
            "color_pick_candidates": ["Red"],
            "selection_order": 1,
        }
    ],
}
asset_node._hmb_image_asset_connected = True
prompt._set_parameter_value(
    asset_node,
    prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    prompt._json_dumps(first_asset_payload),
)
asset_connected = asset_node._write_dashboard_state()
assert asset_connected[prompt.SOURCE_SYNC_REVISION_KEY] == 1
assert asset_connected["images"][0]["asset_source_uid"] == "project:hero-one"

asset_local_edit = frontend_prompt_projection(asset_connected)
asset_local_edit["images"][0]["owner"] = "Hero One"
asset_local_edit[prompt.UI_EDIT_REVISION_KEY] = prompt.MAX_SOURCE_SYNC_REVISION
prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_local_edit),
)
asset_local_reenriched = asset_node._write_dashboard_state()
assert asset_local_reenriched[prompt.SOURCE_SYNC_REVISION_KEY] == 1
assert asset_local_reenriched[prompt.UI_EDIT_REVISION_KEY] == (
    prompt.MAX_SOURCE_SYNC_REVISION
)
assert asset_local_reenriched["images"][0]["owner"] == "Hero One"
assert frontend_prompt_projection(asset_local_reenriched) == asset_local_edit

second_asset_payload = copy.deepcopy(first_asset_payload)
second_asset_payload["selection_id"] = "asset-selection-two"
for key in ("ordered_images", "verified_assets"):
    second_asset_payload[key][0]["source_uid"] = "project:hero-two"
    second_asset_payload[key][0]["order_key"] = "project:hero-two"
    second_asset_payload[key][0]["image_name"] = "HeroTwo"
second_asset_payload["verified_assets"][0]["asset_library_id"] = (
    "hero-library-two"
)
second_asset_payload["verified_assets"][0]["asset_id"] = "HeroTwo"
prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_local_reenriched),
)
prompt._set_parameter_value(
    asset_node,
    prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    prompt._json_dumps(second_asset_payload),
)
asset_updated = asset_node._write_dashboard_state()
assert asset_updated[prompt.SOURCE_SYNC_REVISION_KEY] == 2
assert asset_updated[prompt.UI_EDIT_REVISION_KEY] == prompt.MAX_SOURCE_SYNC_REVISION
assert asset_updated["images"][0]["asset_source_uid"] == "project:hero-two"

# An allowed diagnostic-only payload change is a no-op generation and is
# consumed exactly once, matching the Picker rule above.
asset_diagnostic_payload = copy.deepcopy(second_asset_payload)
asset_diagnostic_payload["media_resolution"] = {"resolved": 1}
prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_updated),
)
prompt._set_parameter_value(
    asset_node,
    prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    prompt._json_dumps(asset_diagnostic_payload),
)
asset_diagnostic = asset_node._write_dashboard_state()
assert asset_diagnostic[prompt.SOURCE_SYNC_REVISION_KEY] == 2
assert asset_node._write_dashboard_state()[prompt.SOURCE_SYNC_REVISION_KEY] == 2

prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_diagnostic),
)
asset_node._hmb_image_asset_connected = False
prompt._set_parameter_value(asset_node, prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME, "")
asset_disconnected = asset_node._write_dashboard_state()
assert asset_disconnected[prompt.SOURCE_SYNC_REVISION_KEY] == 3
assert asset_disconnected[prompt.UI_EDIT_REVISION_KEY] == (
    prompt.MAX_SOURCE_SYNC_REVISION
)
assert asset_disconnected["image_asset"]["enabled"] is False

prompt._set_parameter_value(
    asset_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(asset_disconnected),
)
asset_node._hmb_image_asset_connected = True
prompt._set_parameter_value(
    asset_node,
    prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    prompt._json_dumps(asset_diagnostic_payload),
)
asset_reconnected = asset_node._write_dashboard_state()
assert asset_reconnected[prompt.SOURCE_SYNC_REVISION_KEY] == 4
assert asset_reconnected["image_asset"]["enabled"] is True
assert asset_node._write_dashboard_state()[prompt.SOURCE_SYNC_REVISION_KEY] == 4

revision_bounds = prompt._normalize_state(
    {
        **prompt._default_widget_state(),
        prompt.UI_EDIT_REVISION_KEY: prompt.MAX_SOURCE_SYNC_REVISION + 99,
    }
)
assert revision_bounds[prompt.UI_EDIT_REVISION_KEY] == prompt.MAX_SOURCE_SYNC_REVISION
revision_bounds = prompt._normalize_state(
    {
        **prompt._default_widget_state(),
        prompt.UI_EDIT_REVISION_KEY: -99,
    }
)
assert revision_bounds[prompt.UI_EDIT_REVISION_KEY] == 0

# The private UI transaction counter is transport-only. It must never alter
# either the user-readable PROMPT_OUT or the Agent's private machine snapshot.
ui_revision_zero = prompt._normalize_state(prompt._default_widget_state())
ui_revision_only = copy.deepcopy(ui_revision_zero)
ui_revision_only[prompt.UI_EDIT_REVISION_KEY] = 123456
assert prompt._build_prompt_package(ui_revision_only) == prompt._build_prompt_package(
    ui_revision_zero
)
assert prompt._build_data_only_prompt_package(
    ui_revision_only
) == prompt._build_data_only_prompt_package(ui_revision_zero)
assert prompt._prompt_semantic_fingerprint(
    ui_revision_only
) == prompt._prompt_semantic_fingerprint(ui_revision_zero)


# A delayed local request cannot roll the dashboard back after a newer edit was
# accepted. The instance cache covers both the normal node setter and host
# implementations that assign the Parameter before invoking after_value_set.
echo_node = prompt.HMBPromptLibrary(name="prompt_widget_echo_order")
echo_b = prompt._normalize_state(prompt._default_widget_state())
echo_b[prompt.SOURCE_SYNC_REVISION_KEY] = 9
echo_b[prompt.UI_EDIT_REVISION_KEY] = 2
echo_b["text"]["SCENE_CONTEXT"] = "newer B"
echo_b["images"][0].update({
    "frame_range_intent": {
        "version": 1,
        "enabled": True,
        "start_frame": 101,
        "end_frame": 162,
        "ranges": [{"start": 101, "end": 110}],
        "selected_index": 0,
    },
    "frame_range_enabled": True,
    "frame_range_color_index": 0,
    "frame_range_bindings": {
        "@video1::": {
            "video_slot": "@video1",
            "color_pick": "",
            "enabled": True,
            "origin": "manual",
            "ranges": [{"start": 101, "end": 110}],
            "start_frame": 101,
            "end_frame": 162,
        }
    },
    "frame_range_selected_index": 0,
})
echo_a = copy.deepcopy(echo_b)
echo_a[prompt.UI_EDIT_REVISION_KEY] = 1
echo_a["text"]["SCENE_CONTEXT"] = "stale A"
echo_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(echo_b),
)
echo_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(echo_a),
)
echo_after_stale_setter = prompt._parse_state(
    prompt._get_parameter_raw(echo_node, prompt.WIDGET_PARAMETER_NAME)
)
assert echo_after_stale_setter[prompt.UI_EDIT_REVISION_KEY] == 2
assert echo_after_stale_setter["text"]["SCENE_CONTEXT"] == "newer B"

echo_parameter = prompt._get_parameter_obj(echo_node, prompt.WIDGET_PARAMETER_NAME)
echo_parameter.default_value = prompt._json_dumps(echo_a)
echo_node.after_value_set(echo_parameter, prompt._json_dumps(echo_a))
echo_after_stale_hook = prompt._parse_state(
    prompt._get_parameter_raw(echo_node, prompt.WIDGET_PARAMETER_NAME)
)
assert echo_after_stale_hook[prompt.UI_EDIT_REVISION_KEY] == 2
assert echo_after_stale_hook["text"]["SCENE_CONTEXT"] == "newer B"

# Source and UI revisions are independent axes. A newer Picker generation must
# update source-owned fields without rolling newer Prompt prose or a user Range
# ON transaction back to the older values carried by that delayed snapshot.
echo_authoritative = copy.deepcopy(echo_a)
echo_authoritative[prompt.SOURCE_SYNC_REVISION_KEY] = 10
echo_authoritative[prompt.UI_EDIT_REVISION_KEY] = 0
echo_authoritative["text"]["SCENE_CONTEXT"] = "authoritative source"
echo_authoritative["images"][0]["frame_range_intent"] = {
    "version": 1,
    "enabled": False,
    "start_frame": None,
    "end_frame": None,
    "ranges": [],
    "selected_index": -1,
}
echo_authoritative["images"][0]["frame_range_enabled"] = False
echo_authoritative["images"][0]["frame_range_bindings"] = {}
echo_authoritative["images"][0]["frame_range_binding"] = None
echo_authoritative["images"][0]["frame_range_selected_index"] = -1
echo_authoritative["picker"]["enabled"] = True
echo_authoritative["picker"]["run_id"] = "source-generation-10"
echo_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(echo_authoritative),
)
echo_after_crossed_source = prompt._parse_state(
    prompt._get_parameter_raw(echo_node, prompt.WIDGET_PARAMETER_NAME)
)
assert echo_node._hmb_last_accepted_widget_revisions == (10, 2)
assert echo_after_crossed_source["picker"]["run_id"] == "source-generation-10"
assert echo_after_crossed_source["text"]["SCENE_CONTEXT"] == "newer B"
assert echo_after_crossed_source["images"][0]["frame_range_enabled"] is True
assert echo_after_crossed_source["images"][0]["frame_range_intent"][
    "ranges"
] == [{"start": 101, "end": 110}]

# The inverse crossed pair is also a merge: a UI Range edit authored from an
# older source snapshot keeps the already accepted Picker generation.
echo_newer_ui = copy.deepcopy(echo_authoritative)
echo_newer_ui[prompt.SOURCE_SYNC_REVISION_KEY] = 9
echo_newer_ui[prompt.UI_EDIT_REVISION_KEY] = 3
echo_newer_ui["picker"]["run_id"] = "stale-source-generation"
echo_newer_ui["images"][0].update(copy.deepcopy(echo_b["images"][0]))
echo_newer_ui["images"][0]["frame_range_intent"]["ranges"] = [
    {"start": 120, "end": 130}
]
echo_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(echo_newer_ui),
)
echo_after_crossed_ui = prompt._parse_state(
    prompt._get_parameter_raw(echo_node, prompt.WIDGET_PARAMETER_NAME)
)
assert echo_node._hmb_last_accepted_widget_revisions == (10, 3)
assert echo_after_crossed_ui["picker"]["run_id"] == "source-generation-10"
assert echo_after_crossed_ui["images"][0]["frame_range_enabled"] is True
assert echo_after_crossed_ui["images"][0]["frame_range_intent"][
    "ranges"
] == [{"start": 120, "end": 130}]

# Workflow hydration is a new saved baseline and may intentionally start below
# both live clocks.
echo_hydrated = copy.deepcopy(echo_authoritative)
echo_hydrated[prompt.SOURCE_SYNC_REVISION_KEY] = 3
echo_hydrated["text"]["SCENE_CONTEXT"] = "saved hydration"
echo_node.set_parameter_value(
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(echo_hydrated),
    initial_setup=True,
)
assert echo_node._hmb_last_accepted_widget_revisions == (3, 0)
assert prompt._parse_state(
    prompt._get_parameter_raw(echo_node, prompt.WIDGET_PARAMETER_NAME)
)["text"]["SCENE_CONTEXT"] == "saved hydration"


# The host can replay Prompt's saved Shot before VideoPicker has accepted the
# restored ImageAsset channel. Initial hydration preserves the durable loader
# projection and defers exact validation; the same mismatch outside hydration
# remains fail-closed.
pending_channel = "10000000-0000-4000-8000-000000000001"
pending_shot = "20000000-0000-4000-8000-000000000001"
stale_picker_channel = "30000000-0000-4000-8000-000000000001"
pending_state = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    revision_picker_payload,
    connected=True,
)
pending_state["shot"] = prompt._normalize_shot_selection({
    "channel_uuid": pending_channel,
    "shot_uuid": pending_shot,
    "name": "Shot 1",
    "number": 1,
    "selected_source_uids": [],
})
pending_state = prompt._normalize_state(pending_state)


class HydratingPicker:
    def __init__(self):
        self.snapshot_calls = 0

    def _hmb_shot_channel_subscription(self):
        return {
            "participant_kind": "video_picker",
            "enabled": True,
            "channel_uuid": stale_picker_channel,
            "shot_uuid": pending_shot,
        }

    def _hmb_shot_routing_snapshot(self, expected_channel_uuid=""):
        self.snapshot_calls += 1
        raise ValueError(
            "VideoPicker Shot channel is unavailable or does not match."
        )


pending_picker = HydratingPicker()
pending_node = prompt.HMBPromptLibrary(name="prompt_picker_route_pending")
pending_node._hmb_routing_hydration_rebase_pending = True
(
    pending_projected,
    _pending_images,
    _pending_videos,
    _pending_image_exact,
    pending_picker_exact,
) = pending_node._apply_exact_shot_routes(
    pending_state,
    picker_source_node=pending_picker,
    allow_picker_hydration_pending=True,
)
assert pending_picker.snapshot_calls == 0
assert pending_picker_exact is False
assert pending_node._hmb_picker_route_hydration_pending is True
assert pending_projected["picker"]["enabled"] is True
assert pending_projected["picker"]["ordered_video_uids"] == pending_state[
    "picker"
]["ordered_video_uids"]

try:
    pending_node._apply_exact_shot_routes(
        pending_state,
        picker_source_node=pending_picker,
    )
except ValueError as error:
    assert "channel is unavailable" in str(error)
else:
    raise AssertionError(
        "A live VideoPicker Shot channel mismatch was incorrectly deferred."
    )
assert pending_picker.snapshot_calls == 1


print("HMB Prompt paired-output coalescing regression passed.")
