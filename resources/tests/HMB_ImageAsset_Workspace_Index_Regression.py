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
        state = image._merge_scan_with_state(image._scan_project_assets(self.project), image._default_state())
        state["catalog_root"] = self.catalog.as_posix()
        state["projects"] = image._discover_project_catalog(self.catalog)["projects"]
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
            self.assertEqual([a["path"] for a in restored["assets"]], [a["path"] for a in self.state["assets"]])
            self.assertEqual(restored["shot_routing"], source["shot_routing"])
            self.assertEqual(image._read_local_project_list(self.catalog), self.state["projects"])
            other_root = self.catalog.parent / "Other" / "Show" / "Ai_Ct_image"
            self.assertIsNone(image._read_local_catalog_snapshot(other_root, source))
            wrong_id = dict(source, project_cache_uid="hmbpc1:" + "b" * 32)
            self.assertIsNone(image._read_local_catalog_snapshot(self.project, wrong_id))

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
