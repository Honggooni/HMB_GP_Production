from __future__ import annotations

from itertools import combinations
from pathlib import Path
import importlib.util
import inspect
import json
import copy
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


image = load("HMBImageAssetLibrary")
picker = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")


# The hybrid product supports every non-empty composition of its four nodes.
# Keep this list explicit: deleting even one supported composition must fail this
# regression instead of being hidden by a generated powerset.
HYBRID_COMPOSITIONS = (
    frozenset({"I"}),
    frozenset({"V"}),
    frozenset({"P"}),
    frozenset({"A"}),
    frozenset({"I", "V"}),
    frozenset({"I", "P"}),
    frozenset({"I", "A"}),
    frozenset({"V", "P"}),
    frozenset({"V", "A"}),
    frozenset({"P", "A"}),
    frozenset({"I", "V", "P"}),
    frozenset({"I", "V", "A"}),
    frozenset({"I", "P", "A"}),
    frozenset({"V", "P", "A"}),
    frozenset({"I", "V", "P", "A"}),
)

generated_compositions = {
    frozenset(values)
    for size in range(1, 5)
    for values in combinations(("I", "V", "P", "A"), size)
}
assert len(HYBRID_COMPOSITIONS) == 15
assert len(set(HYBRID_COMPOSITIONS)) == 15
assert set(HYBRID_COMPOSITIONS) == generated_compositions


NODE_CLASSES = {
    "I": image.HMBImageAssetLibrary,
    "V": picker.HMBVideoPickerLibrary,
    "P": prompt.HMBPromptLibrary,
    "A": agent.HMBAgentLibrary,
}

# Every library owns a real execution entry point. No member is merely a helper
# that works only when all four libraries are present.
for key, node_class in NODE_CLASSES.items():
    assert "process" in node_class.__dict__, f"{key} lost its independent process()"
    assert callable(node_class.__dict__["process"])


def expected_edges(composition: frozenset[str]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    if {"I", "P"} <= composition:
        edges.add(("I.ASSET_OUT", "P.ASSET_IN"))
    if {"V", "P"} <= composition:
        edges.add(("V.PICKER_OUT", "P.PICKER_IN"))
    if {"P", "A"} <= composition:
        edges.add(("P.PROMPT_OUT", "A.prompt"))
    return edges


# A composition activates only edges whose two endpoints are present. Image and
# Video never acquire a hidden dependency on each other or on Agent, and Agent
# does not require the HMB source libraries when Prompt is absent.
for composition in HYBRID_COMPOSITIONS:
    members = {key: NODE_CLASSES[key] for key in composition}
    assert set(members) == set(composition)
    assert all(callable(node_class.__dict__["process"]) for node_class in members.values())
    edges = expected_edges(composition)
    assert (("I.ASSET_OUT", "P.ASSET_IN") in edges) is ({"I", "P"} <= composition)
    assert (("V.PICKER_OUT", "P.PICKER_IN") in edges) is ({"V", "P"} <= composition)
    assert (("P.PROMPT_OUT", "A.prompt") in edges) is ({"P", "A"} <= composition)


# Prompt source inputs are optional, empty by default, and independently typed.
picker_input = prompt._picker_input_kwargs()
asset_input = prompt._image_asset_input_kwargs()
for kwargs, parameter_name in (
    (picker_input, prompt.PICKER_INPUT_PARAMETER_NAME),
    (asset_input, prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME),
):
    assert kwargs["name"] == parameter_name
    assert kwargs["default_value"] == ""
    assert kwargs["allow_input"] is True
    assert kwargs["allow_output"] is False
    assert kwargs["hide_property"] is True

prompt_doc = inspect.getdoc(prompt.HMBPromptLibrary) or ""
assert "IMAGE_ASSET_IN and PICKER_IN are optional" in prompt_doc

base_prompt_state = prompt._default_widget_state()
canonical_base_prompt_state = prompt._normalize_state(base_prompt_state)
base_images = json.dumps(canonical_base_prompt_state["images"], sort_keys=True)
base_videos = json.dumps(canonical_base_prompt_state["videos"], sort_keys=True)

without_assets = prompt._apply_image_asset_payload(
    canonical_base_prompt_state,
    {},
    connected=False,
)
assert json.dumps(without_assets["videos"], sort_keys=True) == base_videos
assert without_assets["image_asset"]["enabled"] is False

without_picker = prompt._apply_picker_payload(
    canonical_base_prompt_state,
    {},
    connected=False,
)
assert json.dumps(without_picker["images"], sort_keys=True) == base_images
assert len(without_picker["videos"]) == 1
assert without_picker["videos"][0]["present"] is False
assert without_picker["picker"]["enabled"] is False


def assert_prompt_is_additive(state, label: str) -> str:
    compiled = prompt._build_prompt_package(state)
    assert "SOURCE AUTHORITY CONFLICTS:" not in compiled, label
    assert "requires one validated Motion Guide" not in compiled, label
    assert "@video1 Color Playblast is required" not in compiled, label
    assert "Final prompt generation is blocked" not in compiled, label
    return compiled


# Exercise the actual Prompt boundary for every composition containing P. A
# connection contributes only the rows it owns; it cannot make another library,
# source, companion, or slot mandatory.
manual_primary = prompt._default_widget_state()
manual_primary["videos"][0].update({
    "present": True,
    "label": "manual-motion-reference.mp4",
    "source_type": "Motion Reference",
    "control_role": "Local Motion Detail Only",
})
manual_primary = prompt._normalize_state(manual_primary)
assert manual_primary["videos"][0]["source_type"] == "Motion Reference"
assert manual_primary["videos"][0]["control_role"] == "Local Motion Detail Only"
manual_primary_compiled = assert_prompt_is_additive(manual_primary, "P manual @video1")
assert "@video1 = Motion Reference / Local Motion Detail Only" in manual_primary_compiled
assert "local control binding = not supplied" in manual_primary_compiled
assert "Authority comes from the explicitly supplied role" not in manual_primary_compiled

auxiliary_only = prompt._default_widget_state()
auxiliary_only["videos"].append(prompt._default_video_item(2))
auxiliary_only["videos"][1].update({
    "present": True,
    "label": "auxiliary-context.mp4",
    "source_type": "Motion Reference",
    "control_role": "Context Only",
    "manual": True,
})
auxiliary_compiled = assert_prompt_is_additive(auxiliary_only, "P auxiliary-only")
assert "Active video slots = @video2" in auxiliary_compiled

asset_payload = {
    "mode": "image_asset",
    "schema": "hmb-image-asset-library-binding",
    "selection_id": "hybrid-additive-asset",
    "ordered_images": [{
        "order_key": "external:idea",
        "image_name": "Unclassified idea image",
        "selection_order": 1,
    }],
    "verified_assets": [],
}
picker_color_payload = {
    "mode": "maya",
    "run_id": "hybrid-additive-color",
    "media_ready": True,
    "active_slot_count": 1,
    "videos": [{
        "video_slot": 1,
        "video_path": "C:/shots/color-only.mp4",
    }],
    "markers": [],
}
picker_depth_payload = {
    **picker_color_payload,
    "run_id": "hybrid-additive-color-depth",
    "active_slot_count": 2,
    "videos": [
        {"video_slot": 1, "video_path": "C:/shots/color-only.mp4"},
        {
            "video_slot": 2,
            "video_path": "C:/shots/depth-only.mp4",
            "source_type_hint": "Depth / Spatial Reference",
            "control_role_hint": "Spatial Alignment Verification Only",
        },
    ],
}

prompt_states = {"P": prompt._default_widget_state()}
prompt_states["IP"] = prompt._apply_image_asset_payload(
    copy.deepcopy(prompt_states["P"]), asset_payload, connected=True
)
prompt_states["VP"] = prompt._apply_picker_payload(
    copy.deepcopy(prompt_states["P"]), picker_color_payload, connected=True
)
prompt_states["PA"] = copy.deepcopy(prompt_states["P"])
prompt_states["IVP"] = prompt._apply_picker_payload(
    copy.deepcopy(prompt_states["IP"]), picker_color_payload, connected=True
)
prompt_states["IPA"] = copy.deepcopy(prompt_states["IP"])
prompt_states["VPA"] = copy.deepcopy(prompt_states["VP"])
prompt_states["IVPA"] = copy.deepcopy(prompt_states["IVP"])
for composition_name, composition_state in prompt_states.items():
    assert_prompt_is_additive(composition_state, composition_name)

color_direct_prompt = prompt._build_prompt_package(prompt_states["VP"])
assert "Color Playblast scope = animator-authored acting" in color_direct_prompt
assert "protected shot state by default" in color_direct_prompt
assert "a role label alone does not narrow them" in color_direct_prompt
assert "Proxy marker colors, Color Pick markers" in color_direct_prompt
assert "not final identity, material, lighting, or look authority" in color_direct_prompt
assert "explicit scoped instruction" in color_direct_prompt
assert "Generator exposure prohibited" not in color_direct_prompt
assert "must not be connected" not in color_direct_prompt

color_depth_state = prompt._apply_picker_payload(
    prompt._default_widget_state(), picker_depth_payload, connected=True
)
color_depth_state["videos"][1].update({
    "source_type": "Depth / Spatial Reference",
    "control_role": "Spatial Alignment Verification Only",
})
assert_prompt_is_additive(color_depth_state, "VP Color+Depth without Motion")

# Technical Picker/schema issues reduce or ignore only the affected record.
# They remain visible as warnings while the rest of the hybrid composition and
# user goal continue without a global prompt-generation block.
technical_error_state = prompt._default_widget_state()
technical_error_state["picker"]["contract_errors"] = [
    "PICKER_OUT contains duplicate rows for @video2."
]
technical_error_prompt = prompt._build_prompt_package(technical_error_state)
assert "SOURCE DATA WARNINGS:" in technical_error_prompt
assert "Final prompt generation is blocked" not in technical_error_prompt
assert "Every supplied source and the user goal remain independently usable" in technical_error_prompt

# Picker connections merge their evidence into the current state. A shorter
# payload must not delete independent manual video rows or bindings that point
# to those rows.
merge_state = prompt._default_widget_state()
manual_aux = prompt._default_video_item(2)
manual_aux.update({
    "present": True,
    "label": "manual-independent-aux.mp4",
    "source_type": "Motion Reference",
    "control_role": "Context Only",
    "manual": True,
})
merge_state["videos"].append(manual_aux)
merge_state["images"][0].update({
    "present": True,
    "label": "Dormant binding idea",
    "source_type": "Custom",
    "custom_source_type": "User idea",
    "color_picks": ["Blue"],
    "binding_video_slots": [2],
    "marker_video": 2,
})
merged_picker_state = prompt._apply_picker_payload(
    merge_state,
    picker_color_payload,
    connected=True,
)
assert merged_picker_state["videos"][1]["label"] == "manual-independent-aux.mp4"
assert merged_picker_state["videos"][1]["source_type"] == "Motion Reference"
assert merged_picker_state["images"][0]["binding_video_slots"] == [2]
assert merged_picker_state["images"][0]["color_picks"] == ["Blue"]

# A source does not require a name. Other supplied data activates it and the
# compiler emits a stable fallback label.
unnamed_state = prompt._default_widget_state()
unnamed_state["images"][0].update({
    "present": False,
    "source_type": "Custom",
    "custom_source_type": "Unnamed image idea",
})
unnamed_state["videos"][0].update({
    "present": False,
    "source_type": "Motion Reference",
    "control_role": "Context Only",
})
unnamed_prompt = assert_prompt_is_additive(unnamed_state, "P unnamed sources")
assert "@image1 = image source 1" in unnamed_prompt
assert "@video1 = video source 1" in unnamed_prompt

# Malformed exact-text rows lose only exact-literal authority; their wording is
# preserved as descriptive intent. Exact literals are never rewritten when
# image rows are reordered.
preserved_state = prompt._default_widget_state()
preserved_state["text"]["PRESERVED_TEXT"] = (
    "[On-screen Text] @image2 literal\n"
    "untagged @image2 descriptive words"
)
preserved_state["text"]["SCENE_CONTEXT"] = "Follow @image2 composition."
prompt._remap_image_source_references_in_state(preserved_state, {2: 1})
assert "[On-screen Text] @image2 literal" in preserved_state["text"]["PRESERVED_TEXT"]
assert "untagged @image2 descriptive words" in preserved_state["text"]["PRESERVED_TEXT"]
assert preserved_state["text"]["SCENE_CONTEXT"] == "Follow @image1 composition."
preserved_prompt = prompt._build_prompt_package(preserved_state)
assert "PRESERVED_TEXT_DESCRIPTIVE_FALLBACK" in preserved_prompt
assert "untagged @image2 descriptive words" in preserved_prompt
assert (
    prompt._remap_image_source_references("Use @image2 silhouette", {2: 0})
    == "Use [deselected image source #2] silhouette"
)

# Unknown future taxonomy values and legacy relationships survive migration.
future_image = prompt._migrate_old_image_item({
    "source_type": "Future Image",
    "custom_source_type": "Future Image",
    "owner": "ExistingTarget",
    "binding_scopes": ["Handheld prop"],
    "interaction_targets": ["Hero", "Custom"],
    "interaction_custom_targets": ["", "Dog"],
}, 1)
assert future_image["source_type"] == "Custom"
assert future_image["custom_source_type"] == "Future Image"
assert future_image["owner"] == "ExistingTarget"
assert future_image["legacy_relationship_targets"] == ["Hero", "Dog"]
future_video = prompt._migrate_old_video_item({
    "source_type": "Future Video",
    "custom_source_type": "Future Video",
    "control_role": "Future Role",
    "custom_control_role": "Future Role",
}, 1)
assert future_video["source_type"] == "Custom"
assert future_video["custom_source_type"] == "Future Video"
assert future_video["control_role"] == "Custom Role"
assert future_video["custom_control_role"] == "Future Role"

# Enabling an incomplete optional Range preserves it as immediately usable user
# intent. Missing optional fields are not technical corruption and add no warning.
incomplete_range_state = prompt._default_widget_state()
incomplete_range_state["images"][0].update({
    "present": True,
    "label": "Range-independent idea",
    "frame_range_enabled": True,
})
incomplete_range_state["videos"][0].update({
    "present": True,
    "label": "range-source.mp4",
    "source_type": "Motion Reference",
    "control_role": "Context Only",
})
incomplete_range_prompt = assert_prompt_is_additive(
    incomplete_range_state,
    "P incomplete optional Range",
)
assert "@image1 = Range-independent idea" in incomplete_range_prompt
assert '"FRAME_RANGE_INTENT"' in incomplete_range_prompt
assert "Optional frame-range instruction ignored" not in incomplete_range_prompt
assert "SOURCE DATA WARNINGS:" not in incomplete_range_prompt

# Exceeding the advisory production budget no longer replaces the user goal
# with a conflict-only response. The complete prompt remains available with a
# non-blocking late-context warning.
long_state = prompt._default_widget_state()
long_state["videos"] = []
for slot in range(1, prompt.MAX_VIDEOS + 1):
    row = prompt._default_video_item(slot)
    row.update({
        "present": True,
        "label": f"long-source-{slot}.mp4",
        "source_type": "Motion Reference",
        "control_role": "Context Only",
        "keep_out": "K" * prompt.MAX_KEEP_OUT_CHARS,
        "manual": True,
    })
    long_state["videos"].append(row)
long_state["text"].update({
    "PROJECT_STYLE_LOOK": "GOAL_SENTINEL " + "S" * (prompt.MAX_DESCRIPTION_CHARS - 14),
    "SCENE_CONTEXT": "C" * prompt.MAX_DESCRIPTION_CHARS,
    "EMOTION_INTENT": "E" * prompt.MAX_DESCRIPTION_CHARS,
    "VIDEO_VFX": "V" * prompt.MAX_VIDEO_VFX_CHARS,
})
long_prompt = prompt._build_prompt_package(long_state)
assert len(long_prompt) > prompt.MAX_PROMPT_CHARS
assert "GOAL_SENTINEL" in long_prompt
assert "PROMPT BUDGET NOTICE:" in long_prompt
assert "preserved without truncation" in long_prompt
assert "SOURCE AUTHORITY CONFLICTS:" not in long_prompt
assert "Final prompt generation is blocked" not in long_prompt


# Instantiate and execute the three cheap standalone data paths. Use an empty
# temporary project root so the Image library does not depend on a studio mount.
with tempfile.TemporaryDirectory(prefix="hmb-hybrid-composition-") as temp_root:
    image.DEFAULT_PROJECTS_ROOT = Path(temp_root)
    image_node = image.HMBImageAssetLibrary(name="hybrid_composition_image")
    image_result = image_node.process()
    assert image_result["mode"] == "image_asset"
    assert image_result["asset_count"] == 0

picker_node = picker.HMBVideoPickerLibrary(name="hybrid_composition_picker")

# process() is an output synchronizer only. Guard the real subprocess API while
# executing it so a future accidental Maya/FFmpeg launch fails immediately.
original_popen = picker.subprocess.Popen
original_run = picker.subprocess.run


def forbidden_external_process(*_args, **_kwargs):
    raise AssertionError("VideoPicker.process() attempted an automatic Maya/FFmpeg process")


picker.subprocess.Popen = forbidden_external_process
picker.subprocess.run = forbidden_external_process
try:
    picker_result = picker_node.process()
finally:
    picker.subprocess.Popen = original_popen
    picker.subprocess.run = original_run

assert picker_result["mode"] == "maya"
assert picker_result["action"] == "sync_outputs"
assert picker_result["video_count"] == 0
picker_payload = json.loads(picker_result["picker"])
assert picker_payload["media_ready"] is False
assert picker_payload["active_slot_count"] == 0
assert picker_payload["videos"] == []

picker_process_source = inspect.getsource(picker.HMBVideoPickerLibrary.process)
assert "_sync_outputs_from_state" in picker_process_source
for forbidden_token in ("Popen", "subprocess.run", "mayabatch", "ffmpeg", "Thread("):
    assert forbidden_token not in picker_process_source

prompt_node = prompt.HMBPromptLibrary(name="hybrid_composition_prompt")
prompt_result = prompt_node.process()
assert prompt_result["mode"] == prompt.MODE_NAME
assert prompt_result["active_images"] == 0
assert prompt_result["active_videos"] == 0
assert prompt_node.parameter_output_values["PROMPT_OUT"]


# A plain prompt keeps the untouched Standard Library Agent execution path and
# does not read or inject the sealed HMB policy. Stub only the native model call
# so this regression proves routing without making a request.
plain_prompt = "Independent non-HMB design assistant request."
assert agent._is_hmb_prompt_library_payload(plain_prompt) is False
# CI may not load the optional Standard Library implementation. Construct only
# the HMB routing shell so the test never turns that environment limitation into
# a model request or skips the non-HMB branch contract.
agent_node = object.__new__(agent.HMBAgentLibrary)
agent_node._hmb_rules_active = False
agent_node._hmb_structured_rules_active = False
agent_node._hmb_goal_first_rules = []
agent_node._hmb_native_calls_this_process = 0
native_calls: list[tuple[str, bool, bool, int]] = []
secure_calls: list[bool] = []


def fake_native_once(self):
    native_calls.append(
        (
            plain_prompt,
            bool(self._hmb_rules_active),
            bool(self._hmb_structured_rules_active),
            len(self._hmb_goal_first_rules),
        )
    )
    if False:
        yield None
    return "native-path-complete"


agent_node._run_native_agent_once = types.MethodType(fake_native_once, agent_node)
agent_node._secure_hmb_outputs = types.MethodType(
    lambda _self: secure_calls.append(True),
    agent_node,
)
agent_node._has_canonical_hmb_prompt_connection = types.MethodType(
    lambda _self: False,
    agent_node,
)
agent_node.get_parameter_value = types.MethodType(
    lambda _self, name: plain_prompt if name == "prompt" else None,
    agent_node,
)
process_iterator = agent_node.process()
try:
    while True:
        next(process_iterator)
except StopIteration as stop:
    agent_result = stop.value

assert agent_result == "native-path-complete"
assert native_calls == [(plain_prompt, False, False, 0)]
assert secure_calls == []
assert agent_node._hmb_rules_active is False
assert agent_node._hmb_native_calls_this_process == 0  # Stub owns this isolated call.

agent_process_source = inspect.getsource(agent.HMBAgentLibrary.process)
assert "is_hmb = self._has_canonical_hmb_prompt_connection()" in agent_process_source
assert "_is_hmb_prompt_library_payload(prompt)" not in agent_process_source
assert "_extract_goal_first_rule" in agent_process_source
assert "yield from self._run_native_agent_once()" in agent_process_source
assert "self._secure_hmb_outputs()" in agent_process_source.split("finally:", 1)[1]


print(
    "HMB hybrid composition regression: PASS "
    "(15 subsets; standalone I/V/P/A; optional Prompt inputs; "
    "Video sync-only; Agent stock native non-HMB path)"
)
