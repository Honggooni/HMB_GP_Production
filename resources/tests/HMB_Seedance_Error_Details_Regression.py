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

    def test_nested_provider_error_keeps_code_parameter_without_raw_echo(self):
        task = self.task(error={"code": "InvalidParameter.Model", "message": "모델 권한 확인", "param": "model"})
        self.assertNotIn("모델 권한 확인", task["error_details"])
        for value in ("InvalidParameter.Model", "요청 파라미터 오류", "관련 필드: model"):
            self.assertIn(value, task["error_details"])
        self.assertNotIn("error_code", task)  # Provider text cannot change Broker control codes.

    def test_projected_create_and_poll_reasons_match(self):
        for code, label in (
            ("InputTextSensitiveContentDetected", "프롬프트"), ("InputImageSensitiveContentDetected", "입력 이미지"),
            ("InputVideoSensitiveContentDetected", "입력 영상"), ("OutputVideoSensitiveContentDetected", "생성 영상"),
            ("InputImageSensitiveContentDetected.PrivacyInformation", "실존 인물"),
            ("InvalidParameter.TaskTypeMismatch", "작업 유형 불일치"),
        ):
            with self.subTest(code=code):
                diagnostic = {"schema": "hmb-provider-failure-diagnostics-v1", "code": code, "http_status": 400,
                              "parameters": ["duration", "private-canary"], "message": "private-canary"}
                exc = target.urllib.error.HTTPError("https://broker.invalid", 502, "error", {}, None)
                create = target._HMBAIBrokerBridge._safe_http_error_message(exc, body=json.dumps(
                    {"provider_failure_diagnostics": diagnostic, "detail": "private-canary"}).encode())
                task = self.task(result={"provider_failure_diagnostics": diagnostic}, error="private-canary")
                for value in (create, task["error_details"]):
                    self.assertIn(code, value)
                    self.assertIn(label, value)
                    self.assertNotIn("private-canary", value)
                self.assertNotIn("error_code", task)

    def test_no_provider_code_does_not_invent_moderation(self):
        task = self.task(error="Volcengine create rejected the request (HTTP 400).")
        self.assertIn("상세 코드가 없어", task["error_details"])
        self.assertNotIn("심사 거절", task["error_details"])
        task = self.task(provider_failure_diagnostics={"schema": "hmb-provider-failure-diagnostics-v1",
                         "code": "", "http_status": 400, "hint": "provider_content_rejected"})
        self.assertIn("사유 미확인", task["error_details"])

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
                with mock.patch.object(target._broker_transport, "_broker_load_token", return_value="raw-auth-canary"), mock.patch.object(target._broker_transport, "_broker_clear_token") as clear:
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
        with mock.patch.object(target._broker_transport, "_broker_load_token", return_value="fake-token"):
            bridge = target._HMBAIBrokerBridge(opener=opener)
            raw = bridge.refresh_job("job-diag", timeout=1)
        task = target.HMBSeedanceGeneration._normalize_broker_task(raw)
        self.assertIn("Model access denied", task["error_details"])
        self.assertTrue(task["terminal"])
        self.assertEqual(len(opener.calls), 1)
        self.assertTrue(opener.calls[0][1].endswith("/job-diag/refresh"))

    def test_cloud_project_files_use_authored_slots_and_do_not_echo_server_values(self):
        private_url = "https://secret-user:secret-login@private.invalid/folder/두번째.mp4?sig=secret-sig#secret-fragment"
        node = self.node()
        sources = node._cloud_reference_display_sources({
            "first_frame": Path("secret-dir") / "front.png", "last_frame": "data:image/png;base64,c2VjcmV0",
            "reference_images": [r"C:\secret-dir\Titan.png", r"C:\secret-dir\Titan.png"],
            "video_reference_slots": [None, private_url], "video_references": ["secret-stale.mov"],
            "reference_audio": [{"name": "배경.wav", "url": "data:audio/wav;base64,YQ=="}],
        })
        self.assertEqual(sources, {("first_frame", 0): (1, "front.png"), ("last_frame", 0): (1, "파일명 미제공"),
            ("image_urls", 0): (1, "Titan.png"), ("image_urls", 1): (2, "Titan.png"),
            ("video_urls", 0): (2, "두번째.mp4"), ("audio_urls", 0): (1, "배경.wav")})
        first = {"number": 1, "bytes": 0, "total_ms": 123, "result": "cloud_timeout"}
        last = {"number": 2, "bytes": 12345, "headers_ms": 40, "first_byte_ms": 51, "total_ms": 350,
                "result": "cloud_sha256_mismatch", "detail": private_url, "sha256": "secret-sha"}
        rows = [{"field": "image_urls", "index": 0, "attempts": [{"result": "ok"}]},
                {"field": "image_urls", "index": 1, "file": "secret-filename.png", "attempts": [first, last]},
                {"field": "video_urls", "index": 0, "attempts": [first]},
                {"field": [], "index": 0, "attempts": [first]},
                {"field": "audio_urls", "index": True, "attempts": [first]}]
        opener = FailHTTP(422, {"error_code": "cloud_sha256_mismatch", "files": rows, "detail": private_url})
        with mock.patch.object(target._broker_transport, "_broker_load_token", return_value="secret-login"):
            with self.assertRaises(target._CloudReferenceCheckError) as caught:
                target._HMBAIBrokerBridge(opener=opener)._request_json(
                    "POST", "/api/v1/generate/video", payload={}, timeout=1, submission=True)
        caught.exception.with_sources(sources)
        message = node._safe_exception_message(caught.exception)
        for expected in ("image_urls[1] · 슬롯 2 · Titan.png", "video_urls[0] · 슬롯 2 · 두번째.mp4",
                         "응답 헤더 수신 전", "시도 1 · 수신 0 B · 소요 123 ms", "SHA-256 대조",
                         "시도 2 · 수신 12345 B · 소요 350 ms"):
            self.assertIn(expected, message)
        for excluded in ("image_urls[0]", "audio_urls", "secret", "private.invalid", "https://"):
            self.assertNotIn(excluded, message)
        self.assertFalse(caught.exception.submission_outcome_unknown)
        self.assertEqual(len(opener.calls), 1)

    def test_empty_widget_rows_keep_display_slot_numbers_without_changing_the_wire_order(self):
        node = self.node()
        slots = {"reference_images": [None, "Titan.png", "", "Titan.png"], "reference_audio": [None, "music.wav"]}
        with mock.patch.object(node, "get_parameter_value", side_effect=slots.get):
            sources = node._cloud_reference_display_sources({
                "reference_images": node._get_list_input("reference_images"),
                "reference_audio": node._get_list_input("reference_audio"),
            })
            self.assertEqual(sources["image_urls", 0], (2, "Titan.png"))
            self.assertEqual(sources["image_urls", 1], (4, "Titan.png"))
            self.assertEqual(sources["audio_urls", 0], (2, "music.wav"))
            shot = node._cloud_reference_display_sources({"reference_images": ["Somi.png"]})
            self.assertEqual(shot["image_urls", 0], (1, "Somi.png"))

    def test_cloud_code_only_private_and_empty_project_reports_explain_logs(self):
        for private, status, code in ((True, 422, "cloud_sha256_mismatch"),
                                      (False, 422, "upload_digest_required"), (False, 429, "cloud_preflight_busy")):
            with self.subTest(private=private, status=status):
                opener = FailHTTP(status, {"error_code": code, "error": "private-canary"})
                with mock.patch.object(target._broker_transport, "_broker_load_token", return_value="fake-token"):
                    with self.assertRaises(target._CloudReferenceCheckError) as caught:
                        target._HMBAIBrokerBridge(opener=opener)._request_json(
                            "POST", "/api/v1/generate/video", payload={"my_box_selection": {}} if private else {},
                            timeout=1, submission=True)
                self.assertEqual(caught.exception.status_code, status)
                self.assertIn(code, str(caught.exception))
                self.assertIn("브로커 로그", str(caught.exception))
                self.assertEqual("My Box" in str(caught.exception), private)
                self.assertNotIn("private-canary", str(caught.exception))
                self.assertNotIn("슬롯", str(caught.exception))
                self.assertEqual(len(opener.calls), 1)

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

    def test_only_matching_failed_resume_is_retired_and_history_is_preserved(self):
        for number in range(1, 6):
            for status in target.TERMINAL_FAILURE_STATUSES:
                node = self.node(number)
                job_id = f"job-shot-{number}"
                node.set_parameter_value("resume_generation_id", job_id)
                node.parameter_output_values["video_url"] = "previous-saved-video.mp4"
                task = target.HMBSeedanceGeneration._normalize_broker_task({
                    "job_id": job_id, "status": status, "error": "provider task ended with status failed",
                    "request_id": "10295ed1141229ddca80a262",
                })
                node._set_broker_task_outputs(task, generation_id=job_id, status=status)
                self.assertFalse(node.get_parameter_value("resume_generation_id"))
                self.assertEqual(node.parameter_output_values["generation_id"], job_id)
                self.assertEqual(node.parameter_output_values["video_url"], "previous-saved-video.mp4")
                self.assertIn("10295ed1141229ddca80a262", node.parameter_output_values["provider_response"]["error_details"])
                node.set_parameter_value("resume_generation_id", "job-other-shot")
                node._set_broker_task_outputs(task, generation_id=job_id, status=status)
                self.assertEqual(node.get_parameter_value("resume_generation_id"), "job-other-shot")

    def test_active_unknown_and_successful_resumes_are_not_retired(self):
        node = self.node()
        node.set_parameter_value("resume_generation_id", "job-diag")
        for status in ("running", "queued", "succeeded"):
            task = target.HMBSeedanceGeneration._normalize_broker_task({"job_id": "job-diag", "status": status})
            node._set_broker_task_outputs(task, generation_id="job-diag", status=task["status"])
            self.assertEqual(node.get_parameter_value("resume_generation_id"), "job-diag")
        for code in ("submission_unknown", "provider_overdue"):
            task = self.task(error_code=code, resubmit_allowed=False)
            node._set_broker_task_outputs(task, generation_id="job-diag", status=task["status"])
            self.assertEqual(node.get_parameter_value("resume_generation_id"), "job-diag")

    def test_saved_failed_resume_rechecks_same_task_on_every_run(self):
        async def check():
            node = self.node()
            node._clear_execution_status = mock.Mock()
            node._set_generation_recovery_checkpoint(
                stage="terminal", task_id="job-old", task_identity="broker_task", status="failed", terminal=True,
            )
            node.set_parameter_value("resume_generation_id", "job-old")
            bridge = SimpleNamespace(
                generate_seedance=mock.Mock(side_effect=AssertionError("Unexpected paid submission")),
                refresh_job=mock.Mock(return_value={"job_id": "job-old", "status": "failed",
                                      "error": "provider task ended with status failed"}),
            )
            node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
            for _ in range(2):
                await node._aprocess_impl()
                self.assertFalse(node.get_parameter_value("resume_generation_id"))
                self.assertEqual(node._generation_recovery_state()["task_id"], "job-old")
                self.assertIn("confirmed terminal", node._set_status_results.call_args.kwargs["result_details"])
            bridge.generate_seedance.assert_not_called()
            self.assertEqual([call.args[0] for call in bridge.refresh_job.call_args_list], ["job-old"] * 2)
        asyncio.run(check())

    def test_project_run_shows_original_name_after_cloud_staging(self):
        async def check():
            node = self.node()
            node._clear_execution_status = mock.Mock()
            node._clear_generation_recovery_checkpoint()
            node._submission_start_is_authorized = lambda **kwargs: True
            node._output_file = SimpleNamespace(build_file=lambda: object(), _default_filename="output.mp4")
            node._get_parameters = lambda: {
                "resume_generation_id": "", "model_id": target.SEEDANCE_2_0_MODEL_ID,
                target.TASK_PARAMETER: target.TASK_REFERENCE_TO_VIDEO, "output_format": "mp4", "return_last_frame": False,
                "generation_timeout_seconds": 600, "poll_interval_seconds": 5, "reference_images": ["Titan.png", "Titan.png"],
            }
            selection = {"schema": target.PROJECT_SELECTION_SCHEMA,
                         "project": {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}}
            node._capture_imageasset_project_selection = lambda: deepcopy(selection)
            node._manual_agent_prompt_source = lambda: None
            node._resolve_exact_shot_generation_inputs = lambda p: {
                **p, **selection["project"], "_hmb_imageasset_project_selection": deepcopy(selection)}
            node._validate_parameters = lambda p: None
            node._preflight_output_destination = lambda *args: None
            node._start_review_case = mock.Mock()
            staged = ["https://cloud.invalid/secret-blob?sig=secret-signature"] * 2
            node._prepare_video_references_for_run = lambda p: {**p, "reference_images": staged}
            node._build_broker_payload = lambda p: {"image_urls": p["reference_images"]}
            opener = FailHTTP(422, {"error_code": "cloud_length_mismatch", "provider_submitted": False, "files": [
                {"field": "image_urls", "index": 1, "attempts": [
                    {"number": 1, "bytes": 4, "total_ms": 15, "first_byte_ms": 2, "result": "cloud_length_mismatch"}]}]})
            bridge = target._HMBAIBrokerBridge(opener=opener)
            def submit(payload, *, timeout, **kwargs):
                self.assertEqual(payload["image_urls"], staged)
                return bridge._request_json("POST", "/api/v1/generate/video", payload=payload, timeout=timeout, submission=True)
            node._ensure_broker_connected = mock.AsyncMock(return_value=SimpleNamespace(generate_seedance=submit))
            with mock.patch.object(target._broker_transport, "_broker_load_token", return_value="secret-login"), \
                    mock.patch.object(target, "_negotiate_cloud_reference_proof", new_callable=mock.AsyncMock, return_value=True), \
                    mock.patch.object(target, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fake", backend="regression")):
                await node._aprocess_impl()
            details = node._set_status_results.call_args.kwargs["result_details"]
            self.assertIn("image_urls[1] · 슬롯 2 · Titan.png", details)
            self.assertIn("시도 1 · 수신 4 B · 소요 15 ms", details)
            self.assertNotIn("secret", details)
            self.assertNotIn("image_urls[0]", details)
            self.assertEqual(len(opener.calls), 1)
        asyncio.run(check())

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
