"""Offline shot provenance, export proof and exactly-once web publication checks."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Color_LUT_Node_Regression import ColorLUTNodeRegression as Fixture, ControlledThread, SHOT_A, SHOT_B
import HMBColorLUTLibrary as target
import _hmb_shot_routing as routing
import _hmb_review as review
from _hmb_project import resolve_project


class ColorLUTUploadRegression(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.node, self.root = self.fixture.node, self.fixture.root
        self.fixture.select()
        self.project = resolve_project("superwings12", default_legacy=False)
        self.asset = types.SimpleNamespace(name="Assets", _hmb_shot_routing_catalog=lambda: {
            "channel_uuid": SHOT_A["channel_uuid"], "shots": [{**SHOT_A, "name": "e201s001c001__"}, SHOT_B]},
            _hmb_project_identity=lambda: copy.deepcopy(self.project))
        self.source = {**self.fixture.source(), "schema": "hmb-generated-video-source", "version": 1,
                       "task_id": "job-offline-lut", "generation_id": "job-offline-lut", "result_revision": 1,
                       "source_node_instance_id": "original-generator-instance"}
        self.generator = types.SimpleNamespace(name="Generator", _hmb_generated_video_source_snapshot=lambda: copy.deepcopy(self.source))
        self.generator_sub = types.SimpleNamespace(kind="seedance", enabled=True, channel_uuid=SHOT_A["channel_uuid"], shot_uuid=SHOT_A["shot_uuid"])
        self.edge = types.SimpleNamespace(source_node_name="Generator", source_parameter_name="HMB_GENERATED_VIDEO_SOURCE", target_parameter_name=target.SOURCE)
        self.bridge = types.SimpleNamespace(server_url="https://broker.test/gateway", review_capabilities=lambda: {
            "color_lut_upload": {"schema": target.COLOR_LUT_UPLOAD_SCHEMA, "version": 1, "enabled": True, "max_bytes": 1048576,
                                 "display_name": "HMB Color LUT", "upload_path": "/api/v1/reviews/tasks/{source_task_id}/color-lut"}},
            _request_json=lambda method, path, **_k: {"id": "owner-one"} if path == "/api/me" else {
                "schema": target.COLOR_LUT_UPLOAD_SCHEMA, "version": 1, "enabled": True, "eligible": True,
                "source_task_id": self.source["task_id"], "source_revision": "a" * 64,
                "source_sha256": "b" * 64, "max_bytes": 1048576, "upload_path": "/api/v1/reviews/tasks/" + self.source["task_id"] + "/color-lut",
                **self.project, "display_name": "HMB Color LUT", "shot": {**SHOT_A, "name": "e201s001c001__", "source_node_instance_id": self.source["source_node_instance_id"]}})
        self.patches = [
            mock.patch.object(target, "_upload_receipt_path", side_effect=lambda key: self.root / "receipts" / (key + ".json")),
            mock.patch.object(target, "_upload_bridge", return_value=self.bridge),
            mock.patch.object(target.HMBColorLUTLibrary, "_upload_retry_wait", return_value=True),
            mock.patch.object(routing, "_same_flow_nodes", return_value=("private-flow", [self.node, self.asset, self.generator])),
            mock.patch.object(routing, "_incoming_connections", return_value=[self.edge]),
            mock.patch.object(routing, "_subscription_for", side_effect=lambda node: types.SimpleNamespace(kind="image_asset") if node is self.asset else self.generator_sub if node is self.generator else None),
            mock.patch.object(review, "task_origin", return_value=self.bridge.server_url),
            mock.patch.object(review, "task_project", return_value=self.project),
        ]
        for patch in self.patches:
            patch.start(); self.addCleanup(patch.stop)
        self.node._hmb_color_lut_state["source"] = copy.deepcopy(self.source)
        path = self.root / "graded.mov"
        path.write_bytes(b"offline-graded-video")
        result = {"path": str(path), "source_path": self.source["path"], "job_id": "local-export-1", "settings": copy.deepcopy(self.node._hmb_color_lut_state["settings"])}
        self.node._record_export_proof(copy.deepcopy(self.node._hmb_color_lut_state), result, threading.Event())
        self.node._hmb_color_lut_state["result"] = result

    def ready(self):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        context = self.node._prepare_upload_context(state)
        self.node._web_upload_context = context
        self.node._web_upload = {"enabled": True, "phase": "ready", "reason": "ready"}
        return context

    def acknowledgement(self, context):
        return {"schema": "hmb-color-lut-upload-result", "version": 1, "asset_id": "asset-offline-lut", "derived_task_id": "local-color-lut-offline",
                "display_name": "HMB Color LUT", "source_kind": "HMB Color LUT", "bytes": context["size"], "created": True,
                **{key: context[key] for key in
                ("source_task_id", "project_id", "project_name", "channel_uuid", "shot_uuid", "sha256", "shot_name")}}

    def mounted_responses(self, prefix):
        """The server's broker_path mounts advertised URLs, as well as HTTP."""
        capability = copy.deepcopy(self.bridge.review_capabilities())
        capability["color_lut_upload"]["upload_path"] = prefix + "/api/v1/reviews/tasks/{source_task_id}/color-lut"
        original = self.bridge._request_json
        def request(method, path, **kwargs):
            result = copy.deepcopy(original(method, path, **kwargs))
            if "upload_path" in result:
                result["upload_path"] = prefix + "/api/v1/reviews/tasks/" + self.source["task_id"] + "/color-lut"
            return result
        self.bridge.review_capabilities = lambda: copy.deepcopy(capability)
        self.bridge._request_json = request

    def test_advertised_paths_accept_only_fixed_or_exact_gateway_mount(self):
        expected = "/api/v1/reviews/tasks/{source_task_id}/color-lut"
        for server in ("https://broker.test", "https://broker.test/gateway", "https://broker.test/Company/Gateway/"):
            prefix = urlsplit(server).path.rstrip("/")
            for accepted in {expected, prefix + expected}:
                self.assertTrue(target._advertised_api_path_matches(accepted, expected, server))
            for bad in (None, 1, {}, [], "https://broker.test" + prefix + expected,
                        "https://other.test" + expected, "//other.test" + expected,
                        "/other" + expected, "/gateway2" + expected, prefix + prefix + expected if prefix else "//" + expected,
                        expected + "?token=fixture", expected + "#fragment", expected + "/",
                        "/gateway/../gateway" + expected, "/%67ateway" + expected,
                        expected.replace("/tasks/", "/tasks//"), expected.replace("/api/", "/API/")):
                with self.subTest(server=server, path=bad):
                    self.assertFalse(target._advertised_api_path_matches(bad, expected, server))
        self.assertFalse(target._advertised_api_path_matches(expected, expected, "https://user:fixture@broker.test/gateway"))

    def test_bare_and_mounted_server_responses_prepare_same_shot(self):
        bare = self.ready()
        prefix = urlsplit(self.bridge.server_url).path
        self.mounted_responses(prefix)
        mounted = self.ready()
        for key in ("source_task_id", "project_id", "shot_name", "source_revision", "upload_id", "receipt_id"):
            self.assertEqual(mounted[key], bare[key])

    def test_untrusted_capability_and_eligibility_paths_block_upload(self):
        expected_cap = "/api/v1/reviews/tasks/{source_task_id}/color-lut"
        expected_item = "/api/v1/reviews/tasks/" + self.source["task_id"] + "/color-lut"
        cap = copy.deepcopy(self.bridge.review_capabilities())
        request = self.bridge._request_json
        for prefix, suffix in (("/other", ""), ("/gateway/gateway", ""), ("https://evil.test", ""),
                               ("https://broker.test/gateway", ""), ("/gateway", "?extra=1"), ("/gateway", "#fragment")):
            changed = copy.deepcopy(cap)
            changed["color_lut_upload"]["upload_path"] = prefix + expected_cap + suffix
            with self.subTest(stage="capability", prefix=prefix, suffix=suffix), \
                 mock.patch.object(self.bridge, "review_capabilities", return_value=changed):
                with self.assertRaises(ValueError):
                    self.ready()
            def bad_eligibility(method, path, **kwargs):
                result = copy.deepcopy(request(method, path, **kwargs))
                if "upload_path" in result:
                    result["upload_path"] = prefix + expected_item + suffix
                return result
            with self.subTest(stage="eligibility", prefix=prefix, suffix=suffix), \
                 mock.patch.object(self.bridge, "_request_json", side_effect=bad_eligibility):
                with self.assertRaises(ValueError):
                    self.ready()

    def test_registered_shot_uses_asset_library_name_not_task_title(self):
        context = self.ready()
        self.assertEqual(context["shot_name"], "e201s001c001__")
        self.assertEqual(context["source_task_id"], "job-offline-lut")
        self.assertTrue(self.node._upload_projection()["enabled"])

    def test_only_loader_removed_edges_duplicate_owner_and_other_project_block(self):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        with mock.patch.object(routing, "_incoming_connections", return_value=[]):
            with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        self.generator_sub.enabled = False
        with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        self.generator_sub.enabled = True
        with mock.patch.object(routing, "_same_flow_nodes", return_value=("private-flow", [self.node, self.asset, self.generator, self.asset])):
            with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        with mock.patch.object(review, "task_project", return_value={"project_id": "other"}):
            with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        self.node._hmb_color_lut_state["shot"] = target._shot_only()
        self.assertFalse(self.node._upload_projection()["enabled"])

    def test_foreign_source_instance_forged_result_and_changed_file_block(self):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state["source"]["source_node_instance_id"] = "foreign"
        with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state["result"]["path"] = str(self.root / "unrelated.mov")
        with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
        Path(self.node._hmb_color_lut_state["result"]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError): self.ready()

    def test_settings_change_disables_immediately_and_old_grade_never_uploads(self):
        self.ready()
        self.node._hmb_color_lut_state["settings"]["enabled"] = True
        self.node._hmb_color_lut_state["settings"]["exposure"] = .5
        self.assertFalse(self.node._upload_projection()["enabled"])
        with mock.patch.object(self.node, "_upload_request") as request:
            self.node._command({"id": "stale", "action": "upload_web", "state": copy.deepcopy(self.node._hmb_color_lut_state)})
            request.assert_not_called()

    def test_capability_absent_does_not_upload_and_button_stays_disabled(self):
        self.bridge.review_capabilities = lambda: {}
        self.node._schedule_upload_probe(); self.fixture.drain()
        self.assertFalse(self.node._upload_projection()["enabled"])
        self.assertIn("서버 업데이트", self.node._upload_projection()["reason"])

    def test_server_readiness_recovers_in_one_background_worker_without_rehashing(self):
        ready = self.bridge.review_capabilities
        self.bridge.review_capabilities = lambda: {}
        def online(_delay):
            self.bridge.review_capabilities = ready
            return False
        original = target._file_digest
        with mock.patch.object(self.node, "_upload_retry_wait", side_effect=online) as wait, \
             mock.patch.object(target, "_file_digest", wraps=original) as hashed:
            self.node._schedule_upload_probe()
            self.node._schedule_upload_probe()
            self.assertEqual(len(ControlledThread.pending), 1)
            self.fixture.drain()
            self.assertEqual(wait.call_count, 1)
            self.assertEqual(hashed.call_count, 1)
            self.assertTrue(self.node._upload_projection()["enabled"])

    def test_duplicate_click_and_completed_reopen_never_submit_twice(self):
        self.ready()
        with mock.patch.object(self.node, "_upload_request", side_effect=lambda context, **_kw: self.acknowledgement(context)) as request:
            state = copy.deepcopy(self.node._hmb_color_lut_state)
            self.node._command({"id": "click-one", "action": "upload_web", "state": state})
            self.node._command({"id": "click-two", "action": "upload_web", "state": state})
            self.fixture.drain()
            self.assertEqual(request.call_count, 1)
            self.assertFalse(self.node._upload_projection()["enabled"])
            self.node._web_upload_probe_key = ""
            self.node._web_upload_context = {}
            self.node._schedule_upload_probe(); self.fixture.drain()
            self.assertEqual(self.node._web_upload["phase"], "complete")
            self.assertFalse(self.node._upload_projection()["enabled"])

    def test_uncertain_upload_only_retrieves_same_identity_after_reopen(self):
        self.ready()
        with mock.patch.object(self.node, "_upload_request", side_effect=TimeoutError("offline fixture")) as request:
            self.node._command({"id": "uncertain", "action": "upload_web", "state": copy.deepcopy(self.node._hmb_color_lut_state)})
            self.fixture.drain()
            self.assertFalse(request.call_args.kwargs["retrieve"])
        self.assertEqual(self.node._web_upload["phase"], "unknown")
        with mock.patch.object(self.node, "_upload_request", side_effect=lambda context, **_kw: self.acknowledgement(context)) as request:
            self.node._command({"id": "retrieve-same", "action": "upload_web", "state": copy.deepcopy(self.node._hmb_color_lut_state)})
            self.fixture.drain()
            self.assertTrue(request.call_args.kwargs["retrieve"])
            self.assertEqual(request.call_count, 1)

    def test_confirmed_absent_allows_only_next_click_retry_with_frozen_metadata(self):
        self.ready()
        original_node_id = self.node._web_node_id
        def click(identity):
            self.node._command({"id": identity, "action": "upload_web", "state": copy.deepcopy(self.node._hmb_color_lut_state)})
            self.fixture.drain()
        with mock.patch.object(self.node, "_upload_request", side_effect=TimeoutError()):
            click("unknown-first")
        self.node._web_node_id = "c" * 32  # Save-copy/reopen never changes frozen retry metadata.
        class Absent(Exception):
            status_code = 404
        with mock.patch.object(self.node, "_upload_request", side_effect=Absent()) as request:
            click("check-existing")
            self.assertTrue(request.call_args.kwargs["retrieve"])
        self.assertEqual(self.node._web_upload["phase"], "ready")
        with mock.patch.object(self.node, "_upload_request", side_effect=lambda context, **_kw: self.acknowledgement(context)) as request:
            click("explicit-retry")
            self.assertFalse(request.call_args.kwargs["retrieve"])
            self.assertEqual(request.call_args.args[0]["frozen_metadata"]["color_lut_node_id"], original_node_id)
            self.assertEqual(request.call_count, 1)

    def test_delayed_command_and_delete_never_publish_other_shot(self):
        self.ready()
        old = copy.deepcopy(self.node._hmb_color_lut_state)
        self.node._hmb_color_lut_state["shot"] = copy.deepcopy(SHOT_B)
        with mock.patch.object(self.node, "_upload_request") as request:
            self.node._command({"id": "late", "action": "upload_web", "state": old})
            self.fixture.drain(); request.assert_not_called()
        self.node._hmb_color_lut_state = old
        self.ready()
        with mock.patch.object(self.node, "_upload_request") as request:
            self.node._command({"id": "deleted", "action": "upload_web", "state": old})
            self.node.after_node_deleted(); self.fixture.drain(); request.assert_not_called()

    def test_publish_and_slider_invalidation_do_not_hash_probe_query_or_compile(self):
        self.ready()
        with mock.patch.object(self.node, "_upload_graph_context", side_effect=AssertionError("UI graph scan")), \
             mock.patch.object(target, "_file_digest", side_effect=AssertionError("UI file hash")), \
             mock.patch.object(target, "_upload_bridge", side_effect=AssertionError("UI network")):
            for step in range(100):
                self.node._hmb_color_lut_state["settings"]["exposure"] = step / 40
                self.node._publish()
            self.assertFalse(self.node._upload_projection()["enabled"])

    def test_wire_contract_streams_file_without_paths_names_or_owner_overrides(self):
        self.mounted_responses(urlsplit(self.bridge.server_url).path)
        context = self.ready()
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
        def send(request, **_kwargs):
            captured["request"] = request
            captured["body"] = b"".join(request.data)
            return Response()
        self.bridge._load_access_token = lambda: "offline-token"
        self.bridge._opener = types.SimpleNamespace(open=send)
        fake_seedance = types.ModuleType("HMBSeedanceGeneration")
        fake_seedance._broker_require_exact_response_url = lambda *_args: None
        fake_seedance._broker_read_json = lambda *_args, **_kwargs: self.acknowledgement(context)
        with mock.patch.dict(sys.modules, {"HMBSeedanceGeneration": fake_seedance}):
            self.node._upload_request(context, retrieve=False, cancel=threading.Event())
        request, body = captured["request"], captured["body"]
        self.assertEqual(request.full_url, self.bridge.server_url + "/api/v1/reviews/tasks/" + self.source["task_id"] + "/color-lut")
        self.assertEqual(int(request.get_header("Content-length")), len(body))
        self.assertEqual(request.get_header("Idempotency-key"), context["upload_id"])
        metadata = json.loads(body.split(b"\r\n\r\n", 1)[1].split(b"\r\n--", 1)[0])
        self.assertEqual(set(metadata), {"schema", "version", "source_task_id", "source_revision", "channel_uuid", "shot_uuid", "workflow_id", "generator_node_id", "color_lut_node_id", "export_sha256", "export_bytes", "output_format", "settings_sha256"})
        self.assertNotIn(str(self.root).encode(), body)
        self.assertIn(b'filename="color-lut.mov"', body)
        self.assertIn(b"Content-Type: video/quicktime", body)
        self.assertIn(b"offline-graded-video", body)
        expected = __import__("hashlib").sha256("\n".join(("hmb-color-lut-upload-v1", context["source_task_id"], context["sha256"], context["settings_sha256"], context["shot_uuid"])).encode()).hexdigest()
        self.assertEqual(context["upload_id"], expected)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ColorLUTUploadRegression))
    raise SystemExit(not result.wasSuccessful())
