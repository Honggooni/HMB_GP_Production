"""No-network regression: exact-task terminal evidence and malformed create recovery."""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_identity_recovery", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0


def node():
    item = target.HMBSeedanceGeneration(name="Submission identity regression")
    item.is_cancellation_requested = False
    item._runtime_node_is_live = lambda **kwargs: True
    item._force_save_generation_recovery_checkpoint = mock.AsyncMock(return_value=True)
    item._set_status_results = mock.Mock()
    item.status_component = SimpleNamespace(clear_execution_status=lambda **kwargs: None)
    return item


identity_checks = 0
for index in range(1, 6):
    current_id = f"active-{index}"
    for stage, status in (("accepted", "running"), ("remote_succeeded", "succeeded"), ("timed_out", "timed_out")):
        for old_response in ({"id": f"previous-{index}", "terminal": True}, {"terminal": True}):
            item = node()
            item._set_generation_recovery_checkpoint(stage=stage, task_id=current_id, task_identity="broker_task", status=status)
            item.parameter_output_values["provider_response"] = old_response
            assert item._generation_recovery_blocks_new_submission(), (stage, old_response)
            item._restore_generation_recovery_preview()
            assert item._hmb_generation_preview_state["action"] == "refresh_existing"
            assert item.parameter_output_values["provider_response"].get("terminal") is not True
            assert item._generation_recovery_blocks_new_submission()
            identity_checks += 1
    # Exact terminal evidence still releases, as does a durable local success
    # before Griptape has hydrated any output artifact.
    for stage, status, terminal in (("accepted", "running", True), ("local_succeeded", "succeeded", False)):
        item = node()
        item._set_generation_recovery_checkpoint(stage=stage, task_id=current_id, task_identity="broker_task", status=status)
        item.parameter_output_values["provider_response"] = {"id": current_id, "terminal": terminal}
        assert not item._generation_recovery_blocks_new_submission()
        item._assert_new_submission_is_safe()
    # Output-only restoration must not migrate another task's terminal flag.
    item = node()
    item.parameter_output_values.update(generation_id=current_id, generation_status="running", provider_response={"id": "old", "terminal": True})
    assert item._generation_recovery_state()["terminal"] is False
    assert item._generation_recovery_blocks_new_submission()


class BodyOpener:
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        response = io.BytesIO(self.body)
        response.status = 200
        response.geturl = lambda: request.full_url
        return response


for body in (b"not-json", b"[]", b"null"):
    for submission in (False, True):
        opener = BodyOpener(body)
        with mock.patch.object(target, "_broker_load_token", return_value="synthetic"), mock.patch.object(target, "_broker_validated_server_url", return_value="https://broker.invalid"):
            bridge = target._HMBAIBrokerBridge(opener=opener)
            try:
                bridge._request_json("POST", "/api/v1/generate/video" if submission else "/api/v1/jobs/test/refresh", payload={}, timeout=1, submission=submission)
            except target._BrokerProtocolError as exc:
                assert exc.submission_outcome_unknown is submission
                assert not exc.definitive_submission_rejection
            else:
                raise AssertionError("Malformed HTTP response was accepted")
        assert opener.calls == 1


for status in (400, 401, 403, 429):
    # Explicit server rejections retain their existing semantics: they do not
    # become unknown submissions just because the error response is malformed.
    def reject(request, timeout):
        raise target.urllib.error.HTTPError(request.full_url, status, "rejected", {}, io.BytesIO(b"{}"))
    opener = SimpleNamespace(open=mock.Mock(side_effect=reject))
    with mock.patch.object(target, "_broker_load_token", return_value="synthetic"), mock.patch.object(target, "_broker_clear_token"), mock.patch.object(target, "_broker_validated_server_url", return_value="https://broker.invalid"):
        bridge = target._HMBAIBrokerBridge(opener=opener)
        try:
            bridge._request_json("POST", "/api/v1/generate/video", payload={}, timeout=1, submission=True)
        except target._BrokerError as exc:
            assert exc.status_code == status
            assert not exc.submission_outcome_unknown
        else:
            raise AssertionError("HTTP rejection unexpectedly succeeded")
    assert opener.open.call_count == 1

# A local preflight failure still occurs before any request/unknown marker.
with mock.patch.object(target, "_broker_load_token", return_value="synthetic"), mock.patch.object(target, "_broker_validated_server_url", return_value="https://broker.invalid"):
    opener = SimpleNamespace(open=mock.Mock(side_effect=AssertionError("Preflight reached POST")))
    bridge = target._HMBAIBrokerBridge(opener=opener)
    try:
        bridge._request_json("POST", "/api/v1/generate/video", payload={}, timeout=1, submission=True, idempotency_key="invalid id")
    except target._BrokerProtocolError as exc:
        assert not exc.submission_outcome_unknown
    else:
        raise AssertionError("Invalid local key unexpectedly succeeded")
    opener.open.assert_not_called()


async def verify_bad_create(response):
    item = node()
    item._submission_start_is_authorized = lambda **kwargs: True
    item._output_file = SimpleNamespace(build_file=lambda: object(), _default_filename="output.mp4")
    item._get_parameters = lambda: {"resume_generation_id": "", "model_id": target.SEEDANCE_2_0_MODEL_ID, target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
                                    "output_format": "mp4", "return_last_frame": False, "generation_timeout_seconds": 600, "poll_interval_seconds": 5}
    item._resolve_exact_shot_generation_inputs = lambda params: dict(params)
    item._validate_parameters = lambda params: None
    item._preflight_output_destination = lambda *args: None
    item._build_broker_payload = lambda params: {}
    def prepare(params):
        item._temporary_video_uploads = ["cloud-reference"]
        item._temporary_tos_video_uploads = ["tos-reference"]
        return params
    item._prepare_video_references_for_run = prepare
    item._delete_temporary_video_uploads = mock.Mock()
    item._delete_temporary_tos_video_uploads = mock.Mock()
    bridge = SimpleNamespace(generate_seedance=mock.Mock(return_value=response))
    item._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
    timers = []
    def timer(delay, callback, args):
        timer = SimpleNamespace(start=mock.Mock(), delay=delay, callback=callback, args=args)
        timers.append(timer)
        return timer
    with mock.patch.object(target, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fake", backend="regression")), mock.patch.object(target.threading, "Timer", side_effect=timer):
        try:
            await item._process_generation()
        except target._BrokerProtocolError as exc:
            assert exc.submission_outcome_unknown
            assert not exc.definitive_submission_rejection
        else:
            raise AssertionError("Malformed create unexpectedly succeeded")
    checkpoint = item._generation_recovery_state()
    assert checkpoint["stage"] == checkpoint["status"] == "submission_unknown"
    assert checkpoint["task_id"].startswith("hmb-") and checkpoint["task_identity"] == "client_request"
    assert item._generation_recovery_blocks_new_submission()
    assert item._hmb_generation_preview_state["action"] == "refresh_existing"
    assert bridge.generate_seedance.call_count == 1
    assert len(timers) == 2
    assert all(timer.delay == target.AMBIGUOUS_UPLOAD_CLEANUP_DELAY_SECONDS and timer.start.call_count == 1 for timer in timers)
    assert all(not call.args[0] for call in item._delete_temporary_video_uploads.call_args_list)
    assert all(not call.args[0] for call in item._delete_temporary_tos_video_uploads.call_args_list)
    assert {timer.args[0][0] for timer in timers} == {"cloud-reference", "tos-reference"}
    # Reopening retains the same client key. Refresh may promote this key to a
    # confirmed terminal Broker ID, never replay the create request.
    reopened = node()
    reopened.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER, json.loads(json.dumps(checkpoint)))
    reopened._restore_generation_recovery_preview()
    assert reopened._generation_recovery_blocks_new_submission()
    bridge.refresh_job = mock.Mock(return_value={"job_id": "canonical-resolved", "status": "failed"})
    reopened._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
    await reopened._refresh_async()
    bridge.refresh_job.assert_called_once_with(checkpoint["task_id"], timeout=60.0)
    assert reopened._generation_recovery_state()["task_id"] == "canonical-resolved"
    assert not reopened._generation_recovery_blocks_new_submission()
    assert bridge.generate_seedance.call_count == 1


for response in ({"status": "queued"}, {"job_id": "job-no-status"}, {"job_id": "bad id", "status": "running"}, {"job_id": "job-unknown", "status": "unexpected"}):
    asyncio.run(verify_bad_create(response))

print(f"PASS: {identity_checks} stale/missing identity cases; exact terminal and local success; malformed HTTP/create; both upload services retained; reopen/refresh without duplicate create")
