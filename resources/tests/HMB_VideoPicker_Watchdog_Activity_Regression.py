"""Real watchdog methods, virtual deadlines, and private output files only.

No Maya/Blender process, user graph, network, or model invocation is performed.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker


class Controller:
    _wait_for_process_with_progress = picker.HMBVideoPickerLibrary._wait_for_process_with_progress
    _clean_console_line = staticmethod(picker.HMBVideoPickerLibrary._clean_console_line)
    _maya_console_level = staticmethod(picker.HMBVideoPickerLibrary._maya_console_level)
    _blender_execute_job = picker.HMBVideoPickerLibrary._blender_execute_job

    def __init__(self):
        self.state = {}
        self._hmb_cancel_requested = threading.Event()
        self.active = None

    def _picker_state(self): return copy.deepcopy(self.state)
    def _write_state(self, state): self.state = copy.deepcopy(state); return self.state
    def _assert_operation_current(self, *_args): pass
    def _register_cleanup_dir(self, _path): pass
    def _register_active_process(self, process, _label): self.active = process
    def _clear_active_process(self, process):
        assert self.active is process
        self.active = None


class Clock:
    def __init__(self): self.value = 0.0
    def monotonic(self): return self.value
    def sleep(self, _seconds): self.value += 1.0


class WatchdogActivityTests(unittest.TestCase):
    def run_watchdog(self, *, complete_at=None, log_interval=None, cpu=None,
                     cancel_at=None, json_interval=None, stable_json=False,
                     json_start_at=0, json_until=None):
        clock, node, killed, cpu_reads = Clock(), Controller(), [], []
        with tempfile.TemporaryDirectory(prefix="hmb-watchdog-activity-") as temporary:
            root = Path(temporary)
            log = root / "shared-capture.log"
            log.write_text("external command header\n", encoding="utf-8")
            progress = root / "capture.progress.json"
            if stable_json:
                progress.write_text(json.dumps({"stage": "preparing", "time": 1}), encoding="utf-8")

            class Process:
                pid = 42424242
                last_logged = -1
                last_json = -1

                def poll(self):
                    if log_interval:
                        bucket = int(clock.value // log_interval)
                        if bucket != self.last_logged:
                            self.last_logged = bucket
                            with log.open("a", encoding="utf-8") as output:
                                output.write(f"Maya is preparing object {bucket}\n")
                    if (json_interval and clock.value >= json_start_at
                            and (json_until is None or clock.value <= json_until)):
                        bucket = int(clock.value // json_interval)
                        if bucket != self.last_json:
                            self.last_json = bucket
                            progress.write_text(json.dumps({"stage": "preparing", "object": bucket}), encoding="utf-8")
                    if cancel_at is not None and clock.value >= cancel_at:
                        node._hmb_cancel_requested.set()
                    return 0 if complete_at is not None and clock.value >= complete_at else None

            process = Process()

            def sample_cpu(_process):
                self.assertIs(_process, process)
                cpu_reads.append(clock.value)
                return cpu(clock.value) if cpu else None

            fake_time = SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep,
                                        strftime=time.strftime, time=time.time)
            with patch.object(picker, "time", fake_time), \
                    patch.object(picker, "_process_cpu_seconds", side_effect=sample_cpu), \
                    patch.object(picker, "_terminate_process", side_effect=lambda item: killed.append(item)), \
                    patch.object(socket, "create_connection", side_effect=AssertionError("No network")):
                try:
                    result = node._wait_for_process_with_progress(
                        process, progress, picker.PLAYBLAST_OVERALL_TIMEOUT_SECONDS,
                        picker.PLAYBLAST_STALL_TIMEOUT_SECONDS, "Maya Original Preview",
                        activity_paths=(root / "frames", log),
                    )
                    error = None
                except (TimeoutError, RuntimeError) as exc:
                    result, error = None, exc
            return SimpleNamespace(result=result, error=error, elapsed=clock.value,
                                   state=node.state, killed=killed, cpu_reads=cpu_reads)

    def test_log_only_activity_survives_multiple_stall_windows(self):
        result = self.run_watchdog(complete_at=1800, log_interval=100)
        self.assertEqual(result.result, 0)
        self.assertIsNone(result.error)
        self.assertFalse(result.killed)
        self.assertIn("output activity detected", result.state["activity_log_text"])

    def test_static_log_and_ui_heartbeats_do_not_keep_process_alive(self):
        result = self.run_watchdog()
        self.assertIsInstance(result.error, TimeoutError)
        self.assertIn("made no progress for 600 seconds", str(result.error))
        self.assertEqual(result.elapsed, 601)
        self.assertEqual(len(result.killed), 1)
        self.assertIn("[heartbeat]", result.state["activity_log_text"])

    def test_identical_json_is_not_new_progress(self):
        result = self.run_watchdog(stable_json=True)
        self.assertEqual(result.elapsed, 601)
        self.assertIn("made no progress", str(result.error))

    def test_cpu_only_activity_survives_silent_first_frame(self):
        result = self.run_watchdog(complete_at=1800, cpu=lambda elapsed: elapsed / 2)
        self.assertEqual(result.result, 0)
        self.assertFalse(result.killed)
        self.assertIn("CPU activity detected", result.state["activity_log_text"])
        self.assertGreaterEqual(min(result.cpu_reads), 300)
        self.assertTrue(all(b - a >= 30 for a, b in zip(result.cpu_reads, result.cpu_reads[1:])))

    def test_nonzero_cpu_baseline_is_not_progress(self):
        result = self.run_watchdog(cpu=lambda _elapsed: 120.0)
        self.assertEqual(result.elapsed, 601)
        self.assertIn("made no progress", str(result.error))

    def test_cpu_that_stops_eventually_hits_the_unchanged_stall_window(self):
        result = self.run_watchdog(cpu=lambda elapsed: min(elapsed, 400))
        self.assertIsInstance(result.error, TimeoutError)
        self.assertIn("made no progress for 600 seconds", str(result.error))
        # CPU stops at400; the next30-second sample observes its final increase
        # at420. The stall deadline remains600 seconds after that observation.
        self.assertEqual(result.elapsed, 1021)
        self.assertLessEqual(result.elapsed - 400, 600 + 30 + 1)
        self.assertEqual(len(result.killed), 1)

    def test_continuous_cpu_still_hits_overall_deadline(self):
        result = self.run_watchdog(cpu=lambda elapsed: elapsed)
        self.assertIsInstance(result.error, TimeoutError)
        self.assertIn("exceeded 7200 seconds", str(result.error))
        self.assertEqual(result.elapsed, 7201)
        self.assertEqual(len(result.killed), 1)

    def test_continuous_log_still_hits_overall_deadline(self):
        result = self.run_watchdog(log_interval=100)
        self.assertIn("exceeded 7200 seconds", str(result.error))
        self.assertEqual(result.elapsed, 7201)
        self.assertEqual(len(result.killed), 1)

    def test_stop_wins_during_active_cpu_and_log_output(self):
        result = self.run_watchdog(log_interval=100, cpu=lambda elapsed: elapsed, cancel_at=700)
        self.assertIsInstance(result.error, RuntimeError)
        self.assertIn("cancelled by user", str(result.error))
        self.assertLessEqual(result.elapsed, 701)
        self.assertEqual(len(result.killed), 1)

    def test_primary_json_avoids_cpu_sampling(self):
        result = self.run_watchdog(complete_at=1800, json_interval=100, cpu=lambda elapsed: elapsed)
        self.assertEqual(result.result, 0)
        self.assertEqual(result.cpu_reads, [])

    def test_resumed_primary_progress_discards_the_previous_cpu_baseline(self):
        result = self.run_watchdog(cpu=lambda elapsed: min(elapsed, 400),
                                   json_interval=50, json_start_at=350, json_until=500)
        self.assertIn("made no progress for 600 seconds", str(result.error))
        # The final JSON written at500 is read at501. Old CPU work before that
        # JSON must not extend the deadline when the fallback gate opens again.
        self.assertEqual(result.elapsed, 1102)
        self.assertEqual(len(result.killed), 1)

    def test_absent_or_unavailable_cpu_handle_is_not_activity(self):
        self.assertIsNone(picker._process_cpu_seconds(SimpleNamespace()))
        with patch.object(picker, "_windows_process_cpu_query", return_value=None):
            self.assertIsNone(picker._process_cpu_seconds(SimpleNamespace(_handle=1)))

    def test_cpu_query_failure_is_not_activity(self):
        import ctypes
        from ctypes import wintypes
        for outcome in (False, OSError("closed handle")):
            query = lambda *_args: False
            with patch.object(picker, "_windows_process_cpu_query", return_value=(ctypes, wintypes, query)):
                if isinstance(outcome, OSError):
                    def failure(*_args): raise outcome
                    with patch.object(picker, "_windows_process_cpu_query", return_value=(ctypes, wintypes, failure)):
                        self.assertIsNone(picker._process_cpu_seconds(SimpleNamespace(_handle=1)))
                else:
                    self.assertIsNone(picker._process_cpu_seconds(SimpleNamespace(_handle=1)))

    @unittest.skipUnless(os.name == "nt", "GetProcessTimes is Windows-only")
    def test_real_windows_cpu_read_is_noninvasive(self):
        current_process = SimpleNamespace(_handle=-1)  # Windows current-process pseudo handle.
        first = picker._process_cpu_seconds(current_process)
        self.assertIsNotNone(first)
        deadline = time.process_time() + 0.025
        while time.process_time() < deadline:
            sum(range(500))
        second = picker._process_cpu_seconds(current_process)
        self.assertGreater(second, first)

    def test_blender_watchdog_watches_its_real_stdout_log(self):
        with tempfile.TemporaryDirectory(prefix="hmb-watchdog-blender-") as temporary:
            root = Path(temporary)
            scene = root / "fixture.blend"
            scene.write_bytes(b"isolated fixture")
            node, launched, watched = Controller(), [], []

            class ReachedWatchdog(Exception): pass

            def launch(_command, **kwargs):
                launched.append(kwargs)
                return SimpleNamespace(pid=42424242)

            def wait(_process, _progress, overall, stall, label, **kwargs):
                watched.extend(kwargs["activity_paths"])
                self.assertEqual((overall, stall, label), (7200, 600, "Blender snapshot"))
                raise ReachedWatchdog()

            node._wait_for_process_with_progress = wait
            with patch.object(picker, "_find_blender", return_value=root / "blender.exe"), \
                    patch.object(picker, "_blender_display_version", return_value="Fixture"), \
                    patch.object(picker.subprocess, "Popen", side_effect=launch):
                with self.assertRaises(ReachedWatchdog):
                    node._blender_execute_job(scene, "snapshot", {}, None)
            self.assertEqual(len(launched), 1)
            self.assertIn(Path(launched[0]["stdout"].name), watched)
            self.assertTrue(any(path.name == "frames" for path in watched))
            self.assertIsNone(node.active)


if __name__ == "__main__":
    unittest.main(verbosity=2)
