"""Raw re-read fences and content-keyed analysis/hash reuse; no real host writes."""
from collections import OrderedDict
from copy import deepcopy
import importlib.util
from io import BytesIO
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBImageBash as bash
import _hmb_image_bash_compat as compat
from PIL import Image

class RasterReuseRegression(unittest.TestCase):
    def png(self, color):
        output = BytesIO(); Image.new("RGBA", (3, 2), color).save(output, "PNG"); return output.getvalue()

    def test_each_validation_rereads_raw_but_reuses_exact_sha_raster(self):
        project = {"meta": {"input_images": [{"id": "a", "url": "fixture:a"}],
                            "konva_json": {"images": [{"id": "layer", "src": "fixture:a"}]}}}
        cache = OrderedDict(); payload = self.png("red")
        with mock.patch.object(bash, "_read_bytes", return_value=payload) as reader, mock.patch.object(Image, "open", wraps=Image.open) as opened:
            first = bash.HMBImageBash._source_hashes(None, project, rgba_cache=cache)
            second = bash.HMBImageBash._source_hashes(None, project, rgba_cache=cache)
        self.assertEqual(first, second); self.assertEqual(reader.call_count, 2)
        self.assertEqual(opened.call_count, 1)

    def test_same_url_changed_raw_is_decoded_and_receipt_hash_changes(self):
        project = {"meta": {"input_images": [{"id": "a", "url": "same:url"}]}}
        cache = OrderedDict()
        with mock.patch.object(bash, "_read_bytes", side_effect=[self.png("red"), self.png("blue")]) as reader, mock.patch.object(Image, "open", wraps=Image.open) as opened:
            first = bash.HMBImageBash._source_hashes(None, project, rgba_cache=cache)
            second = bash.HMBImageBash._source_hashes(None, project, rgba_cache=cache)
        self.assertNotEqual(first, second); self.assertEqual(reader.call_count, 2); self.assertEqual(opened.call_count, 2)

    def test_cancel_stops_before_read_and_cache_is_bounded(self):
        project = {"meta": {"input_images": [{"id": "a", "url": "fixture:a"}]}}
        with mock.patch.object(bash, "_read_bytes", side_effect=AssertionError("cancelled work read pixels")):
            with self.assertRaisesRegex(ValueError, "취소"):
                bash.HMBImageBash._source_hashes(None, project, rgba_cache=OrderedDict(), is_live=lambda: False)
        cache = OrderedDict((str(index), {"width": 1}) for index in range(128))
        with mock.patch.object(bash, "_read_bytes", return_value=self.png("red")):
            bash.HMBImageBash._source_hashes(None, project, rgba_cache=cache)
        self.assertEqual(len(cache), 128)

class SnapshotPolicyRegression(unittest.TestCase):
    def test_snapshot_paths_and_lease_use_sdk_workflow(self):
        from griptape_nodes.files import file as file_module
        from griptape_nodes.files.drivers.local_file_driver import LocalFileDriver
        from griptape_nodes.files.file_driver import FileDriverRegistry

        path = "C:/fixture/source.png"
        workflow = object()
        driver = LocalFileDriver()
        calls = []

        def resolve_file_path(file_path, workflow):
            calls.append((file_path, workflow))
            return file_path

        with mock.patch.object(file_module, "_resolve_file_path", resolve_file_path), \
             mock.patch.object(bash.File, "workflow", mock.PropertyMock(return_value=workflow), create=True), \
             mock.patch.object(FileDriverRegistry, "get_driver", return_value=driver), \
             mock.patch.object(bash.File, "resolve", return_value=path):
            paths = bash.HMBImageBash._snapshot_read_paths(records=[{"url": path}])
            self.assertEqual(paths, {path: path})
            self.assertEqual(bash.HMBImageBash._snapshot_driver_lease(paths), ((path, driver),))
        self.assertEqual(calls, [(path, workflow), (path, workflow)])

    def test_unknown_resolver_signature_skips_accelerated_reads(self):
        from griptape_nodes.files import file as file_module

        def unreviewed_resolver(path, workflow, additional_context):
            raise AssertionError("Unreviewed resolver was called")

        with mock.patch.object(file_module, "_resolve_file_path", unreviewed_resolver), \
             mock.patch.object(bash.File, "resolve", side_effect=AssertionError("Private route was used")):
            self.assertIsNone(bash.HMBImageBash._snapshot_read_paths(records=[{"url": "C:/fixture/source.png"}]))

    def test_custom_driver_keeps_original_synchronous_transport(self):
        from griptape_nodes.files.file_driver import FileDriverRegistry
        from griptape_nodes.files import file as file_module
        with mock.patch.object(FileDriverRegistry, "get_driver", return_value=object()), \
             mock.patch.object(file_module, "_resolve_file_path", side_effect=lambda value: value), \
             mock.patch.object(bash.File, "resolve", side_effect=AssertionError("Custom driver bypassed")):
            self.assertIsNone(bash.HMBImageBash._snapshot_read_paths({"value": "custom://approved/PNG", "meta": {}}))

    def test_local_png_envelope_is_snapshot_mapped_and_subclasses_fallback(self):
        from griptape_nodes.files.file_driver import FileDriverRegistry
        from griptape_nodes.files.drivers.local_file_driver import LocalFileDriver
        from griptape_nodes.files import file as file_module
        project = {"value": "C:/fixture/output.png", "meta": {"input_images": [{"url": "C:/fixture/source.png"}]}}
        with mock.patch.object(file_module, "_resolve_file_path", side_effect=lambda value: value), \
             mock.patch.object(FileDriverRegistry, "get_driver", return_value=LocalFileDriver()), \
             mock.patch.object(bash.File, "resolve", lambda instance: instance._file_path):
            paths = bash.HMBImageBash._snapshot_read_paths(project)
            self.assertEqual(set(paths), {"C:/fixture/output.png", "C:/fixture/source.png"})
        class CustomLocal(LocalFileDriver): pass
        with mock.patch.object(file_module, "_resolve_file_path", side_effect=lambda value: value), \
             mock.patch.object(FileDriverRegistry, "get_driver", return_value=CustomLocal()):
            self.assertIsNone(bash.HMBImageBash._snapshot_read_paths(project))


spec = importlib.util.spec_from_file_location("bash_compatibility_existing_fixture", ROOT / "resources/tests/HMB_Image_Bash_Compatibility_Regression.py")
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)

class ColdDraftPromotionRegression(unittest.TestCase):
    def test_same_scene_hash_cold_draft_clears_output_live_refresh_preserves(self):
        from types import SimpleNamespace
        from _hmb_image_bash_state import scene_fingerprint
        records=[]; canvas={"width":4,"height":2,"workspace_id":"w"}
        project={"value":"previous-PNG-preserved", "meta":{"created_at":"same-commit", "konva_json":{"images":[],"lines":[]},"hmb_image_bash":{}}}
        receipt={"source_hashes":{}, "scene_sha256":scene_fingerprint(project,records,canvas)}
        project["meta"]["hmb_image_bash"]["apply"]=receipt
        for force in (False,True):
            with self.subTest(force_draft=force):
                task={"force_draft":force}
                cleared=mock.Mock(); published=[]
                node=SimpleNamespace(_apply_task_current=lambda task:True,_source_hashes=lambda *a,**k:{},
                    _records=lambda:records,_canvas=lambda:canvas,get_parameter_value=lambda name:deepcopy(project),
                    _set_project=lambda p:published.append(deepcopy(p)),_clear_output=cleared,_status=mock.Mock(),
                    _hmb_restore_pending=False,_hmb_last_output={"path":"old-file"},_hmb_output_pending=False)
                result={"project":deepcopy(project),"hashes":{},"rgba_cache":OrderedDict()}
                self.assertTrue(bash.HMBImageBash._finish_prepare.__wrapped__(node,task,result))
                self.assertEqual(cleared.call_count,int(force))
                self.assertEqual(published[0]["value"],project["value"])
                self.assertEqual(published[0]["meta"]["hmb_image_bash"]["apply"],receipt)

    def test_saved_markers_are_draft_only_and_bad_scope_uid_marker_is_rejected(self):
        path=ROOT/"resources/tests/HMB_Image_Bash_Readiness_Regression.py"
        spec=importlib.util.spec_from_file_location("readiness_cold_marker_fixture",path)
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        for kind in ("apply", "prepare", "bad-schema", "bad-commit", "bad-UID", "bad-scope"):
            with self.subTest(marker=kind):
                f=fixture.SavedEditorLeaseRegression();f.setUp()
                try:
                    f.node._hmb_apply_epoch=1;f.node._records=lambda:f.records
                    f.node.get_parameter_value=lambda name:f.project if name=="bash_image" else f.context
                    f.node._schedule_host_callback=mock.Mock(return_value=True)
                    f.node._sync_metadata_with_input_images=mock.Mock()
                    f.node._complete_cold_editor_readiness=lambda *a:bash.HMBImageBash._complete_cold_editor_readiness.__wrapped__(f.node,*a)
                    hmb=f.project["meta"]["hmb_image_bash"]
                    if kind in {"apply","bad-schema","bad-commit"}:
                        f.project["meta"]["created_at"]="new-pending-commit"
                        hmb["pending_apply"]={"schema":"hmb-image-bash-pending-apply-v1","editor_commit":"new-pending-commit"}
                        if kind=="bad-schema": hmb["pending_apply"]["schema"]="forged"
                        if kind=="bad-commit": hmb["pending_apply"]["editor_commit"]="old-commit"
                    else:
                        hmb["pending_prepare"]={"schema":"hmb-image-bash-pending-prepare-v1", "scope":{key:f.scope[key] for key in ("workspace_id","channel_uuid","workspace_revision")}, "source_uids":["a"]}
                        if kind=="bad-UID": hmb["pending_prepare"]["source_uids"]=["foreign"]
                        if kind=="bad-scope": hmb["pending_prepare"]["scope"]["channel_uuid"]="foreign"
                    bash.HMBImageBash._queue_saved_editor_readiness(f.node,f.context,[(f.source,f.catalog)],f.source)
                    if kind in {"apply","prepare"}:
                        f.node._schedule_host_callback.assert_called_once()
                        f.node._schedule_host_callback.call_args.args[0]()
                        f.node._sync_metadata_with_input_images.assert_called_once_with(force_draft=True)
                    else:
                        f.node._schedule_host_callback.assert_not_called()
                        self.assertEqual(f.node._hmb_prepare_phase,"error")
                    f.node._set_project.assert_not_called()
                finally: f.doCleanups()

class NegativeAnalysisRegression(unittest.TestCase):
    def setUp(self):
        with compat._ANALYSIS_LOCK: compat._ANALYSIS_CACHE.clear()

    def test_negative_content_scan_reuses_message_not_exception_or_authority(self):
        anchors = {"scope": ("start", "end")}
        with mock.patch.object(compat, "_editor_contract_uncached", wraps=compat._editor_contract_uncached) as analyzed:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "anchors") as caught:
                    compat.editor_contract("missing", anchors)
                caught.exception.args = ("poisoned failure",)
            self.assertEqual(analyzed.call_count, 1)
        for entry in compat._ANALYSIS_CACHE.values():
            self.assertEqual(entry[0], "ValueError")
            self.assertIsInstance(entry[1], str)

    def test_changed_content_or_anchors_recovers_after_negative_cache(self):
        with self.assertRaises(ValueError): compat.editor_contract("missing", {"scope": ("start", "end")})
        repaired = compat.editor_contract("start body end", {"scope": ("start", "end")})
        self.assertEqual(set(repaired), {"scope"})
        # Same content with a newly reviewed anchor set is a different key.
        got = compat.editor_contract("missing", {"scope": ("mis", "ing")})
        self.assertEqual(set(got), {"scope"})

    def test_io_failure_is_never_memoized(self):
        with mock.patch.object(compat, "_source_contract_uncached", side_effect=PermissionError("denied")) as analyze:
            for _ in range(2):
                with self.assertRaises(PermissionError): compat.source_contract("synthetic")
            self.assertEqual(analyze.call_count, 2)
        self.assertFalse(compat._ANALYSIS_CACHE)

class ContentAnalysisRegression(fixture.CompatibilityRegression):
    def test_returned_contract_and_scopes_cannot_poison_cached_analysis(self):
        text = self.source.read_text("utf-8")
        first = compat.source_contract(text); original = deepcopy(first)
        first["parameters"].clear()
        self.assertEqual(compat.source_contract(text), original)
        scopes = compat.editor_contract(self.editor_source); previous = deepcopy(scopes)
        scopes[next(iter(scopes))]["sha256"] = "forged"
        self.assertEqual(compat.editor_contract(self.editor_source), previous)

    def test_same_size_same_mtime_changed_source_bytes_cannot_hit_approval(self):
        self.assertTrue(self.inspect()["compatible"])
        before = self.source.stat(); raw = self.source.read_bytes()
        self.assertIn(b"DataNode", raw)
        self.source.write_bytes(raw.replace(b"DataNode", b"FakeNode", 1))
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.source.stat().st_size, len(raw))
        self.assertFalse(self.inspect()["compatible"])

    def test_warm_analysis_still_reads_actual_editor_and_registration(self):
        self.assertTrue(self.inspect()["compatible"])
        entry = self.editor / "index-editor.html"
        entry.write_text('<script src="./assets/index-missing.js"></script>', encoding="utf-8")
        self.assertFalse(self.inspect()["compatible"])

if __name__ == "__main__": unittest.main(verbosity=2)
