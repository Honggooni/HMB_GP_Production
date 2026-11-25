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

    def test_directory_confirmation_appends_without_reading_other_media(self):
        self.project.rmdir()
        _, first_id = self.sites.add_site_folder(self.project, str(self.gang), "image")
        self.gang.rename(self.gang.with_name("offline"))  # A previously linked vendor is offline.
        with patch.object(self.sites, "_check_directory_route", wraps=self.sites._check_directory_route) as check:
            added, second_id = self.sites.add_site_folder(self.project, str(self.busan), "image")
            self.assertEqual([x.args[0] for x in check.call_args_list], [self.busan])
        self.assertEqual([r["id"] for r in added["links"]], [first_id, second_id])
        self.assertEqual(added["write_site_id"], "hq")
        replay, again_id = self.sites.add_site_folder(self.project, str(self.busan), "image")
        self.assertEqual((replay, again_id), (added, second_id))
        restored = load_module()
        projects = [{"project_uid":"p", "path":str(self.project)}]
        with patch.object(restored, "_check_directory_route", side_effect=AssertionError("unexpected media probe")):
            self.assertEqual(restored.site_profiles(projects, "image"), {"p": added})
            with patch.object(restored, "_read", side_effect=AssertionError("repeated disk read")):
                self.assertEqual(restored.site_profiles(projects, "image"), {"p": added})
            self.assertEqual(restored.site_profiles(projects, "sound"), {})
            result = restored.save_site_settings(self.project, added["links"][1:], second_id,
                                                added["revision"], existing_only=True)
            self.assertEqual(len(result["links"]), 1)
            default = restored.save_site_settings(self.project, result["links"], "hq", result["revision"], existing_only=True)
            self.assertEqual(default["write_site_id"], "hq")
            self.assertEqual(default["links"], result["links"])
        self.project.mkdir()
        with patch.object(restored, "_check_directory_route", wraps=restored._check_directory_route) as check:
            default = restored.confirm_site_folder(self.project, "image", default["revision"], "hq")
            self.assertEqual([call.args[0] for call in check.call_args_list], [self.project])
            self.assertTrue((self.project / "add").is_dir())
            self.assertEqual(default["selected_site_id"], "")
            last = restored.save_site_settings(self.project, [], "hq", default["revision"], existing_only=True)
            self.assertEqual((last["links"], last["write_site_id"]), ([], "hq"))
            self.assertEqual(restored.site_profiles(projects, "image"), {"p": last})

    def test_done_upgrades_legacy_selection_and_only_prepares_the_chosen_folder(self):
        for media, base in (("image", self.project), ("sound", self.sound)):
            with self.subTest(media=media):
                links = [{"id": key, "label": key, "root": str(root)} for key, root in
                         (("first", self.gang), ("second", self.busan))]
                prior = self.sites.save_site_settings(base, links, "first" if media == "image" else "hq",
                                                     "0", media=media)
                # Recreate a genuine profile written before the Done control existed.
                path = self.sites.settings_path(base, media)
                record = json.loads(path.read_text(encoding="utf-8"))
                del record["selected_site_id"], record["generation"]
                path.write_text(json.dumps(record), encoding="utf-8")
                second_id = prior["links"][1]["id"]
                with patch.object(self.sites, "_check_directory_route", wraps=self.sites._check_directory_route) as inspected:
                    confirmed = self.sites.confirm_site_folder(base, media, prior["revision"], second_id)
                    self.assertEqual([call.args[0] for call in inspected.call_args_list], [self.busan])
                self.assertEqual(confirmed["selected_site_id"], second_id)
                self.assertEqual(confirmed["write_site_id"], prior["write_site_id"])
                self.assertEqual(confirmed["revision"], prior["revision"])
                self.assertEqual(confirmed["generation"], 2)
                expected = {"add", ".json"} if media == "image" else set()
                self.assertEqual({entry.name for entry in self.busan.iterdir()}, expected)
                self.assertEqual(list(self.gang.iterdir()), [])
                restarted = load_module()
                restored = restarted.site_profiles([dict(project_uid="p", path=str(base))], media)
                self.assertEqual(restored["p"], confirmed)
                if media == "sound":
                    self.assertEqual(restarted.confirm_site_folder(base, media, confirmed["revision"], second_id), confirmed)
                    self.assertEqual(list(self.busan.iterdir()), [])
                    continue
                marker = self.busan / ".json" / "existing.json"
                marker.write_bytes(b"keep")
                self.assertEqual(restarted.confirm_site_folder(base, media, confirmed["revision"], second_id), confirmed)
                self.assertEqual(marker.read_bytes(), b"keep")
                (self.busan/"add").rmdir()
                (self.busan/"add").write_bytes(b"file in place of directory")
                with self.assertRaisesRegex(ValueError, "같은 이름의 파일"):
                    restarted.confirm_site_folder(base, media, confirmed["revision"], second_id)
                self.assertEqual(restarted.get_site_settings(base, media, fresh=True), confirmed)
                (self.busan/"add").unlink()
                marker.unlink()
                (self.busan/".json").rmdir()

    def test_failed_add_or_stale_done_preserves_committed_profile(self):
        first, site_id = self.sites.add_site_folder(self.project, str(self.gang), "image")
        self.assertEqual(first["selected_site_id"], site_id)
        self.assertTrue((self.gang/"add").is_dir())
        self.assertTrue((self.gang/".json").is_dir())
        (self.busan/"add").write_bytes(b"conflict")
        with self.assertRaisesRegex(ValueError, "같은 이름의 파일"):
            self.sites.add_site_folder(self.project, str(self.busan), "image")
        with patch.object(self.sites, "_check_directory_route", side_effect=AssertionError("irrelevant share I/O")):
            with self.assertRaisesRegex(ValueError, "다른 창"):
                self.sites.confirm_site_folder(self.project, "image", "old", site_id)
        self.assertEqual(self.sites.get_site_settings(self.project, fresh=True), first)

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
