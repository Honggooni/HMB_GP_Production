"""READ completion survives Maya shutdown and inherited stdout without hiding errors.

Runs production helpers in an SDK-free namespace. The only real subprocesses are
short-lived Python fixtures; no Maya, Desktop, network, or provider is invoked.
"""
from __future__ import annotations

import ast
import copy
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "HMBVideoPickerLibrary.py"


def production_helpers() -> dict:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"), filename=str(SOURCE))
    names = {
        "_clean", "_scene_path_text", "_norm_path", "_scene_path_key", "_read_json",
        "_validated_maya_read_result", "_close_drained_process_stdout", "_progress_signature",
    }
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == names, "READ completion production helpers are missing"
    node_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HMBVideoPickerLibrary")
    functions.append(next(node for node in node_class.body if isinstance(node, ast.FunctionDef) and node.name == "_wait_for_process_with_progress"))
    constants = {
        "READ_COMPLETION_GRACE_SECONDS", "PROCESS_OUTPUT_ACTIVITY_SCAN_INTERVAL_SECONDS",
        "PROCESS_OUTPUT_ACTIVITY_QUIET_FRACTION",
    }
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)]
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                              *assignments, *functions], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(Path=Path, json=json, math=math, os=os, re=re, queue=queue, time=time,
                     urlparse=urlparse, unquote=unquote)
    namespace.update({
        "_diagnostic_exception": lambda *_: None,
        "_filesystem_activity_snapshot": lambda _: ("unchanged", 0, 0),
        "_process_cpu_seconds": lambda _: None,
        "_append_activity_log": lambda state, level, text: state.setdefault("logs", []).append((level, text)),
        "_terminate_process": lambda process: process.terminate_owned(),
    })
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


class Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Process:
    def __init__(self, returncode=None, stoppable=True):
        self.returncode = returncode
        self.stoppable = stoppable
        self.terminations = 0

    def poll(self):
        return self.returncode

    def terminate_owned(self):
        self.terminations += 1
        if self.stoppable:
            self.returncode = -9


class Node:
    def __init__(self):
        self._hmb_cancel_requested = threading.Event()
        self.state = {}
        self.writes = []

    def _picker_state(self):
        return copy.deepcopy(self.state)

    def _write_state(self, state):
        self.state = copy.deepcopy(state)
        self.writes.append(copy.deepcopy(state))

    @staticmethod
    def _clean_console_line(value):
        return str(value).strip()

    @staticmethod
    def _maya_console_level(_value):
        return "INFO"


class ReadCompletionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="hmb-read-completion-")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.scene = self.base / "shot_02.mb"
        self.result = self.base / "private_read_result.json"
        self.progress = self.base / "private_progress.json"
        self.ns = production_helpers()
        self.valid = {
            "ok": True, "operation": "scan", "scene_path": str(self.scene),
            "start_frame": 101.0, "end_frame": 155.0, "current_frame": 101.0, "fps": 24.0,
            "outliner_nodes": [{"name": "FireflyAa1", "full_path": "|FireflyAa1"}],
            "cameras": [{"name": "CAM_shot_02", "full_path": "|CAM_shot_02"}],
        }

    def write_result(self, data):
        self.result.write_text(json.dumps(data), encoding="utf-8")

    def validate(self):
        return self.ns["_validated_maya_read_result"](self.result, self.scene)

    def wait(self, process, *, stage="scan_complete", callback=None, node=None):
        self.progress.write_text(json.dumps({"stage": stage, "message": stage}), encoding="utf-8")
        self.clock = Clock()
        self.ns["time"] = self.clock
        self.node = node or Node()
        wait = types.MethodType(self.ns["_wait_for_process_with_progress"], self.node)
        return wait(process, self.progress, overall_timeout=5.0, stall_timeout=4.0,
                    operation_label="Maya READ", read_result_check=callback)

    def test_complete_metadata_is_retained_without_rewriting(self):
        self.write_result(self.valid)
        before = self.result.read_bytes()
        self.assertEqual(self.validate(), self.valid)
        self.assertEqual(self.result.read_bytes(), before)

    def test_missing_partial_or_non_object_result_is_not_completion(self):
        self.assertIsNone(self.validate())
        for text in ('{"ok":', "[]", "null", "not-json"):
            with self.subTest(text=text):
                self.result.write_text(text, encoding="utf-8")
                self.assertIsNone(self.validate())

    def test_previous_shot_result_is_not_completion(self):
        data = dict(self.valid, scene_path=str(self.base / "shot_01.mb"))
        self.write_result(data)
        self.assertIsNone(self.validate())

    def test_invalid_metadata_is_not_completion(self):
        cases = [("ok", False), ("ok", 1), ("operation", "render"),
                 ("scene_path", ""), ("outliner_nodes", {}), ("outliner_nodes", [None]),
                 ("cameras", None), ("cameras", ["CAM"]), ("end_frame", 100),
                 ("fps", 0), ("fps", -24), ("current_frame", "invalid")]
        cases += [(field, invalid) for field in ("start_frame", "end_frame", "current_frame", "fps")
                  for invalid in (float("nan"), float("inf"), -float("inf"), None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.write_result(dict(self.valid, **{field: value}))
                self.assertIsNone(self.validate())
        for field in self.valid:
            with self.subTest(missing=field):
                self.write_result({key: value for key, value in self.valid.items() if key != field})
                self.assertIsNone(self.validate())

    def test_valid_metadata_unblocks_owned_worker_after_grace(self):
        self.write_result(self.valid)
        worker = Process()
        self.assertEqual(self.wait(worker, callback=self.validate), 0)
        self.assertEqual(worker.terminations, 1)
        self.assertGreaterEqual(self.clock.now - 100, self.ns["READ_COMPLETION_GRACE_SECONDS"])
        self.assertLess(self.clock.now - 100, self.ns["READ_COMPLETION_GRACE_SECONDS"] + 0.2)
        self.assertEqual(self.validate(), self.valid)

    def test_verified_scan_survives_shutdown_error(self):
        self.write_result(self.valid)
        worker = Process(returncode=-1073741819)
        self.assertEqual(self.wait(worker, callback=self.validate), 0)
        self.assertEqual(worker.terminations, 0)
        self.assertTrue(any("shutdown error" in text for _, text in self.node.state["logs"]))

    def test_scan_marker_without_valid_result_still_times_out(self):
        for data in (None, dict(self.valid, scene_path=str(self.base / "shot_01.mb")), dict(self.valid, fps=0)):
            with self.subTest(data=data):
                if data is not None:
                    self.write_result(data)
                elif self.result.exists():
                    self.result.unlink()
                worker = Process()
                with self.assertRaises(TimeoutError):
                    self.wait(worker, callback=self.validate)
                self.assertEqual(worker.terminations, 1)

    def test_metadata_without_terminal_scan_marker_does_not_hide_exit_error(self):
        self.write_result(self.valid)
        calls = []

        def check():
            calls.append(True)
            return self.validate()

        worker = Process(returncode=23)
        self.assertEqual(self.wait(worker, stage="checking_visibility", callback=check), 23)
        self.assertEqual(calls, [])
        self.assertEqual(worker.terminations, 0)

    def test_ordinary_render_error_is_preserved(self):
        for stage in ("render_complete", "scan_complete"):
            with self.subTest(stage=stage):
                worker = Process(returncode=17)
                self.assertEqual(self.wait(worker, stage=stage), 17)
                self.assertEqual(worker.terminations, 0)

    def test_cancellation_cannot_become_success_after_metadata_validation(self):
        self.write_result(self.valid)
        node = Node()
        worker = Process()

        def check_and_cancel():
            node._hmb_cancel_requested.set()
            return self.validate()

        with self.assertRaisesRegex(RuntimeError, "cancelled by user"):
            self.wait(worker, callback=check_and_cancel, node=node)
        self.assertEqual(worker.terminations, 1)

    def test_preexisting_cancel_does_not_read_or_adopt_result(self):
        node = Node()
        node._hmb_cancel_requested.set()
        worker = Process(returncode=0)

        def forbidden():
            self.fail("Cancelled READ must not adopt completion")

        with self.assertRaisesRegex(RuntimeError, "cancelled by user"):
            self.wait(worker, callback=forbidden, node=node)

    def test_verified_metadata_does_not_claim_success_if_owned_worker_remains_alive(self):
        self.write_result(self.valid)
        worker = Process(stoppable=False)
        with self.assertRaisesRegex(RuntimeError, "could not be stopped"):
            self.wait(worker, callback=self.validate)
        self.assertEqual(worker.terminations, 1)

    def test_stdout_close_waits_for_reader_ownership(self):
        class Stream:
            closed = False

            def close(self):
                self.closed = True

        for alive in (True, False, None):
            with self.subTest(reader_alive=alive):
                stream = Stream()
                worker = types.SimpleNamespace(stdout=stream)
                reader = types.SimpleNamespace(is_alive=lambda: alive) if alive is not None else None
                self.assertEqual(self.ns["_close_drained_process_stdout"](worker, reader), alive is not True)
                self.assertEqual(stream.closed, alive is not True)

    def test_inherited_stdout_remains_bounded_after_worker_exit(self):
        # The grandchild inherits stdout and outlives its parent. This recreates
        # a Maya plug-in holding the pipe while the reader owns readline's lock.
        release = self.base / "release-grandchild"
        grandchild_code = (
            "import pathlib,sys,time\n"
            "release=pathlib.Path(sys.argv[1])\n"
            "print('PIPE_HELD', flush=True)\n"
            "deadline=time.monotonic()+8\n"
            "while not release.exists() and time.monotonic()<deadline: time.sleep(.02)\n"
        )
        parent_code = (
            "import subprocess,sys\n"
            "subprocess.Popen([sys.executable,'-u','-c',sys.argv[1],sys.argv[2]],"
            "stdout=sys.stdout,stderr=sys.stdout)\n"
        )
        worker = subprocess.Popen([sys.executable, "-u", "-c", parent_code, grandchild_code, str(release)],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ready = threading.Event()
        errors = []

        def drain():
            try:
                for line in worker.stdout:
                    if "PIPE_HELD" in line:
                        ready.set()
            except Exception as exc:
                errors.append(exc)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        close_finished = threading.Event()
        outcome = []

        def close_pipe():
            try:
                outcome.append(self.ns["_close_drained_process_stdout"](worker, reader))
            finally:
                close_finished.set()

        closer = None
        try:
            self.assertTrue(ready.wait(5), "Inherited pipe fixture did not start")
            self.assertEqual(worker.wait(timeout=5), 0)
            self.assertTrue(reader.is_alive(), "Fixture must retain a blocked stdout reader after parent exits")
            closer = threading.Thread(target=close_pipe, daemon=True)
            closer.start()
            self.assertTrue(close_finished.wait(0.5), "stdout close blocked on the live reader lock")
            self.assertEqual(outcome, [False])
            self.assertFalse(worker.stdout.closed)
        finally:
            release.touch()
            reader.join(timeout=10)
            if closer is not None:
                closer.join(timeout=2)
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
            if not reader.is_alive():
                self.ns["_close_drained_process_stdout"](worker, reader)
        self.assertFalse(reader.is_alive(), "Fixture pipe owner failed to exit")
        self.assertEqual(errors, [])
        self.assertTrue(worker.stdout.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
