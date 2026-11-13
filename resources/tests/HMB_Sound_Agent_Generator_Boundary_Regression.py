"""Offline exact-Shot Sound -> Generator and native Agent transport checks.

No provider, broker, real workflow, credential, source media, or policy DAT is
used. The installed native transport case is explicit SKIP without that SDK.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
sys.dont_write_bytecode = True
SDK_AVAILABLE = importlib.util.find_spec("griptape_nodes") is not None
import HMB_Seedance_Direct_Shot_Source_Regression as fixture
import _hmb_agent_media as media
import _hmb_sound as sound


class GeneratorSoundBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hmb-sound-boundary-")
        self.root = Path(self.temp.name) / "superwings12" / "Ai_Ct_audio"
        self.root.mkdir(parents=True)
        self.path = self.root / "dialogue.wav"
        self.path.write_bytes(b"offline immutable sound fixture; never decoded")
        self.snapshot = {"schema": sound.SCHEMA, "version": 1,
            "project_id": "superwings12", "project_root": str(self.root),
            "project_uid": sound.project_uid(self.root), "channel_uuid": fixture.CHANNEL,
            "revision": 1, "tracks": []}
        self.track = {"instance_id": "selected-dialogue", "source_uid": sound.source_uid(self.root, self.path.name),
            "relative_path": self.path.name, "path": str(self.path), "media_signature": sound.media_signature(self.path),
            "role": "Dialogue", "purpose": "both", "transcript": "안녕 {{KEEP}} 0 OFF",
            "target": "hero", "in_seconds": 0, "out_seconds": None, "start_seconds": 0,
            "gain_db": 0, "enabled": True, "loop": False, "lipsync": True, "duration_seconds": 2,
            "channel_uuid": fixture.CHANNEL, "shot_uuid": fixture.SHOT}
        self.snapshot["tracks"] = [deepcopy(self.track)]
        self.source = SimpleNamespace(name="Registered sound fixture",
            _hmb_sound_snapshot_for=lambda **_kw: deepcopy(self.snapshot))
        self.node = fixture.generator(fixture.image, fixture.picker)
        self.node._hmb_sound_port_registered = True
        original = self.node._exact_incoming_source
        self.node._exact_incoming_source = lambda port, output, required=True: (self.source
            if port == fixture.target.SHOT_SOUND_INPUT_PARAMETER else original(port, output, required=required))
        self.node._hmb_preflight_kind = lambda node: "HMBSoundLibrary" if node is self.source else ""
        self.params = fixture.valid_params(prompt="Keep authored visual prompt")
        self.params["model_id"] = fixture.target.SEEDANCE_2_5_MODEL_ID
        self.params["duration"] = 5
        self.params[fixture.target.TASK_PARAMETER] = fixture.target.TASK_REFERENCE_TO_VIDEO
        self.no_network = patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden"))
        self.no_network.start()

    def tearDown(self):
        self.no_network.stop()
        self.temp.cleanup()

    def resolve(self):
        return self.node._resolve_exact_shot_generation_inputs(deepcopy(self.params))

    def test_exact_reference_and_finishing_intent_preserve_eof_literal_and_authored_input(self):
        original = deepcopy(self.params)
        value = self.resolve()
        self.assertEqual(self.params, original)
        self.assertEqual(value["reference_audio"], [str(self.path.resolve())])
        self.assertIsNone(value["_hmb_sound_tracks"][0]["out_seconds"])
        self.assertEqual(value["_hmb_sound_tracks"][0]["transcript"], self.track["transcript"])
        self.assertEqual(value["_hmb_sound_provenance"]["audio_observation"], "not_performed")
        self.assertEqual(value["prompt"], original["prompt"])
        self.assertEqual(value["_hmb_sound_snapshot"]["tracks"][0]["purpose"], "both")

    def test_other_shot_and_other_flow_tracks_never_reach_reference_audio(self):
        self.snapshot["tracks"][0]["shot_uuid"] = "another-shot"
        self.assertEqual(self.resolve()["reference_audio"], [])
        self.snapshot["channel_uuid"] = "another-flow"
        self.snapshot["tracks"][0]["channel_uuid"] = "another-flow"
        with self.assertRaises(sound.SoundError):
            self.resolve()

    def test_changed_original_and_model_limit_fail_before_any_submission(self):
        self.path.write_bytes(b"changed original")
        with self.assertRaises(sound.SoundError):
            self.resolve()
        self.snapshot["tracks"][0]["media_signature"] = sound.media_signature(self.path)
        limit = fixture.target.MODEL_REFERENCE_LIMITS[self.params["model_id"]][2]
        self.snapshot["tracks"] = [{**self.snapshot["tracks"][0], "instance_id": f"copy-{i}"} for i in range(limit + 1)]
        with self.assertRaisesRegex(ValueError, "reference audio"):
            self.resolve()

    def test_mix_only_and_disabled_tracks_are_not_model_references(self):
        self.snapshot["tracks"][0]["purpose"] = "mix"
        value = self.resolve()
        self.assertEqual(value["reference_audio"], [])
        self.assertEqual(len(value["_hmb_sound_tracks"]), 1)
        self.snapshot["tracks"][0]["enabled"] = False
        self.assertEqual(self.resolve()["_hmb_sound_tracks"], [])

    def test_mixed_purpose_tokens_follow_actual_provider_reference_order(self):
        self.snapshot["tracks"] = [{**deepcopy(self.track), "instance_id": "music-mix", "role": "Music", "purpose": "mix"},
            {**deepcopy(self.track), "instance_id": "dialogue-reference", "role": "Dialogue", "purpose": "both"}]
        directions = sound.public_sound_directions(self.snapshot, channel_uuid=fixture.CHANNEL, shot_uuid=fixture.SHOT)
        self.assertEqual([row["audio"] for row in directions], ["@mix1", "@audio1"])
        resolved = self.resolve()
        self.assertEqual(resolved["reference_audio"], [str(self.path.resolve())])
        self.assertEqual([row["instance_id"] for row in resolved["_hmb_sound_tracks"]], ["music-mix", "dialogue-reference"])

    def test_real_broker_payload_maps_audio_reference_without_sending_finishing_contract(self):
        value = self.resolve()
        prepared = []
        def prepare(kind, source):
            prepared.append((kind, source))
            return "https://offline.invalid/" + kind + ".wav" if kind == "audio" else "https://offline.invalid/" + kind
        self.node._prepare_media_reference = prepare
        value["reference_images"] = ["https://offline.invalid/image.png"]
        value["video_references"] = ["https://offline.invalid/video.mp4"]
        with patch.object(fixture.target, "File", lambda text: SimpleNamespace(resolve=lambda: text)):
            payload = self.node._build_broker_payload(value)
        self.assertEqual(payload["audio_urls"], ["https://offline.invalid/audio.wav"])
        self.assertIn(("audio", str(self.path.resolve())), prepared)
        self.assertFalse(any(key.startswith("_hmb_sound") for key in payload))
        self.assertNotIn("gain_db", payload)
        self.assertNotIn("start_seconds", payload)
        self.snapshot["tracks"][0]["purpose"] = "mix"
        prepared.clear()
        without_reference_audio = self.resolve()
        without_reference_audio.update(reference_images=value["reference_images"], video_references=value["video_references"])
        payload = self.node._build_broker_payload(without_reference_audio)
        self.assertNotIn("audio_urls", payload)
        self.assertFalse(any(kind == "audio" for kind, _source in prepared))

    def test_unwired_ui_json_is_not_sound_authority_and_noaudio_stays_unchanged(self):
        original = self.node._exact_incoming_source
        self.node._exact_incoming_source = lambda port, output, required=True: (None
            if port == fixture.target.SHOT_SOUND_INPUT_PARAMETER else original(port, output, required=required))
        self.node.get_parameter_value = lambda name: deepcopy(self.snapshot)
        self.assertEqual(self.resolve()["reference_audio"], [])
        self.assertNotIn("_hmb_sound_snapshot", self.resolve())

    def test_only_merges_blank_scope_after_manual_audio_without_mutating_authored_list(self):
        self.node._hmb_shot_channel_subscription = lambda: {"enabled": False}
        self.snapshot["channel_uuid"] = ""
        self.snapshot["tracks"][0].update(channel_uuid="", shot_uuid="")
        self.params["reference_audio"] = ["manual.wav"]
        value = self.resolve()
        self.assertEqual(value["reference_audio"], ["manual.wav", str(self.path.resolve())])
        self.assertEqual(self.params["reference_audio"], ["manual.wav"])
        self.params[fixture.target.TASK_PARAMETER] = fixture.target.TASK_TEXT_ONLY
        with self.assertRaisesRegex(ValueError, "does not support reference audio"):
            self.resolve()

    def test_only_manual_prefix_uses_sound_namespace_binding_without_rewriting_authored_body(self):
        self.node._hmb_shot_channel_subscription = lambda: {"enabled": False}
        self.snapshot["channel_uuid"] = ""
        self.snapshot["tracks"] = [{**deepcopy(self.track), "instance_id": "mix-first", "purpose": "mix", "channel_uuid": "", "shot_uuid": ""},
            {**deepcopy(self.track), "instance_id": "speech-reference", "purpose": "both", "channel_uuid": "", "shot_uuid": ""}]
        manual = "https://offline.invalid/manual.wav"
        authored = "  Preserve manual @audio1 exactly; use @sound1 dialogue {{KEEP}} 0 OFF.\n "
        self.params.update(prompt=authored, reference_audio=[manual], reference_images=["https://offline.invalid/image.png"])
        original = deepcopy(self.params)
        directions = sound.public_sound_directions(self.snapshot)
        self.assertEqual([row["audio"] for row in directions], ["@mix1", "@sound1"])
        value = self.resolve()
        self.assertEqual(value["reference_audio"], [manual, str(self.path.resolve())])
        self.assertEqual(value["_hmb_sound_reference_bindings"], [{"sound": "@sound1", "provider_audio": "@audio2"}])
        with patch.object(fixture.target, "File", lambda text: SimpleNamespace(resolve=lambda: text)):
            payload = self.node._build_broker_payload(value)
        self.assertTrue(payload["prompt"].startswith(authored))
        self.assertIn('"sound":"@sound1","provider_audio":"@audio2"', payload["prompt"])
        self.assertEqual(payload["audio_urls"][0], manual)
        self.assertEqual(base64.b64decode(payload["audio_urls"][1].split(",", 1)[1]), self.path.read_bytes())
        self.assertNotIn(str(self.root), payload["prompt"])
        self.assertNotIn("media_signature", payload["prompt"])
        self.assertEqual(self.params, original)
        self.snapshot["tracks"][1]["purpose"] = "mix"
        without_reference = self.resolve()
        without_reference["reference_images"] = value["reference_images"]
        self.assertNotIn("_hmb_sound_reference_bindings", without_reference)
        self.assertEqual(self.node._build_broker_payload(without_reference)["prompt"],
            self.node._compose_finish_look_prompt(authored, ""))

    def test_source_without_registered_sound_identity_is_rejected(self):
        self.node._hmb_preflight_kind = lambda node: ""
        with self.assertRaisesRegex(RuntimeError, "registered HMB Sound"):
            self.resolve()

    def install_prompt_authority(self, effective):
        agent = SimpleNamespace(name="Exact retained Agent", _hmb_sound_snapshot_for=lambda **_kw: deepcopy(effective))
        self.node._manual_agent_prompt_source = lambda: agent
        self.node._hmb_preflight_kind = lambda node: ("HMBSoundLibrary" if node is self.source else "HMBAgentLibrary" if node is agent else "")
        return agent

    def test_only_exact_prompt_reference_enables_broker_audio(self):
        self.params["generate_audio"] = False
        self.node._prepare_media_reference = lambda kind, source: f"https://offline.invalid/{kind}"
        def build_payload(value):
            value = dict(value, reference_images=["https://offline.invalid/image.png"], video_references=[])
            with patch.object(fixture.target, "File", lambda text: SimpleNamespace(resolve=lambda: text)):
                return self.node._build_broker_payload(value)

        direct = self.resolve()
        self.assertTrue(direct["reference_audio"])
        self.assertFalse(build_payload(direct)["generate_audio"])

        effective = deepcopy(self.snapshot)
        self.install_prompt_authority(effective)
        for model in fixture.target.BROKER_SUPPORTED_MODEL_IDS:
            with self.subTest(model=model):
                self.params["model_id"] = model
                self.params["resolution"] = "720p"
                resolved = self.resolve()
                self.assertTrue(build_payload(resolved)["generate_audio"])
        self.assertFalse(self.params["generate_audio"])

        for controls in ({"enabled": False}, {"purpose": "mix"}):
            effective["tracks"] = [dict(self.track, **controls)]
            self.assertFalse(self.resolve()["generate_audio"])
        self.params["generate_audio"] = True
        self.assertTrue(self.resolve()["generate_audio"])

    def test_prompt_disable_overrides_direct_sound_without_erasing_original_selection(self):
        effective = deepcopy(self.snapshot)
        effective["tracks"][0]["enabled"] = False
        self.install_prompt_authority(effective)
        value = self.resolve()
        self.assertEqual(value["reference_audio"], [])
        self.assertEqual(value["_hmb_sound_tracks"], [])
        self.assertFalse(value["_hmb_sound_snapshot"]["tracks"][0]["enabled"])
        self.assertTrue(self.snapshot["tracks"][0]["enabled"])
        self.assertEqual(value["_hmb_sound_provenance"]["kind"], "exact_prompt_document")

    def test_prompt_mix_and_exact_timing_override_direct_sound_and_enter_completed_capture(self):
        effective = deepcopy(self.snapshot)
        effective["tracks"][0].update(purpose="mix", start_seconds=.75, in_seconds=.25, out_seconds=1.5, gain_db=-3, lipsync=False)
        self.install_prompt_authority(effective)
        value = self.resolve()
        self.assertEqual(value["reference_audio"], [])
        for key in ("purpose", "start_seconds", "in_seconds", "out_seconds", "gain_db", "lipsync"):
            self.assertEqual(value["_hmb_sound_tracks"][0][key], effective["tracks"][0][key])
        self.assertEqual(value["_hmb_sound_tracks"][0]["path"], str(self.path.resolve()))
        self.assertEqual(self.snapshot["tracks"][0]["purpose"], "both")
        origin = {"channel_uuid": fixture.CHANNEL, "shot_uuid": fixture.SHOT, "number": 2,
            "name": "Effective Prompt Sound", "source_node_instance_id": "66666666-6666-4666-8666-666666666666"}
        self.node.parameter_values, self.node.parameter_output_values = {}, {}
        self.node._hmb_publish_generated_video_source = lambda: True
        self.node._hmb_generated_video_source_snapshot = lambda: deepcopy(getattr(self.node, "_hmb_generated_video_source", {}))
        self.node._hmb_pending_sound = {"snapshot": deepcopy(value["_hmb_sound_snapshot"]),
            "tracks": deepcopy(value["_hmb_sound_tracks"]), "provenance": deepcopy(value["_hmb_sound_provenance"]), "origin": origin}
        with patch.object(fixture.target._shot_routing, "reconcile_completed_video_routes", lambda *_a, **_k: None):
            self.node._record_completed_video_source(origin, "job-" + "d" * 32,
                SimpleNamespace(resolve=lambda: str(self.root / "effective-completed.mp4")))
        captured = self.node._hmb_sound_finishing_snapshot()
        self.assertEqual(captured["snapshot"], value["_hmb_sound_snapshot"])
        self.assertEqual(captured["tracks"][0]["purpose"], "mix")
        self.assertEqual(captured["tracks"][0]["start_seconds"], .75)

    def test_raw_managed_record_cannot_replace_generator_owned_agent_ticket(self):
        effective = deepcopy(self.snapshot)
        agent = self.install_prompt_authority(effective)
        self.node._hmb_managed_agent_request = {"source": agent, "record": {
            "result": {"run_id": "arbitrary-user-shaped-run"}, "audio_sources": deepcopy(effective)}}
        with self.assertRaisesRegex(RuntimeError, "result ticket"):
            self.resolve()

    def test_prompt_cannot_replace_base_original_or_edit_another_shot(self):
        effective = deepcopy(self.snapshot)
        effective["tracks"][0]["media_signature"] = "f" * 64
        self.install_prompt_authority(effective)
        with self.assertRaisesRegex(RuntimeError, "different original"):
            self.resolve()

    def test_sound_contract_is_published_only_with_matching_completed_render_origin(self):
        origin = {"channel_uuid": fixture.CHANNEL, "shot_uuid": fixture.SHOT, "number": 2,
            "name": "Exact completed sound Shot", "source_node_instance_id": "66666666-6666-4666-8666-666666666666"}
        self.node.parameter_values = {}
        self.node.parameter_output_values = {}
        self.node._hmb_publish_generated_video_source = lambda: True
        self.node._hmb_generated_video_source_snapshot = lambda: deepcopy(getattr(self.node, "_hmb_generated_video_source", {}))
        normalized_snapshot = sound.normalize_sound_snapshot(self.snapshot)
        verified_tracks = sound.resolve_sound_tracks(normalized_snapshot, channel_uuid=fixture.CHANNEL, shot_uuid=fixture.SHOT, project_id="superwings12")
        self.node._hmb_pending_sound = {"snapshot": normalized_snapshot, "tracks": verified_tracks,
            "provenance": {"audio_observation": "not_performed"}, "origin": deepcopy(origin)}
        saved = SimpleNamespace(resolve=lambda: str(self.root / "synthetic-completed.mp4"))
        with patch.object(fixture.target._shot_routing, "reconcile_completed_video_routes", lambda *_a, **_k: None):
            self.assertEqual(self.node._hmb_sound_finishing_snapshot(), {})
            self.assertTrue(self.node._record_completed_video_source(origin, "job-" + "a" * 32, saved))
            original = self.node._hmb_sound_finishing_snapshot()
            self.node._hmb_pending_sound["tracks"][0]["gain_db"] = 6
            self.node._hmb_pending_sound["snapshot"]["tracks"][0]["gain_db"] = 6
            self.assertEqual(self.node._hmb_sound_finishing_snapshot(), original, "pending new request must not replace old video's sound")
            self.node._record_completed_video_source(origin, "job-" + "b" * 32, saved)
            self.assertEqual(self.node._hmb_sound_finishing_snapshot()["tracks"][0]["gain_db"], 6)
            saved_store = json.loads(json.dumps(self.node.parameter_values[fixture.target.GENERATION_SOUND_STORE_PARAMETER]))
            saved_source = deepcopy(self.node._hmb_generated_video_source)
            reopened = fixture.generator(fixture.image, fixture.picker)
            reopened.parameter_values = {fixture.target.GENERATION_SOUND_STORE_PARAMETER: saved_store}
            reopened._hmb_generated_video_source_snapshot = lambda: deepcopy(saved_source)
            self.assertEqual(reopened._hmb_sound_finishing_snapshot()["tracks"][0]["gain_db"], 6)
            saved_source["generation_id"] = "job-" + "e" * 32
            self.assertEqual(reopened._hmb_sound_finishing_snapshot(), {})
            returned = self.node._hmb_sound_finishing_snapshot()
            returned["tracks"][0]["gain_db"] = 12
            self.assertEqual(self.node._hmb_sound_finishing_snapshot()["tracks"][0]["gain_db"], 6)
            self.node._record_completed_video_source({**origin, "shot_uuid": "77777777-7777-4777-8777-777777777777"}, "job-" + "c" * 32, saved)
            self.assertEqual(self.node._hmb_sound_finishing_snapshot(), {})
            for index in range(10):
                self.node._record_completed_video_source(origin, "job-" + str(index) * 32, saved)
            entries = self.node.parameter_values[fixture.target.GENERATION_SOUND_STORE_PARAMETER]["entries"]
            self.assertEqual(len(entries), 8)
            self.assertNotIn("job-" + "a" * 32, entries)
            self.assertEqual(self.node._hmb_sound_finishing_snapshot()["generation_id"], "job-" + "9" * 32)


class LocalPreparation(unittest.TestCase):
    def test_warmup_only_discovers_decoder_for_nonempty_frozen_media(self):
        snapshot = {"schema": "hmb-agent-reference-media", "version": 1,
            "images": [{"source": "unused-selected-path"}], "videos": []}
        with patch.object(media, "_RUNTIME_WARMED", False), patch.object(media, "_binaries", return_value=(None, None)) as discover, \
                patch.object(media, "_decode", side_effect=AssertionError("warmup must not decode")), \
                patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            self.assertEqual(media.prewarm_local_runtime({})["status"], "not_needed")
            self.assertEqual(media.prewarm_local_runtime(snapshot, is_live=lambda: False)["status"], "not_needed")
            self.assertEqual(media.prewarm_local_runtime(snapshot)["status"], "ready")
            self.assertEqual(media.prewarm_local_runtime(snapshot)["status"], "already_ready")
            discover.assert_called_once()

    def test_original_wav_and_mp3_bytes_are_serialized_as_audio_data_references(self):
        with tempfile.TemporaryDirectory(prefix="hmb-sound-serialization-") as directory:
            wav = Path(directory) / "original.wav"
            with wave.open(str(wav), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"\0\0" * 800)
            paths = [wav]
            ffmpeg, _probe = media._binaries()
            if ffmpeg is not None:
                mp3 = wav.with_suffix(".mp3")
                subprocess.run([str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
                    "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "64k", str(mp3)], check=True, capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                paths.append(mp3)
            with patch.object(fixture.target, "File", lambda text: SimpleNamespace(resolve=lambda: text)), \
                    patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
                for path in paths:
                    original = path.read_bytes()
                    reference = fixture.target.HMBSeedanceGeneration._prepare_media_reference("audio", path)
                    self.assertTrue(reference.startswith("data:audio/"))
                    self.assertEqual(base64.b64decode(reference.split(",", 1)[1]), original)
                    self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(paths), 2, "Both WAV and MP3 serialization need an installed local FFmpeg")


class NativeSoundIntent(unittest.TestCase):
    def test_actual_installed_driver_gets_authored_intent_without_audio_observation_claim(self):
        if not SDK_AVAILABLE:
            self.skipTest("installed SDK required")
        try:
            import HMB_Agent_Current_Standard_Transport_Regression as transport
        except (SystemExit, ImportError) as exc:
            self.skipTest(f"installed SDK required: {type(exc).__name__}")
        case = transport.NativeTransport()
        case.setUp()
        try:
            case.node._hmb_runtime_prompt += "\nAUTHORED SOUND: 안녕 {{KEEP}} 0 OFF"
            case.source._hmb_agent_sound_snapshot = lambda _machine: {"tracks": [{"transcript": "안녕 {{KEEP}} 0 OFF"}]}
            case.source._hmb_agent_reference_media = lambda _machine: {}
            result = case.run_native()
            self.assertEqual(result.output, transport.FINAL)
            request = str(case.captured)
            # Keep failed checks from echoing the private bundled policy and
            # authored media text in the captured native request.
            self.assertTrue("AUTHORED SOUND" in request, "Authored sound contract missing")
            self.assertTrue(
                "This authored sound snapshot alone does not verify speech, phonemes or waveforms." in request,
                "Authored sound must not claim speech, phoneme or waveform verification",
            )
            self.assertTrue("input_audio" not in request, "Intent-only fixture must not attach audio")
            self.assertTrue("execution_stage" not in request, "Execution stage must remain local")
            self.assertTrue("stages_seconds" not in request, "Timing diagnostics must remain local")
            timing = case.node._hmb_timing_snapshot()
            self.assertIn("media_prepare", timing["stages_seconds"])
            self.assertGreaterEqual(timing["total_seconds"], 0)
        finally:
            case.tearDown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
