from __future__ import annotations

import inspect
from pathlib import Path
import sys
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent  # noqa: E402


POLICY = (
    "The stylized production source remains authoritative for character identity, "
    "body proportions, character design, rendering medium, surface treatment, "
    "facial proportions, scene composition, and the intended animation language. "
    "Motion references provide timing, pose, camera, framing, visibility, and "
    "occlusion only, without importing realistic anatomy or photographic skin. "
    "Every character must share the scene lighting and shadow space continuously."
)
BINDING = (
    "For the current shot, preserve the assigned image identities and transfer only "
    "the explicitly bound motion, timing, camera, framing, occlusion, lighting, and "
    "look attributes. Never substitute scene content from a look-only reference."
)
NORMALIZED_POLICY = agent._normalized_leak_text(POLICY)
assert len(NORMALIZED_POLICY) > agent._SANITIZER_SECRET_WINDOW_CHARS
RAW_159 = NORMALIZED_POLICY[: agent._SANITIZER_SECRET_WINDOW_CHARS - 1]
RAW_160 = NORMALIZED_POLICY[: agent._SANITIZER_SECRET_WINDOW_CHARS]
SAFE_RESULT = (
    "Use @image1 as the stylized character design and stage the subject in the "
    "assigned scene with coherent animation lighting, grounded contact shadows, "
    "and the requested camera timing."
)
STATE_RESULT = '{"agent":{"tasks":[],"rulesets":[]}}'


assert not agent._contains_raw_policy_material(RAW_159, POLICY, BINDING)
assert agent._contains_raw_policy_material(RAW_160, POLICY, BINDING)

base_runtime_prompt = "CURRENT SHOT FACTS\n@image1 character\n"
retry_runtime_prompt = agent._compose_policy_collision_retry_prompt(
    base_runtime_prompt
)
assert retry_runtime_prompt.startswith(base_runtime_prompt.rstrip())
assert retry_runtime_prompt.count(
    agent._POLICY_COLLISION_REWRITE_CONTRACT_HEADER
) == 1
assert POLICY not in retry_runtime_prompt
assert BINDING not in retry_runtime_prompt
assert agent._PUBLIC_OUTPUT_BLOCKED not in retry_runtime_prompt


class PromptSource:
    @staticmethod
    def _hmb_agent_shot_context(_prompt_value):
        return {}


def drive(scripted_outputs: list[str]):
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_node_deleted = False
    node._hmb_lifecycle_generation = 1
    node._hmb_rules_active = False
    node._hmb_policy = ""
    node._hmb_binding = ""
    node._hmb_policy_rules = []
    node._hmb_binding_rules = []
    node._hmb_ruleset_names = ("", "")
    node._hmb_policy_identity = {}
    node._hmb_runtime_prompt = ""
    node._hmb_native_prompt_read_active = False
    node._hmb_verified_prompt_source_node = PromptSource()
    node._hmb_publication_buffer = {"output": "", "logs": ""}
    node._hmb_scheduler_step_failed = False
    node._hmb_shot_context = {}
    node._hmb_last_generator_snapshot = {}
    node._hmb_execution_shot_binding = {}
    node._hmb_native_calls_this_process = 0
    node.parameter_output_values = {"agent": {}, "output": "", "logs": ""}

    prompts: list[str] = []
    visible_writes: list[str] = []
    native_calls = [0]

    def refresh_route(self, *args, **kwargs):
        self._hmb_verified_prompt_source_node = PromptSource()

    def native_once(self):
        index = native_calls[0]
        native_calls[0] += 1
        if index >= len(scripted_outputs):
            raise AssertionError("Unexpected third native Agent attempt.")
        prompts.append(str(self._hmb_runtime_prompt))
        self.parameter_output_values["agent"] = {}
        self.parameter_output_values["output"] = scripted_outputs[index]
        self.parameter_output_values["logs"] = "private-attempt-log"
        if False:
            yield None
        return f"native-result-{index + 1}"

    def set_visible(self, value: str):
        visible_writes.append(value)
        self.parameter_output_values["output"] = value

    def publish_block(self, message: str):
        self._clear_hmb_runtime_policy()
        self.parameter_output_values["agent"] = {}
        set_visible(self, message)

    node._refresh_agent_shot_route = MethodType(refresh_route, node)
    node._has_canonical_hmb_prompt_connection = MethodType(
        lambda self: True, node
    )
    node._assert_exact_prompt_shot_route = MethodType(
        lambda self: {"enabled": False}, node
    )
    node._adopt_verified_execution_shot_binding = MethodType(
        lambda self, _subscription: None, node
    )
    node._clear_execution_shot_binding = MethodType(lambda self: None, node)
    node._load_hmb_rules = MethodType(
        lambda self: (
            POLICY,
            BINDING,
            ["project-1", "project-2", "project-3", "project-4"],
            ["shot-1", "shot-2", "shot-3", "shot-4"],
        ),
        node,
    )
    node.get_parameter_value = MethodType(
        lambda self, _name: "VISIBLE SHOT PROMPT", node
    )
    node._hide_hmb_policy_warning = MethodType(lambda self: None, node)
    node._set_agent_execution_phase = MethodType(
        lambda self, _phase: None, node
    )
    node._run_native_agent_once = MethodType(native_once, node)
    node._set_visible_output = MethodType(set_visible, node)
    node._publish_hmb_execution_block = MethodType(publish_block, node)
    node._hmb_commit_remote_prompt_publication = MethodType(
        lambda self, _text: None, node
    )
    node._hmb_invalidate_remote_prompt_publication = MethodType(
        lambda self: None, node
    )

    iterator = node.process()
    error = ""
    result = None
    try:
        next(iterator)
    except StopIteration as stop:
        result = stop.value
    except RuntimeError as exc:
        error = str(exc)

    return {
        "calls": native_calls[0],
        "prompts": prompts,
        "visible": visible_writes,
        "output": node.parameter_output_values.get("output"),
        "result": result,
        "error": error,
        "snapshot": dict(node._hmb_last_generator_snapshot),
    }


patched_names = (
    "_paired_machine_prompt",
    "_assert_public_job_data_contract",
    "_assert_fx_timing_source_contract",
    "_assert_fx_candidate_matches_signed_runtime",
    "_derive_fx_timing_runtime_scope",
    "_assert_prompt_policy_identity_matches_signed_runtime",
)
originals = {name: getattr(agent, name) for name in patched_names}
original_bootstrap = agent._hmb._bootstrap_agent_policy_session
try:
    agent._paired_machine_prompt = lambda _node, _value: "MACHINE SHOT FACTS"
    agent._assert_public_job_data_contract = lambda _value: None
    agent._assert_fx_timing_source_contract = lambda _value: {}
    agent._assert_fx_candidate_matches_signed_runtime = lambda _value: None
    agent._derive_fx_timing_runtime_scope = lambda *_args, **_kwargs: {}
    agent._assert_prompt_policy_identity_matches_signed_runtime = lambda: None
    agent._hmb._bootstrap_agent_policy_session = lambda: None

    below_boundary = drive([f"Safe preface. {RAW_159}"])
    assert below_boundary["calls"] == 1
    assert below_boundary["output"] == f"Safe preface. {RAW_159}"

    rewritten = drive([RAW_160, SAFE_RESULT])
    assert rewritten["calls"] == 2
    assert rewritten["output"] == SAFE_RESULT
    assert rewritten["visible"] == [SAFE_RESULT]
    assert rewritten["error"] == ""
    assert RAW_160 not in rewritten["prompts"][1]
    assert POLICY not in rewritten["prompts"][1]
    assert BINDING not in rewritten["prompts"][1]
    assert rewritten["prompts"][1].count(
        agent._POLICY_COLLISION_REWRITE_CONTRACT_HEADER
    ) == 1

    repeated_collision = drive([RAW_160, RAW_160])
    assert repeated_collision["calls"] == 2
    assert repeated_collision["output"] == agent._HMB_OUTPUT_REWRITE_FAILED_MESSAGE
    assert repeated_collision["error"] == agent._HMB_OUTPUT_REWRITE_FAILED_MESSAGE
    assert RAW_160 not in repeated_collision["visible"]

    state_only = drive([STATE_RESULT])
    assert state_only["calls"] == 1
    assert state_only["output"] == agent._PUBLIC_OUTPUT_BLOCKED

    state_after_collision = drive([RAW_160, STATE_RESULT])
    assert state_after_collision["calls"] == 2
    assert state_after_collision["output"] == agent._PUBLIC_OUTPUT_BLOCKED
    assert state_after_collision["error"] == ""

    normal = drive([SAFE_RESULT])
    assert normal["calls"] == 1
    assert normal["output"] == SAFE_RESULT
finally:
    for name, value in originals.items():
        setattr(agent, name, value)
    agent._hmb._bootstrap_agent_policy_session = original_bootstrap


native_guard_source = inspect.getsource(
    agent.HMBAgentLibrary._run_native_agent_once
)
assert "_hmb_policy_rewrite_retry_authorized" in native_guard_source
assert "_hmb_policy_rewrite_retry_consumed" in native_guard_source
assert "call_index == 1" in native_guard_source

print(
    "HMB Agent policy-collision one-retry regression: PASS "
    "(159/160 boundary, raw->clean, raw->raw, state isolation)"
)
