from pathlib import Path
import importlib.util
import json
import sys

from _hmb_private_policy_fixture import install_private_policy_reader


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")
install_private_policy_reader(agent._hmb)


def prompt_json_section(payload: str, header: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    return json.loads(lines[lines.index(header) + 1])

# VideoPicker publishes one ordered catalog snapshot to Prompt and the exact
# same media order through a single VIDEO_OUT list.
picker_node = picker.HMBVideoPickerLibrary(name="three_library_flow_regression")
picker_state = picker_node._picker_state()
picker_state.update({
    "scene_path": "C:/shots/flow_test.mb",
    "active_slot_count": 5,
    "selected_video_slot": 1,
    "videos": [
        {
            "video_slot": slot,
            "video_path": f"C:/shots/flow_test/flow_test_playblast_{slot}.mp4",
            "camera": "|shotCam",
            "markers": [{
                "asset_id": "Hero" if slot == 1 else f"Control{slot}",
                "color": picker.MARKER_ORDER[slot - 1],
                "subject_root": "|Hero_GRP" if slot == 1 else f"|Control{slot}_GRP",
                "group_name": "Hero" if slot == 1 else f"Control{slot}",
                "full_dag_path": "|Hero_GRP" if slot == 1 else f"|Control{slot}_GRP",
                "maya_uuid": "hero-uuid" if slot == 1 else f"control-{slot}-uuid",
                "video_slot": slot,
                "picker_order": 1,
            }],
        }
        for slot in range(1, 6)
    ],
})
original_request_parameter_value = picker._request_parameter_value
picker._request_parameter_value = lambda *_args, **_kwargs: False
try:
    # This node is intentionally not registered in a retained-mode graph. Use
    # the production local-validation fallback instead of asking the host to
    # publish state for a node that exists only inside this regression.
    picker_node._write_state(picker_state)
finally:
    picker._request_parameter_value = original_request_parameter_value
picker_node._sync_outputs_from_state(
    picker_state,
    enforce_media_availability=False,
)
picker_payload = picker_node._build_picker_payload(picker_state)
picker_text = json.dumps(picker_payload, ensure_ascii=False)
assert picker_payload["schema"] == "hmb-prompt-library-picker-binding"
assert picker_payload["schema_version"] == 5
assert picker_payload["videos"][0]["video_slot"] == 1
assert [item["video_slot"] for item in picker_payload["videos"]] == [1, 2, 3, 4, 5]
assert [item["selection_order"] for item in picker_payload["videos"]] == [1, 2, 3, 4, 5]
assert len({item["video_uid"] for item in picker_payload["videos"]}) == 5
assert picker_payload["ordered_video_uids"] == [
    item["video_uid"] for item in picker_payload["videos"]
]
assert picker_payload["markers"][0]["asset_id"] == "Hero"
assert picker.parameter_exists(picker_node, "PICKER_OUT")
assert picker.parameter_exists(picker_node, "VIDEO_OUT")
assert all(
    not picker.parameter_exists(picker_node, f"VIDEO{slot}_OUT")
    for slot in range(1, 11)
)
assert picker_node.parameter_output_values["VIDEO_OUT"] == [
    f"C:/shots/flow_test/flow_test_playblast_{slot}.mp4"
    for slot in range(1, 6)
]

# PromptLibrary consumes PICKER_OUT, maps the exact Asset ID, and emits PROMPT_OUT.
prompt_state = prompt._default_widget_state()
prompt_state["images"][0].update({
    "present": True,
    "label": "Hero",
    "source_type": "Character Appearance",
    "owner": "Hero",
    "binding_scopes": ["Full body / full appearance"],
    "binding_custom_scopes": [""],
    "binding_video_slots": [1],
    "marker_video": 1,
    "color_picks": [""],
})
for slot in range(2, 6):
    prompt_state["images"].append(prompt._default_image_item(slot))
    prompt_state["images"][slot - 1].update({
        "present": True,
        "label": f"Control{slot}",
        "source_type": "Character Appearance",
        "owner": f"Control{slot}",
        "binding_scopes": ["Full body / full appearance"],
        "binding_custom_scopes": [""],
        "binding_video_slots": [slot],
        "marker_video": slot,
        "color_picks": [""],
    })
prompt_state = prompt._apply_picker_payload(
    prompt_state,
    prompt._parse_picker_payload(picker_text),
    connected=True,
)
assert prompt_state["images"][0]["color_picks"] == ["Red"]
assert prompt_state["images"][0]["marker_video"] == 1
assert [prompt_state["images"][slot - 1]["marker_video"] for slot in range(1, 6)] == [1, 2, 3, 4, 5]
assert prompt_state["videos"][0]["label"] == "flow_test_playblast_1"
assert prompt_state["videos"][0]["picker_auto_label"] == "flow_test_playblast_1"
assert [item["slot"] for item in prompt_state["videos"]] == [1, 2, 3, 4, 5]
for video in prompt_state["videos"][1:]:
    video["control_role"] = "Context Only"
prompt_state["videos"][1]["source_type"] = "Motion Guide / Retargeting Reference"
prompt_state["videos"][1]["control_role"] = "Derived Motion Decoding Only"
compiled_prompt = prompt._build_data_only_prompt_package(prompt_state)
compiled_job = prompt_json_section(compiled_prompt, "HMB JOB DATA (JSON):")
assert compiled_job["images"][0]["label"] == "Hero"
assert compiled_job["images"][0]["bindings"][0] == {
    "video": "@video1",
    "marker_color": "Red",
    "target_scope": "Full body / full appearance",
}
assert compiled_job["videos"][0]["video"] == "@video1"
assert compiled_job["videos"][0]["label"] == "flow_test_playblast_1"
assert "video_path" not in compiled_job["videos"][0]

# AgentLibrary recognizes the Prompt output and prepares exactly four rules from
# each internal behavior without changing the downstream native Agent contract.
assert agent._is_hmb_prompt_library_payload(compiled_prompt)
policy_document, binding_document = agent._hmb._load_verified_behavior_documents()
policy_rules = agent._split_behavior_rules(policy_document, 4)
binding_rules = agent._split_behavior_rules(binding_document, 4)
assert len(policy_rules) == 4
assert len(binding_rules) == 4

print("HMB VideoPicker -> PromptLibrary -> AgentLibrary organic flow regression: PASS")
