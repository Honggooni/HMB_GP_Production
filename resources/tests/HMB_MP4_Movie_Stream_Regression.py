"""Reject audio/cover-art MP4s as generated movies with either local verifier."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get("HMB_MEDIA_TEST_ROOT", str(Path(__file__).resolve().parents[2])))
sys.path.insert(0, str(ROOT))

from PIL import Image
from _hmb_mp4_verify import MP4DecodeVerifier, validate_decodable_mp4_file
from _hmb_video_tools import _find_ffmpeg, _find_ffprobe


class MP4MovieStreamRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = Path(_find_ffmpeg())
        probe = _find_ffprobe(str(cls.ffmpeg))
        if not probe:
            raise RuntimeError("Independent local MP4 metadata verification requires ffprobe")
        cls.ffprobe = Path(probe)
        cls.temporary = tempfile.TemporaryDirectory(prefix="hmb-mp4-movie-stream-")
        root = Path(cls.temporary.name)
        cover = root / "cover.jpg"
        Image.new("RGB", (96, 64), "blue").save(cover)
        cls.cover_only = root / "audio-with-cover.mp4"
        cls.movie = root / "movie-with-cover.mp4"
        subprocess.run([
            str(cls.ffmpeg), "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-i", str(cover), "-map", "0:a:0", "-map", "1:v:0", "-t", "0.5",
            "-c:a", "aac", "-c:v", "copy", "-disposition:v:0", "attached_pic", str(cls.cover_only),
        ], capture_output=True, check=True, timeout=45)
        subprocess.run([
            str(cls.ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=red:size=96x64:rate=12:duration=0.5",
            "-i", str(cover), "-map", "0:v:0", "-map", "1:v:0", "-c:v:0", "libx264",
            "-c:v:1", "copy", "-disposition:v:0", "default", "-disposition:v:1", "attached_pic", str(cls.movie),
        ], capture_output=True, check=True, timeout=45)
        meta = json.loads(subprocess.run([
            str(cls.ffprobe), "-v", "error", "-show_streams", "-of", "json", str(cls.cover_only),
        ], capture_output=True, check=True, text=True, encoding="utf-8", timeout=20).stdout)
        video = [stream for stream in meta["streams"] if stream.get("codec_type") == "video"]
        if len(video) != 1 or not video[0].get("disposition", {}).get("attached_pic"):
            raise AssertionError("Fixture must contain audio and attached cover, no actual movie")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_ffprobe_rejects_cover_only(self):
        with self.assertRaises(RuntimeError):
            validate_decodable_mp4_file(self.cover_only, MP4DecodeVerifier("ffprobe", self.ffprobe))

    def test_ffmpeg_rejects_cover_only(self):
        with self.assertRaises(RuntimeError):
            validate_decodable_mp4_file(self.cover_only, MP4DecodeVerifier("ffmpeg", self.ffmpeg))

    def test_ffprobe_accepts_movie_with_cover(self):
        validate_decodable_mp4_file(self.movie, MP4DecodeVerifier("ffprobe", self.ffprobe))

    def test_ffmpeg_accepts_movie_with_cover(self):
        validate_decodable_mp4_file(self.movie, MP4DecodeVerifier("ffmpeg", self.ffmpeg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
