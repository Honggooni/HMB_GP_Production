"""Only destination/filename, byte transport and same-operation recovery; no live service."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest import mock

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
import HMB_Color_LUT_Node_Regression as fixture
import HMBColorLUTLibrary as target
import _hmb_broker_config as config
import _hmb_shot_routing as routing

ORIGIN = "https://broker.test/GripTapeServer"
PROJECTS = [{"id": "superwings12", "name": "슈퍼윙즈12"}, {"id": "katuri8", "name": "까투리8"}]

class ManualLUTRegression(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ColorLUTNodeRegression(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.node, self.root = self.fixture.node, self.fixture.root
        self.cap = {"schema": target.COLOR_LUT_MANUAL_UPLOAD_SCHEMA, "version": 1, "enabled": True,
                    "display_name": "HMB Color LUT", "max_bytes": 1048576,
                    "upload_path": target.COLOR_LUT_MANUAL_UPLOAD_PATH,
                    "status_path": target.COLOR_LUT_MANUAL_UPLOAD_PATH + "/{idempotency_key}",
                    "projects_path": target.COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects"}
        self.bridge = types.SimpleNamespace(server_url=ORIGIN, review_capabilities=lambda: {"color_lut_manual_upload": copy.deepcopy(self.cap)},
                                            _request_json=self.request)
        for patch in [mock.patch.object(config, "load_broker_base_url", return_value=ORIGIN),
                      mock.patch.object(target, "_upload_bridge", return_value=self.bridge),
                      mock.patch.object(target, "_usage_bridge", return_value=self.bridge),
                      mock.patch.object(target, "_upload_receipt_path", side_effect=lambda key: self.root / "receipts" / (key + ".json")),
                      mock.patch.object(routing, "_same_flow_nodes", return_value=("fixture-flow", [self.node])),
                      mock.patch.object(self.node, "_upload_retry_wait", return_value=True)]:
            patch.start(); self.addCleanup(patch.stop)
        self.node._manual_projects, self.node._manual_projects_origin = copy.deepcopy(PROJECTS), ORIGIN
        self.node._queue_source({"path": self.fixture.media("11-12.mp4")}); self.fixture.drain()
        self.choose("superwings12")
        self.export_proof()

    def request(self, method, path, **kwargs):
        self.assertEqual(method, "GET")
        if path == "/api/me": return {"id": "fixture-owner"}
        if path == target.COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects":
            return {"schema": "hmb-color-lut-manual-projects", "version": 1,
                    "projects": [{"project_id": p["id"], "project_name": p["name"]} for p in PROJECTS]}
        raise AssertionError(path)

    def choose(self, identity, **kwargs):
        self.node._command({"id": "choose-" + str(len(self.node._seen_commands)), "action": "select_upload_project",
                             "state": copy.deepcopy(self.node._hmb_color_lut_state), "project_id": identity, **kwargs})
        self.fixture.drain()

    def export_proof(self):
        state = self.node._hmb_color_lut_state
        path = self.root / "graded.mov"; path.write_bytes(b"synthetic graded media fixture")
        result = {"path": str(path), "url": "http://local.test/graded.mov", "source_path": state["source"]["path"], "job_id": "fixture-export"}
        self.node._record_export_proof(copy.deepcopy(state), result, threading.Event()); state["result"] = result

    def ready(self, artifact="source"):
        context = self.node._prepare_upload_context(copy.deepcopy(self.node._hmb_color_lut_state), artifact=artifact)
        self.node._web_upload_context = context; self.node._web_upload = {"enabled": True, "phase": "ready", "reason": "ready"}
        return context

    def ack(self, context):
        return {"schema": "hmb-color-lut-manual-upload-result", "version": 1, "manual": True,
                "source_task_id": None, "channel_uuid": None, "shot_uuid": None, "shot_name": None,
                "display_name": "HMB Color LUT", "source_kind": "HMB Color LUT", "asset_id": "lut-fixture-asset",
                "derived_task_id": "job-" + "d" * 32, "bytes": context["size"], "created": True,
                **{key: context[key] for key in ("project_id", "project_name", "sha256", "file_name")}}

    def upload(self, name="upload"):
        self.node._command({"id": name, "action": "upload_web", "state": copy.deepcopy(self.node._hmb_color_lut_state)})
        self.fixture.drain()

    def test_project_change_keeps_loaded_video_grade_and_result(self):
        before = copy.deepcopy(self.node._hmb_color_lut_state); first = self.ready()
        with mock.patch.object(target, "export_video", side_effect=AssertionError("No re-encode on project selection")):
            self.choose("katuri8"); second = self.ready()
        after = self.node._hmb_color_lut_state
        for key in ("source", "settings", "output", "result"): self.assertEqual(before[key], after[key])
        self.assertNotEqual(first["upload_id"], second["upload_id"])
        self.assertEqual(second["file_name"], "11-12.mp4")
        self.assertEqual(second["project_name"], "까투리8")

    def test_explicit_project_required_and_browser_cannot_authorize_it(self):
        self.choose("")
        self.assertFalse(self.node._upload_projection()["enabled"])
        forged = copy.deepcopy(self.node._hmb_color_lut_state); forged.update(manual_project=PROJECTS[0], project_id="superwings12")
        self.node._apply_ui(forged)
        self.assertEqual(self.node._hmb_color_lut_state["manual_project"], {})
        with self.assertRaises(ValueError): self.node._prepare_upload_context(copy.deepcopy(self.node._hmb_color_lut_state))

    def test_only_destination_does_not_follow_image_asset_project(self):
        before = copy.deepcopy(self.node._hmb_color_lut_state)
        self.node._hmb_follow_image_asset_project({"id": "asset-local-project", "name": "Image project"})
        self.assertEqual(self.node._hmb_color_lut_state, before)
        self.assertEqual(self.node._bound_project["id"], "asset-local-project")

    def test_saved_only_restores_own_destination_after_asset_discovery(self):
        saved = copy.deepcopy(self.node._hmb_color_lut_state)
        restored = target.HMBColorLUTLibrary(name="Restored Only")
        restored._hmb_follow_image_asset_project({"id": "other-asset", "name": "Other"})
        restored._apply_ui(saved, initial_setup=True)
        for key in ("manual_project", "project_id", "source", "settings", "result"):
            self.assertEqual(restored._hmb_color_lut_state[key], saved[key])

    def test_five_bound_slots_keep_project_ownership_and_only_destination(self):
        self.node._hmb_follow_image_asset_project({"id": "asset-local", "name": "Bound project"})
        manual = copy.deepcopy(self.node._hmb_color_lut_state)
        for number in range(1, 6):
            shot = {"channel_uuid": "fixture-channel", "shot_uuid": "fixture-" + str(number), "number": number, "name": "Shot " + str(number)}
            self.node._switch(shot)
            self.assertEqual(self.node._hmb_color_lut_state["project_id"], "asset-local")
            self.choose("katuri8")
            self.assertEqual(self.node._hmb_color_lut_state["project_id"], "asset-local", "Bound project is read-only")
            self.node._switch(target._shot_only()); self.fixture.drain()
            for key in ("project_id", "source", "settings", "result"):
                self.assertEqual(self.node._hmb_color_lut_state[key], manual[key])

    def test_removed_project_disabled_cap_wrong_mount_and_foreign_source_reject(self):
        original = self.bridge._request_json
        self.bridge._request_json = lambda method, path, **kw: ({"schema": "hmb-color-lut-manual-projects", "version": 1, "projects": []}
                                                                if path.endswith("/projects") else original(method, path, **kw))
        with self.assertRaises(ValueError): self.ready()
        self.bridge._request_json = original
        for field, bad in (("enabled", False), ("version", True), ("upload_path", "https://evil.test/upload"), ("status_path", "/wrong"), ("projects_path", "/wrong")):
            cap = copy.deepcopy(self.cap); self.cap[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError): self.ready()
            self.cap = cap
        self.node._hmb_color_lut_state["source"]["shot_uuid"] = "foreign-shot"
        with self.assertRaises(ValueError): self.ready()

    def test_changed_grade_changed_export_and_foreign_context_reject(self):
        self.ready(); self.node._hmb_color_lut_state["settings"].update(enabled=True, exposure=.5)
        self.assertFalse(self.node._upload_projection()["enabled"])
        with self.assertRaises(ValueError): self.ready("export")
        self.export_proof(); self.ready("export")
        Path(self.node._hmb_color_lut_state["result"]["path"]).write_bytes(b"replaced export")
        with self.assertRaises(ValueError): self.ready("export")

    def test_manual_wire_contract_uses_filename_metadata_and_exact_gateway(self):
        context = self.ready(); metadata = self.node._upload_metadata(context)
        self.assertEqual(set(metadata), {"schema", "version", "project_id", "file_name", "settings_sha256", "export_sha256", "export_bytes", "output_format", "workflow_id", "color_lut_node_id"})
        self.assertEqual(metadata["file_name"], "11-12.mp4")
        expected = hashlib.sha256("\n".join(("hmb-color-lut-manual-upload-v1", context["project_id"], context["file_name"], context["sha256"], context["settings_sha256"])).encode()).hexdigest()
        self.assertEqual(context["upload_id"], expected)
        seen = {}
        response = types.SimpleNamespace(__enter__=lambda: None)
        class Response:
            def __enter__(inner): return inner
            def __exit__(inner, *args): return None
        def opened(request, **kwargs):
            seen.update(url=request.full_url, body=b"".join(request.data), headers=dict(request.header_items()))
            return Response()
        context["bridge"]._load_access_token = lambda: "fixture-token"
        context["bridge"]._opener = types.SimpleNamespace(open=opened)
        generator = types.ModuleType("HMBSeedanceGeneration")
        generator._broker_require_exact_response_url = lambda *args: None
        generator._broker_read_json = lambda *args, **kwargs: self.ack(context)
        with mock.patch.dict(sys.modules, {"HMBSeedanceGeneration": generator}):
            self.node._upload_request(context, retrieve=False, cancel=threading.Event())
        self.assertEqual(seen["url"], ORIGIN + target.COLOR_LUT_MANUAL_UPLOAD_PATH)
        self.assertIn(b'filename="color-lut.mp4"', seen["body"])
        self.assertIn(b'"file_name":"11-12.mp4"', seen["body"])
        self.assertNotIn(str(self.root).encode(), seen["body"])
        self.assertEqual(int(seen["headers"]["Content-length"]), len(seen["body"]))

    def test_unknown_upload_retrieves_same_id_and_completed_reopen_never_duplicates(self):
        context = self.ready(); calls = []
        def transport(captured, *, retrieve, cancel):
            calls.append((captured["upload_id"], retrieve))
            if not retrieve: raise TimeoutError("fixture unknown")
            return self.ack(captured)
        with mock.patch.object(self.node, "_upload_request", side_effect=transport):
            self.upload("first")
            self.assertEqual(self.node._web_upload["phase"], "unknown")
            self.upload("recover")
            self.assertEqual(self.node._web_upload["phase"], "complete")
            self.upload("duplicate")
        self.assertEqual(calls, [(context["upload_id"], False), (context["upload_id"], True)])
        self.node._web_upload_context = {}; self.node._web_upload_probe_key = ""; self.node._schedule_upload_probe(); self.fixture.drain()
        self.assertEqual(self.node._web_upload["phase"], "complete")
        self.assertFalse(self.node._upload_projection()["enabled"])

    def test_manual_wrong_ack_never_claims_complete_and_deleted_node_never_sends(self):
        self.ready()
        def wrong(context, **kwargs):
            response = self.ack(context); response["project_id"] = "other"; return response
        with mock.patch.object(self.node, "_upload_request", side_effect=wrong): self.upload()
        self.assertEqual(self.node._web_upload["phase"], "unknown")
        self.node._hmb_node_deleted = True
        with mock.patch.object(self.node, "_upload_request") as request:
            self.upload("deleted"); request.assert_not_called()

    def test_late_success_after_leaving_and_returning_does_not_repaint_current_operation(self):
        context = self.ready()
        def transport(captured, **kwargs):
            self.node._web_upload_epoch += 2
            self.node._web_upload = {"enabled": False, "phase": "unavailable", "reason": "new context"}
            return self.ack(captured)
        with mock.patch.object(self.node, "_upload_request", side_effect=transport): self.upload()
        self.assertEqual(self.node._web_upload["reason"], "new context")
        self.assertEqual(target._read_upload_receipt(context["receipt_id"])["phase"], "complete")

    def test_invalid_broker_settings_do_not_break_existing_view_and_names_fail_before_network(self):
        self.ready()
        with mock.patch.object(config, "load_broker_base_url", side_effect=ValueError("invalid settings")):
            self.assertFalse(self.node._upload_projection()["enabled"])
            self.node._publish()
        for name in ("x\u202ey.mp4", "x\ny.mp4", "x?.mp4", "no-extension"):
            state = copy.deepcopy(self.node._hmb_color_lut_state); state["source"]["path"] = str(self.root / name)
            with self.subTest(name=name), mock.patch.object(self.bridge, "review_capabilities") as request:
                with self.assertRaises(ValueError): self.node._prepare_upload_context(state)
                request.assert_not_called()

    def test_project_command_rejects_foreign_names_mybox_and_malformed_revision(self):
        before = copy.deepcopy(self.node._hmb_color_lut_state["manual_project"])
        for identity in ("my-box", "dinoster5", "../../other", "unknown"):
            self.choose(identity); self.assertEqual(self.node._hmb_color_lut_state["manual_project"], before)
        state = copy.deepcopy(self.node._hmb_color_lut_state); state["revision"] = {"bad": 1}
        self.choose("katuri8", state=state)
        self.assertEqual(self.node._hmb_color_lut_state["manual_project"]["id"], "katuri8")

if __name__ == "__main__": unittest.main(verbosity=2)
