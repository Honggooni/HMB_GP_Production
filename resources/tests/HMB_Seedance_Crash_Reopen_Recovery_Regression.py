"""Crash/reopen recovery contract for the Seedance preview action.

An accepted (or ambiguously submitted) Broker job must survive the local
Griptape process going away.  Hydration recreates only the central
``refresh_existing`` action for the authoritative saved task ID; it never
contacts the Broker automatically and never submits a replacement render.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
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
        "hmb_seedance_crash_reopen_recovery_regression_target",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Seedance recovery target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()


def artifact(path: Path):
    return target.VideoUrlArtifact(value=str(path), name=path.name)


def reopened_node(
    *,
    job_id: str,
    status: str,
    video: object | None = None,
    provider_response: dict | None = None,
):
    """Simulate host output hydration followed by every real load hook."""

    node = target.HMBSeedanceGeneration(
        name=f"Seedance Reopened {status or 'Idle'}"
    )
    node.parameter_output_values.update(
        {
            "generation_id": job_id,
            "generation_status": status,
            "provider_response": provider_response,
            "video_url": video,
            "VIDEO_OUT": video,
        }
    )
    # Prove load merely exposes the action.  Network retrieval is user-driven.
    schedules: list[str] = []
    node._schedule_existing_generation_refresh = lambda: schedules.append(
        "unexpected-auto-refresh"
    )
    for hook_name in ("after_deserialize", "after_load", "on_loaded"):
        getattr(node, hook_name)()
    assert schedules == [], "Reopening must not contact the Broker automatically."
    return node, target._seedance_generation_preview_value(
        node._hmb_generation_preview_state
    )


# Accepted and recoverable jobs recreate the central same-job button after a
# process crash. Repeated lifecycle callbacks must remain idempotent.
for persisted_status in (
    "queued",
    "running",
    "cancelled_locally",
    "timed_out",
    "submission_unknown",
):
    persisted_id = f"reopen-{persisted_status}-job"
    node, preview = reopened_node(
        job_id=persisted_id,
        status=persisted_status,
        provider_response={
            "transport": "fn_ai_broker",
            "id": persisted_id,
            "status": persisted_status,
        },
    )
    assert preview["job_id"] == persisted_id
    assert preview["action"] == "refresh_existing"
    assert node.parameter_output_values["generation_id"] == persisted_id


# Griptape Nodes 0.95.1 does not invoke custom deserialize/load hooks.  The
# real desktop recovery point is HMB's deferred post-registration callback,
# after host output commands have replayed.  Keep this production path covered
# separately from the compatibility hooks above.
post_registration_id = "reopen-post-registration-running"
post_registration = target.HMBSeedanceGeneration(
    name="Seedance Reopened Post Registration"
)
post_registration.parameter_output_values.update(
    {
        "generation_id": post_registration_id,
        "generation_status": "running",
        "provider_response": {
            "transport": "fn_ai_broker",
            "id": post_registration_id,
            "status": "running",
        },
    }
)
post_registration._reconcile_shared_shot_routing = lambda: None
post_registration_schedules: list[str] = []
post_registration._schedule_existing_generation_refresh = (
    lambda: post_registration_schedules.append("unexpected-auto-refresh")
)
post_registration._hmb_post_registration_shot_discovery()
post_registration_preview = target._seedance_generation_preview_value(
    post_registration._hmb_generation_preview_state
)
assert post_registration_preview["job_id"] == post_registration_id
assert post_registration_preview["action"] == "refresh_existing"
assert post_registration_schedules == []


# The client request ID is checkpointed before the billable create call.  If
# the app dies while its status is still ``submitting``, acceptance is unknown:
# reopen may only retrieve this same idempotent request, never submit again.
submitting_id = "hmb-client-request-before-crash"
submitting_node, submitting_preview = reopened_node(
    job_id=submitting_id,
    status="submitting",
    provider_response={
        "transport": "fn_ai_broker",
        "id": submitting_id,
        "status": "submitting",
    },
)
assert submitting_preview["job_id"] == submitting_id
assert submitting_preview["phase"] == "submission_unknown"
assert submitting_preview["action"] == "refresh_existing"
assert submitting_node.parameter_output_values["generation_id"] == submitting_id


# No authoritative ID means there is nothing safe to retrieve.  A stale
# in-memory preview must not manufacture a button or a task identity.
idle = target.HMBSeedanceGeneration(name="Seedance Reopened Without ID")
idle._hmb_generation_preview_state = target._seedance_generation_preview_value(
    {
        "phase": "running",
        "job_id": "stale-runtime-only-job",
        "action": "refresh_existing",
    }
)
idle.parameter_output_values.update(
    {"generation_id": "", "generation_status": "running"}
)
idle_schedules: list[str] = []
idle._schedule_existing_generation_refresh = lambda: idle_schedules.append(
    "unexpected-auto-refresh"
)
idle.after_deserialize()
idle_preview = target._seedance_generation_preview_value(
    idle._hmb_generation_preview_state
)
assert idle_preview["job_id"] == ""
assert idle_preview["action"] == "none"
assert idle_schedules == []


with tempfile.TemporaryDirectory(prefix="hmb-seedance-reopen-") as temporary:
    temporary_root = Path(temporary)
    present_path = temporary_root / "completed.mp4"
    present_path.write_bytes(b"\x00\x00\x00\x18ftypmp42recovery")

    # A completed job with its local output intact needs no recovery button.
    present_id = "reopen-completed-local-media"
    _present_node, present_preview = reopened_node(
        job_id=present_id,
        status="succeeded",
        video=artifact(present_path),
        provider_response={
            "transport": "fn_ai_broker",
            "id": present_id,
            "status": "succeeded",
        },
    )
    assert present_preview["phase"] == "succeeded"
    assert present_preview["has_existing_video"] is True
    assert present_preview["action"] == "none"

    # Griptape Nodes 0.95.1 emits and awaits saved SetParameterValueRequest
    # commands in node-parameter order. The recovery property is therefore an
    # intentional final hydration sentinel: video/status outputs must already
    # exist when it decides whether the completed job still needs retrieval.
    source = (ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8")
    class_offset = source.index("class HMBSeedanceGeneration")
    recovery_offset = source.index(
        "name=SEEDANCE_RECOVERY_PARAMETER",
        class_offset,
    )
    for earlier_parameter in (
        'name="provider_response"',
        'name="video_url"',
        'name="VIDEO_OUT"',
        'name="last_frame_url"',
        'name="generation_id"',
        'name="generation_status"',
        'name="broker_notice"',
    ):
        assert source.index(earlier_parameter, class_offset) < recovery_offset

    ordered_id = "reopen-ordered-local-success"
    ordered_node = target.HMBSeedanceGeneration(
        name="Seedance Ordered Hydration Success"
    )
    ordered_artifact = artifact(present_path)
    # Mirror the host replay: output commands first, final recovery property
    # last. The hidden property is read-only to the browser but remains writable
    # by this node and by the host's initial_setup path.
    ordered_node.parameter_output_values.update(
        {
            "video_url": ordered_artifact,
            "VIDEO_OUT": ordered_artifact,
            "provider_response": {
                "transport": "fn_ai_broker",
                "id": ordered_id,
                "status": "succeeded",
            },
            "generation_id": ordered_id,
            "generation_status": "succeeded",
        }
    )
    ordered_node.set_parameter_value(
        target.SEEDANCE_RECOVERY_PARAMETER,
        {
            "schema": target.SEEDANCE_RECOVERY_SCHEMA,
            "version": target.SEEDANCE_RECOVERY_VERSION,
            "revision": 7,
            "stage": "local_succeeded",
            "task_id": ordered_id,
            "task_identity": "broker_task",
            "status": "succeeded",
            "terminal": False,
            "updated_at_ms": 1,
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "output_format": "mp4",
            "return_last_frame": False,
            "output_file": str(present_path),
        },
        initial_setup=True,
        emit_change=False,
    )
    ordered_node._hmb_post_hydration_state_restore()
    ordered_preview = target._seedance_generation_preview_value(
        ordered_node._hmb_generation_preview_state
    )
    recovery_parameter = ordered_node.get_parameter_by_name(
        target.SEEDANCE_RECOVERY_PARAMETER
    )
    assert getattr(recovery_parameter, "settable") is False
    assert getattr(recovery_parameter, "serializable") is True
    assert ordered_preview["job_id"] == ordered_id
    assert ordered_preview["phase"] == "succeeded"
    assert ordered_preview["has_existing_video"] is True
    assert ordered_preview["action"] == "none"

    # Host workflow saves do not reliably serialize video_url/VIDEO_OUT.  The
    # durable local_succeeded checkpoint itself proves that publication and
    # verification completed, so the same node must permit one new explicit
    # render without forcing a duplicate retrieval of the old task.
    completed_without_outputs_id = "reopen-local-success-no-video-output"
    completed_without_outputs = target.HMBSeedanceGeneration(
        name="Seedance Local Success Without Serialized Artifact"
    )
    completed_without_outputs.parameter_output_values.update(
        {
            "video_url": None,
            "VIDEO_OUT": None,
            "provider_response": {
                "transport": "fn_ai_broker",
                "id": completed_without_outputs_id,
                "status": "succeeded",
            },
            "generation_id": completed_without_outputs_id,
            "generation_status": "succeeded",
        }
    )
    completed_without_outputs.set_parameter_value(
        target.SEEDANCE_RECOVERY_PARAMETER,
        {
            "schema": target.SEEDANCE_RECOVERY_SCHEMA,
            "version": target.SEEDANCE_RECOVERY_VERSION,
            "revision": 8,
            "stage": "local_succeeded",
            "task_id": completed_without_outputs_id,
            "task_identity": "broker_task",
            "status": "succeeded",
            "terminal": False,
            "updated_at_ms": 2,
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "output_format": "mp4",
            "return_last_frame": False,
            "output_file": str(present_path),
        },
        initial_setup=True,
        emit_change=False,
    )
    assert (
        completed_without_outputs._generation_recovery_blocks_new_submission()
        is False
    )
    completed_without_outputs._assert_new_submission_is_safe()
    assert (
        completed_without_outputs.parameter_output_values["generation_id"]
        == completed_without_outputs_id
    ), "Completed task identity remains available as non-blocking history."

    # A submission_unknown recovery starts with an idempotent client_request
    # identity.  If Refresh later downloads, verifies, and publishes that
    # exact result, ``local_succeeded`` is the durable consumed-result proof;
    # the provisional identity must not keep blocking every later explicit
    # Run.  This is the saved-state shape produced by the 2026-08-28 field
    # failure (hmb-* ID, successful local artifact, client_request identity).
    recovered_client_success_id = "hmb-reopen-client-local-success"
    recovered_client_success = target.HMBSeedanceGeneration(
        name="Seedance Recovered Client Request Local Success"
    )
    recovered_client_success.parameter_output_values.update(
        {
            "video_url": None,
            "VIDEO_OUT": None,
            "provider_response": {
                "transport": "fn_ai_broker",
                "id": recovered_client_success_id,
                "status": "succeeded",
                "provider_task_registered": True,
            },
            "generation_id": recovered_client_success_id,
            "generation_status": "succeeded",
        }
    )
    recovered_client_success.set_parameter_value(
        target.SEEDANCE_RECOVERY_PARAMETER,
        {
            "schema": target.SEEDANCE_RECOVERY_SCHEMA,
            "version": target.SEEDANCE_RECOVERY_VERSION,
            "revision": 9,
            "stage": "local_succeeded",
            "task_id": recovered_client_success_id,
            "task_identity": "client_request",
            "status": "succeeded",
            "terminal": False,
            "updated_at_ms": 3,
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "output_format": "mp4",
            "return_last_frame": False,
            "output_file": str(present_path),
        },
        initial_setup=True,
        emit_change=False,
    )
    assert (
        recovered_client_success._generation_recovery_blocks_new_submission()
        is False
    )
    recovered_client_success._assert_new_submission_is_safe()

    # StartFlow may hydrate this durable property before provider_response and
    # video_url.  The node must therefore accept the completed checkpoint even
    # when those output caches are not available yet.  ``local_succeeded`` is
    # backend-authored only after verified atomic publication.
    early_hydrated_client_success_id = "hmb-reopen-early-hydrated-local-success"
    early_hydrated_client_success = target.HMBSeedanceGeneration(
        name="Seedance Early Hydrated Client Request Local Success"
    )
    early_hydrated_client_success.parameter_output_values.update(
        {
            "video_url": None,
            "VIDEO_OUT": None,
            "provider_response": None,
            "generation_id": early_hydrated_client_success_id,
            "generation_status": "succeeded",
        }
    )
    early_hydrated_client_success.set_parameter_value(
        target.SEEDANCE_RECOVERY_PARAMETER,
        {
            "schema": target.SEEDANCE_RECOVERY_SCHEMA,
            "version": target.SEEDANCE_RECOVERY_VERSION,
            "revision": 10,
            "stage": "local_succeeded",
            "task_id": early_hydrated_client_success_id,
            "task_identity": "client_request",
            "status": "succeeded",
            "terminal": False,
            "updated_at_ms": 4,
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "output_format": "mp4",
            "return_last_frame": False,
            "output_file": str(temporary_root / "unproven-missing.mp4"),
        },
        initial_setup=True,
        emit_change=False,
    )
    assert (
        early_hydrated_client_success._generation_recovery_blocks_new_submission()
        is False
    )
    early_hydrated_client_success._assert_new_submission_is_safe()

    # Conversely, remote_succeeded means the paid result has not completed
    # local publication.  A stale video from an earlier render must never make
    # that different task look consumed.
    remote_success_id = "reopen-remote-success-with-stale-video"
    remote_success = target.HMBSeedanceGeneration(
        name="Seedance Remote Success With Stale Local Artifact"
    )
    stale_artifact = artifact(present_path)
    remote_success.parameter_output_values.update(
        {
            "video_url": stale_artifact,
            "VIDEO_OUT": stale_artifact,
            "provider_response": {
                "transport": "fn_ai_broker",
                "id": remote_success_id,
                "status": "succeeded",
            },
            "generation_id": remote_success_id,
            "generation_status": "succeeded",
        }
    )
    remote_success.set_parameter_value(
        target.SEEDANCE_RECOVERY_PARAMETER,
        {
            "schema": target.SEEDANCE_RECOVERY_SCHEMA,
            "version": target.SEEDANCE_RECOVERY_VERSION,
            "revision": 9,
            "stage": "remote_succeeded",
            "task_id": remote_success_id,
            "task_identity": "broker_task",
            "status": "succeeded",
            "terminal": False,
            "updated_at_ms": 3,
            "model_id": target.SEEDANCE_2_5_MODEL_ID,
            "output_format": "mp4",
            "return_last_frame": False,
            "output_file": str(present_path),
        },
        initial_setup=True,
        emit_change=False,
    )
    assert remote_success._generation_recovery_blocks_new_submission() is True
    try:
        remote_success._assert_new_submission_is_safe()
    except RuntimeError as exc:
        assert remote_success_id in str(exc)
    else:
        raise AssertionError(
            "A remote-only success was released by an earlier local video."
        )

    # Saved project outputs may use a Griptape macro. Availability must be
    # tested on File(...).resolve(), not on the literal macro string.
    class MacroResolvingFile:
        def __init__(self, value: object) -> None:
            self.value = str(value)

        def resolve(self) -> str:
            assert self.value == "{workspace_dir}/completed.mp4"
            return str(present_path)

    macro_id = "reopen-completed-macro-media"
    macro_artifact = target.VideoUrlArtifact(
        value="{workspace_dir}/completed.mp4",
        name="completed.mp4",
    )
    with mock.patch.object(target, "File", MacroResolvingFile):
        _macro_node, macro_preview = reopened_node(
            job_id=macro_id,
            status="succeeded",
            video=macro_artifact,
            provider_response={
                "transport": "fn_ai_broker",
                "id": macro_id,
                "status": "succeeded",
            },
        )
    assert macro_preview["phase"] == "succeeded"
    assert macro_preview["has_existing_video"] is True
    assert macro_preview["action"] == "none"

    # The output reference may deserialize even though the file was deleted or
    # never finished publishing.  The paid remote result remains retrievable.
    missing_path = temporary_root / "missing-after-crash.mp4"
    missing_id = "reopen-completed-missing-media"
    missing_node, missing_preview = reopened_node(
        job_id=missing_id,
        status="succeeded",
        video=artifact(missing_path),
        provider_response={
            "transport": "fn_ai_broker",
            "id": missing_id,
            "status": "succeeded",
        },
    )
    assert not missing_path.exists()
    assert missing_preview["job_id"] == missing_id
    assert missing_preview["has_existing_video"] is False
    assert missing_preview["action"] == "refresh_existing"
    assert missing_node.parameter_output_values["generation_id"] == missing_id


# A definitively terminal failure is kept visible but cannot be restarted or
# resubmitted by the recovery UI.  The explicit terminal flag distinguishes it
# from a local/UI failure whose same remote job may still need retrieval.
terminal_id = "reopen-terminal-failure"
_terminal_node, terminal_preview = reopened_node(
    job_id=terminal_id,
    status="failed",
    provider_response={
        "transport": "fn_ai_broker",
        "id": terminal_id,
        "status": "failed",
        "terminal": True,
    },
)
assert terminal_preview["phase"] == "failed"
assert terminal_preview["job_id"] == terminal_id
assert terminal_preview["action"] == "none"


# Pressing the node's normal Run control after reopen cannot bypass the
# recovery action and create a replacement task. A confirmed terminal task is
# the only persisted failure state that releases this guard.
blocked_id = "reopen-new-create-guard"
blocked_node, _blocked_preview = reopened_node(
    job_id=blocked_id,
    status="running",
    provider_response={
        "transport": "fn_ai_broker",
        "id": blocked_id,
        "status": "running",
    },
)
try:
    blocked_node._assert_new_submission_is_safe()
except RuntimeError as exc:
    assert blocked_id in str(exc)
    assert "replacement render was not submitted" in str(exc)
else:
    raise AssertionError("An unresolved recovered task allowed a new create.")
assert terminal_preview["action"] == "none"
assert _terminal_node._generation_recovery_blocks_new_submission() is False

for unresolved_status in (
    "submission_unknown",
    "queued",
    "running",
    "cancelled_locally",
    "timed_out",
):
    unresolved_id = f"reopen-guard-{unresolved_status}"
    unresolved_node, unresolved_preview = reopened_node(
        job_id=unresolved_id,
        status=unresolved_status,
        provider_response={
            "transport": "fn_ai_broker",
            "id": unresolved_id,
            "status": unresolved_status,
        },
    )
    assert unresolved_preview["action"] == "refresh_existing"
    assert unresolved_node._generation_recovery_blocks_new_submission() is True
    try:
        unresolved_node._assert_new_submission_is_safe()
    except RuntimeError as exc:
        assert unresolved_id in str(exc)
    else:
        raise AssertionError(
            f"Unresolved {unresolved_status} task allowed a replacement render."
        )


class RecordingBridge:
    def __init__(self) -> None:
        self.refresh_calls: list[tuple[str, float]] = []
        self.create_calls: list[object] = []

    def refresh_job(self, job_id: str, *, timeout: float = 60):
        self.refresh_calls.append((job_id, timeout))
        return {"id": job_id, "status": "running"}

    def generate_seedance(self, payload, *, timeout: float = 60):
        self.create_calls.append((payload, timeout))
        raise AssertionError("Recovery must never call the create endpoint.")


# A saved checkpoint can hydrate before (or outlive) non-serializable output
# replay.  Both the final restore callback and Status Refresh must recover the
# same provisional request without requiring generation_id or Resume Task ID.
checkpoint_only_id = "hmb-checkpoint-only-refresh"
checkpoint_only = target.HMBSeedanceGeneration(
    name="Seedance Checkpoint Only Refresh"
)
checkpoint_only.set_parameter_value(
    target.SEEDANCE_RECOVERY_PARAMETER,
    {
        "schema": target.SEEDANCE_RECOVERY_SCHEMA,
        "version": target.SEEDANCE_RECOVERY_VERSION,
        "revision": 17,
        "stage": "pre_submit",
        "task_id": checkpoint_only_id,
        "task_identity": "client_request",
        "status": "submitting",
        "terminal": False,
        "updated_at_ms": 17,
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mp4",
        "return_last_frame": False,
        "output_file": "checkpoint-only.mp4",
    },
    initial_setup=True,
    emit_change=False,
)
checkpoint_only._hmb_post_hydration_state_restore()
assert checkpoint_only.parameter_output_values["generation_id"] == checkpoint_only_id
checkpoint_only_preview = target._seedance_generation_preview_value(
    checkpoint_only._hmb_generation_preview_state
)
assert checkpoint_only_preview["job_id"] == checkpoint_only_id
assert checkpoint_only_preview["action"] == "refresh_existing"

# Reproduce the desktop race: the host replays empty output defaults after the
# first successful restore.  An identical recovery fingerprint must still
# repair the outputs rather than returning early.
checkpoint_only.parameter_output_values.update(
    {
        "generation_id": "",
        "generation_status": "",
        "provider_response": None,
    }
)
checkpoint_only._hmb_post_hydration_state_restore()
assert checkpoint_only.parameter_output_values["generation_id"] == checkpoint_only_id
assert checkpoint_only.parameter_output_values["generation_status"] == (
    "submission_unknown"
)

# Status Refresh is also independently safe during the small window before a
# deferred restore callback: clear the volatile outputs again and prove the
# durable checkpoint alone drives one GET and zero billable creates.
checkpoint_only.parameter_output_values.update(
    {
        "generation_id": "",
        "generation_status": "",
        "provider_response": None,
    }
)
assert (
    checkpoint_only._authoritative_existing_generation_id() == checkpoint_only_id
)

# A valid but stale output from an older render must not outrank the unresolved
# paid request in the durable checkpoint.
checkpoint_only.parameter_output_values.update(
    {
        "generation_id": "stale-output-job",
        "generation_status": "succeeded",
        "provider_response": {
            "transport": "fn_ai_broker",
            "id": "stale-output-job",
            "status": "succeeded",
        },
    }
)
checkpoint_only_bridge = RecordingBridge()
checkpoint_only._runtime_node_is_live = lambda *, require_registered=False: True
checkpoint_only.status_component = SimpleNamespace(
    clear_execution_status=lambda **_kwargs: None
)
with mock.patch.object(
    checkpoint_only,
    "_ensure_broker_connected",
    new=mock.AsyncMock(return_value=checkpoint_only_bridge),
), mock.patch.object(checkpoint_only, "_set_status_results", create=True):
    asyncio.run(checkpoint_only._refresh_async())

assert checkpoint_only_bridge.refresh_calls == [(checkpoint_only_id, 60)]
assert checkpoint_only_bridge.create_calls == []
assert checkpoint_only.parameter_output_values["generation_id"] == checkpoint_only_id


# Refreshing historical completed output may repopulate a missing viewport, but
# it must never downgrade the durable proof that this paid result was already
# downloaded, verified, and atomically published.
local_success_id = "reopen-local-success-refresh-monotonic"
local_success = target.HMBSeedanceGeneration(
    name="Seedance Local Success Refresh Monotonic"
)
local_success.set_parameter_value(
    target.SEEDANCE_RECOVERY_PARAMETER,
    {
        "schema": target.SEEDANCE_RECOVERY_SCHEMA,
        "version": target.SEEDANCE_RECOVERY_VERSION,
        "revision": 18,
        "stage": "local_succeeded",
        "task_id": local_success_id,
        "task_identity": "broker_task",
        "status": "succeeded",
        "terminal": False,
        "updated_at_ms": 18,
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mp4",
        "return_last_frame": False,
        "output_file": "local-success.mp4",
    },
    initial_setup=True,
    emit_change=False,
)
local_success.parameter_output_values.update(
    {
        "generation_id": "",
        "generation_status": "",
        "provider_response": None,
    }
)
local_success_bridge = RecordingBridge()
local_success._runtime_node_is_live = lambda *, require_registered=False: True
local_success.status_component = SimpleNamespace(
    clear_execution_status=lambda **_kwargs: None
)
with mock.patch.object(
    local_success,
    "_ensure_broker_connected",
    new=mock.AsyncMock(return_value=local_success_bridge),
), mock.patch.object(local_success, "_set_status_results", create=True):
    asyncio.run(local_success._refresh_async())

local_success_checkpoint = target._seedance_recovery_value(
    local_success.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER)
)
assert local_success_bridge.refresh_calls == [(local_success_id, 60)]
assert local_success_bridge.create_calls == []
assert local_success_checkpoint["stage"] == "local_succeeded"
assert local_success_checkpoint["task_id"] == local_success_id
assert local_success._generation_recovery_blocks_new_submission() is False


# Execute the backend operation reached by the restored button.  It performs
# one GET/refresh for the authoritative ID and zero billable creates.
refresh_id = "reopen-safe-refresh-only"
refresh_node, refresh_preview = reopened_node(
    job_id=refresh_id,
    status="running",
    provider_response={
        "transport": "fn_ai_broker",
        "id": refresh_id,
        "status": "running",
    },
)
assert refresh_preview["action"] == "refresh_existing"
bridge = RecordingBridge()
refresh_node._runtime_node_is_live = lambda *, require_registered=False: True
refresh_node.status_component = SimpleNamespace(
    clear_execution_status=lambda **_kwargs: None
)
with mock.patch.object(
    refresh_node,
    "_ensure_broker_connected",
    new=mock.AsyncMock(return_value=bridge),
), mock.patch.object(refresh_node, "_set_status_results", create=True):
    asyncio.run(refresh_node._refresh_async())

assert bridge.refresh_calls == [(refresh_id, 60)]
assert bridge.create_calls == []
assert refresh_node.parameter_output_values["generation_id"] == refresh_id
assert refresh_node.parameter_output_values["generation_status"] == "running"


class ResolvingClientRequestBridge:
    def __init__(self) -> None:
        self.refresh_calls: list[tuple[str, float]] = []

    def refresh_job(self, job_id: str, *, timeout: float = 60):
        self.refresh_calls.append((job_id, timeout))
        return {"id": "job-resolved-from-client-request", "status": "running"}


# A successful same-job lookup promotes the durable pre-submit identity to the
# Broker's authoritative task identity.  No create call is involved.
client_refresh_id = "hmb-reopen-client-request-refresh"
client_refresh = target.HMBSeedanceGeneration(
    name="Seedance Resolve Client Request Identity"
)
client_refresh._runtime_node_is_live = lambda *, require_registered=False: True
client_refresh.status_component = SimpleNamespace(
    clear_execution_status=lambda **_kwargs: None
)
client_refresh.parameter_output_values.update(
    {
        "generation_id": client_refresh_id,
        "generation_status": "submission_unknown",
        "provider_response": {
            "transport": "fn_ai_broker",
            "id": client_refresh_id,
            "status": "submission_unknown",
        },
    }
)
client_refresh._set_generation_recovery_checkpoint(
    stage="submission_unknown",
    task_id=client_refresh_id,
    task_identity="client_request",
    status="submission_unknown",
    params={
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        "output_format": "mp4",
        "return_last_frame": False,
    },
)
resolving_bridge = ResolvingClientRequestBridge()
client_refresh_saves: list[str] = []


async def record_client_refresh_save(*, required: bool, reason: str) -> bool:
    assert required is False
    client_refresh_saves.append(reason)
    return True


client_refresh._force_save_generation_recovery_checkpoint = (
    record_client_refresh_save
)
with mock.patch.object(
    client_refresh,
    "_ensure_broker_connected",
    new=mock.AsyncMock(return_value=resolving_bridge),
), mock.patch.object(client_refresh, "_set_status_results", create=True):
    asyncio.run(client_refresh._refresh_async())

resolved_checkpoint = target._seedance_recovery_value(
    client_refresh.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER)
)
assert resolving_bridge.refresh_calls == [(client_refresh_id, 60)]
assert resolved_checkpoint["task_id"] == "job-resolved-from-client-request"
assert resolved_checkpoint["task_identity"] == "broker_task"
assert resolved_checkpoint["stage"] == "refresh"
assert client_refresh.parameter_output_values["generation_id"] == (
    "job-resolved-from-client-request"
)
assert client_refresh_saves == ["manual_refresh"]


class FakeWorkflowContext:
    def __init__(self, name: str) -> None:
        self.name = name

    def has_current_workflow(self) -> bool:
        return True

    def get_current_workflow_name(self) -> str:
        return self.name


async def verify_five_node_save_coordinator() -> None:
    from griptape_nodes.retained_mode.events.workflow_events import (
        SaveWorkflowResultSuccess,
    )

    nodes = [
        target.HMBSeedanceGeneration(name=f"Checkpoint Generator {number}")
        for number in range(1, 6)
    ]
    for number, node in enumerate(nodes, start=1):
        node._set_generation_recovery_checkpoint(
            stage="pre_submit",
            task_id=f"hmb-five-save-{number}",
            task_identity="client_request",
            status="submitting",
            params={
                "model_id": target.SEEDANCE_2_5_MODEL_ID,
                "output_format": "mov",
                "return_last_frame": True,
            },
        )

    requests: list[object] = []
    active_saves = 0
    maximum_active_saves = 0

    async def recording_save(request):
        nonlocal active_saves, maximum_active_saves
        requests.append(request)
        active_saves += 1
        maximum_active_saves = max(maximum_active_saves, active_saves)
        try:
            await asyncio.sleep(0.01)
            return SaveWorkflowResultSuccess(
                file_path="C:/synthetic/saved-workflow.py",
                workflow_name="saved-workflow",
                result_details="saved",
            )
        finally:
            active_saves -= 1

    with mock.patch.object(
        target.GriptapeNodes,
        "ContextManager",
        new=lambda: FakeWorkflowContext("saved-workflow"),
        create=True,
    ), mock.patch.object(
        target.GriptapeNodes,
        "ahandle_request",
        new=recording_save,
        create=True,
    ):
        results = await asyncio.gather(
            *(
                node._force_save_generation_recovery_checkpoint(
                    required=True,
                    reason="pre_submit",
                )
                for node in nodes
            )
        )

    assert results == [True] * 5
    assert maximum_active_saves == 1
    assert len(requests) == 5
    assert all(getattr(request, "file_name") == "saved-workflow" for request in requests)
    assert all(getattr(request, "broadcast_result") is False for request in requests)
    assert all(getattr(request, "create_versioned") is False for request in requests)
    assert all(getattr(request, "overwrite_existing") is True for request in requests)

    first_save_requests: list[object] = []

    async def first_save(request):
        first_save_requests.append(request)
        return SaveWorkflowResultSuccess(
            file_path="C:/synthetic/untitled.py",
            workflow_name="untitled",
            result_details="saved",
        )

    with mock.patch.object(
        target.GriptapeNodes,
        "ContextManager",
        new=lambda: FakeWorkflowContext("unsaved:recovery-test"),
        create=True,
    ), mock.patch.object(
        target.GriptapeNodes,
        "ahandle_request",
        new=first_save,
        create=True,
    ):
        assert await nodes[0]._force_save_generation_recovery_checkpoint(
            required=True,
            reason="pre_submit",
        )

    assert len(first_save_requests) == 1
    assert getattr(first_save_requests[0], "file_name") is None
    assert getattr(first_save_requests[0], "broadcast_result") is True


asyncio.run(verify_five_node_save_coordinator())


class NoPostBridge:
    def __init__(self) -> None:
        self.create_calls = 0

    def generate_seedance(self, _payload, *, timeout: float = 60):
        del timeout
        self.create_calls += 1
        raise AssertionError("POST crossed a failed recovery-save boundary.")


# The durable pre-submit save is a hard billing boundary. A host save failure
# clears the unsent provisional identity and reaches neither the Broker create
# method nor the submission wrapper, so a corrected retry is not blocked.
pre_submit = target.HMBSeedanceGeneration(name="Seedance Save Boundary")
pre_submit_bridge = NoPostBridge()
pre_submit._runtime_node_is_live = lambda *, require_registered=False: True
pre_submit._output_file = SimpleNamespace(build_file=lambda: object())
pre_submit._get_parameters = lambda: {
    "resume_generation_id": "",
    "model_id": target.SEEDANCE_2_0_MODEL_ID,
    target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
    "output_format": "mp4",
    "return_last_frame": False,
    "generation_timeout_seconds": 600,
    "poll_interval_seconds": 5,
}
pre_submit._resolve_exact_shot_generation_inputs = lambda params: dict(params)
pre_submit._validate_parameters = lambda _params: None
pre_submit._preflight_output_destination = lambda *_args: None
pre_submit._ensure_broker_connected = mock.AsyncMock(
    return_value=pre_submit_bridge
)
pre_submit._prepare_video_references_for_run = lambda params: dict(params)
pre_submit._build_broker_payload = lambda _params: {}
submission_wrapper_calls: list[str] = []


async def forbidden_submission_wrapper(*_args, **_kwargs):
    submission_wrapper_calls.append("post")
    raise AssertionError("Submission wrapper crossed a failed save boundary.")


pre_submit._await_submission_result = forbidden_submission_wrapper


async def fail_required_checkpoint(*, required: bool, reason: str) -> bool:
    assert required is True
    assert reason == "pre_submit"
    raise RuntimeError("synthetic workflow save failure")


pre_submit._force_save_generation_recovery_checkpoint = fail_required_checkpoint
with mock.patch.object(
    target,
    "_resolve_mp4_decode_verifier",
    return_value=SimpleNamespace(executable="test-verifier", backend="test"),
):
    try:
        asyncio.run(pre_submit._process_generation_impl())
    except RuntimeError as exc:
        assert "synthetic workflow save failure" in str(exc)
    else:
        raise AssertionError("Failed pre-submit workflow save did not stop execution.")

assert submission_wrapper_calls == []
assert pre_submit_bridge.create_calls == 0
pre_submit_checkpoint = target._seedance_recovery_value(
    pre_submit.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER)
)
assert pre_submit_checkpoint["task_id"] == ""
assert pre_submit_checkpoint["status"] == ""
assert pre_submit.parameter_output_values["generation_id"] == ""
assert pre_submit.parameter_output_values["generation_status"] == "failed"


# Once a task identity exists, later UI edits must not redirect its recovered
# result. The accepted-stage checkpoint preserves the original filename and
# the refresh path rebuilds a destination from that saved contract.
destination_node = target.HMBSeedanceGeneration(
    name="Seedance Recovery Output Contract"
)
destination_node.set_parameter_value("output_file", "submitted-target.mov")
destination_node._set_generation_recovery_checkpoint(
    stage="pre_submit",
    task_id="hmb-output-contract",
    task_identity="client_request",
    status="submitting",
    params={
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mov",
        "return_last_frame": False,
    },
)
destination_node.set_parameter_value("output_file", "later-ui-edit.mov")
preserved_destination_checkpoint = destination_node._set_generation_recovery_checkpoint(
    stage="accepted",
    task_id="broker-output-contract",
    task_identity="broker_task",
    status="running",
    params={
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mov",
        "return_last_frame": False,
    },
)
assert preserved_destination_checkpoint["output_file"] == "submitted-target.mov"
recovery_destination = object()
with mock.patch.object(
    target.ProjectFileDestination,
    "from_situation",
    return_value=recovery_destination,
) as destination_builder:
    assert (
        destination_node._build_recovery_output_destination(
            preserved_destination_checkpoint
        )
        is recovery_destination
    )
destination_builder.assert_called_once_with(
    "submitted-target.mov",
    target.ProjectFileParameter.DEFAULT_SITUATION,
    node_name=destination_node.name,
)

# A later new submission never inherits the prior task's destination. If the
# visible value is empty, capture ProjectFileParameter's current default.
new_destination_node = target.HMBSeedanceGeneration(
    name="Seedance New Output Contract"
)
new_destination_node.set_parameter_value("output_file", "previous-task.mov")
new_destination_node._set_generation_recovery_checkpoint(
    stage="terminal",
    task_id="broker-previous-output-contract",
    task_identity="broker_task",
    status="failed",
    params={
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mov",
        "return_last_frame": False,
    },
    terminal=True,
)
new_destination_node.set_parameter_value("output_file", "")
new_destination_checkpoint = new_destination_node._set_generation_recovery_checkpoint(
    stage="pre_submit",
    task_id="hmb-new-output-contract",
    task_identity="client_request",
    status="submitting",
    params={
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        "output_format": "mp4",
        "return_last_frame": False,
    },
)
assert new_destination_checkpoint["output_file"] == (
    new_destination_node._output_file._default_filename
)
assert new_destination_checkpoint["output_file"] != "previous-task.mov"


class MissingTaskBridge:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.refresh_calls: list[str] = []

    def refresh_job(self, job_id: str, *, timeout: float = 60):
        del timeout
        self.refresh_calls.append(job_id)
        raise target._BrokerError(
            "synthetic Broker lookup failure",
            status_code=self.status_code,
        )


async def verify_definitive_client_request_cleanup() -> None:
    cases = (
        (404, "client_request", True),
        (410, "client_request", True),
        (404, "broker_task", False),
        (503, "client_request", False),
    )
    for status_code, identity, should_clear in cases:
        task_id = f"hmb-lookup-{status_code}-{identity}"
        node = target.HMBSeedanceGeneration(
            name=f"Seedance Lookup {status_code} {identity}"
        )
        node._runtime_node_is_live = lambda *, require_registered=False: True
        node.status_component = SimpleNamespace(
            clear_execution_status=lambda **_kwargs: None
        )
        node.parameter_output_values.update(
            {
                "generation_id": task_id,
                "generation_status": "running",
                "provider_response": {
                    "transport": "fn_ai_broker",
                    "id": task_id,
                    "status": "running",
                },
            }
        )
        node._set_generation_recovery_checkpoint(
            stage="accepted" if identity == "broker_task" else "pre_submit",
            task_id=task_id,
            task_identity=identity,
            status="running" if identity == "broker_task" else "submitting",
            params={
                "model_id": target.SEEDANCE_2_0_MODEL_ID,
                "output_format": "mp4",
                "return_last_frame": False,
            },
        )
        bridge = MissingTaskBridge(status_code)
        saves: list[str] = []

        async def record_save(*, required: bool, reason: str) -> bool:
            assert required is False
            saves.append(reason)
            return True

        node._force_save_generation_recovery_checkpoint = record_save
        with mock.patch.object(
            node,
            "_ensure_broker_connected",
            new=mock.AsyncMock(return_value=bridge),
        ), mock.patch.object(node, "_set_status_results", create=True):
            await node._refresh_async()

        checkpoint = target._seedance_recovery_value(
            node.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER)
        )
        assert bridge.refresh_calls == [task_id]
        if should_clear:
            assert checkpoint["task_id"] == ""
            assert node.parameter_output_values["generation_id"] == ""
            assert node._generation_recovery_blocks_new_submission() is False
            assert saves == ["client_request_not_found"]
        else:
            assert checkpoint["task_id"] == task_id
            assert node.parameter_output_values["generation_id"] == task_id
            assert node._generation_recovery_blocks_new_submission() is True
            assert saves == []


asyncio.run(verify_definitive_client_request_cleanup())


async def verify_submission_liveness_gates() -> None:
    # The last gate is inside the paced worker, immediately before the create
    # callback. Deletion while waiting for the cadence slot wins without POST.
    paced_node = target.HMBSeedanceGeneration(name="Seedance Cadence Gate")
    create_calls: list[str] = []

    def delete_during_cadence() -> None:
        paced_node._hmb_node_deleted = True

    def forbidden_create() -> None:
        create_calls.append("post")

    with mock.patch.object(
        target,
        "_broker_wait_for_submission_slot",
        side_effect=delete_during_cadence,
    ):
        try:
            await paced_node._await_submission_result(forbidden_create)
        except target._SubmissionCancelledBeforeStart:
            pass
        else:
            raise AssertionError("Deleted node crossed the final submission gate.")
    assert create_calls == []

    # The engine-loop gate is repeated after the required save because five
    # generators can wait there. A deletion during that await also wins.
    saved_node = target.HMBSeedanceGeneration(name="Seedance Post Save Gate")
    saved_node._runtime_node_is_live = (
        lambda *, require_registered=False: not saved_node._hmb_node_deleted
    )
    saved_node._output_file = SimpleNamespace(build_file=lambda: object())
    saved_node._get_parameters = lambda: {
        "resume_generation_id": "",
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
        "output_format": "mp4",
        "return_last_frame": False,
        "generation_timeout_seconds": 600,
        "poll_interval_seconds": 5,
    }
    saved_node._resolve_exact_shot_generation_inputs = lambda params: dict(params)
    saved_node._validate_parameters = lambda _params: None
    saved_node._preflight_output_destination = lambda *_args: None
    saved_node._ensure_broker_connected = mock.AsyncMock(
        return_value=NoPostBridge()
    )
    saved_node._prepare_video_references_for_run = lambda params: dict(params)
    saved_node._build_broker_payload = lambda _params: {}
    submission_calls: list[str] = []

    async def delete_after_save(*, required: bool, reason: str) -> bool:
        assert required is True
        assert reason == "pre_submit"
        saved_node._hmb_node_deleted = True
        return True

    async def forbidden_after_save(*_args, **_kwargs):
        submission_calls.append("post")
        raise AssertionError("Deleted node crossed the post-save gate.")

    saved_node._force_save_generation_recovery_checkpoint = delete_after_save
    saved_node._await_submission_result = forbidden_after_save
    with mock.patch.object(
        target,
        "_resolve_mp4_decode_verifier",
        return_value=SimpleNamespace(executable="test-verifier", backend="test"),
    ):
        try:
            await saved_node._process_generation_impl()
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Post-save deletion did not cancel submission.")
    assert submission_calls == []

    # Stop keeps the node registered but must still win after the required
    # pre-submit save. Its provisional ID, status, and checkpoint are cleared
    # and persisted before cancellation reaches the outer execution handler.
    class StopGateNode(target.HMBSeedanceGeneration):
        def __init__(self, **kwargs) -> None:
            self._test_cancellation_requested = False
            super().__init__(**kwargs)

        @property
        def is_cancellation_requested(self) -> bool:
            return self._test_cancellation_requested

    stopped_node = StopGateNode(name="Seedance Post Save Stop Gate")
    stopped_node._runtime_node_is_live = lambda *, require_registered=False: True
    stopped_node._output_file = SimpleNamespace(build_file=lambda: object())
    stopped_node._get_parameters = lambda: {
        "resume_generation_id": "",
        "model_id": target.SEEDANCE_2_0_MODEL_ID,
        target.TASK_PARAMETER: target.TASK_TEXT_ONLY,
        "output_format": "mp4",
        "return_last_frame": False,
        "generation_timeout_seconds": 600,
        "poll_interval_seconds": 5,
    }
    stopped_node._resolve_exact_shot_generation_inputs = lambda params: dict(params)
    stopped_node._validate_parameters = lambda _params: None
    stopped_node._preflight_output_destination = lambda *_args: None
    stopped_node._ensure_broker_connected = mock.AsyncMock(return_value=NoPostBridge())
    stopped_node._prepare_video_references_for_run = lambda params: dict(params)
    stopped_node._build_broker_payload = lambda _params: {}
    stop_save_reasons: list[str] = []
    stop_submission_calls: list[str] = []

    async def stop_after_required_save(*, required: bool, reason: str) -> bool:
        stop_save_reasons.append(reason)
        if required:
            assert reason == "pre_submit"
            stopped_node._test_cancellation_requested = True
        else:
            assert reason == "cancelled_after_pre_submit_save"
            checkpoint = target._seedance_recovery_value(
                stopped_node.get_parameter_value(target.SEEDANCE_RECOVERY_PARAMETER)
            )
            assert checkpoint["task_id"] == ""
            assert stopped_node.parameter_output_values["generation_id"] == ""
            assert stopped_node.parameter_output_values["generation_status"] == ""
        return True

    async def forbidden_after_stop(*_args, **_kwargs):
        stop_submission_calls.append("post")
        raise AssertionError("Stopped node crossed the post-save gate.")

    stopped_node._force_save_generation_recovery_checkpoint = stop_after_required_save
    stopped_node._await_submission_result = forbidden_after_stop
    with mock.patch.object(
        target,
        "_resolve_mp4_decode_verifier",
        return_value=SimpleNamespace(executable="test-verifier", backend="test"),
    ):
        try:
            await stopped_node._process_generation_impl()
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Post-save Stop did not cancel submission.")
    assert stop_submission_calls == []
    assert stop_save_reasons == [
        "pre_submit",
        "cancelled_after_pre_submit_save",
    ]


asyncio.run(verify_submission_liveness_gates())


print(
    "HMB Seedance crash/reopen recovery regression: PASS "
    "(persisted same-job action, submitting checkpoint, no-ID fail-closed, "
    "checkpoint-only refresh, stale-output priority, late-output repair, "
    "monotonic local success, missing-media recovery, "
    "terminal no-restart, refresh-only backend path, "
    "five-node serialized save coordinator, pre-submit save billing boundary, "
    "definitive client lookup cleanup, original output target, submission gates)"
)
