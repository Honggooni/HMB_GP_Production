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

    def test_only_server_registered_images_can_leave_the_workstation(self):
        source = self.project / "item.png"
        private = self.catalog.parent / "item.png"
        private.write_bytes(b"same name outside the project")
        from HMBSeedanceGeneration import HMBSeedanceGeneration

        node = HMBSeedanceGeneration.__new__(HMBSeedanceGeneration)
        with patch.object(image, "_PREVIOUS_PROJECTS_ROOT", self.catalog.as_posix()):
            with self.assertRaisesRegex(ValueError, "소스 누락"):
                image.require_registered_shared_image(source)
            image._write_asset_manifest_record(self.project, {
                "path": "item.png", "asset_id": "Item", "image_name": "Item",
                "image_main_type": "Character", "image_sub_type": "Full Appearance",
            })
            self.assertEqual(image.require_registered_shared_image(source), source.resolve())
            validated = node._registered_image_inputs({"reference_images": [str(source)]})
            self.assertEqual(validated["reference_images"], [str(source.resolve())])
            for candidate in (private, "data:image/png;base64,AA==", "https://example.invalid/item.png"):
                with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, "소스 누락"):
                    node._registered_image_inputs({"first_frame": str(candidate), "reference_images": []})

    def _teammate_saved_shot(self):
        manifest = self.project / ".json" / image.MANIFEST_NAMES[0]
        manifest.parent.mkdir(exist_ok=True)
        payload = {
            "schema": image.ASSET_MANIFEST_SCHEMA,
            "version": image.ASSET_MANIFEST_VERSION,
            "project_cache_uid": self.state["project_cache_uid"],
            "assets": [],
        }
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        catalog = {"catalog_root": str(self.catalog), "projects": self.state["projects"]}
        project = catalog["projects"][0]
        cold = image._read_selected_image_catalog(catalog, project, image._default_state())
        self.assertFalse(cold["assets"][0]["registered"])
        image._write_catalog_index(cold)

        # Another workstation introduces a new file and registers both that file
        # and one already known to this reader as unregistered.
        relative_paths = ("new.png", "item.png", "history.png")
        for relative in relative_paths:
            (self.project / relative).write_bytes(b"catalog fixture file")
            name = Path(relative).stem
            payload["assets"].append({"path": relative, "asset_id": name, "image_name": name})
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        saved = image._merge_scan_with_state(image._scan_project_assets(self.project), self.state)
        indexed = {row["relative_path"]: row for row in saved["assets"]}
        selected = [indexed[relative] for relative in relative_paths[:2]]
        for rank, row in enumerate(selected, 1):
            row.update(selected=True, selection_order=rank)
            self.assertTrue(row["registered"])
        history = {"uid": indexed["history.png"]["source_uid"], "label": "Previously removed",
                   "path": indexed["history.png"]["path"]}
        shot = saved["shot_routing"]["shots"][0]
        shot.update(selected_source_uids=[row["source_uid"] for row in selected],
                    image_link_notices=[history])
        self.assertEqual(cold["project_cache_uid"], saved["project_cache_uid"])
        return catalog, project, image._normalize_state(saved)

    def test_teammate_reopen_rechecks_stale_catalog_before_retiring_links(self):
        catalog, project, saved = self._teammate_saved_shot()
        original = deepcopy(saved["shot_routing"]["shots"][0])
        reopened = image._read_selected_image_catalog(catalog, project, saved, reuse_saved=True)
        self.assertEqual(reopened["shot_routing"]["shots"][0], original)
        selected = {row["source_uid"]: row for row in reopened["assets"] if row["selected"]}
        self.assertEqual(set(selected), set(original["selected_source_uids"]))
        self.assertEqual([selected[uid]["relative_path"] for uid in original["selected_source_uids"]],
                         ["new.png", "item.png"])
        self.assertTrue(all(row["registered"] for row in selected.values()))

    def test_teammate_share_failure_does_not_retire_saved_links(self):
        catalog, project, saved = self._teammate_saved_shot()
        original = deepcopy(saved["shot_routing"]["shots"][0])
        with patch.object(image, "_read_asset_manifest", side_effect=OSError("share unavailable")):
            try:
                reopened = image._read_selected_image_catalog(catalog, project, saved, reuse_saved=True)
            except image._ImageAssetSelectionPreparing:
                reopened = saved
        self.assertEqual(reopened["shot_routing"]["shots"][0], original)
        self.assertEqual(saved["shot_routing"]["shots"][0], original)

    def test_offline_disk_cache_does_not_retire_teammate_links(self):
        _, _, saved = self._teammate_saved_shot()
        original = deepcopy(saved["shot_routing"]["shots"][0])
        with patch.object(image, "_discover_shared_image_projects", side_effect=OSError("share unavailable")):
            reopened = image._load_project_catalog(self.catalog, saved)
        self.assertEqual(reopened["shot_routing"]["shots"][0], original)

    def test_authoritative_refresh_keeps_actual_deletion_as_history(self):
        catalog, project, saved = self._teammate_saved_shot()
        original = saved["shot_routing"]["shots"][0]
        removed, remaining = original["selected_source_uids"]
        (self.project / "new.png").unlink()
        refreshed = image._read_selected_image_catalog(catalog, project, saved, use_shared_cache=False)
        shot = refreshed["shot_routing"]["shots"][0]
        self.assertEqual(shot["selected_source_uids"], [remaining])
        self.assertEqual(shot["image_link_notices"][:-1], original["image_link_notices"])
        self.assertEqual(shot["image_link_notices"][-1]["uid"], removed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
