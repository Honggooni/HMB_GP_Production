"""Offline media and upload recorder for Generator submission tests."""
from hashlib import sha256
from pathlib import Path

from PIL import Image


class CloudInputFixture:
    def __init__(self, folder):
        self.images = [Path(folder, name) for name in ("second.png", "first.png")]
        for path, color in zip(self.images, ("blue", "red")):
            with Image.new("RGB", (32, 16), color) as image:
                image.save(path)
        self.video = Path(folder, "reference.mp4")
        self.video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"fixture-video" * 8)
        self.audio = Path(folder, "reference.wav")
        self.audio.write_bytes(b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(38))
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
