"""No-network maintenance reference lifetime, account and native reopen checks.

Cloud/TOS handles and media bytes are synthetic. Native SDK serialization and
the real Only controller are exercised; no provider/storage calls are allowed.
"""
from __future__ import annotations

import asyncio
import ast
from collections import namedtuple
from contextlib import contextmanager, suppress
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_reference_leases as leases
import _hmb_broker_config as broker_config
import _hmb_my_box as my_box

ORIGIN = "https://broker.invalid/gateway"
PRINCIPAL = leases.principal_fingerprint({"id": 3, "display_name": "never compare this"}, ORIGIN)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="hmb-reference-lease-offline-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patch = mock.patch.dict(os.environ, {"APPDATA": str(self.root)})
        patch.start(); self.addCleanup(patch.stop)
        self.cloud, self.tos = mock.Mock(), mock.Mock()

    def acquire(self, index=1, scope="video", principal=PRINCIPAL):
        return leases.acquire(origin=ORIGIN, principal=principal, client_request_id=f"hmb-offline-{index}",
            cloud=[(self.cloud, Path(f"artifact_url_storage/offline-{index}/input.mov"))],
            tos=[(self.tos, "fixture-bucket", f"hmb-seedance-temp/offline-{index}.mov")], scope=scope)

    def observe(self, identifier, response, index=1, **kwargs):
        return leases.observe(identifier, origin=kwargs.get("origin", ORIGIN), principal=kwargs.get("principal", PRINCIPAL),
            requested_id=kwargs.get("requested_id", f"hmb-offline-{index}"), response=response)

    def queued(self, index=1, state="waiting"):
        return dict(job_id=f"job-offline-{index}", client_request_id=f"hmb-offline-{index}",
            status="submission_unknown" if state == "uncertain" else "failed" if state == "blocked" else "pending",
            maintenance_queued=True, maintenance_state=state, resubmit_allowed=False)

    def test_five_shots_old_and_new_runs_never_consume_each_other(self):
        old = [self.acquire(i) for i in range(1, 6)]
        for index, identifier in enumerate(old, 1):
            self.assertEqual(self.observe(identifier, self.queued(index), index), ([], []))
        new = self.acquire(6)
        for index, identifier in enumerate(old, 1):
            for other in range(1, 7):
                if other != index:
                    self.assertEqual(self.observe(identifier, {"job_id": f"job-offline-{other}", "status": "completed"},
                        index, requested_id=f"job-offline-{other}"), ([], []))
            self.assertTrue(leases.pending_metadata(identifier)["unresolved"])
            released = self.observe(identifier, {"job_id": f"job-offline-{index}", "status": "completed"}, index,
                requested_id=f"job-offline-{index}")
            self.assertEqual([len(x) for x in released], [1, 1])
            self.assertEqual(self.observe(identifier, {"job_id": f"job-offline-{index}", "status": "completed"}, index), ([], []))
        self.assertTrue(leases.pending_metadata(new)["unresolved"])

    def test_marker_missing_unknown_404_503_local_cancel_or_delete_do_not_release(self):
        identifier = self.acquire()
        self.observe(identifier, self.queued())
        for response in (None, {}, {"status": 404}, {"status": 503},
            {"job_id": "job-offline-1", "status": "running"},
            {"job_id": "job-offline-1", "status": "cancelled"},
            {"job_id": "job-offline-1", "status": "failed", "error_code": "submission_unknown", "terminal": True},
            {"job_id": "job-offline-1", "status": "failed", "resubmit_allowed": False},
            self.queued(state="dispatching"), self.queued(state="uncertain"), self.queued(state="blocked")):
            with self.subTest(response=response):
                self.assertEqual(self.observe(identifier, response), ([], []))
                self.assertTrue(leases.pending_metadata(identifier)["unresolved"])
                self.assertTrue(leases.pending_metadata(identifier)["queue_held"])
        self.assertEqual(leases.reject_unsubmitted(identifier), ([], []))

    def test_lost_202_provisional_key_promotes_only_matching_response(self):
        identifier = self.acquire()
        # No response from create: the original key still owns both handles.
        self.assertEqual(leases.pending_metadata(identifier)["task_id"], "")
        self.assertEqual(self.observe(identifier, self.queued(), origin="https://other.invalid"), ([], []))
        self.assertEqual(self.observe(identifier, self.queued(), principal="different-account"), ([], []))
        self.assertEqual(self.observe(identifier, dict(self.queued(), client_request_id="wrong-key")), ([], []))
        self.assertEqual(leases.pending_metadata(identifier)["task_id"], "")
        self.observe(identifier, self.queued())
        self.assertEqual(leases.pending_metadata(identifier)["task_id"], "job-offline-1")
        self.assertEqual(self.observe(identifier, {"job_id": "different-job", "status": "completed"}), ([], []))
        self.assertEqual([len(x) for x in self.observe(identifier, {"job_id": "job-offline-1", "status": "failed"})], [1, 1])

    def test_only_video_blocked_explicit_terminal_can_release(self):
        for scope in ("video", "my_box"):
            identifier = self.acquire(scope=scope)
            self.observe(identifier, self.queued())
            blocked = dict(self.queued(state="blocked"), terminal=True)
            self.assertEqual([len(x) for x in self.observe(identifier, blocked)], [1, 1] if scope == "video" else [0, 0])
            if scope == "my_box":
                self.assertTrue(leases.pending_metadata(identifier)["unresolved"])
                completed = {"job_id": "job-offline-1", "status": "completed", "resubmit_allowed": False}
                self.assertEqual([len(x) for x in self.observe(identifier, completed)], [1, 1])

    def test_reopen_journal_has_no_clients_urls_secrets_or_auto_cleanup(self):
        identifier = self.acquire()
        self.observe(identifier, self.queued())
        path = leases._journal_path(identifier)
        data = json.loads(path.read_text("utf-8"))
        self.assertEqual(set(data), {"schema", "version", "updated_at_ms", "lease_id", "origin", "account_fingerprint",
            "process_epoch", "client_request_id", "task_id", "queue_held", "unresolved", "scope", "remote_objects"})
        self.assertEqual(data["remote_objects"][1]["key"], "hmb-seedance-temp/offline-1.mov")
        self.assertNotIn("Mock", path.read_text("utf-8"))
        before = path.read_bytes()
        spec = importlib.util.spec_from_file_location("lease_new_process_fixture", ROOT / "_hmb_reference_leases.py")
        reopened = importlib.util.module_from_spec(spec); spec.loader.exec_module(reopened)
        self.assertEqual(reopened.observe(identifier, origin=ORIGIN, principal=PRINCIPAL,
            requested_id="job-offline-1", response={"job_id": "job-offline-1", "status": "completed"}), ([], []))
        self.assertEqual(before, path.read_bytes())
        self.cloud.delete_file.assert_not_called(); self.tos.delete_object.assert_not_called()

    def test_bad_paths_unverified_account_and_failed_journal_never_authorize_delete(self):
        for path in ("https://host.invalid/key?secret=private", "key?signature=secret", "../foreign", "C:/local"):
            with self.assertRaises(ValueError):
                leases.acquire(origin=ORIGIN, principal=PRINCIPAL, client_request_id="hmb-offline",
                    cloud=[(self.cloud, path)], tos=[])
        identifier = self.acquire(principal="")
        self.assertEqual(self.observe(identifier, {"job_id": "job-offline-1", "status": "completed"}, principal=""), ([], []))
        identifier = self.acquire(2)
        with mock.patch.object(leases, "_write", side_effect=OSError("offline journal failure")):
            with self.assertRaises(OSError):
                self.observe(identifier, {"job_id": "job-offline-2", "status": "completed"}, 2)
        self.assertTrue(leases.pending_metadata(identifier)["unresolved"])
        self.assertEqual([len(x) for x in self.observe(identifier, {"job_id": "job-offline-2", "status": "completed"}, 2)], [1, 1])

    def test_account_name_is_not_principal_and_projection_is_bounded(self):
        self.assertEqual(PRINCIPAL, leases.principal_fingerprint({"user": {"id": 3, "display_name": "other"}}, ORIGIN))
        self.assertNotEqual(PRINCIPAL, leases.principal_fingerprint({"id": 4}, ORIGIN))
        self.assertEqual(leases.principal_fingerprint({"display_name": "comp"}, ORIGIN), "")
        self.assertEqual(leases.safe_queue_fields({"maintenance_state": {}, "maintenance_queued": "true"}), {})
        self.assertEqual(leases.safe_queue_fields({"maintenance_queued": True, "maintenance_state": "waiting", "secret": "no"}),
            {"maintenance_queued": True, "maintenance_state": "waiting"})


def isolated_bridge_methods():
    """Actual Bridge bodies and real urllib Request; only loader/opener are fake."""
    tree = ast.parse((ROOT / "HMBSeedanceGeneration.py").read_text("utf-8"))
    original = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_HMBAIBrokerBridge")
    names = {"__init__", "server_url", "_load_access_token", "_clear_access_token", "_forget_reference_auth",
        "_reference_auth_response", "_reference_principal_scope", "_reference_transfer_response", "_request_json",
        "account_snapshot", "_safe_account", "_account_from_mapping", "_safe_http_error_message", "_http_error_summary",
        "queue_admission", "_queue_admission_headers", "_queue_syntax"}
    selected = [deepcopy(node) for node in original.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    bridge = ast.ClassDef(name="ActualAuthBridge", bases=[], keywords=[], body=selected, decorator_list=[])
    helpers = [deepcopy(node) for node in tree.body if
        isinstance(node, ast.FunctionDef) and node.name in {"_broker_read_json", "_broker_require_exact_response_url"}
        or isinstance(node, ast.ClassDef) and node.name in {"_BrokerError", "_BrokerUnavailableError", "_BrokerAuthenticationError", "_BrokerProtocolError"}]
    namespace = dict(hashlib=hashlib, threading=threading, contextmanager=contextmanager, suppress=suppress,
        json=json, re=re, urllib=urllib, _reference_leases=leases, _broker_config=broker_config,
        _broker_validated_server_url=broker_config.normalize_broker_base_url,
        _BrokerAccountSnapshot=namedtuple("AccountSnapshot", "state connected account"),
        _BROKER_LEGACY_AUTH_GATEWAY="https://legacy-fixture.invalid", _TASK_ID_PATTERN=re.compile(r"[A-Za-z0-9_.:-]+\Z"),
        MAX_REQUEST_BYTES=64*1024*1024, AI_BROKER_MAX_JSON_BYTES=2*1024*1024,
        BROKER_FAILURE_STATUSES={"failed"}, BROKER_CANCELLED_STATUSES={"cancelled"}, BROKER_EXPIRED_STATUSES={"expired"},
        _broker_error_details=lambda value, **kwargs: "offline fixture rejection")
    module = ast.Module(body=helpers + [bridge], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<actual-bridge-auth-methods>", "exec"), namespace)
    namespace["ActualAuthBridge"]._MAX_ERROR_CLASSIFICATION_BYTES = 64*1024
    return namespace


class AuthContinuityTests(unittest.TestCase):
    """Auth changes may hold cleanup; they must never invent transport proof."""
    acquire = LeaseTests.acquire

    def setUp(self):
        LeaseTests.setUp(self)
        self.ns = isolated_bridge_methods()
        self.auth = {"current": "fixture-A", "failure": False}
        self.calls = []
        self.handler = None
        self.clears = mock.Mock()
        def load(**kwargs):
            if self.auth["failure"]:
                raise self.ns["_BrokerAuthenticationError"]("offline missing credential")
            return self.auth["current"]
        self.ns["_broker_load_token"] = load
        self.ns["_broker_clear_token"] = self.clears
        class Response(io.BytesIO):
            status = 200
            def __init__(self, request, data):
                super().__init__(json.dumps(data).encode("utf-8")); self.url = request.full_url
            def geturl(self): return self.url
        def open_request(request, timeout):
            label = request.get_header("Authorization")[7:]
            path = urlsplit(request.full_url).path.removeprefix("/gateway")
            self.calls.append((request.get_method(), path))
            data = self.handler(label, path) if self.handler else None
            if data is None:
                data = {"id": 3 if label == "fixture-A" else 4, "display_name": "unrelated"} if path == "/api/me" else {
                    "job_id": "job-offline-1", "status": "completed"}
            return Response(request, data)
        self.bridge = self.ns["ActualAuthBridge"](opener=SimpleNamespace(open=open_request), server_url=ORIGIN)
        self.bridge._open_create_request = open_request
        self.assertTrue(self.bridge.account_snapshot(connect=False).connected)
        self.assertEqual(self.calls, [("GET", "/api/me")])

    def fetch(self):
        return self.bridge._request_json("POST", "/api/v1/jobs/job-offline-1/refresh", payload=None, timeout=1)

    def observe_authenticated(self, identifier, response, *, requested_id="hmb-offline-1"):
        with self.bridge._reference_principal_scope(response) as principal:
            return leases.observe(identifier, origin=ORIGIN, principal=principal, requested_id=requested_id, response=response)

    def blocked_request(self, path, expected_label="fixture-A"):
        started, release = threading.Event(), threading.Event()
        def handler(label, requested):
            if label == expected_label and requested == path:
                started.set()
                if not release.wait(5): raise AssertionError("Synthetic auth race was not released")
            return None
        self.handler = handler
        result, errors = [], []
        def worker():
            try:
                result.append(self.bridge.account_snapshot(connect=False) if path == "/api/me" else self.fetch())
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        self.addCleanup(release.set)
        self.addCleanup(thread.join, 6)
        self.assertTrue(started.wait(5))
        return release, thread, result, errors

    def test_same_bearer_exact_response_releases_once_and_keeps_json_plain(self):
        identifier = self.acquire()
        response = self.fetch()
        self.assertEqual(set(response), {"job_id", "status", "_http_status"})
        self.assertEqual([len(value) for value in self.observe_authenticated(identifier, response)], [1, 1])
        self.assertEqual(self.observe_authenticated(identifier, response), ([], []))
        self.assertEqual(sum(path == "/api/me" for _, path in self.calls), 1)
        for value in self.root.rglob("*.json"):
            self.assertNotIn("fixture-A", value.read_text("utf-8"))
            self.assertNotIn(self.bridge._reference_auth_digest, value.read_text("utf-8"))

    def test_bearer_switch_admin_terminal_of_original_task_cannot_release_old_account(self):
        identifier = self.acquire()
        self.auth["current"] = "fixture-B"
        response = self.fetch()
        self.assertEqual(self.bridge._reference_account_fingerprint, "")
        self.assertEqual(self.observe_authenticated(identifier, response), ([], []))
        self.assertTrue(self.bridge.account_snapshot(connect=False).connected)
        response = self.fetch()
        self.assertEqual(self.observe_authenticated(identifier, response), ([], []))
        self.assertTrue(leases.pending_metadata(identifier)["unresolved"])

    def test_late_a_terminal_cannot_borrow_new_b_principal(self):
        release, thread, result, errors = self.blocked_request("/api/v1/jobs/job-offline-1/refresh")
        self.auth["current"] = "fixture-B"
        self.bridge.account_snapshot(connect=False)
        principal_b = leases.principal_fingerprint({"id": 4}, ORIGIN)
        identifier = self.acquire(principal=principal_b)
        release.set(); thread.join(6)
        self.assertFalse(thread.is_alive()); self.assertFalse(errors)
        self.assertEqual(self.observe_authenticated(identifier, result[0]), ([], []))
        with self.bridge._reference_principal_scope() as principal:
            self.assertEqual(principal, principal_b)

    def test_late_a_me_cannot_rebind_after_b_snapshot(self):
        release, thread, result, errors = self.blocked_request("/api/me")
        self.auth["current"] = "fixture-B"
        self.bridge.account_snapshot(connect=False)
        release.set(); thread.join(6)
        self.assertFalse(thread.is_alive()); self.assertFalse(errors)
        with self.bridge._reference_principal_scope() as principal:
            self.assertEqual(principal, leases.principal_fingerprint({"id": 4}, ORIGIN))

    def test_a_b_a_rotation_does_not_revive_old_response_epoch(self):
        release, thread, result, errors = self.blocked_request("/api/v1/jobs/job-offline-1/refresh")
        old_epoch = self.bridge._reference_auth_epoch
        for label in ("fixture-B", "fixture-A"):
            self.auth["current"] = label
            self.bridge.account_snapshot(connect=False)
        self.assertGreater(self.bridge._reference_auth_epoch, old_epoch)
        release.set(); thread.join(6)
        self.assertFalse(thread.is_alive()); self.assertFalse(errors)
        with self.bridge._reference_principal_scope(result[0]) as principal:
            self.assertEqual(principal, "")

    def test_401_explicit_clear_and_load_failure_forget_proofs(self):
        for failure in ("401", "clear", "load"):
            with self.subTest(failure=failure):
                self.auth["failure"] = False; self.handler = None
                self.bridge.account_snapshot(connect=False)
                response = self.fetch()
                if failure == "401":
                    def rejected(label, path):
                        raise urllib.error.HTTPError(ORIGIN + path, 401, "offline", {}, io.BytesIO(b'{"error":"denied"}'))
                    self.handler = rejected
                    with self.assertRaises(self.ns["_BrokerAuthenticationError"]): self.fetch()
                elif failure == "clear": self.bridge._clear_access_token()
                else:
                    self.auth["failure"] = True
                    with self.assertRaises(self.ns["_BrokerAuthenticationError"]): self.fetch()
                with self.bridge._reference_principal_scope(response) as principal: self.assertEqual(principal, "")
                self.assertFalse(self.bridge._reference_response_proofs)
        self.assertEqual(self.clears.call_count, 2)

    def test_evicted_and_copied_responses_hold_but_cross_thread_exact_response_works(self):
        first = self.fetch()
        for _ in range(17): self.fetch()
        self.assertLessEqual(len(self.bridge._reference_response_proofs), 16)
        for value in (first, deepcopy(self.fetch())):
            with self.bridge._reference_principal_scope(value) as principal: self.assertEqual(principal, "")
        async def run():
            response = await asyncio.to_thread(self.fetch)
            def inspect():
                with self.bridge._reference_principal_scope(response) as principal: return principal
            return await asyncio.to_thread(inspect)
        self.assertEqual(asyncio.run(run()), PRINCIPAL)

    def test_validated_my_box_projection_transfers_only_exact_current_proof(self):
        workspace = "mbx_" + "1"*32
        selection = dict(schema=my_box.SELECTION_SCHEMA, version=1, selection_source="only_my_box",
            scope=my_box.SCOPE, workspace_id=workspace, explicit_selection=True)
        task = "job-mybox-" + "1"*32
        raw_job = dict(schema=my_box.JOB_SCHEMA, version=1, scope=my_box.SCOPE, publish_to_reviews=False,
            generation_mode="only", resubmit_allowed=False, task_id=task, job_id=task, workspace_id=workspace,
            client_request_id="hmb-offline-1", status="completed", provider="volcengine_ark", model="fixture-model")
        self.handler = lambda label, path: deepcopy(raw_job)
        broker = my_box.MyBoxBroker(self.bridge)
        checked = broker.refresh(task, selection=selection, client_request_id="hmb-offline-1", timeout=1)
        self.assertEqual(set(checked), set(raw_job) | {"_http_status"})
        with self.bridge._reference_principal_scope(checked) as principal: self.assertEqual(principal, PRINCIPAL)
        with self.bridge._reference_principal_scope(deepcopy(checked)) as principal: self.assertEqual(principal, "")
        self.auth["current"] = "fixture-B"; self.bridge._load_access_token()
        with self.bridge._reference_principal_scope(checked) as principal: self.assertEqual(principal, "")


def native_suite():
    spec = importlib.util.spec_from_file_location("lease_my_box_native_fixture", Path(__file__).with_name("HMB_My_Box_Node_Regression.py"))
    fixture = importlib.util.module_from_spec(spec); sys.modules[spec.name] = fixture; spec.loader.exec_module(fixture)

    class NativeAuthContinuityTests(AuthContinuityTests):
        def setUp(self):
            super().setUp()
            opener = self.bridge._opener
            self.ns["_BrokerAuthenticationError"] = fixture.target._BrokerAuthenticationError
            for patcher in (mock.patch.object(fixture.target, "_broker_load_token", side_effect=self.ns["_broker_load_token"]),
                            mock.patch.object(fixture.target, "_broker_clear_token", self.clears)):
                patcher.start(); self.addCleanup(patcher.stop)
            self.bridge = fixture.target._HMBAIBrokerBridge(opener=opener, server_url=ORIGIN)
            self.bridge._open_create_request = opener.open
            self.calls.clear()
            self.assertTrue(self.bridge.account_snapshot(connect=False).connected)
            self.assertEqual(self.calls, [("GET", "/api/me")])

    class NativeLeaseTests(fixture.MyBoxNodeTests):
        def test_queue_hold_survives_cancel_native_delete_reopen_then_same_task_success(self):
            self.backend.status = "submitting"
            original_bridge = self.backend.bridge
            class JsonResponse(io.BytesIO):
                status = 200
                def __init__(self, url, data):
                    super().__init__(json.dumps(data).encode()); self.url = url
                def geturl(self): return self.url
            def open_request(request, timeout):
                path = request.full_url.removeprefix(self.backend.server_url)
                if path == "/api/v1/maintenance-intake/capabilities":
                    raise urllib.error.HTTPError(request.full_url, 404, "Synthetic legacy native admission", {}, io.BytesIO(b'{}'))
                if path == "/api/me":
                    return JsonResponse(request.full_url, {"id": 3, "display_name": "unrelated"})
                if "/media?download=1" in path:
                    return original_bridge.open(request, timeout)
                data = original_bridge._request_json(request.get_method(), path,
                    payload=json.loads(request.data) if request.data else None, timeout=timeout,
                    submission=path == "/api/v1/generate/video", idempotency_key=request.get_header("Idempotency-key", ""))
                return JsonResponse(request.full_url, data)
            loader = mock.patch.object(fixture.target, "_broker_load_token", return_value="NATIVE_OFFLINE_FIXTURE")
            loader.start(); self.addCleanup(loader.stop)
            bridge = fixture.target._HMBAIBrokerBridge(opener=SimpleNamespace(open=open_request), server_url=self.backend.server_url)
            bridge._open_create_request = open_request
            bridge.require_seedance_features = original_bridge.require_seedance_features
            bridge.require_seedance_draft_features = original_bridge.require_seedance_draft_features
            self.assertTrue(bridge.account_snapshot(connect=False).connected)
            self.backend.bridge = bridge
            self.node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
            self.node._broker_bridge_instance = bridge
            cloud, tos = mock.Mock(), mock.Mock()
            def prepared(params):
                self.node._temporary_video_uploads.append((cloud, Path("artifact_url_storage/native/reference.mov")))
                self.node._temporary_tos_video_uploads.append((tos, "fixture-bucket", "hmb-seedance-temp/native.mov"))
                return params
            self.node._prepare_video_references_for_run = prepared
            original_job = self.backend.job
            def queued_job(*args):
                return dict(original_job(*args), maintenance_queued=True, maintenance_state="waiting")
            self.backend.job = queued_job
            # The first poll can stop locally; it cannot consume pending input.
            self.node._sleep = mock.AsyncMock(side_effect=asyncio.CancelledError)
            with self.assertRaises(asyncio.CancelledError):
                self.run_node()
            cp = self.checkpoint(); identifier = cp["reference_lease_id"]
            self.assertTrue(leases.pending_metadata(identifier)["queue_held"])
            cloud.delete_file.assert_not_called(); tos.delete_object.assert_not_called()
            reopened = self.reopen()
            self.assertEqual(self.checkpoint(reopened)["reference_lease_id"], identifier)
            reopened._broker_bridge_instance = self.backend.bridge
            job = self.backend.jobs[cp["job_id"]]
            job.update(status="completed", download_url=self.backend.server_url + fixture.protocol.API + "/items/" + cp["job_id"] + "/media?download=1")
            job.pop("maintenance_queued"); job.pop("maintenance_state")
            self.run_node(reopened, refresh=True)
            self.assert_success(reopened)
            self.assertEqual(len(self.backend.created), 1)
            cloud.delete_file.assert_called_once(); tos.delete_object.assert_called_once(); tos.close.assert_called_once()
            self.run_node(reopened, refresh=True)
            cloud.delete_file.assert_called_once(); tos.delete_object.assert_called_once()

        def test_video_normalizer_and_account_cache_keep_only_verified_fields(self):
            task = fixture.target.HMBSeedanceGeneration._normalize_broker_task(dict(job_id="job-offline", status="pending",
                maintenance_queued=True, maintenance_state="dispatching", submission_outcome_unknown=False, token="never-project"), server_url=ORIGIN)
            self.assertTrue(task["maintenance_queued"]); self.assertEqual(task["maintenance_state"], "dispatching")
            self.node._set_broker_task_outputs(task, generation_id="job-offline", status="running")
            projection = self.node.parameter_output_values["provider_response"]
            self.assertTrue(projection["maintenance_queued"]); self.assertNotIn("token", projection)
            class JsonResponse(io.BytesIO):
                status = 200
                def geturl(self): return ORIGIN + "/api/me"
            opener = SimpleNamespace(open=mock.Mock(return_value=JsonResponse(json.dumps({
                "user": {"id": 3, "username": "fixture", "display_name": "different"}}).encode())))
            bridge = fixture.target._HMBAIBrokerBridge(opener=opener, server_url=ORIGIN)
            with mock.patch.object(fixture.target, "_broker_load_token", return_value="NATIVE_OFFLINE_FIXTURE"), \
                 mock.patch.object(fixture.target, "_broker_clear_token") as clear:
                self.assertTrue(bridge.account_snapshot(connect=False).connected)
                self.assertEqual(bridge._reference_account_fingerprint, PRINCIPAL)
                opener.open.side_effect = urllib.error.HTTPError(ORIGIN + "/api/me", 401, "offline", {}, io.BytesIO(b'{}'))
                self.assertFalse(bridge.account_snapshot(connect=False).connected)
                self.assertEqual(bridge._reference_account_fingerprint, "")
                clear.assert_called_once()

    suite = unittest.TestSuite(NativeLeaseTests(name) for name in NativeLeaseTests.__dict__ if name.startswith("test_"))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(NativeAuthContinuityTests))
    return suite


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LeaseTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(AuthContinuityTests))
    if "--pure" not in sys.argv:
        suite.addTests(native_suite())
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"status": "PASS" if result.wasSuccessful() else "FAIL", "tests": result.testsRun,
        "network_calls": 0, "paid_renders": 0, "synthetic_storage": True, "native_sdk": "--pure" not in sys.argv}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
