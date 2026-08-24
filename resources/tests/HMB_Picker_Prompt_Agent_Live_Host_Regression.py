from __future__ import annotations

import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_STANDARD_ROOT = (
    Path.home()
    / "Documents"
    / "GriptapeNodes"
    / "libraries"
    / "griptape-nodes-library-standard"
)
if (DEFAULT_STANDARD_ROOT / "griptape_nodes_library" / "agents" / "agent.py").is_file():
    os.environ.setdefault(
        "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
        str(DEFAULT_STANDARD_ROOT),
    )

try:
    from griptape_nodes.exe_types.flow import ControlFlow
    from griptape_nodes.retained_mode.events.connection_events import (
        CreateConnectionRequest,
        CreateConnectionResultSuccess,
        DeleteConnectionRequest,
        DeleteConnectionResultSuccess,
    )
    from griptape_nodes.retained_mode.events.parameter_events import (
        SetParameterValueRequest,
        SetParameterValueResultSuccess,
    )
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
except Exception:
    print("HMB Picker -> Prompt -> Agent live host regression: SKIP (host unavailable)")
    raise SystemExit(0)

import HMBAgentLibrary as agent_library
import HMBPromptLibrary as prompt_library
import HMBVideoPickerLibrary as picker_library


def register(flow: ControlFlow, node: Any) -> None:
    flow.add_node(node)
    GriptapeNodes.ObjectManager().add_object_by_name(node.name, node)
    GriptapeNodes.NodeManager()._name_to_parent_flow_name[node.name] = flow.name


def set_value(
    node: Any,
    name: str,
    value: Any,
    data_type: str,
    *,
    initial_setup: bool = False,
    is_output: bool = False,
) -> None:
    result = GriptapeNodes.handle_request(
        SetParameterValueRequest(
            node_name=node.name,
            parameter_name=name,
            value=value,
            data_type=data_type,
            initial_setup=initial_setup,
            is_output=is_output,
        )
    )
    assert isinstance(result, SetParameterValueResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )


def connect(
    source: Any,
    source_parameter: str,
    target: Any,
    target_parameter: str,
    *,
    initial_setup: bool = False,
) -> None:
    result = GriptapeNodes.handle_request(
        CreateConnectionRequest(
            source_node_name=source.name,
            source_parameter_name=source_parameter,
            target_node_name=target.name,
            target_parameter_name=target_parameter,
            initial_setup=initial_setup,
        )
    )
    assert isinstance(result, CreateConnectionResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )


def disconnect(
    source: Any,
    source_parameter: str,
    target: Any,
    target_parameter: str,
) -> None:
    result = GriptapeNodes.handle_request(
        DeleteConnectionRequest(
            source_node_name=source.name,
            source_parameter_name=source_parameter,
            target_node_name=target.name,
            target_parameter_name=target_parameter,
        )
    )
    assert isinstance(result, DeleteConnectionResultSuccess), (
        type(result).__name__,
        getattr(result, "result_details", ""),
    )


def picker_state(source: Any, ordered_uids: tuple[str, ...]) -> dict[str, Any]:
    state = copy.deepcopy(source._picker_state())
    state["videos"] = []
    for order, uid in enumerate(ordered_uids, start=1):
        markers = (
            [
                {
                    "asset_id": "asset-a",
                    "group_name": "asset-a",
                    "subject_root": "|asset-a",
                    "full_dag_path": "|asset-a",
                    "maya_uuid": "asset-a-uuid",
                    "color": "Red",
                    "video_uid": uid,
                    "source_uid": uid,
                    "video_slot": order,
                    "picker_order": 1,
                }
            ]
            if uid == "video-a"
            else []
        )
        state["videos"].append(
            {
                "video_uid": uid,
                "source_uid": uid,
                "catalog_order": order,
                "video_url": f"https://example.test/{uid}.mp4",
                "selected": True,
                "selection_order": order,
                "video_slot": order,
                "source_fps": 24.0,
                "source_frame_count": 24,
                "decoded_frame_count": 24,
                "source_duration_seconds": 1.0,
                "markers": markers,
            }
        )
    state["active_slot_count"] = max(1, len(ordered_uids))
    state["selected_video_count"] = len(ordered_uids)
    return state


def payload_text(source: Any, ordered_uids: tuple[str, ...]) -> str:
    payload, _media = picker_library._build_synchronized_video_outputs(
        picker_state(source, ordered_uids),
        enforce_media_availability=False,
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


CONTEXT_IMAGE_FIELDS = prompt_library._MANUAL_VIDEO_CONTEXT_IMAGE_FIELDS


def manual_surface(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "videos": copy.deepcopy(state["videos"]),
        "text": copy.deepcopy(state["text"]),
        "images": [
            {
                key: copy.deepcopy(item.get(key))
                for key in CONTEXT_IMAGE_FIELDS
            }
            for item in state["images"]
        ],
        "textarea_heights": copy.deepcopy(
            state["ui"].get("textarea_heights", {})
        ),
    }


GriptapeNodes.EventManager().initialize_queue()
stamp = time.time_ns()
flow = ControlFlow(name=f"HMBPickerPromptAgentLive_{stamp}")
GriptapeNodes.ObjectManager().add_object_by_name(flow.name, flow)


# Saved-workflow hydration: the edge exists first, then the source output and
# independently serialized stale target values arrive with initial_setup=True.
hydration_picker = picker_library.HMBVideoPickerLibrary(
    name=f"HydrationPicker_{stamp}"
)
hydration_prompt = prompt_library.HMBPromptLibrary(
    name=f"HydrationPrompt_{stamp}"
)
for node in (hydration_picker, hydration_prompt):
    register(flow, node)
connect(
    hydration_picker,
    "PICKER_OUT",
    hydration_prompt,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
    initial_setup=True,
)

authoritative_text = payload_text(hydration_picker, ("hydrated-current",))
stale_text = payload_text(hydration_picker, ("hydrated-stale",))
set_value(
    hydration_picker,
    "PICKER_OUT",
    authoritative_text,
    "str",
    initial_setup=True,
    is_output=True,
)
stale_state = prompt_library._apply_picker_payload(
    prompt_library._default_widget_state(),
    json.loads(stale_text),
    connected=True,
)
set_value(
    hydration_prompt,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
    stale_text,
    "str",
    initial_setup=True,
)
set_value(
    hydration_prompt,
    prompt_library.WIDGET_PARAMETER_NAME,
    prompt_library._json_dumps(stale_state),
    "str",
    initial_setup=True,
)
assert prompt_library._get_parameter_raw(
    hydration_prompt,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
) == authoritative_text
assert hydration_prompt._current_state()["picker"]["ordered_video_uids"] == [
    "hydrated-current"
]


# A successful graph lookup with no edge makes a serialized target transport
# cache non-authoritative and clears it during hydration.
orphan_prompt = prompt_library.HMBPromptLibrary(name=f"OrphanPrompt_{stamp}")
register(flow, orphan_prompt)
set_value(
    orphan_prompt,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
    stale_text,
    "str",
    initial_setup=True,
)
assert prompt_library._get_parameter_raw(
    orphan_prompt,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
) == ""


# Live worker publication: first and subsequent Picker updates must traverse a
# real registered edge even though no SetParameterValue host transaction owns
# the late publication.
source = picker_library.HMBVideoPickerLibrary(name=f"LivePicker_{stamp}")
target = prompt_library.HMBPromptLibrary(name=f"LivePrompt_{stamp}")
for node in (source, target):
    register(flow, node)

manual = prompt_library._default_widget_state()
manual["videos"] = [
    {
        **prompt_library._default_video_item(1),
        "present": True,
        "label": "manual-one.mp4",
        "keep_out": "manual one",
    },
    {
        **prompt_library._default_video_item(2),
        "present": True,
        "label": "manual-two.mp4",
        "keep_out": "manual two",
        "manual": True,
    },
]
manual["images"][0].update(
    {
        "present": True,
        "label": "asset-a.png",
        "asset_id": "asset-a",
        "asset_source_uid": "asset-a-source",
        "image_main_type": "Character",
        "image_sub_type": "Full Appearance",
        "binding_video_slots": [1],
        "color_picks": [""],
    }
)
manual["text"]["VIDEO_VFX"] = "manual @video1 and @video2 timing"
manual["ui"]["textarea_heights"] = {
    "video:1:keep_out": 111,
    "video:2:keep_out": 222,
}
# Browser-authored writes always advance the independent UI clock. Model that
# contract here so the equal-clock stale-echo guard does not (correctly) reject
# this setup as an unversioned replay.
manual[prompt_library.UI_EDIT_REVISION_KEY] = (
    int(manual.get(prompt_library.UI_EDIT_REVISION_KEY) or 0) + 1
)
set_value(
    target,
    prompt_library.WIDGET_PARAMETER_NAME,
    prompt_library._json_dumps(manual),
    "str",
)
manual_baseline = target._current_state()
assert manual_baseline["text"]["VIDEO_VFX"] == manual["text"]["VIDEO_VFX"]
assert manual_baseline["images"][0]["asset_source_uid"] == "asset-a-source"
baseline_surface = manual_surface(manual_baseline)

connect(source, "PICKER_OUT", target, prompt_library.PICKER_INPUT_PARAMETER_NAME)
revision_before = target._current_state()[prompt_library.SOURCE_SYNC_REVISION_KEY]

first_text = source._sync_outputs_from_state(
    picker_state(source, ("video-a",)),
    enforce_media_availability=False,
)
first_state = target._current_state()
assert prompt_library._get_parameter_raw(
    target,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
) == first_text
assert first_state["picker"]["ordered_video_uids"] == ["video-a"]
assert first_state[prompt_library.SOURCE_SYNC_REVISION_KEY] > revision_before

second_text = source._sync_outputs_from_state(
    picker_state(source, ("video-b", "video-a")),
    enforce_media_availability=False,
)
second_state = target._current_state()
assert prompt_library._get_parameter_raw(
    target,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
) == second_text
assert second_state["picker"]["ordered_video_uids"] == [
    "video-b",
    "video-a",
]
assert second_state[prompt_library.SOURCE_SYNC_REVISION_KEY] > first_state[
    prompt_library.SOURCE_SYNC_REVISION_KEY
]

disconnect(source, "PICKER_OUT", target, prompt_library.PICKER_INPUT_PARAMETER_NAME)
disconnected_state = target._current_state()
assert manual_surface(disconnected_state) == baseline_surface
assert prompt_library._get_parameter_raw(
    target,
    prompt_library.PICKER_INPUT_PARAMETER_NAME,
) == ""
assert {
    item["video_uid"]
    for item in disconnected_state["picker"]["dormant_video_rows"]
} == {"video-a", "video-b"}

# Reconnect uses the source's current output cache immediately. A connected
# user edit must survive the later three-way disconnect restore.
connect(source, "PICKER_OUT", target, prompt_library.PICKER_INPUT_PARAMETER_NAME)
reconnected = target._current_state()
assert reconnected["picker"]["ordered_video_uids"] == ["video-b", "video-a"]
reconnected["text"]["VIDEO_VFX"] = "user edit while Picker remains connected"
reconnected["images"][0]["color_picks"] = ["Green"]
reconnected[prompt_library.UI_EDIT_REVISION_KEY] = (
    int(reconnected.get(prompt_library.UI_EDIT_REVISION_KEY) or 0) + 1
)
set_value(
    target,
    prompt_library.WIDGET_PARAMETER_NAME,
    prompt_library._json_dumps(reconnected),
    "str",
)
stored_connected_edit = target._current_state()
assert stored_connected_edit["text"]["VIDEO_VFX"] == (
    reconnected["text"]["VIDEO_VFX"]
)
assert stored_connected_edit["images"][0]["color_picks"] == ["Green"]
# Advance the connected Picker generation once more. The three-way baseline
# must advance only Picker-owned remaps and retain these later user edits.
source._sync_outputs_from_state(
    picker_state(source, ("video-a", "video-b")),
    enforce_media_availability=False,
)
refreshed_connected_edit = target._current_state()
assert refreshed_connected_edit["text"]["VIDEO_VFX"] == (
    reconnected["text"]["VIDEO_VFX"]
)
assert refreshed_connected_edit["images"][0]["color_picks"] == ["Green"]
disconnect(source, "PICKER_OUT", target, prompt_library.PICKER_INPUT_PARAMETER_NAME)
edited_disconnect = target._current_state()
assert edited_disconnect["videos"] == manual_baseline["videos"]
assert edited_disconnect["text"]["VIDEO_VFX"] == (
    "user edit while Picker remains connected"
)
assert edited_disconnect["images"][0]["color_picks"] == ["Green"]


# PROMPT_OUT has the same late-publication requirement. Use the real Agent
# target and mutate Prompt state without an enclosing host value-set callback;
# the explicit retained-mode graph update must refresh Agent.prompt.
if (DEFAULT_STANDARD_ROOT / "griptape_nodes_library" / "agents" / "agent.py").is_file():
    agent = agent_library.HMBAgentLibrary(name=f"LiveAgent_{stamp}")
    register(flow, agent)
    connect(target, "PROMPT_OUT", agent, "prompt")
    prompt_state = target._current_state()
    prompt_state["videos"][0]["present"] = True
    prompt_state["videos"][0]["label"] = "late-agent-visible.mp4"
    # Store the new state through the base hydration path, then publish after
    # that transaction has ended to reproduce the deferred callback.
    super(prompt_library.HMBPromptLibrary, target).set_parameter_value(
        prompt_library.WIDGET_PARAMETER_NAME,
        prompt_library._json_dumps(prompt_state),
        initial_setup=True,
    )
    target._sync_prompt_output_now()
    visible = target.parameter_output_values["PROMPT_OUT"]
    assert "late-agent-visible.mp4" in visible
    agent_prompt = agent.get_parameter_value("prompt")
    assert "late-agent-visible.mp4" in agent_prompt
    assert agent_prompt.rstrip("\r\n") == visible.rstrip("\r\n")
    snapshot = target._hmb_agent_prompt_snapshot(agent_prompt)
    assert snapshot["schema"] == "hmb-prompt-paired-snapshot"


# A synchronous publisher subscriber may publish generation g2 while g1 still
# owns the outer call stack. The superseded g1 must never reach a registered
# graph target after g2 has taken ownership.
class ReentrantSink(prompt_library.DataNode):
    def __init__(self, name: str):
        super().__init__(name=name)
        prompt_library._safe_add_parameter(
            self,
            name="prompt",
            type="str",
            input_types=["str"],
            default_value="",
            allowed_modes={prompt_library.ParameterMode.INPUT},
            allow_input=True,
            allow_output=False,
            allow_property=False,
            settable=True,
        )
        self.seen: list[str] = []

    def after_value_set(self, parameter: Any, value: Any) -> None:
        if getattr(parameter, "name", "") == "prompt":
            self.seen.append(str(value))


reentrant_source = prompt_library.HMBPromptLibrary(
    name=f"ReentrantPrompt_{stamp}"
)
reentrant_sink = ReentrantSink(name=f"ReentrantSink_{stamp}")
for node in (reentrant_source, reentrant_sink):
    register(flow, node)
connect(reentrant_source, "PROMPT_OUT", reentrant_sink, "prompt")
original_publisher = reentrant_source.publish_update_to_parameter
did_reenter = False


def reentrant_publisher(name: str, value: Any) -> Any:
    global did_reenter
    result = original_publisher(name, value)
    if value == "g1-prompt" and not did_reenter:
        did_reenter = True
        prompt_library._stage_and_notify_prompt_output(
            reentrant_source,
            "g2-prompt",
        )
    return result


reentrant_source.publish_update_to_parameter = reentrant_publisher
reentrant_sink.seen.clear()
prompt_library._stage_and_notify_prompt_output(
    reentrant_source,
    "g1-prompt",
)
assert reentrant_source.parameter_output_values["PROMPT_OUT"] == "g2-prompt"
assert reentrant_sink.get_parameter_value("prompt") == "g2-prompt"
assert reentrant_sink.seen == ["g2-prompt"]


print("HMB Picker -> Prompt -> Agent live host regression: PASS")
