"""Offline timing transitions retain only public numeric diagnostics."""
from __future__ import annotations
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import HMB_Agent_Cold_Source_Readiness_Regression as cold
import _hmb_sound as sound


class ExecutionTiming(unittest.TestCase):
    def setUp(self):
        self.node, _prompt = cold.fixture.manager()
        self.phases = []
        self.node._set_agent_execution_phase = self.phases.append
        self.node._hmb_timing_started = None
        self.node._hmb_timing_finished = None
        self.node._hmb_stage_durations = {}
        self.node._hmb_execution_stage = ""

    def test_stage_durations_total_and_first_chunk_are_separate(self):
        with patch.object(cold.module.time, "monotonic", side_effect=[10.0, 12.0, 15.0]):
            self.node._set_hmb_execution_stage("policy_verify")
            self.node._set_hmb_execution_stage("inference")
            self.node._hmb_first_native_chunk_seconds = 3.0
            self.node._set_hmb_execution_stage("complete")
        value = self.node._hmb_timing_snapshot()
        self.assertEqual(value, {"total_seconds": 5.0,
            "stages_seconds": {"policy_verify": 2.0, "inference": 3.0}, "first_native_chunk_seconds": 3.0,
            "native_inference_start_seconds": 2.0, "first_native_chunk_after_inference_seconds": 1.0})
        self.assertEqual(self.phases, ["authorizing", "running", ""])
        self.node._set_hmb_execution_stage("private-policy-path-or-error")
        self.assertEqual(self.node._hmb_timing_snapshot(), value)

    def test_completed_worker_clears_header_running_without_exposing_private_state(self):
        self.node._hmb_execution_stage = ""
        key = self.node._hmb_slot_key("channel", "shot")
        worker = type("Worker", (), {"_hmb_execution_stage": "complete"})()
        self.node._hmb_shot_workers[key] = worker
        value = self.node._hmb_widget_value({"channel_uuid": "channel", "shot_uuid": "shot", "number": 1}, {}, "running")
        self.assertEqual(value["execution_phase"], "")
        self.assertNotIn("execution_stage", value)


class SoundPreparation(unittest.TestCase):
    def test_typed_sound_preparation_uses_existing_exact_owner_wait_once(self):
        case = cold.ColdSourceReadinessTests("test_ready_source_is_read_once_without_preparation_replay")
        case.setUp()
        try:
            reads = []
            def document(**_kwargs):
                reads.append(1)
                if len(reads) < 3:
                    raise sound.SoundPreparingError()
                return case.document
            case.prompt._hmb_prompt_shot_document = document
            case.run_once()
            self.assertEqual(reads, [1, 1, 1])
            self.assertEqual(case.calls, [1])
            case.assert_retained_and_released()
            self.assertFalse(cold.module._hmb_source_is_preparing(ValueError("sound busy preparing")))
            truthy = ValueError("not a boolean authority")
            truthy.hmb_sound_preparing = 1
            self.assertFalse(cold.module._hmb_source_is_preparing(truthy))
        finally:
            case.tearDown()

    def test_sound_error_codes_are_fixed_and_paths_never_enter_failure(self):
        failure = ValueError("PRIVATE C:/secret/audio.wav")
        failure.code = "SOUND_SOURCE_CHANGED"
        diagnostic = cold.module._hmb_source_failure(failure)
        self.assertEqual(diagnostic.code, "SOURCE_MEDIA_UNAVAILABLE")
        self.assertNotIn("PRIVATE", str(diagnostic))
        self.assertNotIn("audio.wav", str(diagnostic))

    def test_sound_pending_cancel_stops_before_constructing_any_native_worker(self):
        case = cold.ColdSourceReadinessTests("test_ready_source_is_read_once_without_preparation_replay")
        case.setUp()
        class SoundPreparing(ValueError):
            hmb_sound_preparing = True
        try:
            def document(**_kwargs):
                case.generator.is_cancellation_requested = True
                raise SoundPreparing("PRIVATE sound pending")
            case.prompt._hmb_prompt_shot_document = document
            with self.assertRaises(cold.asyncio.CancelledError):
                case.run_once(generator=case.generator)
            self.assertEqual(case.calls, [])
            self.assertEqual(case.workers, [])
            case.assert_retained_and_released()
        finally:
            case.tearDown()

    def test_failed_sound_add_never_retries_or_runs_the_previous_selection(self):
        case = cold.ColdSourceReadinessTests("test_ready_source_is_read_once_without_preparation_replay")
        case.setUp()
        try:
            calls = []
            def document(**_kwargs):
                calls.append(1)
                raise sound.SoundError("SOUND_PREPARATION_FAILED", "PRIVATE old selected source must not run")
            case.prompt._hmb_prompt_shot_document = document
            with self.assertRaises(cold.module._HMBSourcePreparationError):
                case.run_once()
            self.assertEqual(calls, [1])
            case.assert_failed_before_model("SOURCE_MEDIA_UNAVAILABLE")
        finally:
            case.tearDown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
