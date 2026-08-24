"""Provider-free five-node Seedance full-lifecycle concurrency regression.

The production node orchestration and production Broker bridge methods are used
from create through refresh/poll and trusted-result download.  Only the bridge's
lowest I/O boundary is replaced with deterministic in-memory responses, and the
downloaded bytes are published to a temporary local directory.  No network,
Broker, provider, credential, or billable render is touched.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()


def load_target():
    module_path = ROOT / "HMBSeedanceGeneration.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_seedance_five_node_full_lifecycle_target",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the five-node Seedance target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()
NODE_COUNT = 5
VALID_MP4_BYTES = (
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    b"\x00\x00\x00\x10moov\x00\x00\x00\x08mvhd"
    b"\x00\x00\x00\x10mdat12345678"
)


class FullLifecycleCoordinator:
    """Measure overlap at every synchronous Broker boundary."""

    STAGES = ("create", "poll_1", "poll_2", "download")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.barriers = {
            stage: threading.Barrier(NODE_COUNT) for stage in self.STAGES
        }
        self.active = defaultdict(int)
        self.maximum_active = defaultdict(int)
        self.calls: dict[str, list[int]] = {
            stage: [] for stage in self.STAGES
        }
        self.thread_ids: dict[str, set[int]] = {
            stage: set() for stage in self.STAGES
        }
        self.create_started_at: list[float] = []
        self.create_payloads: dict[int, dict] = {}
        self.client_request_ids: set[str] = set()

    def rendezvous(
        self,
        stage: str,
        node_number: int,
        *,
        payload: dict | None = None,
        client_request_id: str = "",
    ) -> None:
        assert stage in self.barriers
        with self.lock:
            self.active[stage] += 1
            self.maximum_active[stage] = max(
                self.maximum_active[stage],
                self.active[stage],
            )
            self.calls[stage].append(node_number)
            self.thread_ids[stage].add(threading.get_ident())
            if stage == "create":
                self.create_started_at.append(time.monotonic())
                assert payload is not None
                self.create_payloads[node_number] = dict(payload)
                assert client_request_id
                self.client_request_ids.add(client_request_id)
        try:
            self.barriers[stage].wait(timeout=8.0)
        finally:
            with self.lock:
                self.active[stage] -= 1


class FakeLifecycleBroker(target._HMBAIBrokerBridge):
    """Real bridge contract with fake transport and fake trusted media bytes."""

    def __init__(
        self,
        node_number: int,
        coordinator: FullLifecycleCoordinator,
    ) -> None:
        # Supplying a harmless object avoids even constructing a system opener.
        super().__init__(opener=SimpleNamespace())
        self.node_number = node_number
        self.coordinator = coordinator
        self.refresh_count = 0
        self.account_calls = 0

    def account_snapshot(self, *, connect: bool):
        assert connect is True
        self.account_calls += 1
        return target._BrokerAccountSnapshot(
            state="connected",
            connected=True,
            account="Fake Five-Node Account",
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload,
        timeout: float,
        submission: bool = False,
        idempotency_key: str | None = None,
    ) -> dict:
        assert method == "POST"
        assert timeout > 0
        job_id = f"fake-full-lifecycle-{self.node_number}"
        if path == "/api/v1/generate/video":
            assert submission is True
            assert isinstance(payload, dict)
            assert idempotency_key == payload.get("client_request_id")
            self.coordinator.rendezvous(
                "create",
                self.node_number,
                payload=payload,
                client_request_id=str(idempotency_key or ""),
            )
            return {"job_id": job_id, "status": "running"}

        assert path == f"/api/v1/jobs/{job_id}/refresh"
        assert submission is False
        assert payload is None
        self.refresh_count += 1
        assert self.refresh_count in (1, 2)
        stage = f"poll_{self.refresh_count}"
        self.coordinator.rendezvous(stage, self.node_number)
        if self.refresh_count == 1:
            return {"job_id": job_id, "status": "running"}
        return {
            "job_id": job_id,
            "status": "succeeded",
            "content": {
                "video_url": (
                    "https://fake-broker.invalid/api/assets/"
                    + f"node-{self.node_number}".ljust(43, "x")
                )
            },
        }

    def is_trusted_broker_url(self, url: str) -> bool:
        return url.startswith("https://fake-broker.invalid/api/assets/")

    def download_trusted_result(
        self,
        url: str,
        *,
        max_bytes: int,
        media_type: str = "video",
    ) -> bytes:
        assert self.is_trusted_broker_url(url)
        assert max_bytes == target.MAX_DOWNLOAD_BYTES
        assert media_type == "video"
        self.coordinator.rendezvous("download", self.node_number)
        return VALID_MP4_BYTES


class LocalDestination:
    def __init__(self, path: Path) -> None:
        self.location = str(path)
        self._append = False
        self._create_parents = True
        raw_overwrite = target.ExistingFilePolicy.OVERWRITE
        self._existing_file_policy = (
            raw_overwrite
            if isinstance(raw_overwrite, target.ExistingFilePolicy)
            else target.ExistingFilePolicy()
        )

    def resolve(self) -> str:
        return self.location


class LocalOutputFile:
    def __init__(self, destination: LocalDestination) -> None:
        self.destination = destination

    def build_file(self) -> LocalDestination:
        return self.destination


class FullLifecycleNode(target.HMBSeedanceGeneration):
    def __init__(
        self,
        node_number: int,
        coordinator: FullLifecycleCoordinator,
        output_root: Path,
    ) -> None:
        super().__init__(name=f"HMB Seedance Generation {node_number}")
        self.node_number = node_number
        self.bridge = FakeLifecycleBroker(node_number, coordinator)
        self.destination = LocalDestination(
            output_root / f"five-node-shot-{node_number:02d}.mp4"
        )
        self._output_file = LocalOutputFile(self.destination)
        self.status_results: list[dict] = []
        self.params = {
            "resume_generation_id": "",
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
            "input_mode": target.INPUT_MODE_TEXT_ONLY,
            "prompt": f"Five-node full lifecycle render {node_number}",
            "first_frame": None,
            "last_frame": None,
            "reference_images": [],
            "video_reference_slots": [],
            "video_references": [],
            "reference_audio": [],
            "resolution": "1080p",
            "ratio": "16:9",
            "duration": 4,
            "generate_audio": False,
            "watermark": False,
            "output_format": "mp4",
            "return_last_frame": False,
            "execution_expires_after": 3600,
            "priority": 0,
            "poll_interval_seconds": 1,
            "generation_timeout_seconds": 60,
            "auto_publish_local_videos": True,
            "local_video_upload_service": target.LOCAL_VIDEO_UPLOAD_GRIPTAPE,
            "tos_region": target.DEFAULT_TOS_REGION,
            "tos_endpoint": target.DEFAULT_TOS_ENDPOINT,
            "tos_url_validity_seconds": target.DEFAULT_TOS_URL_VALIDITY_SECONDS,
        }

    def _runtime_node_is_live(self, *, require_registered: bool = False) -> bool:
        del require_registered
        return not self._hmb_node_deleted

    @property
    def is_cancellation_requested(self) -> bool:
        return False

    async def _force_save_generation_recovery_checkpoint(
        self,
        *,
        required: bool,
        reason: str,
    ) -> bool:
        # These five synthetic nodes intentionally have no host workflow. The
        # crash/reopen suite owns the real save-boundary assertions.
        del required, reason
        return True

    def _create_broker_bridge(self):
        return self.bridge

    def _get_parameters(self) -> dict:
        return dict(self.params)

    def _resolve_exact_shot_generation_inputs(
        self,
        params: dict,
        *,
        verify_agent_prompt: bool = True,
    ) -> dict:
        del verify_agent_prompt
        return dict(params)

    def _sync_seedance_shot_widget(self, *, emit_change: bool = False) -> None:
        del emit_change

    def _clear_execution_status(self) -> None:
        return None

    def _set_status_results(self, **kwargs) -> None:
        self.status_results.append(dict(kwargs))

    async def _sleep(self, seconds: float) -> None:
        assert seconds > 0
        await asyncio.sleep(0)

    @classmethod
    async def _atomic_publish_completed_video(
        cls,
        destination,
        content: bytes,
        output_format: str = "mp4",
        verifier=None,
    ):
        del cls, verifier
        assert output_format == "mp4"
        assert target._video_container_matches_format(content, output_format)
        path = Path(destination.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return SimpleNamespace(location=str(path), name=path.name)


async def run_full_lifecycle() -> tuple[list[FullLifecycleNode], FullLifecycleCoordinator]:
    coordinator = FullLifecycleCoordinator()
    with tempfile.TemporaryDirectory() as temporary:
        output_root = Path(temporary)
        nodes = [
            FullLifecycleNode(number, coordinator, output_root)
            for number in range(1, NODE_COUNT + 1)
        ]

        with mock.patch.object(
            target,
            "_resolve_mp4_decode_verifier",
            return_value=SimpleNamespace(
                executable="provider-free-regression",
                backend="fake-local",
            ),
        ), mock.patch.object(
            target.httpx,
            "AsyncClient",
            side_effect=AssertionError("Full-lifecycle regression attempted HTTP"),
        ):
            await asyncio.wait_for(
                asyncio.gather(*(node.aprocess() for node in nodes)),
                timeout=12.0,
            )

        expected_numbers = list(range(1, NODE_COUNT + 1))
        for stage in coordinator.STAGES:
            assert coordinator.maximum_active[stage] == NODE_COUNT, (
                stage,
                coordinator.maximum_active[stage],
            )
            assert sorted(coordinator.calls[stage]) == expected_numbers
            assert len(coordinator.thread_ids[stage]) == NODE_COUNT

        assert len(coordinator.client_request_ids) == NODE_COUNT
        assert len(coordinator.create_payloads) == NODE_COUNT
        for number, payload in coordinator.create_payloads.items():
            assert payload["model"] == target.SEEDANCE_2_5_MODEL_ID
            assert payload["prompt"] == f"Five-node full lifecycle render {number}"
            # The production 2.5 payload must not regress to contradictory
            # 1280x720 dimensions when the authored quality is 1080p.
            assert payload["quality"] == "1080p"
            assert payload["resolution"] == "1080p"

        ordered_starts = sorted(coordinator.create_started_at)
        start_gaps = [
            later - earlier
            for earlier, later in zip(ordered_starts, ordered_starts[1:])
        ]
        assert all(gap >= 0.02 for gap in start_gaps), start_gaps

        for number, node in enumerate(nodes, start=1):
            expected_job_id = f"fake-full-lifecycle-{number}"
            assert node.bridge.account_calls == 1
            assert node.bridge.refresh_count == 2
            assert node.parameter_output_values["generation_id"] == expected_job_id
            assert node.parameter_output_values["generation_status"] == "succeeded"
            assert node.parameter_output_values["video_url"].value == (
                str(output_root / f"five-node-shot-{number:02d}.mp4")
            )
            assert Path(node.destination.location).read_bytes() == VALID_MP4_BYTES
            assert node.status_results[-1]["was_successful"] is True
            assert not node._generation_run_active.is_set()

        return nodes, coordinator


assert target.SHOT_ROUTING_MAX_SHOTS == NODE_COUNT
target.AI_BROKER_SUBMISSION_MIN_INTERVAL_SECONDS = 0.05
target._BROKER_SUBMISSION_LAST_STARTED = 0.0
asyncio.run(run_full_lifecycle())

print(
    "HMB Seedance five-node full lifecycle concurrency regression: PASS "
    "(production create/payload, two refresh polls, trusted-result download, "
    "five overlapping nodes at every Broker stage, local fake outputs, no network/provider)"
)
