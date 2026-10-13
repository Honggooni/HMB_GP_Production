"""Local diagnostic routing; no real DCC, network, or user project mutation."""
from __future__ import annotations

import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


def diagnostic_node(scene):
    """Run production state/process methods with an in-memory parameter bus.

    Bypass SDK node construction so these tests cannot attach a user graph or
    start an engine. Only unrelated tools/geometry and parameter transport are
    replaced; parsing, routing guards, diagnostics and terminal handling run.
    """
    node = object.__new__(picker.HMBVideoPickerLibrary)
    node._hmb_state_write_lock = threading.RLock()
    node._hmb_runtime_instance_id = "diagnostic-regression"
    node._hmb_lifecycle_generation = 1
    node._hmb_state_revision = 0
    node._hmb_active_operation = None
    node._hmb_active_process = None
    node._hmb_operation_thread_id = None
    node._hmb_cancel_requested = threading.Event()
    node.parameter_values = {}
    node.metadata = {}
    node._reconcile_video_tools_state = lambda state: None
    node._synchronize_picker_expanded_geometry_metadata = lambda state: False
    node._sync_outputs_from_state = lambda state: None
    node.get_parameter_value = lambda name: copy.deepcopy(node.parameter_values.get(name))
    node.set_parameter_value = lambda name, value: node.parameter_values.__setitem__(name, copy.deepcopy(value))
    base = picker._parse_state({})
    owner = copy.deepcopy(base["picker_shots"][0])
    owner.update(workspace_uuid=str(uuid.uuid4()), bound_shot_uuid=str(uuid.uuid4()), number=1, name="Shot 1")
    other = copy.deepcopy(owner)
    other.update(workspace_uuid=str(uuid.uuid4()), bound_shot_uuid=str(uuid.uuid4()), number=2, name="Shot 2")
    base.update({
        "picker_shots": [owner, other], "active_picker_shot_uuid": owner["workspace_uuid"],
        "channel_uuid": str(uuid.uuid4()), "shot_uuid": owner["bound_shot_uuid"],
        "scene_path": str(scene), "scene_request_path": str(scene),
        "native_read_ready": True, "native_metadata": {"scene_path": str(scene)},
        "selected_camera": "|camera", "camera": "|camera", "start_frame": 1.0,
        "end_frame": 10.0, "source_fps": 25.0, "snapshot_request_frame": 5.0,
        "status": "OUTLINER_READY", "scene_stage": "OUTLINER_READY", "original_enabled": True,
    })
    node._hmb_authoritative_state = picker._parse_state(base)
    node._picker_state = lambda: copy.deepcopy(node._hmb_authoritative_state)
    node._current_scene_text = lambda fallback="": str(scene)
    return node


def snapshot_context(node):
    state = node._picker_state()
    context = node._create_operation_context("render_snapshot", state["scene_path"], state)
    state = node._mark_operation_started(state, "render_snapshot")
    state.update(operation_id=context.operation_id, operation_picker_shot_uuid=context.picker_shot_uuid)
    node._hmb_authoritative_state = state
    node._hmb_active_operation = context
    return context


class DiagnosticLogRoutingTests(unittest.TestCase):
    def test_logging_does_not_need_project_folder_write_access(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-readonly-") as temporary:
            base = Path(temporary)
            project = base / "readonly-project"
            project.mkdir()
            scene = project / "shot.mb"
            scene.write_bytes(b"read-only scene fixture")
            before = scene.read_bytes()
            original_mkdir = Path.mkdir

            # Deny project folder writes at the filesystem API boundary. A
            # Windows directory's read-only attribute alone does not deny writes.
            def mkdir(path, *args, **kwargs):
                if path == project or project in path.parents:
                    raise PermissionError("production project is read-only")
                return original_mkdir(path, *args, **kwargs)

            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(base / "local")}), \
                    mock.patch.object(Path, "mkdir", mkdir):
                for operation in ("maya_read", "maya_original", "maya_snapshot", "maya_playblast", "blender_render"):
                    log = picker._picker_diagnostic_path(scene, operation, "independent-operation")
                    self.assertNotIn(project, log.parents)
                    self.assertEqual(log.suffix, ".txt")
                    log.write_text("diagnostic retained\n", encoding="utf-8")
                    self.assertEqual(log.read_text(encoding="utf-8"), "diagnostic retained\n")
            self.assertEqual(scene.read_bytes(), before)
            self.assertEqual(list(project.iterdir()), [scene])

    def test_equal_scene_names_have_distinct_stable_directories(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-names-") as temporary, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
            scene_a = Path(temporary) / "project-a" / "shot.mb"
            scene_b = Path(temporary) / "project-b" / "shot.mb"
            first = picker._picker_diagnostic_path(scene_a, "maya_read", "request")
            second = picker._picker_diagnostic_path(scene_b, "maya_read", "request")
            self.assertNotEqual(first.parent, second.parent)
            self.assertEqual(first, picker._picker_diagnostic_path(scene_a, "maya_read", "request"))
            self.assertEqual(first.name, "maya_read_request.txt")

    def test_parallel_operations_do_not_truncate_each_other(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-concurrent-") as temporary, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
            scene = Path(temporary) / "scene" / "shot.mb"

            def create(index):
                path = picker._picker_diagnostic_path(scene, "maya_playblast")
                with path.open("x", encoding="utf-8") as output:
                    output.write(str(index))
                return path, str(index)

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(create, range(64)))
            self.assertEqual(len({path for path, _ in results}), 64)
            for path, text in results:
                self.assertEqual(path.read_text(encoding="utf-8"), text)
            token_paths = {picker._picker_diagnostic_path(scene, "maya_playblast", f"op-{i}") for i in range(64)}
            self.assertEqual(len(token_paths), 64)

    def test_absent_localappdata_uses_temporary_root(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-fallback-") as temporary, \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(picker.tempfile, "gettempdir", return_value=temporary):
            os.environ.pop("LOCALAPPDATA", None)
            path = picker._picker_diagnostic_path(Path("P:/production/shot.mb"), "maya_read", "request")
            self.assertEqual(path.parents[4], Path(temporary))
            self.assertTrue(path.parent.is_dir())
            self.assertEqual(path.suffix, ".txt")

    def test_all_producers_use_local_router_and_snapshot_batch_identity(self):
        source = (ROOT / "HMBVideoPickerLibrary.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for method in ("_read_scene_mode", "_render_original_preview_mode", "_snapshot_mode", "_maya_mode", "_blender_execute_job"):
            with self.subTest(method=method):
                calls = [node for node in ast.walk(methods[method]) if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name) and node.func.id == "_picker_diagnostic_path"]
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].args[0].id, "scene_path")
                self.assertEqual(calls[0].args[2].id, "batch_uid" if method == "_snapshot_mode" else "token")
        shared = ast.get_source_segment(source, methods["_run_shared_maya_capture"])
        self.assertIn('shared_root / "shared-capture.txt"', shared)
        self.assertIn('shared_log = flight.root / "shared-capture.txt"', shared)
        self.assertIn('source.name == "shared-capture.txt"', shared)
        self.assertNotIn("shared-capture.log", shared)
        watchdog_calls = [node for node in ast.walk(methods["_run_shared_maya_capture"])
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                          and node.func.attr == "_wait_for_process_with_progress"]
        self.assertEqual(len(watchdog_calls), 1)
        activity = next(keyword.value for keyword in watchdog_calls[0].keywords if keyword.arg == "activity_paths")
        self.assertIn("shared-capture.txt", ast.get_source_segment(source, activity))

    def test_txt_stdout_remains_visible_to_activity_monitor(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-activity-") as temporary:
            path = Path(temporary) / "shared-capture.txt"
            path.write_text("startup\n", encoding="utf-8")
            before = picker._filesystem_activity_snapshot((path,))
            with path.open("a", encoding="utf-8") as output:
                output.write("shader preparation is still working\n")
            after = picker._filesystem_activity_snapshot((path,))
            self.assertNotEqual(before[0], after[0])
            self.assertEqual(after[1], 1)
            self.assertGreater(after[2], before[2])

    def test_process_registration_reports_progress_and_preserves_stop_ownership(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-process-") as temporary, \
                mock.patch.object(picker, "_request_parameter_value", return_value=False):
            scene = Path(temporary) / "scene.mb"
            scene.write_bytes(b"scene")
            for mode in ("queued", "shared-running", "direct-running"):
                with self.subTest(mode=mode):
                    node = diagnostic_node(scene)
                    context = snapshot_context(node)
                    native = mock.Mock(spec=("pid", "poll", "kill", "terminate", "wait"))
                    native.pid = 24680
                    native.poll.return_value = None
                    flight = picker._MayaCaptureFlight("fixture", lambda _: None)
                    flight.process = native if mode == "shared-running" else None
                    subscription = picker._MayaCaptureSubscription(flight)
                    sibling = picker._MayaCaptureSubscription(flight)
                    process = native if mode == "direct-running" else subscription
                    node._register_active_process(process, "Maya capture subscription" if process is subscription else "Maya")
                    published = node._picker_state()
                    entry = published["activity_log"][-1]
                    self.assertEqual(entry["level"], "INFO", "Process acceptance is not Snapshot completion.")
                    self.assertNotIn("SUCCESS", published["activity_log_text"])
                    if mode == "queued":
                        self.assertIn("waiting", entry["message"].lower())
                        self.assertNotIn("PID 0", entry["message"])
                    else:
                        self.assertIn(str(native.pid), entry["message"])
                    if process is subscription:
                        self.assertIn("STOP cancels", entry["message"])
                        self.assertNotIn("terminate this process", entry["message"])
                        picker._terminate_process(subscription)
                        self.assertTrue(subscription.cancelled.is_set())
                        self.assertFalse(sibling.cancelled.is_set())
                        self.assertFalse(flight.abort.is_set())
                        native.kill.assert_not_called()
                        native.terminate.assert_not_called()
                    else:
                        self.assertIn("STOP can terminate this process", entry["message"])
                    node._clear_active_process(object())
                    self.assertIs(node._hmb_active_process, process, "An unrelated cleanup cannot clear this owner.")
                    node._clear_active_process(process)
                    cleared = node._picker_state()
                    self.assertIsNone(node._hmb_active_process)
                    self.assertEqual((cleared["active_process_pid"], cleared["active_process_kind"]), (0, ""))
                    self.assertEqual(cleared["operation_id"], context.operation_id)
                    self.assertEqual(cleared["snapshots"], [])

    def test_routing_invalidation_records_exact_local_evidence_without_rebinding(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-routing-") as temporary, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(Path(temporary) / "local")}), \
                mock.patch.object(picker, "_request_parameter_value", return_value=False):
            base = Path(temporary)
            project = base / "production"
            project.mkdir()
            scene = project / "scene.mb"
            scene.write_bytes(b"preserved scene")
            old_log = project / "source.log"
            old_log.write_bytes(b"existing project log must not be accessed")
            original_open = Path.open
            denied = []

            def protect_project(path, *args, **kwargs):
                if path == old_log or (project in path.parents and path.suffix.lower() in {".txt", ".log"}):
                    denied.append(str(path))
                    raise AssertionError("Diagnostic attempted to access the production log folder.")
                return original_open(path, *args, **kwargs)

            for change in ("binding", "channel", "deleted"):
                with self.subTest(change=change), mock.patch.object(Path, "open", protect_project):
                    node = diagnostic_node(scene)
                    context = snapshot_context(node)
                    frozen_context = copy.deepcopy(context)
                    updated = node._picker_state()
                    updated["last_log_path"] = str(old_log)
                    if change == "binding":
                        updated["picker_shots"][0]["bound_shot_uuid"] = str(uuid.uuid4())
                    elif change == "channel":
                        updated["channel_uuid"] = str(uuid.uuid4())
                    else:
                        updated["picker_shots"] = updated["picker_shots"][1:]
                        updated["active_picker_shot_uuid"] = updated["picker_shots"][0]["workspace_uuid"]
                        updated["shot_uuid"] = updated["picker_shots"][0]["bound_shot_uuid"]
                    expected = picker._parse_state(updated)
                    node._write_state(updated)
                    current = node._picker_state()
                    self.assertTrue(current["operation_invalidated"])
                    self.assertTrue(node._hmb_cancel_requested.is_set())
                    self.assertEqual(node._hmb_active_operation, frozen_context)
                    self.assertEqual(current["operation_id"], context.operation_id)
                    self.assertEqual(current["active_picker_shot_uuid"], expected["active_picker_shot_uuid"])
                    self.assertEqual(current["channel_uuid"], expected["channel_uuid"])
                    self.assertEqual([(r["workspace_uuid"], r["bound_shot_uuid"]) for r in current["picker_shots"]],
                                     [(r["workspace_uuid"], r["bound_shot_uuid"]) for r in expected["picker_shots"]])
                    diagnostic = Path(current["last_log_path"])
                    self.assertIn(base / "local", diagnostic.parents)
                    self.assertEqual(diagnostic.suffix, ".txt")
                    text = diagnostic.read_text(encoding="utf-8")
                    evidence = json.loads(text[text.index("{"):])
                    self.assertEqual(evidence["operation_id"], context.operation_id)
                    self.assertEqual(evidence["captured"], {
                        "workspace_uuid": context.picker_shot_uuid, "bound_shot_uuid": context.target_bound_shot_uuid,
                        "channel_uuid": context.target_channel_uuid, "state_revision": context.accepted_state_revision})
                    target = next((r for r in expected["picker_shots"] if r["workspace_uuid"] == context.picker_shot_uuid), None)
                    self.assertEqual(evidence["current"]["captured_workspace_present"], target is not None)
                    self.assertEqual(evidence["current"]["bound_shot_uuid"], target["bound_shot_uuid"] if target else "")
                    self.assertEqual(evidence["current"]["channel_uuid"], expected["channel_uuid"])
                    self.assertEqual(evidence["current"]["active_workspace_uuid"], expected["active_picker_shot_uuid"])
                    expected_reason = {"binding": "Shot binding changed", "channel": "channel changed", "deleted": "captured workspace removed"}[change]
                    self.assertIn(expected_reason, current["operation_invalidation_reason"])
                    warnings = [row for row in current["activity_log"] if row["level"] == "WARNING"]
                    self.assertEqual(len(warnings), 1)
                    self.assertIn(expected_reason, warnings[0]["message"])
                    self.assertEqual(current["snapshots"], [])
            self.assertEqual(denied, [])
            self.assertEqual(scene.read_bytes(), b"preserved scene")
            self.assertEqual(old_log.read_bytes(), b"existing project log must not be accessed")
            self.assertEqual(set(project.iterdir()), {scene, old_log})

    def test_repeated_and_terminal_writes_keep_first_precise_invalidation(self):
        with tempfile.TemporaryDirectory(prefix="hmb-diagnostic-terminal-") as temporary, \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": temporary}), \
                mock.patch.object(picker, "_request_parameter_value", return_value=False):
            scene = Path(temporary) / "scene.mb"
            scene.write_bytes(b"scene")
            node = diagnostic_node(scene)
            context = snapshot_context(node)
            updated = node._picker_state()
            updated["picker_shots"][0]["bound_shot_uuid"] = str(uuid.uuid4())
            node._write_state(updated)
            first = node._picker_state()
            reason = first["operation_invalidation_reason"]
            path = Path(first["last_log_path"])
            evidence = path.read_bytes()
            for _ in range(4):
                stale_echo = node._picker_state()
                stale_echo["last_log_path"] = "//unavailable-server/production/source.log"
                node._write_state(stale_echo)
            with self.assertRaises(picker._StaleOperationError) as failure:
                node._assert_operation_current(context, "Original Snapshot shared capture wait")
            self.assertIn("Original Snapshot shared capture wait", str(failure.exception))
            node._set_stale_discarded_state(context, str(failure.exception))
            terminal = node._picker_state()
            self.assertEqual(terminal["operation_invalidation_reason"], reason)
            self.assertEqual(terminal["message"], reason)
            self.assertEqual(terminal["last_log_path"], first["last_log_path"])
            self.assertEqual(path.read_bytes(), evidence, "Terminal/repeated writes must not append duplicate evidence.")
            self.assertEqual(len(list(path.parent.glob("maya_invalidation_*.txt"))), 1)
            routing_warnings = [row for row in terminal["activity_log"] if "Shot binding changed" in row["message"]]
            self.assertEqual(len(routing_warnings), 1)
            self.assertEqual(node._hmb_active_operation, context)
            self.assertEqual(terminal["snapshots"], [])
            self.assertEqual(terminal["scene_stage"], "OUTLINER_READY")
            self.assertFalse(any(row["level"] == "SUCCESS" for row in terminal["activity_log"]))


if __name__ == "__main__":
    unittest.main()
