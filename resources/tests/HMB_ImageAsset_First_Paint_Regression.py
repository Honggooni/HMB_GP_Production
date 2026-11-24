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
        # NTFS directory enumeration can briefly report the parent timestamp
        # from before Hero.png was created. Establish the fixture's final
        # directory write time before capturing the baseline scan.
        os.utime(self.image.parent, (1_700_000_000, 1_700_000_000))
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

    def test_unstable_directory_is_retried_once_in_isolation(self):
        affected = self.image.parent
        stable = self.project / "Stable"
        stable.mkdir()
        original = library._catalog_directory_entries
        for continuous in (False, True):
            calls = []
            def enumerate_directory(root, current):
                rows = original(root, current)
                calls.append(current)
                if current == affected and (continuous or calls.count(affected) == 1):
                    details = current.stat()
                    os.utime(current, ns=(details.st_atime_ns, details.st_mtime_ns + 2_000_000_000))
                return rows

            with patch.object(library, "_catalog_directory_entries", side_effect=enumerate_directory):
                if continuous:
                    with self.assertRaisesRegex(OSError, "changed during catalog verification"):
                        library._catalog_file_inventory(self.project, incremental=True, full=True)
                else:
                    folders, images, _ = library._catalog_file_inventory(self.project, incremental=True, full=True)
                    self.assertIn("Stable", folders)
                    self.assertIn(self.image, images)
            self.assertEqual(calls.count(affected), 2)
            self.assertEqual(calls.count(self.project), 1)
            self.assertLessEqual(calls.count(stable), 1)

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
        with patch.object(library, "_catalog_directory_stamp", return_value=(1, 1, 0, 0)), \
             patch.object(library, "_adopt_shared_catalog_snapshot", return_value=None), \
             patch.object(library, "_scan_project_assets", wraps=library._scan_project_assets) as scanner:
            # Fast writes on a mapped drive can leave the same observed
            # directory stamp. A disk index never proves current inventory.
            library._catalog_file_inventory(self.project, incremental=True, full=True)
            (self.project / "Assets" / "New.png").write_bytes(b"new image fixture")
            selected = library._select_catalog_project(self.state, self.project)
        self.assertEqual(scanner.call_count, 1)
        self.assertEqual(len(selected["assets"]), 2)

    def test_replaced_project_cannot_adopt_previous_index(self):
        library._write_catalog_index(self.state)
        document = json.loads(self.manifest.read_text(encoding="utf-8"))
        before = self.manifest.stat()
        document["project_cache_uid"] = "hmbpc1:" + "2" * 32
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        os.utime(self.manifest, ns=(before.st_atime_ns, before.st_mtime_ns))
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

    def test_disk_thumbnail_reopens_with_catalog_without_source_io(self):
        library._write_catalog_index(self.state)
        signature = self.state["assets"][0]["media_signature"]
        library._write_persistent_thumbnail_cache(signature, b"cached", "webp", 1, 1)
        _, media_path = library._thumbnail_cache_paths(signature)
        media_mtime = media_path.stat().st_mtime_ns

        class LocalDriver:
            def create_signed_download_url(self, path):
                return f"http://localhost:8124/external/{path.as_posix()}?v={path.stat().st_mtime_ns}"

        with patch.object(library, "_local_thumbnail_storage_driver", return_value=LocalDriver()), \
             patch.object(library, "_asset_file_facts", side_effect=AssertionError("opened original")), \
             patch.object(library, "_generate_thumbnail_payload", side_effect=AssertionError("decoded original")), \
             patch.object(library, "_publish_thumbnail_payload", side_effect=AssertionError("republished thumbnail")):
            snapshot = library._read_local_catalog_snapshot(self.project, self.state)
            self.assertIsNotNone(snapshot)
            library._restore_cached_catalog_thumbnails(snapshot)
            thumb = snapshot["assets"][0]["thumbnail_url"]
            self.assertIn(f"/{signature}.webp", thumb)
            library._ASSET_THUMBNAIL_URLS.clear()
            recovered = library._hydrate_asset_thumbnails(self.state, self.request())
            self.assertEqual(recovered["assets"][0]["thumbnail_url"], thumb)
            self.assertEqual(recovered["thumbnail_result"]["completed_asset_library_ids"], self.request()["asset_library_ids"])
            self.assertEqual(media_path.stat().st_mtime_ns, media_mtime)
            media_path.write_bytes(b"short")
            self.assertEqual(library._cached_asset_thumbnail_url(signature), "")

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

    def test_reopen_keeps_session_catalog_until_explicit_refresh(self):
        for number in range(18):
            (self.project / f"Other{number}").mkdir()
        saved = library._load_project_catalog(self.catalog, self.state, use_shared_cache=False)
        saved["shot_routing"]["shots"][0]["selected_source_uids"] = [saved["assets"][0]["source_uid"]]
        serialized = json.dumps(saved)
        with patch.object(library, "_catalog_directory_entries", wraps=library._catalog_directory_entries) as reads:
            for _ in range(3):
                reopened = library._load_project_catalog(self.catalog, json.loads(serialized))
                self.assertEqual(reopened["shot_routing"], saved["shot_routing"])
            self.assertEqual(reads.call_count, 0, "opening a save must not trigger the rotating raw-file probe")
            document = json.loads(self.manifest.read_text(encoding="utf-8"))
            document["assets"][0]["image_name"] = "서버에서 변경"
            self.manifest.write_text(json.dumps(document), encoding="utf-8")
            reopened = library._load_project_catalog(self.catalog, json.loads(serialized))
            self.assertEqual(reads.call_count, 0)
            self.assertEqual(reopened["assets"][0]["image_name"], saved["assets"][0]["image_name"])
            self.assertEqual(reopened["shot_routing"], saved["shot_routing"])
            self.assertEqual(reopened["assets"][0]["selection_order"], saved["assets"][0]["selection_order"])
        with patch.object(library, "_catalog_directory_entries", wraps=library._catalog_directory_entries) as reads:
            refreshed = library._load_project_catalog(self.catalog, reopened, use_shared_cache=False)
            self.assertEqual(refreshed["assets"][0]["image_name"], "서버에서 변경")
            self.assertEqual(refreshed["shot_routing"], saved["shot_routing"])
            self.assertEqual({call.args[1] for call in reads.call_args_list},
                             {self.project, self.image.parent, *(self.project / f"Other{i}" for i in range(18))})

    def test_new_empty_renamed_removed_and_nested_in_place_files(self):
        parents = [self.project / f"Sub{i:02d}" / "Nested" for i in range(10)]
        for parent in parents:
            parent.mkdir(parents=True)
        nested = parents[-1] / "raw.png"
        nested.write_bytes(b"one")
        warm = library._load_project_catalog(self.catalog, self.state, use_shared_cache=False)
        (parents[0] / "Empty").mkdir()
        (parents[0] / "old.png").write_bytes(b"two")
        self.assertNotIn("Sub00/Nested/Empty", library._load_project_catalog(self.catalog, warm)["folders"])
        changed = library._load_project_catalog(self.catalog, warm, use_shared_cache=False)
        self.assertIn("Sub00/Nested/Empty", changed["folders"])
        (parents[0] / "old.png").rename(parents[0] / "New.png")
        (parents[0] / "Empty").rmdir()
        changed = library._load_project_catalog(self.catalog, changed, use_shared_cache=False)
        self.assertNotIn("Sub00/Nested/Empty", changed["folders"])
        names = {a["relative_path"] for a in changed["assets"]}
        self.assertNotIn("Sub00/Nested/old.png", names)
        self.assertIn("Sub00/Nested/New.png", names)
        before = changed["folder_signature"]
        # Updating bytes need not change the directory's timestamp.
        nested.write_bytes(b"new and longer")
        with patch.object(library, "_catalog_directory_entries", wraps=library._catalog_directory_entries) as reads:
            for _ in range(4):
                reads.reset_mock()
                signature = library._project_folder_metadata_signature(self.project, reconcile=True)
                self.assertLessEqual(reads.call_count, library._RAW_FOLDER_PROBE_BATCH)
                if signature != before:
                    break
            self.assertNotEqual(signature, before, "the rolling verifier must eventually visit every old folder")
            reads.reset_mock()
            confirm = library._project_folder_metadata_signature(self.project, confirm=signature)
            self.assertEqual(confirm, signature)
            self.assertIn(nested.parent, [call.args[1] for call in reads.call_args_list])
        checked = library._load_project_catalog(self.catalog, changed, use_shared_cache=False)
        old_media = next(a for a in changed["assets"] if a["path"] == nested.as_posix())
        new_media = next(a for a in checked["assets"] if a["path"] == nested.as_posix())
        self.assertNotEqual(old_media["media_signature"], new_media["media_signature"])

    def test_failed_registry_or_directory_verification_preserves_last_snapshot(self):
        self.state = library._load_project_catalog(self.catalog, self.state, use_shared_cache=False)
        base = deepcopy(self.state)
        verified = self.manifest.read_bytes()
        self.manifest.write_bytes(b"{")
        with self.assertRaises(ValueError):
            library._load_project_catalog(self.catalog, self.state, use_shared_cache=False)
        self.assertEqual(base, self.state)
        self.manifest.write_bytes(verified)
        with patch.object(library, "_catalog_directory_entries", side_effect=PermissionError("offline")), \
             self.assertRaises(PermissionError):
            library._load_project_catalog(self.catalog, self.state, use_shared_cache=False)
        recovered = library._load_project_catalog(self.catalog, self.state)
        self.assertTrue(recovered["assets"][0]["registered"])
        self.assertTrue(recovered["assets"][0]["selected"])
        self.assertEqual(recovered["shot_routing"], base["shot_routing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
