"""Offline effective-settings and scoped-input contracts for the v7 policy.

Exercises the real Generator parent mapper, Agent snapshot/facade and native
input seam. Model invocation, network and graph execution are never performed.
No private policy plaintext is loaded or reproduced by these fixtures.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
if standard.is_dir():
    os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(standard))

import HMBAgentLibrary as agent_module
import HMBSeedanceGeneration as generator
import _hmb_agent_media as media_module


PROMPT = (
    'PROJECT_STYLE_LOOK: cel finish for hero only; camera unchanged.\n'
    'PRESERVED_TEXT: {{SIGN}} {% include "literal" %} 안녕 0 OFF\n'
    'Use @image1 for hero-A identity, @image2 for scene lighting, '
    '@video1 for approved camera/animation; revise only hero-A expression in 121-132.'
)


def media_snapshot():
    intervals = [{"enabled": True, "video": "@video1", "segments": [
        {"start_frame": 101, "end_frame": 120},
        {"start_frame": 140, "end_frame": 160}]}]
    return {"schema": "hmb-agent-reference-media", "version": 1, "images": [
        {"token": "@image1", "source": "C:/offline/hero.png", "image_main_type": "Character",
         "image_sub_type": "Full Appearance", "target_id": "hero-A", "frame_ranges": copy.deepcopy(intervals)},
        {"token": "@image2", "source": "C:/offline/look.png", "image_main_type": "Look Reference",
         "image_sub_type": "Lighting / Atmosphere", "target_id": "", "frame_ranges": copy.deepcopy(intervals)},
    ], "videos": [
        {"token": "@video1", "source": "C:/offline/preview.mov",
         "video_main_type": "Maya Preview / Playblast", "video_sub_type": "Original Preview",
         "control_role": "Primary Unified Shot Control", "target_id": "", "frame_ranges": []},
        {"token": "@video2", "source": "C:/offline/layout.mov", "video_main_type": "Motion Reference",
         "video_sub_type": "Layout Reference", "control_role": "Camera / Layout Preserved; Free Character Motion",
         "target_id": "hero-B", "frame_ranges": copy.deepcopy(intervals)},
    ]}


def frozen_parent(**changes):
    value = {"model": generator.SEEDANCE_2_5_MODEL_ID,
             "input_mode": generator.INPUT_MODE_MULTIMODAL_REFERENCES,
             "quality": "480p", "duration_seconds": 4, "aspect_ratio": "16:9",
             "generate_audio": False, "watermark": False, "output_format": "mov",
             "return_last_frame": False, "priority": 0, "draft": True}
    value.update(changes)
    return value


def owner():
    node = object.__new__(agent_module.HMBAgentLibrary)
    node.name = "offline_v7_execution_context"
    node.metadata = {"library": "HMB_GP_Production", "node_type": "HMBAgentLibrary"}
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._cancellation_requested = threading.Event()
    node._hmb_lifecycle_is_live = lambda *_args: True
    node._hmb_rules_active = False
    node.parameter_values = {"prompt": "ORIGINAL USER PROMPT", "model": "unchanged-native-model",
        "model_provider": "unchanged-native-provider", "output_schema": {"type": "object"},
        "tools": [], "rulesets": [], "additional_context": {"SIGN": "DO NOT SUBSTITUTE"}}
    node.parameter_output_values = {"output": "ORIGINAL OUTPUT"}
    node.get_parameter_value = lambda name: copy.deepcopy(node.parameter_values.get(name))
    node.get_parameter_list_value = lambda name: copy.deepcopy(node.parameter_values.get(name, []))
    node._begin_hmb_reference_observation = lambda *_args: "offline-observation"
    node._store_hmb_reference_observation = lambda *_args: None
    node._mark_hmb_reference_observation_submission = lambda *_args: None
    return node


class ExecutionContextTests(unittest.TestCase):
    def test_draft_parent_mode_reaches_agent_instead_of_being_silently_dropped(self):
        for draft, expected in ((True, generator.DRAFT_ACTION_PREVIEW), (False, generator.DRAFT_ACTION_OFF)):
            with self.subTest(draft=draft):
                frozen = frozen_parent(draft=draft)
                before = copy.deepcopy(frozen)
                execution, context = generator._web_rerender_parent_execution_settings(frozen)
                _, captured = agent_module._web_rerender_snapshots(media_snapshot(), context, PROMPT)
                self.assertEqual(captured["draft_action"], expected)
                self.assertEqual(captured["draft_action"], execution["draft_action"])
                self.assertEqual(captured["resolution"], "480p")
                self.assertEqual(frozen, before)

    def test_absent_parent_draft_is_not_invented_as_an_authoritative_setting(self):
        frozen = frozen_parent()
        del frozen["draft"]
        execution, context = generator._web_rerender_parent_execution_settings(frozen)
        _, captured = agent_module._web_rerender_snapshots(media_snapshot(), context, PROMPT)
        self.assertEqual(execution["draft_action"], generator.DRAFT_ACTION_OFF)
        self.assertNotIn("draft_action", context)
        self.assertNotIn("draft_action", captured)

    def test_scalar_types_false_zero_format_and_arbitrary_current_model_are_preserved(self):
        for output_format in ("mov", "mp4"):
            with self.subTest(output_format=output_format):
                settings = {"model_id": "native-custom-model", "task": "native-task", "resolution": "480p",
                    "draft_action": generator.DRAFT_ACTION_PREVIEW, "generate_audio": False,
                    "return_last_frame": False, "seed": 0, "priority": 0, "output_format": output_format,
                    "broker_api_key": "NEVER_MODEL_CONTEXT", "draft_job_id": "NEVER_SOURCE_CAPABILITY"}
                _, captured = agent_module._web_rerender_snapshots(media_snapshot(), settings, PROMPT)
                self.assertEqual(captured, {key: value for key, value in settings.items()
                    if key not in {"broker_api_key", "draft_job_id"}})
                self.assertIs(captured["generate_audio"], False)
                self.assertIs(type(captured["seed"]), int)
        for invalid in (True, 0, {}, [], None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                agent_module._web_rerender_snapshots(media_snapshot(), {"draft_action": invalid}, PROMPT)

    def test_selected_roles_targets_blank_scene_scope_and_disjoint_ranges_remain_data(self):
        original = media_snapshot()
        before = copy.deepcopy(original)
        captured, settings = agent_module._web_rerender_snapshots(original, {}, PROMPT)
        expected = copy.deepcopy(original)
        expected["machine_sha256"] = hashlib.sha256(PROMPT.encode()).hexdigest()
        self.assertEqual(captured, expected)
        self.assertEqual(settings, {})
        captured["images"][0]["frame_ranges"][0]["segments"][0]["start_frame"] = 999
        captured["videos"][0]["target_id"] = "changed"
        self.assertEqual(original, before)

    def test_actual_web_facade_native_seam_gets_effective_draft_and_literal_prompt_once(self):
        retained = owner()
        before = copy.deepcopy((retained.parameter_values, retained.parameter_output_values))
        _, context = generator._web_rerender_parent_execution_settings(frozen_parent())
        selected, context = agent_module._web_rerender_snapshots(media_snapshot(), context, PROMPT)
        facade = agent_module._HMBWebRerenderExecution._from_owner(retained, PROMPT, selected, context)
        calls = []
        observations = []

        def native(_node, target, prompt):
            calls.append(prompt)
            return target

        def optional_pixels(prompt, snapshot, _target, **_kwargs):
            observations.append(copy.deepcopy(snapshot))
            return prompt

        with patch.object(agent_module._BaseAgent, "_process", native, create=True), \
             patch.object(agent_module, "_run_native_with_literal_hmb_input",
                side_effect=lambda processor, target, value: processor(target, value)), \
             patch.object(media_module, "augment_prompt", optional_pixels), \
             patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
             patch.object(agent_module._hmb, "_load_agent_rule_payload", side_effect=AssertionError("web policy reload forbidden")):
            target = SimpleNamespace(tasks=[])
            self.assertIs(facade._process(target, PROMPT), target)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith(PROMPT + "\n\n"))
        self.assertIn("HMB RECORDED PARENT GENERATOR SETTINGS (READ-ONLY DATA)", calls[0])
        self.assertIn('"draft_action":"Draft 480p"', calls[0])
        self.assertIn('"generate_audio":false', calls[0])
        self.assertIn('"priority":0', calls[0])
        self.assertEqual(observations, [selected])
        self.assertEqual((retained.parameter_values, retained.parameter_output_values), before)
        self.assertEqual(facade.parameter_values["model"], "unchanged-native-model")
        self.assertFalse(facade._hmb_rules_active)

    def test_optional_context_and_pixel_failures_continue_existing_native_input(self):
        for fail_settings in (False, True):
            with self.subTest(fail_settings=fail_settings):
                node = owner()
                node._hmb_rules_active = True
                node._hmb_runtime_prompt = PROMPT
                def settings(_expected):
                    if fail_settings:
                        raise RuntimeError("optional context unavailable")
                    return {"common": {"generate_audio": False, "output_format": "mov"}}
                node._hmb_verified_prompt_source_node = SimpleNamespace(
                    _hmb_agent_generation_context=settings,
                    _hmb_agent_reference_media=lambda _expected: {
                        "machine_sha256": hashlib.sha256(PROMPT.encode()).hexdigest()})
                calls = []
                with patch.object(agent_module._BaseAgent, "_process",
                        lambda _node, _target, value: calls.append(value) or value, create=True), \
                     patch.object(agent_module, "_run_native_with_literal_hmb_input",
                        side_effect=lambda processor, target, value: processor(target, value)), \
                     patch.object(media_module, "augment_prompt", side_effect=RuntimeError("optional decode unavailable")), \
                     patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
                    result = node._process(SimpleNamespace(tasks=[]), PROMPT)
                self.assertEqual(len(calls), 1)
                self.assertTrue(result.startswith(PROMPT))
                self.assertIn("{{SIGN}}", result)
                self.assertIn('{% include "literal" %}', result)
                self.assertIn("안녕 0 OFF", result)
                self.assertNotIn("optional decode unavailable", result)
                self.assertEqual(node.parameter_values["model"], "unchanged-native-model")

    def test_text_only_driver_continuation_does_not_decode_or_drop_typed_sources(self):
        selected = media_snapshot()
        before = copy.deepcopy(selected)
        reports = []
        with patch.object(media_module, "driver_accepts_images", return_value=False), \
             patch.object(media_module, "_source", side_effect=AssertionError("must not decode")), \
             patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            result = media_module.augment_prompt(PROMPT, selected, SimpleNamespace(tasks=[]), report_sink=reports.append)
        self.assertEqual(result, PROMPT)
        self.assertEqual(selected, before)
        self.assertEqual(reports[0]["native_input_status"], "text_only")
        self.assertEqual(reports[0]["unobserved_media_tokens"], ["@image1", "@image2", "@video1", "@video2"])
        self.assertEqual(reports[0]["coverage"], [])

    def test_pixel_labels_preserve_declared_scope_and_do_not_promote_path_to_authority(self):
        selected = media_snapshot()
        for kind in ("image", "video"):
            for record in selected[kind + "s"]:
                with self.subTest(token=record["token"]):
                    before = copy.deepcopy(record)
                    label = media_module._label(record, kind)
                    self.assertEqual(label["target_id"], record["target_id"])
                    self.assertEqual(label["frame_ranges"], record["frame_ranges"])
                    self.assertEqual(label[kind + "_sub_type"], record[kind + "_sub_type"])
                    self.assertNotIn("source", label)
                    self.assertNotIn("priority", label)
                    self.assertEqual(record, before)

    def test_stale_web_source_snapshot_is_rejected_without_guessing_replacement(self):
        selected, context = agent_module._web_rerender_snapshots(media_snapshot(), {}, PROMPT)
        source = agent_module._HMBWebRerenderSource(PROMPT, selected, context)
        for getter in (source._hmb_agent_reference_media, source._hmb_agent_generation_context):
            with self.subTest(getter=getter.__name__), self.assertRaises(RuntimeError):
                getter("different-parent")
        returned = source._hmb_agent_reference_media(PROMPT)
        returned["images"].clear()
        self.assertEqual(len(source._hmb_agent_reference_media(PROMPT)["images"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
