"""Workstation snapshot migration and offline paths. All catalog writes use a fixture."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBImageAssetLibrary as image


class WorkspaceIndex(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        base = Path(scratch.name)
        workspace = base / "Workstation"
        self.catalog = base / "Projects"
        self.project = self.catalog / "Show" / "Ai_Ct_image"
        self.project.mkdir(parents=True)
        (self.project / "item.png").write_bytes(b"")
        self.index_root = workspace / ".json" / "hmb_image_catalogs"
        self.legacy = base / "old-cache"
        env = patch.dict(os.environ, {"GTN_CONFIG_WORKSPACE_DIRECTORY": str(workspace)})
        env.start()
        self.addCleanup(env.stop)
        for key, value in (("_ASSET_CATALOG_INDEX_ROOT", self.index_root), ("_LEGACY_CATALOG_INDEX_ROOT", self.legacy)):
            setting = patch.object(image, key, value)
            setting.start()
            self.addCleanup(setting.stop)
        catalog = image._discover_shared_image_projects(self.catalog)
        self.catalog = Path(catalog["catalog_root"])
        self.project = Path(catalog["projects"][0]["path"])
        state = image._merge_scan_with_state(image._scan_project_assets(self.project), image._default_state())
        state.update(catalog_root=catalog["catalog_root"], projects=catalog["projects"])
        self.state = image._normalize_state(state)

    def test_workspace_and_offline_lookup_without_saved_identity(self):
        self.assertEqual(image._configured_catalog_index_root(), self.index_root)
        image._write_catalog_index(self.state)
        source = deepcopy(self.state)
        source["project_cache_uid"] = ""
        source["assets"] = []
        original_stat = Path.stat

        def reject_share_access(path, *args, **kwargs):
            if path.is_relative_to(self.catalog):
                self.fail(f"Offline snapshot accessed the share: {path}")
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", reject_share_access), patch.object(image, "_read_asset_manifest", side_effect=AssertionError):
            restored = image._read_local_catalog_snapshot(self.project, source)
            self.assertIsNotNone(restored)
            self.assertEqual([a["path"] for a in restored["assets"]], [a["path"] for a in self.state["assets"]])
            self.assertEqual(restored["shot_routing"], source["shot_routing"])
            self.assertEqual(image._read_local_project_list(self.catalog), self.state["projects"])
            other_root = self.catalog.parent / "Other" / "Show" / "Ai_Ct_image"
            self.assertIsNone(image._read_local_catalog_snapshot(other_root, source))
            wrong_id = dict(source, project_cache_uid="hmbpc1:" + "b" * 32)
            self.assertIsNone(image._read_local_catalog_snapshot(self.project, wrong_id))

    @unittest.skipUnless(os.name == "nt", "Windows DOS path spelling")
    def test_short_catalog_path_reopens_offline_after_verified_discovery(self):
        # A new node can receive a configured 8.3 path even though discovery
        # published the long path in the saved project list.
        import ctypes
        expanded = self.catalog.parent / "Long project directory name" / "Projects"
        project = expanded / "Example" / "Ai_Ct_image"
        project.mkdir(parents=True)
        (project / "one.png").write_bytes(b"")
        short = ctypes.create_unicode_buffer(32768)
        size = ctypes.windll.kernel32.GetShortPathNameW(str(expanded), short, len(short))
        if not size or size >= len(short) or not image._windows_short_catalog_path(Path(short.value)):
            self.skipTest("Volume has no 8.3 aliases")
        requested = Path(short.value)
        catalog = image._discover_shared_image_projects(requested)
        state = image._read_selected_image_catalog(catalog, catalog["projects"][0], image._default_state())
        self.assertEqual(Path(state["catalog_root"]), expanded)
        original_stat = Path.stat
        def offline(path, *args, **kwargs):
            if path.is_relative_to(requested) or path.is_relative_to(expanded):
                self.fail(f"Offline lookup tried the shared drive: {path}")
            return original_stat(path, *args, **kwargs)
        with patch.object(image, "_discover_shared_image_projects", side_effect=OSError("offline")), patch.object(Path, "stat", offline):
            reopened = image._load_project_catalog(requested, state)
            self.assertEqual(reopened["assets"], state["assets"])
            self.assertEqual(reopened["shot_routing"], state["shot_routing"])
            self.assertEqual(image._read_local_project_list(requested), state["projects"])
            # An incorrect or corrupted lookup must not leave its drive/path boundary.
            alias_file = image._catalog_lookup_path("spelling", requested)
            alias_file.write_text(json.dumps("Z:/another/catalog"), encoding="utf-8")
            self.assertEqual(image._read_local_project_list(requested), [])

    def test_verified_legacy_snapshot_migrates_and_corruption_stays_local(self):
        with patch.object(image, "_ASSET_CATALOG_INDEX_ROOT", self.legacy):
            image._write_catalog_index(self.state)
        old_file = self.legacy / image._catalog_index_path(self.project).name
        old_contents = old_file.read_bytes()
        restored = image._read_catalog_index(self.project, self.state)
        self.assertIsNotNone(restored)
        self.assertEqual(old_contents, old_file.read_bytes())
        new_file = image._catalog_index_path(self.project)
        self.assertTrue(new_file.is_file())
        self.assertEqual(image._read_local_project_list(self.catalog), self.state["projects"])
        bad = json.loads(new_file.read_text(encoding="utf-8"))
        bad["assets"][0]["relative_path"] = "../outside.png"
        new_file.write_text(json.dumps(bad), encoding="utf-8")
        self.assertIsNone(image._read_local_catalog_snapshot(self.project, self.state))


if __name__ == "__main__":
    unittest.main(verbosity=2)
