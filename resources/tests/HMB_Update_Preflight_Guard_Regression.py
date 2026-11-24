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
    def test_background_assertion_fails_an_otherwise_successful_host_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            log.write_text("Exception in thread snapshot:\nTraceback (most recent call last):\n"
                           "AssertionError\nHMB_HOST=PASS\n", encoding="utf-8")
            self.assertEqual(preflight.required_check_outcome(0, log), "unhandled_thread_exception")

    def test_missing_standard_agent_cannot_pass_a_required_host_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            log.write_text("HMB_REAL_STANDARD_AGENT_BOUNDARY=SKIP (standard Agent not importable)\n", encoding="utf8")
            self.assertEqual(preflight.required_check_outcome(0, log), "required_coverage_skipped")
            log.write_text("HMB_DESKTOP031_WORKFLOW_ENVELOPE=PASS\n", encoding="utf8")
            self.assertEqual(preflight.required_check_outcome(0, log), 0)
            self.assertEqual(preflight.required_check_outcome(1, log), 1)

    def test_every_registered_node_has_a_mandatory_check(self):
        self.assertEqual(len(preflight.check_inventory()), 11)

    def test_new_node_is_not_silently_uncovered(self):
        descriptor = json.loads((ROOT / "griptape-nodes-library.json").read_bytes())
        descriptor["nodes"].append({"class_name": "HMBNewLibrary"})
        with mock.patch.object(preflight.json, "loads", return_value=descriptor):
            with self.assertRaisesRegex(ValueError, "coverage differs"):
                preflight.check_inventory()

    def test_missing_duplicate_or_swapped_widget_declarations_block(self):
        descriptor = json.loads((ROOT / "griptape-nodes-library.json").read_bytes())
        widget = next(row for row in descriptor["widgets"] if row["name"] == "HMBVideoPickerCommandBridgeWidget")
        others = [row for row in descriptor["widgets"] if row != widget]
        for broken in (others, [*others, widget, widget], [*others, {**widget, "path": others[0]["path"]}]):
            with self.subTest(entries=len(broken)), mock.patch.object(
                    preflight.json, "loads", return_value={**descriptor, "widgets": broken}):
                with self.assertRaisesRegex(RuntimeError, "widget"):
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

    def test_same_desktop_versions_cannot_hide_an_unreviewed_engine(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-engine-") as temporary:
            output = Path(temporary)
            with (mock.patch.object(preflight, "version", side_effect=["0.104.0", "0.130.0", "0.110.0"]),
                  mock.patch.object(preflight, "inspect_editor_fixtures", side_effect=AssertionError("Wrong engine")),
                  mock.patch.object(preflight.subprocess, "run", side_effect=AssertionError("Must not execute"))):
                self.assertEqual(preflight.run(output / "candidate", output / "standard", output, "node"), 1)
            result = json.loads((output / "upgrade-check.json").read_bytes())
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["checks"], {})
            self.assertFalse(result["activation_approved"])
            self.assertIn("Unreviewed Griptape Nodes engine: 0.110.0", result["error"])

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

    def test_wheel_receipt_must_cover_current_widgets_and_behaviors(self):
        with tempfile.TemporaryDirectory(prefix="hmb-wheel-proof-") as temporary:
            proof = Path(temporary) / "wheel.json"
            fields = {"only_selected": True, "middle_pan": True, "selected_viewport_outline_without_reflow": True,
                      "unmount_releases_outline": True, "four_edges_visible_in_pixels": True}
            names = {name: path for name, path in preflight.WIDGET_FILES.items() if "BridgeWidget" not in name}
            self.assertEqual(len(names), len(preflight.LIBRARY_CHECKS))
            hashes = {path: preflight.digest(ROOT / path) for path in names.values()}
            cases = {name: dict(fields) for name in names}
            cases["HMBImageAssetLibraryWidget"]["refresh_keeps_same_grid_only"] = True
            cases["HMBPromptLibraryScopedBindingWidget"]["prompt_wheel_over_select_scrolls_table_with_value_preserved"] = True
            report = {"passed": True, "editor_sha256": "stock", "widget_sha256": hashes, "cases": cases,
                      "errors": [], "paid_calls": 0, "external_requests": 0}
            proof.write_text(json.dumps(report))
            preflight.validate_wheel_evidence(proof, "stock")
            name, path = next(iter(names.items()))
            for overrides in (
                {"cases": {key: value for key, value in cases.items() if key != name}},
                {"cases": {**cases, name: {**fields, "middle_pan": False}}},
                {"widget_sha256": {**hashes, path: "prior build"}},
                {"external_requests": 1},
            ):
                with self.subTest(fields=list(overrides)):
                    proof.write_text(json.dumps({**report, **overrides}))
                    with self.assertRaisesRegex(ValueError, "Wheel evidence"):
                        preflight.validate_wheel_evidence(proof, "stock")

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
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
            for key in ("APPDATA", "LOCALAPPDATA", "HOME", "GTN_CONFIG_WORKSPACE_DIRECTORY"):
                self.assertTrue(Path(env[key]).is_relative_to(root))

    def test_empty_runtime_source_cannot_pass_identity(self):
        with tempfile.TemporaryDirectory(prefix="hmb-update-empty-") as temporary:
            with self.assertRaisesRegex(ValueError, "No runtime source"):
                preflight.source_tree_digest(Path(temporary))


if __name__ == "__main__":
    unittest.main(verbosity=2)
