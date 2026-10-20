"""Saved grades survive optional archive/editor faults without crossing owners.

The tiny FFmpeg cases encode/probe actual media; all other cases use the native
command lifecycle with deterministic dispatch. No upstream generation or HTTP.
"""
from __future__ import annotations

import copy
import contextlib
import json
import subprocess
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_Color_LUT_Node_Regression as fixtures
import HMBColorLUTLibrary as target
import _hmb_color_lut as engine


class ColorLUTPostsaveIsolationRegression(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ColorLUTNodeRegression()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.node, self.root = self.fixture.node, self.fixture.root
        self.fixture.select()
        self.fixture.load()
        self.fixture.apply(output={"codec": "ffv1", "manual_output_enabled": False, "path": ""})
        self.receipt = mock.patch.object(self.node, "_record_export_proof")
        self.receipt_mock = self.receipt.start()
        self.addCleanup(self.receipt.stop)

    def result(self):
        return self.node._hmb_color_lut_state["result"]

    def export(self, **kwargs):
        with mock.patch.object(target, "export_video", side_effect=self.fixture.successful_export):
            self.fixture.export(**kwargs)

    def assert_saved(self, stage=""):
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "complete")
        result = self.result()
        self.assertTrue(Path(result["path"]).is_file())
        history = self.node._hmb_color_lut_state["shot_states"][target._selection_key(self.node._hmb_color_lut_state)]
        self.assertEqual(history["result"], result)
        if stage:
            self.assertIn(stage, [item["stage"] for item in result["postprocess_warnings"]])
        return result

    def reopen(self, saved):
        node = target.HMBColorLUTLibrary(name="Cold reopened saved Color LUT")
        node.publish_update_to_parameter = mock.Mock()
        node._apply_ui(json.loads(json.dumps(saved)), initial_setup=True)
        node._queue_source(saved["source"])
        self.fixture.drain()
        return node

    def test_verified_artifact_is_retained_before_archive_preview_and_receipt(self):
        archive = self.node._archive_grade
        def inspect_archive(state, result, job):
            self.assertEqual(self.result()["path"], result["path"])
            self.assertTrue(Path(self.result()["path"]).is_file())
            return archive(state, result, job)
        with mock.patch.object(self.node, "_archive_grade", side_effect=inspect_archive):
            self.export()
        self.assert_saved()

    def test_archive_error_retains_result_and_does_not_prepare_web_receipt(self):
        with mock.patch.object(self.node, "_archive_grade", side_effect=PermissionError("metadata denied")):
            self.export()
        result = self.assert_saved("archive")
        self.assertTrue(result["url"])
        self.receipt_mock.assert_not_called()
        self.assertNotIn("web_export_proof", result)
        self.assertFalse(self.node._upload_projection()["enabled"])
        reopened = self.reopen(copy.deepcopy(self.node._hmb_color_lut_state))
        self.assertEqual(reopened._hmb_color_lut_state["result"]["path"], result["path"])
        self.assertTrue(reopened.parameter_output_values["video_url"])

    def test_preview_error_retains_result_and_recovers_after_reopen(self):
        with mock.patch.object(target, "_media_url", side_effect=RuntimeError("native service unavailable")):
            self.export()
            result = copy.deepcopy(self.assert_saved("preview"))
            self.assertEqual(result["url"], "")
            saved = copy.deepcopy(self.node._hmb_color_lut_state)
            cold = self.reopen(saved)
            self.assertEqual(cold._hmb_color_lut_state["result"]["path"], result["path"])
            self.assertEqual(cold._hmb_color_lut_state["status"]["phase"], "complete")
            self.assertTrue(cold._hmb_color_lut_state["source"]["path"])
        restored = self.reopen(saved)
        self.assertEqual(restored._hmb_color_lut_state["result"]["path"], result["path"])
        self.assertTrue(restored.parameter_output_values["video_url"])

    def test_receipt_error_retains_result_and_cannot_enable_upload(self):
        def partial_receipt(_state, result, _cancel):
            result["web_export_proof"] = "uncommitted-proof"
            raise PermissionError("private receipt denied")
        self.receipt_mock.side_effect = partial_receipt
        self.export()
        result = self.assert_saved("web_receipt")
        self.assertNotIn("web_export_proof", result)
        self.assertFalse(self.node._upload_projection()["enabled"])
        with self.assertRaises(ValueError):
            self.node._prepare_upload_context(copy.deepcopy(self.node._hmb_color_lut_state))

    def test_optional_failure_matrix_preserves_success_without_worker_escape(self):
        boundaries = {
            "output_notification": "_publish_result_url",
            "ui_notification": "_publish",
            "upload_probe": "_schedule_upload_probe",
        }
        for index, (stage, method) in enumerate(boundaries.items()):
            with self.subTest(stage=stage), mock.patch.object(self.node, method, side_effect=RuntimeError(stage)):
                # Call the dispatch target only after the command has marked
                # its own operation; do not fault the initial working status.
                state = copy.deepcopy(self.node._hmb_color_lut_state)
                state["data_directory"] = str(self.root / "workflow" / "data")
                job_id = stage + str(index)
                self.node._job_id = job_id
                with mock.patch.object(target, "export_video", side_effect=self.fixture.successful_export):
                    self.node._run_command("export", state, job_id, target._selection_key(state), threading.Event())
                self.assert_saved(stage)

    def test_native_state_store_failure_preserves_private_result_and_later_save(self):
        native = target._set_parameter_silently
        def store(node, name, value):
            if name == target.UI:
                raise RuntimeError("native UI storage temporarily unavailable")
            return native(node, name, value)
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state["data_directory"] = str(self.root / "workflow" / "data")
        self.node._job_id = "store-fault"
        with mock.patch.object(target, "_set_parameter_silently", side_effect=store), mock.patch.object(target, "export_video", side_effect=self.fixture.successful_export):
            self.node._run_command("export", state, "store-fault", target._selection_key(state), threading.Event())
        result = copy.deepcopy(self.assert_saved("state_storage"))
        self.node._publish()
        self.assertEqual(self.reopen(self.node._hmb_color_lut_state)._hmb_color_lut_state["result"]["path"], result["path"])

    def test_ui_notification_failure_cannot_prevent_output_notification_or_cold_reopen(self):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state["data_directory"] = str(self.root / "workflow" / "data")
        self.node._job_id = "publish-fault"
        self.node.publish_update_to_parameter = mock.Mock(side_effect=RuntimeError("subscriber unavailable"))
        with mock.patch.object(target, "export_video", side_effect=self.fixture.successful_export):
            self.node._run_command("export", state, "publish-fault", target._selection_key(state), threading.Event())
        result = self.assert_saved("ui_notification")
        self.assertEqual(self.node.parameter_output_values["video_url"], result["url"])
        self.assertEqual(self.reopen(self.node._hmb_color_lut_state)._hmb_color_lut_state["result"]["path"], result["path"])

    def test_cancel_before_verified_commit_never_publishes_result(self):
        def cancel_after_encode(*args, **kwargs):
            result = self.fixture.successful_export(*args, **kwargs)
            kwargs["cancel_event"].set()
            return result
        with mock.patch.object(target, "export_video", side_effect=cancel_after_encode), mock.patch.object(self.node, "_archive_grade") as archive:
            self.fixture.export()
        self.assertFalse(self.result())
        self.assertFalse(self.node.parameter_output_values.get("video_url"))
        archive.assert_not_called()

    def test_cancel_after_verified_commit_does_not_erase_the_saved_result(self):
        archive = self.node._archive_grade
        def cancel_during_archive(*args):
            self.node._cancel.set()
            return archive(*args)
        self.receipt_mock.side_effect = ValueError("Upload cancelled")
        with mock.patch.object(self.node, "_archive_grade", side_effect=cancel_during_archive):
            self.export()
        self.assert_saved("web_receipt")

    def test_deleted_node_during_encode_or_archive_never_receives_late_notifications(self):
        for boundary in ("encode", "archive"):
            with self.subTest(boundary=boundary):
                # Each deletion owns a fresh node and leaves the already saved
                # physical file intact instead of deleting unrelated media.
                node = self.node
                original = self.fixture.successful_export if boundary == "encode" else node._archive_grade
                def deleted(*args, **kwargs):
                    result = original(*args, **kwargs)
                    node.after_node_deleted()
                    node.publish_update_to_parameter.reset_mock()
                    return result
                method = mock.patch.object(target, "export_video", side_effect=deleted) if boundary == "encode" else mock.patch.object(node, "_archive_grade", side_effect=deleted)
                with method:
                    if boundary == "encode": self.fixture.export(request_id=boundary)
                    else: self.export(request_id=boundary)
                node.publish_update_to_parameter.assert_not_called()
                if boundary == "encode":
                    self.assertFalse(node._hmb_color_lut_state["result"])
                if boundary == "encode":
                    self.node = self.fixture.node = target.HMBColorLUTLibrary(name="Fresh post-delete LUT")
                    self.node.publish_update_to_parameter = mock.Mock()
                    self.fixture.select(); self.fixture.load()
                    self.fixture.apply(output={"codec": "ffv1", "manual_output_enabled": False, "path": ""})

    def test_source_replacement_never_receives_old_export_result_or_url(self):
        def replacement(*args, **kwargs):
            result = self.fixture.successful_export(*args, **kwargs)
            self.node._queue_source(self.fixture.source(name="second.mp4", generation="g2"))
            self.fixture.drain()
            return result
        with mock.patch.object(target, "export_video", side_effect=replacement):
            self.fixture.export()
        self.assertFalse(self.result())
        self.assertEqual(self.node._hmb_color_lut_state["source"]["generation_id"], "g2")
        self.assertFalse(self.node.parameter_output_values.get("video_url"))

    def test_other_shot_keeps_only_its_own_result_and_old_grade_restores(self):
        archive = self.node._archive_grade
        def switch(*args):
            self.fixture.select(fixtures.SHOT_B)
            self.fixture.load(name="shot-b.mp4", generation="b", shot=fixtures.SHOT_B)
            return archive(*args)
        with mock.patch.object(self.node, "_archive_grade", side_effect=switch):
            self.export()
        self.assertEqual(self.node._hmb_color_lut_state["shot"], fixtures.SHOT_B)
        self.assertFalse(self.result())
        self.assertFalse(self.node.parameter_output_values.get("video_url"))
        self.fixture.select(fixtures.SHOT_A); self.fixture.load()
        self.assertTrue(self.result().get("path"))
        self.assertEqual(self.result()["shot"], fixtures.SHOT_A)

    def test_new_job_identity_during_archive_cannot_replace_newer_result(self):
        archive = self.node._archive_grade
        def changed_job(*args):
            result = archive(*args)
            self.node._job_id = "newer-job"
            self.node._hmb_color_lut_state["result"] = {"path": "newer-owned-result", "job_id": "newer-job"}
            return result
        with mock.patch.object(self.node, "_archive_grade", side_effect=changed_job):
            self.export()
        self.assertEqual(self.result()["job_id"], "newer-job")
        self.assertFalse(self.node.parameter_output_values.get("video_url"))

    def test_encoder_failure_and_existing_destination_remain_errors(self):
        for failure in (ValueError("invalid video"), PermissionError("output denied")):
            with self.subTest(failure=failure), mock.patch.object(target, "export_video", side_effect=failure):
                self.fixture.export(request_id=str(failure))
                self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "error")
                self.assertFalse(self.result())
        output = self.root / "existing.mkv"; output.write_bytes(b"keep-existing")
        self.fixture.apply(output={"codec": "ffv1", "manual_output_enabled": True, "path": str(output)})
        self.export(request_id="collision")
        self.assertEqual(output.read_bytes(), b"keep-existing")
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "error")
        self.assertFalse(self.result())

    def test_same_request_replay_after_notification_failure_never_encodes_twice(self):
        state = copy.deepcopy(self.node._hmb_color_lut_state)
        state["data_directory"] = str(self.root / "workflow" / "data")
        calls = []
        def encoded(*args, **kwargs):
            calls.append(True)
            result = self.fixture.successful_export(*args, **kwargs)
            self.node.publish_update_to_parameter = mock.Mock(side_effect=RuntimeError("subscriber unavailable"))
            return result
        with mock.patch.object(target, "export_video", side_effect=encoded):
            self.fixture.export(request_id="once-only")
            self.fixture.export(request_id="once-only")
        self.assertEqual(len(calls), 1)
        self.assert_saved("ui_notification")

    def test_all_five_shots_keep_distinct_settings_sources_results_after_faults_and_reopen(self):
        shots = [{**fixtures.SHOT_A, "shot_uuid": f"isolated-shot-{number}", "number": number, "name": f"Authored {number}"} for number in range(1, 6)]
        saved_results = {}
        for number, shot in enumerate(shots, 1):
            self.fixture.select(shot)
            self.fixture.load(name=f"source-{number}.mp4", generation=f"task-{number}", shot=shot)
            self.fixture.apply(settings={"enabled": True, "precision_version": 2, "exposure": number / 4})
            context = {
                1: mock.patch.object(self.node, "_archive_grade", side_effect=PermissionError("archive denied")),
                2: mock.patch.object(target, "_media_url", side_effect=RuntimeError("preview unavailable")),
                3: mock.patch.object(self.node, "_record_export_proof", side_effect=PermissionError("receipt denied")),
                4: mock.patch.object(self.node, "_publish_result_url", side_effect=RuntimeError("subscriber unavailable")),
            }.get(number, contextlib.nullcontext())
            with context:
                self.export(request_id=f"five-shot-{number}")
            result = self.assert_saved()
            self.assertEqual(result["shot"]["shot_uuid"], shot["shot_uuid"])
            self.assertEqual(result["settings"]["exposure"], number / 4)
            saved_results[shot["shot_uuid"]] = copy.deepcopy(result)
        cold = self.reopen(copy.deepcopy(self.node._hmb_color_lut_state))
        self.node = self.fixture.node = cold
        for number, shot in reversed(list(enumerate(shots, 1))):
            self.fixture.select(shot)
            self.fixture.load(name=f"source-{number}.mp4", generation=f"task-{number}", shot=shot)
            self.assertEqual(self.result()["path"], saved_results[shot["shot_uuid"]]["path"])
            self.assertEqual(self.node._hmb_color_lut_state["settings"]["exposure"], number / 4)
            self.assertEqual(self.result()["source_path"], str(self.root / f"source-{number}.mp4"))
            self.assertEqual(cold.parameter_output_values["video_url"], self.result()["url"])

    def saved_grade(self):
        self.export()
        return copy.deepcopy(self.node._hmb_color_lut_state)

    def cold_grade(self, saved):
        node = target.HMBColorLUTLibrary(name="Fault-injected cold reopened Color LUT")
        node.publish_update_to_parameter = mock.Mock()
        node._apply_ui(copy.deepcopy(saved), initial_setup=True)
        return node

    def test_restored_valid_grade_survives_native_ui_cache_probe_and_status_failures(self):
        saved = self.saved_grade()
        for stage in ("native_ui", "selection_cache", "upload_probe", "status", "state_storage"):
            with self.subTest(stage=stage):
                cold = self.cold_grade(saved)
                boundary = {"selection_cache": "_remember_selection", "upload_probe": "_schedule_upload_probe", "status": "_status"}.get(stage)
                def rejected_ui(name, value):
                    if name == target.UI and value.get("source"):
                        raise RuntimeError("Native restored dashboard event unavailable")
                if stage == "native_ui":
                    cold.publish_update_to_parameter.side_effect = rejected_ui
                native_store = target._set_parameter_silently
                def rejected_store(node, name, value):
                    if node is cold and name == target.UI:
                        raise RuntimeError("Restored native state storage unavailable")
                    return native_store(node, name, value)
                fault = mock.patch.object(cold, boundary, side_effect=RuntimeError(stage)) if boundary else mock.patch.object(
                    target, "_set_parameter_silently", side_effect=rejected_store) if stage == "state_storage" else contextlib.nullcontext()
                with fault:
                    cold._queue_source(copy.deepcopy(saved["source"]))
                    self.fixture.drain()
                state = cold._hmb_color_lut_state
                self.assertEqual(state["status"]["phase"], "complete")
                self.assertEqual(state["result"]["path"], saved["result"]["path"])
                self.assertTrue(Path(state["result"]["path"]).is_file())
                self.assertEqual(cold.parameter_output_values["video_url"], state["result"]["url"])
                self.assertEqual(state["shot_states"][target._selection_key(state)]["result"], state["result"])
                self.assertIsNone(cold._source_worker)
                if stage != "status":
                    expected = "ui_notification" if stage == "native_ui" else stage
                    self.assertIn(expected, [item["stage"] for item in state["result"]["postprocess_warnings"]])

    def test_required_restoration_source_and_result_probe_failures_stay_error_without_worker_escape(self):
        saved = self.saved_grade()
        for boundary in ("source", "result", "dimensions", "foreign_source"):
            with self.subTest(boundary=boundary):
                value = copy.deepcopy(saved)
                if boundary == "foreign_source":
                    value["result"]["source_path"] = str(self.root / "unrelated.mp4")
                cold = self.cold_grade(value)
                def required_probe(path):
                    if (boundary == "source" and str(path) == saved["source"]["path"]
                            or boundary == "result" and str(path) == saved["result"]["path"]):
                        raise ValueError("Required media probe failed")
                    info = self.fixture.probe(path)
                    if boundary == "dimensions" and str(path) == saved["result"]["path"]:
                        info["width"] += 2
                    return info
                with mock.patch.object(target, "probe_source", side_effect=required_probe), mock.patch.object(cold, "_publish", side_effect=RuntimeError("UI unavailable")), mock.patch.object(cold, "_status", side_effect=RuntimeError("status unavailable")):
                    cold._queue_source(value["source"])
                    self.fixture.drain()
                self.assertEqual(cold._hmb_color_lut_state["status"]["phase"], "error")
                self.assertFalse(cold._hmb_color_lut_state["result"])
                self.assertFalse(cold.parameter_output_values.get("video_url"))
                self.assertTrue(Path(saved["result"]["path"]).is_file())
                self.assertIsNone(cold._source_worker)

    def test_invalid_new_source_remains_error_when_native_notifications_are_unavailable(self):
        saved = self.saved_grade()
        with mock.patch.object(target, "probe_source", side_effect=ValueError("invalid replacement video")), mock.patch.object(self.node, "_publish", side_effect=RuntimeError("UI unavailable")), mock.patch.object(self.node, "_status", side_effect=RuntimeError("status unavailable")):
            self.node._queue_source(self.fixture.source(name="invalid-next.mp4", generation="g2"))
            self.fixture.drain()
        self.assertEqual(self.node._hmb_color_lut_state["status"]["phase"], "error")
        self.assertFalse(self.result())
        self.assertFalse(self.node.parameter_output_values.get("video_url"))
        self.assertTrue(Path(saved["result"]["path"]).is_file())
        self.assertIsNone(self.node._source_worker)

    def test_source_replaced_during_cold_probe_never_restores_old_grade(self):
        saved = self.saved_grade(); cold = self.cold_grade(saved)
        queued = []
        replacement = self.fixture.source(name="next-source.mp4", generation="g2")
        def probe(path):
            if str(path) == saved["source"]["path"] and not queued:
                queued.append(True)
                cold._queue_source(replacement)
            return self.fixture.probe(path)
        with mock.patch.object(target, "probe_source", side_effect=probe):
            cold._queue_source(saved["source"])
            self.fixture.drain()
        self.assertEqual(cold._hmb_color_lut_state["source"]["generation_id"], "g2")
        self.assertFalse(cold._hmb_color_lut_state["result"])
        self.assertFalse(cold.parameter_output_values.get("video_url"))
        self.assertEqual(cold._hmb_color_lut_state["status"]["phase"], "idle")

    def test_deletion_during_saved_grade_probe_suppresses_all_late_publications(self):
        saved = self.saved_grade(); cold = self.cold_grade(saved)
        def probe(path):
            info = self.fixture.probe(path)
            if str(path) == saved["result"]["path"]:
                cold.after_node_deleted()
                cold.publish_update_to_parameter.reset_mock()
            return info
        with mock.patch.object(target, "probe_source", side_effect=probe):
            cold._queue_source(saved["source"])
            self.fixture.drain()
        cold.publish_update_to_parameter.assert_not_called()
        self.assertFalse(cold.parameter_output_values.get("video_url"))
        self.assertIsNone(cold._source_worker)

    def test_existing_export_cancellation_does_not_cancel_saved_media_restoration(self):
        saved = self.saved_grade(); cold = self.cold_grade(saved)
        cold._cancel.set()
        cold._queue_source(saved["source"])
        self.fixture.drain()
        self.assertEqual(cold._hmb_color_lut_state["status"]["phase"], "complete")
        self.assertEqual(cold._hmb_color_lut_state["result"]["path"], saved["result"]["path"])
        self.assertTrue(cold.parameter_output_values["video_url"])

    def test_malformed_saved_warning_records_cannot_break_restoration_fault_reporting(self):
        saved = self.saved_grade()
        for warnings in (None, "invalid", {}, [None, {}, "invalid", {"stage": [], "message": {}}]):
            with self.subTest(warnings=warnings):
                state = copy.deepcopy(saved)
                state["result"]["postprocess_warnings"] = warnings
                cold = self.cold_grade(state)
                with mock.patch.object(cold, "_schedule_upload_probe", side_effect=RuntimeError("optional probe unavailable")):
                    cold._queue_source(state["source"])
                    self.fixture.drain()
                self.assertEqual(cold._hmb_color_lut_state["status"]["phase"], "complete")
                self.assertEqual(cold._hmb_color_lut_state["result"]["path"], state["result"]["path"])
                self.assertIn("upload_probe", [item["stage"] for item in cold._hmb_color_lut_state["result"]["postprocess_warnings"]])
                self.assertIsNone(cold._source_worker)

    def test_real_encode_archive_permission_and_native_preview_faults(self):
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            service_context = contextlib.nullcontext()
        except ModuleNotFoundError:
            # Pure CI has no desktop SDK. Exercise the same URL import seam
            # with its one required service; SDK runs use the actual class.
            GriptapeNodes = types.SimpleNamespace(StaticFilesManager=lambda: types.SimpleNamespace(static_server_base_url="http://native-fixture.test"))
            service_context = mock.patch.dict(sys.modules, {"griptape_nodes.retained_mode.griptape_nodes": types.SimpleNamespace(GriptapeNodes=GriptapeNodes)})
        # setUp patches the module URL helper. Load the original implementation
        # without importing a second node class or changing registered identity.
        namespace = {"Path": Path, "quote": target.quote}
        import ast
        tree = ast.parse(Path(target.__file__).read_text(encoding="utf-8"))
        definition = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_media_url")
        exec(compile(ast.Module(body=[definition], type_ignores=[]), target.__file__, "exec"), namespace)
        real_media_url = namespace["_media_url"]
        source = self.root / "real-original.mp4"
        made = subprocess.run([engine._find_ffmpeg(), "-hide_banner", "-v", "error", "-nostdin", "-n", "-f", "lavfi", "-i",
                               "testsrc2=size=96x64:rate=12:duration=0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(source)],
                              capture_output=True, timeout=30)
        self.assertEqual(made.returncode, 0, made.stderr)
        with mock.patch.object(target, "probe_source", side_effect=engine.probe_source):
            self.node._queue_source({**self.fixture.source(), "path": str(source), "generation_id": "real", "result_revision": "real"})
            self.fixture.drain()
        original_open = Path.open
        def denied_metadata(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if path.name.startswith("color_lut_") and path.suffix == ".json" and mode == "x":
                raise PermissionError("isolated metadata share write denied")
            return original_open(path, *args, **kwargs)
        for stage in ("archive", "preview"):
            with service_context, self.subTest(stage=stage):
                fault = mock.patch.object(Path, "open", new=denied_metadata) if stage == "archive" else mock.patch.object(
                    GriptapeNodes, "StaticFilesManager", side_effect=RuntimeError("isolated native StaticFilesManager unavailable"), create=True)
                with fault, mock.patch.object(target, "_media_url", new=real_media_url), mock.patch.object(target, "export_video", side_effect=engine.export_video):
                    self.fixture.export(request_id="real-encode-" + stage)
                result = copy.deepcopy(self.assert_saved(stage))
                probe = engine.probe_source(result["path"])
                self.assertEqual((probe["width"], probe["height"]), (96, 64))
                self.assertEqual(probe["video_codec"], "ffv1")
                self.assertGreater(Path(result["path"]).stat().st_size, 0)
                saved = copy.deepcopy(self.node._hmb_color_lut_state)
                with mock.patch.object(target, "probe_source", side_effect=engine.probe_source):
                    reopened = self.reopen(saved)
                self.assertEqual(reopened._hmb_color_lut_state["result"]["path"], result["path"])
                self.assertTrue(reopened.parameter_output_values["video_url"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
