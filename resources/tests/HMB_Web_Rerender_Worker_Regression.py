"""Offline worker integration: paid-call stand-ins, durable replay and node isolation."""
from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import struct
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_web_rerender as web
from _hmb_web_rerender_settings_fixtures import freeze_command


class Engine:
    pass


class Protocol:
    def __init__(self):
        self.owner_key = "17"
        self.events = []
        self.posts = []
        self.fail_event = ""
        self.fail_exception = None
        self.open_exception = None
        self.on_event = None
        self.bridge = SimpleNamespace(server_url="https://broker.example", _opener=self)

    def open(self, request, *, timeout):
        self.posts.append((request.full_url, json.loads(request.data)))
        if self.open_exception is not None:
            raise self.open_exception
        return {"task_id": "job-child"}

    def renew(self, command):
        pass

    def result(self, command, event, **fields):
        self.events.append((event, deepcopy(fields)))
        if self.on_event is not None:
            self.on_event(event)
        if event == self.fail_event:
            raise self.fail_exception or RuntimeError("network failure")
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
        assert settings == {"priority": 0, "generate_audio": False}
        if self.pause is not None:
            await self.pause.wait()
        if self.fail:
            raise RuntimeError("model response lost")
        text = "resolved web output"
        return {"text": text, "run_id": "agent-run", "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "policy_identity": {"mode": "preserved_parent", "reinjected": False},
                "observation": {"private": "not journaled"}}


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
        yield SimpleNamespace()

    def _hmb_web_rerender_bind_parent_settings(self, claim, settings):
        assert settings["priority"] == 0 and settings["generate_audio"] is False
        claim.parent_generation_context = {"priority": settings["priority"], "generate_audio": settings["generate_audio"]}

    async def _hmb_web_rerender_prepare_media(self, claim):
        return {"images": ["one"], "videos": ["two"]}

    async def _hmb_web_rerender_execute(self, claim, result, **kwargs):
        self.executions += 1
        await kwargs["checkpoint_sink"]({"stage": "before_submit"}, reason="submit", required=True)
        bridge = kwargs["submission_bridge"]
        body = {"client_request_id": kwargs["client_request_id"], "model": "doubao-seedance-2-5-260628", "prompt": result["text"],
                "project_id": "superwings12", "project_name": "슈퍼윙즈12"}
        request = Request(bridge.server_url + "/api/v1/generate/video", data=json.dumps(body).encode(),
                          headers={"Idempotency-Key": kwargs["client_request_id"]}, method="POST")
        await asyncio.to_thread(bridge._opener.open, request, timeout=10)
        if self.fail_after_post:
            raise RuntimeError("response lost after acceptance")
        return {"task_id": "job-child", "video": "test.mp4", "status": "completed"}


def command():
    operation = str(uuid4())
    return freeze_command({"operation_id": operation, "render_key": "hmb-web-rerender-" + operation,
            "target_id": str(uuid4()), "session_id": str(uuid4()), "snapshot_sha256": "a" * 64,
            "web_prompt": "web review only", "parent_task_id": "job-parent", "review_id": str(uuid4()),
            "state": "claimed", "lease_id": str(uuid4()), "fence": 1,
            "policy_application": "preserved_parent", "policy_reinjected": False,
            "project_id": "superwings12", "project_name": "슈퍼윙즈12",
            "policy_required": False, "input_mode": "web_only",
            "exclude_authored_prompt": True, "preserve_connected_sources": True})


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
            assert protocol.events[1][1]["policy_application"] == "preserved_parent"
            assert protocol.events[1][1]["policy_reinjected"] is False
            assert record["document"]["agent_result"]["policy_identity"] == {"mode": "preserved_parent", "reinjected": False}
            assert worker.children[request["target_id"]] == ["job-child"]
        elif kind == "changed":
            assert agent.calls == 0 and not protocol.posts and record["state"] == "failed"
        elif kind in {"agent_uncertain", "cancelled"}:
            assert agent.calls == 1 and not protocol.posts and record["state"] == "uncertain"
        elif kind == "render_uncertain":
            assert agent.calls == 1 and len(protocol.posts) == 1 and record["state"] == "uncertain"
        elif kind == "prepared_failure":
            assert agent.calls == 1 and not protocol.posts and record["state"] == "failed"
            assert record["document"]["error_code"] == "prepared_request_failed"
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
        agent._hmb_web_rerender_policy_status = lambda project_id=None: {"ready": True, "version": "test"}
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
        node.parameter_output_values = {"generation_id": "job-parent"}
        node.get_parameter_value = lambda key: None
        worker = web.EngineWorker(engine, web.OperationJournal(directory))
        with patch.object(web._review, "task_origin", lambda task_id: "https://broker.example"):
            first, target, *_ = await worker._target(node)
            first.owner_key = "17"
            worker.children[target["target_id"]] = ["job-account-a-child"]
            node.token = "account-b-token"
            second, changed, *_ = await worker._target(node)
        assert first is not second and second.owner_key == "" and first.owner_key == "17"
        assert first.session_id != second.session_id and target["target_id"] != changed["target_id"]
        assert changed["parent_task_ids"] == ["job-parent"]


async def output_parent_readiness():
    """Native output-only IDs and recovery evidence keep their Broker boundary."""
    origin, other = "https://broker.example", "https://different.example"
    cases = (
        # Output-only IDs do not appear in native get_parameter_value.
        ("job-output", {}, origin, "job-output"),
        ("", {"task_id": "job-recovery", "broker_server_url": origin}, "", "job-recovery"),
        ("job-output", {"task_id": "job-output", "broker_server_url": origin}, origin, "job-output"),
        ("", {}, "", ""),
        ("job-output", {}, other, ""),
        ("job-output", {"task_id": "job-output", "broker_server_url": other}, origin, ""),
        ("job-output", {}, "", ""),
        ("job-output", {"task_id": "", "updated_at_ms": 1}, origin, ""),
        ("", {"task_id": "job-recovery", "broker_server_url": other}, "", ""),
        ("job-output", {"task_id": "job-old", "broker_server_url": origin}, "", ""),
    )
    with tempfile.TemporaryDirectory(prefix="hmb-web-parent-") as directory:
        engine = Engine()
        agent = Agent()
        agent.name = "agent"
        agent._hmb_web_rerender_policy_status = lambda project_id=None: {"ready": True, "version": "test"}
        agent._hmb_web_rerender_busy = lambda: False
        engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: agent)
        engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: "workflow")
        worker = web.EngineWorker(engine, web.OperationJournal(directory))
        engine_thread = threading.get_ident()
        for output_id, checkpoint, pinned, expected in cases:
            node = Generator()
            node.name = "generator"
            node.parameter_output_values = {"generation_id": output_id}
            node._selected_broker_server_url = lambda: origin
            node._create_broker_bridge = lambda **kwargs: SimpleNamespace(
                server_url=origin, _load_access_token=lambda: "same-offline-account")
            node._hmb_web_rerender_capture_inputs = lambda: {
                "agent_name": "agent", "target": {"flow_name": "flow"},
                "source_bindings": [], "binding_fingerprint": "a" * 64}
            node._hmb_web_rerender_readiness = lambda: {"ready": True}
            def value(key):
                assert key == "HMB_SEEDANCE_RECOVERY", "Heartbeat read output ID through input getter or consumed Resume input"
                return checkpoint
            node.get_parameter_value = value
            original = deepcopy((node.parameter_output_values, checkpoint))
            def read_origin(task_id):
                assert threading.get_ident() != engine_thread, "Origin file read blocked engine loop"
                return pinned
            with patch.object(web._review, "task_origin", read_origin):
                protocol, descriptor, *_ = await worker._target(node)
            assert descriptor["parent_task_ids"] == ([expected] if expected else [])
            assert descriptor["ready"] is bool(expected)
            assert descriptor["policy_application"] == "preserved_parent"
            assert descriptor["policy_reinjected"] is False
            assert protocol.owner_key == "", "Local Task identity established authenticated ownership"
            assert original == (node.parameter_output_values, checkpoint), "Heartbeat modified native history"
    return len(cases)


async def optional_project_policy_readiness():
    """Policy absence is truthful metadata after explicit server negotiation."""
    origin = "https://broker.example"
    project = {"project_id": "katuri8", "project_name": "까투리8"}
    capability = {"parent_settings_contract": web.PARENT_SETTINGS_SCHEMA,
                  "project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA,
                                      "project_ids": sorted(web.PROJECT_IDS)}}
    cases = (
        ("absent_supported", {"ready": True, "policy_verified": False, "policy_status": "absent", "version": ""}, True),
        ("absent_legacy", {"ready": True, "policy_verified": False, "policy_status": "absent", "version": ""}, False),
        ("available_legacy", {"ready": True, "policy_verified": True, "policy_status": "available", "version": "test"}, False),
        ("invalid_policy", {"ready": False, "policy_verified": False, "policy_status": "unavailable", "version": ""}, True),
    )
    for kind, policy, supported in cases:
        with tempfile.TemporaryDirectory(prefix="hmb-web-optional-policy-") as directory:
            engine, node, agent = Engine(), Generator(), Agent()
            node.name, agent.name = "generator", "agent"
            agent._hmb_web_rerender_policy_status = lambda project_id=None, value=policy: deepcopy(value)
            agent._hmb_web_rerender_busy = lambda: False
            engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: agent)
            engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: "workflow")
            requests = []
            def get_capability(method, route, *, payload, timeout):
                assert method == "GET" and route == "/api/v1/reviews/capabilities"
                assert payload is None and timeout == 10
                requests.append((method, route))
                return {**deepcopy(capability), **({
                    "optional_project_policy_status_supported": True,
                    "optional_project_policy_status_schema": "hmb-optional-agent-policy-status-v1",
                } if supported else {})}
            bridge = SimpleNamespace(server_url=origin, _load_access_token=lambda: "offline-optional-policy-token",
                                     _request_json=get_capability)
            node._selected_broker_server_url = lambda: origin
            node._create_broker_bridge = lambda **kwargs: bridge
            snapshot = {"agent_name": "agent", "target": {"flow_name": "flow"}, "project": project,
                        "source_bindings": [], "binding_fingerprint": "a" * 64}
            node._hmb_web_rerender_capture_inputs = lambda: deepcopy(snapshot)
            node._hmb_web_rerender_readiness = lambda: {"ready": True}
            node.parameter_output_values = {"generation_id": "job-parent"}
            node.get_parameter_value = lambda key: None
            before = deepcopy((node.original, node.parameter_output_values, agent.original))
            worker = web.EngineWorker(engine, web.OperationJournal(directory))
            with patch.object(web._review, "task_origin", lambda task_id: origin), \
                 patch.object(web._review, "task_project", lambda task_id: deepcopy(project)):
                info = await worker._target(node)
                if kind == "absent_legacy":
                    assert info is None, "An older strict server received an unsupported absent-policy descriptor"
                    protocol = worker.protocols[origin]
                    checked = protocol.policy_status_capability_checked_at
                    with patch.object(web.time, "monotonic", return_value=checked + 29):
                        assert await worker._target(node) is None
                    assert requests == [("GET", "/api/v1/reviews/capabilities")]
                    # Server deployment can advertise optional status while
                    # the desktop remains open. Rediscovery is read-only and
                    # bounded; the user graph/session need no forced reset.
                    supported = True
                    with patch.object(web.time, "monotonic", return_value=checked + 31):
                        _, upgraded, *_ = await worker._target(node)
                    assert upgraded["ready"] is True and upgraded["policy_verified"] is False
                    assert upgraded["policy_status"] == "absent"
                    assert requests == [("GET", "/api/v1/reviews/capabilities")] * 2
                else:
                    protocol, descriptor, *_ = info
                    assert descriptor["parent_task_ids"] == ["job-parent"]
                    assert descriptor["policy_verified"] is policy["policy_verified"]
                    assert descriptor["ready"] is policy["ready"]
                    assert descriptor["policy_version"] == policy["version"]
                    assert descriptor["policy_application"] == "preserved_parent"
                    assert descriptor["policy_reinjected"] is False
                    assert protocol.owner_key == "", "Local readiness inferred authenticated ownership"
                    if kind == "absent_supported":
                        assert descriptor["policy_status"] == "absent"
                        _, repeated, *_ = await worker._target(node)
                        assert repeated == descriptor
                        assert requests == [("GET", "/api/v1/reviews/capabilities")]
                        # Policy absence cannot bypass the parent project fence.
                        with patch.object(web._review, "task_project", lambda task_id: {
                            "project_id": "superwings12", "project_name": "슈퍼윙즈12"}):
                            _, mismatched, *_ = await worker._target(node)
                        assert mismatched["parent_task_ids"] == [] and mismatched["ready"] is False
                    else:
                        assert "policy_status" not in descriptor
                        assert requests == [], "Legacy available/invalid metadata triggered capability I/O"
            assert agent.calls == 0 and node.executions == 0
            assert before == (node.original, node.parameter_output_values, agent.original)
            assert not worker.active and not worker.leases
    return len(cases)


async def broker_origin_rotation():
    """Fence an in-flight A command and recover only authenticated A lineage."""
    origin_a, origin_b = "https://broker.example", "https://different.example"
    for fail_new_auth in (False, True):
        with tempfile.TemporaryDirectory(prefix="hmb-web-origin-") as directory:
            engine, node, agent = Engine(), Generator(), Agent()
            node.name, agent.name = "generator", "agent"
            node.origin = origin_a
            node.fail_new_auth = fail_new_auth
            agent.pause = asyncio.Event()
            agent._hmb_web_rerender_policy_status = lambda project_id=None: {"ready": True, "version": "test"}
            agent._hmb_web_rerender_busy = lambda: False
            engine.node_manager = SimpleNamespace(get_node_by_name=lambda name: agent)
            engine.context_manager = SimpleNamespace(get_current_workflow_name=lambda: "workflow")
            node._selected_broker_server_url = lambda: node.origin
            def bridge(*, server_url):
                def token():
                    if server_url == origin_b and node.fail_new_auth:
                        raise RuntimeError("offline authentication unavailable")
                    return "offline-account-token"
                return SimpleNamespace(server_url=server_url, _load_access_token=token)
            node._create_broker_bridge = bridge
            node.parameter_output_values = {"generation_id": "job-parent"}
            node.get_parameter_value = lambda key: None
            snapshot = {"agent_name": "agent", "target": {"flow_name": "flow"},
                        "source_bindings": [], "binding_fingerprint": "a" * 64,
                        "params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}
            node._hmb_web_rerender_capture_inputs = lambda: deepcopy(snapshot)
            node._hmb_web_rerender_readiness = lambda: {"ready": True}
            original = deepcopy((node.original, node.parameter_output_values, agent.original))
            journal = web.OperationJournal(directory)
            worker = web.EngineWorker(engine, journal)
            evidence = {"origin": origin_a}
            with patch.object(web._review, "task_origin", lambda task_id: evidence["origin"]):
                protocol_a, first, *_ = await worker._target(node)
                protocol_a.owner_key = "17"
                first_id = first["target_id"]
                worker.children[first_id] = ["job-memory-only-a"]
                for origin, owner, child in ((origin_a, "17", "job-journal-a"),
                                             (origin_a, "18", "job-other-account"),
                                             (origin_b, "17", "job-other-origin")):
                    record = journal.accept(origin=origin, owner_key=owner, command={
                        "command_id": str(uuid4()), "render_key": "hmb-seeded-" + uuid4().hex,
                        "parent_task_id": "job-parent"})
                    journal.transition(record["operation_key"], {"accepted"}, "completed", result={"task_id": child})
                request, executing_protocol = command(), Protocol()
                request["target_id"] = first_id
                running = asyncio.create_task(worker.execute(node, agent, snapshot, executing_protocol, request))
                worker.active[first_id] = running
                worker.active_origins[first_id] = origin_a
                running.add_done_callback(lambda done, target=first_id: worker._finished(target, done))
                while agent.calls == 0:
                    await asyncio.sleep(0)
                old_lease = worker.leases[first_id]
                assert old_lease.is_set()
                node.origin = origin_b
                if fail_new_auth:
                    try:
                        await worker._target(node)
                        raise AssertionError("Unavailable new authentication was accepted")
                    except RuntimeError as exc:
                        assert "authentication unavailable" in str(exc)
                    assert not old_lease.is_set() and first_id not in worker.children
                    node.fail_new_auth = False
                protocol_b, second, *_ = await worker._target(node)
                second_id = second["target_id"]
                assert second_id != first_id and not old_lease.is_set()
                assert second["parent_task_ids"] == [] and second["ready"] is False
                assert protocol_b.bridge.server_url == origin_b
                await asyncio.gather(running, return_exceptions=True)
                await asyncio.sleep(0)
                assert running.cancelled() and first_id not in worker.active and first_id not in worker.leases
                assert first_id not in worker.active_origins and first_id not in worker.children
                assert agent.calls == 1 and node.executions == 0 and not executing_protocol.posts
                key = journal.key(origin_a, "17", request["operation_id"])
                assert journal.read(key)["state"] == "uncertain"
                # A delayed callback from the retired target cannot remove a
                # subsequently registered task at the new target identity.
                later = asyncio.create_task(asyncio.Event().wait())
                worker.active[second_id] = later
                worker.active_origins[second_id] = origin_b
                worker._finished(first_id, running)
                assert worker.active[second_id] is later and worker.active_origins[second_id] == origin_b
                later.cancel()
                await asyncio.gather(later, return_exceptions=True)
                worker._finished(second_id, later)

                # A return to A mints another identity and requires current
                # parent origin evidence before reading origin/owner journal.
                node.origin = origin_a
                evidence["origin"] = ""
                _, unavailable, *_ = await worker._target(node)
                assert unavailable["target_id"] not in {first_id, second_id}
                assert unavailable["parent_task_ids"] == [] and unavailable["ready"] is False
                evidence["origin"] = origin_a
                _, restored, *_ = await worker._target(node)
                assert restored["target_id"] == unavailable["target_id"]
                assert restored["parent_task_ids"] == ["job-parent", "job-journal-a"]
                assert restored["ready"] is True

                # Settings can also change while credential lookup yields.
                # No descriptor from that mixed observation may be returned.
                loop = asyncio.get_running_loop()
                def changed_during_auth():
                    loop.call_soon_threadsafe(setattr, node, "origin", origin_b)
                    return "offline-account-token"
                protocol_a.bridge._load_access_token = changed_during_auth
                assert await worker._target(node) is None
                assert worker.target_origins[node] == origin_b
                assert worker.targets[node] != restored["target_id"]
            assert original == (node.original, node.parameter_output_values, agent.original)
    return 2


async def confirmed_descendant_lineage():
    """Preserve the real failed-client-key incident without advertising/replaying it."""
    origin = "https://broker.example"
    cases = (
        ("failed", "client_request", "submission_unknown", "submission_unknown", "client", None, origin, False),
        ("uncertain", "client_request", "submission_unknown", "submission_unknown", "client", None, origin, False),
        ("failed", "client_request", "pre_submit", "submitting", "client", None, origin, False),
        ("failed", "broker_task", "pre_submit", "submitting", "job", None, origin, False),
        ("uncertain", "broker_task", "accepted", "queued", "job", None, origin, True),
        ("failed", "broker_task", "timed_out", "timed_out", "job", None, origin, True),
        ("completed", "", "", "", "", "job", origin, True),
        ("submitted", "", "", "", "", "job", origin, True),
        ("failed", "", "", "", "", "job", origin, False),
        ("completed", "", "", "", "", "client", origin, False),
        ("uncertain", "broker_task", "submission_unknown", "submission_unknown", "job", None, origin, False),
        ("uncertain", "broker_task", "remote_succeeded", "succeeded", "job", None, "https://other.example", False),
    )
    with tempfile.TemporaryDirectory(prefix="hmb-web-confirmed-lineage-") as directory:
        journal = web.OperationJournal(directory)
        for index, (state, identity, stage, status, cp_kind, result_kind, cp_origin, expected) in enumerate(cases):
            request = command()
            if index == 0:
                request["operation_id"] = "0927cb53-4da5-4919-9ce4-afc7d13a3cd3"
                request["render_key"] = "hmb-web-rerender-" + request["operation_id"]
            request["parent_task_id"] = "job-parent-" + str(index)
            # These rows model historical commands which predate settings snapshots.
            for field in web.PARENT_SETTINGS_CONTRACT_FIELDS:
                request.pop(field, None)
            normalized = {"command_id": request["operation_id"], "render_key": request["render_key"],
                          "project_id": request["project_id"], "project_name": request["project_name"],
                          "parent_task_id": request["parent_task_id"], "review_id": request["review_id"],
                          "target_id": request["target_id"], "binding_fingerprint": request["snapshot_sha256"],
                          "prompt": request["web_prompt"]}
            record = journal.accept(origin=origin, owner_key="17", command=normalized)
            key = record["operation_key"]
            child = "job-confirmed-" + str(index)
            cp_id = request["render_key"] if cp_kind == "client" else child if cp_kind == "job" else ""
            result_id = request["render_key"] if result_kind == "client" else child if result_kind == "job" else ""
            checkpoint = {"stage": stage, "status": status, "task_identity": identity,
                          "task_id": cp_id, "broker_server_url": cp_origin,
                          "parent_task_id": request["parent_task_id"], "client_request_id": request["render_key"]}
            journal.transition(key, {"accepted"}, state, checkpoint=checkpoint,
                result={"task_id": result_id} if result_id else None,
                agent_result={"text": "saved Agent result", "run_id": "offline-agent"},
                error_code="execution_failed" if state == "failed" else "")
            before = deepcopy(journal.read(key))
            assert journal.descendants(origin, "17", request["parent_task_id"]) == ([child] if expected else [])
            assert journal.descendants(origin, "18", request["parent_task_id"]) == []
            assert journal.descendants("https://other.example", "17", request["parent_task_id"]) == []
            if index == 0:
                # A reconstructed worker consumes no Agent/render work for the
                # failed operation, retaining all recovery evidence unchanged.
                engine = Engine()
                restarted = web.EngineWorker(engine, web.OperationJournal(directory))
                node, agent, protocol = Generator(), Agent(), Protocol()
                await restarted.execute(node, agent, {}, protocol, request)
                assert node.claims == node.executions == agent.calls == 0 and not protocol.posts
            assert journal.read(key) == before, "Lineage filtering rewrote the recovery journal"

        # Normal multigeneration recovery is still transitive; an unconfirmed
        # client key cannot bridge unrelated tasks into the confirmed tree.
        record = journal.accept(origin=origin, owner_key="17", command={
            "command_id": str(uuid4()), "render_key": "hmb-grandchild", "parent_task_id": "job-confirmed-6"})
        journal.transition(record["operation_key"], {"accepted"}, "completed", result={"task_id": "job-grandchild"})
        assert journal.descendants(origin, "17", "job-parent-6") == ["job-confirmed-6", "job-grandchild"]
    return len(cases) + 1


async def prepared_acknowledgement_errors():
    """Only failed prepared calls carry the host marker and bounded HTTP code."""
    cases = (
        ("prepared", 409, "prepared_http_409"),
        ("prepared", 503, "prepared_http_503"),
        ("prepared", None, "prepared_request_failed"),
        ("prepared", True, "prepared_request_failed"),
        ("prepared", "409 PRIVATE_EXCEPTION_BODY_AUTH", "prepared_request_failed"),
        ("prepared", 0, "prepared_request_failed"),
        ("prepared", 600, "prepared_request_failed"),
        ("post", 503, "execution_uncertain"),
        ("agent_started", 409, "execution_uncertain"),
    )
    for phase, status, expected_code in cases:
        with tempfile.TemporaryDirectory(prefix="hmb-web-prepared-error-") as directory:
            engine, node, agent, protocol = Engine(), Generator(), Agent(), Protocol()
            journal = web.OperationJournal(directory)
            worker = web.EngineWorker(engine, journal)
            request = command()
            snapshot = {"params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}
            failure = RuntimeError("PRIVATE_EXCEPTION_BODY_AUTH prompt credential text must not be persisted")
            failure.status_code = status
            if phase == "post":
                protocol.open_exception = failure
            else:
                protocol.fail_event, protocol.fail_exception = phase, failure
            original = deepcopy((node.original, agent.original))
            await worker.execute(node, agent, snapshot, protocol, request)
            key = journal.key(protocol.bridge.server_url, protocol.owner_key, request["operation_id"])
            record = journal.read(key)
            assert record["state"] == ("failed" if phase == "prepared" else "uncertain")
            assert record["document"]["error_code"] == expected_code
            assert protocol.events[-1] == ("failed", {"error_code": expected_code})
            assert getattr(failure, "_hmb_web_submission_not_started", False) is (phase == "prepared")
            assert len(protocol.posts) == (1 if phase == "post" else 0)
            assert "PRIVATE_EXCEPTION_BODY_AUTH" not in web._json(record["document"])
            assert "_hmb_web_submission_not_started" not in web._json(protocol.events)
            assert "_hmb_web_submission_not_started" not in web._json(protocol.posts)
            assert original == (node.original, agent.original)
            before = (agent.calls, node.executions, len(protocol.posts))
            restarted = web.EngineWorker(engine, web.OperationJournal(directory))
            await restarted.execute(node, agent, snapshot, protocol, request)
            assert before == (agent.calls, node.executions, len(protocol.posts))
            assert journal.read(key) == record
    return len(cases)


async def preserved_parent_provenance():
    invalid = ({"mode": "reinjected", "reinjected": False},
               {"mode": "preserved_parent", "reinjected": True},
               {"mode": "preserved_parent", "reinjected": 0}, {}, None)
    for identity in invalid:
        with tempfile.TemporaryDirectory(prefix="hmb-web-policy-provenance-") as directory:
            engine, node, agent, protocol = Engine(), Generator(), Agent(), Protocol()
            journal = web.OperationJournal(directory)
            worker = web.EngineWorker(engine, journal)
            request = command()
            native = agent._hmb_run_web_rerender
            async def mismatched(*args):
                result = await native(*args)
                result["policy_identity"] = identity
                return result
            agent._hmb_run_web_rerender = mismatched
            await worker.execute(node, agent,
                {"params": {}, "generation_settings": {"seed": 0, "generate_audio": False}}, protocol, request)
            record = journal.read(journal.key(protocol.bridge.server_url, "17", request["operation_id"]))
            assert agent.calls == 1 and node.executions == 0 and not protocol.posts
            assert record["state"] == "uncertain" and record["document"]["agent_result"] is None
            assert not any(event == "prepared" for event, _ in protocol.events)
    return len(invalid)


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


def large_inline_media_fingerprint():
    # Valid PNG with uncompressed pixels: its inline request exceeds the
    # journal limit while remaining inside the Generator's 64 MiB allowance.
    def png_chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    pixels = (b"\x00" + b"\x80\x80\x80" * 1536) * 1536
    png = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1536, 1536, 8, 2, 0, 0, 0))
           + png_chunk(b"IDAT", zlib.compress(pixels, level=0)) + png_chunk(b"IEND", b""))
    source = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    request, protocol = command(), Protocol()
    text = "resolved web output 한글"
    result = {"text": text, "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
              "policy_identity": {"mode": "preserved_parent", "reinjected": False}}
    body = {"client_request_id": request["render_key"], "model": "doubao-seedance-2-5-260628", "prompt": text,
            "project_id": "superwings12", "project_name": "슈퍼윙즈12",
            "image_urls": [source], **request["frozen_generation_settings"]}
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert web._MAX_DOCUMENT < len(encoded) < 64 * 1024 * 1024
    # Matches the Broker's _canonical_request/_request_fingerprint algorithm.
    canonical = {key: value for key, value in body.items() if key != "client_request_id"}
    canonical["provider"] = "volcengine_ark"
    expected = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":")).encode("utf-8")).hexdigest()
    assert web.request_fingerprint(body) == expected
    assert web.request_fingerprint({**body, "Authorization": "excluded", "idempotency_key": "excluded"}) == expected

    with tempfile.TemporaryDirectory(prefix="hmb-web-inline-media-") as directory:
        journal = web.OperationJournal(directory)
        record = journal.accept(origin=protocol.bridge.server_url, owner_key="17", command={
            "command_id": request["operation_id"], "render_key": request["render_key"], "prompt": text})
        key = record["operation_key"]
        journal.transition(key, {"accepted"}, "render_preparing", agent_result=result)
        before = journal.read(key)
        try:
            journal.transition(key, {"render_preparing"}, "render_preparing", checkpoint=body)
            raise AssertionError("Oversized journal record was accepted")
        except ValueError as exc:
            assert str(exc) == "web_rerender_record_too_large"
        assert journal.read(key) == before, "Rejected oversized journal update was not rolled back"

        lease = threading.Event()
        lease.set()
        bridge = web.command_bridge(protocol, request, journal, key, result, lease)
        final_request = Request(bridge.server_url + "/api/v1/generate/video", data=encoded,
                                headers={"Idempotency-Key": request["render_key"]}, method="POST")
        assert bridge._opener.open(final_request, timeout=10) == {"task_id": "job-child"}
        assert len(protocol.posts) == 1 and protocol.posts[0][1] == body
        assert protocol.events[0][0] == "prepared"
        assert protocol.events[0][1]["render_payload_sha256"] == expected
        assert len(web._json(protocol.events).encode("utf-8")) < 2048
        saved = journal.read(key)
        assert saved["state"] == "submitting" and saved["document"]["checkpoint"] is None
        assert len(web._json(saved["document"]).encode("utf-8")) < 2048
    return 2


async def main():
    for kind in ("success", "concurrent", "changed", "agent_uncertain", "render_uncertain", "prepared_failure", "cancelled", "lease_lost_at_ack"):
        await case(kind)
    unload_pending()
    await account_rotation()
    parent_cases = await output_parent_readiness()
    optional_policy_cases = await optional_project_policy_readiness()
    origin_cases = await broker_origin_rotation()
    lineage_cases = await confirmed_descendant_lineage()
    prepared_cases = await prepared_acknowledgement_errors()
    policy_cases = await preserved_parent_provenance()
    await lease_lost_while_waiting_for_agent()
    media_cases = large_inline_media_fingerprint()
    print(f"PASS web rerender worker: {11 + parent_cases + optional_policy_cases + origin_cases + lineage_cases + prepared_cases + policy_cases + media_cases} offline lifecycle, optional-policy negotiation and truthful absent status, preserved-parent provenance, prepared acknowledgement errors, confirmed child lineage, output/recovery parent origin, Broker switch and callback fences, account/lease/unload, queued-Agent lease cancellation, large inline media and bounded journal, restart/replay and immutable-node cases; paid calls 0")


if __name__ == "__main__":
    asyncio.run(main())
