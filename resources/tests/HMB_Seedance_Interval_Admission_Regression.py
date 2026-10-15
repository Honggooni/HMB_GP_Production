"""Actual Bridge over local HTTP: jitter, safe cooldown and no duplicate create.

No production Broker, credential, provider, user graph or paid render is used.
"""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
import time
import unittest
from unittest import mock
import urllib.error

spec = importlib.util.spec_from_file_location("interval_admission_base", Path(__file__).with_name("HMB_Seedance_Draft_Regression.py"))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
t = base.t


class LocalBroker(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, status, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        barrier = self.server.capability_barrier
        if barrier is not None: barrier.wait(timeout=10)
        self.reply(200, base.capability())
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        with self.server.state_lock:
            self.server.requests.append((time.monotonic(), raw, self.headers.get("Idempotency-Key")))
            attempt = len(self.server.requests)
            mode = self.server.mode
        if mode in {"interval_once", "always_interval"} and (attempt == 1 or mode == "always_interval"):
            return self.reply(429, {"error": "다음 요청까지 0.0초 기다려야 합니다."})
        if mode == "typed_once" and attempt == 1:
            return self.reply(429, {"error_code": "submission_interval_limited", "retryable": True,
                                   "provider_create_sent": False, "retry_after_ms": 0, "request_id": "synthetic"})
        if mode == "quota": return self.reply(429, {"error": "이 사용자의 동시 실행 제한을 초과했습니다."})
        if mode == "lookalike": return self.reply(429, {"error": "다음 요청까지 0.0초 기다려야 합니다.", "error_code": "provider_throttled"})
        if mode == "gateway": return self.reply(503, {"error": "synthetic gateway failure"})
        if mode == "invalid_json": return self.reply(200, b"not-json")
        body = json.loads(raw)
        key = body["client_request_id"]
        with self.server.state_lock:
            self.server.accepted.setdefault(key, deepcopy(body))
        self.reply(202, {"job_id": "job-" + "c" * 32, "status": "pending"})


class IntervalAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalBroker)
        cls.server.state_lock = threading.Lock()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = "http://127.0.0.1:" + str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)
    def setUp(self):
        self.server.requests = []; self.server.accepted = {}; self.server.mode = "accept"
        self.server.capability_barrier = None
        t._BROKER_HTTP_SUBMISSION_STATES.clear()
        self.interval = mock.patch.object(t, "AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS", 0.0)
        self.interval.start()
        self.addCleanup(self.interval.stop)
        # The only HTTP exception stays origin-exact; this fixture substitutes
        # its own ephemeral loopback origin for the approved internal server.
        for name in ("AI_BROKER_SERVER_URL", "AI_BROKER_INTERNAL_ORIGIN"):
            patch = mock.patch.object(t, name, self.origin)
            patch.start(); self.addCleanup(patch.stop)
        self.bridge = t._HMBAIBrokerBridge(server_url=self.origin)
        self.bridge._load_access_token = lambda: "synthetic-account-only"
    def payload(self, *, final=False, index=1):
        value = {"provider": "volcengine_ark", "model": t.SEEDANCE_2_5_MODEL_ID,
                 "resolution": "1080p" if final else "480p", "output_format": "mov",
                 "client_request_id": "job-" + str(index) * 32}
        if final: value["draft_job_id"] = "job-" + "d" * 32
        else: value.update(draft=True, quality="480p", prompt="Exact {{prompt}}", input_mode="Text Only", duration_seconds=4)
        return value
    def submit(self, *, final=False): return self.bridge.generate_seedance(self.payload(final=final), timeout=5)

    def test_five_real_bridge_posts_remain_spaced_after_capability_jitter(self):
        self.server.capability_barrier = threading.Barrier(5)
        def send(index):
            bridge = t._HMBAIBrokerBridge(server_url=self.origin)
            bridge._load_access_token = lambda: "synthetic-account-only"
            # Ordinary MOV has one late refreshed capability GET. Hold all five
            # before release to reproduce the actual preflight bunching fault.
            payload = self.payload(index=index)
            payload.pop("draft"); payload["quality"] = payload["resolution"] = "720p"
            return bridge.generate_seedance(payload, timeout=10)
        with mock.patch.object(t, "AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS", 1.20):
            with ThreadPoolExecutor(max_workers=5) as pool: results = list(pool.map(send, range(1, 6)))
        self.assertEqual(len(results), 5); self.assertEqual(len(self.server.accepted), 5)
        times = sorted(row[0] for row in self.server.requests)
        self.assertTrue(all(later - earlier >= 1.0 for earlier, later in zip(times, times[1:])), times)

    def test_legacy_interval_preview_retries_same_exact_bytes_and_key(self):
        self.server.mode = "interval_once"
        self.submit()
        self.assertEqual(len(self.server.requests), 2)
        self.assertEqual(self.server.requests[0][1:], self.server.requests[1][1:])
        self.assertEqual(len(self.server.accepted), 1)

    def test_legacy_interval_final_retries_same_sparse_wire_and_key(self):
        self.server.mode = "interval_once"
        self.submit(final=True)
        self.assertEqual(len(self.server.requests), 2)
        self.assertEqual(self.server.requests[0][1:], self.server.requests[1][1:])
        self.assertNotIn("prompt", json.loads(self.server.requests[1][1]))
        self.assertEqual(len(self.server.accepted), 1)

    def test_typed_contract_requires_all_proof_fields(self):
        self.server.mode = "typed_once"; self.submit()
        self.assertEqual(len(self.server.requests), 2)
        good = {"error_code": "submission_interval_limited", "retryable": True,
                "provider_create_sent": False, "retry_after_ms": 50}
        self.assertEqual(t._broker_interval_rejection_delay(json.dumps(good).encode()), .05)
        for field, bad in (("retryable", False), ("provider_create_sent", True),
                           ("retry_after_ms", True), ("retry_after_ms", -1),
                           ("retry_after_ms", 5001), ("error_code", "other")):
            payload = {**good, field: bad}
            with self.subTest(field=field, bad=bad):
                self.assertIsNone(t._broker_interval_rejection_delay(json.dumps(payload).encode()))

    def test_interval_retry_exhaustion_is_finite_and_unaccepted(self):
        self.server.mode = "always_interval"
        with self.assertRaises(t._BrokerError) as raised: self.submit()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertFalse(raised.exception.submission_outcome_unknown)
        self.assertIn("retry limit", str(raised.exception))
        self.assertEqual(len(self.server.requests), t.AI_BROKER_INTERVAL_RETRY_MAX_ATTEMPTS)
        self.assertEqual(len(self.server.accepted), 0)

    def test_elapsed_retry_budget_retains_definitive_429(self):
        self.server.mode = "always_interval"
        with mock.patch.object(t, "AI_BROKER_INTERVAL_RETRY_MAX_SECONDS", 0):
            with self.assertRaises(t._BrokerError) as raised: self.submit()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertFalse(raised.exception.submission_outcome_unknown)
        self.assertEqual(len(self.server.requests), 1)

    def test_shared_queue_wait_respects_repeat_post_deadline(self):
        self.server.mode = "interval_once"
        original = t._broker_wait_for_http_submission
        def gate(request, origin, *, deadline=None):
            if deadline is not None:
                # Exercise the real gate with a held account lock until the
                # bounded retry deadline expires; never send a second POST.
                state = next(iter(t._BROKER_HTTP_SUBMISSION_STATES.values()))
                state["lock"].acquire()
                try: return original(request, origin, deadline=time.monotonic() + .03)
                finally: state["lock"].release()
            return original(request, origin)
        with mock.patch.object(t, "_broker_wait_for_http_submission", side_effect=gate):
            with self.assertRaises(t._BrokerError) as raised: self.submit()
        self.assertEqual(raised.exception.status_code, 429)
        self.assertFalse(raised.exception.submission_outcome_unknown)
        self.assertIn("retry limit", str(raised.exception))
        self.assertEqual(len(self.server.requests), 1)

    def test_quota_and_lookalike_429_are_not_retried(self):
        for mode in ("quota", "lookalike"):
            self.server.mode = mode; self.server.requests.clear()
            with self.subTest(mode=mode), self.assertRaises(t._BrokerError): self.submit()
            self.assertEqual(len(self.server.requests), 1)

    def test_preview_and_final_gateway_remain_unknown_without_retry(self):
        for final in (False, True):
            self.server.mode = "gateway"; self.server.requests.clear()
            with self.subTest(final=final), self.assertRaises(t._BrokerError) as raised: self.submit(final=final)
            self.assertTrue(raised.exception.submission_outcome_unknown)
            self.assertEqual(len(self.server.requests), 1)

    def test_malformed_accepted_response_is_unknown_without_retry(self):
        self.server.mode = "invalid_json"
        with self.assertRaises(t._BrokerProtocolError) as raised: self.submit()
        self.assertTrue(raised.exception.submission_outcome_unknown)
        self.assertEqual(len(self.server.requests), 1)

    def test_transport_uncertainty_is_never_automatically_retried(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.URLError("synthetic transport")
        self.bridge._opener = opener
        with self.assertRaises(t._BrokerUnavailableError) as raised:
            self.bridge._request_json("POST", "/api/v1/generate/video", payload=self.payload(),
                                      timeout=5, submission=True, idempotency_key="job-" + "1" * 32)
        self.assertTrue(raised.exception.submission_outcome_unknown)
        self.assertEqual(opener.open.call_count, 1)

    def test_cancellation_after_proven_rejection_prevents_second_post(self):
        self.server.mode = "interval_once"
        rejected = threading.Event()
        def check():
            if rejected.is_set(): raise t._SubmissionCancelledBeforeStart()
        t._BROKER_NATIVE_SUBMISSION_CONTEXT.callbacks = (check, rejected.set, check)
        try:
            with self.assertRaises(t._SubmissionCancelledBeforeStart): self.submit()
        finally: t._BROKER_NATIVE_SUBMISSION_CONTEXT.callbacks = None
        self.assertEqual(len(self.server.requests), 1)
        self.assertFalse(self.server.accepted)

    def test_web_command_one_attempt_guard_is_not_bypassed(self):
        from _hmb_web_rerender import CommandSubmissionOpener
        calls = []
        class WebOpener(CommandSubmissionOpener):
            def open(inner, request, *, timeout):
                if request.get_method() == "GET":
                    response = io.BytesIO(json.dumps(base.capability()).encode())
                    response.status = 200; response.geturl = lambda: request.full_url
                    return response
                calls.append(request.data)
                raise urllib.error.HTTPError(request.full_url, 429, "limited", {},
                    io.BytesIO(json.dumps({"error": "다음 요청까지 0.0초 기다려야 합니다."}).encode()))
        self.bridge._opener = object.__new__(WebOpener)
        with self.assertRaises(t._BrokerError): self.submit()
        self.assertEqual(len(calls), 1)

    def test_wrong_origin_interval_error_never_retries(self):
        self.bridge._opener = mock.Mock()
        self.bridge._opener.open.side_effect = urllib.error.HTTPError("https://other.invalid/create", 429, "limited", {},
            io.BytesIO(json.dumps({"error": "다음 요청까지 0.0초 기다려야 합니다."}).encode()))
        with self.assertRaises(t._BrokerProtocolError) as raised:
            self.bridge._request_json("POST", "/api/v1/generate/video", payload=self.payload(),
                                      timeout=5, submission=True, idempotency_key="job-" + "1" * 32)
        self.assertTrue(raised.exception.submission_outcome_unknown)
        self.assertEqual(self.bridge._opener.open.call_count, 1)


if __name__ == "__main__": unittest.main(verbosity=2)
