"""Offline media and upload recorder for Generator submission tests."""
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
import subprocess
import wave

from PIL import Image


@lru_cache(maxsize=1)
def movie_bytes():
    from _hmb_video_tools import _find_ffmpeg
    return subprocess.check_output(
        [_find_ffmpeg(), "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=blue:s=854x480:d=0.2",
         "-an", "-c:v", "libx264", "-movflags", "+frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"],
        timeout=30,
    )


class CloudInputFixture:
    def __init__(self, folder):
        self.images = [Path(folder, name) for name in ("second.png", "first.png")]
        for path, color in zip(self.images, ("blue", "red")):
            with Image.new("RGB", (32, 16), color) as image:
                image.save(path)
        self.video = Path(folder, "reference.mp4")
        self.video.write_bytes(movie_bytes())
        self.audio = Path(folder, "reference.wav")
        with wave.open(str(self.audio), "wb") as output:
            output.setparams((1, 2, 8000, 0, "NONE", ""))
            output.writeframes(bytes(3200))
        self.uploads = []

    def upload_file(self, *, path, file_content, timeout):
        public = f"https://storage.example/{len(self.uploads)}?b=%2f%2B&a=2&a=1&sig=a%2Fb%3D"
        self.uploads.append((bytes(file_content), public))
        return public

    def delete_file(self, path):
        pass

    def expected(self, path):
        body = path.read_bytes()
        matching_urls = [url for data, url in self.uploads if data == body]
        assert len(matching_urls) == 1, (path.name, len(matching_urls))
        return f"{matching_urls[0]}#hmb-v1={sha256(body).hexdigest()}:{len(body)}"

    def assert_payload(self, case, payload, *, frames=False):
        second, first = (self.expected(path) for path in self.images)
        if frames:
            case.assertEqual(payload['first_frame'], [first])
            case.assertEqual(payload['last_frame'], [second])
            case.assertEqual(len(self.uploads), 2)
        else:
            case.assertEqual(payload['image_urls'], [second, first, second])
            case.assertEqual(payload['video_urls'], [self.expected(self.video)] * 2)
            case.assertEqual(payload['audio_urls'], [self.expected(self.audio)] * 2)
            case.assertEqual(len(self.uploads), 4)
