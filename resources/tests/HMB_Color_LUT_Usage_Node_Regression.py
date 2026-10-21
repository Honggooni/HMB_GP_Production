"""Offline real-node usage hooks, synthetic artifacts and fake authenticated HTTP."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_Color_LUT_Node_Regression as node_fixture
from HMB_Color_LUT_Usage_Protocol_Regression import FakeBridge, TransportError
import HMBColorLUTLibrary as target
import _hmb_color_lut_usage as usage


class AuthenticatedBridge(FakeBridge):
    def __init__(self, owner=42, **kwargs):
        super().__init__(**kwargs)
        self.owner = owner

    def _request_json(self, method, path, **kwargs):
        if path == "/api/me":
            self.calls.append((method, path, None, kwargs["timeout"], False))
            return {"id": self.owner}
        return super()._request_json(method, path, **kwargs)


class UsageNodeRegression(unittest.TestCase):
    def setUp(self):
        self.fixture = node_fixture.ColorLUTNodeRegression()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.node, self.root = self.fixture.node, self.fixture.root
        self.bridge = AuthenticatedBridge(prefix="/GripTapeServer")
        self.patches = [
            mock.patch.object(target, "_usage_bridge", return_value=self.bridge),
            mock.patch.object(target, "export_video", side_effect=self.fixture.successful_export),
            mock.patch.object(self.node, "_schedule_upload_probe"),
            mock.patch.object(target, "_upload_receipt_path", side_effect=lambda identity: self.root / "proofs" / (identity + ".json")),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.node._queue_source({"path": self.fixture.media("manual.mov")})
        self.fixture.drain()

    def posts(self, bridge=None):
        return [row[2] for row in (bridge or self.bridge).calls if row[0] == "POST"]

    def export(self, name="export-1", *, drain=True):
        self.node._command({"id": name, "action": "export"})
        self.node._worker.run()
        if drain:
            self.fixture.drain()
        return self.node._hmb_color_lut_state["result"]

    def assert_saved(self):
        state = self.node._hmb_color_lut_state
        self.assertEqual(state["status"]["phase"], "complete")
        self.assertEqual(Path(state["result"]["path"]).read_bytes(), b"graded result")
        return state["result"]["usage_collection"]["local_export"]

    def test_only_success_collects_false_and_zero_once_without_uploading_media(self):
        with mock.patch.object(target, "_verified_export_hash", wraps=target._verified_export_hash) as hashed:
            result = self.export()
        self.assertEqual(hashed.call_count, 1)
        sent = self.posts()[0]
        self.assertFalse(sent["settings"]["enabled"])
        self.assertEqual(sent["settings"]["exposure"], 0)
        self.assertIsNone(sent["source_task_id"])
        self.assertIsNone(sent["upload_idempotency_key"])
        self.assertEqual(sent["export_sha256"], hashlib.sha256(b"graded result").hexdigest())
        self.assertEqual(self.assert_saved(), {"phase": "complete", "reason": "recorded"})
        self.assertFalse(self.node._upload_projection()["enabled"])
        for path in (self.root / "usage-events").glob("*.json"):
            raw = path.read_text(encoding="utf-8")
            stored = json.loads(raw)
            self.assertEqual(set(stored), {"schema", "version", "scope_sha256", "phase", "event", "receipt"})
            for forbidden in (str(self.root), self.bridge.server_url, "access_token", "prompt", "owner_id", "source_path"):
                self.assertNotIn(forbidden, raw)

    def test_only_saved_player_is_published_before_optional_checksum(self):
        original = target._verified_export_hash
        def checked(path, cancel):
            self.assertTrue(self.node.parameter_output_values["video_url"])
            self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "complete")
            self.assertEqual(self.node._hmb_color_lut_state["result"]["usage_collection"]["local_export"]["reason"], "checksum_pending")
            return original(path, cancel)
        with mock.patch.object(target, "_verified_export_hash", side_effect=checked), \
                mock.patch.object(target, "_media_url", wraps=target._media_url) as preview:
            self.export()
        self.assertEqual(preview.call_count, 1)
        self.assertEqual(self.assert_saved()["phase"], "complete")

    def test_only_early_player_does_not_publish_into_replacement_job(self):
        original = self.node._retain_export_result
        calls = []
        def retained(*args, **kwargs):
            current = original(*args, **kwargs)
            calls.append(current)
            if len(calls) == 2:
                self.node._job_id = "newer-fixture-job"
            return current
        with mock.patch.object(self.node, "_retain_export_result", side_effect=retained), \
                mock.patch.object(self.node, "_publish_result_url") as publish:
            self.export()
        publish.assert_not_called()
        self.assertEqual(self.posts(), [])

    def test_bound_export_reuses_one_hash_and_frozen_proof_for_web_stage(self):
        self.fixture.select()
        self.fixture.load()
        with mock.patch.object(self.node, "_upload_graph_context", return_value={"server_url": self.bridge.server_url}), \
                mock.patch.object(target, "_file_digest", side_effect=AssertionError("No second media hash")), \
                mock.patch.object(target, "_verified_export_hash", wraps=target._verified_export_hash) as hashed:
            result = self.export()
        self.assertEqual(hashed.call_count, 1)
        proof = target._read_upload_receipt(result["web_export_proof"])
        local = self.posts()[0]
        self.assertEqual(proof["usage_event"], local)
        context = {"usage_event": proof["usage_event"], "sha256": proof["sha256"],
                   "settings_sha256": local["settings_sha256"], "source_task_id": "job-" + "b" * 32,
                   "upload_id": "c" * 64, "server_url": self.bridge.server_url, "owner_id": "42"}
        self.node._queue_web_usage(context)
        self.fixture.drain()
        self.node._queue_web_usage(context)
        self.fixture.drain()
        self.assertEqual(len(self.posts()), 2)
        self.assertEqual({row["stage"] for row in self.posts()}, {"local_export", "web_upload"})
        self.assertEqual(len({row["export_operation_id"] for row in self.posts()}), 1)
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "complete")

    def test_pending_or_reopened_record_only_looks_up_same_operation(self):
        self.bridge.post_error = TransportError()
        self.bridge.lookup_error = TransportError(503)
        result = self.export()
        sent = self.posts()[0]
        self.assertEqual(self.assert_saved()["phase"], "pending")
        self.bridge.post_error = self.bridge.lookup_error = None
        self.node._queue_usage_event(sent, self.bridge.server_url)
        self.fixture.drain()
        self.node._queue_usage_event(sent, self.bridge.server_url)
        self.fixture.drain()
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.assert_saved()["phase"], "complete")
        lookups = [row[1] for row in self.bridge.calls if row[1].startswith(usage.EVENTS_API + "/")]
        self.assertTrue(all(path == usage.EVENTS_API + "/" + sent["export_operation_id"] + "/local_export" for path in lookups))

    def test_lost_receipt_after_server_success_never_reposts(self):
        original = target._write_usage_record
        def write(identity, value):
            if value["phase"] == "complete":
                raise OSError("fixture local receipt unavailable")
            return original(identity, value)
        with mock.patch.object(target, "_write_usage_record", side_effect=write):
            self.export()
        self.assertEqual(self.assert_saved()["phase"], "pending")
        self.node._queue_usage_event(self.posts()[0], self.bridge.server_url)
        self.fixture.drain()
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.assert_saved()["phase"], "complete")

    def test_offline_capability_hash_failure_and_cancel_do_not_fail_saved_video(self):
        self.bridge.cap["enabled"] = False
        self.export("disabled")
        self.assertEqual(self.assert_saved()["phase"], "not_collected")
        self.assertEqual(self.posts(), [])
        with mock.patch.object(target, "_verified_export_hash", side_effect=OSError("fixture denied")):
            self.export("hash-failed")
        self.assertEqual(self.assert_saved()["reason"], "export_hash_unavailable")
        def cancelled(path, cancel):
            cancel.set()
            raise ValueError("fixture hash cancelled")
        with mock.patch.object(target, "_verified_export_hash", side_effect=cancelled):
            self.export("hash-cancelled")
        self.assertEqual(self.assert_saved()["reason"], "cancelled")
        self.assertEqual(self.posts(), [])

    def test_authentication_is_captured_at_export_and_cross_account_replay_is_blocked(self):
        self.export(drain=False)
        other = AuthenticatedBridge(owner=99, prefix="/GripTapeServer")
        with mock.patch.object(target, "_usage_bridge", return_value=other):
            self.fixture.drain()
            self.assertEqual(len(self.posts()), 1)
            self.assertEqual(self.posts(other), [])
            self.node._queue_usage_event(self.posts()[0], other.server_url)
            self.fixture.drain()
        self.assertEqual(self.posts(other), [])
        self.assertEqual(self.assert_saved()["reason"], "account_identity_mismatch")

    def test_missing_login_at_acceptance_is_not_replaced_by_later_login(self):
        with mock.patch.object(target, "_usage_bridge", return_value=None):
            self.export(drain=False)
        self.fixture.drain()
        self.assertEqual(self.posts(), [])
        self.assertEqual(self.assert_saved()["reason"], "existing_login_required")

    def test_source_settings_and_classification_are_frozen_at_export(self):
        self.fixture.apply(settings={"enabled": True, "precision_version": 2, "exposure": .75})
        self.fixture.drain()
        self.fixture.save_preset("Personal")
        self.export(drain=False)
        self.fixture.apply(settings={"enabled": False, "precision_version": 2, "exposure": -2})
        self.fixture.drain()
        first = self.posts()[0]
        self.assertEqual(first["preset_classification"], "personal")
        self.assertEqual(first["settings"]["exposure"], .75)
        self.assertTrue(first["settings"]["enabled"])
        self.export("custom")
        self.assertEqual(self.posts()[-1]["preset_classification"], "custom")
        self.assertNotEqual(first["export_operation_id"], self.posts()[-1]["export_operation_id"])

    def test_preview_save_delete_hydration_do_not_emit_events_or_hash_media(self):
        with mock.patch.object(target, "_verified_export_hash", side_effect=AssertionError("No media hash")), \
                mock.patch.object(target, "_usage_bridge", side_effect=AssertionError("No login")):
            self.fixture.apply(settings={"enabled": True, "exposure": .5})
            profile = self.fixture.save_preset("Temporary")
            self.fixture.delete_preset(profile)
            cold = target.HMBColorLUTLibrary(name="Cold restored LUT")
            cold._apply_ui(copy.deepcopy(self.node._hmb_color_lut_state), initial_setup=True)
            cold.process()
        self.assertEqual(self.posts(), [])

    def test_all_codecs_keep_independent_operation_identity(self):
        for index, codec in enumerate(("hevc10", "prores", "ffv1")):
            self.fixture.apply(output={"codec": codec}, settings={"precision_version": 2, "enabled": True, "contrast": index / 4})
            self.fixture.drain()
            self.export("codec-" + codec)
        self.assertEqual([row["codec"] for row in self.posts()], ["hevc10", "prores", "ffv1"])
        self.assertEqual(len({row["export_operation_id"] for row in self.posts()}), 3)

    def test_changed_file_and_chunk_bound_are_checked_without_modifying_output(self):
        path = self.root / "identity.mov"
        path.write_bytes(b"x" * (2 * 1024 * 1024 + 13))
        original = target.Path.open
        sizes = []
        class Stream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, size):
                sizes.append(size)
                block = self.stream.read(size)
                if len(sizes) == 1:
                    path.write_bytes(b"changed by fixture")
                return block
        def opened(item, *args, **kwargs):
            stream = original(item, *args, **kwargs)
            return Stream(stream) if item == path and args == ("rb",) else stream
        with mock.patch.object(target.Path, "open", opened):
            with self.assertRaises(ValueError):
                target._verified_export_hash(path, threading.Event())
        self.assertTrue(sizes)
        self.assertLessEqual(max(sizes), 1024 * 1024)
        self.assertEqual(path.read_bytes(), b"changed by fixture")

    def test_deleted_node_never_starts_statistics_http(self):
        self.export(drain=False)
        self.node._hmb_node_deleted = True
        self.fixture.drain()
        self.assertEqual(self.bridge.calls, [])

    def test_statistics_helper_failure_keeps_normal_shot_export_proof(self):
        self.fixture.select()
        self.fixture.load()
        with mock.patch.object(self.node, "_upload_graph_context", return_value={"server_url": self.bridge.server_url}), \
                mock.patch.dict(sys.modules, {"_hmb_color_lut_usage": None}), \
                mock.patch.object(target, "_verified_export_hash", wraps=target._verified_export_hash) as hashed:
            result = self.export()
        self.assertEqual(hashed.call_count, 1)
        self.assertIn("web_export_proof", result)
        self.assertEqual(self.assert_saved()["reason"], "statistics_metadata_unavailable")
        self.assertEqual(self.posts(), [])

    def test_unflushed_personal_selection_captures_exact_id_name_and_settings(self):
        self.fixture.apply(settings={"precision_version": 2, "enabled": True, "exposure": .25})
        self.fixture.drain()
        first = self.fixture.save_preset("A", "save-A")
        self.fixture.apply(settings={"precision_version": 2, "enabled": True, "exposure": .5})
        second = self.fixture.save_preset("B", "save-B")
        self.fixture.apply(preset_id=first["id"], preset_name="A", settings=first["settings"])
        authored = {**copy.deepcopy(self.node._hmb_color_lut_state), "preset_id": second["id"],
                    "preset_name": "B", "settings": second["settings"]}
        self.node._command({"id": "unflushed-B", "action": "export", "state": authored})
        self.node._worker.run()
        self.fixture.drain()
        self.assertEqual(self.posts()[0]["preset_classification"], "personal")
        self.assertEqual(self.posts()[0]["settings"]["exposure"], .5)
        self.assertEqual(self.node._hmb_color_lut_state["preset_id"], second["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
