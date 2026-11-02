"""Offline cold-source readiness through the real Agent per-Shot dispatcher.

The graph fixture owns five exact Shot subscriptions. Only source documents and
the native worker/model boundary are doubles; preparation, cancellation, task
serialization, failure classification and retained Shot publication are real.
No provider, policy, user workflow, credential or operational server is used.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "agent_cold_source_fixture", Path(__file__).with_name("HMB_Agent_Multishot_Regression.py"))
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
module = fixture.module
KEY = "channel\x1fshot-1"
OTHER = "channel\x1fshot-2"


class SourcePreparing(ValueError):
    hmb_image_asset_selection_preparing = True


class PickerPreparing(ValueError):
    hmb_picker_media_preparing = True


class TruthyPreparing(ValueError):
    hmb_image_asset_selection_preparing = 1


class ColdSourceReadinessTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(socket, "create_connection", fixture.forbidden),
            patch.object(socket.socket, "connect", fixture.offline_connect),
            patch.object(urllib.request, "urlopen", fixture.forbidden),
            patch.object(module, "_HMB_SOURCE_PREPARE_TIMEOUT_SECONDS", .045),
            patch.object(module, "_HMB_SOURCE_PREPARE_RETRY_SECONDS", .002),
        ]
        for item in self.patches:
            item.start()
        self.node, self.prompt = fixture.manager()
        self.node._native_parameter_value = lambda name, default=None: self.node.parameter_values.get(name, default)
        self.node._refresh_hmb_execution_result_messages = Mock()
        self.node._hmb_notify_shot_preview = Mock()
        self.node._hmb_shot_slots[KEY]["values"].update(
            prompt="literal {source} 0 OFF", agent_memory={"zero": 0, "off": False, "none": None},
            source_uids=["unchanged-first", "unchanged-second"])
        self.authored = copy.deepcopy(self.node._hmb_shot_slots[KEY]["values"])
        self.node._hmb_shot_slots[OTHER]["outputs"] = {"output": "Other Shot retained"}
        self.node._hmb_shot_results[OTHER] = {"text": "Other Shot retained"}
        self.other = copy.deepcopy(self.node._hmb_shot_slots[OTHER])
        self.calls = []
        self.workers = []
        self.documents = []
        self.inflight = self.max_inflight = 0
        self.worker_delay = .001
        self.generator = SimpleNamespace(_hmb_node_deleted=False, is_cancellation_requested=False)
        self.document = {"identity": {"channel_uuid": "channel", "shot_uuid": "shot-1"},
                         "literal": "keep {source} 0 OFF", "source_uids": ["unchanged-first", "unchanged-second"]}

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def factory(self, owner, prompt_owner, document, subscription, slot, generator):
        self.assertIs(owner, self.node)
        self.assertIs(prompt_owner, self.prompt)
        number = len(self.workers) + 1
        text = "One deterministic Agent result " + str(number)
        result = {"status": "succeeded", "run_id": "offline-cold-source-" + str(number),
                  "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
        self.documents.append(copy.deepcopy(document))
        async def run():
            self.calls.append(number)
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            try:
                await asyncio.sleep(self.worker_delay)
            finally:
                self.inflight -= 1
        worker = SimpleNamespace(parameter_values={"ephemeral": "clear"},
            parameter_output_values={"output": text, "logs": "", "agent": {}},
            _hmb_shot_policy_identity={}, _hmb_agent_reference_observation_snapshot=lambda: {},
            _hmb_execution_result_snapshot=lambda: copy.deepcopy(result),
            _clear_hmb_runtime_policy=Mock(), _hmb_aprocess_locked=run)
        self.workers.append(worker)
        return worker

    async def run_shot(self, *, generator=None):
        return await self.node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-1",
            prompt_owner=self.prompt, generator=generator)

    def run_once(self, *, generator=None):
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.factory):
            return asyncio.run(self.run_shot(generator=generator))

    def assert_retained_and_released(self):
        self.assertFalse(self.node._hmb_shot_execution_locks[KEY].locked())
        self.assertNotIn(KEY, self.node._hmb_shot_workers)
        self.assertEqual(self.node._hmb_shot_slots[KEY]["values"], self.authored)
        self.assertEqual(self.node._hmb_shot_slots[OTHER], self.other)
        self.assertEqual(self.node._hmb_shot_results[OTHER], {"text": "Other Shot retained"})

    def assert_failed_before_model(self, code):
        self.assert_retained_and_released()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.workers, [])
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "failed")
        result = self.node._hmb_shot_slots[KEY]["result"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["code"], code)
        self.assertNotEqual(result["message"], module._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE)
        self.assertNotIn("PRIVATE", result["message"])
        return result

    def test_typed_image_preparing_then_ready_runs_one_exact_worker(self):
        reads = []
        def get_document(**kwargs):
            self.assertEqual(kwargs, {"channel_uuid": "channel", "shot_uuid": "shot-1"})
            reads.append(1)
            if len(reads) < 3:
                self.assertEqual(self.node._hmb_shot_run_status[KEY], "preparing")
                self.assertTrue(getattr(self.node._hmb_shot_workers[KEY], "_hmb_source_preparing", False))
                self.assertEqual(self.calls, [])
                raise SourcePreparing("PRIVATE cold cache pending")
            return copy.deepcopy(self.document)
        self.prompt._hmb_prompt_shot_document = get_document
        record = self.run_once()
        self.assertEqual(len(reads), 3)
        self.assertEqual(self.calls, [1])
        self.assertEqual(self.documents, [self.document])
        self.assertEqual(record["text"], "One deterministic Agent result 1")
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "succeeded")
        self.assert_retained_and_released()

    def test_typed_picker_preparing_then_ready_uses_same_bounded_path(self):
        reads = []
        def get_document(**_kwargs):
            reads.append(1)
            if len(reads) == 1:
                raise PickerPreparing("PRIVATE picker decoding")
            return copy.deepcopy(self.document)
        self.prompt._hmb_prompt_shot_document = get_document
        self.run_once()
        self.assertEqual(len(reads), 2)
        self.assertEqual(self.calls, [1])
        self.assert_retained_and_released()

    def test_ready_source_is_read_once_without_preparation_replay(self):
        self.prompt._hmb_prompt_shot_document = Mock(return_value=copy.deepcopy(self.document))
        self.run_once()
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assertEqual(self.calls, [1])
        self.assert_retained_and_released()

    def test_never_ready_source_times_out_with_distinct_safe_code(self):
        self.prompt._hmb_prompt_shot_document = Mock(side_effect=SourcePreparing("PRIVATE internal cache and path"))
        with self.assertRaises(module._HMBSourcePreparationError):
            self.run_once()
        self.assertGreater(self.prompt._hmb_prompt_shot_document.call_count, 1)
        self.assertLess(self.prompt._hmb_prompt_shot_document.call_count, 80)
        self.assert_failed_before_model("SOURCE_PREPARATION_TIMEOUT")

    def test_missing_media_is_not_retried_or_labelled_as_connection(self):
        error = ValueError("ImageAsset exact Shot selected image media is unavailable: PRIVATE source path")
        self.prompt._hmb_prompt_shot_document = Mock(side_effect=error)
        with self.assertRaises(Exception):
            self.run_once()
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assert_failed_before_model("SOURCE_MEDIA_UNAVAILABLE")

    def test_wrong_shot_is_not_retried_and_has_identity_code(self):
        self.prompt._hmb_prompt_shot_document = Mock(side_effect=RuntimeError(
            "ImageAsset exact Shot is no longer in the current catalog."))
        with self.assertRaises(Exception):
            self.run_once()
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assert_failed_before_model("SOURCE_SHOT_IDENTITY_MISMATCH")

    def test_untyped_preparing_word_is_an_ordinary_validation_failure(self):
        self.prompt._hmb_prompt_shot_document = Mock(side_effect=ValueError("PRIVATE says preparing but has no typed flag"))
        with self.assertRaises(Exception):
            self.run_once()
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assert_failed_before_model("SOURCE_VALIDATION_FAILED")

    def test_truthy_nonboolean_preparing_flag_does_not_authorize_retry(self):
        self.prompt._hmb_prompt_shot_document = Mock(side_effect=TruthyPreparing("PRIVATE retry marker 1"))
        with self.assertRaises(Exception):
            self.run_once()
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assert_failed_before_model("SOURCE_VALIDATION_FAILED")

    def test_cancel_selected_reaches_preparation_token_before_worker(self):
        self.node._hmb_shot_channel_subscription = lambda: fixture.subscription(1)
        def get_document(**_kwargs):
            self.node._hmb_handle_shot_action({"kind": "cancel_selected", "request_id": "e" * 32})
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(asyncio.CancelledError):
            self.run_once()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "cancelled")
        self.assert_retained_and_released()

    def test_generator_cancel_during_preparation_never_constructs_worker(self):
        def get_document(**_kwargs):
            self.generator.is_cancellation_requested = True
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(asyncio.CancelledError):
            self.run_once(generator=self.generator)
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()

    def test_removed_prompt_owner_during_wait_is_not_replaced(self):
        reads = []
        def get_document(**_kwargs):
            reads.append(1)
            self.prompt._hmb_node_deleted = True
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(Exception):
            self.run_once()
        self.assertEqual(reads, [1])
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()
        self.assertIn(self.node._hmb_shot_slots[KEY]["result"]["code"],
                      {"SOURCE_PROMPT_OWNER_UNAVAILABLE", "SOURCE_CONNECTION_UNAVAILABLE"})

    def test_replaced_prompt_owner_during_wait_never_uses_its_document(self):
        replacement = SimpleNamespace(_hmb_node_deleted=False, _hmb_prompt_shot_document=Mock())
        def get_document(**_kwargs):
            self.node._hmb_manager_prompt_owner = lambda **_kw: replacement
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(Exception):
            self.run_once()
        replacement._hmb_prompt_shot_document.assert_not_called()
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()

    def test_changed_exact_shot_identity_during_wait_blocks_worker(self):
        def get_document(**_kwargs):
            self.node._hmb_shot_catalog_snapshot["shots"] = [row for row in self.node._hmb_shot_catalog_snapshot["shots"]
                                                            if row["shot_uuid"] != "shot-1"]
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(Exception):
            self.run_once()
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()

    def test_owner_changed_inside_successful_document_read_blocks_worker(self):
        replacement = SimpleNamespace(_hmb_node_deleted=False, _hmb_prompt_shot_document=Mock())
        def get_document(**_kwargs):
            self.node._hmb_manager_prompt_owner = lambda **_kw: replacement
            return copy.deepcopy(self.document)
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(Exception):
            self.run_once()
        replacement._hmb_prompt_shot_document.assert_not_called()
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()

    def test_deleted_agent_during_preparation_does_not_publish_late_failure(self):
        original = copy.deepcopy(self.node._hmb_shot_slots[KEY])
        def get_document(**_kwargs):
            self.node._hmb_node_deleted = True
            raise SourcePreparing("PRIVATE pending")
        self.prompt._hmb_prompt_shot_document = get_document
        with self.assertRaises(asyncio.CancelledError):
            self.run_once()
        self.assertEqual(self.node._hmb_shot_slots[KEY], original)
        self.assertEqual(self.calls, [])
        self.assert_retained_and_released()

    def test_two_concurrent_requests_are_serial_per_exact_shot(self):
        self.worker_delay = .008
        self.prompt._hmb_prompt_shot_document = Mock(return_value=copy.deepcopy(self.document))
        async def run():
            with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.factory):
                return await asyncio.gather(self.run_shot(), self.run_shot())
        records = asyncio.run(run())
        self.assertEqual(self.calls, [1, 2])
        self.assertEqual(self.max_inflight, 1)
        self.assertEqual(len(self.documents), 2)
        self.assertEqual(self.prompt._hmb_prompt_shot_document.call_count, 2)
        self.assertEqual(len({record["result"]["run_id"] for record in records}), 2)
        self.assert_retained_and_released()

    def test_failed_worker_is_never_retried_as_source_preparation(self):
        self.prompt._hmb_prompt_shot_document = Mock(return_value=copy.deepcopy(self.document))
        def bad_factory(*args, **kwargs):
            worker = self.factory(*args, **kwargs)
            async def fail():
                self.calls.append("failed-worker")
                raise SourcePreparing("PRIVATE error raised after model boundary")
            worker._hmb_aprocess_locked = fail
            return worker
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=bad_factory):
            with self.assertRaises(SourcePreparing):
                asyncio.run(self.run_shot())
        self.assertEqual(self.calls, ["failed-worker"])
        self.prompt._hmb_prompt_shot_document.assert_called_once()
        self.assertEqual(len(self.workers), 1)
        self.assert_retained_and_released()


if __name__ == "__main__":
    unittest.main(verbosity=2)
