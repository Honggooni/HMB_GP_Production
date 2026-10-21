"""Bounded Pillow declarations and real image operations; no SDK or network."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import random
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from packaging.requirements import Requirement
from PIL import Image, __version__ as pillow_version
import _hmb_image_generation as images
from tools import package_runtime_release as release


class PillowHostCompatibility(unittest.TestCase):
    def setUp(self):
        self.project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        self.manifest = json.loads((ROOT / "griptape-nodes-library.json").read_text("utf-8"))
        self.sbom = json.loads((ROOT / "SBOM.spdx.json").read_text("utf-8"))

    def test_exact_bounded_declarations_accept_minimum_and_current_host(self):
        release.validate_editor_dependency_contract(self.project, self.manifest, self.sbom)
        requirement = Requirement("Pillow>=12.3.0,<14")
        for version in ("12.3.0", "13.0.0", "13.9.9", pillow_version):
            self.assertIn(version, requirement.specifier)
        for version in ("11.2.1", "12.2.9", "14.0.0", "15.0.0"):
            self.assertNotIn(version, requirement.specifier)

    def test_old_downgrade_pin_unbounded_or_divergent_declarations_fail(self):
        for bad in ("Pillow==12.3.0", "Pillow>=12.3.0", "Pillow>=11.2.1,<14", "Pillow>=12.3.0,<15"):
            with self.subTest(requirement=bad):
                project, manifest = deepcopy(self.project), deepcopy(self.manifest)
                for values in (project["project"]["dependencies"], manifest["metadata"]["dependencies"]["pip_dependencies"]):
                    values[values.index("Pillow>=12.3.0,<14")] = bad
                with self.assertRaisesRegex(RuntimeError, "bounded compatibility"):
                    release.validate_editor_dependency_contract(project, manifest, self.sbom)
        project = deepcopy(self.project)
        project["project"]["dependencies"].append("Pillow>=12.3.0,<14")
        with self.assertRaises(RuntimeError):
            release.validate_editor_dependency_contract(project, self.manifest, self.sbom)

    def test_sbom_does_not_claim_a_bundled_exact_pillow_version(self):
        package = next(item for item in self.sbom["packages"] if item["SPDXID"] == "SPDXRef-Pillow")
        self.assertEqual(package["versionInfo"], "NOASSERTION")
        self.assertIn("No Pillow distribution is bundled", package["comment"])
        changed = deepcopy(self.sbom)
        next(item for item in changed["packages"] if item["SPDXID"] == "SPDXRef-Pillow")["versionInfo"] = "12.3.0"
        with self.assertRaisesRegex(RuntimeError, "declared range"):
            release.validate_editor_dependency_contract(self.project, self.manifest, changed)

    def test_decode_and_atomic_save_preserve_png_jpeg_webp_bytes_and_existing_files(self):
        for format_name, suffix in (("PNG", ".png"), ("JPEG", ".jpg"), ("WEBP", ".webp")):
            with self.subTest(format=format_name), tempfile.TemporaryDirectory(prefix="hmb-pillow-codec-") as folder:
                buffer = BytesIO()
                with Image.new("RGB", (32, 16), (26, 85, 164)) as image:
                    image.save(buffer, format_name)
                raw = buffer.getvalue()
                checked = images.validate_image_bytes(raw, advertised_sha256=hashlib.sha256(raw).hexdigest())
                self.assertEqual((checked.width, checked.height), (32, 16))
                destination = Path(folder) / ("image" + suffix)
                destination.write_bytes(b"existing-user-file")
                saved = images.save_image_atomic(checked, destination)
                self.assertNotEqual(saved.path, destination)
                self.assertEqual(saved.path.read_bytes(), raw)
                self.assertEqual(destination.read_bytes(), b"existing-user-file")
                self.assertEqual(images.validate_image_bytes(saved.path.read_bytes()).sha256, checked.sha256)

    def test_real_lanczos_reference_resize_retains_original_and_global_limit(self):
        generator = random.Random(137)
        pixels = generator.randbytes(256 * 128 * 3)
        buffer = BytesIO()
        with Image.frombytes("RGB", (256, 128), pixels) as image:
            image.save(buffer, "PNG")
        original = images.validate_image_bytes(buffer.getvalue())
        original_hash, global_limit = original.sha256, Image.MAX_IMAGE_PIXELS
        resized = images._shrink_reference(original, 16_384)
        self.assertLessEqual(len(resized.data), 16_384)
        self.assertLess(resized.width, original.width)
        self.assertLess(resized.height, original.height)
        self.assertLess(abs(resized.width / resized.height - 2), 0.1)
        self.assertEqual(hashlib.sha256(original.data).hexdigest(), original_hash)
        self.assertEqual(Image.MAX_IMAGE_PIXELS, global_limit)

    def test_rgba_png_preserves_alpha_and_invalid_image_stays_error(self):
        buffer = BytesIO()
        with Image.new("RGBA", (16, 8), (15, 80, 145, 97)) as image:
            image.save(buffer, "PNG")
        checked = images.validate_image_bytes(buffer.getvalue())
        with Image.open(BytesIO(checked.data)) as image:
            self.assertEqual(image.getpixel((0, 0)), (15, 80, 145, 97))
        with self.assertRaises(images.ImageGenerationError):
            images.validate_image_bytes(b"not-an-image")


if __name__ == "__main__":
    print("Pillow host compatibility runtime=" + pillow_version, flush=True)
    unittest.main()
