from pathlib import Path
import importlib.util
import json
import os
import random
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]


class Parameter:
    def __init__(self, name, default_value=None):
        self.name = name
        self.default_value = default_value
        self.ui_options = {}


class Agent:
    def __init__(self, **kwargs):
        self.parameters = {}
        self.parameter_output_values = {}
        self.native_calls = 0
        self.emit_hidden_rule = False
        self.raise_after_publish = False
        self.output_override = None
        self.shown_messages = []
        self.hidden_messages = []
        for name, value in (
            ("prompt", ""),
            ("rulesets", []),
            ("agent_memory", {}),
            ("output", ""),
            ("agent", {}),
        ):
            self.add_parameter(Parameter(name, value))

    def add_parameter(self, parameter):
        self.parameters[parameter.name] = parameter

    def get_parameter_by_name(self, name):
        return self.parameters.get(name)

    def get_parameter_value(self, name):
        return self.parameters[name].default_value

    def set_parameter_value(self, name, value):
        if name in self.parameters:
            self.parameters[name].default_value = value
        self.parameter_output_values[name] = value

    def get_parameter_list_value(self, name):
        return list(self.parameters[name].default_value or [])

    def show_message_by_name(self, name):
        self.shown_messages.append(name)

    def hide_message_by_name(self, name):
        self.hidden_messages.append(name)

    def process(self):
        self.native_calls += 1
        rules = self.get_parameter_list_value("rulesets")
        self.captured_rules = list(rules)
        output = "FINAL ENGLISH OUTPUT"
        if self.emit_hidden_rule:
            output = "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE leaked"
        if self.output_override is not None:
            output = self.output_override
        self.set_parameter_value("output", output)
        configs = []
        string_index = 0
        for rule in rules:
            if isinstance(rule, dict):
                configs.append(rule)
            else:
                string_index += 1
                configs.append({"name": f"behavior_{string_index}", "rules": [str(rule)]})
        self.parameter_output_values["agent"] = {
            "agent": {
                "conversation_memory": {
                    "runs": [{"output": {"value": output}}],
                }
            },
            "tools": [],
            "rulesets": configs,
        }
        if self.raise_after_publish:
            raise RuntimeError("simulated native Agent failure after partial publication")
        if False:
            yield None
        return None


Agent.__name__ = "Agent"
package = types.ModuleType("griptape_nodes_library")
package.__path__ = []
agents_package = types.ModuleType("griptape_nodes_library.agents")
agents_package.__path__ = []
agent_module = types.ModuleType("griptape_nodes_library.agents.agent")
agent_module.Agent = Agent
_standard_library_temp = tempfile.TemporaryDirectory()
_canonical_agent_file = (
    Path(_standard_library_temp.name)
    / "griptape_nodes_library"
    / "agents"
    / "agent.py"
)
_canonical_agent_file.parent.mkdir(parents=True)
_canonical_agent_file.write_text("# canonical test Agent module\n", encoding="utf-8")
agent_module.__file__ = str(_canonical_agent_file)
os.environ["HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"] = _standard_library_temp.name
sys.modules["griptape_nodes_library"] = package
sys.modules["griptape_nodes_library.agents"] = agents_package
sys.modules["griptape_nodes_library.agents.agent"] = agent_module

spec = importlib.util.spec_from_file_location("HMBAgentLibrary_regression", ROOT / "HMBAgentLibrary.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

# Runtime activation is graph provenance, not a recognizable payload string.
# This isolated regression has no host graph, so mark only the instances that
# represent the canonical HMBPromptLibrary.PROMPT_OUT -> Agent.prompt edge.
module.HMBAgentLibrary._has_canonical_hmb_prompt_connection = (
    lambda self: bool(getattr(self, "_test_canonical_hmb_prompt", False))
)


def canonical_hmb_agent():
    instance = module.HMBAgentLibrary()
    instance._test_canonical_hmb_prompt = True
    return instance

hmb_payload = """HMB_GP_Production
TARGET GENERATOR:
Active downstream generator
IMAGE SOURCE:
@image1 = 제이민
IMAGE ROLE MAP:
제이민 / Approved final appearance source = @image1
REPLACEMENT BINDING:
제이민
VIDEO SOURCE:
No video source assigned in HMBPromptLibrary.
"""

EXPECTED_V3_POLICY_IDENTITY = (
    "2026-08-06.animation-look-continuity.v3",
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93",
)
SIGNED_RUNTIME_POLICY_IDENTITY = (
    str(module._hmb._AGENT_POLICY_VERSION),
    str(module._hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
)
actual_prompt_identity_reader = module._prompt_policy_source_identity
actual_prompt_identity = actual_prompt_identity_reader()
assert SIGNED_RUNTIME_POLICY_IDENTITY == EXPECTED_V3_POLICY_IDENTITY
assert actual_prompt_identity == EXPECTED_V3_POLICY_IDENTITY
assert module._assert_prompt_policy_identity_matches_signed_runtime() == (
    EXPECTED_V3_POLICY_IDENTITY
)

# A stale or partially updated Prompt compiler must fail before loading or
# executing the signed v3 runtime.
def synthetic_stale_prompt_identity(_source_path=None):
    return (
        "2026-08-01.goal-final-authority.v2",
        "0" * 64,
    )


module._prompt_policy_source_identity = synthetic_stale_prompt_identity
identity_mismatch = canonical_hmb_agent()
identity_mismatch.set_parameter_value("prompt", hmb_payload)
try:
    list(identity_mismatch.process())
except RuntimeError as exc:
    assert exc.__cause__ is None
    assert str(exc) == module._HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
else:
    raise AssertionError("A stale Prompt/signed-v3 runtime mismatch was accepted.")
assert identity_mismatch.native_calls == 0
assert identity_mismatch.parameter_output_values["agent"] == {}
assert identity_mismatch.parameter_output_values["output"] == (
    module._HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
)

module._prompt_policy_source_identity = actual_prompt_identity_reader
assert module._assert_prompt_policy_identity_matches_signed_runtime() == (
    EXPECTED_V3_POLICY_IDENTITY
)

node = canonical_hmb_agent()
assert module._AGENT_WIDGET_PARAMETER in node.parameters
assert node.get_parameter_by_name("output").ui_options["display_name"] == (
    "FINAL TEXT · GENERATOR"
)
assert node.get_parameter_by_name("agent").ui_options["display_name"] == (
    "AGENT STATE · CHAIN ONLY"
)
assert "Display Text" in node.get_parameter_by_name("agent").ui_options["tooltip"]

# A state-to-display connection receives a warning without deleting, rewiring,
# renaming, or retyping either endpoint. Native Agent-to-Agent chaining stays
# warning-free, and removing the invalid edge clears the advisory.
agent_source = node.get_parameter_by_name("agent")
agent_source.output_types = ["Agent"]
display_target = Parameter("text", "")
display_target.input_types = ["any"]
chain_target = Parameter("agent", {})
chain_target.input_types = ["Agent"]
original_source_name = agent_source.name
original_source_types = list(agent_source.output_types)
node.after_outgoing_connection(agent_source, object(), display_target)
assert node.shown_messages == [module._AGENT_STATE_WARNING_NAME]
assert agent_source.name == original_source_name
assert agent_source.output_types == original_source_types
assert display_target.name == "text"
assert display_target.input_types == ["any"]
node.after_outgoing_connection(agent_source, object(), chain_target)
assert node.shown_messages == [module._AGENT_STATE_WARNING_NAME]
node.after_outgoing_connection_removed(agent_source, object(), display_target)
assert node.hidden_messages == [module._AGENT_STATE_WARNING_NAME]

agent_widget_parameter = node.get_parameter_by_name(module._AGENT_WIDGET_PARAMETER)
assert agent_widget_parameter.ui_options["height"] == 64
assert agent_widget_parameter.ui_options["expandable"] is False
assert agent_widget_parameter.ui_options["resizable"] is False
# Saved workflows may restore the former expandable setting. The deserialize
# lifecycle must normalize it so the native controls move directly below the
# compact HMB header instead of leaving a large black spacer.
agent_widget_parameter.ui_options["expandable"] = True
node.get_parameter_by_name("output").ui_options["display_name"] = "output"
node.get_parameter_by_name("agent").ui_options["display_name"] = "agent"
node.after_deserialize()
assert agent_widget_parameter.ui_options["expandable"] is False
assert node.get_parameter_by_name("output").ui_options["display_name"] == (
    "FINAL TEXT · GENERATOR"
)
assert node.get_parameter_by_name("agent").ui_options["display_name"] == (
    "AGENT STATE · CHAIN ONLY"
)
assert "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE" not in str(
    node.get_parameter_value(module._AGENT_WIDGET_PARAMETER)
)
node.set_parameter_value("prompt", hmb_payload)
node.set_parameter_value("rulesets", ["USER RULE"])
node.set_parameter_value("agent_memory", {"runs": [{"input": "before", "output": "before"}]})
list(node.process())

assert node.native_calls == 1
assert node.get_parameter_value("prompt") == hmb_payload
assert node.get_parameter_value("rulesets") == ["USER RULE"]
assert node.get_parameter_value("agent_memory") == {"runs": [{"input": "before", "output": "before"}]}
assert len(node.captured_rules) == 3
expected_project_rules = module._split_behavior_rules(module.get_internal_policy_rules(), 4)
expected_shot_rules = module._split_behavior_rules(module.get_internal_binding_rules(), 4)
assert node.captured_rules[0] == {
    "name": "hmb_project_behavior",
    "rules": expected_project_rules,
}
assert node.captured_rules[1] == {
    "name": "hmb_shot_behavior",
    "rules": expected_shot_rules,
}
assert len(node.captured_rules[0]["rules"]) == 4
assert len(node.captured_rules[1]["rules"]) == 4
assert node.captured_rules[2] == "USER RULE"
assert node.parameter_output_values["output"] == "FINAL ENGLISH OUTPUT"
assert node.parameter_output_values["agent"]["rulesets"] == [
    {"name": "behavior_1", "rules": ["USER RULE"]}
]
assert "conversation_memory" in node.parameter_output_values["agent"]["agent"]
assert node._hmb_policy == ""
assert node._hmb_binding == ""
assert node._hmb_policy_rules == []
assert node._hmb_binding_rules == []
assert node._hmb_goal_first_rules == []

standalone = module.HMBAgentLibrary()
standalone.set_parameter_value("prompt", "ordinary standalone prompt")
standalone.set_parameter_value("rulesets", ["USER RULE"])
list(standalone.process())
assert standalone.native_calls == 1
assert standalone.captured_rules == ["USER RULE"]
assert standalone.parameter_output_values["agent"]["rulesets"] == [
    {"name": "behavior_1", "rules": ["USER RULE"]}
]

# Standalone/direct-source execution is the untouched Standard Library Agent.
# With no HMBPromptLibrary package there is no HMB policy, injection, or output
# scrub, including when the user's ordinary response happens to use HMB-reserved
# words as plain JSON keys.
standalone_json = module.HMBAgentLibrary()
standalone_json.output_override = '{"system":"user-requested standalone JSON"}'
standalone_json.set_parameter_value("prompt", "ordinary standalone prompt")
list(standalone_json.process())
assert standalone_json.parameter_output_values["output"] == standalone_json.output_override

for direct_payload in (
    hmb_payload,
    '{"schema":"hmb-image-asset-library-binding","ordered_images":[{"image_name":"Idea"}]}',
    '{"schema":"hmb-video-picker-output","videos":[{"video_slot":2,"path":"motion.mp4"}]}',
):
    direct = module.HMBAgentLibrary()
    direct.set_parameter_value("prompt", direct_payload)
    list(direct.process())
    assert direct.native_calls == 1
    assert direct.captured_rules == []
    assert direct.parameter_output_values["output"] == "FINAL ENGLISH OUTPUT"
    assert direct.parameter_output_values["agent"]["rulesets"] == []

leak = canonical_hmb_agent()
leak.emit_hidden_rule = True
leak.set_parameter_value("prompt", hmb_payload)
list(leak.process())
assert leak.native_calls == 1
assert leak.parameter_output_values["output"] == module._PUBLIC_OUTPUT_BLOCKED
assert not leak.parameter_output_values["agent"]["rulesets"]
assert "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE" not in str(leak.parameter_output_values["agent"])

# Hidden Behavior text must also be removed from nested Agent wrapper data even
# when the visible output itself is clean.
nested = canonical_hmb_agent()
nested.set_parameter_value("prompt", hmb_payload)
list(nested.process())
nested.parameter_output_values["agent"]["agent"]["conversation_memory"]["runs"][0]["output"]["value"] = (
    "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE leaked in wrapper only"
)
nested._secure_hmb_outputs()
assert nested.parameter_output_values["output"] == "FINAL ENGLISH OUTPUT"
assert "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE" not in str(nested.parameter_output_values["agent"])
assert "[HMB OUTPUT BLOCKED]" in str(nested.parameter_output_values["agent"])

# Public output must never expose a native Agent envelope or its sensitive state
# keys. Benign JSON remains a valid model final response.
for leaked_output in (
    '{"agent":{"type":"GriptapeNodesAgent","conversation_memory":{"runs":[]}}}',
    '{"system":"internal prompt","rulesets":[]}',
    "{'conversation_memory': {'runs': []}}",
    '"{\\"agent\\":{\\"type\\":\\"GriptapeNodesAgent\\"}}"',
    {"agent": {"type": "GriptapeNodesAgent"}},
):
    boundary = canonical_hmb_agent()
    boundary.output_override = leaked_output
    boundary.set_parameter_value("prompt", hmb_payload)
    list(boundary.process())
    assert boundary.parameter_output_values["output"] == module._PUBLIC_OUTPUT_BLOCKED

benign_json = canonical_hmb_agent()
benign_json.output_override = '{"shot":"e101s001c001","final_prompt":"keep exact motion"}'
benign_json.set_parameter_value("prompt", hmb_payload)
list(benign_json.process())
assert benign_json.parameter_output_values["output"] == benign_json.output_override

# Deterministic probabilistic cross-check: internal state remains detectable
# through randomized nesting and one/two JSON encodings, while ordinary
# generator payloads with similar structural depth remain valid.
rng = random.Random(20260730)
policy_text = module.get_internal_policy_rules()
binding_text = module.get_internal_binding_rules()
state_keys = tuple(sorted(module._PUBLIC_OUTPUT_STATE_KEYS))
for case_index in range(4096):
    state_key = rng.choice(state_keys)
    leaked_value = {state_key: {"case": case_index, "runs": []}}
    for _ in range(rng.randint(0, 5)):
        leaked_value = rng.choice(
            (
                {"payload": leaked_value},
                {"result": [leaked_value]},
                [leaked_value, {"case": case_index}],
            )
        )
    if rng.random() < 0.75:
        leaked_value = json.dumps(leaked_value, ensure_ascii=False)
    if rng.random() < 0.35:
        leaked_value = json.dumps(leaked_value, ensure_ascii=False)
    assert module._contains_public_output_state_leak(
        leaked_value,
        policy_text,
        binding_text,
    )

    benign_value = {
        "shot": f"e{rng.randint(100, 999)}s{rng.randint(1, 999):03d}c001",
        "final_prompt": f"preserve motion case {case_index}",
        "frames": [rng.randint(1, 100), rng.randint(101, 9999)],
        "roles": [{"name": "hero", "source": f"@image{rng.randint(1, 50)}"}],
    }
    for _ in range(rng.randint(0, 4)):
        benign_value = rng.choice(
            (
                {"payload": benign_value},
                {"result": [benign_value]},
                [benign_value, {"case": case_index}],
            )
        )
    if rng.random() < 0.75:
        benign_value = json.dumps(benign_value, ensure_ascii=False)
    assert not module._contains_public_output_state_leak(
        benign_value,
        policy_text,
        binding_text,
    )

# Cyclic and adversarially deep host values are bounded without RecursionError.
cyclic_benign = {"shot": "e101s001c001"}
cyclic_benign["self"] = cyclic_benign
assert not module._mapping_contains_agent_state(cyclic_benign)
assert not module._contains_internal_rule_text(cyclic_benign, policy_text, binding_text)

cyclic_leak = {"conversation_memory": {"runs": []}}
cyclic_leak["self"] = cyclic_leak
assert module._mapping_contains_agent_state(cyclic_leak)

cyclic_wrapper = []
cyclic_wrapper.append(cyclic_wrapper)
cyclic_wrapper.append("PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE leaked")
scrubbed_cycle = module._replace_leaked_strings(
    cyclic_wrapper,
    policy_text,
    binding_text,
    module._PUBLIC_OUTPUT_BLOCKED,
)
assert scrubbed_cycle[0] == module._PUBLIC_OUTPUT_BLOCKED
assert scrubbed_cycle[1] == module._PUBLIC_OUTPUT_BLOCKED

tuple_cycle_list = []
tuple_cycle = (
    tuple_cycle_list,
    "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE leaked through tuple cycle",
)
tuple_cycle_list.append(tuple_cycle)
scrubbed_tuple_cycle = module._replace_leaked_strings(
    tuple_cycle,
    policy_text,
    binding_text,
    module._PUBLIC_OUTPUT_BLOCKED,
)
assert "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE" not in str(scrubbed_tuple_cycle)

deep_value = {"leaf": "safe"}
for _ in range(1_100):
    deep_value = {"payload": deep_value}
assert module._mapping_contains_agent_state(deep_value)
assert module._contains_internal_rule_text(deep_value, policy_text, binding_text)
module._replace_leaked_strings(
    deep_value,
    policy_text,
    binding_text,
    module._PUBLIC_OUTPUT_BLOCKED,
)

# A future sanitizer regression must not replace the native return/exception.
sanitizer_failure = canonical_hmb_agent()
sanitizer_failure.set_parameter_value("prompt", hmb_payload)
sanitizer_failure._secure_hmb_outputs = types.MethodType(
    lambda _self: (_ for _ in ()).throw(RuntimeError("simulated sanitizer failure")),
    sanitizer_failure,
)
list(sanitizer_failure.process())
assert sanitizer_failure.native_calls == 1
assert sanitizer_failure.parameter_output_values["output"] == module._PUBLIC_OUTPUT_BLOCKED
assert sanitizer_failure._hmb_policy == ""

sanitizer_failure_after_native_error = canonical_hmb_agent()
sanitizer_failure_after_native_error.raise_after_publish = True
sanitizer_failure_after_native_error.set_parameter_value("prompt", hmb_payload)
sanitizer_failure_after_native_error._secure_hmb_outputs = types.MethodType(
    lambda _self: (_ for _ in ()).throw(RuntimeError("simulated sanitizer failure")),
    sanitizer_failure_after_native_error,
)
try:
    list(sanitizer_failure_after_native_error.process())
except RuntimeError as exc:
    assert "simulated native Agent failure" in str(exc)
else:
    raise AssertionError("The native Agent failure was masked or lost.")
assert sanitizer_failure_after_native_error._hmb_policy == ""

# A native exception after publishing a partial wrapper must still execute the
# finally-path sanitizer before the exception escapes.
exceptional = canonical_hmb_agent()
exceptional.emit_hidden_rule = True
exceptional.raise_after_publish = True
exceptional.set_parameter_value("prompt", hmb_payload)
try:
    list(exceptional.process())
except RuntimeError as exc:
    assert "simulated native Agent failure" in str(exc)
else:
    raise AssertionError("The simulated native Agent failure did not escape.")
assert exceptional.native_calls == 1
assert exceptional._hmb_rules_active is False
assert exceptional.parameter_output_values["output"] == module._PUBLIC_OUTPUT_BLOCKED
assert not exceptional.parameter_output_values["agent"]["rulesets"]
assert "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE" not in str(
    exceptional.parameter_output_values["agent"]
)

for obsolete in ("PROJECT", "project", "episode", "shot", "projects_root", "project_load_path", "Task"):
    assert obsolete not in node.parameters

module._prompt_policy_source_identity = actual_prompt_identity_reader

print("HMB native single-execution and hidden-rule protection regression: PASS")
