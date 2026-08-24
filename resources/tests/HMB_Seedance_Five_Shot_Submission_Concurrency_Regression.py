"""Five-node Seedance submission concurrency regression.

This test never contacts the Broker or a provider.  It drives the production
``aprocess`` and cancellation-safe ``_await_submission_result`` boundaries on
five distinct Seedance instances.  A worker barrier proves all five billable
submission slots can be entered together; a module-global lock or accidental
cross-node run guard would break the barrier and fail the test.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()


def load_target():
    module_path = ROOT / "HMBSeedanceGeneration.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_seedance_five_shot_submission_concurrency_target",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the five-Shot Seedance target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()
SHOT_COUNT = 5


class FiveSubmissionBarrier:
    def __init__(self) -> None:
        self.barrier = threading.Barrier(SHOT_COUNT)
        self.render_barrier = threading.Barrier(SHOT_COUNT)
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.remote_active = 0
        self.maximum_remote_active = 0
        self.calls: list[int] = []
        self.render_calls: list[int] = []
        self.thread_ids: set[int] = set()
        self.render_thread_ids: set[int] = set()
        self.started_at: list[float] = []

    def submit(self, node: "FiveShotNode", *, timeout: float):
        assert timeout == 30.0
        assert node._generation_run_active.is_set()
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.calls.append(node.shot_number)
            self.thread_ids.add(threading.get_ident())
            self.started_at.append(time.monotonic())
        try:
            # Every distinct Seedance instance must reach the real blocking
            # submission boundary before any one of them is allowed to return.
            self.barrier.wait(timeout=5.0)
            return {
                "job_id": f"local-five-shot-{node.shot_number}",
                "status": "running",
            }
        finally:
            with self.lock:
                self.active -= 1

    def await_remote_render(self, node: "FiveShotNode") -> None:
        """Model five accepted provider jobs remaining active together."""

        with self.lock:
            self.remote_active += 1
            self.maximum_remote_active = max(
                self.maximum_remote_active,
                self.remote_active,
            )
            self.render_calls.append(node.shot_number)
            self.render_thread_ids.add(threading.get_ident())
        try:
            # Submission cadence must not become a render/poll semaphore. Once
            # accepted, all five jobs can occupy the account's remote slots at
            # the same time (the real Broker remains the quota authority).
            self.render_barrier.wait(timeout=5.0)
        finally:
            with self.lock:
                self.remote_active -= 1


class FiveShotNode(target.HMBSeedanceGeneration):
    def configure(self, shot_number: int, coordinator: FiveSubmissionBarrier) -> None:
        self.name = f"HMB Seedance Generation Shot {shot_number}"
        self.shot_number = shot_number
        self.coordinator = coordinator
        self.result: dict = {}
        self._hmb_node_deleted = False
        self._generation_refresh_lock = threading.Lock()
        self._generation_refresh_running = False
        self._generation_run_active = threading.Event()
        self._submission_outcome_unknown = False
        self._detached_submission_tasks = set()
        self.parameter_output_values = {}

    def _runtime_node_is_live(self, *, require_registered: bool = False) -> bool:
        del require_registered
        return not self._hmb_node_deleted

    async def _aprocess_impl(self) -> None:
        result, cancelled = await self._await_submission_result(
            self.coordinator.submit,
            self,
            timeout=30.0,
        )
        assert cancelled is False
        self.result = dict(result)
        await asyncio.to_thread(self.coordinator.await_remote_render, self)


async def run_five_shots() -> list[FiveShotNode]:
    # Keep the regression fast while proving that the production cadence is
    # shared by five node instances. Production uses 1.20 seconds.
    target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.08
    target._BROKER_SUBMISSION_LAST_STARTED = 0.0
    coordinator = FiveSubmissionBarrier()
    nodes: list[FiveShotNode] = []
    for shot_number in range(1, SHOT_COUNT + 1):
        node = object.__new__(FiveShotNode)
        node.configure(shot_number, coordinator)
        nodes.append(node)

    await asyncio.wait_for(
        asyncio.gather(*(node.aprocess() for node in nodes)),
        timeout=8.0,
    )

    assert coordinator.maximum_active == SHOT_COUNT
    assert coordinator.maximum_remote_active == SHOT_COUNT
    assert sorted(coordinator.calls) == list(range(1, SHOT_COUNT + 1))
    assert sorted(coordinator.render_calls) == list(range(1, SHOT_COUNT + 1))
    assert len(coordinator.thread_ids) == SHOT_COUNT
    assert len(coordinator.render_thread_ids) == SHOT_COUNT
    ordered_starts = sorted(coordinator.started_at)
    start_gaps = [
        later - earlier
        for earlier, later in zip(ordered_starts, ordered_starts[1:])
    ]
    assert all(gap >= 0.04 for gap in start_gaps), start_gaps
    assert all(not node._generation_run_active.is_set() for node in nodes)
    assert [node.result["job_id"] for node in nodes] == [
        f"local-five-shot-{shot_number}"
        for shot_number in range(1, SHOT_COUNT + 1)
    ]
    return nodes


assert target.SHOT_ROUTING_MAX_SHOTS == SHOT_COUNT
asyncio.run(run_five_shots())


async def cancel_before_submission_slot() -> None:
    coordinator = FiveSubmissionBarrier()
    node = object.__new__(FiveShotNode)
    node.configure(1, coordinator)
    called = threading.Event()

    def forbidden_submit(*, timeout: float):
        del timeout
        called.set()
        return {"job_id": "must-not-exist", "status": "running"}

    target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.08
    target._BROKER_SUBMISSION_LAST_STARTED = time.monotonic()
    operation = asyncio.create_task(
        node._await_submission_result(forbidden_submit, timeout=30.0)
    )
    await asyncio.sleep(0.01)
    operation.cancel()
    try:
        await operation
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Queued submission cancellation was swallowed")
    for _ in range(100):
        if not node._detached_submission_tasks:
            break
        await asyncio.sleep(0.01)
    assert not called.is_set()
    assert node._submission_outcome_unknown is False
    assert not node._detached_submission_tasks


asyncio.run(cancel_before_submission_slot())


def add_stub_parameter(node, name: str, value) -> None:
    if node.get_parameter_by_name(name) is None:
        node.add_parameter(target.Parameter(name=name, default_value=value))
    node.parameter_values[name] = value


# The five workers must also own five different default destinations. Legacy
# saved workflows all carried the unsuffixed filename, so this migration is
# tested independently of the provider-free submission barrier above.
filename_nodes = []
filename_channel_uuid = str(uuid4())
for shot_number in range(1, SHOT_COUNT + 1):
    node = target.HMBSeedanceGeneration(name=f"Filename Shot {shot_number}")
    add_stub_parameter(
        node,
        target.SHOT_CHANNEL_UUID_PARAMETER,
        filename_channel_uuid,
    )
    add_stub_parameter(node, target.SHOT_UUID_PARAMETER, str(uuid4()))
    add_stub_parameter(node, target.SHOT_NUMBER_PARAMETER, shot_number)
    add_stub_parameter(node, target.SHOT_NAME_PARAMETER, f"Shot {shot_number}")
    add_stub_parameter(node, "output_format", "mp4")
    add_stub_parameter(node, "output_file", "volcengine_seedance_video.mp4")
    add_stub_parameter(node, "last_frame_file", target.LAST_FRAME_FILENAME)
    node._sync_shot_output_filenames()
    assert node.get_parameter_value("output_file") == (
        f"volcengine_seedance_video_shot_{shot_number:02d}.mp4"
    )
    assert node.get_parameter_value("last_frame_file") == (
        f"seedance_2_5_last_frame_shot_{shot_number:02d}.png"
    )
    filename_nodes.append(node)

assert len(
    {node.get_parameter_value("output_file") for node in filename_nodes}
) == SHOT_COUNT
assert len(
    {node.get_parameter_value("last_frame_file") for node in filename_nodes}
) == SHOT_COUNT

# Format changes retain the Shot suffix. Explicit user filenames never become
# managed defaults, and returning to Only removes an existing managed suffix.
format_node = filename_nodes[4]
format_node.parameter_values["output_format"] = "mov"
format_node._sync_shot_output_filenames("mov")
assert format_node.get_parameter_value("output_file") == (
    "volcengine_seedance_video_shot_05.mov"
)
format_node.parameter_values["output_file"] = "artist_final_delivery.mov"
format_node.parameter_values["last_frame_file"] = "artist_last_frame.png"
format_node._sync_shot_output_filenames("mov")
assert format_node.get_parameter_value("output_file") == "artist_final_delivery.mov"
assert format_node.get_parameter_value("last_frame_file") == "artist_last_frame.png"

only_node = filename_nodes[0]
only_node.parameter_values[target.SHOT_CHANNEL_UUID_PARAMETER] = ""
only_node.parameter_values[target.SHOT_UUID_PARAMETER] = ""
only_node._sync_shot_output_filenames("mp4")
assert only_node.get_parameter_value("output_file") == "volcengine_seedance_video.mp4"
assert only_node.get_parameter_value("last_frame_file") == target.LAST_FRAME_FILENAME

print(
    "HMB Seedance five-Shot submission concurrency regression: PASS "
    "(five distinct aprocess runs, safely paced Broker starts, five overlapping "
    "submission workers, five concurrent accepted-render waits, pre-submit cancellation, "
    "collision-free managed outputs, no provider)"
)
