"""Offline project policy routing, provenance, and snapshot isolation checks."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
standard = Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"
if standard.is_dir():
    os.environ.setdefault("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", str(standard))
import HMBAgentLibrary as agent
from _hmb_project import ProjectPolicyPendingError, project_from_asset_payload, resolve_project

common = agent._hmb


def fresh_session():
    spec = importlib.util.spec_from_file_location("offline_project_session", ROOT / "_hmb_agent_session.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def bare_agent(source=None):
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_verified_prompt_source_node = source
    return node


class ProjectIdentity(unittest.TestCase):
    def test_all_three_folder_and_display_identities(self):
        for identity, name, folder in (("dinoster5", "다이노스터", "Dinoster5"), ("katuri8", "까투리8", "Katuri8"), ("superwings12", "슈퍼윙즈12", "superwings12")):
            expected = {"project_id": identity, "project_name": name, "project_folder": folder}
            self.assertEqual(resolve_project(folder), expected)
            self.assertEqual(resolve_project(name), expected)
            self.assertEqual(project_from_asset_payload(json.dumps({"project_id": folder, "project_root": "//server/catalog/" + folder})), expected)

    def test_legacy_absence_only(self):
        self.assertEqual(resolve_project()["project_id"], "superwings12")
        self.assertEqual(project_from_asset_payload({"projects": [{"project_id": "Dinoster5"}]})["project_id"], "superwings12")
        with self.assertRaisesRegex(ValueError, "project_required"):
            project_from_asset_payload({}, default_legacy=False)

    def test_unknown_mismatch_traversal_and_large_input_rejected(self):
        for payload in ({"project_id": "unknown"}, {"project_id": "Dinoster5", "project_root": "//server/catalog/superwings12"}, {"project_root": "//server/../Dinoster5"}, {"project_folder": "../superwings12"}, {"project_id": True}, "X" * (1024 * 1024 + 1)):
            with self.subTest(payload=str(payload)[:80]), self.assertRaises(ValueError):
                project_from_asset_payload(payload)

    def test_explicit_nested_project_conflict_rejected(self):
        with self.assertRaisesRegex(ValueError, "project_identity_mismatch"):
            project_from_asset_payload({"project_id": "Katuri8", "library": {"project_id": "Dinoster5"}})

    def test_connected_selection_precedes_stale_transport(self):
        asset = SimpleNamespace(_hmb_project_identity=lambda: resolve_project("Dinoster5"))
        prompt = SimpleNamespace(_hmb_connected_source_nodes={"SHOT_ASSET_IN": asset}, get_parameter_value=lambda key: {"project_id": "superwings12"})
        self.assertEqual(bare_agent(prompt)._hmb_selected_project()["project_id"], "dinoster5")

    def test_connected_blank_never_uses_legacy_default(self):
        asset = SimpleNamespace(get_parameter_value=lambda key: {})
        prompt = SimpleNamespace(_hmb_connected_source_nodes={"SHOT_ASSET_IN": asset})
        with self.assertRaisesRegex(ValueError, "project_required"):
            bare_agent(prompt)._hmb_selected_project()

    def test_two_different_connected_publishers_rejected(self):
        prompt = SimpleNamespace(_hmb_connected_source_nodes={"SHOT_ASSET_IN": object(), "IMAGE_ASSET_IN": object()})
        with self.assertRaisesRegex(ValueError, "project_source_ambiguous"):
            bare_agent(prompt)._hmb_selected_project()

    def test_switching_project_never_reuses_agent_identity(self):
        current = {"project_id": "Dinoster5"}
        asset = SimpleNamespace(_hmb_project_identity=lambda: resolve_project(current))
        node = bare_agent(SimpleNamespace(_hmb_connected_source_nodes={"SHOT_ASSET_IN": asset}))
        self.assertEqual(node._hmb_selected_project()["project_id"], "dinoster5")
        current["project_id"] = "Katuri8"
        self.assertEqual(node._hmb_selected_project()["project_id"], "katuri8")
        current["project_id"] = "unknown"
        with self.assertRaises(ValueError):
            node._hmb_selected_project()

    def test_legacy_wildcard_media_preserves_default_without_project_identity(self):
        for value in ("C:/reference/image.png", "data:image/png;base64,AAAA", ["C:/reference/image.png"], [{"url": "https://example.invalid/reference.png"}], {"url": "https://example.invalid/reference.png"}):
            prompt = SimpleNamespace(get_parameter_value=lambda key: value if key == "IMAGE_ASSET_IN" else None)
            with self.subTest(value=value):
                self.assertEqual(bare_agent(prompt)._hmb_selected_project()["project_id"], "superwings12")

    def test_legacy_explicit_unknown_or_malformed_project_still_rejected(self):
        for value in ({"project_id": "unknown"}, '{"project_id":"unknown"}', '{"project_id":"Dinoster5"', {"project_id": "Dinoster5", "project_root": "//server/Katuri8"}, [{"project_id": "unknown"}]):
            prompt = SimpleNamespace(get_parameter_value=lambda key: value if key == "IMAGE_ASSET_IN" else None)
            with self.subTest(value=value), self.assertRaises(ValueError):
                bare_agent(prompt)._hmb_selected_project()


class SignedProjectArtifact(unittest.TestCase):
    def test_installed_sw_signed_bytes_exact_and_other_projects_pending(self):
        encoded = (ROOT / "resources/agent/superwings12/hmb_agent_core.dat").read_bytes()
        self.assertEqual(common._read_agent_policy_envelope(), encoded)
        self.assertEqual(common._load_verified_agent_rule_payload()["project_id"], "superwings12")
        for project in ("dinoster5", "katuri8"):
            with self.assertRaises(ProjectPolicyPendingError):
                common._read_agent_policy_envelope(project)
            self.assertEqual(bare_agent()._hmb_web_rerender_policy_status(project)["reason"], "project_policy_pending")

    def test_copied_sw_dat_cannot_become_another_project_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "resources/agent/Dinoster5/hmb_agent_core.dat"
            destination.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "resources/agent/superwings12/hmb_agent_core.dat", destination)
            with patch.object(common, "ROOT", root), self.assertRaisesRegex(RuntimeError, "project identity"):
                common._load_verified_agent_rule_payload("dinoster5")

    def test_missing_project_never_reads_legacy_root_dat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "resources/agent"
            folder.mkdir(parents=True)
            shutil.copyfile(ROOT / "resources/agent/superwings12/hmb_agent_core.dat", folder / "hmb_agent_core.dat")
            with patch.object(common, "ROOT", root), patch.object(common, "_AGENT_POLICY_FILE", folder / "superwings12/hmb_agent_core.dat"):
                with self.assertRaises(ProjectPolicyPendingError):
                    common._read_agent_policy_envelope()

    def test_readiness_verifies_without_claiming_or_injecting_policy(self):
        session = fresh_session()
        with patch.object(common, "_agent_process_session", session):
            status = bare_agent()._hmb_web_rerender_policy_status("superwings12")
            self.assertTrue(status["ready"])
            self.assertEqual(session._status_for_regression(), ("empty", 0))
            self.assertEqual(session._status_for_regression(project_id="dinoster5"), ("empty", 0))

    def test_unknown_project_stops_before_policy_read(self):
        with patch.object(common, "_read_agent_policy_envelope") as reader:
            with self.assertRaises(ValueError):
                common._load_verified_agent_rule_payload("../../superwings12")
            reader.assert_not_called()

    def test_pending_manual_run_then_sw_keeps_original_prompt(self):
        current = {"project_id": "dinoster5"}
        asset = SimpleNamespace(_hmb_project_identity=lambda: resolve_project(current))
        source = SimpleNamespace(_hmb_connected_source_nodes={"SHOT_ASSET_IN": asset})
        node = bare_agent(source)
        node.parameter_values = {"prompt": "Original authored prompt {{SIGN}}", "SHOT_PROMPT_IN": "Original authored prompt {{SIGN}}"}
        before = dict(node.parameter_values)
        node.parameter_output_values = {"output": "previous output", "agent": {}}
        node._hmb_shot_channel_subscription = lambda: {"enabled": False}
        node._refresh_agent_shot_route = lambda **kwargs: {}
        def topology():
            node._hmb_verified_prompt_source_node = source
            return True
        node._has_canonical_hmb_prompt_connection = topology
        node.get_parameter_value = lambda name: node.parameter_values.get(name)
        node._secure_hmb_outputs = lambda: None
        native_calls = []
        def native():
            native_calls.append(node._hmb_policy_identity["project_id"])
            node.parameter_output_values["output"] = "Completed offline check"
            if False:
                yield None
            return "native-complete"
        node._run_native_agent_once = native
        session = fresh_session()
        with patch.object(common, "_agent_process_session", session), patch.object(common, "_agent_policy_process_provenance_valid", return_value=True), patch.object(agent, "_paired_machine_prompt", return_value=before["prompt"]):
            with self.assertRaisesRegex(RuntimeError, "HMB PROJECT POLICY PENDING"):
                list(node.process())
            self.assertFalse(native_calls)
            self.assertEqual(node.parameter_output_values["output"], agent._HMB_PROJECT_POLICY_PENDING_MESSAGE)
            self.assertEqual(session._status_for_regression(project_id="dinoster5"), ("empty", 0))
            current["project_id"] = "superwings12"
            list(node.process())
            self.assertEqual(native_calls, ["superwings12"])
            self.assertEqual(node.parameter_values, before)


class ProjectSessionIsolation(unittest.TestCase):
    def test_concurrent_initialization_is_once_per_project(self):
        session = fresh_session()
        counts = {name: 0 for name in ("superwings12", "dinoster5", "katuri8")}
        def bootstrap(name):
            def loader():
                counts[name] += 1
                return {"project_id": name, "rules": [name]}
            session.bootstrap_once_authorized(lambda: True, loader, project_id=name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(bootstrap, list(counts) * 8))
        self.assertEqual(set(counts.values()), {1})
        for name in counts:
            self.assertEqual(session.read_ready(project_id=name)["project_id"], name)
        changed = session.read_ready(project_id="dinoster5")
        changed["rules"].append("mutated")
        self.assertEqual(session.read_ready(project_id="dinoster5")["rules"], ["dinoster5"])

    def test_failed_project_cannot_poison_or_reuse_ready_sw(self):
        session = fresh_session()
        session.bootstrap_once_authorized(lambda: True, lambda: {"project_id": "superwings12"})
        called = []
        with self.assertRaises(RuntimeError):
            session.bootstrap_once_authorized(lambda: False, lambda: called.append(True) or {}, project_id="dinoster5")
        with self.assertRaises(RuntimeError):
            session.bootstrap_once_authorized(lambda: True, lambda: called.append(True) or {}, project_id="dinoster5")
        self.assertFalse(called)
        self.assertEqual(session.read_ready()["project_id"], "superwings12")
        self.assertEqual(session._status_for_regression(project_id="katuri8"), ("empty", 0))

    def test_shutdown_wipes_every_buffer_and_disallows_reopen(self):
        session = fresh_session()
        for name in ("superwings12", "dinoster5", "katuri8"):
            session.bootstrap_once_authorized(lambda: True, lambda: {"policy": "PRIVATE"}, project_id=name)
        buffers = [session._payload_bytes] + [cell.payload for cell in session._project_sessions.values()]
        session._expire_for_process_shutdown()
        self.assertTrue(all(not any(buffer) for buffer in buffers))
        for name in ("superwings12", "dinoster5", "katuri8"):
            self.assertEqual(session._status_for_regression(project_id=name), ("closed", 0))
            with self.assertRaises(RuntimeError):
                session.bootstrap_once_authorized(lambda: True, lambda: {}, project_id=name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
