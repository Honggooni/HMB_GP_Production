"""Offline returned-frame compatibility; no engine, credentials or network."""
from __future__ import annotations

import asyncio
import importlib.util
import io
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import httpx
from PIL import Image

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("hmb_last_frame_formats", ROOT / "HMBSeedanceGeneration.py")
assert spec and spec.loader
t = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = t
spec.loader.exec_module(t)

ORIGIN = "http://192.168.203.245:8080"
ASSET = ORIGIN + "/api/assets/" + "a" * 43
EXTERNAL = "https://example.com/returned-frame.jpg?signature=synthetic-canary"


def image_bytes(image_format, *, mode="RGB", size=(8, 6)):
    output = io.BytesIO()
    color = (12, 44, 199, 128) if mode == "RGBA" else (12, 44, 199)
    Image.new(mode, size, color).save(output, format=image_format)
    return output.getvalue()


class Response:
    def __init__(self, content): self.content = content
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def geturl(self): return ASSET
    def read(self, maximum): return self.content[:maximum]


class ReturnedFrameFormats(unittest.TestCase):
    def assert_png_equivalent(self, normalized, original):
        self.assertTrue(t._is_valid_png(normalized))
        with Image.open(io.BytesIO(normalized)) as converted, Image.open(io.BytesIO(original)) as source:
            converted.load(); source.load()
            self.assertEqual(converted.size, source.size)
            self.assertEqual(converted.convert("RGB").tobytes(), source.convert("RGB").tobytes())

    def external(self, content, content_type="image/jpeg"):
        calls = []
        async def handler(request):
            calls.append(request)
            self.assertEqual(request.method, "GET")
            self.assertNotIn("authorization", request.headers)
            self.assertIn("image/jpeg", request.headers.get("accept", ""))
            self.assertIn("image/png", request.headers.get("accept", ""))
            return httpx.Response(200, content=content, headers={"content-type": content_type})
        original = t.httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        def client(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)
        node = object.__new__(t.HMBSeedanceGeneration)
        with mock.patch.object(t.httpx, "AsyncClient", side_effect=client), mock.patch.object(
            node, "_resolve_host_addresses", return_value=("93.184.216.34",)):
            result = asyncio.run(node._download_image(EXTERNAL))
        self.assertEqual(len(calls), 1)
        return result

    def trusted(self, content):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        requests = []
        def opened(request, *, timeout):
            requests.append(request)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, ASSET)
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-token")
            self.assertIn("image/jpeg", request.get_header("Accept"))
            return Response(content)
        bridge._opener = SimpleNamespace(open=opened)
        bridge._load_access_token = lambda: "synthetic-token"
        result = bridge.download_trusted_result(ASSET, max_bytes=t.MAX_LAST_FRAME_BYTES, media_type="image")
        self.assertEqual(len(requests), 1)
        return result

    def test_jpeg_external_download_becomes_png_without_rerender(self):
        raw = image_bytes("JPEG")
        self.assert_png_equivalent(self.external(raw), raw)

    def test_jpeg_trusted_download_becomes_png_with_same_origin_auth(self):
        raw = image_bytes("JPEG")
        self.assert_png_equivalent(self.trusted(raw), raw)

    def test_png_external_original_bytes_are_preserved(self):
        raw = image_bytes("PNG", mode="RGBA")
        self.assertEqual(self.external(raw, "image/png"), raw)

    def test_png_trusted_original_bytes_are_preserved(self):
        raw = image_bytes("PNG", mode="RGBA")
        self.assertEqual(self.trusted(raw), raw)

    def test_helper_preserves_png_with_transparency(self):
        raw = image_bytes("PNG", mode="RGBA")
        self.assertEqual(t._normalize_returned_last_frame(raw), raw)

    def test_helper_normalizes_jpeg_actual_decoded_pixels(self):
        raw = image_bytes("JPEG")
        self.assert_png_equivalent(t._normalize_returned_last_frame(raw), raw)

    def test_unsupported_gif_rejected(self):
        with self.assertRaises((RuntimeError, ValueError)):
            t._normalize_returned_last_frame(image_bytes("GIF"))

    def test_html_empty_and_corrupt_images_are_rejected(self):
        for raw in (b"", b"<html>error</html>", image_bytes("JPEG")[:40], image_bytes("PNG")[:40]):
            with self.subTest(length=len(raw)), self.assertRaises((RuntimeError, ValueError)):
                t._normalize_returned_last_frame(raw)

    def test_input_byte_budget_is_checked_before_decode(self):
        raw = image_bytes("JPEG")
        with mock.patch.object(Image, "open", side_effect=AssertionError("Must reject before decoding")):
            with self.assertRaises((RuntimeError, ValueError)):
                t._normalize_returned_last_frame(raw, max_bytes=len(raw) - 1)

    def test_normalized_output_byte_budget_is_enforced(self):
        image = Image.frombytes("RGB", (64, 64), random.Random(81).randbytes(64 * 64 * 3))
        encoded = io.BytesIO(); image.save(encoded, "JPEG", quality=75)
        raw = encoded.getvalue()
        self.assertGreater(len(t._normalize_returned_last_frame(raw)), len(raw))
        with self.assertRaises((RuntimeError, ValueError)):
            t._normalize_returned_last_frame(raw, max_bytes=len(raw))

    def test_pixel_budget_is_checked_before_verify_or_load(self):
        image = mock.MagicMock()
        image.format = "JPEG"
        image.size = (100_000_001, 1)
        image.__enter__.return_value = image
        with mock.patch.object(Image, "open", return_value=image):
            with self.assertRaises((RuntimeError, ValueError)):
                t._normalize_returned_last_frame(image_bytes("JPEG"))
        image.verify.assert_not_called()
        image.load.assert_not_called()

    def test_decompression_bomb_is_rejected_without_global_limit_changes(self):
        raw = image_bytes("JPEG")
        original = Image.MAX_IMAGE_PIXELS
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 4):
            with self.assertRaises((RuntimeError, ValueError)):
                t._normalize_returned_last_frame(raw)
            self.assertEqual(Image.MAX_IMAGE_PIXELS, 4)
        self.assertEqual(Image.MAX_IMAGE_PIXELS, original)

    def test_trusted_origin_guard_remains_before_image_decode_or_auth(self):
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        bridge._load_access_token = mock.Mock(side_effect=AssertionError("External origin cannot receive auth"))
        with self.assertRaises(t._BrokerProtocolError):
            bridge.download_trusted_result(EXTERNAL, max_bytes=t.MAX_LAST_FRAME_BYTES, media_type="image")
        bridge._load_access_token.assert_not_called()

    def test_existing_video_container_path_is_not_transformed(self):
        video = b"\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00qt  "
        bridge = t._HMBAIBrokerBridge(server_url=ORIGIN)
        bridge._load_access_token = lambda: "synthetic-token"
        bridge._opener = SimpleNamespace(open=lambda *args, **kwargs: Response(video))
        self.assertEqual(bridge.download_trusted_result(ASSET, max_bytes=1024, media_type="video"), video)


if __name__ == "__main__": unittest.main(verbosity=2)
