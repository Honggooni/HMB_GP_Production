"""Offline durable web-rerender journal and actual Broker transport contracts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_web_rerender as target
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("_web_rerender_transport_generator", ROOT / "HMBSeedanceGeneration.py")
generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generator
spec.loader.exec_module(generator)

ORIGIN = "https://broker.invalid"
WORKER, SESSION, TARGET, OPERATION, LEASE = [str(uuid4()) for _ in range(5)]
TEXT = '한국어 수정 {{SIGN}} / {% include "literal" %}'


def command():
    return {
        "operation_id": OPERATION, "command_id": OPERATION, "target_id": TARGET,
        "session_id": SESSION, "lease_id": LEASE, "fence": 3,
        "render_key": "hmb-web-rerender-" + OPERATION,
        "parent_task_id": "previous-render-task", "review_id": "review-1",
        "binding_fingerprint": "a" * 64, "prompt": TEXT, "web_prompt": TEXT,
        "web_prompt_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
        "exclude_authored_prompt": True, "preserve_connected_sources": True,
        "policy_required": True, "input_mode": "web_only",
    }


class ProtocolBridge:
    server_url = ORIGIN

    def __init__(self):
        self.calls = []
        self.response = {}

    def _request_json(self, method, route, **kwargs):
        self.calls.append((method, route, deepcopy(kwargs)))
        return deepcopy(self.response)


class RecordingOpener:
    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    def open(self, request, *, timeout):
        self.requests.append(request)
        if self.fail:
            raise TimeoutError("offline ambiguous provider submission")
        response = io.BytesIO(b'{"job_id":"new-render-task","status":"queued"}')
        response.status = 200
        response.geturl = lambda: request.full_url
        return response


class PreparedProtocol:
    def __init__(self, bridge, *, hook=None):
        self.bridge = bridge
        self.calls = []
        self.hook = hook

    def result(self, command, event, **fields):
        self.calls.append((deepcopy(command), event, deepcopy(fields)))
        if self.hook:
            self.hook()
        return {"operation_id": command["operation_id"]}


class TransportRegression(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hmb-web-transport-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.journal = target.OperationJournal(self.root)

    def accepted(self, current=None):
        return self.journal.accept(origin=ORIGIN, owner_key="123", command=current or command())

    def prepared(self, current=None):
        row = self.accepted(current)
        key = row["operation_key"]
        self.journal.transition(key, {"accepted"}, "agent_running")
        self.journal.transition(key, {"agent_running"}, "agent_succeeded", agent_result={"text": TEXT})
        self.journal.transition(key, {"agent_succeeded"}, "render_preparing")
        return key

    def opener(self, *, hook=None, underlying=None):
        current = command()
        key = self.prepared(current)
        underlying = underlying or RecordingOpener()
        protocol = PreparedProtocol(type("Bridge", (), {"server_url": ORIGIN})(), hook=hook)
        live = threading.Event(); live.set()
        result = {"text": TEXT, "output_sha256": hashlib.sha256(TEXT.encode()).hexdigest()}
        opener = target.CommandSubmissionOpener(underlying, protocol, current, self.journal, key, result, live)
        return opener, underlying, protocol, live, key

    @staticmethod
    def request(current=None, **extra):
        current = current or command()
        body = {"model": generator.SEEDANCE_2_5_MODEL_ID, "prompt": TEXT,
                "client_request_id": current["render_key"], "generate_audio": False, **extra}
        return Request(ORIGIN + "/api/v1/generate/video", data=json.dumps(body, ensure_ascii=False).encode(),
                       headers={"Idempotency-Key": current["render_key"]}, method="POST")

    def test_concurrent_duplicate_accept_and_restart(self):
        barrier = threading.Barrier(12)
        def accept(_):
            local = target.OperationJournal(self.root)
            barrier.wait()
            return local.accept(origin=ORIGIN, owner_key="123", command=command())
        with ThreadPoolExecutor(max_workers=12) as pool:
            rows = list(pool.map(accept, range(12)))
        self.assertEqual(len({row["operation_key"] for row in rows}), 1)
        key = rows[0]["operation_key"]
        with closing(sqlite3.connect(self.journal.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 1)
        self.journal.transition(key, {"accepted"}, "agent_running")
        replay = command(); replay["lease_id"] = str(uuid4()); replay["fence"] += 1
        reopened = target.OperationJournal(self.root)
        row = reopened.accept(origin=ORIGIN, owner_key="123", command=replay)
        self.assertEqual(row["state"], "agent_running")
        with self.assertRaises(RuntimeError):
            reopened.transition(key, {"accepted"}, "agent_running")
        self.assertNotIn("lease_id", row["document"]["command"])

    def test_cas_allows_one_consumer(self):
        key = self.accepted()["operation_key"]
        barrier = threading.Barrier(12)
        def claim(_):
            barrier.wait()
            try:
                target.OperationJournal(self.root).transition(key, {"accepted"}, "agent_running")
                return True
            except RuntimeError:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(claim, range(12))), 1)
        self.journal.transition(key, {"agent_running"}, "agent_succeeded", agent_result={"text": TEXT})
        self.assertEqual(target.OperationJournal(self.root).read(key)["document"]["agent_result"]["text"], TEXT)
        with self.assertRaises(ValueError):
            self.journal.transition(key, {"agent_succeeded"}, "render_preparing", prompt="overwrite original")

    def test_owner_origin_isolation_and_conflict(self):
        first = self.accepted()
        second = self.journal.accept(origin=ORIGIN, owner_key="456", command=command())
        third = self.journal.accept(origin="https://other-broker.invalid", owner_key="123", command=command())
        self.assertEqual(len({row["operation_key"] for row in (first, second, third)}), 3)
        for field, value in (("prompt", "changed"), ("render_key", "new-render-key"),
                             ("target_id", str(uuid4())), ("binding_fingerprint", "b" * 64)):
            changed = command(); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.accepted(changed)
        self.assertEqual(self.journal.read(first["operation_key"])["document"]["command"]["prompt"], TEXT)
        with self.assertRaises(ValueError):
            self.journal.output_directory("../escape")

    def test_protocol_registration_owner_binding_and_routes(self):
        bridge = ProtocolBridge(); protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
        bridge.response = {"schema": target.PROTOCOL, "worker_id": WORKER, "session_id": SESSION,
                           "registered": True, "user_id": 123}
        protocol.heartbeat([], register=True)
        self.assertEqual(protocol.owner_key, "123")
        self.assertEqual(bridge.calls[-1][1], target.API_ROOT + "/worker/register")
        bridge.response["user_id"] = 456
        with self.assertRaises(ValueError):
            protocol.heartbeat([])
        for malformed in (True, None, ""):
            fresh = target.BrokerProtocol(bridge, WORKER, SESSION)
            bridge.response["user_id"] = malformed
            with self.subTest(owner=malformed), self.assertRaises(ValueError):
                fresh.heartbeat([])
        for route in ("https://evil.invalid", "/../other", "/claim?unsafe=true"):
            with self.subTest(route=route), self.assertRaises(ValueError):
                protocol.request("POST", route, {})

    def test_protocol_rejects_malformed_leases_prompts_and_contracts(self):
        bridge = ProtocolBridge(); protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
        bridge.response = {"command": command()}
        self.assertEqual(protocol.claim(TARGET)["web_prompt"], TEXT)
        edits = [
            ("operation_id", "not-uuid"), ("target_id", str(uuid4())),
            ("session_id", str(uuid4())), ("render_key", "unbound"),
            ("lease_id", "bad-lease"), ("lease_id", None),
            ("fence", 0), ("fence", True), ("fence", "1"),
            ("web_prompt", ""), ("web_prompt", "  \n"), ("web_prompt", 42),
            ("web_prompt", "x" * 54001), ("web_prompt_sha256", "0" * 64),
            ("exclude_authored_prompt", False), ("preserve_connected_sources", False),
            ("policy_required", False), ("input_mode", "native"),
            ("exclude_authored_prompt", 1), ("preserve_connected_sources", 1), ("policy_required", 1),
        ]
        for field, value in edits:
            changed = command(); changed[field] = value
            bridge.response = {"command": changed}
            with self.subTest(field=field, value=str(value)[:40]), self.assertRaises(ValueError):
                protocol.claim(TARGET)
        for length in (50000, 54000):
            good = command(); good["web_prompt"] = "x" * length
            good["web_prompt_sha256"] = hashlib.sha256(good["web_prompt"].encode()).hexdigest()
            bridge.response = {"command": good}
            self.assertEqual(len(protocol.claim(TARGET)["web_prompt"]), length)

    def test_exact_one_post_and_restart_cannot_replay(self):
        opener, wire, protocol, live, key = self.opener()
        barrier = threading.Barrier(8)
        def submit(_):
            barrier.wait()
            try:
                opener.open(self.request(), timeout=1).close()
                return True
            except RuntimeError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(submit, range(8))), 1)
        self.assertEqual(len(wire.requests), 1)
        self.assertEqual(self.journal.read(key)["state"], "submitting")
        sent = wire.requests[0]
        self.assertEqual(sent.get_header("X-hmb-rerender-operation"), OPERATION)
        self.assertEqual(sent.get_header("X-hmb-rerender-lease"), LEASE)
        self.assertEqual(sent.get_header("X-hmb-rerender-fence"), "3")
        reopened = target.OperationJournal(self.root)
        new_opener = target.CommandSubmissionOpener(wire, protocol, command(), reopened, key, opener.agent_result, live)
        with self.assertRaises(RuntimeError):
            new_opener.open(self.request(), timeout=1)
        self.assertEqual(len(wire.requests), 1)

    def test_prepared_failure_lost_lease_and_agent_mismatch_never_post(self):
        for case in ("prepared_failure", "lease_already_lost", "lease_lost_during_prepared", "bad_agent_digest", "wrong_body_prompt"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                previous = self.journal
                self.journal = target.OperationJournal(folder)
                opener, wire, protocol, live, key = self.opener()
                request = self.request()
                if case == "prepared_failure":
                    protocol.hook = lambda: (_ for _ in ()).throw(RuntimeError("prepared refused"))
                elif case == "lease_already_lost":
                    live.clear()
                elif case == "lease_lost_during_prepared":
                    protocol.hook = live.clear
                elif case == "bad_agent_digest":
                    opener.agent_result["output_sha256"] = "f" * 64
                else:
                    request = self.request(prompt="stale different Agent prompt")
                with self.assertRaises((RuntimeError, ValueError)):
                    opener.open(request, timeout=1)
                self.assertEqual(wire.requests, [])
                self.journal = previous

    def test_ambiguous_post_is_never_retried(self):
        opener, wire, protocol, live, key = self.opener(underlying=RecordingOpener(fail=True))
        with self.assertRaises(TimeoutError):
            opener.open(self.request(), timeout=1)
        with self.assertRaises(RuntimeError):
            opener.open(self.request(), timeout=1)
        self.assertEqual(len(wire.requests), 1)
        self.assertEqual(target.OperationJournal(self.root).read(key)["state"], "submitting")

    def test_claim_headers_are_bound_to_exact_create_endpoint(self):
        opener, wire, protocol, live, key = self.opener()
        for url, method in ((ORIGIN + "/api/v1/jobs/old/refresh", "POST"),
                            (ORIGIN + "/api/v1/generate/video", "GET"),
                            ("https://other.invalid/api/v1/generate/video", "POST"),
                            (ORIGIN + "/api/v1/generate/video?different=1", "POST")):
            request = Request(url, data=b"{}" if method == "POST" else None, method=method)
            opener.open(request, timeout=1).close()
            self.assertFalse(any(key.lower().startswith("x-hmb-rerender-") for key in dict(request.header_items())))
        self.assertEqual(protocol.calls, [])
        self.assertEqual(self.journal.read(key)["state"], "render_preparing")

    def test_actual_generator_filtered_payload_is_prepared_fingerprint(self):
        wire = RecordingOpener()
        with patch.object(generator, "_broker_load_token", return_value="offline-synthetic-token"), patch.object(generator, "_broker_validated_server_url", return_value=ORIGIN):
            bridge = generator._HMBAIBrokerBridge(opener=wire, server_url=ORIGIN)
            protocol = PreparedProtocol(bridge)
            key = self.prepared()
            live = threading.Event(); live.set()
            result = {"text": TEXT, "output_sha256": hashlib.sha256(TEXT.encode()).hexdigest()}
            wrapped = target.command_bridge(protocol, command(), self.journal, key, result, live)
            payload = {"model": generator.SEEDANCE_2_0_MODEL_ID, "provider": "volcengine_ark",
                       "prompt": TEXT, "task": generator.TASK_TEXT_ONLY,
                       "output_format": "mp4", "return_last_frame": True,
                       "client_request_id": command()["render_key"], "generate_audio": False,
                       "duration_seconds": 4, "aspect_ratio": "16:9", "resolution": "1080p"}
            original = deepcopy(payload)
            for forbidden in ("api_key", "invented_field"):
                with self.subTest(forbidden=forbidden), self.assertRaises(generator._BrokerProtocolError):
                    wrapped.generate_seedance({**payload, forbidden: "DROP_UNKNOWN"}, timeout=1)
            self.assertEqual(wire.requests, [])
            response = wrapped.generate_seedance(payload, timeout=1)
        self.assertEqual(response["job_id"], "new-render-task")
        self.assertEqual(payload, original)
        self.assertEqual(len(wire.requests), 1)
        sent = json.loads(wire.requests[0].data.decode())
        for key in ("task", "output_format", "return_last_frame", "api_key", "invented_field"):
            self.assertNotIn(key, sent)
        self.assertIs(sent["generate_audio"], False)
        prepared = protocol.calls[0]
        self.assertEqual(prepared[1], "prepared")
        self.assertEqual(prepared[2]["agent_output"], TEXT)
        self.assertEqual(prepared[2]["render_payload_sha256"], target.request_fingerprint(sent))
        self.assertNotEqual(prepared[2]["render_payload_sha256"], target.request_fingerprint(original))
        self.assertIs(bridge._opener, wire)


if __name__ == "__main__":
    unittest.main(verbosity=2)
