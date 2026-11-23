"""Local-only multi-folder configuration, replacement installs and competing editors."""
from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "_hmb_image_asset_sites.py"


def load_module(path=MODULE):
    spec = importlib.util.spec_from_file_location("hmb_site_settings_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save_competing(workspace, project, folder, ready, start, output):
    os.environ["GTN_CONFIG_WORKSPACE_DIRECTORY"] = workspace
    sites = load_module()
    prior = sites.get_site_settings(project)
    ready.put(prior["revision"])
    start.wait(20)
    try:
        sites.save_site_settings(project, [{"id": "new-1", "label": "업체", "root": folder}],
                                 "new-1", prior["revision"])
        output.put("saved")
    except ValueError:
        output.put("stale")


class SiteSettingsRegression(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hmb-project-add-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.workspace = self.path / "workspace"
        env = patch.dict(os.environ, GTN_CONFIG_WORKSPACE_DIRECTORY=str(self.workspace))
        env.start()
        self.addCleanup(env.stop)
        self.project = self.path / "projects" / "superwings12" / "Ai_Ct_image"
        self.sound = self.project.with_name("Ai_Ct_audio")
        self.gang = self.project.with_name("Ai_Ct_image_Gang")
        self.busan = self.path / "Busan" / "projects" / "superwings12" / "Ai_Ct_image_Gang"
        for folder in (self.project, self.sound, self.gang, self.busan):
            folder.mkdir(parents=True)
        self.sites = load_module()

    def test_upgrade_restart_keep_image_and_sound_separately(self):
        links = [{"id": "new-a", "label": "광주", "root": str(self.gang)},
                 {"id": "new-b", "label": "부산", "root": str(self.busan)}]
        first = self.sites.save_site_settings(self.project, links, "new-b", "0")
        self.assertEqual(len({item["id"] for item in first["links"]}), 2)
        self.assertEqual(first["write_site_id"], first["links"][1]["id"])
        self.assertEqual(self.sites.get_site_settings(self.sound, "sound")["links"], [])
        sounds = self.sites.save_site_settings(self.sound, links[:1], "hq", "0", media="sound")
        self.assertEqual(sounds["links"][0]["id"], first["links"][0]["id"])
        self.assertEqual(self.sites.settings_path(self.project).parent, self.sites.settings_path(self.sound, "sound").parent)
        # A replacement library carries no previous files. Its fresh module
        # finds the same local profile, including the old workstation choices.
        updated = self.path / "replacement-library"
        updated.mkdir()
        shutil.copyfile(MODULE, updated / MODULE.name)
        replacement = load_module(updated / MODULE.name)
        self.assertEqual(replacement.get_site_settings(self.project), first)
        self.assertEqual(replacement.get_site_settings(self.sound, "sound"), sounds)
        self.assertTrue(self.sites.settings_path(self.project).is_relative_to(self.workspace))
        self.assertEqual(list(self.gang.iterdir()) + list(self.busan.iterdir()), [])

    def test_disconnect_offline_and_reconnect_preserve_identity(self):
        link = {"id": "new-a", "label": "광주", "root": str(self.gang)}
        first = self.sites.save_site_settings(self.project, [link], "new-a", "0")
        marker = self.gang / "existing.bin"
        marker.write_bytes(b"kept")
        offline = self.gang.with_name("temporarily-offline")
        self.gang.rename(offline)
        second = self.sites.save_site_settings(self.project, [], "hq", first["revision"])
        offline.rename(self.gang)
        self.assertEqual(marker.read_bytes(), b"kept")
        third = self.sites.save_site_settings(self.project, [link], "new-a", second["revision"])
        self.assertEqual(first["write_site_id"], third["write_site_id"])
        self.assertEqual(self.sites.verify_folder_identity(self.gang, self.project, first["write_site_id"]), self.gang.resolve())
        with self.assertRaises(ValueError):
            self.sites.verify_folder_identity(self.busan, self.project, first["write_site_id"])

    def test_invalid_target_or_overlap_cannot_replace_profile(self):
        link = {"id": "new", "label": "광주", "root": str(self.gang)}
        first = self.sites.save_site_settings(self.project, [link], "new", "0")
        before = self.sites.settings_path(self.project).read_bytes()
        for links, target in (([], "not-attached"), ([dict(link, root=str(self.project))], "hq"),
                              ([link, dict(link, id="new-2")], "hq")):
            with self.assertRaises(ValueError):
                self.sites.save_site_settings(self.project, links, target, first["revision"])
        self.assertEqual(before, self.sites.settings_path(self.project).read_bytes())
        copy = self.sites.get_site_settings(self.project)
        copy["links"].clear()
        self.assertEqual(self.sites.get_site_settings(self.project), first)

    def test_first_read_prepares_separate_directories_and_reuses_result(self):
        ensure = self.sites.ensure_registration_directory
        existing = self.project / ".json"
        existing.mkdir()
        registry = existing / "hmb_image_assets.json"
        registry.write_bytes(b"existing registry")
        self.assertEqual(ensure(self.project), "")
        for root in (self.gang, self.busan, self.sound):
            self.assertEqual(ensure(root), "")
            self.assertEqual(list((root / ".json").iterdir()), [])
        with patch.object(Path, "lstat", side_effect=AssertionError("unexpected I/O")):
            self.assertEqual(ensure(self.project), "")
            self.assertEqual(ensure(self.gang), "")
        self.assertEqual(registry.read_bytes(), b"existing registry")

    def test_missing_source_read_only_and_explicit_retry(self):
        ensure = self.sites.ensure_registration_directory
        missing = self.path / "disconnected-media"
        self.assertIn("새로고침", ensure(missing))
        self.assertFalse(missing.exists())
        missing.mkdir()
        self.assertEqual(ensure(missing, refresh=True), "")
        with patch.object(Path, "mkdir", side_effect=PermissionError("read only")):
            warning = ensure(self.gang)
        self.assertIn("권한", warning)
        self.assertFalse((self.gang / ".json").exists())
        with patch.object(Path, "lstat", side_effect=AssertionError("unexpected I/O")):
            self.assertEqual(ensure(self.gang), warning)
        self.assertEqual(ensure(self.gang, refresh=True), "")
        self.assertTrue((self.gang / ".json").is_dir())

    def test_conflicts_and_redirects_do_not_create_or_replace_files(self):
        ensure = self.sites.ensure_registration_directory
        target = self.gang / ".json"
        target.write_bytes(b"this is a file")
        with self.assertRaises(ValueError):
            ensure(self.gang)
        self.assertEqual(target.read_bytes(), b"this is a file")
        target.unlink()
        self.assertEqual(ensure(self.gang, refresh=True), "")
        original_lstat = Path.lstat
        for redirected in (self.gang, self.gang.parent, target):
            def flagged_lstat(path):
                info = original_lstat(path)
                return (SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
                        if path == redirected else info)
            with patch.object(Path, "lstat", flagged_lstat):
                with self.assertRaises(ValueError):
                    ensure(self.gang, refresh=True)
                with self.assertRaises(ValueError):
                    ensure(self.gang)
        self.assertEqual(list(target.iterdir()), [])
        for invalid in ("https://example.invalid/source", "relative/path", str(self.path / ".." / "elsewhere")):
            with self.assertRaises(ValueError):
                ensure(invalid)

    def test_competing_settings_dialogs_cannot_overwrite_each_other(self):
        ctx = multiprocessing.get_context("spawn")
        ready, output, start = ctx.Queue(), ctx.Queue(), ctx.Event()
        workers = [ctx.Process(target=save_competing,
                               args=(str(self.workspace), str(self.project), str(folder), ready, start, output))
                   for folder in (self.gang, self.busan)]
        try:
            for worker in workers:
                worker.start()
            self.assertEqual([ready.get(timeout=20) for _ in workers], ["0", "0"])
            start.set()
            self.assertEqual(sorted(output.get(timeout=20) for _ in workers), ["saved", "stale"])
        finally:
            start.set()
            for worker in workers:
                worker.join(10)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(5)
        data = json.loads(self.sites.settings_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(data["write_site_id"], data["links"][0]["id"])


if __name__ == "__main__":
    unittest.main()
