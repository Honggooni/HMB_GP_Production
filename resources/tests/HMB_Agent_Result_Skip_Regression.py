"""Offline Agent failure/result gating through real async execution boundaries.

The native model, Broker, host publications and filesystem boundaries are local
fixtures. Agent.aprocess, Seedance.aprocess/_aprocess_impl, generation orchestration,
result validation, task output publication and unsent-checkpoint discard are real.
No workflow, policy DAT, application configuration or network is accessed.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import importlib.util
import io
import logging
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent_module = load_module("hmb_agent_result_skip_agent", "HMBAgentLibrary.py")
seedance_module = load_module("hmb_agent_result_skip_seedance", "HMBSeedanceGeneration.py")
Agent = agent_module.HMBAgentLibrary
Seedance = seedance_module.HMBSeedanceGeneration
RESULT = agent_module._AGENT_EXECUTION_RESULT_PARAMETER


def no_network(*_args, **_kwargs):
    raise AssertionError("Offline regression attempted a network operation")


def unavailable_connection_or_result(*_args, **_kwargs):
    raise RuntimeError("PRIVATE_CONNECTION_OR_RESULT_ERROR")


def make_agent(number: int = 1):
    node = object.__new__(Agent)
    node.name = f"Offline Agent {number}"
    node.number = number
    node.parameter_values = {"output": "old text"}
    node.parameter_output_values = {"output": "old text", "agent": {"old": True}}
    node._hmb_node_deleted = False
    node._hmb_execution_result = {}
    node._hmb_native_failure_code = ""
    node._last_raw_output = "old text"
    node._set_agent_execution_phase = mock.Mock()
    node._clear_execution_shot_binding = mock.Mock()
    node._refresh_agent_shot_route = mock.Mock()
    node.show_message_by_name = mock.Mock()
    node.hide_message_by_name = mock.Mock()
    node.set_parameter_value = lambda key, value, **_kwargs: node.parameter_values.__setitem__(key, value)
    return node


class FakeBroker:
    def __init__(self, number: int):
        self.number = number
        self.creates: list[dict] = []
        self.refreshes: list[str] = []
        self.failure: BaseException | None = None

    def generate_seedance(self, payload, **_kwargs):
        self.creates.append(copy.deepcopy(payload))
        if self.failure:
            raise self.failure
        return {"id": f"offline-job-{self.number}", "status": "succeeded"}

    def refresh_job(self, task_id, **_kwargs):
        self.refreshes.append(task_id)
        return {"id": task_id, "status": "succeeded"}


class OfflineSeedance(Seedance):
    @property
    def is_cancellation_requested(self):
        return False


def make_generator(source, number: int = 1):
    """Construct without host registration, policy/session setup or journal IO."""
    node = object.__new__(OfflineSeedance)
    node.name = f"Offline Generator {number}"
    node.parameter_values = {"prompt": "old text", "resume_generation_id": ""}
    node.parameter_output_values = {}
    node._hmb_node_deleted = False
    node._generation_refresh_lock = threading.Lock()
    node._generation_refresh_running = False
    node._generation_run_active = threading.Event()
    node._detached_submission_tasks = set()
    node._hmb_expected_agent_result = None
    node.source = source
    node.checkpoint = {}
    node.saved_checkpoints = []
    node.previews = []
    node.completed = []
    node.result = None
    node.broker = FakeBroker(number)
    node._runtime_node_is_live = lambda **_kwargs: True
    node.get_parameter_value = lambda key: node.parameter_values.get(key)
    node._manual_agent_prompt_source = lambda: node.source
    node._clear_execution_status = lambda: setattr(node, "result", None)
    node._set_status_results = lambda **value: setattr(node, "result", value)
    node._publish_generation_preview = lambda phase, **value: node.previews.append({"phase": phase, **value})
    node._begin_generation_preview = lambda: None
    node._generation_recovery_state = lambda: copy.deepcopy(node.checkpoint)
    node._generation_recovery_blocks_new_submission = lambda: bool(node.checkpoint.get("task_id"))

    def assert_new_submission_safe(*, explicit_run: bool = False):
        assert type(explicit_run) is bool
        assert not node.checkpoint.get("task_id"), "Existing task must be explicitly resumed"

    def checkpoint(**value):
        node.checkpoint = {key: item for key, item in value.items() if key != "params"}

    async def save_checkpoint(**value):
        node.saved_checkpoints.append((value["reason"], copy.deepcopy(node.checkpoint)))
        return True

    async def submit(operation, *args, **kwargs):
        await asyncio.sleep(0)
        return operation(*args, **kwargs), False

    async def save_completed(task, generation_id, *_args, **_kwargs):
        node.completed.append(generation_id)
        node._set_broker_task_outputs(task, generation_id=generation_id, status="succeeded")
        node._set_status_results(was_successful=True, result_details="Offline completed result")

    node._assert_new_submission_is_safe = assert_new_submission_safe
    node._set_generation_recovery_checkpoint = checkpoint
    node._clear_generation_recovery_checkpoint = lambda: setattr(node, "checkpoint", {})
    node._force_save_generation_recovery_checkpoint = save_checkpoint
    node._set_safe_defaults = lambda: None
    node._cleanup_temporary_video_uploads = lambda: None
    node._defer_temporary_video_upload_cleanup = mock.Mock()
    node._output_file = SimpleNamespace(build_file=lambda: object())
    node._preflight_output_destination = lambda *_args: None
    node._get_parameters = lambda: {
        "prompt": node.parameter_values["prompt"],
        "resume_generation_id": node.parameter_values["resume_generation_id"],
        "model_id": seedance_module.SEEDANCE_2_0_MODEL_ID,
        seedance_module.TASK_PARAMETER: seedance_module.TASK_TEXT_ONLY,
        "output_format": "mp4", "return_last_frame": False,
        "generation_timeout_seconds": 60, "poll_interval_seconds": 1,
    }
    node._resolve_exact_shot_generation_inputs = lambda params: dict(params)
    node._validate_parameters = lambda _params: None
    node._prepare_video_references_for_run = lambda params: dict(params)
    node._build_broker_payload = lambda params: {"prompt": params["prompt"]}
    node._ensure_broker_connected = mock.AsyncMock(return_value=node.broker)
    node._await_submission_result = submit
    node._save_completed_task = save_completed
    node._monotonic = time.monotonic
    return node


async def native_success(node):
    assert node.parameter_output_values["output"] == "", "Old Agent text reached a new native run"
    assert node.parameter_output_values["agent"] == {}
    assert node._last_raw_output is None
    assert node._hmb_execution_result_snapshot()["status"] == "running"
    await asyncio.sleep(0)
    node._set_visible_output(f"Fresh resolved instruction for shot {node.number}.")


async def succeed(node):
    with mock.patch.object(agent_module._BaseAgent, "aprocess", native_success, create=True):
        await node.aprocess()
    result = node._hmb_execution_result_snapshot()
    assert result["status"] == "succeeded" and result["code"] == ""
    text = node.parameter_output_values["output"]
    assert result["output_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result == node.parameter_values[RESULT] == node.parameter_output_values[RESULT]
    return text


async def five_branches(failed_number: int, *, generation_failure: bool = False):
    agents = [make_agent(n) for n in range(1, 6)]
    generators = [make_generator(agent, agent.number) for agent in agents]
    all_started = asyncio.Event()
    started = set()

    async def native(node):
        started.add(node.number)
        if len(started) == 5:
            all_started.set()
        await all_started.wait()
        if node.number == failed_number and not generation_failure:
            raise TimeoutError("Read timed out: PRIVATE_PROVIDER_PAYLOAD")
        await native_success(node)

    async def branch(agent, generator):
        await agent.aprocess()
        generator.parameter_values["prompt"] = agent.parameter_output_values["output"]
        if generation_failure and agent.number == failed_number:
            generator.broker.failure = RuntimeError("offline rendering failure")
        await generator.aprocess()

    with mock.patch.object(agent_module._BaseAgent, "aprocess", native, create=True):
        await asyncio.gather(*(branch(agent, generator) for agent, generator in zip(agents, generators)))
    assert started == set(range(1, 6))
    for agent, generator in zip(agents, generators):
        assert not generator._generation_run_active.is_set()
        if agent.number == failed_number:
            assert generator.result["was_successful"] is False
            assert not generator.completed
            if generation_failure:
                assert generator.result["result_details"].startswith("FAILURE:")
                assert len(generator.broker.creates) == 1
            else:
                assert agent._hmb_execution_result_snapshot()["status"] == "failed"
                assert "PRIVATE_PROVIDER_PAYLOAD" not in agent.parameter_output_values["output"]
                assert generator.result["result_details"].startswith("SKIPPED:")
                assert generator.broker.creates == []
                generator._ensure_broker_connected.assert_not_awaited()
        else:
            assert generator.result["was_successful"] is True
            assert generator.completed == [f"offline-job-{agent.number}"]
            assert len(generator.broker.creates) == 1
            assert generator.broker.creates[0]["prompt"] == agent.parameter_output_values["output"]


async def cadence_change(mutation: str):
    """Mutate authority while the real submission worker waits for cadence."""
    source = make_agent()
    text = await succeed(source)
    generator = make_generator(source)
    generator.parameter_values["prompt"] = text
    # Remove only the fixture override: invoke the production thread, shield,
    # cadence reservation, final result guard and create-call boundary.
    del generator._await_submission_result
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def wait_for_cadence():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5), "Offline cadence test did not release its worker"

    with mock.patch.object(seedance_module, "_broker_wait_for_submission_slot", wait_for_cadence):
        task = asyncio.create_task(generator.aprocess())
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            provisional_id = generator.checkpoint["task_id"]
            assert provisional_id.startswith("hmb-")
            assert generator.checkpoint["stage"] == "pre_submit"
            assert generator.parameter_output_values["generation_id"] == provisional_id
            assert generator.broker.creates == []
            if mutation == "failed":
                source._set_hmb_execution_result("failed", code="MODEL_TIMEOUT")
            elif mutation == "rerun":
                previous_run = source._hmb_execution_result_snapshot()["run_id"]
                assert await succeed(source) == text
                assert source._hmb_execution_result_snapshot()["run_id"] != previous_run
            elif mutation == "rebind":
                replacement = make_agent()
                assert await succeed(replacement) == text
                generator.source = replacement
            elif mutation == "resume_failed":
                generator.parameter_values["resume_generation_id"] = "unrelated-late-resume"
                source._set_hmb_execution_result("failed", code="MODEL_TIMEOUT")
            elif mutation == "connection_error":
                generator._manual_agent_prompt_source = unavailable_connection_or_result
            elif mutation == "getter_error":
                source._hmb_execution_result_snapshot = unavailable_connection_or_result
            elif mutation == "live_newer_prompt":
                new_text = "Newer successful Agent text that is absent from the frozen payload."
                source._set_visible_output(new_text)
                source._set_hmb_execution_result("running")
                source._set_hmb_execution_result("succeeded")
                generator.parameter_values["prompt"] = new_text
                # Another callback can update the node field after this worker
                # captured it. It must still validate the actual queued bytes.
                generator._hmb_agent_submission_prompt = new_text
                assert source._hmb_execution_result_snapshot()["output_sha256"] == hashlib.sha256(new_text.encode()).hexdigest()
            else:
                assert mutation == "unchanged"
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=5)

    assert not generator._generation_run_active.is_set()
    assert generator._detached_submission_tasks == set()
    if mutation == "unchanged":
        assert generator.result["was_successful"] is True, generator.result
        assert generator.completed == ["offline-job-1"]
        assert len(generator.broker.creates) == 1
        assert generator.broker.creates[0]["client_request_id"] == provisional_id
        assert generator.broker.creates[0]["prompt"] == text
    else:
        assert generator.result["result_details"].startswith("SKIPPED:"), generator.result
        assert generator.result["was_successful"] is False
        assert generator.broker.creates == []
        assert generator.completed == []
        assert generator.parameter_output_values["generation_id"] == ""
        assert generator.parameter_output_values["generation_status"] == "skipped"
        assert generator.parameter_output_values["provider_response"] is None
        assert generator.checkpoint == {}
        assert generator.saved_checkpoints[-1] == ("agent_result_changed_at_submission_gate", {})
        assert "PRIVATE_CONNECTION_OR_RESULT_ERROR" not in generator.result["result_details"]
        assert generator.broker.refreshes == []
        if mutation == "live_newer_prompt":
            assert "No stale prompt was submitted" in generator.result["result_details"]


async def run():
    for failed_number in range(1, 6):
        await five_branches(failed_number)
        await five_branches(failed_number, generation_failure=True)
    for mutation in (
        "failed", "rerun", "rebind", "unchanged", "resume_failed",
        "connection_error", "getter_error", "live_newer_prompt",
    ):
        await cadence_change(mutation)

    # Exact Agent identity distinguishes a reopened empty output from a manual
    # media-only input. Legacy Agents with a valid saved text remain usable.
    empty_agent = make_agent()
    empty_agent.parameter_values["output"] = ""
    empty_agent.parameter_output_values["output"] = ""
    assert empty_agent._hmb_execution_result_snapshot() == {}
    blank_agent_input = make_generator(empty_agent)
    blank_agent_input.parameter_values["prompt"] = "   "
    await blank_agent_input.aprocess()
    assert blank_agent_input.result["result_details"].startswith("SKIPPED:")
    assert blank_agent_input.broker.creates == []
    blank_agent_input._ensure_broker_connected.assert_not_awaited()

    manual_blank = make_generator(None)
    manual_blank.parameter_values["prompt"] = ""
    manual_blank._assert_agent_result_available()
    assert manual_blank._hmb_expected_agent_result is None

    legacy_agent = make_agent()
    legacy_text = "Valid saved legacy Agent instruction."
    legacy_agent._set_visible_output(legacy_text)
    assert legacy_agent._hmb_execution_result_snapshot() == {}
    legacy_generator = make_generator(legacy_agent)
    legacy_generator.parameter_values["prompt"] = legacy_text
    await legacy_generator.aprocess()
    assert legacy_generator.result["was_successful"] is True, legacy_generator.result
    assert len(legacy_generator.broker.creates) == 1
    assert legacy_generator.broker.creates[0]["prompt"] == legacy_text

    source = make_agent()
    original_text = await succeed(source)
    original_run = source._hmb_execution_result_snapshot()["run_id"]
    source._set_hmb_execution_result("failed", code="MODEL_TIMEOUT", message="safe failure")

    # Source authority wins even when the prompt cable still contains old success.
    failed = make_generator(source)
    failed.parameter_values["prompt"] = original_text
    await failed.aprocess()
    assert failed.result["result_details"].startswith("SKIPPED:")
    assert failed.broker.creates == []

    # Output-map clearing/reopen still sees the persisted execution result.
    source.parameter_output_values.clear()
    source._hmb_execution_result = {}
    assert source._hmb_execution_result_snapshot()["status"] == "failed"
    failed_again = make_generator(source)
    failed_again.parameter_values["prompt"] = original_text
    await failed_again.aprocess()
    assert failed_again.broker.creates == [] and failed_again.result["was_successful"] is False

    # A saved paid task survives the failed dependency even with empty outputs.
    existing = make_generator(source)
    existing.checkpoint = {"task_id": "existing-paid-task", "task_identity": "broker_task", "status": "running", "stage": "accepted"}
    saved = copy.deepcopy(existing.checkpoint)
    await existing.aprocess()
    assert existing.checkpoint == saved
    assert existing.parameter_output_values["generation_id"] == "existing-paid-task"
    assert existing.parameter_output_values["generation_status"] == "running"
    assert existing.previews[-1]["action"] == "refresh_existing"
    assert existing.broker.creates == [] and existing.saved_checkpoints == []

    # Explicit retrieval bypasses Agent gating and preserves the same remote ID.
    existing.parameter_values["resume_generation_id"] = "existing-paid-task"
    existing.parameter_values["prompt"] = "[HMB EXECUTION FAILED] prior Agent failure"
    await existing.aprocess()
    assert existing.result["was_successful"] is True, existing.result
    assert existing.completed == ["existing-paid-task"]
    assert existing.broker.refreshes == ["existing-paid-task"]
    assert existing.broker.creates == []
    assert existing.parameter_output_values["generation_id"] == "existing-paid-task"

    # A successful retry establishes a new run/hash and clears old failure text.
    retry_text = await succeed(source)
    assert source._hmb_execution_result_snapshot()["run_id"] != original_run
    assert "FAILED" not in retry_text and "old text" not in retry_text
    retry = make_generator(source)
    retry.parameter_values["prompt"] = retry_text
    await retry.aprocess()
    assert retry.result["was_successful"] is True

    mismatch = make_generator(source)
    mismatch.parameter_values["prompt"] = "different stale prompt"
    await mismatch.aprocess()
    assert mismatch.result["result_details"].startswith("SKIPPED:")
    assert mismatch.broker.creates == []

    source._set_hmb_execution_result("running")
    pending = make_generator(source)
    pending.parameter_values["prompt"] = retry_text
    await pending.aprocess()
    assert "AGENT_RUNNING" in pending.result["result_details"]
    assert pending.broker.creates == []
    await succeed(source)

    # Exercise both real submission guards, including checkpoint cleanup after
    # a result changes while awaiting the required pre-submit journal save.
    for stage in ("prepare", "pre_submit"):
        for mutation in (
            "failed", "rerun", "source_removed", "source_replaced",
            "resume_failed", "connection_error", "getter_error", "live_newer_prompt",
        ):
            source = make_agent()
            text = await succeed(source)
            generator = make_generator(source)
            generator.parameter_values["prompt"] = text

            def mutate_source():
                if mutation == "failed":
                    source._set_hmb_execution_result("failed", code="MODEL_TIMEOUT")
                elif mutation == "rerun":
                    source._set_hmb_execution_result("running")
                    source._set_hmb_execution_result("succeeded")
                elif mutation == "source_removed":
                    generator.source = None
                elif mutation == "source_replaced":
                    replacement = make_agent(2)
                    replacement._set_visible_output(text)
                    replacement._set_hmb_execution_result("running")
                    replacement._set_hmb_execution_result("succeeded")
                    generator.source = replacement
                elif mutation == "resume_failed":
                    generator.parameter_values["resume_generation_id"] = "unrelated-late-resume"
                    source._set_hmb_execution_result("failed", code="MODEL_TIMEOUT")
                elif mutation == "connection_error":
                    generator._manual_agent_prompt_source = unavailable_connection_or_result
                elif mutation == "getter_error":
                    source._hmb_execution_result_snapshot = unavailable_connection_or_result
                else:
                    assert mutation == "live_newer_prompt"
                    newer = "New successful text after parameters were captured."
                    source._set_visible_output(newer)
                    source._set_hmb_execution_result("running")
                    source._set_hmb_execution_result("succeeded")
                    generator.parameter_values["prompt"] = newer

            if stage == "prepare":
                def prepare(params):
                    mutate_source()
                    return dict(params)
                generator._prepare_video_references_for_run = prepare
            else:
                original_save = generator._force_save_generation_recovery_checkpoint
                async def save_then_change(**kwargs):
                    result = await original_save(**kwargs)
                    if kwargs["reason"] == "pre_submit":
                        mutate_source()
                    return result
                generator._force_save_generation_recovery_checkpoint = save_then_change

            await generator.aprocess()
            assert generator.result["result_details"].startswith("SKIPPED:"), (stage, mutation, generator.result)
            assert generator.broker.creates == [], (stage, mutation)
            assert generator.broker.refreshes == [], (stage, mutation)
            assert not generator.parameter_output_values.get("generation_id")
            assert not generator.checkpoint.get("task_id")
            assert "PRIVATE_CONNECTION_OR_RESULT_ERROR" not in generator.result["result_details"]
            if mutation == "live_newer_prompt":
                assert "No stale prompt was submitted" in generator.result["result_details"]
            if stage == "pre_submit":
                assert generator.saved_checkpoints[-1] == ("agent_result_changed_before_submission", {})

    # Explicit cancellation is not converted into a handled ordinary failure.
    cancelled_agent = make_agent()
    async def cancel_native(_node):
        raise asyncio.CancelledError()
    with mock.patch.object(agent_module._BaseAgent, "aprocess", cancel_native, create=True):
        try:
            await cancelled_agent.aprocess()
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Agent swallowed explicit cancellation")
    assert cancelled_agent._hmb_execution_result_snapshot()["code"] == "CANCELLED"
    assert cancelled_agent.parameter_output_values["agent"] == {}

    source = make_agent()
    text = await succeed(source)
    cancelled_generator = make_generator(source)
    cancelled_generator.parameter_values["prompt"] = text
    cancelled_generator._ensure_broker_connected.side_effect = asyncio.CancelledError()
    try:
        await cancelled_generator.aprocess()
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Seedance swallowed explicit cancellation")
    assert cancelled_generator.result["result_details"].startswith("CANCELLED:")
    assert cancelled_generator.broker.creates == []
    assert not cancelled_generator._generation_run_active.is_set()


if __name__ == "__main__":
    verifier = SimpleNamespace(executable="offline-verifier", backend="offline")
    # Windows constructs an internal loopback socketpair when creating the
    # event loop. Install the network guard after that private wakeup pipe.
    with asyncio.Runner() as runner, contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(socket.socket, "connect", no_network))
        stack.enter_context(mock.patch.object(socket.socket, "connect_ex", no_network))
        stack.enter_context(mock.patch.object(socket, "create_connection", no_network))
        stack.enter_context(mock.patch.object(seedance_module, "_resolve_mp4_decode_verifier", return_value=verifier))
        stack.enter_context(mock.patch.object(logging.Logger, "error"))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        runner.run(run())
    print("HMB Agent result skip regression: PASS (50 branch runs; stale/running/hash/empty-Agent gates; 16 preparation races; 8 real cadence cases; frozen prompt/late resume/lookup errors; legacy/manual compatibility; checkpoint/resume/retry; cancellation; no network)")
