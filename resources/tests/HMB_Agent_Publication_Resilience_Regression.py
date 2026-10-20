"""Offline terminal fault injection; no model, policy, user graph or network I/O.

Exercise the actual per-Shot admission path and native store/status setters.
Auxiliary failure must not erase a verified result or keep a Shot lock held.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
from contextlib import redirect_stdout
import io
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "agent_publication_fixture", Path(__file__).with_name("HMB_Agent_Multishot_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
module = fixture.module
KEY = "channel\x1fshot-1"
OTHER = "channel\x1fshot-2"


class CleanupAbort(BaseException):
    pass


class PublicationResilienceTests(unittest.TestCase):
    def setUp(self):
        self.guards = [patch.object(socket, "create_connection", fixture.forbidden),
            patch.object(socket.socket, "connect", fixture.offline_connect),
            patch.object(urllib.request, "urlopen", fixture.forbidden)]
        for guard in self.guards:
            guard.start()
        self.node, self.prompt = fixture.manager()
        self.node._native_parameter_value = lambda name, default=None: self.node.parameter_values.get(name, default)
        self.node._refresh_hmb_execution_result_messages = Mock()
        self.node._hmb_notify_shot_preview = Mock()
        self.node._hmb_shot_results[OTHER] = {"text": "Other Shot preserved"}
        self.node._hmb_shot_slots[OTHER]["outputs"] = {"output": "Other Shot preserved"}
        self.other_before = copy.deepcopy(self.node._hmb_shot_slots[OTHER])
        self.calls = []
        self.workers = []
        self.generator = SimpleNamespace(_hmb_node_deleted=False, is_cancellation_requested=False)

    def tearDown(self):
        for guard in reversed(self.guards):
            guard.stop()

    def worker(self, *args):
        number = len(self.workers) + 1
        text = "Exact protected output " + str(number)
        result = {"status": "succeeded", "run_id": "offline-publication-" + str(number),
            "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
        async def run():
            self.calls.append(number)
            await asyncio.sleep(0)
        worker = SimpleNamespace(parameter_values={"transient": "clear"},
            parameter_output_values={"output": text, "logs": "", "agent": {}},
            _hmb_shot_policy_identity={}, _hmb_agent_reference_observation_snapshot=lambda: {},
            _hmb_execution_result_snapshot=lambda: copy.deepcopy(result),
            _clear_hmb_runtime_policy=Mock(), _hmb_aprocess_locked=run)
        self.workers.append(worker)
        return worker

    def test_optional_success_does_not_create_a_shot_warning_document(self):
        before = copy.deepcopy(self.node._hmb_shot_slots)
        callback = Mock()
        self.assertTrue(self.node._hmb_shot_publication_step(KEY, "store", callback))
        callback.assert_called_once()
        self.assertEqual(self.node._hmb_shot_slots, before)

    def test_late_deleted_optional_failure_cannot_change_retained_documents(self):
        self.node._hmb_node_deleted = True
        before = copy.deepcopy(self.node._hmb_shot_slots)
        callback = Mock(side_effect=RuntimeError("late deleted publication"))
        self.assertFalse(self.node._hmb_shot_publication_step(KEY, "store", callback))
        callback.assert_called_once()
        self.assertEqual(self.node._hmb_shot_slots, before)

    def test_success_clears_only_the_resolved_warning(self):
        self.node._hmb_shot_slots[KEY]["publication_warnings"] = {"store": "RuntimeError", "notify": "ValueError"}
        self.assertTrue(self.node._hmb_shot_publication_step(KEY, "store", lambda: None))
        self.assertEqual(self.node._hmb_shot_slots[KEY]["publication_warnings"], {"notify": "ValueError"})
        self.assertTrue(self.node._hmb_shot_publication_step(KEY, "notify", lambda: None))
        self.assertNotIn("publication_warnings", self.node._hmb_shot_slots[KEY])

    def run_once(self, *, generator=True):
        return asyncio.run(self.node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-1",
            prompt_owner=self.prompt, generator=self.generator if generator else None))

    def assert_released(self):
        self.assertFalse(self.node._hmb_shot_execution_locks[KEY].locked())
        self.assertNotIn(KEY, self.node._hmb_shot_workers)
        self.assertEqual(self.node._hmb_shot_results[OTHER], {"text": "Other Shot preserved"})
        self.assertEqual(self.node._hmb_shot_slots[OTHER], self.other_before)

    def assert_success(self, record):
        self.assert_released()
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "succeeded")
        self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["status"], "succeeded")
        self.assertEqual(self.node._hmb_agent_shot_result(channel_uuid="channel", shot_uuid="shot-1"), record)
        self.assertEqual(self.node._hmb_agent_shot_result(channel_uuid="channel", shot_uuid="shot-1",
            generator=self.generator, run_id=record["result"]["run_id"]), record)
        self.assertEqual(record["result"]["output_sha256"], hashlib.sha256(record["text"].encode()).hexdigest())

    def test_terminal_native_status_exception_preserves_result_and_unlocks_next_run(self):
        del self.node._hmb_publish_shot_status
        self.node.parameter_values[module._AGENT_WIDGET_PARAMETER] = self.node._hmb_widget_value(
            {"channel_uuid": "channel", "shot_uuid": "shot-1", "number": 1, "name": "Renamed 1"},
            self.node._hmb_shot_catalog_snapshot)
        original = module._BaseAgent.set_parameter_value
        def setter(owner, name, value, *args, **kwargs):
            if owner is self.node and name == module._AGENT_WIDGET_PARAMETER:
                if value.get("shot_states", {}).get("shot-1") == "succeeded":
                    raise RuntimeError("PRIVATE terminal status failure")
                owner.parameter_values[name] = copy.deepcopy(value)
                return
            return original(owner, name, value, *args, **kwargs)
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker), \
                patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=setter):
            first = self.run_once()
            self.assert_success(first)
            second = asyncio.run(asyncio.wait_for(self.node._hmb_run_agent_shot(channel_uuid="channel",
                shot_uuid="shot-1", prompt_owner=self.prompt, generator=self.generator), .6))
            self.assert_success(second)
        self.assertEqual(self.calls, [1, 2])

    def test_native_store_event_failure_preserves_result_and_retries_without_model(self):
        del self.node._hmb_persist_shot_store
        original = module._BaseAgent.set_parameter_value
        events = []
        def setter(owner, name, value, *args, **kwargs):
            if owner is self.node and name == module._AGENT_SHOT_STORE_PARAMETER:
                events.append(copy.deepcopy(value))
                if len(events) == 1:
                    raise RuntimeError("PRIVATE store event failure")
                owner.parameter_values[name] = copy.deepcopy(value)
                return
            return original(owner, name, value, *args, **kwargs)
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker), \
                patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=setter):
            record = self.run_once()
        self.assert_success(record)
        self.assertEqual(self.calls, [1])
        self.assertEqual(len(events), 2)
        saved = self.node.parameter_values[module._AGENT_SHOT_STORE_PARAMETER]
        self.assertEqual(saved["results"][KEY], record)
        self.assertFalse(saved["slots"][KEY].get("publication_warnings"))
        self.assertFalse(self.node._hmb_shot_store_syncing)

    def test_persistent_store_error_remains_warning_and_later_persist_recovers(self):
        self.node._hmb_persist_shot_store.side_effect = RuntimeError("PRIVATE persistent store")
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker):
            record = self.run_once()
        self.assert_success(record)
        self.assertEqual(self.calls, [1])
        self.assertIn("store", self.node._hmb_shot_slots[KEY]["publication_warnings"])
        del self.node._hmb_persist_shot_store
        def store(owner, name, value, *args, **kwargs):
            owner.parameter_values[name] = copy.deepcopy(value)
        with patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=store):
            self.node._hmb_persist_shot_store()
        self.assertFalse(self.node._hmb_shot_slots[KEY].get("publication_warnings"))
        self.assertEqual(self.node.parameter_values[module._AGENT_SHOT_STORE_PARAMETER]["results"][KEY], record)

    def test_active_native_output_error_preserves_other_outputs_and_result(self):
        self.node._hmb_active_slot_key = KEY
        def setter(owner, name, value, *args, **kwargs):
            if name == "output":
                raise RuntimeError("PRIVATE output display event")
            owner.parameter_values[name] = copy.deepcopy(value)
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker), \
                patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=setter):
            record = self.run_once()
        self.assert_success(record)
        self.assertEqual(self.node.parameter_output_values["output"], record["text"])
        self.assertEqual(self.node._hmb_execution_result["status"], "succeeded")
        self.assertFalse(self.node._hmb_slot_switching)

    def test_independent_auxiliary_faults_do_not_skip_other_stages(self):
        for stage in ("running_status", "notify", "result_messages", "policy_cleanup", "input_cleanup", "output_cleanup"):
            with self.subTest(stage=stage):
                self.setUp_case(stage)

    def setUp_case(self, stage):
        # A fresh manager makes each injected boundary an independent run.
        self.node, self.prompt = fixture.manager()
        self.node._native_parameter_value = lambda name, default=None: self.node.parameter_values.get(name, default)
        self.node._hmb_shot_results[OTHER] = {"text": "Other Shot preserved"}
        self.other_before = copy.deepcopy(self.node._hmb_shot_slots[OTHER])
        self.node._hmb_active_slot_key = KEY
        self.node._hmb_notify_shot_preview = Mock()
        self.node._refresh_hmb_execution_result_messages = Mock()
        error = RuntimeError("PRIVATE auxiliary fault")
        if stage == "running_status": self.node._hmb_publish_shot_status.side_effect = [error, None]
        if stage == "notify": self.node._hmb_notify_shot_preview.side_effect = error
        if stage == "result_messages": self.node._refresh_hmb_execution_result_messages.side_effect = error
        def factory(*args):
            worker = self.worker(*args)
            if stage == "policy_cleanup": worker._clear_hmb_runtime_policy.side_effect = error
            if stage in {"input_cleanup", "output_cleanup"}:
                class FailingClear(dict):
                    def clear(self): raise error
                attr = "parameter_values" if stage == "input_cleanup" else "parameter_output_values"
                setattr(worker, attr, FailingClear(getattr(worker, attr)))
            return worker
        def native_value(owner, name, value, *args, **kwargs):
            owner.parameter_values[name] = copy.deepcopy(value)
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory), \
                patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=native_value):
            record = self.run_once()
        self.assert_success(record)
        self.node._hmb_persist_shot_store.assert_called()
        self.node._hmb_notify_shot_preview.assert_called()

    def test_cleanup_baseexception_still_clears_worker_unlocks_and_allows_next_run(self):
        def factory(*args):
            worker = self.worker(*args)
            if len(self.workers) == 1:
                worker._clear_hmb_runtime_policy.side_effect = CleanupAbort("cleanup abort")
            return worker
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
            with self.assertRaises(CleanupAbort): self.run_once()
            self.assert_released()
            self.assertFalse(self.node._hmb_shot_request_records)
            self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["status"], "succeeded")
            self.assertFalse(self.workers[0].parameter_values)
            self.assertFalse(self.workers[0].parameter_output_values)
            record = self.run_once()
        self.assert_success(record)
        self.assertEqual(self.calls, [1, 2])

    def test_terminal_status_and_policy_cleanup_cancel_leave_no_orphan_ticket(self):
        for stage in ("policy", "terminal_status"):
            with self.subTest(stage=stage):
                self.node, self.prompt = fixture.manager()
                self.node._hmb_shot_results[OTHER] = {"text": "Other Shot preserved"}
                self.other_before = copy.deepcopy(self.node._hmb_shot_slots[OTHER])
                if stage == "terminal_status":
                    self.node._hmb_publish_shot_status.side_effect = [None, asyncio.CancelledError()]
                def factory(*args):
                    worker = self.worker(*args)
                    if stage == "policy": worker._clear_hmb_runtime_policy.side_effect = asyncio.CancelledError()
                    return worker
                with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
                    with self.assertRaises(asyncio.CancelledError): self.run_once()
                self.assert_released()
                self.assertFalse(self.node._hmb_shot_request_records)
                self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["status"], "succeeded")
                self.assertIn(KEY, self.node._hmb_shot_results)

    def test_terminal_cleanup_attribute_failure_does_not_strand_lock(self):
        def factory(*args):
            worker = self.worker(*args)
            del worker._clear_hmb_runtime_policy
            return worker
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
            record = self.run_once()
        self.assert_success(record)
        self.assertFalse(self.workers[0].parameter_values)
        self.assertFalse(self.workers[0].parameter_output_values)

    def test_post_admission_host_cancellation_preserves_result_and_releases_ticket(self):
        self.node._hmb_notify_shot_preview.side_effect = asyncio.CancelledError()
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker):
            with self.assertRaises(asyncio.CancelledError): self.run_once()
        self.assert_released()
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "succeeded")
        self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["status"], "succeeded")
        self.assertIn(KEY, self.node._hmb_shot_results)
        self.assertFalse(self.node._hmb_shot_request_records)
        self.assertEqual(self.calls, [1])

    def test_warning_does_not_expose_exception_text_and_is_separate_from_result(self):
        self.node._hmb_persist_shot_store.side_effect = RuntimeError("PRIVATE credential policy provider path")
        stdout = io.StringIO()
        with redirect_stdout(stdout), patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=self.worker):
            record = self.run_once()
        self.assert_success(record)
        self.assertNotIn("PRIVATE", stdout.getvalue())
        self.assertEqual(self.node._hmb_shot_slots[KEY]["publication_warnings"]["store"], "RuntimeError")
        self.assertNotIn("publication_warnings", record["result"])
        self.assertNotIn("publication_warnings", record)

    def test_failure_publication_ui_exception_preserves_original_model_error(self):
        self.node._hmb_active_slot_key = KEY
        self.node._refresh_hmb_execution_result_messages.side_effect = RuntimeError("secondary message fault")
        self.node._hmb_persist_shot_store.side_effect = RuntimeError("secondary store fault")
        def factory(*args):
            worker = self.worker(*args)
            async def failed(): raise ValueError("original offline model failure")
            worker._hmb_aprocess_locked = failed
            return worker
        def setter(owner, name, value, *args, **kwargs): raise RuntimeError("secondary native UI fault")
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory), \
                patch.object(module._BaseAgent, "set_parameter_value", autospec=True, side_effect=setter):
            with self.assertRaisesRegex(ValueError, "original offline model failure"): self.run_once()
        self.assert_released()
        self.assertNotIn(KEY, self.node._hmb_shot_results)
        self.assertFalse(getattr(self.node, "_hmb_shot_request_records", {}))
        self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["status"], "failed")
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "failed")

    def test_missing_run_identity_is_rejected_before_record_or_ticket_commit(self):
        def factory(*args):
            worker = self.worker(*args)
            original = worker._hmb_execution_result_snapshot
            worker._hmb_execution_result_snapshot = lambda: {**original(), "run_id": ""}
            return worker
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
            with self.assertRaisesRegex(RuntimeError, "identity is invalid"): self.run_once()
        self.assert_released()
        self.assertNotIn(KEY, self.node._hmb_shot_results)
        self.assertFalse(getattr(self.node, "_hmb_shot_request_records", {}))

    def test_five_concurrent_shots_keep_exact_records_under_auxiliary_failures(self):
        async def scenario():
            entered = {number: asyncio.Event() for number in range(1, 6)}
            finish = {number: asyncio.Event() for number in range(1, 6)}
            targets = [SimpleNamespace(_hmb_node_deleted=False, is_cancellation_requested=False) for _ in range(5)]
            def factory(owner, prompt, document, shot, slot, target):
                number = shot["shot_number"]
                worker = self.worker(owner, prompt, document, shot, slot, target)
                text = "Exact concurrent Shot " + str(number)
                result = {"status": "succeeded", "run_id": "concurrent-" + str(number),
                    "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
                worker.parameter_output_values["output"] = text
                worker._hmb_execution_result_snapshot = lambda: copy.deepcopy(result)
                async def run():
                    self.calls.append(number)
                    entered[number].set()
                    await finish[number].wait()
                worker._hmb_aprocess_locked = run
                if number in {2, 4}: worker._clear_hmb_runtime_policy.side_effect = RuntimeError("PRIVATE cleanup")
                return worker
            self.node._hmb_publish_shot_status.side_effect = RuntimeError("PRIVATE native header")
            self.node._hmb_persist_shot_store.side_effect = RuntimeError("PRIVATE durable store")
            with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
                tasks = [asyncio.create_task(self.node._hmb_run_agent_shot(channel_uuid="channel", shot_uuid="shot-" + str(number),
                    prompt_owner=self.prompt, generator=targets[number-1])) for number in range(1, 6)]
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 1)
                targets[2].is_cancellation_requested = True
                records = []
                for number in (5, 4, 3, 2, 1):
                    finish[number].set()
                    if number == 3:
                        with self.assertRaises(asyncio.CancelledError): await tasks[number-1]
                    else:
                        record = await tasks[number-1]
                        self.assertEqual(record["text"], "Exact concurrent Shot " + str(number))
                        self.assertEqual(self.node._hmb_agent_shot_result(channel_uuid="channel", shot_uuid="shot-" + str(number),
                            run_id=record["result"]["run_id"], generator=targets[number-1]), record)
                        for foreign in targets:
                            if foreign is targets[number-1]: continue
                            self.assertFalse(self.node._hmb_agent_shot_result(channel_uuid="channel", shot_uuid="shot-" + str(number),
                                run_id=record["result"]["run_id"], generator=foreign))
                        records.append(record)
                    key = "channel\x1fshot-" + str(number)
                    self.assertFalse(self.node._hmb_shot_execution_locks[key].locked())
                    self.assertNotIn(key, self.node._hmb_shot_workers)
                self.assertEqual(len(records), 4)
                self.assertNotIn("channel\x1fshot-3", self.node._hmb_shot_results)
                self.assertEqual(self.node._hmb_shot_run_status["channel\x1fshot-3"], "cancelled")
                self.assertCountEqual(self.calls, [1, 2, 3, 4, 5])
        asyncio.run(scenario())

    def test_cancellation_during_model_with_terminal_failures_stays_cancelled(self):
        def factory(*args):
            worker = self.worker(*args)
            async def cancelled():
                self.calls.append(1)
                raise asyncio.CancelledError()
            worker._hmb_aprocess_locked = cancelled
            return worker
        self.node._hmb_publish_shot_status.side_effect = RuntimeError("PRIVATE status fault")
        self.node._hmb_persist_shot_store.side_effect = RuntimeError("PRIVATE persist fault")
        with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
            with self.assertRaises(asyncio.CancelledError): self.run_once()
        self.assert_released()
        self.assertEqual(self.node._hmb_shot_run_status[KEY], "cancelled")
        self.assertEqual(self.node._hmb_shot_slots[KEY]["result"]["code"], "CANCELLED")
        self.assertNotIn(KEY, self.node._hmb_shot_results)
        self.assertFalse(getattr(self.node, "_hmb_shot_request_records", {}))

    def test_identity_source_and_model_failures_are_not_admitted(self):
        for failure in ("identity", "source", "model", "target_cancel", "deleted"):
            with self.subTest(failure=failure):
                self.node, self.prompt = fixture.manager()
                self.node._hmb_shot_results[OTHER] = {"text": "Other Shot preserved"}
                self.other_before = copy.deepcopy(self.node._hmb_shot_slots[OTHER])
                def factory(*args):
                    worker = self.worker(*args)
                    async def run():
                        self.calls.append(failure)
                        if failure == "identity": worker.parameter_output_values["output"] = "Changed unverified text"
                        if failure == "source": self.prompt._hmb_node_deleted = True
                        if failure == "model": raise RuntimeError("offline model failed")
                        if failure == "target_cancel": self.generator.is_cancellation_requested = True
                        if failure == "deleted": self.node._hmb_node_deleted = True
                    worker._hmb_aprocess_locked = run
                    return worker
                try:
                    with patch.object(module._HMBAgentShotExecution, "_from_owner", side_effect=factory):
                        with self.assertRaises((RuntimeError, asyncio.CancelledError)): self.run_once()
                    self.assert_released()
                    self.assertNotIn(KEY, self.node._hmb_shot_results)
                    self.assertFalse(getattr(self.node, "_hmb_shot_request_records", {}))
                finally:
                    self.generator.is_cancellation_requested = False


if __name__ == "__main__":
    unittest.main(verbosity=2)
