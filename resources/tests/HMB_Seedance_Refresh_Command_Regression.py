"""Minimal refresh-command and single-publication regression for Seedance.

The browser command must never carry a Broker task identity or republish the
Shot catalog. Python resolves the already-authoritative task ID, deduplicates
one-shot action IDs, and emits one preview value event.
"""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
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
        "hmb_seedance_refresh_command_regression_target",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Seedance refresh-command target.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


target = load_target()
node = target.HMBSeedanceGeneration(name="Seedance Refresh Command Regression")
command_parameter = node.get_parameter_by_name(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER
)
assert command_parameter is not None
assert command_parameter.type == "dict"
assert command_parameter.serializable is False
assert command_parameter.default_value == target._seedance_refresh_command_value()

authoritative_id = "authoritative-existing-job-17"
node.parameter_output_values["generation_id"] = authoritative_id
node.parameter_output_values["generation_status"] = "submission_unknown"
node._hmb_generation_preview_state = target._seedance_generation_preview_value(
    {
        "phase": "submission_unknown",
        "job_id": authoritative_id,
        "action": "refresh_existing",
    }
)
shot_before = deepcopy(
    node.get_parameter_value(target.SEEDANCE_SHOT_WIDGET_PARAMETER)
)
browser_command = {
    "schema": target.SEEDANCE_REFRESH_COMMAND_SCHEMA,
    "version": target.SEEDANCE_REFRESH_COMMAND_VERSION,
    "action": "refresh_existing",
    "action_id": "refresh-command-17",
    "issued_at_ms": 1_776_000_000_000,
    "job_id": "browser-task-must-never-be-used",
    "shot_catalog": {"browser": "not-authority"},
}
schedules: list[str] = []

with mock.patch.object(
    node,
    "_schedule_existing_generation_refresh",
    side_effect=lambda: schedules.append("scheduled"),
):
    normalized = node.before_value_set(command_parameter, browser_command)
    assert set(normalized) == {
        "schema", "version", "action", "action_id", "issued_at_ms"
    }
    assert normalized["action"] == "refresh_existing"
    assert normalized["action_id"] == "refresh-command-17"
    assert "job_id" not in normalized
    assert "browser-task" not in repr(normalized)
    node.parameter_values[target.SEEDANCE_REFRESH_COMMAND_PARAMETER] = normalized
    node.after_value_set(command_parameter, normalized)
    assert schedules == ["scheduled"]

    # A renderer retry or late response with the same one-shot ID is harmless.
    duplicate = node.before_value_set(command_parameter, browser_command)
    node.parameter_values[target.SEEDANCE_REFRESH_COMMAND_PARAMETER] = duplicate
    node.after_value_set(command_parameter, duplicate)
    assert schedules == ["scheduled"]

    # A new command cannot nominate a stale/browser task when backend preview
    # and output identity no longer agree.
    mismatched = dict(browser_command, action_id="refresh-command-18")
    node._hmb_generation_preview_state = target._seedance_generation_preview_value(
        {
            "phase": "submission_unknown",
            "job_id": "different-authoritative-job",
            "action": "refresh_existing",
        }
    )
    rejected = node.before_value_set(command_parameter, mismatched)
    node.parameter_values[target.SEEDANCE_REFRESH_COMMAND_PARAMETER] = rejected
    node.after_value_set(command_parameter, rejected)
    assert schedules == ["scheduled"]

assert node.get_parameter_value(target.SEEDANCE_SHOT_WIDGET_PARAMETER) == shot_before
assert node.parameter_output_values["generation_id"] == authoritative_id

# The browser still supplies no task ID when only the durable recovery
# checkpoint has hydrated. Python must authorize the one-shot command against
# that checkpoint instead of dropping the visible recovery button action.
checkpoint_node = target.HMBSeedanceGeneration(
    name="Seedance Checkpoint Refresh Command Regression"
)
checkpoint_command_parameter = checkpoint_node.get_parameter_by_name(
    target.SEEDANCE_REFRESH_COMMAND_PARAMETER
)
checkpoint_id = "hmb-checkpoint-command-19"
checkpoint_node.set_parameter_value(
    target.SEEDANCE_RECOVERY_PARAMETER,
    {
        "schema": target.SEEDANCE_RECOVERY_SCHEMA,
        "version": target.SEEDANCE_RECOVERY_VERSION,
        "revision": 19,
        "stage": "pre_submit",
        "task_id": checkpoint_id,
        "task_identity": "client_request",
        "status": "submitting",
        "terminal": False,
        "updated_at_ms": 19,
        "model_id": target.SEEDANCE_2_5_MODEL_ID,
        "output_format": "mp4",
        "return_last_frame": False,
        "output_file": "checkpoint-command.mp4",
    },
    initial_setup=True,
    emit_change=False,
)
checkpoint_node.parameter_output_values["generation_id"] = ""
checkpoint_node._hmb_generation_preview_state = target._seedance_generation_preview_value(
    {
        "phase": "submission_unknown",
        "job_id": checkpoint_id,
        "action": "refresh_existing",
    }
)
checkpoint_schedules: list[str] = []
checkpoint_command = dict(browser_command, action_id="refresh-command-19")
with mock.patch.object(
    checkpoint_node,
    "_schedule_existing_generation_refresh",
    side_effect=lambda: checkpoint_schedules.append("scheduled"),
):
    normalized_checkpoint_command = checkpoint_node.before_value_set(
        checkpoint_command_parameter,
        checkpoint_command,
    )
    checkpoint_node.parameter_values[target.SEEDANCE_REFRESH_COMMAND_PARAMETER] = (
        normalized_checkpoint_command
    )
    checkpoint_node.after_value_set(
        checkpoint_command_parameter,
        normalized_checkpoint_command,
    )
assert checkpoint_schedules == ["scheduled"]

# Runtime preview state is stored without a lifecycle event and then published
# exactly once. This prevents the prior lifecycle + value WebSocket duplicate.
node._hmb_generation_preview_state = target._seedance_generation_preview_value(
    {
        "phase": "retrieving",
        "job_id": authoritative_id,
        "action": "none",
    }
)
set_calls: list[tuple[str, object, bool]] = []
publish_calls: list[tuple[str, object]] = []

with mock.patch.object(
    node,
    "_hmb_available_seedance_shot_catalog",
    return_value={},
), mock.patch.object(
    node,
    "_set_shot_value",
    side_effect=lambda name, value, *, emit_change=False: set_calls.append(
        (name, deepcopy(value), emit_change)
    ),
), mock.patch.object(
    node,
    "publish_update_to_parameter",
    side_effect=lambda name, value: publish_calls.append(
        (name, deepcopy(value))
    ),
    create=True,
):
    node._sync_seedance_shot_widget(emit_change=True)

assert len(set_calls) == 1
assert set_calls[0][0] == target.SEEDANCE_SHOT_WIDGET_PARAMETER
assert set_calls[0][2] is False
assert len(publish_calls) == 1
assert publish_calls[0][0] == target.SEEDANCE_SHOT_WIDGET_PARAMETER
assert publish_calls[0][1] == set_calls[0][1]

print(
    "HMB Seedance refresh-command regression: PASS "
    "(minimal action, no browser task ID, dedupe, checkpoint fallback, "
    "authoritative same-job gate, Shot isolation, single preview publication)"
)
