"""One manager, isolated Generator intents; no model or Broker traffic."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("managed_agent_seedance_fixture", Path(__file__).with_name("HMB_Seedance_Draft_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t


class Manager:
    def __init__(self):
        self.calls, self.records, self.waits, self.requests = [], {}, {}, {}
        self.owner = object()

    def _hmb_shot_manager_enabled(self):
        return True

    def _hmb_manager_prompt_owner(self, **_kwargs):
        return self.owner

    async def _hmb_run_agent_shot(self, *, channel_uuid, shot_uuid, prompt_owner, generator):
        assert prompt_owner is self.owner
        self.calls.append(shot_uuid)
        if shot_uuid in self.waits:
            await self.waits[shot_uuid].wait()
        else:
            await asyncio.sleep(0)
        text = "Exact result " + shot_uuid
        result = {"status": "succeeded", "run_id": str(uuid4()),
                  "output_sha256": hashlib.sha256(text.encode()).hexdigest()}
        self.records[shot_uuid] = {"text": text, "result": result,
            "shot": deepcopy(generator.subscription), "observation": {"shot_uuid": shot_uuid}}
        self.requests[result["run_id"]] = (self.records[shot_uuid], generator)
        return deepcopy(self.records[shot_uuid])

    def _hmb_agent_shot_result(self, *, channel_uuid, shot_uuid, run_id=None, generator=None):
        if run_id:
            record, owner = self.requests.get(run_id, ({}, None))
            return deepcopy(record) if owner is generator else {}
        return deepcopy(self.records.get(shot_uuid))

    def _hmb_release_agent_shot_result(self, *, channel_uuid, shot_uuid, run_id, generator):
        if self.requests.get(run_id, (None, None))[1] is generator:
            self.requests.pop(run_id, None)


class Node(fixture.Node):
    _assert_agent_result_available = t.HMBSeedanceGeneration._assert_agent_result_available

    def __init__(self, manager, channel, shot):
        super().__init__()
        self.manager = manager
        self.subscription = {"enabled": True, "channel_uuid": channel, "shot_uuid": shot,
                             "shot_number": 1, "shot_name": "Authored name"}
        self.values["prompt"] = "AUTHOR TEXT MUST STAY"
        self.values["resolution"] = "480p"
        self._hmb_managed_agent_request = None
        self._hmb_expected_agent_result = None
        self._hmb_agent_submission_prompt = None
        self.invalid_project = False

    def _manual_agent_prompt_source(self):
        return self.manager

    def _reconcile_shared_shot_routing(self, **_kwargs):
        return {"ok": True}

    def _hmb_shot_channel_subscription(self):
        return deepcopy(self.subscription)

    def _resolve_exact_shot_generation_inputs(self, params):
        if self.invalid_project:
            raise ValueError("Project is unavailable")
        return {**params, "_hmb_imageasset_project_selection": {"project": "fixed"}}

    def _capture_generated_video_origin(self):
        return {"channel_uuid": self.subscription["channel_uuid"], "shot_uuid": self.subscription["shot_uuid"]}

    def _assert_imageasset_project_selection(self, _selection):
        if self.invalid_project:
            raise ValueError("Project changed")

    def get_parameter_value(self, name):
        if hasattr(self, "values") and name in self.values:
            return self.values[name]
        return super().get_parameter_value(name)


class ManagedShotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.channel = str(uuid4())
        self.manager = Manager()
        self.nodes = [Node(self.manager, self.channel, str(uuid4())) for _ in range(5)]

    async def asyncTearDown(self):
        while fixture.TEMPORARIES:
            fixture.TEMPORARIES.pop().cleanup()

    async def test_one_generator_requests_only_its_shot_and_keeps_authoring(self):
        node = self.nodes[2]
        before = deepcopy(node.values)
        await node._prepare_managed_agent_shot()
        node._assert_agent_result_available()
        self.assertEqual(self.manager.calls, [node.subscription["shot_uuid"]])
        self.assertEqual(node.values, before)
        self.assertIsNone(self.nodes[0]._hmb_managed_agent_request)

    async def test_five_concurrent_results_keep_distinct_tokens_and_observations(self):
        await asyncio.gather(*(node._prepare_managed_agent_shot() for node in self.nodes))
        for node in self.nodes:
            node._assert_agent_result_available(allow_resume=False)
            record = node._hmb_managed_agent_request["record"]
            self.assertEqual(record["observation"]["shot_uuid"], node.subscription["shot_uuid"])
            self.assertEqual(node._hmb_agent_submission_prompt, record["text"])
        self.assertEqual(len(set(node._hmb_expected_agent_result for node in self.nodes)), 5)

    async def test_other_shot_completion_does_not_invalidate_prepared_request(self):
        first, second = self.nodes[:2]
        await first._prepare_managed_agent_shot()
        first._assert_agent_result_available()
        await second._prepare_managed_agent_shot()
        first._assert_agent_result_available(allow_resume=False)

    async def test_two_generators_same_shot_keep_their_own_request_tickets(self):
        first, second = self.nodes[:2]
        second.subscription = deepcopy(first.subscription)
        await first._prepare_managed_agent_shot()
        first._assert_agent_result_available()
        first_token = first._hmb_expected_agent_result
        await second._prepare_managed_agent_shot()
        second._assert_agent_result_available()
        first._assert_agent_result_available(allow_resume=False)
        self.assertEqual(first._hmb_expected_agent_result, first_token)
        self.assertNotEqual(first_token, second._hmb_expected_agent_result)

    async def test_changed_same_shot_result_rejected_before_submission(self):
        node = self.nodes[0]
        await node._prepare_managed_agent_shot()
        self.manager.records[node.subscription["shot_uuid"]]["result"]["run_id"] = "replacement"
        with self.assertRaises(t._AgentResultUnavailable):
            node._assert_agent_result_available()

    async def test_foreign_shot_result_rejected_even_with_valid_hash(self):
        node = self.nodes[0]
        native = self.manager._hmb_run_agent_shot
        async def wrong_shot(**kwargs):
            result = await native(**kwargs)
            result["shot"]["shot_uuid"] = self.nodes[1].subscription["shot_uuid"]
            return result
        self.manager._hmb_run_agent_shot = wrong_shot
        node._clear_execution_status = mock.Mock()
        node._publish_agent_result_skipped = mock.Mock()
        node._process_generation = mock.AsyncMock(side_effect=AssertionError("Foreign result reached generation"))
        await node._aprocess_impl()
        self.assertIn("different Shot", node._publish_agent_result_skipped.call_args.args[0])
        node._process_generation.assert_not_awaited()
        self.assertIsNone(node._hmb_managed_agent_request)
        self.assertEqual(self.manager.requests, {})

    async def test_current_record_text_and_shot_are_rechecked_at_submission(self):
        node = self.nodes[0]
        await node._prepare_managed_agent_shot()
        self.manager.records[node.subscription["shot_uuid"]]["shot"]["shot_name"] = "Changed"
        with self.assertRaises(t._AgentResultUnavailable):
            node._assert_agent_result_available()

    async def test_resume_and_draft_final_call_agent_zero_times(self):
        node = self.nodes[0]
        node.values["resume_generation_id"] = fixture.JOB
        await node._prepare_managed_agent_shot()
        node._assert_agent_result_available()
        node.values["resume_generation_id"] = ""
        node._draft_final_requested = lambda: True
        await node._prepare_managed_agent_shot()
        node._assert_agent_result_available()
        self.assertEqual(self.manager.calls, [])

    async def test_invalid_project_calls_agent_zero_times(self):
        node = self.nodes[0]
        node.invalid_project = True
        with self.assertRaisesRegex(ValueError, "Project"):
            await node._prepare_managed_agent_shot()
        self.assertEqual(self.manager.calls, [])

    async def test_cancel_one_generator_preserves_sibling(self):
        first, second = self.nodes[:2]
        self.manager.waits[first.subscription["shot_uuid"]] = asyncio.Event()
        task = asyncio.create_task(first._prepare_managed_agent_shot())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await second._prepare_managed_agent_shot()
        second._assert_agent_result_available()
        self.assertIsNone(first._hmb_managed_agent_request)

    async def test_repeated_fresh_runs_keep_480p_and_new_result_identity(self):
        node = self.nodes[0]
        tokens = []
        for _ in range(4):
            node._hmb_expected_agent_result = None
            await node._prepare_managed_agent_shot()
            node._assert_agent_result_available()
            tokens.append(node._hmb_expected_agent_result)
        self.assertEqual(len(set(tokens)), 4)
        self.assertEqual(node.values["resolution"], "480p")
        self.assertEqual(node.values["prompt"], "AUTHOR TEXT MUST STAY")


if __name__ == "__main__":
    unittest.main()
