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
assert output_kwargs["ui_options"]["display_name"] == "PROMPT OUT"
assert output_kwargs["ui_options"]["compact"] is True
assert output_kwargs["ui_options"]["height"] == 24


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
    node._write_dashboard_state = lambda: copy.deepcopy(ui_only_state)
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
    node._write_dashboard_state = lambda: copy.deepcopy(text_state)
    node._sync_prompt_output_from_state()
    text_visible = node._hmb_last_prompt_output
    text_machine = node._hmb_last_machine_prompt_output
    assert text_visible == base_visible
    assert text_machine != base_machine
    assert "User-authored scene description." in text_machine
    assert node._hmb_prompt_snapshot_generation == 2
    assert node.parameter_output_values["PROMPT_OUT"] == base_visible
    assert set_calls == []
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
    node._write_dashboard_state = lambda: copy.deepcopy(local_only_state)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 2
    assert node._hmb_last_prompt_output == text_visible
    assert node._hmb_last_machine_prompt_output == text_machine
    assert set_calls == []
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
    node._write_dashboard_state = lambda: copy.deepcopy(semantic_state)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 3
    assert len(set_calls) == 1
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
    node._write_dashboard_state = lambda: copy.deepcopy(semantic_ui_only)
    node._sync_prompt_output_from_state()
    assert node._hmb_prompt_snapshot_generation == 3
    assert len(set_calls) == 1
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
    assert len(set_calls) == 2
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
    node._write_dashboard_state = lambda: copy.deepcopy(failure_state)
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
prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_base),
)
revision_node._hmb_picker_connected = True
prompt._set_parameter_value(
    revision_node,
    prompt.PICKER_INPUT_PARAMETER_NAME,
    prompt._json_dumps(
        {
            "media_ready": True,
            "video_path": "C:/synthetic/first-picker-shot.mp4",
            "run_id": "first-picker-ready",
            "selection_id": "selection-one",
        }
    ),
)
revision_connected = revision_node._write_dashboard_state()
assert revision_connected[prompt.SOURCE_SYNC_REVISION_KEY] == 1
assert revision_connected["picker"]["enabled"] is True

prompt._set_parameter_value(
    revision_node,
    prompt.WIDGET_PARAMETER_NAME,
    prompt._json_dumps(revision_connected),
)
revision_node._hmb_picker_connected = False
prompt._set_parameter_value(revision_node, prompt.PICKER_INPUT_PARAMETER_NAME, "")
revision_disconnected = revision_node._write_dashboard_state()
assert revision_disconnected[prompt.SOURCE_SYNC_REVISION_KEY] == 2
assert revision_disconnected["picker"]["enabled"] is False


print("HMB Prompt paired-output coalescing regression passed.")
