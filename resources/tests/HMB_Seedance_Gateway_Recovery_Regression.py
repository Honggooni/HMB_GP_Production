"""No-network regression for ambiguous create and same-request recovery."""
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
spec = importlib.util.spec_from_file_location("seedance_gateway_recovery", ROOT / "HMBSeedanceGeneration.py")
assert spec and spec.loader
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


class HTTPFailure:
    def __init__(self, code, payload):
        self.code, self.payload = code, payload

    def open(self, request, timeout):
        raise target.urllib.error.HTTPError(
            request.full_url, self.code, "synthetic error", {},
            io.BytesIO(json.dumps(self.payload).encode()),
        )


def request(code, payload, *, create=False):
    bridge = target._HMBAIBrokerBridge(opener=HTTPFailure(code, payload))
    with mock.patch.object(target, "_broker_load_token", return_value="test-token"), mock.patch.object(
        target, "_broker_validated_server_url", return_value="https://broker.invalid"
    ):
        return bridge._request_json(
            "POST", "/api/v1/generate/video" if create else "/api/v1/jobs/hmb-client-key/refresh",
            payload={} if create else None, timeout=1, submission=create,
        )


# A 502 create remains uncertain even if its error body mentions a failed job.
for body in ({}, {"status": "failed", "job_id": "job-canonical"}):
    try:
        request(502, body, create=True)
    except target._BrokerError as exc:
        assert exc.submission_outcome_unknown is True
        assert exc.definitive_submission_rejection is False
    else:
        raise AssertionError("An HTTP 502 create was treated as accepted/rejected")

# Only a same-task lookup may consume an explicit terminal record in 5xx/410.
for code, status in ((502, "failed"), (503, "cancelled"), (410, "expired")):
    result = request(code, {"status": status, "job_id": "job-canonical"})
    assert result["status"] == status and result["_http_status"] == code
for body in ({}, {"error": "gateway"}, {"status": "failed"}, {"status": "running", "job_id": "job-canonical"}):
    try:
        request(502, body)
    except target._BrokerError:
        pass
    else:
        raise AssertionError("An unproven gateway response became a terminal task")


def node_with_checkpoint(task_id="hmb-client-key", identity="client_request"):
    node = target.HMBSeedanceGeneration(name="Gateway Recovery")
    node.is_cancellation_requested = False
    node._runtime_node_is_live = lambda **_kwargs: True
    node._force_save_generation_recovery_checkpoint = mock.AsyncMock(return_value=True)
    node._set_status_results = mock.Mock()
    node.status_component = SimpleNamespace(clear_execution_status=lambda **_kwargs: None)
    if task_id:
        node._set_generation_recovery_checkpoint(
            stage="submission_unknown" if identity == "client_request" else "accepted",
            task_id=task_id, task_identity=identity,
            status="submission_unknown" if identity == "client_request" else "running",
        )
        node._restore_generation_recovery_preview()
    return node


class ResponseBridge:
    def __init__(self, response):
        self.response = response
        self.lookups = []
        self.create_count = 0

    def refresh_job(self, job_id, **_kwargs):
        self.lookups.append(job_id)
        return self.response

    def generate_seedance(self, *_args, **_kwargs):
        self.create_count += 1
        raise AssertionError("Recovery must not submit a render")


async def verify_recovery():
    # The canonical failed job recovered after an unknown POST unlocks Run,
    # while keeping the ID as terminal history. Refresh never creates a job.
    node = node_with_checkpoint()
    node.set_parameter_value("resume_generation_id", "hmb-client-key")
    bridge = ResponseBridge(request(502, {"status": "failed", "job_id": "job-canonical"}))
    node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
    await node._refresh_async()
    checkpoint = node._generation_recovery_state()
    assert checkpoint["task_id"] == "job-canonical"
    assert checkpoint["task_identity"] == "broker_task"
    assert checkpoint["terminal"] is True
    assert node._generation_recovery_blocks_new_submission() is False
    assert not node.get_parameter_value("resume_generation_id")
    node._assert_new_submission_is_safe()
    assert bridge.lookups == ["hmb-client-key"] and bridge.create_count == 0

    # The server giving up confirmation is not a confirmed failed provider job.
    for code in ("submission_unknown", "provider_overdue"):
        node = node_with_checkpoint()
        bridge = ResponseBridge({"status": "failed", "job_id": "job-unresolved", "terminal": True,
                                 "error_code": code, "resubmit_allowed": False, "recovery_action": "contact_admin"})
        node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
        await node._refresh_async()
        checkpoint = node._generation_recovery_state()
        assert checkpoint["status"] == "submission_unknown" and checkpoint["terminal"] is False
        assert checkpoint["task_id"] == "job-unresolved"
        assert node._generation_recovery_blocks_new_submission() is True
        assert node._hmb_generation_preview_state["action"] == "refresh_existing"
        reopened = node_with_checkpoint(task_id="")
        reopened.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER, json.loads(json.dumps(checkpoint)))
        reopened._restore_generation_recovery_preview()
        assert reopened._generation_recovery_blocks_new_submission() is True
        assert reopened._hmb_generation_preview_state["job_id"] == "job-unresolved"
        assert bridge.create_count == 0

    # A different explicit Resume must not discard an unresolved paid task.
    guarded = node_with_checkpoint()
    guarded.set_parameter_value("resume_generation_id", "job-unrelated")
    with mock.patch.object(guarded, "_ensure_broker_connected", side_effect=AssertionError("wrong Resume reached Broker")):
        try:
            await guarded._process_generation_impl()
        except RuntimeError as exc:
            assert "still requires confirmation" in str(exc)
        else:
            raise AssertionError("Resume replaced an unresolved ID")
    assert guarded._generation_recovery_state()["task_id"] == "hmb-client-key"

    # Explicit same-key Resume promotes to canonical ID; a normal independent
    # manual Resume remains available when no unresolved checkpoint exists.
    for existing, resume, response_id in (("hmb-client-key", "hmb-client-key", "job-canonical"), ("", "job-manual", "job-manual")):
        node = node_with_checkpoint(existing)
        node.set_parameter_value("resume_generation_id", resume)
        node.set_parameter_value("prompt", "test resume")
        node.set_parameter_value("poll_interval_seconds", 1)
        node.set_parameter_value("generation_timeout_seconds", 30)
        bridge = ResponseBridge({"status": "failed", "job_id": response_id})
        node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
        node._preflight_output_destination = mock.Mock()
        node._output_file = SimpleNamespace(build_file=lambda: object(), _default_filename="output.mp4")
        try:
            await node._process_generation_impl()
        except RuntimeError as exc:
            assert "ended with status failed" in str(exc), str(exc)
        else:
            raise AssertionError("Synthetic failed Resume should report failure")
        assert bridge.lookups == [resume] and bridge.create_count == 0
        assert node._generation_recovery_state()["task_id"] == response_id
        assert node._generation_recovery_blocks_new_submission() is False
        assert not node.get_parameter_value("resume_generation_id")


asyncio.run(verify_recovery())
print("HMB Seedance gateway recovery: PASS (unknown create, exact terminal lookup, missing-ID safety, canonical Resume, unresolved-provider retention, no create replay)")
