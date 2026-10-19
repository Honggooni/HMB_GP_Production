"""Exercise policy and typed media handoffs without a model or provider call.

Default: verify the signed policy bundled with this checkout.  A private,
unsigned source candidate can be checked through the Manager compiler with
--source PATH --manager PATH.  Candidate mode does not validate a signature.
Policy prose is neither embedded in this test nor printed on success.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from _hmb_bundled_policy_session import install_bundled_policy_session


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--manager", type=Path)
    parser.add_argument("--expected-version-suffix", default="")
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    agent = load("HMBAgentLibrary")
    prompt = load("HMBPromptLibrary")
    generator = load("HMBSeedanceGeneration")
    finish = load("HMBFinishLookLibrary")
    assert not args.require_native or agent._BuiltinAgent is not None, (
        "Set HMB_GRIPTAPE_STANDARD_LIBRARY_PATH to the installed Standard Library"
    )

    expected_sections = None
    if args.source:
        if not args.manager:
            parser.error("--manager is required with --source")
        sys.path.insert(0, str(args.manager.resolve()))
        from hmb_core.source import compile_source_file, normalize, parse_sections

        payload = agent._hmb._validate_agent_policy_payload(
            compile_source_file(args.source).payload
        )
        expected_sections = parse_sections(
            normalize(args.source.read_text(encoding="utf-8-sig"))
        )
        mode = "compiled candidate (signature not tested)"
    else:
        install_bundled_policy_session(agent._hmb)
        payload = agent._hmb._load_agent_rule_payload()
        mode = "verified bundled DAT"
    version = payload["final_policy_version"]
    assert not args.expected_version_suffix or version.endswith(
        args.expected_version_suffix
    ), "Unexpected policy version"

    node = object.__new__(agent.HMBAgentLibrary)
    with patch.object(agent._hmb, "_load_agent_rule_payload", return_value=payload):
        policy, binding, projects, shots = node._load_hmb_rules()
    assert [policy, binding] == [payload["policy"], payload["binding"]]
    assert len(projects) == len(shots) == 4
    assert node._hmb_policy_identity["version"] == version
    if expected_sections is not None:
        # Compare every character, including each section's last paragraph,
        # across compiler -> runtime loader -> native rules. No phrase allowlist.
        assert projects + shots == [
            heading + "\n\n" + body
            for _kind, _number, heading, body in expected_sections
        ], "Source section content was lost before native rule injection"
    for behavior, rules in ((1, projects), (2, shots)):
        reconstructed = f"Behavior {behavior}\n\n" + "\n\n".join(
            f"{index}. {rule}" for index, rule in enumerate(rules, 1)
        )
        assert reconstructed == (policy if behavior == 1 else binding)
        assert agent._split_behavior_rules(
            "\ufeff" + reconstructed.replace("\n", "\r\n") + "\r\n", 4
        ) == rules

    caller_rules = [{"name": "caller", "rules": ["caller-owned-context"]}]
    caller_before = copy.deepcopy(caller_rules)
    native_values = {
        "prompt": "native-visible-prompt",
        "additional_context": {"literal": "{{KEEP_ME}}", "shot_note": "한글"},
        "output_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}},
        "model": "caller-selected-model",
    }
    node._hmb_rules_active = True
    node._hmb_ruleset_names = ("project-private-scope", "shot-private-scope")
    node._hmb_policy_rules = projects
    node._hmb_binding_rules = shots
    node._hmb_runtime_prompt = "paired-machine {{KEEP_ME}}"
    node._hmb_native_prompt_read_active = True
    with patch.object(agent._BaseAgent, "get_parameter_list_value", return_value=caller_rules, create=True), patch.object(
        agent._BaseAgent, "get_parameter_value", lambda _self, name: native_values.get(name), create=True
    ), patch.object(agent._BaseAgent, "_process", lambda _self, native, text, *args: (native, text, args), create=True):
        combined = node.get_parameter_list_value("rulesets")
        assert combined == caller_rules + [
            {"name": node._hmb_ruleset_names[0], "rules": projects},
            {"name": node._hmb_ruleset_names[1], "rules": shots},
        ]
        assert caller_rules == caller_before
        assert combined is not caller_rules
        if agent._BuiltinAgent is not None:
            native_module = sys.modules[agent._BuiltinAgent.__module__]
            if hasattr(native_module, "rulesets_from_inputs"):
                # Current Standard/PydanticAI consumes normalized dictionary
                # rulesets. Verify the exact native normalizer and all eight
                # full rules rather than a retired Griptape-object adapter.
                native_rules = native_module.rulesets_from_inputs(combined)
                assert native_rules == combined
                assert [rule for ruleset in native_rules[1:] for rule in ruleset["rules"]] == projects + shots
            else:
                native_rules = native_module.build_rulesets_from_configs(
                    [native_module.ruleset_to_config(item) for item in combined]
                )
                assert [native_module.ruleset_to_config(item) for item in native_rules] == combined
                assert [rule.value for ruleset in native_rules[1:] for rule in ruleset.rules] == projects + shots
        assert node.get_parameter_value("prompt") == node._hmb_runtime_prompt
        for name in ("additional_context", "output_schema", "model"):
            assert node.get_parameter_value(name) is native_values[name]
        enriched = node._handle_additional_context(
            node.get_parameter_value("prompt"), native_values["additional_context"]
        )
        assert enriched.startswith(node._hmb_runtime_prompt + "\n\n")
        assert "{{KEEP_ME}}" in enriched
        context_json = enriched.split("HMB ADDITIONAL CONTEXT DATA (JSON):\n", 1)[1].splitlines()[0]
        assert json.loads(context_json) == native_values["additional_context"]
        native_sentinel = object()
        native_output_type = object()
        returned, model_input, forwarded = node._process(native_sentinel, enriched, native_output_type)
        assert returned is native_sentinel
        assert forwarded == (native_output_type,)
        assert model_input == agent._with_english_agent_output_contract(enriched)
        assert enriched in model_input
        node._hmb_native_prompt_read_active = False
        assert node.get_parameter_value("prompt") == native_values["prompt"]
        node._hmb_rules_active = False
        assert node.get_parameter_list_value("rulesets") is caller_rules

    cases = round_trips = 0
    for shot_number in range(1, 6):
        marker = "" if shot_number == 5 else "Red"
        for range_enabled in (False, True):
            for depth in (1, 4, 16):
                state = prompt._default_widget_state()
                state["text"]["SCENE_CONTEXT"] = f"Shot {shot_number}: independently authored action and camera."
                state["text"]["PRESERVED_TEXT"] = '표지 {{SIGN}} / "literal"'
                state["images"][0].update({
                    "present": True,
                    "label": f"approved-sheet-{shot_number}.png",
                    "image_main_type": "Character",
                    "image_sub_type": "Full Appearance",
                    "owner": f"Hero-{shot_number}",
                    "color_picks": [marker],
                    "binding_video_slots": [1],
                    "binding_scopes": ["Full body / full appearance"],
                    "frame_range_enabled": range_enabled,
                    "frame_range_intent": {
                        "version": 1, "enabled": range_enabled,
                        "start_frame": 1, "end_frame": 120,
                        "ranges": [{"start": 1, "end": 24}, {"start": 73, "end": 120}],
                        "selected_index": 0,
                    },
                    "frame_range_bindings": {f"@video1::{marker}": {
                        "video_slot": "@video1", "color_pick": marker, "enabled": True,
                        "origin": "manual", "start_frame": 1, "end_frame": 120,
                        "ranges": [{"start": 1, "end": 24}, {"start": 73, "end": 120}],
                    }},
                })
                look = copy.deepcopy(state["images"][0])
                look.update({
                    "slot": 2, "token": "@image2", "label": "authored-look.png",
                    "image_main_type": "Look Reference", "image_sub_type": "Lighting / Atmosphere",
                    "owner": "Global Look", "color_picks": [""],
                    "binding_scopes": ["Global Look"],
                    "frame_range_bindings": {
                        "@video1::": {
                            "video_slot": "@video1", "color_pick": "", "enabled": True,
                            "origin": "manual", "start_frame": 1, "end_frame": 120,
                            "ranges": [{"start": 1, "end": 24}, {"start": 73, "end": 120}],
                        },
                        "@video3::Blue": {
                            "video_slot": "@video3", "color_pick": "Blue", "enabled": True,
                            "origin": "manual", "start_frame": 1, "end_frame": 48,
                            "ranges": [{"start": 31, "end": 36}],
                        },
                    },
                })
                state["images"] = [state["images"][0], look]
                state["videos"] = [prompt._default_video_item(i) for i in (1, 2, 3)]
                for video, subtype in zip(state["videos"], ("Original Preview", "Mask", "Timing / Edit")):
                    video.update({
                        "present": True, "label": f"shot-{shot_number}-{subtype}.mp4",
                        "video_main_type": "Maya Preview / Playblast", "video_sub_type": subtype,
                        "keep_out": "Keep foreground boundary readable.\nLiteral {{KEEP_OUT}}",
                    })
                canonical = prompt._normalize_state(copy.deepcopy(state))
                expected_machine = prompt._build_data_only_prompt_package(canonical)
                for _ in range(depth):
                    canonical = prompt._normalize_state(json.loads(json.dumps(canonical, ensure_ascii=False)))
                    assert prompt._build_data_only_prompt_package(canonical) == expected_machine
                    round_trips += 1
                visible = prompt._build_prompt_package(canonical)
                machine = prompt._build_data_only_prompt_package(canonical)
                job = json.loads(machine.splitlines()[2])
                assert job["images"][0]["target_id"] == f"Hero-{shot_number}"
                assert job["images"][1]["image_main_type"] == "Look Reference"
                assert job["images"][1]["image_sub_type"] == "Lighting / Atmosphere"
                assert job["videos"][0]["control_role"] == "Primary Unified Shot Control"
                assert job["videos"][1]["control_role"] == "Mask / Guide Only"
                assert job["videos"][2]["control_role"] == "Timing Only"
                assert [item["video"] for item in job["videos"]] == ["@video1", "@video2", "@video3"]
                if range_enabled:
                    assert job["frame_ranges"][0]["segments"] == [
                        {"start_frame": 1, "end_frame": 24},
                        {"start_frame": 73, "end_frame": 120},
                    ]
                    look_ranges = [item for item in job["frame_ranges"] if item["image"] == "@image2"]
                    assert {(item["video"], item["marker_color"]) for item in look_ranges} == {
                        ("@video1", ""), ("@video3", "Blue")
                    }, look_ranges
                    assert next(item for item in look_ranges if item["video"] == "@video3")["segments"] == [
                        {"start_frame": 31, "end_frame": 36}
                    ]
                else:
                    assert job["frame_ranges"] == []
                assert json.loads(machine.splitlines()[6])["PRESERVED_TEXT"] == state["text"]["PRESERVED_TEXT"]
                snapshot = {
                    "schema": "hmb-prompt-paired-snapshot", "version": 1, "generation": depth,
                    "visible_sha256": hashlib.sha256(visible.encode()).hexdigest(),
                    "machine_sha256": hashlib.sha256(machine.encode()).hexdigest(),
                    "machine_prompt": machine,
                }
                source = SimpleNamespace(_hmb_agent_prompt_snapshot=lambda _text: dict(snapshot))
                assert agent._paired_machine_prompt(
                    SimpleNamespace(_hmb_verified_prompt_source_node=source), visible
                ) == machine
                # A previous Layout role must not survive selecting Original Preview.
                switched = copy.deepcopy(canonical)
                switched["videos"][0].update({"video_main_type": "Motion Reference", "video_sub_type": "Layout Reference"})
                layout_job = json.loads(prompt._build_data_only_prompt_package(switched).splitlines()[2])
                assert layout_job["videos"][0]["reference_scope"]["frame_by_frame_motion_matching"] is False
                switched["videos"][0].update({
                    "video_main_type": "Maya Preview / Playblast", "video_sub_type": "Original Preview",
                    "reference_scope": layout_job["videos"][0]["reference_scope"],
                })
                restored_job = json.loads(prompt._build_data_only_prompt_package(switched).splitlines()[2])
                assert restored_job["videos"][0]["control_role"] == "Primary Unified Shot Control"
                assert "reference_scope" not in restored_job["videos"][0]
                # Generator's finishing handoff must leave the approved Agent text exact.
                resolved = f"Shot {shot_number}: @image1 identity; @video1 performance and camera.\n{{{{SIGN}}}}"
                beauty = finish.default_finish_look_state()
                assert generator.HMBSeedanceGeneration._compose_finish_look_prompt(
                    resolved, finish.compile_finish_look_prompt(beauty)
                ) == resolved
                beauty["beauty"]["enabled"] = True
                beauty_text = finish.compile_finish_look_prompt(beauty)
                submitted = generator.HMBSeedanceGeneration._compose_finish_look_prompt(resolved, beauty_text)
                assert submitted.startswith("HMB RESOLVED SHOT INSTRUCTION\n" + resolved + "\n\n")
                assert submitted.count(resolved) == 1
                assert beauty_text in submitted
                cases += 1
    node._clear_hmb_runtime_policy()
    assert node._hmb_policy_rules == node._hmb_binding_rules == []
    assert node._hmb_runtime_prompt == ""
    print(
        f"HMB V5.6 policy propagation: PASS ({mode}; {version}; "
        f"4+4 full rules; native rule conversion={agent._BuiltinAgent is not None}; "
        f"context/schema preserved; {cases} media cases; "
        f"{round_trips} recursive round trips; no model/provider call)"
    )


if __name__ == "__main__":
    main()
