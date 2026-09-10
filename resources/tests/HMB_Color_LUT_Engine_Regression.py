from __future__ import annotations

"""Pure LUT checks and real tiny-video encodes; no installed-library mutation."""

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _hmb_color_lut as target


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ColorLUTRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace = tempfile.TemporaryDirectory(prefix="hmb_lut_regression_")
        cls.root = Path(cls.workspace.name)
        cls.ffmpeg = target._find_ffmpeg()
        cls.source = cls.root / "original 한글 ' quoted.mp4"
        cls.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=12:duration=0.5", "-f", "lavfi", "-i",
                       "sine=frequency=440:sample_rate=48000:duration=0.5", "-c:v", "libx264", "-crf", "12",
                       "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                       "-color_range", "tv", "-c:a", "aac", "-shortest", str(cls.source))
        cls.original_hash = digest(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.workspace.cleanup()

    @classmethod
    def run_ffmpeg(cls, *arguments: str, cwd: Path | None = None) -> bytes:
        completed = subprocess.run([cls.ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n", *arguments],
                                   cwd=cwd, capture_output=True, timeout=90)
        if completed.returncode:
            raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
        return completed.stdout

    def test_settings_and_identity(self) -> None:
        self.assertEqual(target.default_settings(), dict(enabled=False, precision_version=2, exposure=0, temperature=0, contrast=0,
                                                        saturation=0, shadows=0, highlights=0))
        for enabled in (False, True):
            for color in ((0, 0, 0), (1, 1, 1), (0.08, 0.5, 0.9)):
                for actual, expected in zip(target.transform_rgb(*color, {"enabled": enabled}), color):
                    self.assertAlmostEqual(actual, expected, places=14)
        normalized = target.normalize_settings({"enabled": "true", "exposure": 90, "contrast": -99,
                                               "temperature": -1.9, "saturation": float("inf"), "highlights": None})
        self.assertFalse(normalized["enabled"])
        self.assertEqual((normalized["exposure"], normalized["contrast"], normalized["temperature"], normalized["saturation"]),
                         (3, -3, -1, 0))
        self.assertEqual(target.transform_rgb(0.2, 0.4, 0.6, {"enabled": False, "contrast": 3}), (0.2, 0.4, 0.6))
        self.assertGreater(target.transform_rgb(0.3, 0.3, 0.3, {"enabled": True, "exposure": 1})[0], 0.3)
        warm = target.transform_rgb(0.3, 0.3, 0.3, {"enabled": True, "temperature": 1})
        self.assertGreater(warm[0], warm[2])
        with self.assertRaises(target.ColorLUTError):
            target.transform_rgb(float("nan"), 0, 0, {})

    def test_cube_is_deterministic_and_red_fastest(self) -> None:
        first, second = self.root / "identity.cube", self.root / "identity2.cube"
        target.write_cube(first, {})
        target.write_cube(second, {})
        self.assertEqual(first.read_bytes(), second.read_bytes())
        entries = [tuple(map(float, line.split())) for line in first.read_text().splitlines()
                   if line and (line[0].isdigit() or line[0] == "-")]
        self.assertEqual(len(entries), 33**3)
        self.assertEqual(entries[0], (0, 0, 0))
        self.assertEqual(entries[1], (1 / 32, 0, 0))
        self.assertEqual(entries[33], (0, 1 / 32, 0))
        self.assertEqual(entries[-1], (1, 1, 1))
        self.assertEqual(target._cube_component(.0009765625), .000976563)
        before = digest(first)
        with self.assertRaises(target.ColorLUTError):
            target.write_cube(first, {"enabled": True, "exposure": 3})
        self.assertEqual(digest(first), before)

    def test_twelve_steps_and_legacy_presets(self) -> None:
        for key in target.STEP_KEYS:
            colors = set()
            for step in range(-12, 13):
                settings = {**target.default_settings(), "enabled": True, key: step / 4}
                normalized = target.normalize_settings(settings)
                self.assertEqual(normalized, settings)
                self.assertEqual(target.normalize_settings(normalized), normalized)
                color = target.transform_rgb(.2, .4, .6, settings)
                colors.add(color)
                if step % 4 == 0:
                    legacy = {"enabled": True, key: step // 4}
                    self.assertEqual(target.transform_rgb(.2, .4, .6, legacy), color)
            self.assertEqual(len(colors), 25, key)
        self.assertEqual(target.normalize_settings({"precision_version":2, "exposure":-.125})["exposure"], 0)
        self.assertEqual(target.normalize_settings({"precision_version":2, "exposure":.125})["exposure"], .25)

    def test_real_export_modes_preserve_source_and_geometry(self) -> None:
        settings = {**target.default_settings(), "enabled": True, "exposure": .25, "temperature": .75, "contrast": 1.25, "shadows": -1.75, "highlights": 2.75}
        for codec, extension in target.CODEC_EXTENSIONS.items():
            with self.subTest(codec=codec):
                output = self.root / ("graded_" + codec + extension)
                progress = []
                result = target.export_video(self.source, output, settings, codec, progress=progress.append)
                self.assertEqual((result["width"], result["height"]), (96, 64))
                self.assertAlmostEqual(result["frame_rate"], 12, places=4)
                self.assertTrue(result["has_audio"])
                self.assertEqual(result["audio_mode"], "copy")
                self.assertEqual(result["encoding_lossless"], codec == "ffv1")
                self.assertEqual(progress[-1], 1.0)
                self.assertEqual(digest(self.source), self.original_hash)
                self.assertFalse(list(self.root.glob(".*.part*")))
                details = target._color_details(output)
                self.assertEqual(details["color_primaries"], "bt709")
                self.assertEqual(details["color_transfer"], "iec61966-2-1" if codec == "ffv1" else "bt709")
                before = digest(output)
                with self.assertRaises(target.ColorLUTError):
                    target.export_video(self.source, output, {}, codec)
                self.assertEqual(digest(output), before)

    def test_ffv1_preserves_encoder_input_pixels(self) -> None:
        settings = {**target.default_settings(), "enabled": True, "exposure": .25, "saturation": -1.75, "shadows": 2.25}
        output = self.root / "exact_rgb.mkv"
        target.export_video(self.source, output, settings, "ffv1")
        # Independent raw encoding branch evaluates the same filter once without
        # a video encoder; decoded FFV1 must match every 16-bit channel exactly.
        with tempfile.TemporaryDirectory(prefix="hmb_lut_pixels_") as temporary:
            work = Path(temporary)
            target.write_cube(work / "grade.cube", settings)
            expected = self.run_ffmpeg("-i", str(self.source), "-an", "-vf",
                                       target.build_color_filter(target.probe_source(self.source), "ffv1"),
                                       "-pix_fmt", "gbrp16le", "-f", "rawvideo", "pipe:1", cwd=work)
        actual = self.run_ffmpeg("-i", str(output), "-an", "-pix_fmt", "gbrp16le", "-f", "rawvideo", "pipe:1")
        self.assertEqual(len(actual), 6 * 96 * 64 * 3 * 2)
        self.assertEqual(actual, expected)

    def test_cancellation_cleans_only_own_staging(self) -> None:
        event = threading.Event()
        event.set()
        output = self.root / "cancelled.mp4"
        with self.assertRaisesRegex(target.ColorLUTError, "cancelled"):
            target.export_video(self.source, output, {}, cancel_event=event)
        self.assertFalse(output.exists())
        sentinel = self.root / "unrelated.part.mp4"
        sentinel.write_bytes(b"keep")
        event.clear()
        # Cancel after FFmpeg has actually started; _notify(0) before startup
        # deliberately does not cancel until the polling progress callback.
        calls = []
        def cancel_when_running(value: float) -> None:
            calls.append(value)
            if len(calls) > 1:
                event.set()
        with self.assertRaisesRegex(target.ColorLUTError, "cancelled"):
            target.export_video(self.source, output, {"enabled": True, "exposure": 1}, progress=cancel_when_running,
                                cancel_event=event)
        self.assertFalse(output.exists())
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertEqual(digest(self.source), self.original_hash)
        self.assertEqual(list(self.root.glob(".*.part*")), [])

    def test_hdr_and_unsafe_source_are_rejected(self) -> None:
        basic = {"pixel_format": "yuv420p10le"}
        with self.assertRaisesRegex(target.ColorLUTError, "HDR_UNSUPPORTED"):
            target._color_contract(basic, {"color_transfer": "smpte2084", "color_primaries": "bt2020"})
        with self.assertRaisesRegex(target.ColorLUTError, "HDR_UNSUPPORTED"):
            target._color_contract(basic, {"color_transfer": "arib-std-b67"})
        with self.assertRaisesRegex(target.ColorLUTError, "COLORSPACE_UNSUPPORTED"):
            target._color_contract(basic, {"color_transfer": "bt709", "color_primaries": "bt2020"})
        with self.assertRaisesRegex(target.ColorLUTError, "ALPHA_UNSUPPORTED"):
            target._color_contract({"pixel_format": "rgba"}, {})
        with self.assertRaises(target.ColorLUTError):
            target.export_video(self.source, self.source, {})
        with self.assertRaises(target.ColorLUTError):
            target.resolve_source("https://example.com/video.mp4")

    def test_ffmpeg_fallback_preserves_hdr_evidence(self) -> None:
        with mock.patch.object(target, "_find_ffprobe", return_value=""):
            source = target.probe_source(self.source)
        self.assertEqual(source["color_primaries"], "bt709")
        self.assertEqual(source["color_range"], "tv")
        self.assertEqual(source["audio_streams"][0]["codec_name"], "aac")

    def test_nonzero_variable_frame_timestamps_are_preserved(self) -> None:
        ffprobe = target._find_ffprobe(self.ffmpeg)
        if not ffprobe:
            self.skipTest("Per-frame timestamp inspection requires ffprobe.")
        source = self.root / "variable_pts.mkv"
        self.run_ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=12:duration=0.5", "-vf",
                        "setpts=5/TB+(N+floor(N/2))/(12*TB)", "-fps_mode", "passthrough", "-c:v", "ffv1", str(source))
        def frame_times(path: Path) -> list[float]:
            result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_frames",
                                     "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path)],
                                    capture_output=True, encoding="utf-8", check=True, timeout=30)
            return [float(frame["best_effort_timestamp_time"]) for frame in json.loads(result.stdout)["frames"]]
        expected = frame_times(source)
        self.assertEqual(len(expected), 6)
        self.assertGreater(expected[0], 4.9)
        for codec, extension in target.CODEC_EXTENSIONS.items():
            with self.subTest(codec=codec):
                output = self.root / ("variable_" + codec + extension)
                target.export_video(source, output, {}, codec)
                actual = frame_times(output)
                self.assertEqual(len(actual), len(expected))
                for received, original in zip(actual, expected):
                    self.assertAlmostEqual(received, original, delta=0.0011)

    def test_pcm_audio_is_copied_or_explicitly_encoded(self) -> None:
        source = self.root / "pcm_source.mkv"
        self.run_ffmpeg("-i", str(self.source), "-c:v", "copy", "-c:a", "pcm_s24le", str(source))
        for codec, extension in target.CODEC_EXTENSIONS.items():
            with self.subTest(codec=codec):
                result = target.export_video(source, self.root / ("pcm_" + codec + extension), {}, codec)
                self.assertEqual(result["audio_mode"], "aac_320k" if codec == "hevc10" else "copy")
                self.assertEqual(result["audio_codec"], "aac" if codec == "hevc10" else "pcm_s24le")
                self.assertEqual(result["audio_sample_rate"], 48000)

    def test_late_output_collision_does_not_overwrite(self) -> None:
        output = self.root / "late_collision.mp4"
        calls = []
        def concurrent_writer(value: float) -> None:
            calls.append(value)
            if len(calls) == 2:
                output.write_bytes(b"someone else's new output")
        with self.assertRaisesRegex(target.ColorLUTError, "already exists"):
            target.export_video(self.source, output, {}, progress=concurrent_writer)
        self.assertEqual(output.read_bytes(), b"someone else's new output")
        self.assertEqual(list(self.root.glob(".*.part*")), [])

    def test_browser_and_python_cube_values_match(self) -> None:
        node = shutil.which("node")
        widget = Path(__file__).resolve().parents[2] / "widgets" / "HMBColorLUTLibraryWidget.js"
        if not node or not widget.is_file():
            self.skipTest("Browser cross-language parity needs Node and the widget source.")
        cases = [{}, {"enabled": True}, {"enabled": True, "temperature": -1.9, "contrast": 1.9},
                 {"enabled": True, "exposure": -3, "temperature": 2, "contrast": -1, "saturation": 3, "shadows": -2, "highlights": 1},
                 {"enabled": True, "exposure": 2, "temperature": -3, "contrast": 3, "saturation": -2, "shadows": 1, "highlights": -3}]
        cases.extend({**target.default_settings(), "enabled":True, key:step/4}
                     for key in target.STEP_KEYS for step in range(-12, 13))
        cases.extend({**target.default_settings(), "enabled":True, "exposure":value, "shadows":-value}
                     for value in (.125, -.125, 1.9, -1.9))
        script = """import {createHash} from 'node:crypto';
const t=await import(process.argv[1]);
const cases=JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(s=>({settings:t.hmbColorLUTSettings(s),
hash:createHash('sha256').update(Buffer.from(t.hmbColorLUTCube(s).buffer)).digest('hex')}))));"""
        completed = subprocess.run([node, "--input-type=module", "-e", script, widget.as_uri(), json.dumps(cases)],
                                   capture_output=True, encoding="utf-8", timeout=30, check=True)
        browser = json.loads(completed.stdout)
        for settings, actual in zip(cases, browser):
            normalized = target.normalize_settings(settings)
            self.assertEqual(actual["settings"], normalized)
            content = bytearray()
            for blue in range(33):
                for green in range(33):
                    for red in range(33):
                        rgb = target._transform(red / 32, green / 32, blue / 32, normalized)
                        content.extend(struct.pack("<fff", *(target._cube_component(channel) for channel in rgb)))
            if hashlib.sha256(content).hexdigest() != actual["hash"]:
                dump = "const t=await import(process.argv[1]); console.log(Buffer.from(t.hmbColorLUTCube(JSON.parse(process.argv[2])).buffer).toString('base64'));"
                import base64
                decoded = subprocess.run([node, "--input-type=module", "-e", dump, widget.as_uri(), json.dumps(settings)],
                                         capture_output=True, encoding="utf-8", timeout=30, check=True)
                preview_bytes = base64.b64decode(decoded.stdout)
                pairs = list(zip(struct.iter_unpack("<f", content), struct.iter_unpack("<f", preview_bytes)))
                mismatches = [(index, a[0], b[0]) for index, (a, b) in enumerate(pairs) if a != b]
                self.fail(f"{settings}: mismatches={len(mismatches)}; max_abs={max(abs(a-b) for _,a,b in mismatches)}; first={mismatches[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
