"""Seedance media validation: real codecs, boundaries and no original mutation."""

from __future__ import annotations

import hashlib
import asyncio
import base64
from copy import deepcopy
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
import zlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image
from _hmb_image_limits import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    SeedanceImageLimitError,
    _inspect_image,
    inspect_seedance_image_payload,
    suggested_seedance_image_dimensions,
)


def image_bytes(format_name: str, width: int = 32, height: int = 16, **options) -> bytes:
    stream = BytesIO()
    with Image.new("RGB", (width, height), (24, 105, 188)) as image:
        image.save(stream, format=format_name, **options)
    return stream.getvalue()


def png_header(width: int, height: int) -> bytes:
    # Oversized declarations must be rejected before a decoder can allocate pixels.
    chunk = b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + struct.pack(">I", zlib.crc32(chunk))


class SeedanceImagePixelLimitsRegression(unittest.TestCase):
    def test_png_jpeg_and_webp_are_decoded_with_actual_dimensions(self):
        for codec in ("PNG", "JPEG", "WEBP"):
            with self.subTest(codec=codec):
                data = image_bytes(codec, 43, 29)
                info = inspect_seedance_image_payload(data, media_name="reference.jpg", reference_ordinal=3)
                self.assertEqual((info["width"], info["height"], info["pixels"]), (43, 29, 1247))
                self.assertEqual(info["format"], codec)
                self.assertEqual(info["mime_type"], {"PNG":"image/png", "JPEG":"image/jpeg", "WEBP":"image/webp"}[codec])
                self.assertEqual(info["bytes"], len(data))

    def test_lossless_and_alpha_webp_headers_match_the_decoder(self):
        for options in ({"lossless":True}, {"lossless":False}):
            with self.subTest(options=options):
                stream = BytesIO()
                with Image.new("RGBA", (39, 17), (10, 20, 30, 125)) as im:
                    im.save(stream, format="WEBP", **options)
                info = inspect_seedance_image_payload(stream.getvalue())
                self.assertEqual((info["width"], info["height"]), (39,17))

    def test_progressive_jpeg_is_valid(self):
        info = inspect_seedance_image_payload(image_bytes("JPEG", 25, 19, progressive=True))
        self.assertEqual((info["width"],info["height"]), (25,19))

    def test_exact_production_36_million_pixels_are_allowed(self):
        # Grayscale bounds test uses 36 MB of pixels, not a hundreds-of-MB RGB fixture.
        stream = BytesIO()
        with Image.new("L", (6000, 6000), 0) as image:
            image.save(stream, format="PNG")
        self.assertEqual(inspect_seedance_image_payload(stream.getvalue())["pixels"], MAX_IMAGE_PIXELS)

    def test_one_pixel_over_and_incident_dimensions_fail_before_decoding(self):
        for width,height in ((36_000_001,1),(8602,4301)):
            with self.subTest(dimensions=(width,height)), patch("PIL.Image.open") as decoder:
                with self.assertRaises(SeedanceImageLimitError) as caught:
                    inspect_seedance_image_payload(png_header(width,height),media_name="katurihouse_extr.jpg",reference_ordinal=3)
                decoder.assert_not_called()
                error=caught.exception
                self.assertEqual(error.code,"SEEDANCE_IMAGE_PIXEL_LIMIT")
                self.assertEqual(error.details["pixels"],width*height)
                self.assertIn("Image reference 3 (katurihouse_extr.jpg)",str(error))
                self.assertIn("36,000,000",str(error))

    def test_within_small_budget_decodes_and_one_pixel_over_is_rejected(self):
        data=image_bytes("PNG",17,13)
        self.assertEqual(_inspect_image(data,media_name="test.png",reference_ordinal=1,max_pixels=221,max_bytes=MAX_IMAGE_BYTES)["pixels"],221)
        with self.assertRaises(SeedanceImageLimitError) as caught:
            _inspect_image(data,media_name="test.png",reference_ordinal=1,max_pixels=220,max_bytes=MAX_IMAGE_BYTES)
        self.assertEqual(caught.exception.code,"SEEDANCE_IMAGE_PIXEL_LIMIT")

    def test_byte_limit_remains_strictly_below_30_mib(self):
        data=image_bytes("PNG")
        self.assertEqual(_inspect_image(data,media_name="",reference_ordinal=1,max_pixels=MAX_IMAGE_PIXELS,max_bytes=len(data)+1)["bytes"],len(data))
        for maximum in (len(data),len(data)-1):
            with self.subTest(maximum=maximum), self.assertRaises(SeedanceImageLimitError) as caught:
                _inspect_image(data,media_name="",reference_ordinal=1,max_pixels=MAX_IMAGE_PIXELS,max_bytes=maximum)
            self.assertEqual(caught.exception.code,"SEEDANCE_IMAGE_BYTE_LIMIT")
        self.assertEqual(MAX_IMAGE_BYTES,30*1024*1024)

    def test_invalid_truncated_and_unsupported_media_cannot_be_published(self):
        malformed = (b"",b"not an image",b"<svg></svg>",image_bytes("PNG")[:-14],image_bytes("JPEG")[:45],image_bytes("WEBP")[:-1])
        for data in malformed:
            with self.subTest(data_length=len(data)), self.assertRaises(SeedanceImageLimitError) as caught:
                inspect_seedance_image_payload(data)
            self.assertEqual(caught.exception.code,"SEEDANCE_IMAGE_INVALID")

    def test_existing_animated_webp_transport_keeps_original_bytes(self):
        stream=BytesIO()
        with Image.new("RGB",(20,20),(255,0,0)) as first, Image.new("RGB",(20,20),(0,0,255)) as second:
            first.save(stream,format="WEBP",save_all=True,append_images=[second],duration=100,loop=0)
        value = stream.getvalue()
        before = hashlib.sha256(value).hexdigest()
        info = inspect_seedance_image_payload(value)
        self.assertEqual((info["width"], info["height"]), (20, 20))
        self.assertEqual(hashlib.sha256(value).hexdigest(), before)

    def test_existing_bmp_gif_and_tiff_formats_remain_accepted(self):
        for format_name in ("BMP", "GIF", "TIFF"):
            with self.subTest(format_name=format_name):
                info = inspect_seedance_image_payload(image_bytes(format_name))
                self.assertEqual(info["format"], format_name)
                self.assertLessEqual(info["pixels"], MAX_IMAGE_PIXELS)

    def test_original_bytes_and_pillow_global_limit_are_preserved(self):
        original=bytearray(image_bytes("PNG"))
        before=hashlib.sha256(original).hexdigest()
        global_limit=Image.MAX_IMAGE_PIXELS
        inspect_seedance_image_payload(original)
        with self.assertRaises(SeedanceImageLimitError):
            inspect_seedance_image_payload(png_header(8602,4301))
        self.assertEqual(hashlib.sha256(original).hexdigest(),before)
        self.assertEqual(Image.MAX_IMAGE_PIXELS,global_limit)

    def test_public_errors_never_echo_a_url_secret_or_parent_directory(self):
        for name in (r"C:\Private\Company\shot.jpg","https://host/private/shot.jpg?token=credential","authorization=secret-value"):
            with self.subTest(name=name),self.assertRaises(SeedanceImageLimitError) as caught:
                inspect_seedance_image_payload(png_header(8602,4301),media_name=name,reference_ordinal=4)
            message=str(caught.exception)
            self.assertNotIn("Private",message)
            self.assertNotIn("credential",message)
            self.assertNotIn("secret-value",message)
            self.assertNotIn("https://",message)
            self.assertIn("Image reference 4",message)

    def test_suggested_incident_dimensions_preserve_ratio_and_fit(self):
        self.assertEqual(suggested_seedance_image_dimensions(8602,4301),(8484,4242))
        self.assertEqual(suggested_seedance_image_dimensions(6000,6000),(6000,6000))
        for width,height in ((50001,70003),(1,36_000_001),(36_000_001,1),(100000,100000)):
            with self.subTest(dimensions=(width,height)):
                resized=suggested_seedance_image_dimensions(width,height)
                self.assertGreaterEqual(min(resized),1)
                self.assertLessEqual(resized[0]*resized[1],MAX_IMAGE_PIXELS)
                self.assertLessEqual(resized[0],width)
                self.assertLessEqual(resized[1],height)

    def test_unsupported_input_and_dimensions_raise_bounded_errors(self):
        with self.assertRaises(SeedanceImageLimitError):
            inspect_seedance_image_payload("raw data URL")
        for dimensions in ((True,1),(0,1),(-1,2),(1.5,4)):
            with self.subTest(dimensions=dimensions),self.assertRaises(ValueError):
                suggested_seedance_image_dimensions(*dimensions)


class SeedanceImagePipelineIntegrationRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "pixel_limits_five_generator_fixture",
            ROOT / "resources/tests/HMB_Seedance_Five_Agent_Result_Consistency_Regression.py",
        )
        cls.fixture = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.fixture
        spec.loader.exec_module(cls.fixture)

    def tearDown(self):
        while self.fixture.base.TEMPORARIES:
            self.fixture.base.TEMPORARIES.pop().cleanup()

    def batch(self, references):
        batch = self.fixture.Batch("katuri8", agent_count=0)
        target = self.fixture.t
        for node in batch.nodes:
            node.values.update({target.TASK_PARAMETER: target.TASK_REFERENCE_TO_VIDEO,
                                "input_mode": target.INPUT_MODE_MULTIMODAL_REFERENCES,
                                "reference_images": list(references)})
            node.parameter_values.update(node.values)
            # Keep real image validation, cloud preparation and Base64 request
            # construction; replace only external capabilities and transport.
            node._prepare_video_references_for_run = target.HMBSeedanceGeneration._prepare_video_references_for_run.__get__(node)
            node._try_create_gt_cloud_storage_driver = unittest.mock.Mock(return_value=None)
            node.bridge.require_seedance_features = unittest.mock.Mock(
                side_effect=lambda *, output_format, **_features: output_format,
            )
        return batch

    def test_five_oversized_third_local_images_fail_before_cloud_or_billable_post(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            good = folder / "character.png"
            good.write_bytes(image_bytes("PNG", 32, 16))
            bad = folder / "oversized-background.png"
            stream = BytesIO()
            with Image.new("L", (8602, 4301), 0) as image:
                image.save(stream, format="PNG")
            bad.write_bytes(stream.getvalue())
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (good, bad)}
            batch = self.batch([str(good), str(good), str(bad)])
            asyncio.run(batch.execute())
            messages = []
            for node in batch.nodes:
                self.assertIs(node.results[-1]["was_successful"], False)
                message = node.results[-1]["result_details"]
                self.assertIn("SEEDANCE_IMAGE_PIXEL_LIMIT", message)
                self.assertIn("Image reference 3 (oversized-background.png)", message)
                self.assertIn("36,997,202", message)
                self.assertIn("36,000,000", message)
                messages.append(message)
                self.assertEqual(node.bridge.posts, [])
                self.assertEqual(node._temporary_video_uploads, [])
                node._try_create_gt_cloud_storage_driver.assert_not_called()
            self.assertEqual(len(set(messages)), 1)
            self.assertEqual({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (good, bad)}, before)

    def test_five_valid_local_images_submit_original_bytes_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            paths = [folder / ("image-" + str(number) + ".png") for number in range(1, 4)]
            contents = [image_bytes("PNG", 32 + number, 16 + number) for number in range(1, 4)]
            for path, content in zip(paths, contents):
                path.write_bytes(content)
            batch = self.batch(list(map(str, paths)))
            before = [deepcopy(node.values) for node in batch.nodes]
            asyncio.run(batch.execute())
            keys = []
            for node, authored in zip(batch.nodes, before):
                self.assertIs(node.results[-1]["was_successful"], True, node.results[-1])
                self.assertEqual(len(node.bridge.posts), 1)
                wire = node.bridge.posts[0]
                self.assertEqual(len(wire["image_urls"]), 3)
                for url, original in zip(wire["image_urls"], contents):
                    self.assertEqual(base64.b64decode(url.split(",", 1)[1], validate=True), original)
                self.assertEqual(node.values, authored)
                keys.append(wire["client_request_id"])
            self.assertEqual(len(set(keys)), 5)
            self.assertEqual([path.read_bytes() for path in paths], contents)

    def test_invalid_data_uri_fails_before_cloud_or_billable_post(self):
        valid = "data:image/png;base64," + base64.b64encode(image_bytes("PNG")).decode("ascii")
        invalid = "data:image/png;base64," + base64.b64encode(b"not an image").decode("ascii")
        batch = self.batch([valid, valid, invalid])
        asyncio.run(batch.execute())
        for node in batch.nodes:
            self.assertIs(node.results[-1]["was_successful"], False)
            self.assertIn("SEEDANCE_IMAGE_INVALID", node.results[-1]["result_details"])
            self.assertIn("Image reference 3", node.results[-1]["result_details"])
            self.assertEqual(node.bridge.posts, [])
            node._try_create_gt_cloud_storage_driver.assert_not_called()

    def test_https_reference_keeps_local_error_ordinal_and_does_not_fetch_remote_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "third-reference.png"
            path.write_bytes(png_header(8602, 4301))
            valid = "data:image/png;base64," + base64.b64encode(image_bytes("PNG")).decode("ascii")
            batch = self.batch(["https://cdn.example/first.png", valid, str(path)])
            asyncio.run(batch.execute())
            for node in batch.nodes:
                self.assertIs(node.results[-1]["was_successful"], False)
                self.assertIn("Image reference 3 (third-reference.png)", node.results[-1]["result_details"])
                self.assertEqual(node.bridge.posts, [])
                node._try_create_gt_cloud_storage_driver.assert_not_called()


if __name__ == "__main__":
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"status":"PASS" if result.wasSuccessful() else "FAIL","tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
