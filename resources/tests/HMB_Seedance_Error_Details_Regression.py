"""Diagnostic-only Broker failures: no network, rendering, or user workflow writes."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seedance_error_details", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


class FailHTTP:
    def __init__(self, status, payload):
        self.status, self.payload, self.calls = status, payload, []

    def open(self, request, timeout):
        self.calls.append((request.method, request.full_url))
        raise target.urllib.error.HTTPError(
            request.full_url, self.status, "synthetic", {},
            io.BytesIO(json.dumps(self.payload).encode()),
        )


class ErrorDetailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hmb-error-details-")
        self.addCleanup(self.temp.cleanup)
        patcher = mock.patch.object(target, "_seedance_recovery_journal_path",
                                    side_effect=lambda key: Path(self.temp.name) / (key + ".json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def task(self, **extra):
        return target.HMBSeedanceGeneration._normalize_broker_task({
            "job_id": "job-diag", "status": "failed", "provider_job_id": "", **extra,
        })

    def node(self, number=1):
        node = target.HMBSeedanceGeneration(name=f"Diagnostic Shot {number}")
        node._runtime_node_is_live = lambda **kwargs: True
        node._set_status_results = mock.Mock()
        node._force_save_generation_recovery_checkpoint = mock.AsyncMock(return_value=True)
        node.status_component = SimpleNamespace(clear_execution_status=mock.Mock())
        node._set_generation_recovery_checkpoint(
            stage="accepted", task_id=f"job-shot-{number}", task_identity="broker_task", status="running",
        )
        return node

    def test_plain_failure_retains_reason_without_changing_control(self):
        before = self.task()
        after = self.task(error="Selected model is not enabled for this account", request_id="req-001")
        self.assertEqual(before, {k: v for k, v in after.items() if k != "error_details"})
        self.assertIn("model is not enabled", after["error_details"])
        self.assertIn("req-001", after["error_details"])
        self.assertIn("model is not enabled", target.HMBSeedanceGeneration._broker_terminal_failure_message(after, "job-diag"))

    def test_nested_provider_error_keeps_code_message_parameter(self):
        task = self.task(error={"code": "InvalidParameter.Model", "message": "모델 권한 확인", "param": "model"})
        for value in ("InvalidParameter.Model", "모델 권한 확인", "param: model"):
            self.assertIn(value, task["error_details"])
        self.assertNotIn("error_code", task)  # Provider text cannot change Broker control codes.

    def test_validation_detail_preserves_field_not_input_or_context(self):
        task = self.task(detail=[{"loc": ["body", "resolution"], "msg": "Unsupported 1080p", "type": "value_error",
                                 "input": "private-input-canary", "ctx": {"secret": "private-context-canary"}}])
        self.assertIn("resolution", task["error_details"])
        self.assertIn("Unsupported 1080p", task["error_details"])
        self.assertNotIn("private-", task["error_details"])

    def test_nested_and_json_credentials_are_not_copied(self):
        payload = {"error": {"message": "Request rejected", "api_key": "key-canary", "headers": {"Authorization": "Bearer auth-canary"},
                             "detail": json.dumps({"message": "Bad parameter", "token": "json-token-canary", "input": "input-canary"})},
                   "token": "root-token-canary", "prompt": "prompt-canary"}
        detail = target._broker_error_details(payload)
        self.assertIn("Request rejected", detail)
        self.assertIn("Bad parameter", detail)
        self.assertNotIn("canary", detail)

    def test_free_text_credentials_media_and_signed_urls_are_redacted(self):
        raw = ('Model rejected; api_key="api-canary"; token=token-canary; password=\'password canary\'; '
               'secret_access_key=secret-canary; signature=sign-canary; Bearer bearer-canary; '
               'Basic YmFzaWMtY2FuYXJ5; https://user:pass@host.invalid/private-path?signature=url-canary#fragment; '
               'data:image/png;base64,bWVkaWEtY2FuYXJ5; ib_abcdefghijklmnopqrstuvwx')
        detail = target._broker_safe_error_text(raw)
        self.assertIn("Model rejected", detail)
        for value in ("api-canary", "token-canary", "password canary", "secret-canary", "sign-canary", "bearer-canary",
                      "YmFzaWMtY2FuYXJ5", "host.invalid", "private-path", "url-canary", "bWVkaWEtY2FuYXJ5", "abcdefghijklmnopqrstuvwx"):
            self.assertNotIn(value, detail)

    def test_http_errors_retain_reason_and_existing_acceptance_classification(self):
        for code in (400, 401, 403, 413, 429, 500, 502, 503, 504):
            with self.subTest(code=code):
                opener = FailHTTP(code, {"error": "Requested model cannot accept the parameter", "detail": "raw-auth-canary", "request_id": "req-002"})
                with mock.patch.object(target, "_broker_load_token", return_value="raw-auth-canary"), mock.patch.object(target, "_broker_clear_token") as clear:
                    bridge = target._HMBAIBrokerBridge(opener=opener)
                    with self.assertRaises(target._BrokerError) as caught:
                        bridge._request_json("POST", "/api/v1/generate/video", payload={}, timeout=1, submission=True)
                    self.assertEqual(clear.call_count, int(code == 401))
                self.assertIn("Requested model cannot accept", str(caught.exception))
                self.assertIn("req-002", str(caught.exception))
                self.assertNotIn("raw-auth-canary", str(caught.exception))
                self.assertEqual(caught.exception.submission_outcome_unknown, 500 <= code <= 599)
                self.assertEqual(len(opener.calls), 1)

    def test_terminal_error_body_in_502_refresh_is_diagnostic_not_resubmission(self):
        opener = FailHTTP(502, {"job_id": "job-diag", "status": "failed", "provider_job_id": "", "error": "Model access denied"})
        with mock.patch.object(target, "_broker_load_token", return_value="fake-token"):
            bridge = target._HMBAIBrokerBridge(opener=opener)
            raw = bridge.refresh_job("job-diag", timeout=1)
        task = target.HMBSeedanceGeneration._normalize_broker_task(raw)
        self.assertIn("Model access denied", task["error_details"])
        self.assertTrue(task["terminal"])
        self.assertEqual(len(opener.calls), 1)
        self.assertTrue(opener.calls[0][1].endswith("/job-diag/refresh"))

    def test_refresh_shots_save_diagnostics_without_crossing_tasks(self):
        async def check():
            snapshots = []
            for number in range(1, 6):
                node = self.node(number)
                bridge = SimpleNamespace(refresh_job=mock.Mock(return_value={"job_id": f"job-shot-{number}", "status": "failed",
                                             "error": f"Shot {number} parameter rejected", "provider_job_id": ""}),
                                         generate_seedance=mock.Mock(side_effect=AssertionError("No create allowed")))
                node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
                await node._refresh_async()
                detail = node.parameter_output_values["provider_response"]["error_details"]
                self.assertIn(f"Shot {number} parameter rejected", detail)
                self.assertIn(detail, node._set_status_results.call_args.kwargs["result_details"])
                self.assertEqual(node._generation_recovery_state()["task_id"], f"job-shot-{number}")
                self.assertFalse(node._generation_recovery_blocks_new_submission())
                bridge.generate_seedance.assert_not_called()
                snapshots.append((node, deepcopy(node.parameter_output_values["provider_response"])))
            for node, saved in snapshots:
                node._restore_generation_recovery_preview()
                self.assertEqual(node.parameter_output_values["provider_response"], saved)
        asyncio.run(check())

    def test_next_success_does_not_retain_prior_error(self):
        node = self.node()
        node._set_broker_task_outputs(self.task(error="old failure"), generation_id="job-diag", status="failed")
        node._set_broker_task_outputs({"id": "job-new", "status": "succeeded"}, generation_id="job-new", status="succeeded")
        self.assertNotIn("error_details", node.parameter_output_values["provider_response"])

    def test_malformed_oversized_and_html_http_bodies_are_bounded(self):
        for body in (b"<html>private-canary</html>", b"not-json-private-canary", b"x" * 70000):
            exc = target.urllib.error.HTTPError("https://broker.invalid", 502, "error", {}, io.BytesIO(body))
            message = target._HMBAIBrokerBridge._safe_http_error_message(exc)
            self.assertEqual(message, "FN AI Broker request failed with HTTP 502.")
        self.assertLessEqual(len(target._broker_error_details({"error": "x" * 65536})), 3020)
        self.assertNotIn("canary", target._broker_error_details({"error": "x" * 65536 + "canary"}))

    def test_details_cannot_change_ambiguous_task_authority(self):
        task = self.task(error="Safe to retry", error_code="submission_unknown", resubmit_allowed=False)
        self.assertEqual(task["status"], "submission_unknown")
        self.assertFalse(task["terminal"])
        self.assertIn("Safe to retry", target.HMBSeedanceGeneration._broker_unconfirmed_task_message(task, "job-diag"))

    def test_empty_or_successful_response_keeps_original_shape(self):
        task = target.HMBSeedanceGeneration._normalize_broker_task({"job_id": "job-ok", "status": "queued", "message": "normal queue"})
        self.assertNotIn("error_details", task)
        self.assertNotIn("error_details", self.task(error=None, detail={}, message=""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
