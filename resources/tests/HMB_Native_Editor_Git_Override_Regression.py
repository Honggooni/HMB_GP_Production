"""ZIP-free native override transactions, using report-only synthetic files."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import struct
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("native_release_fixture", Path(__file__).with_name("HMB_Native_Editor_Installer_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class NativeGitOverride(unittest.TestCase):
    setUp = fixture.NativeEditorInstall.setUp
    tearDown = fixture.NativeEditorInstall.tearDown
    previous_candidate = fixture.NativeEditorInstall.previous_candidate

    def app(self):
        archive = self.m.DEFAULT_SOURCE.parents[2] / "app.asar"
        archive.write_bytes(struct.pack("<4I", 4, 32, 28, 24) + b"x" * 40)
        return archive

    def result(self):
        result = self.m.apply_git_override()
        self.assertEqual(result["schema"], "hmb-native-editor-git-override")
        self.assertEqual(result["version"], 1)
        self.assertFalse(result["renderer_verified"])
        self.assertEqual(result["restart_required"], result["disk_ready"])
        return result

    def test_git_override_is_explicitly_independent_of_stopped_installer_guard(self):
        self.app()
        self.stopped.side_effect = RuntimeError("running app fixture")
        with mock.patch.object(self.m.subprocess, "run", side_effect=AssertionError("No process or engine requests")):
            result = self.result()
        self.assertEqual(result["status"], "applied")
        self.assertTrue(result["changed"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
        self.stopped.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "running app"):
            self.m.prepare_release_install()

    def test_backup_candidate_and_applying_receipt_are_durable_before_replace(self):
        self.app()
        real = self.m._atomic_write
        def inspect(path, value):
            if path == self.m.DEFAULT_SOURCE:
                plans = list(self.m.RELEASE_STATE_ROOT.glob("*/plan.json"))
                self.assertEqual(len(plans), 1)
                self.assertEqual(json.loads(plans[0].read_text())["status"], "applying")
                self.assertEqual((plans[0].parent / "before.js").read_bytes(), self.original)
                self.assertEqual((plans[0].parent / "candidate.js").read_bytes(), self.candidate)
            return real(path, value)
        with mock.patch.object(self.m, "_atomic_write", side_effect=inspect), mock.patch.object(self.m.os, "fsync", wraps=self.m.os.fsync) as sync:
            result = self.result()
        self.assertEqual(result["status"], "applied")
        self.assertGreaterEqual(sync.call_count, 6)

    def test_second_invocation_is_idempotent_and_does_not_create_backup_or_replace(self):
        self.app()
        first = self.result()
        with mock.patch.object(self.m, "_atomic_write", side_effect=AssertionError("No second disk replace")):
            second = self.result()
        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "current")
        self.assertTrue(second["already_current"])
        self.assertFalse(second["changed"])
        self.assertEqual(len(list(self.m.RELEASE_STATE_ROOT.glob("*/plan.json"))), 1)

    def test_locked_file_retains_original_and_returns_retry_without_retrying(self):
        self.app()
        real = self.m._atomic_write
        count = []
        def locked(path, value):
            if path == self.m.DEFAULT_SOURCE:
                count.append(path)
                raise PermissionError("synthetic Windows sharing violation")
            return real(path, value)
        with mock.patch.object(self.m, "_atomic_write", side_effect=locked):
            result = self.result()
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["reason_code"], "atomic_replace_blocked")
        self.assertEqual(len(count), 1)
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.assertEqual(json.loads(Path(result["plan"]).read_text())["status"], "pending")
        self.assertEqual(self.result()["status"], "applied")

    def test_actual_atomic_replace_failure_keeps_original_and_cleans_temporary_file(self):
        self.app()
        real = self.m.os.replace
        def locked(source, target):
            if Path(target) == self.m.DEFAULT_SOURCE:
                raise PermissionError("synthetic os.replace sharing violation")
            return real(source, target)
        with mock.patch.object(self.m.os, "replace", side_effect=locked):
            self.assertEqual(self.result()["status"], "pending")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
        self.assertEqual(list(self.m.DEFAULT_SOURCE.parent.glob("*.tmp")), [])

    def test_release_and_git_writes_share_one_exclusive_lock(self):
        self.app()
        with self.m._release_write_lock():
            result = self.result()
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["reason_code"], "write_lock_busy")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_receipt_failure_after_replace_restores_only_owned_original(self):
        self.app()
        real = self.m._json_write
        def fail(path, value):
            if value.get("status") == "applied":
                raise OSError("synthetic receipt failure")
            return real(path, value)
        with mock.patch.object(self.m, "_json_write", side_effect=fail):
            result = self.result()
        self.assertEqual(result["reason_code"], "rolled_back")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_failure_after_replace_restores_previous_candidate_not_pristine(self):
        self.app()
        previous = self.previous_candidate()
        real = self.m._atomic_write
        def fail(path, value):
            real(path, value)
            if path == self.m.DEFAULT_SOURCE and value == self.candidate:
                raise OSError("synthetic failure after replacement")
        with mock.patch.object(self.m, "_atomic_write", side_effect=fail):
            result = self.result()
        self.assertEqual(result["reason_code"], "rolled_back")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), previous)

    def test_failed_recovery_retains_backup_path_and_never_claims_unchanged(self):
        self.app()
        real = self.m._atomic_write
        def fail(path, value):
            if path == self.m.DEFAULT_SOURCE and value == self.original:
                raise PermissionError("synthetic recovery locked")
            real(path, value)
            if path == self.m.DEFAULT_SOURCE and value == self.candidate:
                raise OSError("synthetic failure after replace")
        with mock.patch.object(self.m, "_atomic_write", side_effect=fail):
            result = self.result()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason_code"], "rollback_unconfirmed")
        self.assertIsNone(result["changed"])
        self.assertEqual(Path(result["backup"]).read_bytes(), self.original)
        self.assertTrue(Path(result["plan"]).is_file())

    def test_foreign_update_after_replace_is_preserved_and_never_rolled_back(self):
        self.app()
        real = self.m._json_write
        foreign = b"different desktop updater's exact bytes"
        def fail(path, value):
            if value.get("status") == "applied":
                self.m.DEFAULT_SOURCE.write_bytes(foreign)
                raise OSError("synthetic external concurrent update")
            return real(path, value)
        with mock.patch.object(self.m, "_json_write", side_effect=fail):
            result = self.result()
        self.assertEqual(result["status"], "error")
        self.assertIn("foreign bytes preserved", result["reason"])
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), foreign)

    def test_source_drift_after_applying_receipt_is_not_overwritten(self):
        self.app()
        real = self.m._json_write
        foreign = b"external source update before native write"
        def drift(path, value):
            real(path, value)
            if value.get("status") == "applying":
                self.m.DEFAULT_SOURCE.write_bytes(foreign)
        with mock.patch.object(self.m, "_json_write", side_effect=drift):
            result = self.result()
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), foreign)

    def test_package_sdk_app_and_staged_drift_rejected_before_target_write(self):
        for changed in ("package", "sdk", "app", "candidate", "backup"):
            with self.subTest(changed=changed):
                self.app()
                self.m.DEFAULT_SOURCE.write_bytes(self.original)
                real = self.m._json_write
                before = {}
                def drift(path, value):
                    real(path, value)
                    if value.get("status") == "prepared":
                        target = {"package": self.m.RELEASE_DESCRIPTOR, "sdk": self.sdk_engine,
                                  "app": self.m.DEFAULT_SOURCE.parents[2] / "app.asar",
                                  "candidate": path.parent / "candidate.js", "backup": path.parent / "before.js"}[changed]
                        before[target] = target.read_bytes()
                        target.write_bytes(before[target] + b"\n ")
                try:
                    with mock.patch.object(self.m, "_json_write", side_effect=drift):
                        self.assertEqual(self.result()["status"], "unsupported")
                    self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)
                finally:
                    for path, value in before.items():
                        path.write_bytes(value)

    def test_unknown_source_and_version_are_unsupported_not_partial_success(self):
        self.app()
        self.m.DEFAULT_SOURCE.write_bytes(b"unknown modified bundle")
        self.assertEqual(self.result()["status"], "unsupported")
        self.assertEqual(list(self.m.RELEASE_STATE_ROOT.glob("*/plan.json")), [])
        self.m.DEFAULT_SOURCE.write_bytes(self.original)
        self.version.write_text("0.999.0")
        self.assertEqual(self.result()["status"], "unsupported")
        self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.original)

    def test_descriptor_helper_patcher_mismatch_unsupported(self):
        self.app()
        for key in ("helper_sha256", "patcher_sha256"):
            with self.subTest(key=key):
                self.m.RELEASE_DESCRIPTOR.write_text(json.dumps({**self.descriptor, key: "0" * 64}))
                self.assertEqual(self.result()["status"], "unsupported")
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_invalid_app_archive_prefix_cannot_apply(self):
        self.app().write_bytes(b"untrusted archive")
        self.assertEqual(self.result()["status"], "unsupported")
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_missing_sdk_hook_cannot_apply_without_importing_sdk(self):
        self.app()
        self.sdk_events.write_text("raise AssertionError('must not import SDK')\nclass EventManager: pass\n")
        self.assertEqual(self.result()["status"], "unsupported")
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_unknown_predecessor_allowlist_is_not_expanded(self):
        self.app()
        self.descriptor["previous_candidates"] = [{"bundle_sha256": "0" * 64, "helper_sha256": "1" * 64}]
        self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
        self.assertEqual(self.result()["status"], "unsupported")
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_both_exact_previous_releases_upgrade_with_their_own_backup(self):
        self.app()
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
                result = self.result()
                self.assertEqual(result["status"], "applied")
                self.assertEqual(Path(result["backup"]).read_bytes(), previous)
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)

    def test_reparse_point_target_rejected_before_state_creation(self):
        self.app()
        real = Path.lstat
        def reparse(path, *args, **kwargs):
            value = real(path, *args, **kwargs)
            if path == self.m.DEFAULT_SOURCE:
                return type("Reparse", (), {"st_mode": value.st_mode, "st_file_attributes": 0x400})()
            return value
        with mock.patch.object(Path, "lstat", reparse):
            self.assertEqual(self.result()["status"], "unsupported")
        self.assertFalse(self.m.RELEASE_STATE_ROOT.exists())

    def test_three_previous_releases_upgrade_and_only_exact_order_is_allowed(self):
        self.app()
        for selected in ("RECENT", "CURRENT", "PREVIOUS"):
            with self.subTest(selected=selected):
                previous = self.previous_candidate()
                previous_bundle = self.m.SUPPORTED_PREVIOUS_CANDIDATE_SHA256
                previous_helper = self.m.SUPPORTED_PREVIOUS_HELPER_SHA256
                for index, name in enumerate(("RECENT", "CURRENT", "PREVIOUS"), 1):
                    setattr(self.m, f"SUPPORTED_{name}_CANDIDATE_SHA256", previous_bundle if name == selected else str(index) * 64)
                    setattr(self.m, f"SUPPORTED_{name}_HELPER_SHA256", previous_helper if name == selected else str(index + 3) * 64)
                chain = [{"bundle_sha256": getattr(self.m, f"SUPPORTED_{name}_CANDIDATE_SHA256"),
                          "helper_sha256": getattr(self.m, f"SUPPORTED_{name}_HELPER_SHA256")}
                         for name in ("RECENT", "CURRENT", "PREVIOUS")]
                self.descriptor.pop("previous_candidate")
                self.descriptor["previous_candidates"] = chain
                self.m.RELEASE_DESCRIPTOR.write_text(json.dumps(self.descriptor))
                result = self.result()
                self.assertEqual(result["status"], "applied")
                self.assertEqual(Path(result["backup"]).read_bytes(), previous)
                self.assertEqual(self.m.DEFAULT_SOURCE.read_bytes(), self.candidate)
                for invalid in (list(reversed(chain)), [chain[0], chain[0], chain[2]],
                                [chain[0], chain[1], {**chain[2], "helper_sha256": "f" * 64}],
                                [chain[0]], [chain[0], chain[1]]):
                    with self.assertRaisesRegex(ValueError, "Unsupported previous"):
                        self.m._release_previous_candidates({"previous_candidates": invalid})
                with self.assertRaisesRegex(ValueError, "Unsupported previous"):
                    self.m._release_previous_candidates({"previous_candidates": chain, "previous_candidate": chain[2]})

    def test_cli_outputs_one_json_object_and_rejects_user_target_options(self):
        self.app()
        with mock.patch("sys.argv", [self.m.__file__, "--apply-git-override"]), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.m.main()
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "applied")
        with mock.patch("sys.argv", [self.m.__file__, "--apply-git-override", "--source", str(self.base / "other.js")]):
            with self.assertRaisesRegex(ValueError, "cannot be combined"):
                self.m.main()

    def test_git_cli_json_is_ascii_and_round_trips_through_cp949_stdout(self):
        expected = {"schema": "hmb-native-editor-git-override", "version": 1,
                    "status": "pending", "disk_ready": False, "restart_required": False,
                    "renderer_verified": False, "reason": "파일이 사용 중입니다. 저장 후 다시 시작하세요. 🌐",
                    "target": "C:/Users/한글사용자/문서/GriptapeNodes/라이브러리/파일.js"}
        buffer = io.BytesIO()
        stdout = io.TextIOWrapper(buffer, encoding="cp949")
        try:
            with mock.patch("sys.argv", [self.m.__file__, "--apply-git-override"]), \
                 mock.patch("sys.stdout", stdout), \
                 mock.patch.object(self.m, "apply_git_override", return_value=expected):
                self.m.main()
            stdout.flush()
            raw = buffer.getvalue()
            self.assertTrue(raw.isascii())
            self.assertEqual(json.loads(raw), expected)
        finally:
            stdout.detach()

    def test_unrelated_workflow_and_userdata_bytes_are_untouched(self):
        self.app()
        files = [self.base / "workflow.py", self.base / "output.png", self.base / "prefs.json"]
        before = {path: ("unchanged fixture " + path.name).encode() for path in files}
        for path, value in before.items():
            path.write_bytes(value)
        self.assertEqual(self.result()["status"], "applied")
        self.assertEqual({path: path.read_bytes() for path in files}, before)

    def test_no_background_waiter_or_dynamic_targets_are_exposed(self):
        text = Path(self.m.__file__).read_text("utf-8")
        body = text[text.index("def _git_override_apply_unlocked"):text.index("def main()")]
        self.assertNotIn("subprocess.", body)
        self.assertNotIn("time.sleep", body)
        self.assertNotIn("handle_request", body)
        self.assertEqual(list(__import__("inspect").signature(self.m.apply_git_override).parameters), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
