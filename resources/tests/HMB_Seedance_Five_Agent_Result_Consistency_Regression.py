"""Five simultaneous renders apply the same upstream Agent result checks.

The registered graph and Generator orchestration are production code.
Generators do not read project policies; Agent result status is
the only gate under test. Broker/model/media/save boundaries are deterministic
local fixtures. No user workflow, server or billable generation is touched.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))
import _hmb_common as common
spec = importlib.util.spec_from_file_location(
    "five_policy_project_source_fixture",
    TESTS / "HMB_Seedance_Project_Source_Routing_Regression.py",
)
assert spec and spec.loader
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t
base = fixture.base


class Node(fixture.Node):
    # Exercise the production downstream Agent guard rather than the Draft-only
    # fixture override.
    _assert_agent_result_available = t.HMBSeedanceGeneration._assert_agent_result_available

    def __init__(self, number, *, action=None):
        values = base.params(t.DRAFT_ACTION_OFF if action is None else action)
        values["prompt"] = f"Shot {number} " + "한국어 {{SIGN}} {% raw %} 🙂"
        values["resolution"] = "480p" if action == t.DRAFT_ACTION_PREVIEW else "720p"
        super().__init__(values)
        self.name = f"Five Agent Result Generator {number}"
        self.number = number
        self.parameter_values.update(values)
        self.results = []
        self.agent = None
        self.agent_lookup = mock.Mock(side_effect=lambda: self.agent)
        self._manual_agent_prompt_source = self.agent_lookup
        self._clear_execution_status = lambda: None
        self._set_status_results = lambda **value: self.results.append(deepcopy(value))
        self._publish_generation_preview = lambda *args, **kwargs: None
        self._sync_seedance_shot_widget = lambda **kwargs: None
        self._update_parameter_visibility = lambda: None
        self._ensure_broker_connected = mock.AsyncMock(return_value=self.bridge)
        self.bridge.generate_seedance = self._fake_create

    def _fake_create(self, payload, *, timeout):
        assert timeout > 0
        self.bridge.posts.append(deepcopy(payload))
        return {"id": "job-" + str(self.number).zfill(32), "status": "succeeded", "video_url": "fixture"}

    async def _save_completed_task(self, task, job_id, destination, *args, **kwargs):
        # Deterministic downloaded-result publication boundary; the dedicated
        # full-lifecycle suite validates actual download/decode/publication.
        await super()._save_completed_task(task, job_id, destination, *args, **kwargs)
        self._set_status_results(was_successful=True, result_details="Offline result published")


class Batch:
    """Five independent selected-project paths with configurable Agent edges."""

    def __init__(self, project, *, failed_agent=None, action=None, agent_count=5, created=False):
        self.nodes = [Node(number, action=action) for number in range(1, 6)]
        self.graph = fixture.Graph(self.nodes[0])
        for node in self.nodes[1:]:
            self.graph.add(node)
        self.image = self.graph.add(fixture.HMBImageAssetLibrary("Shared ImageAsset", project))
        self.agents = []
        for node in self.nodes:
            if node.number <= agent_count:
                prompt = self.graph.add(fixture.HMBPromptLibrary(f"Shot Prompt {node.number}"))
                agent = self.graph.add(fixture.HMBAgentLibrary(f"Shot Agent {node.number}"))
                self.graph.edge(self.image, "SHOT_ASSET_OUT", prompt, "SHOT_ASSET_IN")
                self.graph.edge(prompt, "PROMPT_OUT", agent, "SHOT_PROMPT_IN")
                self.graph.edge(agent, "output", node, "prompt")
                if created:
                    node.values["prompt"] = "Agent created."
                    node.parameter_values["prompt"] = "Agent created."
                text = node.values["prompt"]
                status = "created" if created else "failed" if failed_agent in {"all", node.number} else "succeeded"
                code = "AGENT_CREATED" if created else "PROJECT_POLICY_PENDING" if failed_agent == "all" else "MODEL_TIMEOUT" if status == "failed" else ""
                snapshot = {"status": status, "code": code, "run_id": f"offline-run-{node.number}",
                            "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
                agent._hmb_execution_result_snapshot = mock.Mock(return_value=snapshot)
                node.agent = agent
                self.agents.append(agent)
            else:
                self.graph.edge(self.image, "SHOT_ASSET_OUT", node, "SHOT_ASSET_IN")

    async def execute(self):
        with self.graph.context(), \
             mock.patch.object(t, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fixture", backend="test")), \
             mock.patch.object(t._review, "capture_inputs", return_value={}), \
             mock.patch.object(t, "_broker_wait_for_submission_slot"), \
             mock.patch.object(common, "_load_verified_agent_rule_payload", side_effect=AssertionError("Generator read project policy")) as policy_loader, \
             mock.patch.object(common, "_read_agent_policy_envelope", side_effect=AssertionError("Generator read policy DAT")) as policy_reader, \
             mock.patch.object(common, "_agent_policy_session_state", side_effect=AssertionError("Generator read policy session")) as policy_state, \
             mock.patch.object(common, "_bootstrap_agent_policy_session", side_effect=AssertionError("Generator claimed policy authority")) as policy_bootstrap, \
             mock.patch.object(t.httpx, "AsyncClient", side_effect=AssertionError("network forbidden")), \
             mock.patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            await asyncio.wait_for(asyncio.gather(*(node.aprocess() for node in self.nodes)), timeout=15)
            policy_loader.assert_not_called()
            policy_reader.assert_not_called()
            policy_state.assert_not_called()
            policy_bootstrap.assert_not_called()


class FiveAgentResultConsistencyTests(unittest.TestCase):
    def tearDown(self):
        while base.TEMPORARIES:
            base.TEMPORARIES.pop().cleanup()

    def assert_blocked_batch(self, batch, code):
        before = [deepcopy(node.parameter_values) for node in batch.nodes]
        asyncio.run(batch.execute())
        messages = []
        for node in batch.nodes:
            self.assertTrue(node.results)
            result = node.results[-1]
            self.assertIs(result["was_successful"], False)
            self.assertIn(code, result["result_details"])
            messages.append(result["result_details"])
            self.assertEqual(node.bridge.posts, [])
            self.assertEqual(node.bridge.cap_calls, 0)
            self.assertEqual(node.upload_calls, 0)
            self.assertEqual(node.saved, [])
            node._ensure_broker_connected.assert_not_awaited()
            self.assertFalse(node._generation_run_active.is_set())
        self.assertEqual(len(set(messages)), 1, "The same upstream result condition must expose the same cause")
        for agent in batch.agents:
            agent._hmb_execution_result_snapshot.assert_called()
            agent.process.assert_not_called()
        self.assertEqual([node.parameter_values["prompt"] for node in batch.nodes], [value["prompt"] for value in before])

    def test_legacy_failed_pending_results_block_all_five_with_same_failure_code(self):
        # Compatibility with already-failed saved Agents. New absent-policy
        # Agents run without HMB policy and publish ordinary succeeded output.
        self.assert_blocked_batch(Batch("katuri8", failed_agent="all"), "PROJECT_POLICY_PENDING")

    def test_all_five_created_objects_are_not_completed_model_results(self):
        self.assert_blocked_batch(Batch("katuri8", created=True), "AGENT_CREATED")

    def test_draft_preview_also_blocks_all_five_upstream_pending_before_capability_or_upload(self):
        self.assert_blocked_batch(Batch("katuri8", failed_agent="all", action=t.DRAFT_ACTION_PREVIEW), "PROJECT_POLICY_PENDING")

    def assert_submitted_batch(self, batch):
        before = [deepcopy(node.parameter_values["prompt"]) for node in batch.nodes]
        asyncio.run(batch.execute())
        keys = []
        jobs = []
        for node, authored in zip(batch.nodes, before):
            self.assertIs(node.results[-1]["was_successful"], True, node.results[-1])
            self.assertEqual(len(node.bridge.posts), 1)
            wire = node.bridge.posts[0]
            self.assertEqual(wire["project_id"], batch.image.project)
            self.assertEqual(wire["project_selection_schema"], t.PROJECT_SELECTION_SCHEMA)
            self.assertEqual(wire["prompt"], authored)
            self.assertIs(wire["generate_audio"], False)
            keys.append(wire["client_request_id"])
            jobs.append(node.parameter_output_values["generation_id"])
            self.assertEqual(len(node.saved), 1)
            self.assertFalse(node._generation_run_active.is_set())
        self.assertEqual(len(set(keys)), 5)
        self.assertEqual(len(set(jobs)), 5)
        self.assertEqual(len({node.saved[0][1] for node in batch.nodes}), 5)
        for agent in batch.agents:
            agent.process.assert_not_called()

    def test_five_successful_agent_results_submit_once_each_and_preserve_prompts(self):
        self.assert_submitted_batch(Batch("superwings12"))

    def test_five_completed_katuri_agents_render_without_generator_policy_recheck(self):
        self.assert_submitted_batch(Batch("katuri8"))

    def test_five_manual_katuri_generators_submit_without_any_agent_or_policy_check(self):
        self.assert_submitted_batch(Batch("katuri8", agent_count=0))

    def test_three_pending_agents_and_two_direct_inputs_remain_independent(self):
        batch = Batch("katuri8", failed_agent="all", agent_count=3)
        asyncio.run(batch.execute())
        for node in batch.nodes:
            if node.number <= 3:
                self.assertIs(node.results[-1]["was_successful"], False)
                self.assertIn("PROJECT_POLICY_PENDING", node.results[-1]["result_details"])
                self.assertEqual(node.bridge.posts, [])
                node._ensure_broker_connected.assert_not_awaited()
            else:
                self.assertIs(node.results[-1]["was_successful"], True, node.results[-1])
                self.assertEqual(len(node.bridge.posts), 1)
                self.assertEqual(node.bridge.posts[0]["project_id"], "katuri8")

    def test_ready_project_keeps_single_model_failure_local_to_its_shot(self):
        batch = Batch("superwings12", failed_agent=2)
        asyncio.run(batch.execute())
        for node in batch.nodes:
            if node.number == 2:
                self.assertIs(node.results[-1]["was_successful"], False)
                self.assertIn("MODEL_TIMEOUT", node.results[-1]["result_details"])
                self.assertEqual(node.bridge.posts, [])
                node._ensure_broker_connected.assert_not_awaited()
            else:
                self.assertIs(node.results[-1]["was_successful"], True, node.results[-1])
                self.assertEqual(len(node.bridge.posts), 1)

    def test_existing_resume_and_final_skip_current_agent_result_and_policy(self):
        for operation in ("resume", "final"):
            node = Node(1)
            if operation == "resume":
                node.parameter_values["resume_generation_id"] = base.JOB
            else:
                node._hmb_draft_final_context = {"source": deepcopy(base.SOURCE)}
            with mock.patch.object(node, "_manual_agent_prompt_source", side_effect=AssertionError("Current Agent was read")), \
                 mock.patch.object(common, "_load_verified_agent_rule_payload", side_effect=AssertionError("Current policy was read")):
                node._assert_agent_result_available()

    def test_project_change_after_cadence_blocks_any_billable_post(self):
        async def scenario():
            node = Node(4)
            graph = fixture.Graph(node)
            image = graph.direct(project="superwings12")
            loop = asyncio.get_running_loop()
            entered = asyncio.Event()
            release = threading.Event()
            def cadence():
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)
            with graph.context(), \
                 mock.patch.object(t, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fixture", backend="test")), \
                 mock.patch.object(t._review, "capture_inputs", return_value={}), \
                 mock.patch.object(t, "_broker_wait_for_submission_slot", side_effect=cadence):
                task = asyncio.create_task(node.aprocess())
                await asyncio.wait_for(entered.wait(), timeout=5)
                # The selected source changes while waiting for its create
                # slot. Snapshot validation must stop the queued POST.
                image.project = "katuri8"
                release.set()
                await asyncio.wait_for(task, timeout=5)
            self.assertEqual(node.bridge.posts, [])
            self.assertIs(node.results[-1]["was_successful"], False)
        asyncio.run(scenario())

if __name__ == "__main__":
    unittest.main(verbosity=2)
