"""Real local media and native Standard model serialization, with zero provider calls."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_reference_analysis as analysis


def observations(kind: str, *, start=None, end=None) -> dict:
    rows = {category: [] for category in analysis.ANALYSIS_CATEGORIES[kind]}
    category = next(iter(rows))
    rows[category].append({"observation": "관찰", "interpretation": "해석", "start": start, "end": end})
    return rows


class ReferenceAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg, cls.probe = analysis._binaries()
        if not cls.ffmpeg or not cls.probe:
            raise RuntimeError("FFmpeg and FFprobe are required for this regression.")
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.image = cls.root / "fixture.png"
        cls.video = cls.root / "fixture.mp4"
        cls.audio = cls.root / "fixture.wav"
        cls.media("-f", "lavfi", "-i", "color=c=blue:s=80x48:d=1", "-frames:v", "1", "-c:v", "png", str(cls.image))
        cls.media("-f", "lavfi", "-i", "color=c=red:s=80x48:r=24:d=1", "-f", "lavfi", "-i", "color=c=blue:s=80x48:r=24:d=1",
                  "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", str(cls.video))
        cls.media("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "pcm_s16le", str(cls.audio))

    @classmethod
    def media(cls, *args):
        subprocess.run([str(cls.ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", *args],
                       capture_output=True, timeout=15, check=True)

    def test_image_and_audio_return_independently_selectable_evidence(self):
        cases = {
            "image": ("composition", "lighting_reference", "color_look", "character_pose", "appearance"),
            "audio": ("audio_content", "audio_delivery", "audio_rhythm", "audio_effects", "audio_timing"),
        }
        for kind, keys in cases.items():
            with self.subTest(kind=kind):
                self.assertEqual(analysis.ANALYSIS_CATEGORIES[kind], keys)
                span = {"start": 0.0, "end": 2.0} if kind == "audio" else {"start": None, "end": None}
                prompt = analysis._prompt(kind, span, {}, "")
                fixture = {category: [] for category in analysis.ANALYSIS_CATEGORIES[kind]}
                for key in keys:
                    self.assertIn(key, prompt)
                    fixture[key] = [{"observation": f"Fixture {key}"}]
                normalized = analysis._normalize_observations(fixture, kind, span)
                self.assertEqual([key for key, rows in normalized.items() if rows], list(keys))

    def test_video_observations_keep_only_decoded_timing_anchors(self):
        span = {"start": 0.0, "end": 2.0}
        evidence = {"frame_times": [0.0, 0.666667, 1.0, 1.5], "cut_candidates": [1.0, 1.25]}
        fixture = observations("video")
        fixture["cut_timing"] = [
            {"observation": "change between frames", "start": 0.667, "end": 1.0},
            {"observation": "unsupported time", "start": 1.25},
        ]
        cuts = analysis._normalize_observations(fixture, "video", span, evidence=evidence)["cut_timing"]
        self.assertEqual((cuts[0]["start"], cuts[0]["end"]), (0.666667, 1.0))
        self.assertEqual((cuts[1]["start"], cuts[1]["end"]), (None, None))
        self.assertEqual(cuts[1]["observation"], "unsupported time")

    def test_disjoint_frame_and_audio_ranges_use_only_selected_media(self):
        self.assertEqual(analysis.normalize_analysis_ranges([{"start": 36, "end": 39},
            {"start": 0, "end": 2}], kind="video"),
            [{"start": 0, "end": 2}, {"start": 36, "end": 39}])
        for kind, ranges in (("video", []), ("video", [{"start": 0, "end": 2}, {"start": 2, "end": 4}]),
                             ("audio", [{"start": 0.5, "end": 1.5}, {"start": 1.0, "end": 1.8}])):
            with self.assertRaises(analysis.AnalysisError) as failure:
                analysis.normalize_analysis_ranges(ranges, kind=kind)
            self.assertEqual(failure.exception.code, "ANALYSIS_INVALID_RANGE")
        info = analysis.analysis_video_frame_info(str(self.video), legacy_start=0.0, legacy_end=0.2)
        self.assertEqual(info["frame_count"], 48)
        self.assertAlmostEqual(info["frame_rate"], 24.0)
        self.assertEqual(info["legacy_frame_ranges"], [{"start": 0, "end": 4}])
        self.assertEqual(analysis.analysis_video_frame_info(str(self.video), legacy_start=99)["legacy_frame_ranges"], [])
        self.assertAlmostEqual(analysis.analysis_audio_duration(str(self.audio)), 2.0, places=2)

        captured = []
        def invoke(_node, _model, _prompt, attachments, _live, mark_submitted):
            mark_submitted()
            captured.append(attachments)
            return observations("video" if attachments[0][2] == "image/png" else "audio")

        video = analysis.analyze_reference(None, source=str(self.video), kind="video",
            frame_ranges=[{"start": 0, "end": 2}, {"start": 36, "end": 39}], invoke=invoke,
            cache_dir=self.root / "disjoint-frame-cache")
        observed = {row["frame"] for row in video["evidence"]["sampled_frames"]}
        self.assertTrue(observed)
        self.assertTrue(observed <= {0, 1, 2, 36, 37, 38, 39})
        self.assertEqual(len(captured[0]), len(observed))
        self.assertTrue(all(blob.startswith(b"\x89PNG\r\n\x1a\n") for _, blob, _ in captured[0]))
        self.assertEqual(video["range"]["frame_ranges"], [{"start": 0, "end": 2}, {"start": 36, "end": 39}])
        audio = analysis.analyze_reference(None, source=str(self.audio), kind="audio",
            time_ranges=[{"start": 0.0, "end": 0.25}, {"start": 1.25, "end": 1.5}], invoke=invoke,
            cache_dir=self.root / "disjoint-audio-cache")
        self.assertEqual(audio["range"]["time_ranges"],
            [{"start": 0.0, "end": 0.25}, {"start": 1.25, "end": 1.5}])
        self.assertEqual(len(captured[1]), 2)
        self.assertIn("source offset 1.250000", captured[1][1][0])
        self.assertTrue(all(blob.startswith(b"RIFF") for _, blob, _ in captured[1]))

    def test_whole_video_samples_full_duration_without_a_range(self):
        long_video = self.root / "long-video.mp4"
        self.media("-f", "lavfi", "-i", "testsrc2=size=80x48:rate=5:duration=40",
                   "-c:v", "libx264", str(long_video))
        calls = []

        def invoke(_node, _model, _prompt, attachments, _live, mark_submitted):
            mark_submitted()
            calls.append(attachments)
            return observations("video")

        result = analysis.analyze_reference(None, source=str(long_video), kind="video", invoke=invoke,
                                            cache_dir=self.root / "whole-video-cache")
        self.assertEqual(result["range"], {"start": 0.0, "end": 40.0})
        self.assertEqual(result["evidence"]["mode"], "timestamped_frames")
        times = result["evidence"]["frame_times"]
        self.assertLessEqual(len(times), 8)
        self.assertEqual(times[0], 0)
        self.assertGreaterEqual(times[-1], 39)
        for start in (0, 10, 20, 30):
            self.assertTrue(any(start <= time < start + 10 for time in times))
        self.assertEqual(len(calls[0]), len(times))
        with self.assertRaises(analysis.AnalysisError) as explicit:
            analysis.analyze_reference(None, source=str(long_video), kind="video", start=0, end=40, invoke=invoke,
                                       cache_dir=self.root / "whole-video-cache")
        self.assertEqual(explicit.exception.code, "ANALYSIS_INVALID_RANGE")
        self.assertEqual(len(calls), 1)

    def test_frame_ranges_use_irregular_pts_and_measured_final_duration(self):
        times = [0.0, 0.04, 0.14, 0.30]
        scope = analysis._video_frame_scope([{"start": 1, "end": 1}, {"start": 3, "end": 3}],
                                             times, duration=0.40, last_duration=None)
        self.assertEqual(scope["time_ranges"], [
            {"start": 0.04, "end": 0.14, "start_frame": 1, "end_frame": 1},
            {"start": 0.30, "end": 0.40, "start_frame": 3, "end_frame": 3},
        ])
        with self.assertRaises(analysis.AnalysisError) as failure:
            analysis._video_frame_scope([{"start": 3, "end": 3}], times, duration=None, last_duration=None)
        self.assertEqual(failure.exception.code, "ANALYSIS_FRAME_METADATA_UNAVAILABLE")

    def test_image_and_video_attach_real_bytes_and_reuse_result(self):
        calls = []

        def invoke(node, model, prompt, attachments, is_live, mark_submitted):
            mark_submitted()
            calls.append((prompt, attachments))
            kind = "video" if "timestamped_frames" in prompt else "image"
            return observations(kind, start=1.0 if kind == "video" else None)

        cache = self.root / "visual-cache"
        image = analysis.analyze_reference(None, source=str(self.image), kind="image", invoke=invoke, cache_dir=cache)
        uri = "data:image/png;base64," + base64.b64encode(self.image.read_bytes()).decode("ascii")
        cached = analysis.analyze_reference(None, source=uri, kind="image", invoke=invoke, cache_dir=cache)
        self.assertEqual(image["cache_key"], cached["cache_key"])
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(calls[0][1][0][1][:8], b"\x89PNG\r\n\x1a\n")
        self.assertNotIn(str(self.image), calls[0][0])

        video = analysis.analyze_reference(None, source=str(self.video), kind="video", start=0, end=2,
                                           invoke=invoke, cache_dir=cache)
        same_video = analysis.analyze_reference(None, source=str(self.video), kind="video", invoke=invoke, cache_dir=cache)
        self.assertEqual(video["cache_key"], same_video["cache_key"])
        self.assertTrue(same_video["cache_hit"])
        self.assertEqual(len(calls), 2)
        self.assertGreaterEqual(len(video["evidence"]["frame_times"]), 4)
        self.assertEqual(len(set(blob for _, blob, _ in calls[1][1])), 2)
        self.assertIn(1.0, video["evidence"]["cut_candidates"])
        self.assertIn(1.0, video["evidence"]["frame_times"])
        for span, guidance in (({"start": 0.5, "end": 2}, ""), ({}, "효과 참고")):
            different = analysis.analyze_reference(None, source=str(self.video), kind="video", **span, guidance=guidance,
                                                   invoke=invoke, cache_dir=cache)
            self.assertNotEqual(video["cache_key"], different["cache_key"])
        self.assertEqual(len(calls), 4)
        self.assertIn("효과 참고", calls[-1][0])

    def test_installed_sdk_serializes_image_video_and_wav_inputs(self):
        import httpx
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from griptape_nodes_library.llm.models import override_model
        from griptape_nodes_library.utils import model_invocation

        requests = []
        receipts = []
        active_kind = ""

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            arguments = json.dumps(observations(active_kind, start=0.5 if active_kind == "audio" else None))
            payload = {"id": "offline", "object": "chat.completion.chunk", "created": 1,
                       "model": body["model"], "choices": [{"index": 0, "finish_reason": "tool_calls",
                           "delta": {"role": "assistant", "tool_calls": [{"index": 0, "id": "test-output",
                               "type": "function", "function": {"name": analysis._OUTPUT_TOOL_NAME,
                                                                 "arguments": arguments}}]}}]}
            usage_chunk = {**payload, "choices": [], "usage": {"prompt_tokens": 121, "completion_tokens": 26,
                           "total_tokens": 147, "completion_tokens_details": {"reasoning_tokens": 11}}}
            events = [json.dumps(payload)]
            if active_kind != "audio":
                events.append(json.dumps(usage_chunk))
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                                  content="".join(f"data: {event}\n\n" for event in (*events, "[DONE]")))

        def invoke(node, model, prompt, attachments, is_live, mark_submitted):
            return analysis._native_invoke(node, model, prompt, attachments, is_live, mark_submitted,
                                           kind=active_kind, on_usage=receipts.append)

        client = AsyncOpenAI(base_url="https://analysis.invalid/v1", api_key="offline-only",
                             http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)
        model = OpenAIChatModel("gemini-4-argon", provider=OpenAIProvider(openai_client=client))
        with override_model(model), patch.object(model_invocation, "require_model_invocation_sync") as gate:
            for active_kind, source in (("image", self.image), ("video", self.video), ("audio", self.audio)):
                scope = {"start": 0.5, "end": 1.5} if active_kind == "audio" else {}
                result = analysis.analyze_reference(None, source=str(source), kind=active_kind,
                                                    cache_dir=self.root / "native-cache", invoke=invoke, **scope)
        self.assertEqual(gate.call_count, 3)
        for invocation in gate.call_args_list:
            self.assertEqual(invocation.args, (None, "gemini-4-argon"))
            self.assertEqual(invocation.kwargs, {"purpose": "HMB reference analysis"})
        self.assertEqual(result["range"], {"start": 0.5, "end": 1.5})
        self.assertEqual(len(requests), 3)
        for kind, request in zip(("image", "video", "audio"), requests):
            self.assertEqual(request["model"], "gemini-4-argon")
            tool, = request["tools"]
            function = tool["function"]
            self.assertEqual(function["name"], "hmb_reference_observations")
            self.assertTrue(function["strict"])
            self.assertEqual(function["parameters"]["required"], list(analysis.ANALYSIS_CATEGORIES[kind]))
            self.assertFalse(function["parameters"]["additionalProperties"])
            self.assertNotIn(request["tool_choice"], (None, "auto", "none"))
        observed = {"status": "reported", "input_tokens": 121, "output_tokens": 26, "total_tokens": 147,
                    "reasoning_tokens": 11}
        self.assertEqual(receipts, [observed, observed, {"status": "unreported"}])
        contents = [request["messages"][-1]["content"] for request in requests]
        visuals = [[part["image_url"]["url"] for part in content if part["type"] == "image_url"]
                   for content in contents[:2]]
        self.assertEqual(len(visuals[0]), 1)
        self.assertGreaterEqual(len(visuals[1]), 4)
        for url in visuals[0] + visuals[1]:
            self.assertTrue(base64.b64decode(url.split(",", 1)[1]).startswith(b"\x89PNG\r\n\x1a\n"))
        parts = contents[2]
        audio = next(part["input_audio"] for part in parts if part["type"] == "input_audio")
        self.assertEqual(audio["format"], "wav")
        wav = base64.b64decode(audio["data"])
        self.assertTrue(wav.startswith(b"RIFF"))
        self.assertEqual(int.from_bytes(wav[4:8], "little"), len(wav) - 8)
        self.assertNotIn(str(self.audio), str(parts))

    def test_concurrent_or_unconfirmed_call_does_not_submit_twice(self):
        entered, release = Event(), Event()

        def invoke(_node, _model, _prompt, _attachments, _is_live, mark_submitted):
            mark_submitted()
            entered.set()
            if not release.wait(12):
                raise RuntimeError("test did not release")
            return {"invalid": []}

        args = dict(source=str(self.image), kind="image", invoke=invoke, cache_dir=self.root / "concurrent-cache")
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(analysis.analyze_reference, None, **args)
            self.assertTrue(entered.wait(12))
            try:
                with self.assertRaises(analysis.AnalysisError) as busy:
                    analysis.analyze_reference(None, **args)
                self.assertEqual(busy.exception.code, "ANALYSIS_BUSY")
            finally:
                release.set()
            with self.assertRaises(analysis.AnalysisError) as failed:
                first.result(timeout=12)
            self.assertEqual(failed.exception.code, "ANALYSIS_INVALID_RESULT")
        with self.assertRaises(analysis.AnalysisError) as uncertain:
            analysis.analyze_reference(None, **args)
        self.assertEqual(uncertain.exception.code, "ANALYSIS_RESULT_UNCONFIRMED")

    def test_validation_reuses_agent_model_credentials_and_token_settings(self):
        from griptape_nodes_library.llm import runner
        from griptape_nodes_library.llm.model_config import cloud_model_config
        from griptape_nodes_library.utils import model_invocation

        config = cloud_model_config("gemini-2.5-pro")
        config.settings["max_tokens"] = 1234
        config.api_key = "fake-agent-key-for-test"
        cache_dir = self.root / "agent-settings-cache"
        run = AsyncMock(return_value=SimpleNamespace(output=observations("image")))
        with patch.object(model_invocation, "require_model_invocation_sync") as gate, \
                patch.object(runner, "build_agent") as build, patch.object(runner, "run_agent_async", run):
            first = analysis.analyze_reference(None, source=str(self.image), kind="image",
                                               model_config=config, cache_dir=cache_dir)
            self.assertTrue(analysis.analyze_reference(None, source=str(self.image), kind="image",
                                                       model_config=config, cache_dir=cache_dir)["cache_hit"])
            changed = config.model_copy(deep=True)
            changed.settings["max_tokens"] = 2345
            self.assertNotEqual(analysis.analyze_reference(None, source=str(self.image), kind="image",
                                                           model_config=changed, cache_dir=cache_dir)["cache_key"],
                                first["cache_key"])
            with self.assertRaises(analysis.AnalysisError) as unsupported:
                analysis.analyze_reference(None, source=str(self.image), kind="image",
                                           model_config=cloud_model_config("unsupported-text-model"), cache_dir=cache_dir)
            self.assertEqual(unsupported.exception.code, "ANALYSIS_MODEL_UNAVAILABLE")
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(config.settings["max_tokens"], 1234)
        self.assertIsNone(config.max_retries)
        for built, token_limit in zip(build.call_args_list, (1234, 2345), strict=True):
            resolved = built.args[0]
            self.assertEqual(resolved.model, config.model)
            self.assertEqual(resolved.api_key, config.api_key)
            self.assertEqual(resolved.settings["max_tokens"], token_limit)
            self.assertEqual(resolved.max_retries, 0)
        for entry in cache_dir.glob("*.json"):
            self.assertNotIn(config.api_key, entry.read_text("utf-8"))

    def test_selected_agent_audio_model_keeps_exact_settings_without_fallback(self):
        from griptape_nodes_library.llm import runner
        from griptape_nodes_library.llm.model_config import cloud_model_config
        from griptape_nodes_library.utils import model_invocation

        config = cloud_model_config("gemini-2.5-pro")
        config.settings["max_tokens"] = 1379
        expected_digest = analysis.analysis_model_settings_digest(config)
        run = AsyncMock(return_value=SimpleNamespace(output=observations("audio", start=0.1, end=0.2)))
        with patch.object(model_invocation, "require_model_invocation_sync"), \
                patch.object(runner, "build_agent") as build, patch.object(runner, "run_agent_async", run):
            result = analysis.analyze_reference(None, source=str(self.audio), kind="audio",
                model=config.model, model_config=config, cache_dir=self.root / "agent-audio-cache")
        self.assertEqual(result["model_settings_sha256"], expected_digest)
        self.assertEqual(build.call_args.args[0].model, config.model)
        self.assertEqual(build.call_args.args[0].settings["max_tokens"], 1379)
        self.assertEqual(config.settings["max_tokens"], 1379)

    def test_same_shot_agent_model_uses_active_and_saved_native_choices(self):
        import HMBAgentLibrary as agent_module
        from griptape_nodes_library.llm.model_config import ModelConfig, ModelProvider, cloud_model_config

        class RegisteredAgent(agent_module.HMBAgentLibrary):
            pass

        owner = object()
        agent = object.__new__(RegisteredAgent)
        active = cloud_model_config("gemini-2.5-pro")
        saved = cloud_model_config("gemini-2.5-flash")
        agent._hmb_shot_manager_mode = True
        agent._hmb_node_deleted = False
        agent._hmb_active_slot_key = agent._hmb_slot_key("channel", "shot")
        agent._hmb_shot_slots = {agent._hmb_slot_key("channel", "other"):
            {"values": {"agent": None, "model": saved.model, "model_provider": None}}}
        agent._native_parameter_value = lambda name, default=None: {
            "agent": None, "model": active.model, "model_provider": "griptape_cloud"}.get(name, default)
        agent._resolve_model_config = lambda model, provider: (
            active if model == active.model and provider == "griptape_cloud" else
            saved if model == saved.model and provider == "griptape_cloud" else None)
        agent._hmb_reference_analysis_owner = lambda **_scope: owner
        with patch("HMBAnalysisAgent._same_flow_nodes", return_value=("flow", [owner, agent])), \
                patch("HMBAnalysisAgent._registered_node_class", return_value=RegisteredAgent):
            selected = agent_module.get_same_shot_analysis_model(owner,
                channel_uuid="channel", shot_uuid="shot", kind="image")
            self.assertEqual(selected.model, active.model)
            selected = agent_module.get_same_shot_analysis_model(owner,
                channel_uuid="channel", shot_uuid="other", kind="audio")
            self.assertEqual(selected.model, saved.model)
            with patch("griptape_nodes.node_library.library_registry.get_declared_models",
                       return_value=[SimpleNamespace(model=SimpleNamespace(
                           provider_model_id=saved.model, display_name="Gemini 2.5 Flash"))]):
                self.assertEqual(agent_module.get_same_shot_analysis_model_label(
                    owner, channel_uuid="channel", shot_uuid="other"), "Gemini 2.5 Flash")
            unsupported = ModelConfig(provider=ModelProvider.OPENAI_COMPATIBLE,
                model="private-text-only", base_url="https://offline-fixture.invalid")
            agent._hmb_active_slot_key = agent._hmb_slot_key("channel", "shot")
            agent._resolve_model_config = lambda *_args: unsupported
            self.assertEqual(agent_module.get_same_shot_analysis_model_label(
                owner, channel_uuid="channel", shot_uuid="shot"), unsupported.model)
            with self.assertRaises(analysis.AnalysisError) as failure:
                agent_module.get_same_shot_analysis_model(owner,
                    channel_uuid="channel", shot_uuid="shot", kind="video")
            self.assertEqual(failure.exception.code, "ANALYSIS_AGENT_MODEL_UNSUPPORTED")

    def test_agent_public_analysis_preview_lists_names_without_changing_prompt(self):
        import HMBAgentLibrary as agent_module

        visible = ("HMB_GP_Production\n\nIMAGE SOURCE:\nNo image source assigned in HMBPromptLibrary.\n\n"
                   "VIDEO SOURCE:\nNo video source assigned in HMBPromptLibrary.\n")
        originals = [{"kind": "video", "shot_reference": "@video2", "name": "scene.mov",
                      "path": r"P:\projects\private\scene.mov"},
                     {"kind": "audio", "shot_reference": "@analysis_original_audio_1",
                      "name": r"C:\private\dialogue.wav", "path": r"C:\private\dialogue.wav"}]
        preview = agent_module._hmb_analysis_public_source_preview(visible, originals)
        self.assertIn("@video2 = scene.mov / Analysis source", preview)
        self.assertIn("@analysis_original_audio_1 = dialogue.wav / Analysis source", preview)
        self.assertNotIn("No video source assigned", preview)
        self.assertNotIn("P:\\projects", preview)
        self.assertNotIn("C:\\private", preview)
        self.assertEqual(agent_module._hmb_analysis_public_source_preview(visible, []), visible)
        self.assertIn("No video source assigned", visible)

    def test_invalid_scope_and_non_media_fail_before_invocation(self):
        def forbidden_invoke(*_args):
            self.fail("Invalid local media must not reach an analysis provider")
        with self.assertRaises(analysis.AnalysisError) as range_error:
            analysis.analyze_reference(None, source=str(self.video), kind="video", end=99, cache_dir=self.root / "invalid-cache", invoke=forbidden_invoke)
        self.assertEqual(range_error.exception.code, "ANALYSIS_INVALID_RANGE")
        disguised = self.root / "playlist.mov"
        disguised.write_text("ffconcat version 1.0\nfile fixture.mp4\n", encoding="ascii")
        with self.assertRaises(analysis.AnalysisError) as format_error:
            analysis.analyze_reference(None, source=str(disguised), kind="video", cache_dir=self.root / "invalid-cache", invoke=forbidden_invoke)
        self.assertEqual(format_error.exception.code, "ANALYSIS_SOURCE_FORMAT")


if __name__ == "__main__":
    unittest.main()
