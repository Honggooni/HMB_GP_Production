from __future__ import annotations

"""Real local FFmpeg audio/grade checks and offline sound-authority lifecycle checks."""

import array
import copy
import hashlib
import importlib.util
import math
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_color_lut as engine
import HMBColorLUTLibrary as node_module


class SoundLUTEngineRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="hmb_sound_lut_")
        cls.root = Path(cls.workspace.name).resolve()
        cls.ffmpeg = engine._find_ffmpeg()
        cls.source = cls.root / "original 영상.mov"
        cls.silent = cls.root / "silent.mov"
        cls.sound = cls.root / "sound 원본.wav"
        cls.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24:duration=1.25", "-f", "lavfi", "-i",
                       "sine=frequency=440:sample_rate=48000:duration=1.25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", str(cls.source))
        cls.run_ffmpeg("-i", str(cls.source), "-map", "0:v:0", "-c:v", "copy", "-an", str(cls.silent))
        cls.run_ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=0.4", "-c:a", "pcm_s16le", str(cls.sound))
        cls.original_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (cls.source, cls.silent, cls.sound)}

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    @classmethod
    def run_ffmpeg(cls, *arguments):
        result = subprocess.run([cls.ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n", *arguments],
                                capture_output=True, timeout=90)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout

    def track(self, **changes):
        return {"source_uid": "tone-880", "path": str(self.sound), "role": "SFX", "purpose": "mix", "transcript": "",
                "in_seconds": .1, "out_seconds": .3, "start_seconds": .4, "gain_db": 0,
                "enabled": True, "loop": False, **changes}

    def export(self, name, *, source=None, settings=None, **kwargs):
        return engine.export_video(source or self.source, self.root / name, settings or {}, codec="prores", **kwargs)

    def rms(self, path, start, end):
        raw = self.run_ffmpeg("-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1")
        samples = array.array("f", raw)[round(start * 48000):round(end * 48000)]
        return math.sqrt(sum(value * value for value in samples) / len(samples))

    def test_trim_start_gain_and_loop_preserve_complete_video(self):
        muted = self.export("muted.mov", sound_tracks=[self.track()], original_audio="mute")
        looped = self.export("looped.mov", sound_tracks=[self.track(loop=True)], original_audio="mute")
        quiet = self.export("quiet.mov", sound_tracks=[self.track(gain_db=-12)], original_audio="mute")
        for result in (muted, looped, quiet):
            self.assertEqual((result["width"], result["height"]), (96, 64))
            self.assertAlmostEqual(result["duration"], 1.25, places=5)
            self.assertEqual(result["video_codec"], "h264")
            self.assertEqual(result["video_mode"], "copy")
            self.assertEqual(result["audio_codec"], "aac")
            self.assertLess(self.rms(result["path"], .06, .18), .001)
            self.assertGreater(self.rms(result["path"], .46, .54), .01)
            original_packets = self.run_ffmpeg("-i", str(self.source), "-map", "0:v:0", "-c:v", "copy", "-f", "data", "pipe:1")
            output_packets = self.run_ffmpeg("-i", result["path"], "-map", "0:v:0", "-c:v", "copy", "-f", "data", "pipe:1")
            self.assertEqual(original_packets, output_packets, "Audio-only output must retain every original video packet.")
        self.assertLess(self.rms(muted["path"], 1.0, 1.1), .001)
        self.assertGreater(self.rms(looped["path"], 1.0, 1.1), .03)
        ratio = self.rms(quiet["path"], .46, .54) / self.rms(muted["path"], .46, .54)
        self.assertAlmostEqual(ratio, 10 ** (-12 / 20), delta=.035)

    def test_preserve_source_audio_and_mix_silent_video(self):
        preserved = self.export("preserved.mov", sound_tracks=[self.track()], original_audio="preserve")
        self.assertGreater(self.rms(preserved["path"], .06, .18), .04)
        self.assertGreater(self.rms(preserved["path"], 1.0, 1.1), .04)
        supplied = self.export("supplied.mov", source=self.silent, sound_tracks=[self.track()], original_audio="preserve")
        self.assertTrue(supplied["has_audio"])
        self.assertLess(self.rms(supplied["path"], .06, .18), .001)

    def test_grade_and_sound_use_selected_codec_and_preserve_frame_count(self):
        result = self.export("graded.mov", settings={"enabled": True, "exposure": 1}, sound_tracks=[self.track()])
        self.assertEqual(result["video_codec"], "prores")
        self.assertEqual(result["video_mode"], "encode")
        self.assertEqual(engine.probe_source(result["path"])["frame_count"], engine.probe_source(self.source)["frame_count"])
        self.assertAlmostEqual(result["duration"], 1.25, places=5)

    def test_mute_without_sounds_never_creates_silent_stream(self):
        result = self.export("no-audio.mov", sound_tracks=[], original_audio="mute")
        self.assertFalse(result["has_audio"])
        self.assertEqual(result["audio_mode"], "none")

    def test_nonzero_video_clock_and_odd_geometry_are_preserved_for_audio_only(self):
        shifted = self.root / "shifted.mov"
        self.run_ffmpeg("-itsoffset", "2", "-i", str(self.silent), "-map", "0:v:0", "-copyts", "-c:v", "copy", str(shifted))
        result = self.export("shifted-mix.mov", source=shifted, sound_tracks=[self.track()], original_audio="mute")
        source_probe, output_probe = engine.probe_source(shifted), engine.probe_source(result["path"])
        self.assertAlmostEqual(float(source_probe["start_time"]), 2, places=5)
        self.assertAlmostEqual(float(output_probe["start_time"]), 2, places=5)
        self.assertAlmostEqual(output_probe["duration"], source_probe["duration"], places=5)
        odd = self.root / "odd.mov"
        self.run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=97x65:rate=24:duration=1.25", "-c:v", "libx264", "-pix_fmt", "yuv444p", str(odd))
        result = self.export("odd-mix.mov", source=odd, sound_tracks=[self.track()])
        self.assertEqual((result["width"], result["height"]), (97, 65))
        self.assertEqual(result["video_mode"], "copy")

    def test_ffv1_mix_reads_matroska_stream_duration_without_losing_nonzero_clock(self):
        for offset in (0, 2):
            source = self.source
            if offset:
                source = self.root / "ffv1-shifted-source.mov"
                self.run_ffmpeg("-itsoffset", str(offset), "-i", str(self.source), "-copyts", "-c", "copy", str(source))
            destination = self.root / f"ffv1-mix-{offset}.mkv"
            result = engine.export_video(source, destination, {}, codec="ffv1", sound_tracks=[self.track()], original_audio="mute")
            self.assertEqual(result["video_codec"], "ffv1")
            self.assertEqual(result["audio_codec"], "aac")
            self.assertAlmostEqual(result["duration"], 1.25, places=3)
            self.assertAlmostEqual(float(engine.probe_source(destination)["start_time"]), offset, places=3)
            self.assertGreater(self.rms(destination, .46, .54), .03)

    def test_invalid_timing_cancel_collision_preserve_originals(self):
        for index, change in enumerate(({"in_seconds": .3, "out_seconds": .1}, {"out_seconds": .9},
                                        {"start_seconds": 2}, {"gain_db": float("nan")})):
            destination = self.root / f"invalid-{index}.mov"
            with self.assertRaises(engine.ColorLUTError):
                engine.export_video(self.source, destination, {}, sound_tracks=[self.track(**change)])
            self.assertFalse(destination.exists())
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(engine.ColorLUTError):
            self.export("cancelled.mov", sound_tracks=[self.track()], cancel_event=cancelled)
        self.assertFalse((self.root / "cancelled.mov").exists())
        collision = self.root / "keep.mov"
        collision.write_bytes(b"keep original destination")
        with self.assertRaises(engine.ColorLUTError):
            self.export(collision.name, sound_tracks=[self.track()])
        self.assertEqual(collision.read_bytes(), b"keep original destination")
        for path, expected in self.original_hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_mutated_sound_is_not_published(self):
        changing = self.root / "changing.wav"
        changing.write_bytes(self.sound.read_bytes())
        original_run = engine._run_export
        def run_and_change(*args, **kwargs):
            result = original_run(*args, **kwargs)
            changing.write_bytes(changing.read_bytes() + b"changed")
            return result
        with mock.patch.object(engine, "_run_export", side_effect=run_and_change), self.assertRaises(engine.ColorLUTError):
            self.export("changed-sound.mov", sound_tracks=[self.track(path=str(changing))])
        self.assertFalse((self.root / "changed-sound.mov").exists())


_fixture_spec = importlib.util.spec_from_file_location("hmb_lut_node_fixture", ROOT / "resources/tests/HMB_Color_LUT_Node_Regression.py")
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)


class SoundLUTNodeRegression(unittest.TestCase):
    def setUp(self):
        self.fixture = _fixture_module.ColorLUTNodeRegression()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.node = self.fixture.node

    def test_audio_settings_follow_shot_and_survive_reload(self):
        self.fixture.select(_fixture_module.SHOT_A)
        self.fixture.apply(audio_mix={"enabled": True, "original_audio": "mute", "source": "current"})
        self.fixture.select(_fixture_module.SHOT_B)
        self.assertEqual(self.node._hmb_color_lut_state["audio_mix"], {"enabled": False, "original_audio": "preserve", "source": "current"})
        self.fixture.select(_fixture_module.SHOT_A)
        self.assertEqual(self.node._hmb_color_lut_state["audio_mix"], {"enabled": True, "original_audio": "mute", "source": "current"})
        saved = copy.deepcopy(self.node._hmb_color_lut_state)
        self.node._apply_ui(saved, initial_setup=True)
        self.assertEqual(self.node._hmb_color_lut_state["audio_mix"], saved["audio_mix"])

    def test_browser_cannot_supply_sound_authority_and_connection_is_required(self):
        self.fixture.apply(sound={"connected": True, "revision": "forged"}, _sound_snapshot={"tracks": [{"path": "wrong"}]})
        self.assertFalse(self.node._hmb_color_lut_state["sound"]["connected"])
        self.fixture.apply(audio_mix={"enabled": True})
        self.fixture.load(shot={"channel_uuid": "", "shot_uuid": ""})
        with mock.patch.object(self.node, "_capture_sound_snapshot", side_effect=ValueError("Sound connection missing")), mock.patch.object(node_module, "export_video") as export:
            self.fixture.export()
            export.assert_not_called()
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "error")

    def test_sound_change_invalidates_export_upload_stamp(self):
        self.fixture.apply(audio_mix={"enabled": True})
        before = self.node._export_operation_stamp(self.node._hmb_color_lut_state)
        self.node._receive_sound({"revision": 1, "tracks": [{"source_uid": "first"}]})
        after = self.node._export_operation_stamp(self.node._hmb_color_lut_state)
        self.assertNotEqual(before, after)
        self.fixture.apply(audio_mix={"enabled": False})
        disabled = self.node._export_operation_stamp(self.node._hmb_color_lut_state)
        self.node._receive_sound({"revision": 2, "tracks": []})
        self.assertEqual(disabled, self.node._export_operation_stamp(self.node._hmb_color_lut_state))

    def test_reference_only_tracks_never_enter_final_mix(self):
        self.fixture.select()
        self.fixture.load()
        snapshot = {"revision": 1, "tracks": []}
        self.fixture.apply(audio_mix={"enabled": True, "original_audio": "preserve"})
        self.node._receive_sound(snapshot)
        resolved = [{"source_uid": "reference", "purpose": "reference"}, {"source_uid": "mix", "purpose": "mix"}]
        helper = types.SimpleNamespace(resolve_sound_tracks=mock.Mock(return_value=resolved))
        with mock.patch.dict(sys.modules, {"_hmb_sound": helper}), mock.patch.object(self.node, "_capture_sound_snapshot", return_value=snapshot), \
             mock.patch.object(node_module, "export_video", side_effect=self.fixture.successful_export) as export:
            self.fixture.export()
        self.assertEqual(export.call_args.kwargs["sound_tracks"], [resolved[1]])
        self.assertEqual(export.call_args.kwargs["original_audio"], "preserve")
        self.assertEqual(helper.resolve_sound_tracks.call_args.kwargs["shot_uuid"], _fixture_module.SHOT_A["shot_uuid"])

    def test_sound_capture_requires_registered_correct_source(self):
        import _hmb_shot_routing as routing
        snapshot = {"schema": "fixture", "revision": 1, "tracks": []}
        class HMBSoundLibrary:
            name = "sound-node"
            metadata = {"library": "HMB_GP_Production", "node_type": "HMBSoundLibrary"}
            def _hmb_sound_snapshot_for(self, **kwargs):
                return copy.deepcopy(snapshot)
        source = HMBSoundLibrary()
        self.node._receive_sound(snapshot)
        edge = types.SimpleNamespace(target_parameter_name=node_module.SOUND_IN, source_parameter_name="SOUND_OUT", source_node_name="sound-node")
        with mock.patch.dict(sys.modules, {"_hmb_sound": types.SimpleNamespace(normalize_sound_snapshot=copy.deepcopy)}), \
             mock.patch("inspect.getfile", return_value=str(ROOT / "HMBSoundLibrary.py")), \
             mock.patch.object(routing, "_same_flow_nodes", return_value=("flow", [self.node, source])), \
             mock.patch.object(routing, "_incoming_connections", return_value=[edge]):
            self.assertEqual(self.node._capture_sound_snapshot(self.node._hmb_color_lut_state), snapshot)
            edge.source_parameter_name = "untrusted"
            with self.assertRaises(ValueError):
                self.node._capture_sound_snapshot(self.node._hmb_color_lut_state)

    def test_current_prompt_edits_and_rendered_plan_are_distinct_exact_contracts(self):
        import _hmb_sound as sound_helper
        shot=copy.deepcopy(_fixture_module.SHOT_A)
        original={"instance_id":"audio-one","source_uid":"original","path":"C:/original.wav","media_signature":"a"*64,
                  "channel_uuid":shot["channel_uuid"],"shot_uuid":shot["shot_uuid"],"enabled":True,"purpose":"both",
                  "in_seconds":0,"out_seconds":None,"start_seconds":0}
        base={"schema":"fixture","project_id":"showA","channel_uuid":shot["channel_uuid"],"tracks":[original]}
        current=copy.deepcopy(base);current["tracks"][0].update(enabled=False,purpose="mix",in_seconds=.1,out_seconds=.4,start_seconds=.6)
        rendered=copy.deepcopy(base);rendered["tracks"][0].update(purpose="reference",start_seconds=.2)
        source_record={"path":"C:/completed.mov","completed":True,"channel_uuid":shot["channel_uuid"],"shot_uuid":shot["shot_uuid"],
                       "generation_id":"completed-job","result_revision":"revision-one","source_node_instance_id":"generator-one"}
        HMBSoundLibrary=type("HMBSoundLibrary",(),{"name":"actual-sound","metadata":{"library":"HMB_GP_Production","node_type":"HMBSoundLibrary"},
            "_hmb_sound_snapshot_for":lambda self,**kwargs:copy.deepcopy(base)})
        sound=HMBSoundLibrary()
        HMBPromptLibrary=type("HMBPromptLibrary",(),{"metadata":{"library":"HMB_GP_Production","node_type":"HMBPromptLibrary"},
            "_registered_sound_source":lambda self:sound,"_hmb_sound_snapshot_for":lambda self,**kwargs:copy.deepcopy(current)})
        captured={"snapshot":rendered,"generation_id":"completed-job","origin":shot}
        HMBSeedanceGeneration=type("HMBSeedanceGeneration",(),{"name":"actual-generator","metadata":{"library":"HMB_GP_Production","node_type":"HMBSeedanceGeneration"},
            "_hmb_generated_video_source_snapshot":lambda self:copy.deepcopy(source_record),"_hmb_sound_finishing_snapshot":lambda self:copy.deepcopy(captured)})
        generator=HMBSeedanceGeneration();prompt=HMBPromptLibrary()
        state=copy.deepcopy(self.node._hmb_color_lut_state);state.update(shot=shot,source=source_record,audio_mix={"enabled":True,"source":"current"})
        nodes=[self.node,sound,prompt,generator]
        with mock.patch.object(sound_helper,"normalize_sound_snapshot",side_effect=copy.deepcopy), \
             mock.patch("inspect.getfile",side_effect=lambda kind:str(ROOT/(kind.__name__+".py"))), \
             mock.patch.object(__import__("_hmb_shot_routing"),"_incoming_connections",return_value=[types.SimpleNamespace(
                 target_parameter_name=node_module.SOURCE,source_parameter_name="HMB_GENERATED_VIDEO_SOURCE",source_node_name=generator.name)]):
            selected=self.node._current_shot_sound_contract(state,nodes,sound)
            self.assertEqual(selected["tracks"][0],current["tracks"][0],"Prompt enabled/purpose/trim/start must stay authored.")
            selected=self.node._bound_sound_contract(state,nodes,sound)
            self.assertEqual(selected["tracks"][0],rendered["tracks"][0],"Rendered selection must use that completed job, not today's edits.")
            captured.clear()
            with self.assertRaisesRegex(ValueError,"기록"):self.node._bound_sound_contract(state,nodes,sound)
            captured.update(snapshot=rendered,generation_id="wrong-job",origin=shot)
            with self.assertRaises(ValueError):self.node._bound_sound_contract(state,nodes,sound)

    def test_prompt_disabled_audio_keeps_video_export_and_changed_contract_blocks_reuse(self):
        self.fixture.select();self.fixture.load();self.fixture.apply(audio_mix={"enabled":True,"source":"current"})
        snapshot={"tracks":[{"enabled":False,"purpose":"mix","start_seconds":.4}]}
        helper=types.SimpleNamespace(resolve_sound_tracks=mock.Mock(return_value=[]))
        with mock.patch.dict(sys.modules,{"_hmb_sound":helper}),mock.patch.object(self.node,"_capture_sound_snapshot",return_value=snapshot), \
             mock.patch.object(node_module,"export_video",side_effect=self.fixture.successful_export) as export:
            self.fixture.export()
        self.assertEqual(export.call_args.kwargs["sound_tracks"],[])
        self.assertEqual(self.node._hmb_color_lut_state["result"]["sound_contract_sha256"],node_module._digest(snapshot))
        proof={"schema":"hmb-color-lut-local-export-v1","path":"C:/finished.mov","sound_contract_sha256":node_module._digest(snapshot)}
        state=copy.deepcopy(self.node._hmb_color_lut_state)
        state["result"]={"path":proof["path"],"web_export_proof":node_module._digest(proof)}
        state["_sound_snapshot"]={"tracks":[{"enabled":True,"purpose":"mix","start_seconds":.8}]}
        with mock.patch.object(node_module,"_read_upload_receipt",return_value=proof),self.assertRaisesRegex(ValueError,"Sound direction changed"):
            self.node._export_upload_proof(state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
