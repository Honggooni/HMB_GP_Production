"""Detached connections cannot bypass native Run protection through web rerender.

Uses existing offline Generator fixture and real connection metadata predicates.
No live graph, provider, upload, or production configuration is accessed.
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
import HMB_Seedance_Web_Rerender_Regression as fixture
import HMBAgentLibrary as agent_module
import _hmb_connection_management as connections


def suspended(node, *, kind="video_picker", remote=False):
    node.metadata = {**getattr(node, "metadata", {}), connections.IDENTITY: str(uuid4())}
    node.metadata[connections.FENCES] = [{"source_id": str(uuid4()),
        "target_id": node.metadata[connections.IDENTITY], "source_kind": kind,
        "kind": "remote" if remote else "wire",
        "target_parameter_name": "" if remote else fixture.target.SHOT_PICKER_INPUT_PARAMETER}]


class ConnectionFenceRegression(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="hmb-web-detached-"))
        self.stack.enter_context(mock.patch.dict(os.environ, {"LOCALAPPDATA": temporary}))
        self.stack.enter_context(mock.patch.object(fixture.Base, "_runtime_node_is_live", lambda self, **kw: not self._hmb_node_deleted))
        self.stack.enter_context(mock.patch.object(fixture.Base, "_manual_agent_prompt_source", lambda self: fixture.agent))
        self.stack.enter_context(mock.patch.object(fixture.Base, "_exact_incoming_source", lambda self, *a, **kw: None))
        self.stack.enter_context(mock.patch.object(fixture.Base, "_has_incoming_parameter_connection", lambda self, name: False))
        self.stack.enter_context(mock.patch.object(fixture.target.GriptapeNodes, "NodeManager",
            lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "offline-flow"), create=True))
        self.stack.enter_context(mock.patch.object(fixture.agent, "metadata", {}, create=True))
        self.node = fixture.new_node()
        self.node.metadata = {}
        self.before = deepcopy((self.node.parameter_values,
            fixture.target._web_rerender_plain(dict(self.node.parameter_output_values))))

    def tearDown(self):
        try:
            self.assertEqual(self.before, (self.node.parameter_values,
                fixture.target._web_rerender_plain(dict(self.node.parameter_output_values))))
        finally:
            self.stack.close()

    async def test_attached_snapshot_still_preserves_order_and_values(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        self.assertEqual(snapshot["params"]["reference_images"], self.node.parameter_values["reference_images"])
        self.assertIs(snapshot["generation_settings"]["generate_audio"], False)
        self.assertEqual(snapshot["generation_settings"]["priority"], 0)

    async def test_detached_generator_is_not_ready(self):
        self.node.metadata[connections.STATE] = {"version": 1, "detached": True}
        ready = self.node._hmb_web_rerender_readiness()
        self.assertFalse(ready["ready"])
        self.assertIn("HMB_CONNECTION_DETACHED", ready["reason"])

    async def test_picker_detach_cannot_silently_use_remaining_image_and_agent(self):
        # Remaining Agent authority and authored image references are valid.
        # A removed Picker wire is represented by its durable target fence.
        suspended(self.node)
        self.assertTrue(self.node.parameter_values["reference_images"])
        self.assertIs(self.node._manual_agent_prompt_source(), fixture.agent)
        self.assertTrue(connections.target_has_suspended_role(self.node))
        with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
            self.node._hmb_web_rerender_capture_inputs()

    async def test_remote_only_fence_is_not_ready(self):
        suspended(self.node, kind="image_asset", remote=True)
        self.assertFalse(self.node._hmb_web_rerender_readiness()["ready"])

    async def test_agent_incoming_fence_blocks_generator_snapshot(self):
        suspended(fixture.agent, kind="prompt", remote=True)
        with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
            self.node._hmb_web_rerender_capture_inputs()

    async def test_outgoing_fence_does_not_block_unrelated_source_execution(self):
        self.node.metadata = {connections.IDENTITY: str(uuid4())}
        self.node.metadata[connections.FENCES] = [{"source_id": self.node.metadata[connections.IDENTITY],
            "target_id": str(uuid4()), "source_kind": "seedance"}]
        self.node._hmb_web_rerender_capture_inputs()

    async def test_detach_after_capture_blocks_claim_without_leaking_busy(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        suspended(self.node)
        with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
            async with self.node._hmb_web_rerender_claim(snapshot):
                self.fail("Detached claim admitted")
        self.assertFalse(self.node._generation_run_active.is_set())

    async def test_active_claim_revalidates_new_fence(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        async with self.node._hmb_web_rerender_claim(snapshot) as claim:
            suspended(self.node)
            with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
                self.node._hmb_web_rerender_validate_claim(claim)

    async def test_reconnect_restores_exact_snapshot_and_claim(self):
        original = self.node._hmb_web_rerender_capture_inputs()
        suspended(self.node)
        self.assertFalse(self.node._hmb_web_rerender_readiness()["ready"])
        self.node.metadata[connections.FENCES] = []
        self.node.metadata[connections.STATE] = {"version": 1, "detached": False}
        restored = self.node._hmb_web_rerender_capture_inputs()
        self.assertEqual(original, restored)
        async with self.node._hmb_web_rerender_claim(restored) as claim:
            self.node._hmb_web_rerender_validate_claim(claim)

    async def test_connection_transaction_finishes_before_claim_can_activate(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        started, entered, finished = threading.Event(), threading.Event(), threading.Event()
        errors = []
        async def claim():
            started.set()
            async with self.node._hmb_web_rerender_claim(snapshot):
                entered.set()
        def run():
            try:
                asyncio.run(claim())
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()
        worker = threading.Thread(target=run, daemon=True)
        # This is the actual common transaction lock used by manage(), not a
        # mocked reservation. A claim cannot enter after describe() passed.
        with connections.execution_reservation():
            worker.start()
            self.assertTrue(started.wait(3))
            self.assertFalse(finished.wait(0.1))
            self.assertFalse(entered.is_set())
            self.assertFalse(self.node._generation_run_active.is_set())
            suspended(self.node)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn("HMB_CONNECTION_DETACHED", str(errors[0]))
        self.assertFalse(entered.is_set())
        self.assertFalse(self.node._generation_run_active.is_set())

    async def test_claim_first_makes_connection_transaction_busy_until_release(self):
        snapshot = self.node._hmb_web_rerender_capture_inputs()
        entered, release = threading.Event(), threading.Event()
        errors = []
        async def claim():
            async with self.node._hmb_web_rerender_claim(snapshot):
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Claim release was not signalled")
        def run():
            try:
                asyncio.run(claim())
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            # Claim activation releases the common lock before its body: the
            # connection transaction can inspect it and must see busy=True.
            with connections.execution_reservation():
                self.assertTrue(connections._busy(self.node))
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        with connections.execution_reservation():
            self.assertFalse(connections._busy(self.node))
        self.assertIsNone(getattr(self.node, "_hmb_web_rerender_active_claim", None))

    def agent(self):
        value = object.__new__(agent_module.HMBAgentLibrary)
        value.metadata = {}
        return value

    async def test_agent_authority_rejects_detached_agent_and_generator(self):
        for endpoint in ("agent", "generator"):
            agent, generator = self.agent(), SimpleNamespace(metadata={})
            suspended(agent if endpoint == "agent" else generator, remote=True)
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
                agent._hmb_issue_web_rerender_authority(request_id="offline-one", generator=generator, owner_key="offline")

    async def test_agent_rechecks_after_authority_issue_before_native_call(self):
        agent, generator = self.agent(), SimpleNamespace(metadata={})
        authority = agent._hmb_issue_web_rerender_authority(request_id="offline-two", generator=generator, owner_key="offline")
        suspended(generator)
        with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
            await agent._hmb_run_web_rerender("prompt", {}, {}, authority)

    async def test_agent_queued_gate_rechecks_detach_and_releases_lock(self):
        agent, generator = self.agent(), SimpleNamespace(metadata={})
        authority = agent._hmb_issue_web_rerender_authority(request_id="offline-three", generator=generator, owner_key="offline")
        gate = threading.Lock()
        async def acquire(_node):
            gate.acquire()
            suspended(generator, remote=True)
            return gate
        media = {"schema": "hmb-agent-reference-media", "version": 1, "images": [], "videos": []}
        with mock.patch.object(agent_module.HMBAgentLibrary, "_hmb_shot_manager_enabled", return_value=False), \
             mock.patch.object(agent_module, "_acquire_agent_execution_gate", acquire), \
             mock.patch.object(agent_module._HMBWebRerenderExecution, "_from_owner", side_effect=AssertionError("native execution reached")) as native:
            with self.assertRaisesRegex(RuntimeError, "HMB_CONNECTION_DETACHED"):
                await agent._hmb_run_web_rerender("prompt", media, {}, authority)
            native.assert_not_called()
        self.assertFalse(gate.locked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
