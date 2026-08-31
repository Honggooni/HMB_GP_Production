from __future__ import annotations

from itertools import combinations
from pathlib import Path
import asyncio
import importlib.util
import inspect
import json
import logging
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


def prompt_sections(payload: str):
    lines = payload.splitlines()
    assert lines[0] == "HMB_GP_Production"
    assert len(lines) == 7
    assert lines[1] == "HMB JOB DATA (JSON):"
    assert lines[3] == "FX/TIMING SOURCE DATA (JSON):"
    assert lines[5] == "USER DESCRIPTION DATA (JSON):"
    return json.loads(lines[2]), json.loads(lines[4]), json.loads(lines[6])


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
    compiled = prompt._build_data_only_prompt_package(state)
    job, fx_contract, user_data = prompt_sections(compiled)
    assert job["schema"] == "hmb-public-job-data", label
    assert fx_contract["schema"] == "hmb-fx-timing-source-facts", label
    assert isinstance(user_data, dict), label
    return compiled


# Exercise the actual Prompt boundary for every composition containing P. A
# connection contributes only the rows it owns; it cannot make another library,
# source, companion, or slot mandatory.
manual_primary = prompt._default_widget_state()
manual_primary["videos"][0].update({
    "present": True,
    "label": "manual-motion-reference.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "Local Motion",
    "source_type": "Motion Reference",
    "control_role": "Local Motion Detail Only",
})
manual_primary = prompt._normalize_state(manual_primary)
assert manual_primary["videos"][0]["source_type"] == "Motion Reference"
assert manual_primary["videos"][0]["control_role"] == "Local Motion Detail Only"
manual_primary_compiled = assert_prompt_is_additive(manual_primary, "P manual @video1")
manual_primary_job = prompt_sections(manual_primary_compiled)[0]
assert manual_primary_job["videos"][0]["video"] == "@video1"
assert manual_primary_job["videos"][0]["source_type"] == "Motion Reference"
assert manual_primary_job["videos"][0]["control_role"] == "Local Motion Detail Only"
assert manual_primary_job["control_only_bindings"] == []

auxiliary_only = prompt._default_widget_state()
auxiliary_only["videos"].append(prompt._default_video_item(2))
auxiliary_only["videos"][1].update({
    "present": True,
    "label": "auxiliary-context.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "Secondary Motion",
    "source_type": "Motion Reference",
    "control_role": "Secondary Motion Only",
    "manual": True,
})
auxiliary_compiled = assert_prompt_is_additive(auxiliary_only, "P auxiliary-only")
assert [video["video"] for video in prompt_sections(auxiliary_compiled)[0]["videos"]] == [
    "@video2",
]

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

color_direct_prompt = prompt._build_data_only_prompt_package(prompt_states["VP"])
color_direct_job, color_direct_fx, color_direct_user = prompt_sections(
    color_direct_prompt
)
assert color_direct_job["videos"][0]["source_type"] == "Unified Shot-Control Video"
assert color_direct_job["videos"][0]["control_role"] == "Primary Unified Shot Control"
assert [source["video"] for source in color_direct_fx["sources"]] == ["@video1"]
assert color_direct_fx["sources"][0]["role"] == "Primary Unified Shot Control"
assert color_direct_user == {}

color_depth_state = prompt._apply_picker_payload(
    prompt._default_widget_state(), picker_depth_payload, connected=True
)
color_depth_state["videos"][1].update({
    "video_main_type": "Maya Preview / Playblast",
    "video_sub_type": "Depth",
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
technical_error_prompt = prompt._build_data_only_prompt_package(technical_error_state)
technical_job, technical_fx, technical_user = prompt_sections(technical_error_prompt)
assert technical_job["images"] == []
assert technical_job["videos"] == []
assert technical_fx == {
    "schema": "hmb-fx-timing-source-facts",
    "version": 3,
    "sources": [],
    "control_bindings": [],
}
assert "valid" not in technical_fx
assert "errors" not in technical_fx
assert technical_user == {}

# Picker connections merge their evidence into the current state. A shorter
# payload must not delete independent manual video rows or bindings that point
# to those rows.
merge_state = prompt._default_widget_state()
manual_aux = prompt._default_video_item(2)
manual_aux.update({
    "present": True,
    "label": "manual-independent-aux.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "Secondary Motion",
    "source_type": "Motion Reference",
    "control_role": "Secondary Motion Only",
    "manual": True,
})
merge_state["videos"].append(manual_aux)
merge_state["images"][0].update({
    "present": True,
    "label": "Dormant binding idea",
    "image_main_type": "Custom / Context",
    "image_sub_type": "Custom",
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
    "image_main_type": "Custom / Context",
    "image_sub_type": "Custom",
    "source_type": "Custom",
    "custom_source_type": "Unnamed image idea",
})
unnamed_state["videos"][0].update({
    "present": False,
    "video_main_type": "Custom / Context",
    "video_sub_type": "Context",
    "source_type": "Motion Reference",
    "control_role": "Context Only",
})
unnamed_prompt = assert_prompt_is_additive(unnamed_state, "P unnamed sources")
unnamed_job = prompt_sections(unnamed_prompt)[0]
assert unnamed_job["images"][0]["image"] == "@image1"
assert unnamed_job["images"][0]["label"] == ""
assert unnamed_job["images"][0]["custom_source_type"] == "Unnamed image idea"
assert unnamed_job["videos"][0]["video"] == "@video1"
assert unnamed_job["videos"][0]["label"] == ""

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
preserved_prompt = prompt._build_data_only_prompt_package(preserved_state)
preserved_user = prompt_sections(preserved_prompt)[2]
assert preserved_user == {
    "SCENE_CONTEXT": "Follow @image1 composition.",
    "PRESERVED_TEXT": (
        "[On-screen Text] @image2 literal\n"
        "untagged @image2 descriptive words"
    ),
}
assert (
    prompt._remap_image_source_references("Use @image2 silhouette", {2: 0})
    == "Use [deselected image source #2] silhouette"
)

# Unknown derived wire values are released because current Main/Sub is the
# authoring contract. Blank Main/Sub and independent custom/Target fields are
# serialized exactly as authored rather than filled or semantically rewritten.
future_image = prompt._normalize_image_item({
    "source_type": "Future Image",
    "custom_source_type": "Future Image",
    "owner": "ExistingTarget",
    "binding_scopes": ["Handheld prop"],
}, 1)
assert future_image["image_main_type"] == ""
assert future_image["image_sub_type"] == ""
assert future_image["source_type"] == "Role Required / Select Source Type"
assert future_image["custom_source_type"] == "Future Image"
assert future_image["owner"] == "ExistingTarget"
future_video = prompt._migrate_old_video_item({
    "source_type": "Future Video",
    "custom_source_type": "Future Video",
    "control_role": "Future Role",
    "custom_control_role": "Future Role",
}, 1)
assert future_video["video_main_type"] == ""
assert future_video["video_sub_type"] == ""
assert future_video["source_type"] == "Role Required / Select Video Type"
assert future_video["custom_source_type"] == "Future Video"
assert future_video["control_role"] == ""
assert future_video["custom_control_role"] == "Future Role"

# Enabling an incomplete optional Range preserves it as an unresolved typed
# constraint. Missing optional fields are not technical corruption and add no warning.
incomplete_range_state = prompt._default_widget_state()
incomplete_range_state["images"][0].update({
    "present": True,
    "label": "Range-independent idea",
    "frame_range_intent": {
        "version": 1,
        "enabled": True,
        "start_frame": None,
        "end_frame": None,
        "ranges": [],
        "selected_index": -1,
    },
    "frame_range_enabled": True,
})
incomplete_range_state["videos"][0].update({
    "present": True,
    "label": "range-source.mp4",
    "video_main_type": "Motion Reference",
    "video_sub_type": "Secondary Motion",
    "source_type": "Motion Reference",
    "control_role": "Secondary Motion Only",
})
incomplete_range_prompt = assert_prompt_is_additive(
    incomplete_range_state,
    "P incomplete optional Range",
)
incomplete_job = prompt_sections(incomplete_range_prompt)[0]
assert incomplete_job["images"][0]["label"] == "Range-independent idea"
assert incomplete_job["videos"][0]["label"] == "range-source.mp4"
assert incomplete_job["frame_ranges"] == [{
    "image": "@image1",
    "video": "@video1",
    "marker_color": "",
    "enabled": True,
    "origin": "manual",
    "domain": {},
    "segments": [],
}]

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
        "video_main_type": "Motion Reference",
        "video_sub_type": "Secondary Motion",
        "source_type": "Motion Reference",
        "control_role": "Secondary Motion Only",
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
long_prompt = prompt._build_data_only_prompt_package(long_state)
long_job, long_fx, long_user = prompt_sections(long_prompt)
assert len(long_job["videos"]) == prompt.MAX_VIDEOS
assert len(long_fx["sources"]) == prompt.MAX_VIDEOS
for slot, source in enumerate(long_fx["sources"], start=1):
    assert source["video"] == f"@video{slot}"
    assert source["video_main_type"] == "Motion Reference"
    assert source["video_sub_type"] == "Secondary Motion"
    assert source["role"] == "Secondary Motion Only"
    assert source["keep_out"] == "K" * prompt.MAX_KEEP_OUT_CHARS
    assert "role_selected" not in source
assert "valid" not in long_fx
assert "errors" not in long_fx
assert long_user["PROJECT_STYLE_LOOK"].startswith("GOAL_SENTINEL ")
assert len(long_user["SCENE_CONTEXT"]) == prompt.MAX_DESCRIPTION_CHARS
assert len(long_user["EMOTION_INTENT"]) == prompt.MAX_DESCRIPTION_CHARS
assert len(long_user["VIDEO_VFX"]) == prompt.MAX_VIDEO_VFX_CHARS


# Instantiate and execute the three cheap standalone data paths. Use an empty
# temporary project root so the Image library does not depend on a studio mount.
with tempfile.TemporaryDirectory(prefix="hmb-hybrid-composition-") as temp_root:
    image.DEFAULT_PROJECTS_ROOT = Path(temp_root)
    image_node = image.HMBImageAssetLibrary(name="hybrid_composition_image")
    assert image_node.process() is None
    image_payload = json.loads(
        image_node.parameter_output_values[image.OUTPUT_PARAMETER]
    )
    assert image_payload["mode"] == "image_asset"
    assert image_payload["media_resolution"]["selected_count"] == 0

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

assert picker_result is None
picker_payload = json.loads(picker_node.parameter_output_values["PICKER_OUT"])
assert picker_payload["mode"] == "maya"
assert picker_payload["catalog_video_count"] == 0
assert picker_payload["media_ready"] is False
assert picker_payload["active_slot_count"] == 0
assert picker_payload["videos"] == []

picker_process_source = inspect.getsource(picker.HMBVideoPickerLibrary.process)
assert "_sync_outputs_from_state" in picker_process_source
for forbidden_token in ("Popen", "subprocess.run", "mayabatch", "ffmpeg", "Thread("):
    assert forbidden_token not in picker_process_source

prompt_node = prompt.HMBPromptLibrary(name="hybrid_composition_prompt")
prompt_result = prompt_node.process()
assert prompt_result is None
assert prompt_node.parameter_output_values["PROMPT_OUT"]


class _ProcessContractWarningCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "process() returned unexpected type" in message:
            self.messages.append(message)


process_warning_capture = _ProcessContractWarningCapture()
root_logger = logging.getLogger()
root_logger.addHandler(process_warning_capture)
try:
    for node in (image_node, picker_node, prompt_node):
        async_process = getattr(node, "aprocess", None)
        if callable(async_process):
            asyncio.run(async_process())
finally:
    root_logger.removeHandler(process_warning_capture)
assert process_warning_capture.messages == []


# A plain prompt keeps the untouched Standard Library Agent execution path and
# does not read or inject the sealed HMB policy. Stub only the native model call
# so this regression proves routing without making a request.
plain_prompt = "Independent non-HMB design assistant request."
# CI may not load the optional Standard Library implementation. Construct only
# the HMB routing shell so the test never turns that environment limitation into
# a model request or skips the non-HMB branch contract.
agent_node = object.__new__(agent.HMBAgentLibrary)
agent_node._hmb_rules_active = False
agent_node._hmb_ruleset_names = ("", "")
agent_node._hmb_native_calls_this_process = 0
native_calls: list[tuple[str, bool, int]] = []
secure_calls: list[bool] = []


def fake_native_once(self):
    native_calls.append(
        (
            plain_prompt,
            bool(self._hmb_rules_active),
            sum(bool(name) for name in self._hmb_ruleset_names),
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
assert native_calls == [(plain_prompt, False, 0)]
assert secure_calls == []
assert agent_node._hmb_rules_active is False
assert agent_node._hmb_native_calls_this_process == 0  # Stub owns this isolated call.

agent_process_source = inspect.getsource(agent.HMBAgentLibrary.process)
assert "is_hmb = self._has_canonical_hmb_prompt_connection()" in agent_process_source
assert "_is_hmb_prompt_library_payload(prompt)" not in agent_process_source
assert "yield from self._run_native_agent_once()" in agent_process_source
assert "self._secure_hmb_outputs()" in agent_process_source.split("finally:", 1)[1]


print(
    "HMB hybrid composition regression: PASS "
    "(15 subsets; standalone I/V/P/A; optional Prompt inputs; "
    "Video sync-only; Agent stock native non-HMB path)"
)
