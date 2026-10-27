"""Native editor deployment transactions; synthetic bundles, no live app access."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


class NativeEditorInstall(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "reports/predeploy-fixes-20261026/installer"
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="native-adapter-", dir=parent)
        self.base = Path(self.tmp.name).resolve()
        spec = importlib.util.spec_from_file_location("fixture_native_patch", ROOT / "tools/hmb_color_lut_native_header_patch.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.original = b"synthetic pristine editor transaction fixture\n"
        self.candidate = b"synthetic HMB native editor transaction fixture\n"
        self.m.DEFAULT_SOURCE = self.base / "app/current/resources/editor-bundle/assets/index-DEZU41rc.js"
        self.m.DEFAULT_SOURCE.parent.mkdir(parents=True)
        self.m.DEFAULT_SOURCE.write_bytes(self.original)
        self.version = self.m.DEFAULT_SOURCE.parent.parent / ".version"
        self.version.write_text(self.m.EXPECTED_EDITOR_VERSION)
        self.sdk_site = self.m.DEFAULT_SOURCE.parents[2] / "engine-bundle/python/Lib/site-packages"
        self.sdk_engine = self.sdk_site / "griptape_nodes/retained_mode/engine.py"
        self.sdk_events = self.sdk_engine.parent / "managers/event_manager.py"
        self.sdk_metadata = self.sdk_site / "griptape_nodes-0.101.3.dist-info/METADATA"
        for path in (self.sdk_engine, self.sdk_events, self.sdk_metadata):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.sdk_engine.write_text("raise AssertionError('SDK must not execute')\ndef current_engine():\n    return None\n")
        self.sdk_events.write_text("raise AssertionError('SDK must not execute')\nclass EventManager:\n    def add_pre_dispatch_hook(self, hook): pass\n    def remove_pre_dispatch_hook(self, hook): pass\n    def register_request_handlers(self, owner): pass\n")
        self.sdk_metadata.write_text("Name: griptape-nodes\nVersion: 0.101.3\n")
        self.m.RELEASE_STATE_ROOT = self.base / "native-editor-installs"
        self.m.HELPER = self.base / "package/resources/editor/hmb-color-lut-native-header.js"
        self.m.HELPER.parent.mkdir(parents=True)
        self.m.HELPER.write_text("synthetic helper; transaction test only\n")
        self.m.RELEASE_DESCRIPTOR = self.m.HELPER.parent / "native-editor-patch.json"
        self.m.EXPECTED_SOURCE_SHA256 = self.m.sha256(self.original)
        self.descriptor = {
            "schema": "hmb-native-editor-patch-release", "version": 1,
            "editor_version": self.m.EXPECTED_EDITOR_VERSION, "bundle_name": self.m.EXPECTED_BUNDLE_NAME,
            "source_sha256": self.m.EXPECTED_SOURCE_SHA256, "candidate_sha256": self.m.sha256(self.candidate),
            "helper_path": "resources/editor/hmb-color-lut-native-header.js",
            "helper_sha256": self.m.sha256(self.m.HELPER.read_bytes()),
            "patcher_path": "tools/hmb_color_lut_native_header_patch.py",
            "patcher_sha256": self.m.sha256(Path(self.m.__file__).read_bytes()),
        }
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        # Existing exact-anchor transformation is covered by the package/native
        # UI suites. Here only its result is synthetic; deploy/backup/restore
        # functions and filesystem operations are the actual implementation.
        self.transform = mock.patch.object(self.m, "patch_editor_source", return_value=(self.candidate.decode(), {})).start()
        self.real_stopped = self.m._require_release_stopped
        self.stopped = mock.patch.object(self.m, "_require_release_stopped").start()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.assertTrue(self.base.is_relative_to((ROOT / "reports/predeploy-fixes-20261026/installer").resolve()))
        self.tmp.cleanup()

    def prepare(self):
        return Path(self.m.prepare_release_install()["plan"])

    def previous_candidate(self, *, old_helper=None):
        old_helper = old_helper or (b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n"
            b"old synthetic helper\n/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */\n")
        new_helper = (b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n"
            b"new synthetic helper\n/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */\n")
        suffix = b"\nvar D$t=({node_name:e,node_type:t,unchanged editor suffix\n"
        previous = b"unchanged editor prefix\n" + old_helper + suffix
        self.candidate = b"unchanged editor prefix\n" + new_helper + suffix
        self.m.HELPER.write_bytes(new_helper)
        self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256 = self.m.sha256(previous)
        self.m.SUPPORTED_PREVIOUS_HELPER_SHA256 = self.m.sha256(old_helper)
        self.descriptor.update(candidate_sha256=self.m.sha256(self.candidate),
            helper_sha256=self.m.sha256(new_helper), previous_candidate={
                "bundle_sha256": self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256,
                "helper_sha256": self.m.SUPPORTED_PREVIOUS_HELPER_SHA256})
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        self.m.DEFAULT_SOURCE.write_bytes(previous)
        return previous

    def test_previous_candidate_upgrade_only_replaces_verified_helper_and_backs_up_previous(self):
        previous = self.previous_candidate()
        path = self.prepare()
        self.transform.assert_not_called()
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
        self.assertEqual((path.parent / "before.js").read_bytes(), previous)
        self.assertEqual((path.parent / "candidate.js").read_bytes(), self.candidate)
        self.assertTrue(self.m.apply_release_install(path)["changed"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
        self.assertTrue(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])

    def test_previous_candidate_write_failure_restores_exact_previous_not_pristine(self):
        previous = self.previous_candidate()
        path = self.prepare()
        real_write = self.m._atomic_write
        def fail(target, value):
            real_write(target, value)
            if target == self.m.DEFAULT_SOURCE and value == self.candidate:
                raise OSError("injected after upgrade replace")
        with mock.patch.object(self.m, "_atomic_write", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected after upgrade"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
        # Ownership remains durable for the installer's explicit catch/rollback.
        self.assertEqual(json.loads(path.read_text())["status"], "applying")
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(json.loads(path.read_text())["status"], "rolled_back")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)

    def test_previous_candidate_receipt_failure_restores_exact_previous(self):
        previous = self.previous_candidate()
        path = self.prepare()
        real_write = self.m._json_write
        def fail(target, value):
            if value.get("status") == "applied":
                raise OSError("injected upgrade receipt failure")
            return real_write(target, value)
        with mock.patch.object(self.m, "_json_write", side_effect=fail):
            with self.assertRaisesRegex(OSError, "upgrade receipt"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)

    def test_previous_candidate_staged_tamper_and_intervening_change_are_not_overwritten(self):
        previous = self.previous_candidate()
        path = self.prepare()
        (path.parent / "before.js").write_bytes(b"changed backup")
        with self.assertRaisesRegex(ValueError, "staged candidate or backup changed"):
            self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
        path = self.prepare()
        self.m.DEFAULT_SOURCE.write_bytes(b"other update")
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.m.apply_release_install(path)
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), b"other update")

    def test_previous_candidate_requires_pinned_descriptor_full_bundle_and_helper_hashes(self):
        previous = self.previous_candidate()
        bad = {**self.descriptor, "previous_candidate": {
            **self.descriptor["previous_candidate"], "bundle_sha256": "0" * 64}}
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "Unsupported previous"):
            self.prepare()
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        self.m.DEFAULT_SOURCE.write_bytes(previous + b"changed outside helper")
        with self.assertRaisesRegex(ValueError, "Unknown installed editor"):
            self.prepare()
        self.m.DEFAULT_SOURCE.write_bytes(previous)
        self.m.SUPPORTED_PREVIOUS_HELPER_SHA256 = "0" * 64
        self.descriptor["previous_candidate"]["helper_sha256"] = "0" * 64
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        with self.assertRaisesRegex(ValueError, "Previous native editor helper hash"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_previous_candidate_requires_unique_markers_and_exact_boundary(self):
        for helper in (
            b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */\n",
            b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 *//* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */\n",
            b"/* HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1\n/* END_HMB_COLOR_LUT_NATIVE_HEADER_PORTAL_V1 */changed",
        ):
            with self.subTest(helper=helper):
                previous = self.previous_candidate(old_helper=helper)
                with self.assertRaisesRegex(ValueError, "markers are not unique|boundary changed"):
                    self.prepare()
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
                self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_previous_candidate_requires_exact_final_full_bundle_hash(self):
        previous = self.previous_candidate()
        self.descriptor["candidate_sha256"] = "0" * 64
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        with self.assertRaisesRegex(ValueError, "Upgraded native editor candidate differs"):
            self.prepare()
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_previous_candidate_stale_plan_cannot_rollback_another_upgrade(self):
        previous = self.previous_candidate()
        first, stale = self.prepare(), self.prepare()
        self.m.apply_release_install(first)
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.m.apply_release_install(stale)
        self.assertFalse(self.m.rollback_release_install(stale)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
        self.assertTrue(self.m.rollback_release_install(first)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)

    def test_two_previous_releases_upgrade_with_exact_individual_backup(self):
        for use_recent in (True, False):
            with self.subTest(use_recent=use_recent):
                previous = self.previous_candidate()
                if use_recent:
                    self.m.SUPPORTED_CURRENT_CANDIDATE_SHA256 = self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256
                    self.m.SUPPORTED_CURRENT_HELPER_SHA256 = self.m.SUPPORTED_PREVIOUS_HELPER_SHA256
                    self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256 = "1" * 64
                    self.m.SUPPORTED_PREVIOUS_HELPER_SHA256 = "2" * 64
                else:
                    self.m.SUPPORTED_CURRENT_CANDIDATE_SHA256 = "3" * 64
                    self.m.SUPPORTED_CURRENT_HELPER_SHA256 = "4" * 64
                self.descriptor.pop("previous_candidate")
                self.descriptor["previous_candidates"] = [
                    {"bundle_sha256": self.m.SUPPORTED_CURRENT_CANDIDATE_SHA256, "helper_sha256": self.m.SUPPORTED_CURRENT_HELPER_SHA256},
                    {"bundle_sha256": self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256, "helper_sha256": self.m.SUPPORTED_PREVIOUS_HELPER_SHA256},
                ]
                self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
                path = self.prepare()
                self.assertEqual((path.parent / "before.js").read_bytes(), previous)
                self.assertTrue(self.m.apply_release_install(path)["changed"])
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
                self.assertTrue(self.m.rollback_release_install(path)["rolled_back"])
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)

    def test_previous_array_rejects_unreviewed_pairs_duplicates_or_mixed_formats(self):
        older = {"bundle_sha256": self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256, "helper_sha256": self.m.SUPPORTED_PREVIOUS_HELPER_SHA256}
        recent = {"bundle_sha256": self.m.SUPPORTED_CURRENT_CANDIDATE_SHA256, "helper_sha256": self.m.SUPPORTED_CURRENT_HELPER_SHA256}
        for change in (
            {"previous_candidates": [older, recent]},
            {"previous_candidates": [recent, recent]},
            {"previous_candidates": [recent, {**older, "helper_sha256": "0" * 64}]},
            {"previous_candidates": [recent, older], "previous_candidate": older},
        ):
            with self.subTest(change=change):
                self.m.RELEASE_DESCRIPTOR.write_text(json.dumps({**self.descriptor, **change}))
                with self.assertRaisesRegex(ValueError, "Unsupported previous"):
                    self.prepare()
                self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_pristine_prepare_preserves_editor_and_captures_exact_backup(self):
        path = self.prepare()
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.assertEqual((path.parent / "before.js").read_bytes(), self.original)
        self.assertEqual((path.parent / "candidate.js").read_bytes(), self.candidate)
        self.transform.assert_called_once_with(self.original.decode())

    def test_sdk_preflight_reads_metadata_and_ast_without_executing_sdk(self):
        path = self.prepare()
        evidence = json.loads(path.read_text())["sdk_preflight"]
        self.assertEqual(evidence["version"], "0.101.3")
        self.assertEqual(evidence["capabilities"], ["current_engine", "add_pre_dispatch_hook", "remove_pre_dispatch_hook", "register_request_handlers"])
        self.assertEqual(evidence["source_sha256"]["engine"], self.m.sha256(self.sdk_engine.read_bytes()))
        self.assertEqual(self.m.apply_release_install(path)["sdk_preflight"], evidence)

    def test_unsupported_sdk_blocks_before_native_preparation(self):
        cases = (
            (self.sdk_metadata, "Name: griptape-nodes\nVersion: 0.93.0\n", "0.101.3"),
            (self.sdk_metadata, "Name: griptape-nodes-engine\nVersion: 0.104.2\n", "metadata"),
            (self.sdk_engine, "def old_engine(): pass\n", "current_engine"),
            (self.sdk_engine, "def current_engine(required): pass\n", "without arguments"),
            (self.sdk_engine, "def current_engine(:\n", "cannot be parsed"),
            (self.sdk_events, "class EventManager:\n    def add_pre_dispatch_hook(self, hook): pass\n", "remove_pre_dispatch_hook"),
            (self.sdk_events, "class EventManager:\n    def add_pre_dispatch_hook(self, hook): pass\n    def remove_pre_dispatch_hook(self, hook): pass\n", "register_request_handlers"),
            (self.sdk_events, "class EventManager:\n    async def add_pre_dispatch_hook(self, hook): pass\n    def remove_pre_dispatch_hook(self, hook): pass\n", "synchronous"),
            (self.sdk_events, "class EventManager:\n    def add_pre_dispatch_hook(self, hook, required): pass\n    def remove_pre_dispatch_hook(self, hook): pass\n", "one hook"),
        )
        for target, replacement, message in cases:
            with self.subTest(target=target.name, message=message):
                original = target.read_bytes()
                try:
                    target.write_text(replacement)
                    with self.assertRaisesRegex(ValueError, message):
                        self.prepare()
                    self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())
                    self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
                finally:
                    target.write_bytes(original)

    def test_sdk_metadata_ambiguity_and_missing_source_block_before_native_preparation(self):
        duplicate = self.sdk_site / "griptape_nodes-0.102.0.dist-info/METADATA"
        duplicate.parent.mkdir()
        duplicate.write_text("Name: griptape-nodes\nVersion: 0.102.0\n")
        with self.assertRaisesRegex(ValueError, "one griptape-nodes"):
            self.prepare()
        duplicate.unlink()
        self.sdk_engine.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_sdk_change_after_prepare_blocks_apply_but_does_not_block_rollback(self):
        path = self.prepare()
        self.sdk_engine.write_text(self.sdk_engine.read_text() + "# external SDK update\n")
        with self.assertRaisesRegex(ValueError, "SDK changed after preflight"):
            self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])
        path = self.prepare()
        self.m.apply_release_install(path)
        self.sdk_engine.unlink()
        self.assertTrue(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_apply_rollback_and_repeat_apply_are_idempotent(self):
        path = self.prepare()
        self.assertTrue(self.m.apply_release_install(path)["changed"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
        with mock.patch.object(self.m, "_atomic_write", side_effect=AssertionError("duplicate write")):
            self.m.apply_release_install(path)
        self.assertTrue(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])

    def test_exact_current_candidate_is_noop_even_on_rollback(self):
        self.m.DEFAULT_SOURCE.write_bytes(self.candidate)
        path = self.prepare()
        self.transform.assert_not_called()
        self.assertFalse((path.parent / "before.js").exists())
        self.assertFalse(self.m.apply_release_install(path)["changed"])
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)

    def test_unknown_bundle_is_rejected_before_creating_state(self):
        self.m.DEFAULT_SOURCE.write_bytes(b"other release or custom patch")
        with self.assertRaisesRegex(ValueError, "Unknown installed editor hash"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_unknown_editor_version_is_rejected_before_creating_state(self):
        self.version.write_text("0.999.0")
        with self.assertRaisesRegex(ValueError, "Unsupported installed editor version"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_helper_or_patcher_hash_mismatch_is_rejected(self):
        for key in ("helper_sha256", "patcher_sha256"):
            with self.subTest(key=key):
                self.m.RELEASE_DESCRIPTOR.write_text(json.dumps({**self.descriptor, key: "0" * 64}))
                with self.assertRaisesRegex(ValueError, "differs from the verified release"):
                    self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_generated_candidate_must_match_descriptor(self):
        self.transform.return_value = ("wrong generated output", {})
        with self.assertRaisesRegex(ValueError, "Generated native editor candidate"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_running_app_prevents_prepare_and_apply(self):
        self.stopped.side_effect = RuntimeError("running fixture app")
        with self.assertRaisesRegex(RuntimeError, "running"):
            self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())
        self.stopped.side_effect = None
        path = self.prepare()
        self.stopped.side_effect = RuntimeError("running fixture app")
        with self.assertRaisesRegex(RuntimeError, "running"):
            self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    @unittest.skipUnless(__import__("os").name == "nt", "Windows process probe")
    def test_process_probe_excludes_only_the_installers_exact_pid(self):
        # Exercise the real probe function under the mocked process-list I/O.
        # The helper must ignore itself but still reject another bundled worker.
        probe = self.real_stopped
        own_pid = self.m.os.getpid()
        with mock.patch.object(self.m.subprocess, "run", return_value=SimpleNamespace(stdout=str(own_pid) + "\n")):
            probe()
        with mock.patch.object(self.m.subprocess, "run", return_value=SimpleNamespace(stdout=f"{own_pid}\n{own_pid + 1}\n")):
            with self.assertRaisesRegex(RuntimeError, "bundled engine is running"):
                probe()

    def test_changed_editor_between_prepare_apply_is_not_overwritten(self):
        path = self.prepare()
        changed = b"external update after prepare"
        self.m.DEFAULT_SOURCE.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.m.apply_release_install(path)
        self.assertFalse(self.m.rollback_release_install(path)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), changed)

    def test_staged_backup_or_candidate_tampering_is_rejected(self):
        for name in ("before.js", "candidate.js"):
            with self.subTest(name=name):
                path = self.prepare()
                (path.parent / name).write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "staged candidate or backup changed"):
                    self.m.apply_release_install(path)
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_write_failure_before_replace_keeps_original(self):
        path = self.prepare()
        real_write = self.m._atomic_write
        def fail(target, value):
            if target == self.m.DEFAULT_SOURCE:
                raise OSError("injected replace failure")
            return real_write(target, value)
        with mock.patch.object(self.m, "_atomic_write", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_write_failure_after_replace_restores_original(self):
        path = self.prepare()
        real_write = self.m._atomic_write
        def fail(target, value):
            real_write(target, value)
            if target == self.m.DEFAULT_SOURCE and value == self.candidate:
                raise OSError("injected after replace")
        with mock.patch.object(self.m, "_atomic_write", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_plan_receipt_failure_after_replace_restores_original(self):
        path = self.prepare()
        real_write = self.m._json_write
        def fail_applied(target, value):
            if value.get("status") == "applied":
                raise OSError("injected receipt failure")
            return real_write(target, value)
        with mock.patch.object(self.m, "_json_write", side_effect=fail_applied):
            with self.assertRaisesRegex(OSError, "injected"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_stale_prepared_plan_cannot_undo_another_completed_install(self):
        first = self.prepare()
        stale = self.prepare()
        self.m.apply_release_install(first)
        with self.assertRaisesRegex(ValueError, "changed after preflight"):
            self.m.apply_release_install(stale)
        self.assertFalse(self.m.rollback_release_install(stale)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
        self.assertTrue(self.m.rollback_release_install(first)["rolled_back"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_direct_adapter_writes_share_an_exclusive_os_lock(self):
        path = self.prepare()
        with self.m._release_write_lock():
            with self.assertRaisesRegex(RuntimeError, "Another native editor write"):
                self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)

    def test_applying_ownership_is_durable_before_editor_replace(self):
        path = self.prepare()
        real_write = self.m._atomic_write
        def inspect(target, value):
            if target == self.m.DEFAULT_SOURCE and value == self.candidate:
                self.assertEqual(json.loads(path.read_text())["status"], "applying")
            return real_write(target, value)
        with mock.patch.object(self.m, "_atomic_write", side_effect=inspect):
            self.m.apply_release_install(path)
        self.assertEqual(json.loads(path.read_text())["status"], "applied")

    def test_plan_target_or_descriptor_tampering_is_rejected(self):
        path = self.prepare()
        value = json.loads(path.read_text())
        path.write_text(json.dumps({**value, "target": str(self.base / "foreign.js")}))
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.m.apply_release_install(path)
        path.write_text(json.dumps(value))
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps({**self.descriptor, "extra": "different descriptor bytes"}))
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.m.apply_release_install(path)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_foreign_plan_or_reparse_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the owned"):
            self.m.apply_release_install(self.base / "foreign/plan.json")
        original_lstat = Path.lstat
        target = self.m.DEFAULT_SOURCE
        def fake_lstat(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == target:
                return type("Reparse", (), {"st_mode": info.st_mode, "st_file_attributes": 0x400})()
            return info
        with mock.patch.object(Path, "lstat", fake_lstat):
            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                self.prepare()
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
