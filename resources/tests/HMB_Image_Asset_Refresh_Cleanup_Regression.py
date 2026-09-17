"""Explicit Refresh audit/confirmation regression; all durable IO is temporary."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "hmb_image_asset_refresh_cleanup_regression", ROOT / "HMBImageAssetLibrary.py"
)
assert spec is not None and spec.loader is not None
library = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = library
spec.loader.exec_module(library)


def record(path: str, name: str) -> dict:
    return {
        "path": path,
        "asset_id": name,
        "image_name": name,
        "source_type": "Character Appearance",
        "custom_source_type": "",
        "scope_candidate": "Full body / full appearance",
        "custom_metadata": {"retained": [1, "한글", True]},
    }


def fake_node(initial_state: dict):
    """Use the existing Background_Mutation regression's retained-mode fixture."""
    node = object.__new__(library.HMBImageAssetLibrary)
    live = {"state": library._normalize_state(initial_state)}
    published = []
    node._hmb_manifest_poll_received = False
    node._hmb_manifest_poll_pending = False
    node._hmb_refresh_revision = live["state"]["refresh_revision"]
    node._hmb_import_media_by_uid = {}
    node._hmb_import_revision = 0
    node._scan_owner_is_current = lambda: not getattr(node, "_hmb_node_deleted", False)
    node._replace_import_media = lambda _media: None
    node._merge_captured_imports_into_scan = lambda state, _media: state
    node.get_parameter_value = lambda _name: []
    node._current_state = lambda: live["state"]

    def publish(value):
        normalized = library._normalize_state(value)
        live["state"] = normalized
        published.append(normalized)
        return normalized

    node._publish_state = publish
    node._ensure_scan_runtime_state()
    return node, live, published


def finish_worker(node, live) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        thread = getattr(node, "_hmb_scan_thread", None)
        if thread is not None:
            thread.join(timeout=0.1)
        if node._consume_pending_catalog_scan_result():
            return live["state"]
        if not getattr(node, "_hmb_scan_pending_key", ""):
            return live["state"]
        time.sleep(0.01)
    raise AssertionError("Refresh/cleanup worker did not finish in five seconds.")


class RefreshCleanupRegression(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-refresh-regression-")
        self.addCleanup(self.temporary.cleanup)
        # Windows CI can return an 8.3 TEMP alias (RUNNER~1), while the real
        # audit resolves it to runneradmin. Use one physical path for fixture
        # state, fault-injection predicates and backup assertions alike.
        temporary_root = Path(self.temporary.name).resolve(strict=True)
        index_root = patch.object(library, "_ASSET_CATALOG_INDEX_ROOT", temporary_root / "catalog-index")
        index_root.start()
        self.addCleanup(index_root.stop)
        self.root = temporary_root / "ProjectA"
        self.root.mkdir()
        self.manifest = self.root / ".json" / library.MANIFEST_NAMES[0]
        self.manifest.parent.mkdir()
        self.keep = record("Present/Hero.png", "PresentHero")
        self.missing = record("RemovedFolder/Hero.png", "MissingHero")
        self.payload = {
            "schema": library.ASSET_MANIFEST_SCHEMA,
            "version": library.ASSET_MANIFEST_VERSION,
            "project_cache_uid": "hmbpc1:" + "a" * 32,
            "custom_top_level": {"order": [3, 1, 2], "note": "원본 유지"},
            "assets": [self.keep, self.missing],
        }
        self.write_manifest(self.payload)
        self.make_image("Present/Hero.png")
        self.make_image("Unregistered/Hero.png")

    def write_manifest(self, payload):
        self.manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def make_image(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        # Audit explicitly inspects filesystem facts, without decoding pixels.
        path.write_bytes(b"refresh-regression-file-not-pixel-decoded")
        return path

    def snapshot(self):
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

    def audit(self):
        review = library._audit_project_manifest_refresh(self.root)
        self.assertTrue(review["safe_to_clean"], review["error"])
        return review

    def state(self):
        state = library._default_state()
        state.update({
            "catalog_root": self.root.parent.as_posix(),
            "project_root": self.root.as_posix(),
            "project_id": "ProjectA",
            "project_uid": "project-a-uid",
            "projects": [{"project_id": "ProjectA", "project_uid": "project-a-uid",
                          "name": "ProjectA", "label": "ProjectA", "path": self.root.as_posix()}],
            "assets": [{
                **self.keep,
                "relative_path": self.keep["path"],
                "path": (self.root / self.keep["path"]).as_posix(),
                "asset_library_id": "library:present-hero",
                "source_uid": "project:library:present-hero",
                "source_kind": "project", "registered": True,
                "selected": True, "selection_order": 1, "extension": ".png",
            }],
        })
        return library._normalize_state(state)

    def refresh_node(self, initial=None):
        node, live, published = fake_node(initial or self.state())
        with patch.object(library, "_load_project_catalog", side_effect=lambda _root, state, **_kw: deepcopy(state)):
            pending = node._schedule_project_manifest_refresh(live["state"], self.root.parent.as_posix(), [])
            self.assertTrue(pending["scan_busy"])
            completed = finish_worker(node, live)
        self.assertEqual(completed["asset_refresh_review"]["status"], "review")
        self.assertIsInstance(node._hmb_refresh_authority, dict)
        return node, live, published

    def test_audit_full_relative_paths_missing_folder_and_no_mutation(self):
        before = self.snapshot()
        review = self.audit()
        self.assertEqual(review["registered_count"], 2)
        self.assertEqual(review["file_count"], 2)
        self.assertEqual(review["missing_paths"], ["RemovedFolder/Hero.png"])
        self.assertEqual(review["missing_records"], [self.missing])
        self.assertEqual(review["unregistered_paths"], ["Unregistered/Hero.png"])
        self.assertEqual(review["missing_count"], 1)
        self.assertEqual(review["unregistered_count"], 1)
        self.assertEqual(self.snapshot(), before)

    def test_cleanup_preserves_metadata_cache_uid_files_and_unregistered_status(self):
        before = self.snapshot()
        cached = library._read_asset_manifest(self.root)
        self.assertIn(self.missing["path"].casefold(), cached)
        cache_uid = library._project_cache_uid(self.root)
        result = library._clean_project_manifest_refresh(self.audit(), lambda: True)
        expected = {**self.payload, "assets": [self.keep]}
        self.assertEqual(json.loads(self.manifest.read_text(encoding="utf-8")), expected)
        self.assertEqual(result["cleaned_count"], 1)
        self.assertEqual(result["missing_count"], 0)
        self.assertEqual(result["unregistered_paths"], ["Unregistered/Hero.png"])
        self.assertEqual(Path(result["backup_path"]).read_bytes(), before[".json/" + self.manifest.name])
        self.assertEqual(library._project_cache_uid(self.root), cache_uid)
        self.assertNotIn(self.missing["path"].casefold(), library._read_asset_manifest(self.root))
        for relative, content in before.items():
            if relative.lower().endswith(".png"):
                self.assertEqual((self.root / relative).read_bytes(), content)

    def test_backup_rotation_keeps_three_feature_backups_and_user_backup(self):
        user_backup = self.manifest.parent / "customer-backup.json.bak"
        user_backup.write_bytes(b"user-owned")
        last_backup = None
        for index in range(4):
            self.write_manifest({**self.payload, "assets": [self.keep, record(f"Absent/Gone{index}.png", f"Gone{index}")]})
            result = library._clean_project_manifest_refresh(self.audit(), lambda: True)
            last_backup = Path(result["backup_path"])
        backups = list(self.manifest.parent.glob("hmb_image_assets.refresh-*.json.bak"))
        self.assertEqual(len(backups), 3)
        self.assertIn(last_backup, backups)
        self.assertEqual(user_backup.read_bytes(), b"user-owned")

    def test_legacy_list_container_is_retained(self):
        self.write_manifest([self.keep, self.missing])
        library._clean_project_manifest_refresh(self.audit(), lambda: True)
        self.assertEqual(json.loads(self.manifest.read_text(encoding="utf-8")), [self.keep])

    def test_project_without_manifest_is_read_only_and_cannot_clean(self):
        empty = self.root.parent / "NoManifest"
        empty.mkdir()
        (empty / "Unregistered.png").write_bytes(b"image")
        review = library._audit_project_manifest_refresh(empty)
        self.assertEqual(review["unregistered_paths"], ["Unregistered.png"])
        self.assertEqual(review["registered_count"], 0)
        self.assertFalse((empty / ".json").exists())
        with self.assertRaises(ValueError):
            library._clean_project_manifest_refresh(review, lambda: True)
        self.assertFalse((empty / ".json").exists())

    def test_missing_project_root_fails_closed(self):
        review = library._audit_project_manifest_refresh(self.root.parent / "MissingProject")
        self.assertFalse(review["safe_to_clean"])
        self.assertTrue(review["error"])

    def test_corrupt_json_fails_closed_and_is_untouched(self):
        self.manifest.write_bytes(b'{"assets": [broken json')
        before = self.snapshot()
        review = library._audit_project_manifest_refresh(self.root)
        self.assertFalse(review["safe_to_clean"])
        with self.assertRaises(ValueError):
            library._clean_project_manifest_refresh(review, lambda: True)
        self.assertEqual(self.snapshot(), before)

    def test_malformed_duplicate_and_unsafe_paths_fail_closed(self):
        for entries in ([None], [{"path": "../Outside.png"}], [self.keep, deepcopy(self.keep)]):
            with self.subTest(entries=entries):
                self.write_manifest({**self.payload, "assets": entries})
                before = self.snapshot()
                review = library._audit_project_manifest_refresh(self.root)
                self.assertFalse(review["safe_to_clean"])
                self.assertTrue(review["error"])
                self.assertEqual(self.snapshot(), before)

    def test_permissions_error_is_not_reported_as_missing_media(self):
        before = self.snapshot()
        actual = library.os.scandir

        def denied(path):
            if Path(path) == self.root / "Present":
                raise PermissionError("simulated folder permission denial")
            return actual(path)

        with patch.object(library.os, "scandir", side_effect=denied):
            review = library._audit_project_manifest_refresh(self.root)
        self.assertFalse(review["safe_to_clean"])
        self.assertIn("permission denial", review["error"])
        self.assertEqual(self.snapshot(), before)

    def test_partial_directory_enumeration_fails_closed(self):
        actual = library.os.scandir

        class PartialEntries:
            def __enter__(inner):
                inner.real = actual(self.root)
                return inner

            def __iter__(inner):
                yield next(inner.real)
                raise OSError("simulated share disconnect during enumeration")

            def __exit__(inner, *_args):
                inner.real.close()

        with patch.object(library.os, "scandir", side_effect=lambda path: PartialEntries() if Path(path) == self.root else actual(path)):
            review = library._audit_project_manifest_refresh(self.root)
        self.assertFalse(review["safe_to_clean"])
        self.assertIn("disconnect", review["error"])

    def test_inventory_limit_is_incomplete_not_missing(self):
        with patch.object(library, "MAX_ASSETS", 1):
            # Remove registered rows so this exercises the image walk limit.
            self.write_manifest({**self.payload, "assets": []})
            review = library._audit_project_manifest_refresh(self.root)
        self.assertFalse(review["safe_to_clean"])
        self.assertIn("complete-image", review["error"])

    def test_concurrent_add_invalidates_review_without_losing_add(self):
        review = self.audit()
        added = record("Unregistered/Hero.png", "NewlyAdded")
        library._write_asset_manifest_record(self.root, added)
        committed = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            library._clean_project_manifest_refresh(review, lambda: True)
        self.assertEqual(self.manifest.read_bytes(), committed)
        self.assertIn(added, json.loads(committed)["assets"])

    def test_restored_file_and_new_inventory_invalidate_review(self):
        for relative in ("RemovedFolder/Hero.png", "NewFolder/New.png"):
            with self.subTest(relative=relative):
                review = self.audit()
                self.make_image(relative)
                committed = self.manifest.read_bytes()
                with self.assertRaisesRegex(ValueError, "changed"):
                    library._clean_project_manifest_refresh(review, lambda: True)
                self.assertEqual(self.manifest.read_bytes(), committed)

    def test_permission_loss_at_confirmation_leaves_manifest_untouched(self):
        review = self.audit()
        committed = self.manifest.read_bytes()
        with patch.object(library.os, "scandir", side_effect=PermissionError("share inaccessible")):
            with self.assertRaisesRegex(ValueError, "inaccessible"):
                library._clean_project_manifest_refresh(review, lambda: True)
        self.assertEqual(self.manifest.read_bytes(), committed)

    def test_expired_authority_before_lock_creates_no_backup(self):
        review = self.audit()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "expired"):
            library._clean_project_manifest_refresh(review, lambda: False)
        self.assertEqual(self.snapshot(), before)

    def test_restore_after_reaudit_before_replace_aborts_cleanup(self):
        review = self.audit()
        committed = self.manifest.read_bytes()
        checks = 0

        def current():
            nonlocal checks
            checks += 1
            if checks == 3:
                self.make_image("RemovedFolder/Hero.png")
            return True

        with self.assertRaisesRegex(ValueError, "restored"):
            library._clean_project_manifest_refresh(review, current)
        self.assertEqual(self.manifest.read_bytes(), committed)
        self.assertEqual(list(self.manifest.parent.glob("*.json.bak")), [])
        self.assertEqual(list(self.manifest.parent.glob("*.tmp")), [])

    def test_ambiguous_replace_failure_retains_original_recovery_backup(self):
        review = self.audit()
        original = self.manifest.read_bytes()
        actual_replace = library.os.replace

        def replace_then_disconnect(source, destination):
            actual_replace(source, destination)
            raise OSError("simulated lost SMB acknowledgement after rename")

        with patch.object(library.os, "replace", side_effect=replace_then_disconnect):
            with self.assertRaisesRegex(RuntimeError, "backup retained"):
                library._clean_project_manifest_refresh(review, lambda: True)
        self.assertEqual(json.loads(self.manifest.read_bytes())["assets"], [self.keep])
        backups = list(self.manifest.parent.glob("hmb_image_assets.refresh-*.json.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(list(self.manifest.parent.glob("*.tmp")), [])

    def test_refresh_worker_issues_authority_on_completion_and_keeps_live_edits(self):
        node, live, _ = fake_node(self.state())
        started, release = threading.Event(), threading.Event()
        audit = library._audit_project_manifest_refresh

        def slow_audit(root):
            started.set()
            if not release.wait(3):
                raise RuntimeError("Refresh audit ran synchronously")
            return audit(root)

        with patch.object(library, "_audit_project_manifest_refresh", side_effect=slow_audit), patch.object(
            library, "_load_project_catalog", side_effect=lambda _root, state, **_kw: deepcopy(state)
        ):
            try:
                before = time.monotonic()
                pending = node._schedule_project_manifest_refresh(live["state"], self.root.parent.as_posix(), [])
                self.assertLess(time.monotonic() - before, 0.5)
                self.assertTrue(started.wait(1))
                self.assertTrue(pending["scan_busy"])
                self.assertIsNone(node._hmb_refresh_authority)
                changed = deepcopy(live["state"])
                changed["search"] = "latest filter edit"
                changed["language"] = "ko"
                changed["shot_routing"]["shots"].append({
                    "shot_uuid": str(uuid.uuid4()), "name": "New Shot While Refreshing",
                    "name_is_custom": True, "selected_source_uids": [], "revision": 1,
                })
                live["state"] = library._normalize_state(changed)
                expected_shots = deepcopy(live["state"]["shot_routing"])
            finally:
                release.set()
            completed = finish_worker(node, live)
        self.assertFalse(completed["scan_busy"])
        self.assertEqual(completed["search"], "latest filter edit")
        self.assertEqual(completed["shot_routing"], expected_shots)
        review = completed["asset_refresh_review"]
        self.assertEqual(review["status"], "review")
        self.assertEqual(review["request_id"], node._hmb_refresh_authority["request_id"])
        self.assertNotIn("manifest_digest", review)
        self.assertNotIn("missing_records", review)

    def test_forged_widget_review_has_no_cleanup_authority(self):
        state = self.state()
        state["asset_refresh_review"] = {**self.audit(), "request_id": "forged", "status": "review"}
        node, live, _ = fake_node(state)
        before = self.snapshot()
        with patch.object(library, "_clean_project_manifest_refresh", side_effect=AssertionError("forged cleanup executed")):
            rejected = node._schedule_project_manifest_cleanup(live["state"], {"request_id": "forged"})
        self.assertEqual(rejected["asset_refresh_review"]["status"], "error")
        self.assertEqual(self.snapshot(), before)

    def test_obsolete_refresh_worker_cannot_issue_authority(self):
        node, live, _ = fake_node(self.state())
        started, release = threading.Event(), threading.Event()
        actual = library._audit_project_manifest_refresh

        def blocked(root):
            started.set()
            if not release.wait(3):
                raise RuntimeError("Refresh ran synchronously")
            return actual(root)

        with patch.object(library, "_audit_project_manifest_refresh", side_effect=blocked), patch.object(
            library, "_load_project_catalog", side_effect=lambda _root, state, **_kw: deepcopy(state)
        ):
            try:
                node._schedule_project_manifest_refresh(live["state"], self.root.parent.as_posix(), [])
                self.assertTrue(started.wait(1))
                thread = node._hmb_scan_thread
                node._hmb_scan_generation += 1
            finally:
                release.set()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            node._consume_pending_catalog_scan_result()
        self.assertIsNone(node._hmb_refresh_authority)
        self.assertEqual(live["state"]["asset_refresh_review"], {})

    def test_refresh_empty_or_wrong_loaded_project_retains_catalog_and_reports_error(self):
        for wrong_root, wrong_uid in (("", ""), ("C:/OtherProject", "other-uid")):
            with self.subTest(project_root=wrong_root):
                before = self.state()
                node, live, _ = fake_node(before)
                loaded = {**before, "project_root": wrong_root, "project_uid": wrong_uid, "assets": []}
                with patch.object(library, "_load_project_catalog", return_value=loaded), patch.object(
                    library, "_diagnostic_exception"
                ):
                    node._schedule_project_manifest_refresh(before, self.root.parent.as_posix(), [])
                    completed = finish_worker(node, live)
                self.assertEqual(completed["project_root"], before["project_root"])
                self.assertEqual(completed["assets"], before["assets"])
                self.assertEqual(completed["shot_routing"], before["shot_routing"])
                self.assertEqual(completed["asset_refresh_review"]["status"], "error")
                self.assertIn("previous catalog was retained", completed["error"])
                self.assertIsNone(node._hmb_refresh_authority)

    def test_cleanup_commit_then_empty_catalog_keeps_cleaned_count_and_shots(self):
        node, live, _ = self.refresh_node()
        before = deepcopy(live["state"])
        request = {"request_id": before["asset_refresh_review"]["request_id"]}
        with patch.object(library, "_load_project_catalog", return_value=library._default_state()), patch.object(
            library, "_diagnostic_exception"
        ):
            node._schedule_project_manifest_cleanup(before, request)
            completed = finish_worker(node, live)
        self.assertEqual(json.loads(self.manifest.read_bytes())["assets"], [self.keep])
        self.assertEqual(completed["asset_refresh_review"]["status"], "cleaned")
        self.assertEqual(completed["asset_refresh_review"]["cleaned_count"], 1)
        self.assertIn("project became unavailable", completed["error"])
        self.assertEqual(completed["project_root"], before["project_root"])
        self.assertEqual(completed["assets"], before["assets"])
        self.assertEqual(completed["shot_routing"], before["shot_routing"])

    def test_postcommit_audit_error_keeps_cleaned_result_and_usable_catalog(self):
        node, live, _ = self.refresh_node()
        before = deepcopy(live["state"])
        request = {"request_id": before["asset_refresh_review"]["request_id"]}
        actual_audit = library._audit_project_manifest_refresh
        audit_calls = 0

        def audit_then_lose_share(root):
            nonlocal audit_calls
            audit_calls += 1
            if audit_calls == 1:
                return actual_audit(root)
            return {"safe_to_clean": False, "error": "post-commit share unavailable"}

        with patch.object(library, "_audit_project_manifest_refresh", side_effect=audit_then_lose_share), patch.object(
            library, "_load_project_catalog", side_effect=AssertionError("unsafe post-commit catalog load")
        ):
            node._schedule_project_manifest_cleanup(before, request)
            completed = finish_worker(node, live)
        self.assertEqual(audit_calls, 2)
        self.assertEqual(json.loads(self.manifest.read_bytes())["assets"], [self.keep])
        review = completed["asset_refresh_review"]
        self.assertEqual(review["status"], "cleaned")
        self.assertEqual(review["cleaned_count"], 1)
        self.assertFalse(review["safe_to_clean"])
        self.assertIn("post-commit share unavailable", review["error"])
        self.assertIn("post-commit share unavailable", completed["error"])
        self.assertTrue(Path(review["backup_path"]).is_file())
        self.assertEqual(completed["project_root"], before["project_root"])
        self.assertEqual(completed["assets"], before["assets"])
        self.assertEqual(completed["shot_routing"], before["shot_routing"])

    def test_deserialize_and_root_change_clear_private_and_public_confirmation(self):
        for lifecycle in ("deserialize", "root-change"):
            with self.subTest(lifecycle=lifecycle):
                node, live, _ = self.refresh_node()
                live["state"]["asset_cleanup_request"] = {"request_id": node._hmb_refresh_authority["request_id"]}
                scheduled = []

                def capture(_key, candidate, _scan, **_kwargs):
                    scheduled.append(deepcopy(candidate))
                    return candidate

                node._schedule_catalog_scan = capture
                if lifecycle == "root-change":
                    node._schedule_catalog_root_change(self.root.parent.as_posix())
                else:
                    node._ensure_parameters = lambda: None
                    node._schedule_post_hydration_shot_reconcile = lambda: None
                    with patch.object(library.DataNode, "after_deserialize", create=True), patch.object(
                        library, "_set_parameter_value"
                    ), patch.object(library, "_read_catalog_index", return_value=None):
                        node.after_deserialize()
                self.assertIsNone(node._hmb_refresh_authority)
                self.assertEqual(len(scheduled), 1)
                self.assertEqual(scheduled[0]["asset_refresh_review"], {})
                self.assertEqual(scheduled[0]["asset_cleanup_request"], {})

    def test_cleanup_worker_coalesces_duplicate_and_retains_new_shot_and_filter(self):
        node, live, _ = self.refresh_node()
        request = {"request_id": live["state"]["asset_refresh_review"]["request_id"]}
        started, release = threading.Event(), threading.Event()
        actual = library._clean_project_manifest_refresh
        calls = []

        def blocked(review, current):
            calls.append(review["request_id"])
            started.set()
            if not release.wait(3):
                raise RuntimeError("cleanup ran synchronously")
            return actual(review, current)

        with patch.object(library, "_clean_project_manifest_refresh", side_effect=blocked), patch.object(
            library, "_load_project_catalog", side_effect=lambda _root, state, **_kw: deepcopy(state)
        ):
            try:
                before = time.monotonic()
                node._schedule_project_manifest_cleanup(live["state"], request)
                self.assertLess(time.monotonic() - before, 0.5)
                self.assertTrue(started.wait(1))
                generation = node._hmb_scan_generation
                node._schedule_project_manifest_cleanup(live["state"], request)
                self.assertEqual(node._hmb_scan_generation, generation)
                changed = deepcopy(live["state"])
                changed["search"] = "edited during cleanup"
                changed["shot_routing"]["shots"].append({
                    "shot_uuid": str(uuid.uuid4()), "name": "Cleanup Running Shot",
                    "name_is_custom": True, "selected_source_uids": [], "revision": 1,
                })
                live["state"] = library._normalize_state(changed)
                expected_shots = deepcopy(live["state"]["shot_routing"])
            finally:
                release.set()
            completed = finish_worker(node, live)
        self.assertEqual(calls, [request["request_id"]])
        self.assertEqual(completed["search"], "edited during cleanup")
        self.assertEqual(completed["shot_routing"], expected_shots)
        self.assertEqual(completed["asset_refresh_review"]["status"], "cleaned")

    def test_real_token_is_single_use_and_replay_cannot_write(self):
        node, live, _ = self.refresh_node()
        request = {"request_id": live["state"]["asset_refresh_review"]["request_id"]}
        with patch.object(library, "_load_project_catalog", side_effect=lambda _root, state, **_kw: deepcopy(state)):
            pending = node._schedule_project_manifest_cleanup(live["state"], request)
            self.assertTrue(pending["scan_busy"])
            self.assertIsNone(node._hmb_refresh_authority)
            completed = finish_worker(node, live)
        self.assertEqual(completed["asset_refresh_review"]["status"], "cleaned")
        self.assertEqual(completed["asset_refresh_review"]["cleaned_count"], 1)
        before_replay = self.snapshot()
        replay = node._schedule_project_manifest_cleanup(completed, request)
        self.assertEqual(replay["asset_refresh_review"]["status"], "error")
        self.assertEqual(self.snapshot(), before_replay)

    def test_wrong_token_project_root_and_uid_are_rejected(self):
        for field, value in (("request_id", "wrong-token"), ("project_root", "C:/other-project"), ("project_uid", "different-uid")):
            with self.subTest(field=field):
                node, live, _ = self.refresh_node()
                state = deepcopy(live["state"])
                request = {"request_id": state["asset_refresh_review"]["request_id"]}
                if field == "request_id":
                    request[field] = value
                else:
                    state[field] = value
                with patch.object(library, "_clean_project_manifest_refresh", side_effect=AssertionError("invalid cleanup executed")):
                    rejected = node._schedule_project_manifest_cleanup(state, request)
                self.assertEqual(rejected["asset_refresh_review"]["status"], "error")

    def test_reset_replacement_cannot_reuse_previous_nodes_displayed_review(self):
        _old_node, live, _ = self.refresh_node()
        retained = deepcopy(live["state"])
        replacement, _replacement_live, _ = fake_node(retained)
        with patch.object(library, "_clean_project_manifest_refresh", side_effect=AssertionError("reset replay executed")):
            rejected = replacement._schedule_project_manifest_cleanup(retained, {"request_id": retained["asset_refresh_review"]["request_id"]})
        self.assertEqual(rejected["asset_refresh_review"]["status"], "error")

    def test_inflight_cleanup_rechecks_deletion_generation_and_project(self):
        for invalidation in ("deleted", "generation", "project"):
            with self.subTest(invalidation=invalidation):
                node, live, _ = self.refresh_node()
                request = {"request_id": live["state"]["asset_refresh_review"]["request_id"]}
                committed = self.manifest.read_bytes()
                started, release = threading.Event(), threading.Event()
                actual = library._clean_project_manifest_refresh
                errors = []

                def blocked_cleanup(review, current):
                    started.set()
                    if not release.wait(3):
                        raise RuntimeError("cleanup ran synchronously")
                    try:
                        return actual(review, current)
                    except ValueError as exc:
                        errors.append(str(exc))
                        raise

                with patch.object(library, "_clean_project_manifest_refresh", side_effect=blocked_cleanup), patch.object(
                    library, "_diagnostic_exception"
                ):
                    try:
                        node._schedule_project_manifest_cleanup(live["state"], request)
                        self.assertTrue(started.wait(1))
                        thread = node._hmb_scan_thread
                        if invalidation == "deleted":
                            node._hmb_node_deleted = True
                        elif invalidation == "generation":
                            node._hmb_scan_generation += 1
                        else:
                            live["state"]["project_uid"] = "project-switched-during-cleanup"
                    finally:
                        release.set()
                    thread.join(3)
                    self.assertFalse(thread.is_alive())
                    node._consume_pending_catalog_scan_result()
                self.assertTrue(errors and "expired" in errors[0], errors)
                self.assertEqual(self.manifest.read_bytes(), committed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
