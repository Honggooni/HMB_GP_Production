"""Offline admission failures must never be reported as an approved update."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import hmb_griptape_update_preflight as preflight


class PreflightGuardTests(unittest.TestCase):
    def test_every_registered_node_has_a_mandatory_check(self):
        self.assertEqual(len(preflight.check_inventory()), 11)

    def test_new_node_is_not_silently_uncovered(self):
        descriptor = json.loads((ROOT / "griptape-nodes-library.json").read_bytes())
        descriptor["nodes"].append({"class_name": "HMBNewLibrary"})
        with mock.patch.object(preflight.json, "loads", return_value=descriptor):
            with self.assertRaisesRegex(ValueError, "coverage differs"):
                preflight.check_inventory()

    def test_missing_required_check_blocks(self):
        with mock.patch.object(preflight, "BROWSER_CHECKS", (*preflight.BROWSER_CHECKS, "Missing.mjs")):
            with self.assertRaisesRegex(ValueError, "Missing mandatory"):
                preflight.check_inventory()

    def test_duplicate_check_cannot_inflate_pass_count(self):
        with mock.patch.object(preflight, "CHECKS", (*preflight.CHECKS, preflight.CHECKS[0])):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                preflight.check_inventory()

    def test_unreviewed_sdk_stops_before_tests_and_never_activates(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-guard-") as temporary:
            output = Path(temporary)
            with mock.patch.object(preflight, "version", side_effect=["0.105.0", "0.130.0"]), \
                    mock.patch.object(preflight.subprocess, "run", side_effect=AssertionError("Must not execute")):
                self.assertEqual(preflight.run(output / "candidate", output / "standard", output, "node"), 1)
            result = json.loads((output / "upgrade-check.json").read_bytes())
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["checks"], {})
            self.assertFalse(result["activation_approved"])
            self.assertFalse(result["desktop_interaction_checked"])
            self.assertEqual(result["check_counts"], {
                "required": len(result["mandatory_checks"]), "passed": 0, "failed": 0,
                "not_run": len(result["mandatory_checks"]),
            })
            self.assertIn(preflight.HEADER_CHECK, result["mandatory_checks"])
            self.assertIn("0.105.0/0.130.0", result["error"])

    def test_same_entry_bundle_cannot_hide_a_changed_editor_dependency(self):
        with tempfile.TemporaryDirectory(prefix="hmb-editor-fixture-") as temporary:
            assets = Path(temporary)
            stock = assets / preflight.STOCK_EDITOR_ASSET
            react = assets / "react-Cwox1F5v.js"
            stock.write_bytes(b"fixture entry")
            react.write_bytes(b"fixture react")
            fixtures = {path.name: preflight.digest(path) for path in (stock, react)}
            with mock.patch.object(preflight, "EDITOR_0130_FIXTURES", fixtures):
                self.assertEqual(preflight.inspect_editor_fixtures(assets), fixtures)
                react.write_bytes(b"changed fixture react")
                with self.assertRaisesRegex(ValueError, "react-Cwox1F5v"):
                    preflight.inspect_editor_fixtures(assets)

    def test_old_header_receipt_cannot_validate_new_overlay(self):
        with tempfile.TemporaryDirectory(prefix="hmb-header-proof-") as temporary:
            proof = Path(temporary) / "header-0130.json"
            report = {"passed": True, "editor_source_sha256": preflight.STOCK_SHA256,
                      "header_sha256": "candidate-one", "integrated_headers": 11}
            proof.write_text(json.dumps(report), encoding="utf-8")
            preflight.validate_header_evidence(proof, "candidate-one")
            with self.assertRaisesRegex(ValueError, "header evidence"):
                preflight.validate_header_evidence(proof, "candidate-two")

    def test_legacy_deletion_receipt_cannot_validate_editor_0130(self):
        with tempfile.TemporaryDirectory(prefix="hmb-deletion-proof-") as temporary:
            proof = Path(temporary) / "native-safety.json"
            report = {"schema": "hmb-native-stock-deletion-safety/v1", "passed": True,
                      "editor_source_sha256": "legacy", "paid_calls": 0, "live_app_calls": 0,
                      "external_requests": 0, "cases": ["editor_0130_link_identity_and_checked_deletion"]}
            proof.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deletion safety evidence"):
                preflight.validate_deletion_evidence(proof)
            report["editor_source_sha256"] = preflight.STOCK_SHA256
            proof.write_text(json.dumps(report), encoding="utf-8")
            preflight.validate_deletion_evidence(proof)

    def test_same_version_source_change_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-source-") as temporary:
            root = Path(temporary)
            source = root / "api.py"
            source.write_text("def bind(workflow): pass\n", encoding="utf-8")
            before = preflight.source_tree_digest(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "noise.py").write_text("ignored", encoding="utf-8")
            self.assertEqual(preflight.source_tree_digest(root), before)
            source.write_text("def bind(workflow, owner): pass\n", encoding="utf-8")
            self.assertNotEqual(preflight.source_tree_digest(root), before)

    def test_test_environment_does_not_inherit_user_tokens(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-env-") as temporary:
            root = Path(temporary)
            with mock.patch.dict(preflight.os.environ, {"OPENAI_API_KEY": "secret", "HMB_BROKER_TOKEN": "secret"}):
                env = preflight.isolated_environment(root, root / "standard", root / "editor")
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("HMB_BROKER_TOKEN", env)
            for key in ("APPDATA", "LOCALAPPDATA", "HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY"):
                self.assertTrue(Path(env[key]).is_relative_to(root))

    def test_empty_runtime_source_cannot_pass_identity(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-empty-") as temporary:
            with self.assertRaisesRegex(ValueError, "No runtime source"):
                preflight.source_tree_digest(Path(temporary))


if __name__ == "__main__":
    unittest.main(verbosity=2)
