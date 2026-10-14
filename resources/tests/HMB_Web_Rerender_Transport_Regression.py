"""Offline durable web-rerender journal and actual Broker transport contracts."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_web_rerender as target
from _hmb_web_rerender_settings_fixtures import freeze_command, wire_settings
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
    return freeze_command({
        "operation_id": OPERATION, "command_id": OPERATION, "target_id": TARGET,
        "session_id": SESSION, "lease_id": LEASE, "fence": 3,
        "render_key": "hmb-web-rerender-" + OPERATION,
        "parent_task_id": "previous-render-task", "review_id": "review-1",
        "binding_fingerprint": "a" * 64, "prompt": TEXT, "web_prompt": TEXT,
        "web_prompt_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
        "exclude_authored_prompt": True, "preserve_connected_sources": True,
        "policy_required": False, "input_mode": "web_only",
        "policy_application": "preserved_parent", "policy_reinjected": False,
        "project_id": "superwings12", "project_name": "슈퍼윙즈12",
    })


def agent_result():
    return {"text": TEXT, "output_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
            "policy_identity": {"mode": "preserved_parent", "reinjected": False}}


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
        result = agent_result()
        opener = target.CommandSubmissionOpener(underlying, protocol, current, self.journal, key, result, live)
        return opener, underlying, protocol, live, key

    @staticmethod
    def request(current=None, **extra):
        current = current or command()
        body = {"model": generator.SEEDANCE_2_5_MODEL_ID, "prompt": TEXT,
                "project_id": current["project_id"], "project_name": current["project_name"],
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
                           "parent_settings_contract": target.PARENT_SETTINGS_SCHEMA,
                           "project_routing": {"schema": target.PROJECT_ROUTING_SCHEMA,
                                               "project_ids": sorted(target.PROJECT_IDS)},
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

    def test_optional_policy_capability_requires_exact_schema_and_literal_true(self):
        base = {"parent_settings_contract": target.PARENT_SETTINGS_SCHEMA,
                "project_routing": {"schema": target.PROJECT_ROUTING_SCHEMA,
                                    "project_ids": sorted(target.PROJECT_IDS)}}
        cases = (
            (True, "hmb-optional-agent-policy-status-v1", True),
            (True, "foreign-v1", False),
            (1, "hmb-optional-agent-policy-status-v1", False),
            (False, "hmb-optional-agent-policy-status-v1", False),
            ("true", "hmb-optional-agent-policy-status-v1", False),
            (None, None, False),
        )
        for flag, schema, expected in cases:
            bridge = ProtocolBridge()
            bridge.response = {**deepcopy(base), "optional_project_policy_status_supported": flag,
                               "optional_project_policy_status_schema": schema}
            before = deepcopy(bridge.response)
            protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
            protocol.discover_capabilities()
            self.assertIs(protocol.optional_policy_status_supported, expected)
            self.assertTrue(protocol.policy_status_capability_checked)
            self.assertTrue(protocol.parent_settings_ready)
            self.assertEqual(protocol.owner_key, "")
            self.assertEqual(bridge.response, before)
            self.assertEqual(len(bridge.calls), 1)
            self.assertEqual(bridge.calls[0][:2], ("GET", "/api/v1/reviews/capabilities"))
            self.assertIsNone(bridge.calls[0][2]["payload"])

    def test_optional_policy_discovery_refresh_does_not_retain_stale_support(self):
        bridge = ProtocolBridge()
        base = {"parent_settings_contract": target.PARENT_SETTINGS_SCHEMA,
                "project_routing": {"schema": target.PROJECT_ROUTING_SCHEMA,
                                    "project_ids": sorted(target.PROJECT_IDS)}}
        protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
        bridge.response = {**base, "optional_project_policy_status_supported": True,
                           "optional_project_policy_status_schema": "hmb-optional-agent-policy-status-v1"}
        protocol.discover_capabilities()
        self.assertTrue(protocol.optional_policy_status_supported)
        bridge.response = deepcopy(base)
        protocol.discover_capabilities()
        self.assertFalse(protocol.optional_policy_status_supported)
        self.assertTrue(protocol.policy_status_capability_checked)
        self.assertEqual([call[0] for call in bridge.calls], ["GET", "GET"])
        self.assertEqual(protocol.owner_key, "")

    def test_legacy_heartbeat_omits_absent_targets_and_new_optional_fields(self):
        capability = {"parent_settings_contract": target.PARENT_SETTINGS_SCHEMA,
                      "project_routing": {"schema": target.PROJECT_ROUTING_SCHEMA,
                                          "project_ids": sorted(target.PROJECT_IDS)}}
        absent = {"target_id": str(uuid4()), "project_id": "katuri8", "project_name": "까투리8",
                  "policy_status": "absent", "policy_verified": False, "policy_version": "", "ready": True}
        available = {"target_id": TARGET, "project_id": "superwings12", "project_name": "슈퍼윙즈12",
                     "policy_status": "available", "policy_verified": True, "policy_version": "test", "ready": True}
        originals = deepcopy([absent, available])
        calls = []
        def request(method, route, *, payload, timeout):
            calls.append((method, route, deepcopy(payload)))
            if method == "GET":
                self.assertIsNone(payload)
                return deepcopy(capability)
            self.assertEqual(route, target.API_ROOT + "/worker/register")
            return {"schema": target.PROTOCOL, "worker_id": WORKER, "session_id": SESSION,
                    "registered": True, "user_id": 123, **capability}
        bridge = SimpleNamespace(server_url=ORIGIN, _request_json=request)
        protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
        protocol.heartbeat([absent, available], register=True)
        self.assertEqual([call[0] for call in calls], ["GET", "POST"])
        expected = deepcopy(available)
        expected.pop("policy_status")
        self.assertEqual(calls[-1][2]["targets"], [expected])
        self.assertEqual([absent, available], originals)
        self.assertFalse(protocol.optional_policy_status_supported)
        self.assertEqual(protocol.owner_key, "123")

    def test_first_registration_uses_actual_bridge_get_signature_and_bound_reply(self):
        capability = {"parent_settings_contract": target.PARENT_SETTINGS_SCHEMA,
                           "project_routing": {"schema": target.PROJECT_ROUTING_SCHEMA,
                                           "project_ids": sorted(target.PROJECT_IDS)}}
        descriptor = {"target_id": TARGET, "project_id": "superwings12", "project_name": "슈퍼윙즈12"}
        registration = {"schema": target.PROTOCOL, "worker_id": WORKER, "session_id": SESSION,
                        "registered": True, "user_id": 123, **capability}
        calls = []
        reply = deepcopy(registration)
        advertised_capability = deepcopy(capability)

        def open_request(request, *, timeout):
            self.assertEqual(timeout, 10)
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-registration-only")
            method, url = request.get_method(), request.full_url
            calls.append((method, url, deepcopy(request.data)))
            if method == "GET":
                self.assertEqual(url, ORIGIN + "/api/v1/reviews/capabilities")
                self.assertIsNone(request.data, "Capability GET must not serialize an empty JSON body")
                self.assertIsNone(request.get_header("Content-type"))
                body = advertised_capability
            else:
                self.assertEqual(method, "POST")
                self.assertIn(url, (ORIGIN + target.API_ROOT + "/worker/register",
                                    ORIGIN + target.API_ROOT + "/worker/heartbeat"))
                self.assertEqual(json.loads(request.data), {"worker_id": WORKER, "session_id": SESSION,
                                                           "targets": [descriptor]})
                body = reply
            response = io.BytesIO(json.dumps(body, ensure_ascii=False).encode("utf-8"))
            response.status = 200
            response.geturl = lambda: url
            return response

        # Keep the real request_json method and its mandatory payload keyword;
        # only the credential fixture and wire opener are replaced. A permissive
        # **kwargs bridge double would miss the production GET signature error.
        bridge = generator._HMBAIBrokerBridge(opener=SimpleNamespace(open=open_request), server_url=ORIGIN)
        with patch.object(bridge, "_load_access_token", return_value="synthetic-registration-only"), \
             patch("socket.create_connection", side_effect=AssertionError("External network forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("External network forbidden")):
            protocol = target.BrokerProtocol(bridge, WORKER, SESSION)
            protocol.heartbeat([descriptor], register=True)
            self.assertEqual([method for method, _, _ in calls], ["GET", "POST"])
            self.assertEqual(protocol.owner_key, "123")
            self.assertTrue(protocol.project_routing_ready)
            protocol.heartbeat([descriptor])
            self.assertEqual([method for method, _, _ in calls], ["GET", "POST", "POST"])
            self.assertTrue(calls[-1][1].endswith("/worker/heartbeat"))

            for field, value in (("worker_id", str(uuid4())), ("session_id", str(uuid4())),
                                 ("schema", "foreign-protocol"), ("registered", 1)):
                with self.subTest(binding_field=field):
                    calls.clear(); reply = {**registration, field: value}
                    fresh = target.BrokerProtocol(bridge, WORKER, SESSION)
                    with self.assertRaisesRegex(ValueError, "invalid_web_rerender_registration"):
                        fresh.heartbeat([descriptor], register=True)
                    self.assertEqual([method for method, _, _ in calls], ["GET", "POST"])
                    self.assertEqual(fresh.owner_key, "")
                    self.assertFalse(fresh.project_routing_ready)

            calls.clear(); advertised_capability = {}
            fresh = target.BrokerProtocol(bridge, WORKER, SESSION)
            with self.assertRaisesRegex(ValueError, "project_server_upgrade_required"):
                fresh.heartbeat([descriptor], register=True)
            self.assertEqual([method for method, _, _ in calls], ["GET"])
            self.assertEqual(fresh.owner_key, "")
        self.assertEqual(self.journal.descendants(ORIGIN, "123", "previous-render-task"), [])

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
            ("policy_required", True), ("input_mode", "native"),
            ("exclude_authored_prompt", 1), ("preserve_connected_sources", 1), ("policy_required", 1),
            ("policy_required", 0), ("policy_application", "reinjected"),
            ("policy_application", None), ("policy_reinjected", True), ("policy_reinjected", 0),
        ]
        for field, value in edits:
            changed = command(); changed[field] = value
            bridge.response = {"command": changed}
            with self.subTest(field=field, value=str(value)[:40]), self.assertRaises(ValueError):
                protocol.claim(TARGET)
        for field in ("policy_application", "policy_reinjected"):
            missing = command(); missing.pop(field)
            bridge.response = {"command": missing}
            with self.subTest(missing=field), self.assertRaises(ValueError):
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

    def test_prepared_rejection_and_timeout_keep_create_unstarted(self):
        for failure in ("conflict", "translated_timeout", "raw_timeout"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                journal = target.OperationJournal(folder)
                current = command()
                row = journal.accept(origin=ORIGIN, owner_key="123", command=current)
                key = row["operation_key"]
                journal.transition(key, {"accepted"}, "render_preparing")
                wire = RecordingOpener()
                bare = generator._HMBAIBrokerBridge(opener=wire, server_url=ORIGIN)
                bare._load_access_token = lambda: "offline-fixture-only"
                error = (generator._BrokerError("prepared conflict", status_code=409)
                         if failure == "conflict" else
                         generator._BrokerUnavailableError("prepared timeout")
                         if failure == "translated_timeout" else TimeoutError("prepared timeout"))
                protocol = PreparedProtocol(bare, hook=lambda: (_ for _ in ()).throw(error))
                live = threading.Event(); live.set()
                result = agent_result()
                bridge = target.command_bridge(protocol, current, journal, key, result, live)
                with self.assertRaises(generator._BrokerError) as raised:
                    bridge._request_json("POST", "/api/v1/generate/video", timeout=1,
                                         payload={"model": current["frozen_generation_settings"]["model"], "prompt": TEXT, "client_request_id": current["render_key"],
                                                  "project_id": current["project_id"], "project_name": current["project_name"]},
                                         submission=True, idempotency_key=current["render_key"])
                self.assertIs(raised.exception._hmb_web_submission_not_started, True)
                self.assertIs(raised.exception.submission_outcome_unknown, False)
                if failure == "conflict":
                    self.assertEqual(raised.exception.status_code, 409)
                self.assertEqual(wire.requests, [])
                self.assertEqual(journal.read(key)["state"], "render_preparing")

    def test_real_create_errors_remain_unknown_without_preflight_marker(self):
        for failure in ("timeout", "protocol"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                journal = target.OperationJournal(folder)
                current = command()
                key = journal.accept(origin=ORIGIN, owner_key="123", command=current)["operation_key"]
                journal.transition(key, {"accepted"}, "render_preparing")
                wire = RecordingOpener(fail=failure == "timeout")
                if failure == "protocol":
                    def invalid_response(request, *, timeout):
                        wire.requests.append(request)
                        # An arbitrary response field cannot grant the internal
                        # exception authority to say a POST never happened.
                        response = io.BytesIO(b'[{"_hmb_web_submission_not_started":true}]')
                        response.status = 200
                        response.geturl = lambda: request.full_url
                        return response
                    wire.open = invalid_response
                bare = generator._HMBAIBrokerBridge(opener=wire, server_url=ORIGIN)
                bare._load_access_token = lambda: "offline-fixture-only"
                protocol = PreparedProtocol(bare)
                live = threading.Event(); live.set()
                result = agent_result()
                bridge = target.command_bridge(protocol, current, journal, key, result, live)
                with self.assertRaises(generator._BrokerError) as raised:
                    bridge._request_json("POST", "/api/v1/generate/video", timeout=1,
                                         payload={"model": current["frozen_generation_settings"]["model"], "prompt": TEXT, "client_request_id": current["render_key"],
                                                  "project_id": current["project_id"], "project_name": current["project_name"]},
                                         submission=True, idempotency_key=current["render_key"])
                self.assertIs(raised.exception.submission_outcome_unknown, True)
                self.assertIsNot(getattr(raised.exception, "_hmb_web_submission_not_started", None), True)
                self.assertEqual(len(wire.requests), 1)
                self.assertEqual(journal.read(key)["state"], "submitting")

    def test_prepared_failure_discards_provisional_checkpoint_without_changing_node(self):
        # Reuse the real Generator fixture's isolated native-node environment.
        spec = importlib.util.spec_from_file_location(
            "_transport_preflight_generator_fixture", ROOT / "resources/tests/HMB_Seedance_Web_Rerender_Regression.py")
        fixture = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = fixture
        spec.loader.exec_module(fixture)
        module, base, execution = fixture.target, fixture.Base, fixture.Execution
        with ExitStack() as stack:
            folder = stack.enter_context(tempfile.TemporaryDirectory())
            stack.enter_context(patch.dict(os.environ, {"LOCALAPPDATA": folder}))
            for owner, name, replacement in (
                (base, "_runtime_node_is_live", lambda self, **kw: not self._hmb_node_deleted),
                (base, "_manual_agent_prompt_source", lambda self: fixture.agent),
                (base, "_exact_incoming_source", lambda self, *a, **kw: None),
                (base, "_has_incoming_parameter_connection", lambda self, name: False),
                (base, "_generation_recovery_blocks_new_submission", lambda self: False),
                (module.GriptapeNodes, "NodeManager", lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "flow-web")),
                (execution, "_preflight_output_destination", lambda *a, **kw: None),
                (execution, "_prepare_video_references_for_run", lambda self, params: params),
                (module._HMBWebRerenderOutput, "build_file", lambda self: object()),
                (module, "_resolve_mp4_decode_verifier", lambda: SimpleNamespace(executable="offline", backend="offline")),
                (module, "_get_build_diagnostics", lambda: {}),
            ):
                stack.enter_context(patch.object(owner, name, replacement, create=True))

            async def verify():
                for failure in ("conflict", "timeout"):
                    node = fixture.new_node()
                    checkpoints = []
                    def sink(value, *, reason, required):
                        checkpoints.append((deepcopy(value), reason))
                    bridge = fixture.Broker(checkpoints)
                    error = (module._BrokerError("prepared rejected", status_code=409) if failure == "conflict"
                             else module._BrokerUnavailableError("prepared timeout"))
                    error._hmb_web_submission_not_started = True
                    def reject(*args, **kwargs):
                        raise error
                    bridge.generate_seedance = reject
                    snapshot = node._hmb_web_rerender_capture_inputs()
                    with self.subTest(failure=failure):
                        async with node._hmb_web_rerender_claim(snapshot) as claim:
                            node._hmb_web_rerender_bind_parent_settings(claim, wire_settings(snapshot["generation_settings"]))
                            await node._hmb_web_rerender_prepare_media(claim)
                            with self.assertRaises(module._BrokerError) as raised:
                                await node._hmb_web_rerender_execute(claim, fixture.result(),
                                    client_request_id="hmb-preflight-" + failure, output_directory=folder,
                                    checkpoint_sink=sink, submission_bridge=bridge, parent_task_id="original-task")
                        self.assertIs(raised.exception, error)
                        self.assertIs(raised.exception.submission_outcome_unknown, False)
                        self.assertEqual(bridge.calls, [])
                        self.assertIn("web_prepared_not_submitted", [reason for _, reason in checkpoints])
                        self.assertFalse(checkpoints[-1][0].get("task_id"))
                        self.assertNotIn("submission_unknown", [value.get("status") for value, _ in checkpoints])
                        fixture.unchanged(node)
            asyncio.run(verify())

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
            current = freeze_command(command(), {"model": generator.SEEDANCE_2_0_MODEL_ID,
                "input_mode": generator.INPUT_MODE_TEXT_ONLY, "resolution": "1080p",
                "duration_seconds": 4, "aspect_ratio": "16:9", "generate_audio": False})
            key = self.prepared(current)
            live = threading.Event(); live.set()
            result = agent_result()
            wrapped = target.command_bridge(protocol, current, self.journal, key, result, live)
            payload = {"model": generator.SEEDANCE_2_0_MODEL_ID, "provider": "volcengine_ark",
                       "project_id": "superwings12", "project_name": "슈퍼윙즈12",
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
