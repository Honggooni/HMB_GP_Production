from __future__ import annotations

import inspect
from pathlib import Path
import sys
from types import MethodType


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import HMBAgentLibrary as agent  # noqa: E402


POLICY = """BEHAVIOR 1

CHARACTER VISUAL AUTHORITY

Appearance-bearing character images own face identity, facial and body
proportions, character design, stylization, rendering medium, intrinsic
surface and material treatment, intrinsic color, and pattern. The main
background remains the sole scene-content authority while the look reference
transfers only rendering-language attributes.
"""
BINDING = """BEHAVIOR 2

SHOT SOURCE BINDING

Preserve every assigned machine address and apply the verified shot sources.
"""
LONG_POLICY_DERIVED_RESULT = (
    "Use @image1 as the appearance authority for face identity, facial and body "
    "proportions, character design, stylization, rendering medium, intrinsic "
    "surface and material treatment, intrinsic color, and pattern. Use @image3 "
    "as the sole scene-content authority and transfer only the rendering language "
    "from @image4. Integrate the characters into the same environmental lighting, "
    "shadow, reflection, exposure, and atmospheric space without changing their "
    "design. Preserve the requested camera, timing, framing, and occlusion."
)
assert len(" ".join(LONG_POLICY_DERIVED_RESULT.casefold().split())) > 160
VERBATIM_LONG_CLAUSE = " ".join(POLICY.casefold().split()).split(
    "character visual authority", 1
)[1].strip()
assert len(VERBATIM_LONG_CLAUSE) > 160
for removed_name in (
    "_SANITIZER_SECRET_WINDOW_CHARS",
    "_contains_raw_policy_material",
    "_string_contains_raw_policy_window",
    "_compose_policy_collision_retry_prompt",
    "_POLICY_COLLISION_REWRITE_CONTRACT_HEADER",
    "_POLICY_COLLISION_REWRITE_CONTRACT",
    "_HMB_OUTPUT_REWRITE_FAILED_MESSAGE",
    "_AGENT_WRAPPER_KEY_PATTERN",
    "_SANITIZER_MAX_JSON_CHARS",
    "_normalized_leak_text",
    "_secret_heading_signatures",
    "_string_contains_internal_rule_text",
    "_value_contains_protected_headings",
    "_contains_internal_rule_text",
    "_contains_complete_policy_document",
    "_replace_leaked_strings",
    "_strip_internal_rules_from_agent_wrapper",
):
    assert not hasattr(agent, removed_name), removed_name


class PromptSource:
    @staticmethod
    def _hmb_agent_shot_context(_prompt_value):
        return {}


def drive(scripted_output: str):
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

    visible_writes: list[str] = []
    native_calls = [0]
    injected_rulesets: list[list[dict]] = []

    def refresh_route(self, *args, **kwargs):
        self._hmb_verified_prompt_source_node = PromptSource()

    def native_once(self):
        native_calls[0] += 1
        if native_calls[0] > 1:
            raise AssertionError("A policy-text result must not trigger another Agent call.")
        injected_rulesets.append(self.get_parameter_list_value("rulesets"))
        self.parameter_output_values["agent"] = {}
        self.parameter_output_values["output"] = scripted_output
        self.parameter_output_values["logs"] = "private-attempt-log"
        if False:
            yield None
        return "native-result-1"

    def set_visible(self, value: str):
        visible_writes.append(value)
        self.parameter_output_values["output"] = value

    def publish_block(self, message: str):
        self._clear_hmb_runtime_policy()
        self.parameter_output_values["agent"] = {}
        set_visible(self, message)

    node._refresh_agent_shot_route = MethodType(refresh_route, node)
    node._has_canonical_hmb_prompt_connection = MethodType(lambda self: True, node)
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
    node._set_agent_execution_phase = MethodType(lambda self, _phase: None, node)
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
    result = None
    try:
        next(iterator)
    except StopIteration as stop:
        result = stop.value

    return {
        "calls": native_calls[0],
        "visible": visible_writes,
        "output": node.parameter_output_values.get("output"),
        "result": result,
        "snapshot": dict(node._hmb_last_generator_snapshot),
        "injected_rulesets": injected_rulesets,
    }


patched_names = (
    "_paired_machine_prompt",
    "_assert_prompt_policy_identity_matches_signed_runtime",
)
originals = {name: getattr(agent, name) for name in patched_names}
original_bootstrap = agent._hmb._bootstrap_agent_policy_session
try:
    agent._paired_machine_prompt = lambda _node, _value: "MACHINE SHOT FACTS"
    agent._assert_prompt_policy_identity_matches_signed_runtime = lambda: None
    agent._hmb._bootstrap_agent_policy_session = lambda: None

    policy_text = drive(LONG_POLICY_DERIVED_RESULT)
    assert policy_text["calls"] == 1
    assert policy_text["output"] == LONG_POLICY_DERIVED_RESULT
    assert policy_text["visible"] == [LONG_POLICY_DERIVED_RESULT]
    assert len(policy_text["injected_rulesets"]) == 1
    injected = policy_text["injected_rulesets"][0]
    assert len(injected) == 2
    assert injected[0]["name"] != injected[1]["name"]
    assert injected[0]["rules"] == [
        "project-1", "project-2", "project-3", "project-4"
    ]
    assert injected[1]["rules"] == [
        "shot-1", "shot-2", "shot-3", "shot-4"
    ]

    verbatim_clause = drive(VERBATIM_LONG_CLAUSE)
    assert verbatim_clause["calls"] == 1
    assert verbatim_clause["output"] == VERBATIM_LONG_CLAUSE
    assert verbatim_clause["visible"] == [VERBATIM_LONG_CLAUSE]

    complete_document = drive(f"{POLICY}\n{BINDING}")
    assert complete_document["calls"] == 1
    assert complete_document["output"] == agent._PUBLIC_OUTPUT_BLOCKED
    assert complete_document["visible"] == [agent._PUBLIC_OUTPUT_BLOCKED]
    assert complete_document["snapshot"] == {}
finally:
    for name, value in originals.items():
        setattr(agent, name, value)
    agent._hmb._bootstrap_agent_policy_session = original_bootstrap


native_guard_source = inspect.getsource(agent.HMBAgentLibrary._run_native_agent_once)
assert "if call_index >= 1" in native_guard_source
assert "rewrite_retry" not in native_guard_source
assert "call_index == 1" not in native_guard_source

print(
    "HMB Agent signed-policy injection / exact-document no-exposure / "
    "no-retry regression: PASS"
)
