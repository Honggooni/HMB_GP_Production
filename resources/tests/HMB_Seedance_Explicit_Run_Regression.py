"""Offline: an explicit Run resolves an existing Broker submission before new work.

No provider requests, uploads, renders, workflow saves, or media deletion.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_explicit_run", ROOT / "HMBSeedanceGeneration.py")
assert spec and spec.loader
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
target._broker_transport.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0


class ExplicitRunSeedance(target.HMBSeedanceGeneration):
    @property
    def is_cancellation_requested(self):
        # The minimal CI host provides the Event; the installed SDK exposes
        # this property backed by that same Event.
        return self._cancellation_requested.is_set()


def make_node(shot=1):
    node = ExplicitRunSeedance(name=f"Explicit Run Shot {shot}")
    if hasattr(node, "_cancellation_requested"):
        node._cancellation_requested.clear()
    else:
        node.is_cancellation_requested = False
    # This test supplies manual text, with no registered upstream Agent node.
    node._manual_agent_prompt_source = lambda: None
    node._runtime_node_is_live = lambda **kw: not node._hmb_node_deleted
    node._submission_start_is_authorized = lambda **kw: not node.is_cancellation_requested and not node._hmb_node_deleted
    node._force_save_generation_recovery_checkpoint = mock.AsyncMock(return_value=True)
    node._clear_execution_status = mock.Mock()
    node._set_status_results = mock.Mock()
    node.status_component = SimpleNamespace(clear_execution_status=lambda **kw: None)
    node._output_file = SimpleNamespace(build_file=lambda: object(), _default_filename="output.mp4")
    node.origin = {"channel_uuid": str(uuid4()), "shot_uuid": str(uuid4()), "number": shot,
                   "name": f"Shot {shot}", "source_node_instance_id": str(uuid4())}
    node._capture_generated_video_origin = lambda: dict(node.origin)
    node._get_parameters = lambda: {
        "resume_generation_id": node.get_parameter_value("resume_generation_id") or "",
        "model_id": target.SEEDANCE_2_0_MODEL_ID, target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
        "output_format": "mp4", "return_last_frame": False,
        "generation_timeout_seconds": 30, "poll_interval_seconds": 1,
    }
    # Explicit-Run transport fixture has no retained graph. Keep the selected
    # project snapshot and production boundary comparisons explicit.
    selection = {"schema": target.PROJECT_SELECTION_SCHEMA,
                 "project": {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}}
    node._capture_imageasset_project_selection = lambda: copy.deepcopy(selection)
    node._resolve_exact_shot_generation_inputs = lambda params: {
        **params, **selection["project"],
        "_hmb_imageasset_project_selection": copy.deepcopy(selection)}
    node._validate_parameters = mock.Mock()
    node._preflight_output_destination = mock.Mock()
    node._prepare_video_references_for_run = lambda params: params
    node._build_broker_payload = lambda params: {"test_shot": shot}
    node._delete_temporary_video_uploads = mock.Mock()
    node._delete_temporary_tos_video_uploads = mock.Mock()
    node.previous_video = target.VideoUrlArtifact(value=f"C:/synthetic/shot-{shot}.mp4")
    node.parameter_output_values.update(video_url=node.previous_video, VIDEO_OUT=node.previous_video)
    bridge = SimpleNamespace(
        generate_seedance=mock.Mock(return_value={"job_id": f"new-shot-{shot}", "status": "failed", "error": "synthetic provider failure"}),
        refresh_job=mock.Mock(side_effect=AssertionError("Fresh Run queried historical task")),
    )
    node._ensure_broker_connected = mock.AsyncMock(return_value=bridge)
    node.bridge = bridge
    return node


def history(node, status, stage=None):
    node._set_generation_recovery_checkpoint(
        stage=stage or ("terminal" if status in target.TERMINAL_FAILURE_STATUSES else status),
        status=status, task_id=f"old-shot-{node.origin['number']}",
        task_identity="client_request" if status == "submission_unknown" else "broker_task",
        terminal=status in target.TERMINAL_FAILURE_STATUSES,
        params={"_hmb_generation_origin": dict(node.origin)},
    )


async def matrix():
    cases = (("submission_unknown", None), ("queued", "accepted"), ("running", "accepted"),
             ("timed_out", None), ("cancelled_locally", None), ("failed", None),
             ("cancelled", None), ("expired", None), ("succeeded", "remote_succeeded"))
    for shot in range(1, 6):
        for status, stage in cases:
            node = make_node(shot)
            history(node, status, stage)
            old_id = node._generation_recovery_state()["task_id"]
            node.bridge.refresh_job.side_effect = None
            node.bridge.refresh_job.return_value = {
                "job_id": old_id, "status": "failed", "error": "Fixture terminal failure"}
            node._prepare_managed_agent_shot = mock.AsyncMock()
            node._await_local_render_preflight = mock.AsyncMock()
            for _ in range(2):
                await node.aprocess()
                assert node._generation_recovery_state()["task_id"] == old_id
                assert "Fixture terminal failure" in node._set_status_results.call_args.kwargs["result_details"]
                assert not node._generation_run_active.is_set()
            assert [c.args[0] for c in node.bridge.refresh_job.call_args_list] == [old_id] * 2
            node.bridge.generate_seedance.assert_not_called()
            node._prepare_managed_agent_shot.assert_not_awaited()
            node._await_local_render_preflight.assert_not_awaited()
            assert node.parameter_output_values["VIDEO_OUT"] is node.previous_video


async def unknown_then_run():
    node = make_node()
    node.bridge.generate_seedance.side_effect = target._BrokerError(
        "Synthetic HTTP 502", status_code=502, submission_outcome_unknown=True)
    await node.aprocess()
    node.bridge.generate_seedance.assert_called_once()
    cp = node._generation_recovery_state()
    key = cp["task_id"]
    assert key.startswith("hmb-") and cp["status"] == "submission_unknown"
    initial_message = node._set_status_results.call_args.kwargs["result_details"]
    assert "Run checks this same request" in initial_message
    assert "separate render" not in initial_message and "duplicate charges" not in initial_message
    assert "기존 요청 ID" in target.GENERATION_PREVIEW_GUIDANCE["submission_unknown"]
    for status in (404, 502, 504):
        node.bridge.refresh_job.side_effect = target._BrokerError("lookup failed", status_code=status)
        await node.aprocess()
        assert node._generation_recovery_state()["task_id"] == key
        assert all(call.args[0] == key for call in node.bridge.refresh_job.call_args_list)
        message = node._set_status_results.call_args.kwargs["result_details"]
        assert key in message and "separate render" not in message and "duplicate charges" not in message
        node.bridge.generate_seedance.assert_called_once()
    node.bridge.refresh_job.side_effect = None
    node.bridge.refresh_job.return_value = {"job_id": "job-canonical", "status": "failed", "error": "fixture rejection"}
    await node.aprocess()
    assert node._generation_recovery_state()["task_id"] == "job-canonical"
    await node.aprocess()
    assert node.bridge.refresh_job.call_args.args[0] == "job-canonical"
    node.bridge.generate_seedance.assert_called_once()
    node.set_parameter_value("prompt", "Changed authored shot")
    node.bridge.generate_seedance.side_effect = None
    await node.aprocess()
    assert node.bridge.generate_seedance.call_count == 2
    assert node.bridge.generate_seedance.call_args.args[0]["client_request_id"] != key


async def reopened_legacy_receipts():
    for initial in ("submission_unknown", "failed"):
        saved = make_node()
        history(saved, initial)
        old_receipt = copy.deepcopy(saved._generation_recovery_state())
        old_receipt.pop("render_input_sha256", None)
        reopened = make_node()
        reopened.origin = dict(saved.origin)
        reopened.set_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER, old_receipt, emit_change=False)
        reopened.set_parameter_value("prompt", "Edited after loading the old workfile")
        reopened.parameter_output_values["generation_id"] = "stale-output-job"
        old_id = old_receipt["task_id"]
        reopened.bridge.refresh_job.side_effect = None
        reopened.bridge.refresh_job.return_value = {"job_id": old_id, "status": "failed"}
        await reopened.aprocess()
        reopened.bridge.generate_seedance.assert_not_called()
        assert [call.args[0] for call in reopened.bridge.refresh_job.call_args_list] == [old_id]
        verified = reopened._generation_recovery_state()
        assert verified["task_id"] == old_id and verified["terminal"]
        assert verified["render_input_sha256"] == reopened._render_authoring_digest()
        await reopened.aprocess()
        reopened.bridge.generate_seedance.assert_not_called()
        reopened.set_parameter_value("prompt", "An intentional edit after confirmed terminal status")
        await reopened.aprocess()
        reopened.bridge.generate_seedance.assert_called_once()


async def preparation_failures():
    for step in ("_validate_parameters", "_preflight_output_destination", "_ensure_broker_connected"):
        node = make_node()
        before = copy.deepcopy(node._generation_recovery_state())
        getattr(node, step).side_effect = ValueError("Synthetic preparation/authentication rejection")
        await node.aprocess()
        node.bridge.generate_seedance.assert_not_called()
        assert node._generation_recovery_state() == before
        assert node._set_status_results.call_args.kwargs["was_successful"] is False
        assert not node._generation_run_active.is_set()
        getattr(node, step).side_effect = None
        await node.aprocess()
        node.bridge.generate_seedance.assert_called_once()
    # Agent failure is not submitted as prompt text, even in fresh-Run mode.
    node = make_node()
    node.set_parameter_value("prompt", "[HMB EXECUTION FAILED] synthetic")
    await node.aprocess()
    node.bridge.generate_seedance.assert_not_called()
    # A required recovery write and native Stop/delete remain pre-POST gates.
    for gate in ("journal", "stop", "deleted"):
        node = make_node()
        if gate == "journal":
            node._force_save_generation_recovery_checkpoint.side_effect = OSError("synthetic write failure")
        elif gate == "stop":
            if hasattr(node, "_cancellation_requested"):
                node._cancellation_requested.set()
            else:
                node.is_cancellation_requested = True
        else:
            node._hmb_node_deleted = True
        try:
            await node.aprocess()
        except asyncio.CancelledError:
            assert gate == "stop"
        node.bridge.generate_seedance.assert_not_called()
        assert not node._generation_run_active.is_set()


async def active_lock_and_shots():
    nodes = [make_node(shot) for shot in range(1, 6)]
    started, release = threading.Event(), threading.Event()
    def slow_create(payload, **kw):
        started.set()
        assert release.wait(5), "Test release not signalled"
        return {"job_id": "new-shot-1", "status": "failed"}
    nodes[0].bridge.generate_seedance.side_effect = slow_create
    task = asyncio.create_task(nodes[0].aprocess())
    try:
        assert await asyncio.to_thread(started.wait, 5)
        await nodes[0].aprocess()  # Same-node second click cannot POST again.
        assert nodes[0].bridge.generate_seedance.call_count == 1
        untouched = copy.deepcopy(nodes[0]._generation_recovery_state())
        await asyncio.gather(*(node.aprocess() for node in nodes[1:]))
        assert nodes[0]._generation_recovery_state() == untouched
        assert all(node.bridge.generate_seedance.call_count == 1 for node in nodes)
    finally:
        release.set()
        await task
    nodes[0].bridge.generate_seedance.side_effect = None
    nodes[0].bridge.refresh_job.side_effect = None
    nodes[0].bridge.refresh_job.return_value = {"job_id": "new-shot-1", "status": "failed"}
    await nodes[0].aprocess()
    assert nodes[0].bridge.generate_seedance.call_count == 1
    assert nodes[0].bridge.refresh_job.call_args.args[0] == "new-shot-1"
    for node in nodes:
        assert node._generation_recovery_state()["generation_origin"] == node.origin
        assert node.parameter_output_values["VIDEO_OUT"] is node.previous_video
    refreshing = make_node()
    refreshing._generation_refresh_running = True
    await refreshing.aprocess()
    refreshing.bridge.generate_seedance.assert_not_called()


async def explicit_resume():
    node = make_node()
    history(node, "submission_unknown")
    old_id = node._generation_recovery_state()["task_id"]
    node.set_parameter_value("resume_generation_id", old_id)
    node.bridge.refresh_job.side_effect = None
    node.bridge.refresh_job.return_value = {"job_id": "canonical-existing", "status": "failed"}
    await node.aprocess()
    node.bridge.generate_seedance.assert_not_called()
    assert node.bridge.refresh_job.call_args.args[0] == old_id
    assert not node.get_parameter_value("resume_generation_id")
    await node.aprocess()
    assert node.bridge.refresh_job.call_args.args[0] == "canonical-existing"
    node.bridge.generate_seedance.assert_not_called()


async def main():
    with mock.patch.object(target, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fake", backend="offline")):
        await matrix()
        await unknown_then_run()
        await reopened_legacy_receipts()
        await preparation_failures()
        await active_lock_and_shots()
        await explicit_resume()


asyncio.run(main())
print("PASS: 45 recovery cases across 5 shots, repeated unknown and terminal retrievals without re-submission, changed inputs, locking and validation gates")
