"""Saved Draft observers must not lock otherwise idle connection controls.

Execute the actual Generator observer method bodies and connection inventory
logic with a synthetic same-flow graph and a local status coroutine. No user
workflow is evaluated, no SDK/app is connected and no Broker request is sent.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import ExitStack, suppress
from copy import deepcopy
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import _hmb_connection_management as connections


def observer_type():
    """Keep real observer scheduling, loop lifetime and terminal-state rules."""
    source = ROOT / "HMBSeedanceGeneration.py"
    tree = ast.parse(source.read_text("utf-8"), filename=str(source))
    owner = next(row for row in tree.body if isinstance(row, ast.ClassDef)
                 and row.name == "HMBSeedanceGeneration")
    names = {"_draft_final_server_snapshot", "_schedule_draft_final_status_sync",
             "_poll_draft_final_server_state"}
    methods = [deepcopy(row) for row in owner.body
               if isinstance(row, (ast.FunctionDef, ast.AsyncFunctionDef)) and row.name in names]
    assert len(methods) == len(names)
    constants = [deepcopy(row) for row in tree.body if isinstance(row, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id in
                         {"_DRAFT_FINAL_HIDDEN_STATES", "_DRAFT_FINAL_SYNC_SECONDS"}
                         for target in row.targets)]
    assert len(constants) == 2
    shell = deepcopy(owner)
    shell.name = "Observer"
    shell.bases = []
    shell.keywords = []
    shell.decorator_list = []
    shell.body = methods
    namespace = {"asyncio": asyncio, "deepcopy": deepcopy, "suppress": suppress,
                 "time": time, "GriptapeNodes": SimpleNamespace(
                     EventManager=lambda: SimpleNamespace(event_loop=asyncio.get_running_loop()))}
    module = ast.Module(body=constants + [shell], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(source), "exec"), namespace)
    return namespace["Observer"]


Observer = observer_type()


class SavedDraftConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.guards = ExitStack()
        self.guards.enter_context(mock.patch.object(socket, "create_connection",
            side_effect=AssertionError("Passive Draft fixture cannot contact a server")))
        self.observer = Observer()
        generator = self.observer
        generator.name = "Generator"
        generator.metadata = {"library": connections.LIBRARY,
                              connections.IDENTITY: str(uuid4())}
        generator.state = "resolved"
        generator.lock = False
        generator._generation_run_active = threading.Event()
        generator._generation_refresh_running = False
        generator._hmb_draft_finalize_pending = False
        generator._hmb_draft_final_status_future = None
        generator._hmb_draft_final_status_cache = {}
        generator._hmb_draft_final_status_scope = ()
        generator._runtime_node_is_live = lambda **kwargs: True
        self.source = {"draft_job_id": "job-" + "a" * 32,
                       "broker_server_url": "https://unused.invalid",
                       "project_id": "synthetic", "project_name": "Saved Draft"}
        self.saved_values = {"Draft": deepcopy(self.source), "prompt": "Authored OFF 0 {{SIGN}}",
                             "generation_id": self.source["draft_job_id"],
                             "generation_status": "succeeded", "output": "unchanged.mov"}
        self.original_values = deepcopy(self.saved_values)
        generator._draft_source_record = lambda: deepcopy(self.source)
        generator._draft_final_status_identity = lambda source: (
            source["draft_job_id"], "synthetic-credential-fingerprint")
        self.status = "available"
        self.polls = 0

        async def local_status(source):
            self.polls += 1
            return {"state": self.status, "eligible": self.status == "available"}

        generator._query_draft_final_server_state = local_status
        generator._sync_seedance_shot_widget = lambda **kwargs: None
        self.nodes = {"Generator": generator}
        for name in ("Prompt", "Agent"):
            self.nodes[name] = SimpleNamespace(name=name, lock=False, state="resolved",
                metadata={"library": connections.LIBRARY, connections.IDENTITY: str(uuid4())})
        edges = [("Prompt", "Agent"), ("Agent", "Generator")]

        def relations(engine, node, nodes, parents):
            return [dict(kind="wire", source_node_name=source, target_node_name=target,
                         source_parameter_name="output", target_parameter_name="input",
                         peer_name=target if node.name == source else source, shots=[])
                    for source, target in edges if node.name in (source, target)]

        self.guards.enter_context(mock.patch.object(connections, "_inventory",
            return_value=(self.nodes, {name: "same-flow" for name in self.nodes})))
        self.guards.enter_context(mock.patch.object(connections, "_context",
            return_value=("saved-workflow", "same-flow")))
        self.guards.enter_context(mock.patch.object(connections, "_relations", side_effect=relations))
        self.guards.enter_context(mock.patch.object(connections, "_missing_records", return_value=([], "")))

    async def asyncTearDown(self):
        future = self.observer._hmb_draft_final_status_future
        if future is not None:
            future.cancel()
            await asyncio.sleep(0)
        self.guards.close()
        self.assertEqual(self.saved_values, self.original_values)

    def describe(self, name):
        return connections.describe(None, name)

    async def start_observer(self, status="available"):
        self.status = status
        result = self.observer._draft_final_server_snapshot(deepcopy(self.source))
        self.assertEqual(result["state"], "checking")
        for _ in range(100):
            if self.polls:
                break
            await asyncio.sleep(.001)
        self.assertGreater(self.polls, 0)
        self.assertFalse(self.observer._hmb_draft_final_status_future.done())
        self.assertFalse(self.observer._generation_run_active.is_set())
        self.assertFalse(self.observer._generation_refresh_running)

    async def test_saved_available_Draft_observer_keeps_Prompt_Agent_Generator_disconnectable(self):
        await self.start_observer()
        for name in self.nodes:
            with self.subTest(node=name):
                self.assertTrue(self.describe(name)["can_disconnect"])
                self.assertEqual(self.describe(name)["details"], "현재 연결 상태")

    async def test_unavailable_status_observation_is_not_an_active_render(self):
        await self.start_observer("unknown")
        self.assertTrue(self.describe("Agent")["can_disconnect"])
        self.assertTrue(self.describe("Generator")["can_disconnect"])

    async def test_actual_Final_dispatch_and_run_ownership_still_block_connected_peers(self):
        await self.start_observer()
        pending = SimpleNamespace(done=lambda: False)
        active = threading.Event()
        active.set()
        for field, value in (("_hmb_draft_finalize_pending", True),
                             ("_hmb_draft_finalize_future", pending),
                             ("_generation_run_active", active),
                             ("_generation_refresh_running", True),
                             ("_broker_action_running", True),
                             ("_hmb_web_rerender_active_claim", object()),
                             ("lock", True)):
            with self.subTest(active_owner=field), mock.patch.object(self.observer, field, value, create=True):
                self.assertFalse(self.describe("Agent")["can_disconnect"])
                self.assertFalse(self.describe("Generator")["can_disconnect"])
                self.assertIn("Generator", self.describe("Agent")["details"])
                self.assertTrue(self.describe("Prompt")["can_disconnect"])
            self.assertTrue(self.describe("Agent")["can_disconnect"])

    async def test_running_Agent_worker_still_blocks_its_Generator(self):
        await self.start_observer()
        worker = SimpleNamespace(is_alive=lambda: True)
        with mock.patch.object(self.nodes["Agent"], "_hmb_shot_workers", {"shot": worker}, create=True):
            self.assertFalse(self.describe("Generator")["can_disconnect"])
        self.assertTrue(self.describe("Generator")["can_disconnect"])


if __name__ == "__main__":
    unittest.main()
