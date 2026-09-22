"""Offline: an explicit fresh Run supersedes history, never an active invocation.

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
target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0


def make_node(shot=1):
    node = target.HMBSeedanceGeneration(name=f"Explicit Run Shot {shot}")
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
    node._resolve_exact_shot_generation_inputs = lambda params: dict(params)
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
             ("cancelled", None), ("expired", None), ("succeeded", "remote_succeeded"),
             ("succeeded", "local_succeeded"))
    keys = []
    for shot in range(1, 6):
        for status, stage in cases:
            node = make_node(shot)
            history(node, status, stage)
            before = copy.deepcopy(node._generation_recovery_state())
            # The previous ID remains recoverable until the new request is ready.
            def check_history(*args):
                assert node._generation_recovery_state() == before, "history cleared early"
            node._preflight_output_destination.side_effect = check_history
            await node.aprocess()
            node.bridge.generate_seedance.assert_called_once()
            node.bridge.refresh_job.assert_not_called()
            key = node.bridge.generate_seedance.call_args.args[0]["client_request_id"]
            assert key != before["task_id"] and key.startswith("hmb-")
            keys.append(key)
            checkpoint = node._generation_recovery_state()
            assert checkpoint["task_id"] == f"new-shot-{shot}"
            assert checkpoint["generation_origin"] == node.origin
            assert node.parameter_output_values["VIDEO_OUT"] is node.previous_video
            assert node._set_status_results.call_args.kwargs["was_successful"] is False
            assert "synthetic provider failure" in node._set_status_results.call_args.kwargs["result_details"]
            assert not node._generation_run_active.is_set()
    assert len(set(keys)) == len(keys) == 50


async def unknown_then_run():
    node = make_node()
    history(node, "submission_unknown")
    node.bridge.generate_seedance.side_effect = target._BrokerError(
        "Synthetic HTTP 502", status_code=502, submission_outcome_unknown=True,
    )
    keys = []
    for count in range(1, 4):
        await node.aprocess()
        assert node.bridge.generate_seedance.call_count == count
        checkpoint = node._generation_recovery_state()
        keys.append(checkpoint["task_id"])
        assert checkpoint["status"] == "submission_unknown" and not checkpoint["terminal"]
        assert node._set_status_results.call_args.kwargs["was_successful"] is False
        assert "duplicate charges" in node._set_status_results.call_args.kwargs["result_details"]
    assert len(set(keys)) == 3
    # Refresh inspects the newest ID once without generating a fourth render.
    node.bridge.refresh_job.side_effect = None
    node.bridge.refresh_job.return_value = {"job_id": "resolved-newest", "status": "failed"}
    await node._refresh_async()
    assert node.bridge.refresh_job.call_args.args[0] == keys[-1]
    assert node.bridge.generate_seedance.call_count == 3


async def preparation_failures():
    for step in ("_validate_parameters", "_preflight_output_destination", "_ensure_broker_connected"):
        node = make_node()
        history(node, "submission_unknown")
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
    history(node, "submission_unknown")
    node.set_parameter_value("prompt", "[HMB EXECUTION FAILED] synthetic")
    await node.aprocess()
    node.bridge.generate_seedance.assert_not_called()
    # A required recovery write and native Stop/delete remain pre-POST gates.
    for gate in ("journal", "stop", "deleted"):
        node = make_node()
        history(node, "submission_unknown")
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
    for node in nodes:
        history(node, "submission_unknown")
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
    await nodes[0].aprocess()  # After completion a deliberate Run starts anew.
    assert nodes[0].bridge.generate_seedance.call_count == 2
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
    node.bridge.generate_seedance.assert_called_once()


async def main():
    with mock.patch.object(target, "_resolve_mp4_decode_verifier", return_value=SimpleNamespace(executable="fake", backend="offline")):
        await matrix()
        await unknown_then_run()
        await preparation_failures()
        await active_lock_and_shots()
        await explicit_resume()


asyncio.run(main())
print("PASS: 50 history/shot combinations; repeated 502 -> explicit fresh Run; exact-ID Refresh/Resume; no automatic replay; live locks; preparation/Agent/journal/Stop gates; five-shot isolation; previous media preserved")
