"""Readiness fences and retry leases, with no app/files/network/Run calls.

Uses the installed SDK to import the actual adapter, then exercises the real
projection/sync/command methods on bounded in-memory node/source stand-ins.
Full retained graph transport remains covered by the live-sync host fixture.
"""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import HMBImageBash as product


class ReadinessRegression(unittest.TestCase):
    def setUp(self):
        self.source = SimpleNamespace(name="Assets")
        self.context = {"schema": product.CONTEXT_SCHEMA, "workspace_id": "workspace", "revision": 4,
                        "ready": True, "records": [{"url": "/source-a", "source_uid": "a"}]}
        self.project = {"value": "retained-render", "meta": {"authored": {"zero": 0, "off": False},
            "hmb_image_bash": {"workspace_id": "workspace", "workspace_revision": 4,
                               "channel_uuid": "channel", "node_instance_uuid": "bash-instance", "prepared_source_hashes": {}}}}
        self.values = {"image_bash_context": self.context, "input_images": ["/source-a"], "bash_image": self.project}
        self.node = SimpleNamespace(metadata={"hmb_image_bash_workspace_id": "workspace",
                                             "hmb_image_bash_channel_uuid": "channel"},
            _hmb_prepare_phase="ready", _hmb_prepare_error="", _hmb_syncing=False, _initializing=False,
            _hmb_inputs_unready=False, _hmb_last_output={"workspace_id": "workspace", "path": "retained.png"},
            _remote_source_instance=lambda node: "source-instance" if node is self.source else "bash-instance",
            get_parameter_value=lambda name: self.values[name], _clear_output=mock.Mock(),
            _set_project=mock.Mock(), _status=mock.Mock(), _publish_header=mock.Mock(),
            _source_hashes=mock.Mock(side_effect=AssertionError("Projection must not read rasters")))
        self.catalog = {"workspaces": [{"workspace_id": "workspace", "revision": 4, "count": 1}]}

    def preparation(self):
        return product.HMBImageBash._editor_preparation(self.node, self.context,
            [(self.source, self.catalog)], self.source)

    def test_ready_requires_current_scene_scope_and_image_pair(self):
        ready = self.preparation()
        self.assertTrue(ready["ready"]); self.assertEqual(ready["phase"], "ready")
        self.assertEqual((ready["requested_count"], ready["prepared_count"]), (1, 1))
        self.values["input_images"] = ["/old-source"]
        self.assertFalse(self.preparation()["ready"])
        self.node._source_hashes.assert_not_called()

    def test_pending_retained_records_never_claim_latest_count_or_readiness(self):
        self.context.update(ready=False, revision=5, requested_count=3, preparation_phase="preparing")
        self.catalog["workspaces"][0].update(revision=5, count=3)
        ready = self.preparation()
        self.assertFalse(ready["ready"]); self.assertEqual(ready["phase"], "preparing")
        self.assertEqual((ready["requested_count"], ready["prepared_count"]), (3, 0))
        self.assertEqual(ready["workspace_revision"], 5)

    def test_pending_and_source_error_preserve_authored_scene_and_completed_output(self):
        original = deepcopy(self.project)
        for phase in ("preparing", "error"):
            with self.subTest(phase=phase):
                self.context.update(ready=False, preparation_phase=phase, error="source unavailable")
                product.HMBImageBash._sync_metadata_with_input_images(self.node)
                self.assertEqual(self.project, original)
                self.node._clear_output.assert_not_called(); self.node._set_project.assert_not_called()
                self.assertTrue(self.node._hmb_inputs_unready)
                self.assertEqual(self.node._hmb_prepare_phase, phase)

    def test_failed_revision_does_not_enable_editor(self):
        self.context.update(ready=False, preparation_phase="error", error="Source disappeared")
        ready = self.preparation()
        self.assertEqual(ready["phase"], "error"); self.assertEqual(ready["error"], "Source disappeared")
        self.assertFalse(ready["ready"])

    def test_catalog_ahead_of_ready_pair_is_still_preparing(self):
        self.catalog["workspaces"][0].update(revision=5, count=2)
        ready = self.preparation()
        self.assertEqual(ready["workspace_revision"], 5)
        self.assertFalse(ready["ready"])

    def test_same_revision_count_mismatch_is_not_ready(self):
        self.catalog["workspaces"][0]["count"] = 2
        self.assertFalse(self.preparation()["ready"])

    def test_malformed_scene_reports_error_instead_of_retaining_old_ready_projection(self):
        self.values["bash_image"] = {"meta": None}
        ready = self.preparation()
        self.assertFalse(ready["ready"]); self.assertEqual(ready["phase"], "error")
        self.assertIn("장면 정보", ready["error"])

    def test_stale_scene_instance_and_revision_are_not_ready(self):
        hmb = self.project["meta"]["hmb_image_bash"]
        for field, bad in (("workspace_revision", 3), ("node_instance_uuid", "old-instance"),
                           ("workspace_id", "old-workspace"), ("channel_uuid", "old-channel")):
            saved = hmb[field]; hmb[field] = bad
            with self.subTest(field=field): self.assertFalse(self.preparation()["ready"])
            hmb[field] = saved

    def test_blank_disconnected_canvas_is_openable(self):
        self.node.metadata = {}; self.context.clear()
        ready = product.HMBImageBash._editor_preparation(self.node, {}, [], None)
        self.assertTrue(ready["ready"]); self.assertEqual(ready["phase"], "idle")
        self.assertIsNone(ready["requested_count"])
        self.node._source_hashes.assert_not_called()

    def test_legacy_pending_context_uses_catalog_count_without_invented_progress(self):
        self.context.update(ready=False)
        self.catalog["workspaces"][0]["count"] = 5
        ready = self.preparation()
        self.assertEqual((ready["phase"], ready["requested_count"], ready["prepared_count"]), ("preparing", 5, 0))
        self.catalog = {}
        self.assertIsNone(self.preparation()["requested_count"])

    def test_retry_rechecks_lease_and_calls_only_scoped_revalidation(self):
        self.source._hmb_retry_image_bash_inputs = mock.Mock()
        self.node._remote_sources = lambda: [(self.source, self.catalog)]
        self.node._remote_bound_source = lambda candidates: self.source
        self.node._sync_metadata_with_input_images = mock.Mock()
        self.node.state = "unresolved"
        request = {"operation": "retry_inputs", "source_node_name": "Assets", "workspace_id": "workspace",
                   "source_instance_id": "source-instance"}
        product.HMBImageBash._header_command(self.node, {"hmb_image_bash_command": request})
        self.source._hmb_retry_image_bash_inputs.assert_called_once_with(self.node, "workspace")
        self.node._sync_metadata_with_input_images.assert_called_once()
        self.source._hmb_retry_image_bash_inputs.reset_mock()
        product.HMBImageBash._header_command(self.node, {"hmb_image_bash_command": {**request, "source_instance_id": "old-instance"}})
        self.source._hmb_retry_image_bash_inputs.assert_not_called()
        self.node._clear_output.assert_not_called(); self.node._set_project.assert_not_called()


class SavedEditorLeaseRegression(unittest.TestCase):
    def setUp(self):
        self.records = [{"url": "/a.png", "source_uid": "a"}]
        self.scope = {"workspace_id": "workspace", "workspace_revision": 4,
                      "channel_uuid": "channel", "node_instance_uuid": "new-live-instance"}
        self.project = {"value": "verified-exact-png", "meta": {"created_at": "commit", "viewport": {"x": 7},
            "konva_json": {"images": [{"id": "brush", "type": "brush", "lines": [0, False, 12]}]},
            "hmb_image_bash": {**self.scope, "node_instance_uuid": "saved-instance",
                "source_bindings": [{"source_uid": "a", "source_id": "image-a", "url": "/a.png"}],
                "prepared_source_hashes": {"input:image-a": {"sha256": "verified-source"}},
                "apply": {"schema": product.RECEIPT_SCHEMA, "editor_commit": "commit",
                          "scene_sha256": "1"*64, "png_sha256": "2"*64,"rgba_sha256":"3"*64,
                          "width":1920,"height":1080,"source_hashes":{},"png_base64":"cG5n", "output_path": "/saved.png"}}}}
        self.source = SimpleNamespace(name="Assets")
        self.catalog = {"workspaces": [{"workspace_id": "workspace", "revision": 4, "count": 1}]}
        self.context = {"schema": product.CONTEXT_SCHEMA, "ready": True, "workspace_id": "workspace", "revision": 4}
        self.node = SimpleNamespace(name="Bash", _hmb_node_deleted=False, _hmb_prepare_phase="idle",
            _hmb_prepare_error="", _hmb_inputs_unready=True,
            metadata={"hmb_image_bash_workspace_id": "workspace"},
            _remote_sources=lambda: [(self.source, self.catalog)], _remote_bound_source=lambda rows: self.source,
            _apply_scope=lambda: dict(self.scope), get_parameter_value=lambda name: self.context,
            _canvas=lambda:{"width":1920,"height":1080,"background_color":"#ffffff","workspace_id":"workspace"},
            _remote_source_instance=lambda node:"new-live-instance" if node is self.node else "source-instance",
            _validate_apply_source_bindings=product.HMBImageBash._validate_apply_source_bindings,
            _set_project=mock.Mock(), _publish_header=mock.Mock(), _status=mock.Mock())
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        self.registered = mock.patch.object(product, "_hmb_is_registered_node", return_value=True)
        self.manager = mock.patch.object(GriptapeNodes, "NodeManager", return_value=SimpleNamespace(get_node_by_name=lambda name:self.node))
        self.registered.start(); self.manager.start(); self.addCleanup(self.registered.stop); self.addCleanup(self.manager.stop)

    def adopt(self):
        return product.HMBImageBash._adopt_verified_saved_editor_scope(self.node, self.project, self.records)

    def test_verified_saved_scope_renews_only_transient_lease(self):
        original = deepcopy(self.project)
        self.assertTrue(self.adopt())
        updated = self.node._set_project.call_args.args[0]
        expected = deepcopy(original); expected["meta"]["hmb_image_bash"]["node_instance_uuid"] = "new-live-instance"
        self.assertEqual(updated, expected); self.assertEqual(self.project, original)
        self.assertEqual(self.node._hmb_prepare_phase, "ready"); self.assertFalse(self.node._hmb_inputs_unready)
        self.node._publish_header.assert_called_once()

    def test_changed_workspace_channel_revision_or_sources_never_rebind(self):
        for field,value in (("workspace_id","different"),("channel_uuid","different"),("workspace_revision",3)):
            with self.subTest(field=field):
                before=deepcopy(self.project); self.project["meta"]["hmb_image_bash"][field]=value
                self.assertFalse(self.adopt()); self.node._set_project.assert_not_called()
                self.project=before
        self.project["meta"]["hmb_image_bash"]["source_bindings"][0]["source_uid"]="changed"
        self.assertFalse(self.adopt()); self.node._set_project.assert_not_called()

    def test_no_current_registered_object_or_actual_source_edges_never_rebind(self):
        self.node._remote_bound_source=lambda rows:None
        self.assertFalse(self.adopt()); self.node._set_project.assert_not_called()
        self.node._remote_bound_source=lambda rows:self.source
        with mock.patch.object(product,"_hmb_is_registered_node",return_value=False):self.assertFalse(self.adopt())
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        with mock.patch.object(GriptapeNodes,"NodeManager",return_value=SimpleNamespace(get_node_by_name=lambda name:object())):
            self.assertFalse(self.adopt())
        self.node._set_project.assert_not_called()

    def test_pending_context_or_changed_catalog_never_rebind(self):
        self.context["ready"]=False;self.assertFalse(self.adopt());self.context["ready"]=True
        self.catalog["workspaces"][0]["revision"]=5;self.assertFalse(self.adopt())
        self.catalog["workspaces"][0].update(revision=4,count=2);self.assertFalse(self.adopt())
        self.node._set_project.assert_not_called();self.assertEqual(self.node._hmb_prepare_phase,"idle")

    def test_non_retained_receipt_and_stale_live_apply_remain_rejected(self):
        self.project["meta"]["created_at"]="different-commit"
        self.assertFalse(self.adopt());self.node._set_project.assert_not_called()
        with self.assertRaises(ValueError):
            product.HMBImageBash._validate_apply_source_bindings(self.project,self.records,expected_scope=self.scope)

    def test_failed_receipt_or_changed_saved_png_cannot_reach_lease_adoption(self):
        # This small fake explicitly exercises the unchanged synchronous
        # fallback; the real queued SDK path has its own Host regression.
        self.node._queue_cold_restore=lambda *args:False
        self.node._adopt_verified_saved_editor_scope=mock.Mock()
        self.node._verify_apply=mock.Mock(side_effect=ValueError("invalid retained receipt"))
        with self.assertRaises(ValueError):product.HMBImageBash._restore_saved_output.__wrapped__(self.node,self.project,self.records)
        self.node._adopt_verified_saved_editor_scope.assert_not_called()
        self.node._verify_apply=mock.Mock(return_value=(b"valid",{"png_sha256":"expected"}))
        with mock.patch.object(product,"File",return_value=SimpleNamespace(read_bytes=lambda:b"changed")),mock.patch.object(product,"validate_png_bytes",return_value={"png_sha256":"changed"}):
            product.HMBImageBash._restore_saved_output.__wrapped__(self.node,self.project,self.records)
        self.node._adopt_verified_saved_editor_scope.assert_not_called();self.node._set_project.assert_not_called()
        self.assertEqual(self.node._hmb_prepare_phase,"idle")

    def test_initial_saved_readiness_queues_verification_once_without_reading_pixels(self):
        self.node._records=lambda:self.records
        self.node.get_parameter_value=lambda name:self.project
        self.node._hmb_apply_epoch=3
        self.node._schedule_host_callback=mock.Mock(return_value=True)
        before=deepcopy(self.project)
        with mock.patch.object(product,"scene_fingerprint",return_value="1"*64):
            product.HMBImageBash._queue_saved_editor_readiness(self.node,self.context,[(self.source,self.catalog)],self.source)
        self.assertEqual(self.node._hmb_prepare_phase,"preparing");self.assertTrue(self.node._hmb_restore_pending)
        self.node._schedule_host_callback.assert_called_once();self.node._set_project.assert_not_called()
        self.assertEqual(self.project,before)
        product.HMBImageBash._queue_saved_editor_readiness(self.node,self.context,[(self.source,self.catalog)],self.source)
        self.node._schedule_host_callback.assert_called_once()

    def test_changed_scene_retains_old_receipt_but_queues_only_draft_preparation(self):
        self.node._records=lambda:self.records
        self.node.get_parameter_value=lambda name:self.project
        self.node._hmb_apply_epoch=4
        self.node._schedule_host_callback=mock.Mock(return_value=True)
        before=deepcopy(self.project)
        with mock.patch.object(product,"scene_fingerprint",return_value="4"*64):
            product.HMBImageBash._queue_saved_editor_readiness(self.node,self.context,[(self.source,self.catalog)],self.source)
        self.assertFalse(self.node._hmb_restore_pending)
        self.assertEqual(self.project,before);self.node._set_project.assert_not_called()
        self.node._schedule_host_callback.assert_called_once()

    def test_initial_draft_queues_without_apply_and_no_loop_reports_error(self):
        self.project["meta"]["hmb_image_bash"].pop("apply")
        self.node._records=lambda:self.records
        self.node.get_parameter_value=lambda name:self.project
        self.node._hmb_apply_epoch=0
        self.node._schedule_host_callback=mock.Mock(return_value=False)
        product.HMBImageBash._queue_saved_editor_readiness(self.node,self.context,[(self.source,self.catalog)],self.source)
        self.assertEqual(self.node._hmb_prepare_phase,"error")
        self.assertIn("이벤트 루프",self.node._hmb_prepare_error)
        self.assertFalse(self.node._hmb_restore_pending);self.node._set_project.assert_not_called()

    def test_malformed_saved_document_is_error_without_restore_or_scene_changes(self):
        for value in ("invalid",{"meta":{"hmb_image_bash":None}}):
            with self.subTest(value=value):
                self.node._hmb_prepare_phase="idle"
                self.node.get_parameter_value=lambda name:value
                product.HMBImageBash._queue_saved_editor_readiness(self.node,self.context,[(self.source,self.catalog)],self.source)
                self.assertEqual(self.node._hmb_prepare_phase,"error")
                self.assertIn("장면 정보",self.node._hmb_prepare_error)
                self.node._set_project.assert_not_called()

    def test_cold_callback_rejects_changed_workspace_before_any_restore_or_scene_sync(self):
        self.node._hmb_apply_epoch=4
        self.node._records=lambda:self.records
        self.node._restore_saved_output=mock.Mock();self.node._sync_metadata_with_input_images=mock.Mock()
        self.scope["workspace_revision"]=5
        previous={**self.scope,"workspace_revision":4}
        product.HMBImageBash._complete_cold_editor_readiness.__wrapped__(self.node,previous,self.source,"source-instance",4,True)
        self.node._restore_saved_output.assert_not_called();self.node._sync_metadata_with_input_images.assert_not_called()
        self.node._set_project.assert_not_called();self.assertEqual(self.node._hmb_prepare_phase,"error")


if __name__ == "__main__": unittest.main(verbosity=2)
