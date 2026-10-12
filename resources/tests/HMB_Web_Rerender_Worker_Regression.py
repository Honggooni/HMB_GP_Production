"""Offline worker integration: paid-call stand-ins, durable replay and node isolation."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_web_rerender as web


class Engine:
    pass


class Protocol:
    def __init__(self):
        self.owner_key = "17"
        self.events = []
        self.posts = []
        self.fail_event = ""
        self.on_event = None
        self.bridge = SimpleNamespace(server_url="https://broker.example", _opener=self)

    def open(self, request, *, timeout):
        self.posts.append((request.full_url, json.loads(request.data)))
        return {"task_id": "job-child"}

    def renew(self, command):
        pass

    def result(self, command, event, **fields):
        self.events.append((event, deepcopy(fields)))
        if self.on_event is not None:
            self.on_event(event)
        if event == self.fail_event:
            raise RuntimeError("network failure")
        return {"operation_id": command["operation_id"], "state": "completed" if event == "ack" else "prepared"}


class Agent:
    def __init__(self):
        self.calls = 0
        self.original = {"prompt": "authored original", "output": "previous"}
        self.fail = False
        self.pause = None

    def _hmb_issue_web_rerender_authority(self, **kwargs):
        assert kwargs["owner_key"] == "17"
        return object()

    async def _hmb_run_web_rerender(self, prompt, media, settings, authority):
        self.calls += 1
        assert prompt == "web review only" and media == {"images": ["one"], "videos": ["two"]}
        assert settings == {"seed": 0, "generate_audio": False}
        if self.pause is not None:
            await self.pause.wait()
        if self.fail:
            raise RuntimeError("model response lost")
        text = "resolved web output"
        return {"text": text, "run_id": "agent-run", "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "policy_identity": {"version": "test"}, "observation": {"private": "not journaled"}}


class Generator:
    def __init__(self):
        self.claims = 0
        self.executions = 0
        self.changed = False
        self.fail_after_post = False
        self.original = {"generation_id": "job-parent", "prompt": "existing", "video": "original.mp4"}

    def _compose_finish_look_prompt(self, text, finish):
        return text if not finish else text + "\n" + finish

    @asynccontextmanager
    async def _hmb_web_rerender_claim(self, snapshot):
        self.claims += 1
        if self.changed:
            raise RuntimeError("changed")
        yield object()

    async def _hmb_web_rerender_prepare_media(self, claim):
        return {"images": ["one"], "videos": ["two"]}

    async def _hmb_web_rerender_execute(self, claim, result, **kwargs):
        self.executions += 1
        await kwargs["checkpoint_sink"]({"stage": "before_submit"}, reason="submit", required=True)
        bridge = kwargs["submission_bridge"]
        body = {"client_request_id": kwargs["client_request_id"], "model": "seedance-test", "prompt": result["text"]}
        request = Request(bridge.server_url + "/api/v1/generate/video", data=json.dumps(body).encode(),
                          headers={"Idempotency-Key": kwargs["client_request_id"]}, method="POST")
        await asyncio.to_thread(bridge._opener.open, request, timeout=10)
        if self.fail_after_post:
            raise RuntimeError("response lost after acceptance")
        return {"task_id": "job-child", "video": "test.mp4", "status": "completed"}


def command():
    operation = str(uuid4())
    return {"operation_id": operation, "render_key": "hmb-web-rerender-" + operation,
            "target_id": str(uuid4()), "session_id": str(uuid4()), "snapshot_sha256": "a" * 64,
            "web_prompt": "web review only", "parent_task_id": "job-parent", "review_id": str(uuid4()),
            "state": "claimed", "lease_id": str(uuid4()), "fence": 1}


async def case(kind):
    with tempfile.TemporaryDirectory(prefix="hmb-web-worker-") as directory:
        engine = Engine()
        journal = web.OperationJournal(directory)
        worker = web.EngineWorker(engine, journal)
        node, agent, protocol, request = Generator(), Agent(), Protocol(), command()
        snapshot = {"params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}
        original = deepcopy((node.original, agent.original))
        if kind == "changed":
            node.changed = True
        elif kind == "agent_uncertain":
            agent.fail = True
        elif kind == "render_uncertain":
            node.fail_after_post = True
        elif kind == "prepared_failure":
            protocol.fail_event = "prepared"
        elif kind == "cancelled":
            agent.pause = asyncio.Event()
        elif kind == "lease_lost_at_ack":
            protocol.on_event = lambda event: worker.leases[request["target_id"]].clear() if event == "agent_started" else None
        if kind == "concurrent":
            await asyncio.gather(*(worker.execute(node, agent, snapshot, protocol, request) for _ in range(8)))
        elif kind == "cancelled":
            task = asyncio.create_task(worker.execute(node, agent, snapshot, protocol, request))
            while agent.calls == 0:
                await asyncio.sleep(0.001)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            await worker.execute(node, agent, snapshot, protocol, request)
        key = journal.key(protocol.bridge.server_url, protocol.owner_key, request["operation_id"])
        record = journal.read(key)
        if kind in {"success", "concurrent"}:
            assert agent.calls == 1 and len(protocol.posts) == 1 and record["state"] == "completed"
            assert "observation" not in record["document"]["agent_result"]
            assert [event[0] for event in protocol.events] == ["agent_started", "prepared", "ack"]
            assert worker.children[request["target_id"]] == ["job-child"]
        elif kind == "changed":
            assert agent.calls == 0 and not protocol.posts and record["state"] == "failed"
        elif kind in {"agent_uncertain", "cancelled"}:
            assert agent.calls == 1 and not protocol.posts and record["state"] == "uncertain"
        elif kind == "render_uncertain":
            assert agent.calls == 1 and len(protocol.posts) == 1 and record["state"] == "uncertain"
        elif kind == "prepared_failure":
            assert agent.calls == 1 and not protocol.posts and record["state"] == "failed"
        elif kind == "lease_lost_at_ack":
            assert agent.calls == 0 and not protocol.posts and record["state"] == "uncertain"
        before = (agent.calls, len(protocol.posts), node.executions)
        # Reconstructed process/SQLite replay cannot repeat either paid call.
        restarted = web.EngineWorker(engine, web.OperationJournal(directory))
        assert restarted.worker_id == worker.worker_id and restarted.session_id != worker.session_id
        await restarted.execute(node, agent, snapshot, protocol, request)
        assert before == (agent.calls, len(protocol.posts), node.executions)
        assert original == (node.original, agent.original)
        assert not worker.leases
        if kind in {"success", "concurrent"}:
            assert journal.descendants(protocol.bridge.server_url, "17", "job-parent") == ["job-child"]
            assert journal.descendants(protocol.bridge.server_url, "18", "job-parent") == []
            assert journal.descendants("https://different.example", "17", "job-parent") == []


def unload_pending():
    callbacks = []
    loop = SimpleNamespace(is_closed=lambda: False, is_running=lambda: True,
                           call_soon_threadsafe=lambda callback: callbacks.append(callback))
    engine = Engine()
    engine.event_manager = SimpleNamespace(event_loop=loop)
    engine.library_manager = SimpleNamespace(is_worker=False)
    web.ensure_engine_worker(engine)
    web.ensure_engine_worker(engine)
    assert len(callbacks) == 1
    web.stop_engine_worker(engine)
    callbacks[0]()
    assert engine not in web._WORKERS and engine not in web._PENDING_STARTS


async def account_rotation():
    with tempfile.TemporaryDirectory(prefix="hmb-web-owner-") as directory:
        engine = Engine()
        agent = Agent()
        agent.name = "agent"
        agent._hmb_web_rerender_policy_status = lambda: {"ready": True, "version": "test"}
        agent._hmb_web_rerender_busy = lambda: False
        engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: agent)
        engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: "workflow")
        node = Generator()
        node.name = "generator"
        node.token = "account-a-token"
        node._selected_broker_server_url = lambda: "https://broker.example"
        node._create_broker_bridge = lambda **kwargs: SimpleNamespace(server_url="https://broker.example",
                                                                     _load_access_token=lambda: node.token)
        node._hmb_web_rerender_capture_inputs = lambda: {
            "agent_name": "agent", "target": {"flow_name": "flow"}, "source_bindings": [], "binding_fingerprint": "a"*64}
        node._hmb_web_rerender_readiness = lambda: {"ready": True}
        node.get_parameter_value = lambda key: "job-parent"
        worker = web.EngineWorker(engine, web.OperationJournal(directory))
        first, target, *_ = await worker._target(node)
        first.owner_key = "17"
        worker.children[target["target_id"]] = ["job-account-a-child"]
        node.token = "account-b-token"
        second, changed, *_ = await worker._target(node)
        assert first is not second and second.owner_key == "" and first.owner_key == "17"
        assert first.session_id != second.session_id and target["target_id"] != changed["target_id"]
        assert changed["parent_task_ids"] == ["job-parent"]


async def lease_lost_while_waiting_for_agent():
    # Use the production Agent reservation wait, with no model implementation
    # invoked. A second Generator can have queued behind a manual/other run
    # after both targets were advertised ready in the same heartbeat.
    import HMBAgentLibrary as agent_module

    entered = asyncio.Event()
    renewals = []

    class QueuedAgent(Agent):
        async def _hmb_run_web_rerender(self, *args):
            entered.set()
            gate = await agent_module._acquire_agent_execution_gate(self)
            try:
                return await super()._hmb_run_web_rerender(*args)
            finally:
                gate.release()

    def failed_renew(command):
        renewals.append(command["operation_id"])
        raise RuntimeError("lease no longer belongs to this worker")

    original_sleep = asyncio.sleep

    async def short_renew_sleep(delay, *args, **kwargs):
        if delay == 25:
            await entered.wait()
            return await original_sleep(0)
        return await original_sleep(delay, *args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="hmb-web-queued-lease-") as directory:
        engine = Engine()
        journal = web.OperationJournal(directory)
        worker = web.EngineWorker(engine, journal)
        node, agent, protocol, request = Generator(), QueuedAgent(), Protocol(), command()
        snapshot = {"params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}
        original = deepcopy((node.original, agent.original))
        protocol.renew = failed_renew
        gate = agent_module._agent_execution_gate(agent)
        assert gate.acquire(blocking=False)
        try:
            with patch.object(web.asyncio, "sleep", short_renew_sleep):
                task = asyncio.create_task(worker.execute(node, agent, snapshot, protocol, request))
                try:
                    await asyncio.wait_for(task, timeout=3)
                    raise AssertionError("expired lease execution was not cancelled")
                except asyncio.CancelledError:
                    pass
            assert entered.is_set() and renewals == [request["operation_id"]]
            assert task.cancelled() and gate.locked()
            assert agent.calls == 0 and node.executions == 0 and protocol.posts == []
        finally:
            gate.release()
        await original_sleep(0.06)
        assert agent.calls == 0 and protocol.posts == []
        key = journal.key(protocol.bridge.server_url, protocol.owner_key, request["operation_id"])
        assert journal.read(key)["state"] == "uncertain" and not worker.leases
        assert [event[0] for event in protocol.events] == ["agent_started", "failed"]
        restarted = web.EngineWorker(engine, web.OperationJournal(directory))
        await restarted.execute(node, agent, snapshot, protocol, request)
        assert agent.calls == 0 and node.executions == 0 and protocol.posts == []
        assert original == (node.original, agent.original)


async def main():
    for kind in ("success", "concurrent", "changed", "agent_uncertain", "render_uncertain", "prepared_failure", "cancelled", "lease_lost_at_ack"):
        await case(kind)
    unload_pending()
    await account_rotation()
    await lease_lost_while_waiting_for_agent()
    print("PASS web rerender worker: 11 offline lifecycle, account/lease/unload, queued-Agent lease cancellation, restart/replay and immutable-node cases; paid calls 0")


if __name__ == "__main__":
    asyncio.run(main())
