"""Bounded metadata fixtures and real local clips; no app/provider/user writes."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(os.environ.get("HMB_MEDIA_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))
import _hmb_video_tools as target
import _hmb_color_lut as color


def video_line(index=0, size="96x64", rate="24 fps, 24 tbr", suffix=""):
    return (f"  Stream #0:{index}[0x1](und): Video: h264 (High) (avc1 / 0x31637661), "
            f"yuv420p(tv, bt709), {size} [SAR 1:1 DAR 3:2], {rate}, 12288 tbn{suffix}")


class MetadataProbeRegression(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hmb-metadata-regression-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "원본 영상.mp4"
        self.source.write_bytes(b"metadata fixture; decoder is mocked")

    def fallback(self, header):
        completed = subprocess.CompletedProcess([], 1, "", header)
        with mock.patch.object(target, "_find_ffprobe", return_value=""), \
                mock.patch.object(target, "_find_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(target.subprocess, "run", return_value=completed) as run:
            result = target.probe_video(self.source)
        return result, run.call_args.kwargs

    def native(self, streams, duration="1"):
        completed = subprocess.CompletedProcess([], 0, json.dumps({"streams": streams, "format": {"duration": duration}}), "")
        with mock.patch.object(target, "_find_ffprobe", return_value="ffprobe"), \
                mock.patch.object(target, "_find_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(target.subprocess, "run", return_value=completed) as run:
            result = target.probe_video(self.source)
        return result, run.call_args.kwargs

    def test_fallback_uses_positive_geometry_not_hex_and_supports_tiny_video(self):
        result, _ = self.fallback("Duration: 00:00:01.00\n" + video_line(size="8x6"))
        self.assertEqual((result["width"], result["height"]), (8, 6))

    def test_fallback_prefers_reported_fps_over_nominal_clock(self):
        result, _ = self.fallback("Duration: 00:00:01.00\n" + video_line(rate="23.33 fps, 30 tbr"))
        self.assertEqual(result["frame_rate"], 23.33)

    def test_fallback_ignores_cover_art_and_keeps_selected_stream_metadata(self):
        header = ("Duration: 00:00:01.00\n"
                  "  Stream #0:0: Video: mjpeg, yuvj420p(pc, bt709), 320x320, 90 fps, 90 tbr (attached pic)\n"
                  "  Stream #0:1: Audio: aac, 48000 Hz, stereo, fltp\n" + video_line(index=2, rate="23.33 fps, 30 tbr"))
        result, _ = self.fallback(header)
        self.assertEqual((result["width"], result["height"], result["frame_rate"], result["video_codec"]), (96, 64, 23.33, "h264"))
        self.assertEqual(result["video_stream_index"], 2)
        self.assertEqual((result["audio_codec"], result["audio_channels"], result["audio_sample_rate"]), ("aac", 2, 48000))

    def test_both_probe_paths_decode_process_text_as_utf8(self):
        _, fallback = self.fallback("Duration: 00:00:01.00\n" + video_line())
        _, native = self.native([dict(codec_type="video", codec_name="h264", width=96, height=64, avg_frame_rate="24/1")])
        for options in (fallback, native):
            self.assertEqual(options.get("encoding"), "utf-8")
            self.assertEqual(options.get("errors"), "replace")

    def test_native_ignores_attached_picture_and_uses_valid_fallback_rate(self):
        result, _ = self.native([
            dict(index=0, codec_type="video", codec_name="mjpeg", width=320, height=320, avg_frame_rate="90/1", disposition={"attached_pic": 1}),
            dict(index=1, codec_type="audio", codec_name="aac", sample_rate="48000", channels=2),
            dict(index=2, codec_type="video", codec_name="h264", width=96, height=64, avg_frame_rate="0/0", r_frame_rate="24000/1001")])
        self.assertEqual((result["width"], result["height"]), (96, 64))
        self.assertAlmostEqual(result["frame_rate"], 24000 / 1001)
        self.assertEqual(result["video_stream_index"], 2)

    def test_cover_only_source_fails_before_editing(self):
        with self.assertRaises(target.VideoToolError):
            self.native([dict(index=0, codec_type="video", codec_name="mjpeg", width=320, height=320, disposition={"attached_pic": 1})])
        with self.assertRaises(target.VideoToolError):
            self.fallback("Stream #0:0: Video: mjpeg, yuv420p, 320x320, 24 fps (attached pic)")

    def test_nonfinite_metadata_never_becomes_usable_geometry_rate_or_duration(self):
        with self.assertRaises(target.VideoToolError):
            self.native([dict(codec_type="video", width=0, height=64, avg_frame_rate="24/1")])
        result, _ = self.native([dict(codec_type="video", width=96, height=64, avg_frame_rate="nan/1", r_frame_rate="25/1")], duration="nan")
        self.assertEqual(result["frame_rate"], 25)
        self.assertEqual(result["duration"], 0)

    def test_color_lut_fallback_ignores_cover_without_resizing_movie(self):
        header = ("Duration: 00:00:01.00\n"
                  "Stream #0:0: Video: mjpeg, yuvj420p(pc, bt709), 320x320, 90 fps (attached pic)\n" + video_line(index=2))
        with mock.patch.object(color, "_find_ffprobe", return_value=""), \
                mock.patch.object(color, "_find_ffmpeg", return_value="ffmpeg"), \
                mock.patch.object(color.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", header)):
            result = color.probe_source(self.source)
        self.assertEqual((result["width"], result["height"], result["video_stream_index"]), (96, 64, 2))


class VideoPublishRegression(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hmb-video-publish-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.mp4"; self.source.write_bytes(b"original fixture")
        self.output = self.root / "crop.mp4"
        self.settings = target.default_picker_tools_state()["crop"]
        self.settings.update(input=str(self.source), output_path=str(self.output), custom_width=64, custom_height=48)
        self.probe = dict(width=96, height=64, duration=1, has_audio=True, video_codec="h264", frame_rate=24, video_stream_index=2)
        self.service = target.VideoMediaService()

    def run_crop(self, candidate):
        def probe(path):
            if Path(path) == self.source: return copy.deepcopy(self.probe)
            if isinstance(candidate, BaseException): raise candidate
            return copy.deepcopy(candidate)
        def encode(command, *_args):
            Path(command[-1]).write_bytes(b"unverified output")
            return ""
        with mock.patch.object(target, "probe_video", side_effect=probe), \
                mock.patch.object(self.service, "_run", side_effect=encode), \
                mock.patch.object(target, "_find_ffmpeg", return_value="ffmpeg"):
            return self.service.crop(self.settings)

    def test_bad_crop_probe_does_not_publish_unusable_final_file(self):
        with self.assertRaises(target.VideoToolError):
            self.run_crop(target.VideoToolError("synthetic corrupt encoded output"))
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".*.part*")))

    def test_crop_geometry_and_audio_loss_fail_before_publication(self):
        good = dict(self.probe, width=64, height=48)
        for candidate in (dict(good, width=62), dict(good, has_audio=False), dict(good, video_codec="mjpeg")):
            with self.subTest(candidate=candidate), self.assertRaises(target.VideoToolError):
                self.run_crop(candidate)
            self.assertFalse(self.output.exists())

    def test_exclusive_publish_preserves_concurrent_destination(self):
        stage = self.root / ".stage.mp4"; stage.write_bytes(b"new render")
        self.output.write_bytes(b"concurrent user output")
        with self.assertRaises(target.VideoToolError):
            target._publish_video_exclusive(stage, self.output)
        self.assertEqual(self.output.read_bytes(), b"concurrent user output")

    def test_selected_video_track_is_used_by_crop_and_concat_commands(self):
        crop = target.build_crop_ffmpeg_command("ffmpeg", "a.mov", "out.mp4", (64, 48, 0, 0), has_audio=False, video_stream_index=2)
        self.assertEqual(crop[crop.index("-map") + 1], "0:2")
        settings = target.default_picker_tools_state()["concatenate"]
        filtered = target.build_filter_concat_ffmpeg_command("ffmpeg", ["a.mov", "b.mov"], "out.mp4", settings,
            [dict(self.probe), dict(self.probe, video_stream_index=3)])
        graph = filtered[filtered.index("-filter_complex") + 1]
        self.assertIn("[0:2]trim=", graph); self.assertIn("[1:3]trim=", graph)
        self.assertEqual(filtered[filtered.index("-fps_mode") + 1], "cfr")
        copied = target.build_concat_ffmpeg_command("ffmpeg", "inputs.txt", "out.mp4", settings, video_stream_index=2)
        self.assertEqual(copied[copied.index("-map") + 1], "0:2")


class RealMediaProbeRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="hmb-media-real-")
        cls.root = Path(cls.temporary.name)
        cls.ffmpeg = target._find_ffmpeg()
        cls.ffprobe = target._find_ffprobe(cls.ffmpeg)
        cls.source = cls.root / "테스트 원본.mp4"
        cls.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=24:duration=0.5", "-f", "lavfi", "-i",
            "sine=sample_rate=48000:duration=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.source))

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    @classmethod
    def run_ffmpeg(cls, *args):
        return subprocess.run([cls.ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n", *args],
            check=True, capture_output=True, timeout=90)

    def test_real_no_ffprobe_tiny_movie_and_utf8_filename(self):
        tiny = self.root / "tiny_8x6.mp4"
        self.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=8x6:rate=24:duration=0.25", "-c:v", "libx264", str(tiny))
        with mock.patch.object(target, "_find_ffprobe", return_value=""):
            result = target.probe_video(tiny)
            korean = target.probe_video(self.source)
        self.assertEqual((result["width"], result["height"]), (8, 6))
        self.assertEqual((korean["width"], korean["height"], korean["frame_rate"]), (96, 64, 24))

    def test_real_variable_frame_rate_fallback_matches_measured_rate(self):
        variable = self.root / "vfr.mp4"
        self.run_ffmpeg("-i", str(self.source), "-an", "-vf", "setpts=(N+floor(N/2))/(24*TB)", "-fps_mode", "vfr", "-c:v", "libx264", str(variable))
        completed = subprocess.run([self.ffmpeg, "-hide_banner", "-i", str(variable)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        line = next(line for line in completed.stderr.splitlines() if "Video:" in line)
        import re
        reported = re.search(r"([0-9.]+) fps", line)
        self.assertIsNotNone(reported)
        with mock.patch.object(target, "_find_ffprobe", return_value=""):
            result = target.probe_video(variable)
        self.assertEqual(result["frame_rate"], float(reported.group(1)))

    def test_real_nonfirst_video_track_is_cropped_instead_of_first(self):
        dual = self.root / "dual.mp4"
        self.run_ffmpeg("-f", "lavfi", "-i", "color=red:size=80x80:rate=24:duration=0.5", "-i", str(self.source),
            "-map", "0:v:0", "-map", "1:v:0", "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", str(dual))
        original = target.probe_video
        def selected(path):
            value = original(path)
            if Path(path) == dual:
                value.update(width=96, height=64, video_stream_index=1)
            return value
        settings = target.default_picker_tools_state()["crop"]
        settings.update(input=str(dual), output_path=str(self.root / "selected.mp4"), custom_width=96, custom_height=64)
        with mock.patch.object(target, "probe_video", side_effect=selected):
            result = target.VideoMediaService().crop(settings)
        self.assertEqual((result["width"], result["height"]), (96, 64))

    def test_real_no_ffprobe_concat_has_measured_not_only_nominal_cadence(self):
        settings = target.default_picker_tools_state()["concatenate"]
        settings.update(inputs=[str(self.source), str(self.source)], output_path=str(self.root / "fallback-concat.mp4"))
        with mock.patch.object(target, "_find_ffprobe", return_value=""):
            result = target.VideoMediaService().concatenate(settings)
            actual = target.probe_video(result["path"])
        self.assertAlmostEqual(actual["frame_rate"], 24, delta=.01)


if __name__ == "__main__": unittest.main(verbosity=2)
