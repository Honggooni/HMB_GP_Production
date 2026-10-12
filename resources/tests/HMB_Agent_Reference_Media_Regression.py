"""Offline native artifact, selected-source, bounded decode and continuation checks."""
from __future__ import annotations

import ast
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_agent_media as media
from griptape.artifacts import ImageArtifact, ListArtifact, TextArtifact
from griptape.common import PromptStack
from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver
from griptape_nodes.drivers.cloud_models import MODEL_CHOICES_ARGS, VISION_MODEL_CHOICES
from PIL import Image


def agent(model=None):
    return SimpleNamespace(tasks=[SimpleNamespace(prompt_driver=GriptapeCloudPromptDriver(
        model=model or VISION_MODEL_CHOICES[0], api_key="offline-not-invoked"))])


def snapshot(images=(), videos=()):
    return {"schema": "hmb-agent-reference-media", "version": 1,
            "images": list(images), "videos": list(videos)}


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.picture = self.directory / "character.png"
        Image.new("RGB", (80, 40), "red").save(self.picture)
        self.record = {"token": "@image1", "source": str(self.picture),
                       "source_type": "Character Sheet", "target_id": "ch_A",
                       "frame_ranges": [{"enabled": True, "segments": [
                           {"start_frame": 10, "end_frame": 20}]}]}

    def tearDown(self):
        self.temp.cleanup()

    def test_probe_discovery_is_independent_of_imageio_decoder(self):
        name = "ffmpeg.exe" if media.os.name == "nt" else "ffmpeg"
        probe_name = "ffprobe.exe" if media.os.name == "nt" else "ffprobe"
        decoder = self.directory / "imageio" / name
        decoder.parent.mkdir()
        decoder.write_bytes(b"fixture: never executed")
        package = self.directory / "static_ffmpeg"
        probe = package / "bin" / ("win32" if media.os.name == "nt" else "linux") / probe_name
        probe.parent.mkdir(parents=True)
        probe.write_bytes(b"fixture: never executed")
        explicit_probe = self.directory / ("explicit-" + probe_name)
        explicit_probe.write_bytes(b"fixture: never executed")
        modules = {"imageio_ffmpeg": SimpleNamespace(get_ffmpeg_exe=lambda: str(decoder)),
                   "static_ffmpeg": SimpleNamespace(__file__=str(package / "__init__.py"))}
        with patch.dict(sys.modules, modules), patch.dict(media.os.environ, {"FFMPEG_PATH": "", "FFPROBE_PATH": ""}):
            self.assertEqual(media._binaries(), (decoder, probe))
            with patch.dict(media.os.environ, {"FFPROBE_PATH": str(explicit_probe)}):
                self.assertEqual(media._binaries(), (decoder, explicit_probe))
            sibling_probe = decoder.with_name(probe_name)
            sibling_probe.write_bytes(b"fixture: never executed")
            self.assertEqual(media._binaries(), (decoder, sibling_probe))

    def test_native_multimodal_serialization_keeps_source_identity_and_text(self):
        prompt = "EXACT INPUT {{SIGN}} @image1 @video1"
        result = media.augment_prompt(prompt, snapshot([self.record]), agent())
        self.assertIsInstance(result, ListArtifact)
        self.assertTrue(result.value[0].value.startswith(prompt))
        label = result.value[1].value
        self.assertIn('"target_id":"ch_A"', label)
        self.assertIn('"start_frame":10', label)
        self.assertNotIn(str(self.picture), label)
        self.assertIsInstance(result.value[2], ImageArtifact)
        stack = PromptStack.from_artifact(result)
        body = agent().tasks[0].prompt_driver._base_params(stack)
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(len(body["messages"][0]["content"]), 3)
        self.assertIn("image", str(body["messages"][0]["content"][2]).lower())

    def test_nonvision_and_unknown_provider_keep_same_text(self):
        nonvision = next(str(v["name"]) for v in MODEL_CHOICES_ARGS if not v.get("vision"))
        prompt = "unchanged"
        with patch.object(media, "_source", side_effect=AssertionError("must not decode")):
            self.assertEqual(media.augment_prompt(prompt, snapshot([self.record]), agent(nonvision)), prompt)
            unknown = SimpleNamespace(tasks=[SimpleNamespace(prompt_driver=SimpleNamespace(model=VISION_MODEL_CHOICES[0]))])
            self.assertEqual(media.augment_prompt(prompt, snapshot([self.record]), unknown), prompt)

    def test_missing_remote_and_bad_images_are_optional(self):
        records = [{"token": "@image1", "source": "https://example.invalid/private.png"},
                   {"token": "@image2", "source": str(self.directory / "missing.png")}]
        bad = self.directory / "bad.png"
        bad.write_text("not an image")
        records.append({"token": "@image3", "source": str(bad)})
        self.assertEqual(media.augment_prompt("preserve all refs", snapshot(records), agent()), "preserve all refs")
        for value in ("https://example.invalid/a.png", "asset://id", "\\\\server\\asset.png"):
            with self.assertRaises(ValueError):
                media._source(value, "image")

    def test_partial_coverage_and_limits_are_truthful(self):
        records = [dict(self.record, token=f"@image{i}") for i in range(1, 18)]
        result = media.augment_prompt("all 17 remain", snapshot(records), agent())
        self.assertEqual(sum(isinstance(v, ImageArtifact) for v in result.value), media.MAX_IMAGE_ATTACHMENTS)
        self.assertIn('"@image17"', result.value[0].value)
        self.assertIn("Sampling is partial", result.value[0].value)

    def test_cancellation_and_expired_budget_preserve_text(self):
        self.assertEqual(media.augment_prompt("text", snapshot([self.record]), agent(), is_live=lambda: False), "text")
        with patch.object(media, "PREPARATION_SECONDS", 0):
            self.assertEqual(media.augment_prompt("text", snapshot([self.record]), agent()), "text")
        with patch.object(media, "_decode", side_effect=subprocess.TimeoutExpired("ffmpeg", 0.1)):
            self.assertEqual(media.augment_prompt("text", snapshot([self.record]), agent()), "text")

    def test_decoder_timeout_terminates_real_child(self):
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            media._run([sys.executable, "-c", "import time; time.sleep(10)"], started + .1)
        self.assertLess(time.monotonic() - started, 2.0)

    def test_actual_griptape_task_retains_images_and_existing_rules(self):
        from griptape.common import Message, TextMessageContent
        from griptape.rules import Rule, Ruleset
        from griptape.structures import Agent
        driver = agent().tasks[0].prompt_driver
        native = Agent(prompt_driver=driver, rulesets=[Ruleset(name="caller", rules=[Rule("Caller instruction")])])
        prepared = media.augment_prompt("EXACT SOURCE", snapshot([self.record]), native)
        captured = []
        def offline_run(_driver, stack):
            captured.append(stack)
            return Message(role=Message.ASSISTANT_ROLE, content=[TextMessageContent(TextArtifact("Final shot prompt"))])
        logging.disable(logging.CRITICAL)
        try:
            with patch.object(GriptapeCloudPromptDriver, "try_run", offline_run):
                native.run(prepared)
        finally:
            logging.disable(logging.NOTSET)
        self.assertEqual(len(captured), 1)
        self.assertIn("Caller instruction", captured[0].system_messages[0].to_text())
        self.assertTrue(any(content.__class__.__name__ == "ImageMessageContent"
                            for message in captured[0].user_messages for content in message.content))
        self.assertEqual(native.output.value, "Final shot prompt")

    def test_file_change_invalidates_cache_and_pillow_fallback(self):
        source, before = media._source(str(self.picture), "image")
        first = media._decode(source, before, None, None, time.monotonic() + 5)
        Image.new("RGB", (64, 32), "blue").save(self.picture)
        source, after = media._source(str(self.picture), "image")
        second = media._decode(source, after, None, None, time.monotonic() + 5)
        self.assertNotEqual(before, after)
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(second[1:3], (64, 32))

    def test_local_video_real_decode_reports_sampled_pts(self):
        ffmpeg, probe = media._binaries()
        if ffmpeg is None or probe is None:
            self.skipTest("Local FFmpeg and FFprobe not installed")
        path = self.directory / "preview.mp4"
        subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                        "testsrc=size=160x90:rate=10:duration=2", "-pix_fmt", "yuv420p",
                        "-threads", "1", str(path)], check=True, timeout=10,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record = {"token": "@video1", "source": str(path), "source_type": "UnifiedShot-Control",
                  "video_sub_type": "Original Preview"}
        result = media.augment_prompt("Keep subject and camera motion", snapshot(videos=[record]), agent())
        self.assertIsInstance(result, ListArtifact)
        labels = [v.value for v in result.value[1:] if isinstance(v, TextArtifact)]
        self.assertEqual(len(labels), 3)
        decoded = [json.loads(v.split(": ", 1)[1]) for v in labels]
        self.assertEqual([v["token"] for v in decoded], ["@video1"] * 3)
        self.assertEqual([v["decoded_pts_seconds"] for v in decoded], [0.0, 1.0, 1.9])
        self.assertTrue(all("unverified" in v["coverage"] for v in decoded))


class NativeSeamTests(unittest.TestCase):
    def test_native_called_once_and_optional_failure_never_changes_plain_path(self):
        tree = ast.parse((ROOT / "HMBAgentLibrary.py").read_text(encoding="utf-8"))
        source_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "HMBAgentLibrary")
        method = next(n for n in source_class.body if isinstance(n, ast.FunctionDef) and n.name == "_process")
        native_calls = []
        class Native:
            def _process(self, model_agent, prompt):
                native_calls.append(prompt)
                return prompt
        adapted = ast.ClassDef(name="Adapter", bases=[ast.Name(id="Native", ctx=ast.Load())],
                               keywords=[], body=[method], decorator_list=[])
        namespace = {"Native": Native, "Any": object, "json": json,
                     "_VERIFIED_PROMPT_SOURCE_ATTRIBUTE": "source",
                     "_prompt_text_sha256": lambda v: hashlib.sha256(v.encode()).hexdigest(),
                     "_run_native_with_literal_hmb_input": lambda native, target, value: native(target, value),
                     "_with_english_agent_output_contract": lambda v: str(v) + "\nENGLISH CONTRACT"}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[adapted], type_ignores=[])), "native_seam", "exec"), namespace)
        node = namespace["Adapter"]()
        node._hmb_rules_active = True
        node._hmb_runtime_prompt = "machine"
        node._hmb_lifecycle_generation = 1
        node._hmb_lifecycle_is_live = lambda generation: True
        node.source = SimpleNamespace(
            _hmb_agent_generation_context=lambda value: {"common": {"duration_seconds": 8}},
            _hmb_agent_reference_media=lambda value: {"machine_sha256": "stale"})
        with patch.object(media, "augment_prompt", side_effect=AssertionError("stale must not decode")):
            result = node._process(agent(), "native additional_context")
        self.assertEqual(len(native_calls), 1)
        self.assertIn('"duration_seconds":8', result)
        self.assertTrue(result.startswith("native additional_context"))
        node._hmb_rules_active = False
        self.assertEqual(node._process(agent(), "plain native input"), "plain native input")
        self.assertEqual(len(native_calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
