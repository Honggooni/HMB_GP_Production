"""Nonblocking/idempotent regression for Retrieve Existing Result.

Retained node state must stay on Griptape's engine loop. The synchronous Broker
refresh is the part that must leave that loop through ``asyncio.to_thread`` so
the UI/request heartbeat remains responsive while the provider is slow.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()

from griptape_nodes.exe_types.core_types import NodeMessagePayload


def load_target():
    module_path = ROOT / "HMBSeedanceGeneration.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_seedance_retrieve_ui_nonblocking_target", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Seedance retrieve regression target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()


class BlockingRefreshBridge:
    """Provider bridge whose synchronous refresh remains blocked on demand."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()
        self.calls: list[tuple[str, float, int]] = []

    def refresh_job(self, job_id: str, *, timeout: float = 60):
        self.calls.append((job_id, timeout, threading.get_ident()))
        self.started.set()
        assert self.release.wait(2.0), "blocking Broker mock was never released"
        self.finished.set()
        return {"job_id": job_id, "status": "running"}


class LiveRetrieveNode(target.HMBSeedanceGeneration):
    """Minimal retained node that exercises the production refresh coroutine."""

    def _runtime_node_is_live(self, *, require_registered=False):
        del require_registered
        return not bool(self._hmb_node_deleted)

    async def _ensure_broker_connected(self):
        return self.bridge

    def _validate_task_id(self, value):
        return str(value)

    def _monotonic(self):
        return 10.0

    def get_parameter_value(self, name):
        if name == "resume_generation_id":
            return ""
        return None

    def _publish_generation_preview(self, phase, **kwargs):
        self.preview_publications.append((phase, kwargs, threading.get_ident()))

    def _normalize_broker_task(self, response, *, fallback_job_id):
        task = dict(response)
        task.setdefault("job_id", fallback_job_id)
        return task

    def _set_broker_task_outputs(self, task, **kwargs):
        self.output_publications.append((dict(task), kwargs, threading.get_ident()))
        self.output_published.set()

    def _set_status_results(self, **kwargs):
        self.status_publications.append((kwargs, threading.get_ident()))


def make_node(name, bridge):
    # Avoid BaseNode construction: host post-registration reconciliation would
    # enqueue unrelated NodeManager work on this synthetic engine loop.
    node = object.__new__(LiveRetrieveNode)
    node.name = name
    node.bridge = bridge
    node._hmb_node_deleted = False
    node._generation_refresh_lock = threading.Lock()
    node._generation_refresh_running = False
    node._generation_run_active = threading.Event()
    node._hmb_generation_started_monotonic = None
    node._hmb_generation_started_at_ms = 0
    node.parameter_output_values = {
        "generation_id": "authoritative-existing-job-7",
        "generation_status": "cancelled_locally",
    }
    node.preview_publications = []
    node.output_publications = []
    node.status_publications = []
    node.output_published = threading.Event()
    node.status_component = SimpleNamespace(
        clear_execution_status=lambda **_kwargs: None
    )
    return node


# The overlay uses a dedicated non-serializable command parameter. Browser
# metadata cannot select a Broker task: Python accepts only an idempotency ID
# and resolves the task from its authoritative generation output.
command_node = target.HMBSeedanceGeneration(
    name="Seedance Refresh Command Transport Regression"
)
command_parameter = command_node.get_parameter_by_name(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER
)
assert command_parameter is not None
assert command_parameter.serializable is False
authoritative_job_id = "authoritative-existing-job-7"
command_node.parameter_output_values["generation_id"] = authoritative_job_id
command_node._hmb_generation_preview_state = (
    target._seedance_generation_preview_value(
        {
            "phase": "cancelled_locally",
            "job_id": authoritative_job_id,
            "action": "refresh_existing",
        }
    )
)
shot_widget_before = deepcopy(
    command_node.get_parameter_value(target.SEEDANCE_SHOT_WIDGET_PARAMETER)
)
shot_catalog_before = deepcopy(command_node._hmb_shot_catalog_snapshot)
preview_before = deepcopy(command_node._hmb_generation_preview_state)
scheduled_authoritative_ids: list[str] = []
command_node._schedule_existing_generation_refresh = lambda: (
    scheduled_authoritative_ids.append(
        str(command_node.parameter_output_values.get("generation_id") or "")
    )
)
browser_command = {
    "schema": target.SEEDANCE_REFRESH_COMMAND_SCHEMA,
    "version": target.SEEDANCE_REFRESH_COMMAND_VERSION,
    "action": "refresh_existing",
    "action_id": "refresh-command-regression-1",
    "issued_at_ms": 1_777_777_777_777,
    # These hostile/stale fields must be discarded by normalization.
    "task_id": "browser-selected-wrong-task",
    "job_id": "browser-selected-wrong-task",
    "shot": {"prompt": "must not replace durable state"},
}
command_node.set_parameter_value(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER,
    browser_command,
)
stored_command = command_node.get_parameter_value(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER
)
assert stored_command == {
    "schema": target.SEEDANCE_REFRESH_COMMAND_SCHEMA,
    "version": target.SEEDANCE_REFRESH_COMMAND_VERSION,
    "action": "refresh_existing",
    "action_id": "refresh-command-regression-1",
    "issued_at_ms": 1_777_777_777_777,
}
assert "task_id" not in stored_command and "job_id" not in stored_command
assert scheduled_authoritative_ids == [authoritative_job_id]
assert command_node.get_parameter_value(
    target.SEEDANCE_SHOT_WIDGET_PARAMETER
) == shot_widget_before
assert command_node._hmb_shot_catalog_snapshot == shot_catalog_before
assert command_node._hmb_generation_preview_state == preview_before

# Replaying the same action identity is idempotent. A new action identity is
# accepted once, but still resolves only the authoritative generation ID.
command_node.set_parameter_value(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER,
    browser_command,
)
assert scheduled_authoritative_ids == [authoritative_job_id]
second_command = {
    **browser_command,
    "action_id": "refresh-command-regression-2",
    "task_id": "another-browser-selected-task",
}
command_node.set_parameter_value(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER,
    second_command,
)
assert scheduled_authoritative_ids == [authoritative_job_id, authoritative_job_id]

# Runtime preview synchronization has one retained-mode publication path. The
# state setter is silent and exactly one explicit publisher carries the small
# widget value; repeating identical state emits nothing.
sync_parameter = SimpleNamespace(default_value={})
sync_values = {target.SEEDANCE_SHOT_WIDGET_PARAMETER: {}}
sync_set_calls: list[tuple[str, dict, bool]] = []
sync_publish_calls: list[tuple[str, dict]] = []


def sync_setter(name, value, *, emit_change=False):
    sync_set_calls.append((name, deepcopy(value), bool(emit_change)))
    sync_values[name] = deepcopy(value)


def sync_publisher(name, value):
    sync_publish_calls.append((name, deepcopy(value)))


sync_node = SimpleNamespace(
    _hmb_shot_catalog_snapshot={},
    _hmb_generation_preview_state=target._seedance_generation_preview_value(
        {
            "phase": "retrieving",
            "job_id": authoritative_job_id,
            "action": "none",
        }
    ),
    _hmb_shot_syncing=False,
    get_parameter_by_name=lambda name: (
        sync_parameter
        if name == target.SEEDANCE_SHOT_WIDGET_PARAMETER
        else None
    ),
    _shot_identity=lambda: {
        "channel_uuid": "",
        "shot_uuid": "",
        "shot_number": 1,
        "shot_name": "Only",
    },
    _hmb_available_seedance_shot_catalog=lambda _snapshot: {},
    get_parameter_value=lambda name: sync_values.get(name),
    _set_shot_value=sync_setter,
    publish_update_to_parameter=sync_publisher,
)
target.HMBSeedanceGeneration._sync_seedance_shot_widget(
    sync_node,
    emit_change=True,
)
assert len(sync_set_calls) == 1
assert sync_set_calls[0][0] == target.SEEDANCE_SHOT_WIDGET_PARAMETER
assert sync_set_calls[0][2] is False
assert len(sync_publish_calls) == 1
assert sync_publish_calls[0][0] == target.SEEDANCE_SHOT_WIDGET_PARAMETER
assert sync_publish_calls[0][1] == sync_set_calls[0][1]
assert len(
    json.dumps(sync_publish_calls[0][1], separators=(",", ":")).encode("utf-8")
) < 4096
target.HMBSeedanceGeneration._sync_seedance_shot_widget(
    sync_node,
    emit_change=True,
)
assert len(sync_set_calls) == 1
assert len(sync_publish_calls) == 1


engine_loop = asyncio.new_event_loop()
engine_loop_started = threading.Event()
engine_loop_thread_id: list[int] = []


def run_engine_loop():
    asyncio.set_event_loop(engine_loop)
    engine_loop_thread_id.append(threading.get_ident())
    engine_loop_started.set()
    engine_loop.run_forever()


engine_thread = threading.Thread(
    target=run_engine_loop,
    name="seedance-regression-engine-loop",
    daemon=True,
)
engine_thread.start()
assert engine_loop_started.wait(1.0), "synthetic engine loop did not start"

event_manager = SimpleNamespace(event_loop=engine_loop, put_event=lambda _event: None)
bridge = BlockingRefreshBridge()
node = make_node("Seedance Retrieve Nonblocking Regression", bridge)
heartbeat_seen = threading.Event()
button_details = NodeMessagePayload(data={"source": "retrieve-regression"})


async def heartbeat():
    heartbeat_seen.set()


try:
    with mock.patch.object(
        target.GriptapeNodes,
        "EventManager",
        return_value=event_manager,
        create=True,
    ):
        # A refresh must never race an active aprocess/generation transaction.
        node._generation_run_active.set()
        busy_ack = node._on_refresh_clicked(None, button_details)
        assert busy_ack.success is True
        assert busy_ack.response is button_details
        assert busy_ack.altered_workflow_state is False
        assert "busy" in busy_ack.details
        assert bridge.calls == []
        assert node._generation_refresh_running is False
        node._generation_run_active.clear()

        started_at = time.monotonic()
        accepted_ack = node._on_refresh_clicked(None, button_details)
        assert accepted_ack.success is True
        assert accepted_ack.response is button_details
        assert accepted_ack.altered_workflow_state is False
        assert "scheduled" in accepted_ack.details
        assert time.monotonic() - started_at < 0.25
        assert bridge.started.wait(1.0), "existing-job refresh did not start"

        # Retained preview state stays engine-owned; only blocking provider I/O
        # is in the asyncio.to_thread worker.
        assert node.preview_publications[0][0] == "retrieving"
        assert node.preview_publications[0][2] == engine_loop_thread_id[0]
        assert bridge.calls[0][0] == "authoritative-existing-job-7"
        assert bridge.calls[0][2] != engine_loop_thread_id[0]

        # A slow synchronous provider must not stall the shared engine/UI loop.
        heartbeat_future = asyncio.run_coroutine_threadsafe(heartbeat(), engine_loop)
        assert heartbeat_seen.wait(0.5), "engine loop stalled behind Broker refresh"

        # A click burst is one authoritative-job refresh, never a new task.
        duplicate_ack = node._on_refresh_clicked(None, button_details)
        assert duplicate_ack.success is True
        assert duplicate_ack.response is button_details
        assert duplicate_ack.altered_workflow_state is False
        assert "no duplicate" in duplicate_ack.details
        time.sleep(0.03)
        assert len(bridge.calls) == 1

        # Deleting/replacing the node suppresses all late retained-state writes.
        node._hmb_node_deleted = True
        inactive_ack = node._on_refresh_clicked(None, button_details)
        assert inactive_ack.success is False
        assert inactive_ack.response is button_details
        assert inactive_ack.altered_workflow_state is False
        assert "inactive" in inactive_ack.details
        assert len(bridge.calls) == 1
        bridge.release.set()
        assert bridge.finished.wait(1.0)
        heartbeat_future.result(timeout=1.0)

        deadline = time.monotonic() + 1.0
        while node._generation_refresh_running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert node._generation_refresh_running is False
        assert node.output_publications == []
        assert node.status_publications == []

        # A host without a runnable engine loop uses the compatibility thread.
        # If that thread cannot be scheduled, the button transport still gets
        # an explicit non-mutating failure ACK and the busy guard is released.
        scheduling_node = make_node(
            "Seedance Retrieve Scheduling Failure Regression",
            BlockingRefreshBridge(),
        )
        scheduling_details = NodeMessagePayload(
            data={"source": "schedule-regression"}
        )
        unavailable_event_manager = SimpleNamespace(event_loop=None)
        with mock.patch.object(
            target.GriptapeNodes,
            "EventManager",
            return_value=unavailable_event_manager,
            create=True,
        ), mock.patch.object(
            target.threading.Thread,
            "start",
            side_effect=RuntimeError("simulated thread scheduling failure"),
        ):
            scheduling_ack = scheduling_node._on_refresh_clicked(
                None,
                scheduling_details,
            )
        assert scheduling_ack.success is False
        assert scheduling_ack.response is scheduling_details
        assert scheduling_ack.altered_workflow_state is False
        assert "could not be scheduled" in scheduling_ack.details
        assert scheduling_node._generation_refresh_running is False
finally:
    bridge.release.set()
    engine_loop.call_soon_threadsafe(engine_loop.stop)
    engine_thread.join(timeout=1.0)
    assert not engine_thread.is_alive(), "synthetic engine loop did not terminate"
    engine_loop.close()


print(
    "HMB Seedance retrieve UI nonblocking regression: PASS "
    "(dedicated action command, authoritative task ID, single bounded publish, "
    "engine-owned state, to_thread Broker I/O, heartbeat, idempotence, "
    "explicit non-mutating ACKs, deletion, scheduling failure)"
)
