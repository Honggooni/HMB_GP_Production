from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import types
from itertools import combinations
from pathlib import Path

from _hmb_bundled_policy_session import install_bundled_policy_session


ROOT = Path(__file__).resolve().parents[2]
ORDER = ("I", "V", "P", "A")


def load(name: str):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


image = load("HMBImageAssetLibrary")
video = load("HMBVideoPickerLibrary")
prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")
install_bundled_policy_session(agent._hmb)

COMPOSITIONS = tuple(
    frozenset(values)
    for size in range(1, len(ORDER) + 1)
    for values in combinations(ORDER, size)
)
assert len(COMPOSITIONS) == 15
assert len(set(COMPOSITIONS)) == 15

ASSET_PAYLOAD = {
    "mode": "image_asset",
    "schema": "hmb-image-asset-library-binding",
    "selection_id": "all-15-asset-edge",
    "ordered_images": [
        {
            "order_key": "external:connected-idea",
            "image_name": "Connected optional idea",
            "selection_order": 1,
            "source_uid": "external:connected-idea",
        }
    ],
    "verified_assets": [],
}

PICKER_PAYLOAD = {
    "mode": "maya",
    "run_id": "all-15-picker-edge",
    "media_ready": True,
    "active_slot_count": 1,
    "videos": [
        {
            "video_slot": 1,
            "video_path": "C:/shots/optional-color.mp4",
            "source_type_hint": "Maya Preview / Playblast",
        }
    ],
    "markers": [],
}


def seeded_prompt_state() -> dict:
    state = prompt._default_widget_state()
    state["text"].update(
        {
            "PROJECT_STYLE_LOOK": "ALL15_USER_GOAL_SENTINEL",
            "SCENE_CONTEXT": (
                "Preserve dormant @image9 and @video4 references as user intent.\n"
                "CONTROL_ONLY_BINDING: incomplete free-form control idea"
            ),
            "PRESERVED_TEXT": (
                "free-form exact words must survive\n"
                "[Unknown User Type] keep this line too"
            ),
        }
    )
    state["images"][0].update(
        {
            "present": True,
            "label": "",
            "image_main_type": "Custom / Context",
            "image_sub_type": "Custom",
            "source_type": "Custom",
            "custom_source_type": "User invented image role",
            "owner": "Whole imagined world",
            "scope": "Custom scope",
            "binding_scopes": ["Custom scope"],
            "binding_custom_scopes": ["User invented scope"],
            "binding_video_slots": [5],
            "marker_video": 5,
            "color_picks": ["Red"],
            "manual": True,
        }
    )
    while len(state["videos"]) < 5:
        state["videos"].append(prompt._default_video_item(len(state["videos"]) + 1))
    state["videos"][1].update(
        {
            "present": True,
            "label": "MANUAL_VIDEO2_SENTINEL.mp4",
            "video_main_type": "Custom / Context",
            "video_sub_type": "Custom",
            "source_type": "Custom",
            "custom_source_type": "User invented video role",
            "control_role": "Custom Role",
            "custom_control_role": "User invented control role",
            "keep_out": "Keep dormant @image8 wording exactly.",
            "manual": True,
        }
    )
    state["videos"][4].update(
        {
            "present": True,
            "label": "MANUAL_VIDEO5_SENTINEL.mp4",
            "video_main_type": "Custom / Context",
            "video_sub_type": "Custom",
            "source_type": "Custom",
            "custom_source_type": "Any-purpose user evidence",
            "control_role": "Custom Role",
            "custom_control_role": "Use exactly as the current goal asks",
            "manual": True,
        }
    )
    return prompt._normalize_state(state)


def assert_user_state_survives(state: dict, label: str) -> None:
    image_rows = list(state["images"])
    if state.get("image_asset", {}).get("enabled"):
        image_rows.extend(
            state.get("image_asset", {}).get("dormant_manual_rows", [])
        )
    manual_image = next(
        (
            item
            for item in image_rows
            if item.get("owner") == "Whole imagined world"
        ),
        None,
    )
    assert manual_image is not None, label
    assert manual_image["source_type"] == "Custom", label
    assert "User invented image role" in manual_image["custom_source_type"], label
    assert manual_image["manual"] is True, label
    assert state["videos"][1]["label"] == "MANUAL_VIDEO2_SENTINEL.mp4", label
    assert state["videos"][1]["source_type"] == "Custom", label
    assert "User invented video role" in state["videos"][1]["custom_source_type"], label
    assert state["videos"][1]["control_role"] == "Custom Role", label
    assert "User invented control role" in state["videos"][1]["custom_control_role"], label
    assert state["videos"][4]["label"] == "MANUAL_VIDEO5_SENTINEL.mp4", label
    assert "@image8" in state["videos"][1]["keep_out"], label
    assert "@image9" in state["text"]["SCENE_CONTEXT"], label
    assert "@video4" in state["text"]["SCENE_CONTEXT"], label


def assert_data_only_prompt(compiled: str, label: str) -> None:
    assert "ALL15_USER_GOAL_SENTINEL" in compiled, label
    assert "MANUAL_VIDEO2_SENTINEL.mp4" in compiled, label
    assert "MANUAL_VIDEO5_SENTINEL.mp4" in compiled, label
    assert "free-form exact words must survive" in compiled, label
    assert "[Unknown User Type] keep this line too" in compiled, label
    assert "@image9" in compiled, label
    assert "@video4" in compiled, label
    for forbidden in (
        "Final prompt generation is blocked",
        "requires one validated Motion Guide",
        "Target must match",
        "Boundary must be",
        "prohibited full-shot/global",
        "one marker cannot",
        "Assign distinct",
        "These notes limit authority",
        "Affected records are ignored or limited",
    ):
        assert forbidden.casefold() not in compiled.casefold(), (label, forbidden)


def exercise_agent_once(
    prompt_value: str,
    *,
    canonical_prompt_connected: bool = False,
) -> tuple[int, bool, bool, int, int, int]:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_ruleset_names = ("", "")
    node._hmb_native_calls_this_process = 0
    calls: list[tuple[bool, bool, int, int, int]] = []

    if canonical_prompt_connected:
        class PromptSnapshotSource:
            @staticmethod
            def _hmb_agent_prompt_snapshot(visible_prompt: str) -> dict:
                return {
                    "schema": agent._PAIRED_PROMPT_SNAPSHOT_SCHEMA,
                    "version": agent._PAIRED_PROMPT_SNAPSHOT_VERSION,
                    "generation": 1,
                    "visible_sha256": hashlib.sha256(
                        visible_prompt.encode("utf-8")
                    ).hexdigest(),
                    "machine_sha256": hashlib.sha256(
                        prompt_value.encode("utf-8")
                    ).hexdigest(),
                    "machine_prompt": prompt_value,
                }

            @staticmethod
            def _hmb_shot_channel_subscription():
                return None

        setattr(
            node,
            agent._VERIFIED_PROMPT_SOURCE_ATTRIBUTE,
            PromptSnapshotSource(),
        )

    def native_once(self):
        names = tuple(self._hmb_ruleset_names)
        calls.append(
            (
                bool(self._hmb_rules_active),
                len(set(names)) == 2
                and all(
                    len(name) == 32
                    and all(character in "0123456789abcdef" for character in name)
                    for name in names
                ),
                sum(bool(name) for name in names),
                len(self._hmb_policy_rules),
                len(self._hmb_binding_rules),
            )
        )
        self.parameter_output_values = {"agent": {}, "output": "agent-output"}
        if False:
            yield None
        return "agent-output"

    node.get_parameter_value = types.MethodType(
        lambda _self, name: (
            prompt_value
            if name == agent._AGENT_SHOT_PROMPT_INPUT_PARAMETER
            else None
        ),
        node,
    )
    node._run_native_agent_once = types.MethodType(native_once, node)
    node._secure_hmb_outputs = types.MethodType(
        lambda _self: setattr(_self, "_hmb_last_sanitizer_status", "clean"),
        node,
    )
    node._has_canonical_hmb_prompt_connection = types.MethodType(
        lambda _self: canonical_prompt_connected,
        node,
    )
    iterator = node.process()
    try:
        while True:
            next(iterator)
    except StopIteration as stop:
        assert stop.value == "agent-output"
    assert len(calls) == 1
    active, opaque_names, name_count, project_rules, shot_rules = calls[0]
    return len(calls), active, opaque_names, name_count, project_rules, shot_rules


runtime_results: dict[str, dict] = {}
external_process_attempts: list[tuple] = []
original_subprocess_module = video.subprocess


def forbidden_external_process(*args, **kwargs):
    external_process_attempts.append((args, kwargs))
    raise AssertionError("Independent VideoPicker process launched Maya/FFmpeg automatically")


guarded_subprocess = types.ModuleType("hmb_guarded_subprocess")
guarded_subprocess.__dict__.update(original_subprocess_module.__dict__)
guarded_subprocess.Popen = forbidden_external_process
guarded_subprocess.run = forbidden_external_process
video.subprocess = guarded_subprocess
try:
    with tempfile.TemporaryDirectory(prefix="hmb-all-15-runtime-") as temp_root:
        image.DEFAULT_PROJECTS_ROOT = Path(temp_root)
        for composition in COMPOSITIONS:
            label = "".join(key for key in ORDER if key in composition)
            edges: set[str] = set()
            outputs: dict[str, object] = {}

            if "I" in composition:
                image_node = image.HMBImageAssetLibrary(name=f"all15_image_{label}")
                assert image_node.process() is None
                image_output = json.loads(
                    image_node.parameter_output_values[image.OUTPUT_PARAMETER]
                )
                assert image_output["mode"] == "image_asset", label
                outputs["I"] = image_output

            if "V" in composition:
                video_node = video.HMBVideoPickerLibrary(name=f"all15_video_{label}")
                assert video_node.process() is None
                video_output = json.loads(
                    video_node.parameter_output_values["PICKER_OUT"]
                )
                assert video_output["mode"] == "maya", label
                outputs["V"] = video_output

            compiled = ""
            if "P" in composition:
                state = seeded_prompt_state()
                assert_user_state_survives(state, f"{label}:seed")
                if "I" in composition:
                    state = prompt._apply_image_asset_payload(
                        state,
                        copy.deepcopy(ASSET_PAYLOAD),
                        connected=True,
                    )
                    edges.add("I->P")
                if "V" in composition:
                    state = prompt._apply_picker_payload(
                        state,
                        copy.deepcopy(PICKER_PAYLOAD),
                        connected=True,
                    )
                    edges.add("V->P")
                assert_user_state_survives(state, f"{label}:connected")
                compiled = prompt._build_data_only_prompt_package(state)
                assert_data_only_prompt(compiled, label)
                assert bool(state["image_asset"]["enabled"]) is ("I" in composition), label
                assert bool(state["picker"]["enabled"]) is ("V" in composition), label
                outputs["P"] = compiled

                if {"I", "V"} <= composition:
                    reverse = seeded_prompt_state()
                    reverse = prompt._apply_picker_payload(
                        reverse,
                        copy.deepcopy(PICKER_PAYLOAD),
                        connected=True,
                    )
                    reverse = prompt._apply_image_asset_payload(
                        reverse,
                        copy.deepcopy(ASSET_PAYLOAD),
                        connected=True,
                    )
                    assert_user_state_survives(reverse, f"{label}:reverse")
                    assert_data_only_prompt(
                        prompt._build_data_only_prompt_package(reverse),
                        f"{label}:reverse",
                    )

            agent_calls = 0
            if "A" in composition:
                agent_input = compiled if "P" in composition else f"Native goal-only request for {label}."
                route = exercise_agent_once(
                    agent_input,
                    canonical_prompt_connected="P" in composition,
                )
                agent_calls = route[0]
                assert route[0] == 1, label
                if "P" in composition:
                    edges.add("P->A")
                    assert route[1:] == (True, True, 2, 4, 4), label
                else:
                    assert route[1:] == (False, False, 0, 0, 0), label
                outputs["A"] = "agent-output"

            expected_edges = set()
            if {"I", "P"} <= composition:
                expected_edges.add("I->P")
            if {"V", "P"} <= composition:
                expected_edges.add("V->P")
            if {"P", "A"} <= composition:
                expected_edges.add("P->A")
            assert edges == expected_edges, (label, edges, expected_edges)
            assert set(outputs) == set(composition), (label, outputs)
            assert agent_calls == (1 if "A" in composition else 0), label
            runtime_results[label] = {
                "members": sorted(composition),
                "edges": sorted(edges),
                "agent_calls": agent_calls,
                "produced": sorted(outputs),
            }
finally:
    video.subprocess = original_subprocess_module

assert len(runtime_results) == 15
assert all(result["produced"] for result in runtime_results.values())
assert not external_process_attempts
print(
    "HMB all-15 dynamic composition runtime regression: PASS "
    f"({json.dumps(runtime_results, ensure_ascii=False, sort_keys=True)})"
)
