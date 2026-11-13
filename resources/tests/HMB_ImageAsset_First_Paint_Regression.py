"""Initial catalog reuse and bounded thumbnail work, without application/network IO."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("hmb_first_paint_regression", ROOT / "HMBImageAssetLibrary.py")
library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = library
spec.loader.exec_module(library)


class FirstPaintRegression(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-image-first-paint-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.catalog = self.base / "Projects"
        self.project = self.catalog / "Show" / "Ai_Ct_image"
        (self.project / "Assets").mkdir(parents=True)
        self.image = self.project / "Assets" / "Hero.png"
        # Catalog scanning permits unsupported image bytes but never claims
        # them as decoded. The thumbnail decoder is supplied below explicitly.
        self.image.write_bytes(b"original bounded image fixture")
        metadata = self.project / ".json"
        metadata.mkdir()
        self.manifest = metadata / "hmb_image_assets.json"
        self.manifest.write_text(json.dumps({
            "schema": "hmb-image-assets", "version": 1,
            "project_cache_uid": "hmbpc1:" + "1" * 32,
            "assets": [{"path": "Assets/Hero.png", "asset_id": "Hero",
                "image_name": "Hero", "image_main_type": "Character",
                "image_sub_type": "Full Appearance", "selected": True,
                "selection_order": 1}],
        }), encoding="utf-8")
        for name, value in (("_ASSET_CATALOG_INDEX_ROOT", self.base / "catalog-cache"),
                            ("_ASSET_THUMBNAIL_CACHE_ROOT", self.base / "thumbnail-cache")):
            patcher = patch.object(library, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        library._ASSET_THUMBNAIL_URLS.clear()
        library._SHARED_CATALOG_CACHE.clear()
        library._SHARED_CATALOG_ROOT_BINDINGS.clear()
        self.state = library._merge_scan_with_state(library._scan_project_assets(self.project), library._default_state())
        self.state["catalog_root"] = self.catalog.as_posix()
        self.state["projects"] = library._discover_project_catalog(self.catalog)["projects"]
        self.state = library._normalize_state(self.state)

    def request(self):
        return {"request_id": "first-paint", "project_uid": self.state["project_uid"],
            "project_cache_uid": self.state["project_cache_uid"],
            "manifest_signature": self.state["manifest_signature"],
            "scan_revision": self.state["scan_revision"],
            "asset_library_ids": [self.state["assets"][0]["asset_library_id"]]}

    def test_selection_uses_verified_disk_index_and_preserves_semantics(self):
        library._write_catalog_index(self.state)
        before = deepcopy(self.state)
        manifest_bytes = self.manifest.read_bytes()
        with patch.object(library, "_adopt_shared_catalog_snapshot", return_value=None), \
             patch.object(library, "_scan_project_assets", side_effect=AssertionError("valid index rescanned source")), \
             patch.object(library, "_asset_dimensions", side_effect=AssertionError("valid index opened image headers")):
            selected = library._select_catalog_project(self.state, self.project)
        self.assertEqual(selected["shot_routing"], before["shot_routing"])
        for field in ("project_uid", "project_cache_uid", "manifest_signature"):
            self.assertEqual(selected[field], before[field])
        for field in ("source_uid", "media_signature", "selected", "selection_order"):
            self.assertEqual(selected["assets"][0][field], before["assets"][0][field])
        self.assertEqual(self.manifest.read_bytes(), manifest_bytes)

    def test_changed_folder_index_falls_back_to_scan(self):
        library._write_catalog_index(self.state)
        (self.project / "Assets" / "New.png").write_bytes(b"new image fixture")
        with patch.object(library, "_adopt_shared_catalog_snapshot", return_value=None), \
             patch.object(library, "_scan_project_assets", wraps=library._scan_project_assets) as scanner:
            selected = library._select_catalog_project(self.state, self.project)
        self.assertEqual(scanner.call_count, 1)
        self.assertEqual(len(selected["assets"]), 2)

    def test_replaced_project_cannot_adopt_previous_index(self):
        library._write_catalog_index(self.state)
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        document["project_cache_uid"] = "hmbpc1:" + "2" * 32
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        with patch.object(library, "_adopt_shared_catalog_snapshot", return_value=None), \
             patch.object(library, "_scan_project_assets", wraps=library._scan_project_assets) as scanner:
            selected = library._select_catalog_project(self.state, self.project)
        self.assertEqual(scanner.call_count, 1)
        self.assertNotEqual(selected["project_cache_uid"], self.state["project_cache_uid"])
        self.assertNotEqual(selected["assets"][0]["media_signature"], self.state["assets"][0]["media_signature"])

    def test_request_reuses_verified_facts_but_checks_source_after_decode(self):
        with patch.object(library, "_asset_file_facts", wraps=library._asset_file_facts) as facts, \
             patch.object(library, "_generate_thumbnail_payload", return_value=(b"thumbnail", "webp", 1, 1)), \
             patch.object(library, "_publish_thumbnail_payload", return_value="memory://first-paint"):
            result = library._hydrate_asset_thumbnails(self.state, self.request())
        self.assertEqual(facts.call_count, 2, "one exact source check plus one post-decode check")
        self.assertEqual(result["thumbnail_result"]["completed_asset_library_ids"], self.request()["asset_library_ids"])
        self.assertEqual(result["shot_routing"], self.state["shot_routing"])

        # Equal-size/equal-mtime replacement during decoding is still rejected.
        library._ASSET_THUMBNAIL_URLS.clear()
        stat = self.image.stat()
        def replace_during_decode(_path):
            original = self.image.read_bytes()
            self.image.write_bytes(b"X" * len(original))
            os.utime(self.image, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return b"thumbnail", "webp", 1, 1
        with patch.object(library, "_read_persistent_thumbnail_cache", return_value=None), \
             patch.object(library, "_generate_thumbnail_payload", side_effect=replace_during_decode), \
             patch.object(library, "_publish_thumbnail_payload", return_value="memory://changed"):
            result = library._hydrate_asset_thumbnails(self.state, self.request())
        self.assertEqual(result["thumbnail_result"]["completed_asset_library_ids"], [])
        self.assertEqual(result["thumbnail_result"]["failed_asset_library_ids"], self.request()["asset_library_ids"])
        self.assertEqual(result["assets"][0]["thumbnail_url"], "")

    def test_slow_signature_does_not_block_another_or_duplicate_its_work(self):
        other = self.project / "Assets" / "Other.png"
        other.write_bytes(b"different fixture")
        entered = threading.Event()
        release = threading.Event()
        decoded = []
        def decode(path):
            decoded.append(path.name)
            if path == self.image:
                entered.set()
                self.assertTrue(release.wait(5), "held decoder was never released")
            return b"thumbnail", "webp", 1, 1
        with patch.object(library, "_read_persistent_thumbnail_cache", return_value=None), \
             patch.object(library, "_write_persistent_thumbnail_cache"), \
             patch.object(library, "_generate_thumbnail_payload", side_effect=decode), \
             patch.object(library, "_publish_thumbnail_payload", side_effect=lambda _b, _e, aid, _s: "memory://" + aid), \
             ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(library._asset_thumbnail_url, self.image, "hero")
            try:
                self.assertTrue(entered.wait(5))
                duplicate = pool.submit(library._asset_thumbnail_url, self.image, "duplicate")
                independent = pool.submit(library._asset_thumbnail_url, other, "other")
                self.assertEqual(independent.result(timeout=3), "memory://other")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3), "memory://hero")
            self.assertEqual(duplicate.result(timeout=3), "memory://hero")
        self.assertEqual(decoded.count("Hero.png"), 1)
        self.assertEqual(library._ASSET_THUMBNAIL_FLIGHTS, {})

    def test_failed_decoder_releases_signature_flight(self):
        with patch.object(library, "_read_persistent_thumbnail_cache", return_value=None), \
             patch.object(library, "_generate_thumbnail_payload", side_effect=ValueError("bad fixture")):
            self.assertEqual(library._asset_thumbnail_url(self.image, "hero"), "")
        self.assertEqual(library._ASSET_THUMBNAIL_FLIGHTS, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
