"""No-network coverage for the timeout -> false policy-banner incident."""

from pathlib import Path
import sys
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBAgentLibrary as target


def probe(message):
    node = object.__new__(target.HMBAgentLibrary)
    node._hmb_node_deleted = False
    node.parameter_output_values = {"agent": {"private": "must be cleared"}}
    node._set_agent_execution_phase = Mock()
    node._clear_execution_shot_binding = Mock()
    node._clear_hmb_runtime_policy = Mock()
    node._set_visible_output = Mock()
    node._refresh_agent_shot_route = Mock()
    node.hide_message_by_name = Mock()
    node.show_message_by_name = Mock()
    node._publish_hmb_execution_block(message)
    node._set_visible_output.assert_called_once_with(message)
    assert node.parameter_output_values["agent"] == {}
    assert target._HMB_POLICY_WARNING_NAME in [
        call.args[0] for call in node.hide_message_by_name.call_args_list
    ]
    return node


for code in sorted(target._HMB_NATIVE_FAILURE_CODES):
    message = target._hmb_execution_failure_message(code)
    assert message.startswith(target._HMB_EXECUTION_FAILED_MESSAGE)
    assert f"Reason: {code}." in message
    probe(message).show_message_by_name.assert_not_called()

for message in (
    target._HMB_EXECUTION_FAILED_MESSAGE,
    target._HMB_SOURCE_CONTRACT_INVALID_MESSAGE,
):
    probe(message).show_message_by_name.assert_not_called()

probe(target._HMB_POLICY_UNAVAILABLE_MESSAGE).show_message_by_name.assert_called_once_with(
    target._HMB_POLICY_WARNING_NAME
)
probe(target._HMB_TOPOLOGY_UNAVAILABLE_MESSAGE).show_message_by_name.assert_called_once_with(
    target._HMB_TOPOLOGY_WARNING_NAME
)

private_text = "Read timed out: private provider request payload / secret"
code = target._hmb_native_failure_code(RuntimeError(private_text))
assert code == "MODEL_TIMEOUT"
assert private_text not in target._hmb_execution_failure_message(code)
assert target._hmb_execution_failure_message(private_text) == target._HMB_EXECUTION_FAILED_MESSAGE

# A wrapped transport failure keeps its structured HTTP classification. A 404
# never proves whether the model registration or the service route is absent.
class HttpFailure(RuntimeError):
    def __init__(self, status):
        super().__init__(private_text)
        self.status_code = status

for status, expected in ((401, "MODEL_CREDENTIAL"), (403, "MODEL_ACCESS"),
                         (404, "MODEL_OR_ENDPOINT_NOT_FOUND"), (400, "MODEL_REQUEST_INVALID"),
                         (422, "MODEL_REQUEST_INVALID"), (429, "MODEL_RATE_LIMIT"),
                         (504, "MODEL_TIMEOUT"), (503, "MODEL_PROVIDER")):
    wrapper = RuntimeError("native wrapper")
    wrapper.__cause__ = HttpFailure(status)
    assert target._hmb_native_failure_code(wrapper) == expected
    visible = target._hmb_execution_failure_message(expected, stage="invoke_model")
    assert "Stage: invoke_model." in visible and private_text not in visible
    probe(visible).show_message_by_name.assert_not_called()

cycle = RuntimeError("wrapped failure")
cycle.__cause__ = cycle
assert target._hmb_native_failure_code(cycle) == "MODEL_PROVIDER"
assert private_text not in target._hmb_execution_failure_message("MODEL_PROVIDER", stage=private_text)

# Reusing a node clears old static warnings before a different failure.
node = probe(target._HMB_POLICY_UNAVAILABLE_MESSAGE)
node.show_message_by_name.reset_mock()
node._publish_hmb_execution_block(target._hmb_execution_failure_message("MODEL_TIMEOUT"))
node.show_message_by_name.assert_not_called()
assert node.hide_message_by_name.call_count == 4

print(f"HMB Agent failure diagnostics: PASS ({len(target._HMB_NATIVE_FAILURE_CODES)} native codes, wrapped HTTP classification, exact policy/topology banners, stage, no provider payload or model call)")
