"""Keep cover artwork out of native Agent video-frame attachments."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(os.environ.get("HMB_MEDIA_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))
import _hmb_agent_media as media
from _hmb_video_tools import _find_ffmpeg, _find_ffprobe
from PIL import Image


class AgentMovieStreamRegression(unittest.TestCase):
    def test_video_info_uses_movie_not_cover_start_or_duration(self):
        body = {"streams": [
            dict(codec_type="video", start_time="0", duration=".04", disposition={"attached_pic": 1}),
            dict(codec_type="audio", duration="1"),
            dict(codec_type="video", start_time="5", duration="1", disposition={"attached_pic": 0})],
            "format": {"duration": "6", "start_time": "0"}}
        with mock.patch.object(media, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(body).encode(), b"")) as run:
            result = media._video_info(Path("movie.mp4"), Path("ffprobe"), time.monotonic() + 5)
        self.assertEqual(result, {"duration": 1, "start_pts": 5})
        self.assertIn("stream_disposition=attached_pic", run.call_args.args[0][run.call_args.args[0].index("-show_entries") + 1])

    def test_cover_only_file_does_not_report_audio_duration_as_movie(self):
        body = {"streams": [dict(codec_type="video", disposition={"attached_pic": 1}), dict(codec_type="audio")],
                "format": {"duration": "10", "start_time": "0"}}
        with mock.patch.object(media, "_run", return_value=subprocess.CompletedProcess([], 0, json.dumps(body).encode(), b"")):
            self.assertEqual(media._video_info(Path("cover.mp4"), Path("ffprobe"), time.monotonic() + 5), {})

    def test_video_frame_decoder_excludes_artwork_without_changing_image_decode(self):
        buf = io.BytesIO(); Image.new("RGB", (2, 2), "red").save(buf, "PNG")
        result = subprocess.CompletedProcess([], 0, buf.getvalue(), b"n: 0 pts: 0 pts_time:0")
        with mock.patch.object(media, "_run", return_value=result) as run:
            media._decode(Path("video.mp4"), ("stream-filter", 1), 0.0, Path("ffmpeg"), time.monotonic() + 5)
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("-map") + 1], "0:V:0")
            media._decode(Path("image.png"), ("image-filter", 1), None, Path("ffmpeg"), time.monotonic() + 5)
            self.assertNotIn("-map", run.call_args.args[0])

    def test_real_video_with_large_cover_yields_movie_pixels(self):
        ffmpeg = Path(_find_ffmpeg()); probe_text = _find_ffprobe(str(ffmpeg))
        self.assertTrue(probe_text, "Independent local MP4 metadata verification requires ffprobe")
        with tempfile.TemporaryDirectory(prefix="hmb-agent-movie-stream-") as directory:
            root = Path(directory); cover = root / "cover.jpg"; output = root / "movie.mp4"
            Image.new("RGB", (320, 320), "blue").save(cover)
            subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=red:size=96x64:rate=12:duration=0.5",
                "-i", str(cover), "-map", "0:v:0", "-map", "1:v:0", "-c:v:0", "libx264", "-c:v:1", "copy",
                "-disposition:v:0", "default", "-disposition:v:1", "attached_pic", str(output)], check=True, capture_output=True, timeout=45)
            meta = json.loads(subprocess.run([probe_text, "-v", "error", "-show_streams", "-of", "json", str(output)],
                capture_output=True, text=True, encoding="utf-8", check=True, timeout=30).stdout)
            self.assertTrue(any(s.get("disposition", {}).get("attached_pic") for s in meta["streams"]))
            info = media._video_info(output, Path(probe_text), time.monotonic() + 10)
            self.assertAlmostEqual(info["duration"], .5, delta=.01)
            png, width, height, pts = media._decode(output, (str(output), output.stat().st_size), 0.0, ffmpeg, time.monotonic() + 10)
            self.assertEqual((width, height), (96, 64))
            with Image.open(io.BytesIO(png)) as image:
                red, _, blue = image.convert("RGB").getpixel((width // 2, height // 2))
                self.assertGreater(red, blue + 100)


if __name__ == "__main__": unittest.main(verbosity=2)
