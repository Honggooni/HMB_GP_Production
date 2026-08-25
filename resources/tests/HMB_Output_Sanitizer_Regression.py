from pathlib import Path
import importlib.util
import json
import os
import random
import sys
import tempfile
import types

from _hmb_private_policy_fixture import install_private_policy_reader

ROOT = Path(__file__).resolve().parents[2]
SEALED_TEST_FRAGMENT = ""


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
        self.intermediate_override = None
        self.output_override = None
        self.nested_output_override = None
        self.shown_messages = []
        self.hidden_messages = []
        for name, value in (
            ("prompt", ""),
            ("additional_context", ""),
            ("include_details", True),
            ("rulesets", []),
            ("tools", []),
            ("agent_memory", {}),
            ("output_schema", None),
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
        self.captured_additional_context = self.get_parameter_value(
            "additional_context"
        )
        self.captured_include_details = self.get_parameter_value("include_details")
        self.captured_agent_memory = self.get_parameter_value("agent_memory")
        self.captured_agent_input = self.get_parameter_value("agent")
        self.captured_output_schema = self.get_parameter_value("output_schema")
        self.captured_tools = self.get_parameter_list_value("tools")
        if self.intermediate_override is not None:
            yield self.intermediate_override
        output = "FINAL ENGLISH OUTPUT"
        if self.emit_hidden_rule:
            output = f"{SEALED_TEST_FRAGMENT} leaked"
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
                    "runs": [
                        {
                            "output": {
                                "value": (
                                    self.nested_output_override
                                    if self.nested_output_override is not None
                                    else output
                                )
                            }
                        }
                    ],
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


def drive_scheduler(generator):
    """Run the host's callable-yield/send contract without a live model."""

    yielded = []
    try:
        pending = next(generator)
        while True:
            assert callable(pending)
            yielded.append(pending)
            pending = generator.send(pending())
    except StopIteration:
        return yielded


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
install_private_policy_reader(module._hmb)
_sealed_policy, _sealed_binding = module._hmb._load_verified_behavior_documents()
SEALED_TEST_FRAGMENT = module._split_behavior_rules(_sealed_policy, 4)[0].splitlines()[0]
assert SEALED_TEST_FRAGMENT

# Runtime activation is graph provenance, not a recognizable payload string.
# This isolated regression has no host graph, so mark only the instances that
# represent the canonical HMBPromptLibrary.PROMPT_OUT -> Agent.prompt edge.
module.HMBAgentLibrary._has_canonical_hmb_prompt_connection = (
    lambda self: bool(getattr(self, "_test_canonical_hmb_prompt", False))
)


def canonical_hmb_agent():
    instance = module.HMBAgentLibrary()
    instance._test_canonical_hmb_prompt = True
    # This sanitizer-focused host double has no real Prompt node or paired
    # snapshot. Feed the same validated machine package through the router-owned
    # hidden input and keep snapshot verification covered by its dedicated
    # regressions.
    instance.set_parameter_value(
        module._AGENT_SHOT_PROMPT_INPUT_PARAMETER,
        hmb_payload,
    )
    instance._refresh_agent_shot_route = types.MethodType(
        lambda _self, strict=False: {},
        instance,
    )
    instance._refresh_routed_prompt_preview = types.MethodType(
        lambda _self: None,
        instance,
    )
    instance._assert_exact_prompt_shot_route = types.MethodType(
        lambda _self: {"enabled": False},
        instance,
    )
    instance._adopt_verified_execution_shot_binding = types.MethodType(
        lambda _self, _subscription: None,
        instance,
    )
    return instance

hmb_payload = "\n".join(
    (
        "HMB_GP_Production",
        module._PUBLIC_JOB_CONTRACT_HEADER,
        json.dumps(
            {
                "schema": module._PUBLIC_JOB_CONTRACT_SCHEMA,
                "version": module._PUBLIC_JOB_CONTRACT_VERSION,
                "images": [],
                "videos": [],
                "control_only_bindings": [],
                "frame_ranges": [],
                "connections": {"image_asset": False, "picker": False},
            },
            separators=(",", ":"),
        ),
        module._FX_TIMING_CONTRACT_HEADER,
        json.dumps(
            {
                "schema": module._FX_TIMING_CONTRACT_SCHEMA,
                "version": module._FX_TIMING_CONTRACT_VERSION,
                "valid": True,
                "errors": [],
                "sources": [],
            },
            separators=(",", ":"),
        ),
        module._USER_DESCRIPTION_DATA_HEADER,
        "{}",
    )
)
visible_prompt = "Describe the selected shot in production-ready English."

module._paired_machine_prompt = lambda _node, prompt_value: str(prompt_value or "")

SIGNED_V4_PROMPT_IDENTITY = (
    str(module._hmb._AGENT_POLICY_VERSION),
    str(module._hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
)
actual_prompt_identity_reader = module._prompt_policy_source_identity
actual_prompt_identity = actual_prompt_identity_reader()
assert actual_prompt_identity == SIGNED_V4_PROMPT_IDENTITY

# A compiler version label is audit metadata, but a changed stable contract
# must fail before loading or executing the signed runtime.
module._prompt_policy_source_identity = lambda _source_path=None: (
    SIGNED_V4_PROMPT_IDENTITY[0] + ".1",
    "0" * 64,
)
identity_mismatch = canonical_hmb_agent()
identity_mismatch.set_parameter_value("prompt", visible_prompt)
try:
    list(identity_mismatch.process())
except RuntimeError as exc:
    assert exc.__cause__ is None
    assert str(exc) == module._HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
else:
    raise AssertionError("A synthetic Prompt/runtime contract mismatch was accepted.")
assert identity_mismatch.native_calls == 0
assert identity_mismatch.parameter_output_values["agent"] == {}
assert identity_mismatch.parameter_output_values["output"] == (
    module._HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
)


def synthetic_signed_v4_prompt_identity(_source_path=None):
    """Explicit test-only identity for the signed-v4 sanitizer fixture."""

    return SIGNED_V4_PROMPT_IDENTITY


module._prompt_policy_source_identity = synthetic_signed_v4_prompt_identity
assert module._assert_prompt_policy_identity_matches_signed_runtime() == (
    SIGNED_V4_PROMPT_IDENTITY
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
node.set_parameter_value("prompt", visible_prompt)
node.set_parameter_value("additional_context", "CALLER CONTEXT")
node.set_parameter_value("rulesets", ["USER RULE"])
node.set_parameter_value("tools", ["SIDE EFFECT TOOL"])
node.set_parameter_value("agent_memory", {"runs": [{"input": "before", "output": "before"}]})
node.set_parameter_value("agent", {"conversation_memory": {"runs": ["before"]}})
node.set_parameter_value("output_schema", {"description": "CALLER SCHEMA"})
list(node.process())

assert node.native_calls == 1
assert node.get_parameter_value("prompt") == visible_prompt
assert node.get_parameter_value("additional_context") == "CALLER CONTEXT"
assert node.get_parameter_value("rulesets") == ["USER RULE"]
assert node.get_parameter_value("tools") == ["SIDE EFFECT TOOL"]
assert node.get_parameter_value("agent_memory") == {"runs": [{"input": "before", "output": "before"}]}
assert len(node.captured_rules) == 2
assert node.captured_additional_context == ""
assert node.captured_include_details is False
assert node.captured_agent_memory == {}
assert node.captured_agent_input is None
assert node.captured_output_schema is None
assert node.captured_tools == []
expected_project_rules = module._split_behavior_rules(_sealed_policy, 4)
expected_shot_rules = module._split_behavior_rules(_sealed_binding, 4)
captured_names = [str(ruleset.get("name", "")) for ruleset in node.captured_rules]
assert len(set(captured_names)) == 2
assert all(
    len(name) == 32
    and all(character in "0123456789abcdef" for character in name)
    for name in captured_names
)
assert node.captured_rules[0]["rules"] == expected_project_rules
assert node.captured_rules[1]["rules"] == expected_shot_rules
assert len(node.captured_rules[0]["rules"]) == 4
assert len(node.captured_rules[1]["rules"]) == 4
assert node.parameter_output_values["output"] == "FINAL ENGLISH OUTPUT"
# The public Agent wrapper is chain state only. All active rule containers are
# scrubbed after the native call, including the caller's ruleset copy.
assert node.parameter_output_values["agent"]["rulesets"] == []
assert "conversation_memory" in node.parameter_output_values["agent"]["agent"]
assert node._hmb_policy == ""
assert node._hmb_binding == ""
assert node._hmb_policy_rules == []
assert node._hmb_binding_rules == []
assert node._hmb_ruleset_names == ("", "")

# Native streaming/progress values stay buffered until final publication. The
# lightweight client no longer inspects policy wording in the completed log.
intermediate_leak = canonical_hmb_agent()


def publish_intermediate_leak():
    intermediate_leak.append_value_to_parameter("output", SEALED_TEST_FRAGMENT)
    intermediate_leak.append_value_to_parameter("logs", SEALED_TEST_FRAGMENT)
    return {"private": SEALED_TEST_FRAGMENT}


intermediate_leak.intermediate_override = publish_intermediate_leak
intermediate_leak.set_parameter_value("prompt", visible_prompt)
assert len(drive_scheduler(intermediate_leak.process())) == 1
assert intermediate_leak.parameter_output_values["output"] == "FINAL ENGLISH OUTPUT"
assert intermediate_leak.parameter_output_values.get("logs", "") == (
    SEALED_TEST_FRAGMENT
)
assert intermediate_leak._hmb_policy == ""

standalone = module.HMBAgentLibrary()
standalone.set_parameter_value("prompt", "ordinary standalone prompt")
standalone.set_parameter_value("additional_context", "CALLER CONTEXT")
standalone.set_parameter_value("rulesets", ["USER RULE"])
standalone.set_parameter_value("tools", ["SIDE EFFECT TOOL"])
standalone.set_parameter_value("agent_memory", {"runs": ["before"]})
standalone.intermediate_override = "ordinary native progress"
assert list(standalone.process()) == ["ordinary native progress"]
assert standalone.native_calls == 1
assert standalone.captured_rules == ["USER RULE"]
assert standalone.captured_additional_context == "CALLER CONTEXT"
assert standalone.captured_include_details is True
assert standalone.captured_tools == ["SIDE EFFECT TOOL"]
assert standalone.captured_agent_memory == {"runs": ["before"]}
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
leak.set_parameter_value("prompt", visible_prompt)
list(leak.process())
assert leak.native_calls == 1
assert leak.parameter_output_values["output"] == f"{SEALED_TEST_FRAGMENT} leaked"
assert not leak.parameter_output_values["agent"]["rulesets"]
assert SEALED_TEST_FRAGMENT in str(leak.parameter_output_values["agent"])


# The lightweight public boundary does not parse text, including JSON, Python
# repr, or a runtime-scope echo. Protected native output publication itself is
# string-valued; direct state objects are scrubbed on the separate Agent port.
for serialized_output in (
    '{"agent":{"type":"GriptapeNodesAgent","conversation_memory":{"runs":[]}}}',
    '{"system":"internal prompt","rulesets":[]}',
    "{'conversation_memory': {'runs': []}}",
    '"{\\"agent\\":{\\"type\\":\\"GriptapeNodesAgent\\"}}"',
):
    boundary = canonical_hmb_agent()
    boundary.output_override = serialized_output
    boundary.set_parameter_value("prompt", visible_prompt)
    list(boundary.process())
    assert boundary.parameter_output_values["output"] == serialized_output

structured_boundary = canonical_hmb_agent()
structured_boundary.output_override = {"agent": {"type": "GriptapeNodesAgent"}}
structured_boundary.set_parameter_value("prompt", visible_prompt)
list(structured_boundary.process())
assert structured_boundary.parameter_output_values["output"] == str(
    structured_boundary.output_override
)

benign_json = canonical_hmb_agent()
benign_json.output_override = '{"shot":"e101s001c001","final_prompt":"keep exact motion"}'
benign_json.set_parameter_value("prompt", visible_prompt)
list(benign_json.process())
assert benign_json.parameter_output_values["output"] == benign_json.output_override

# Runtime-scope text is also no longer inspected at the public string boundary.
runtime_scope_echo = canonical_hmb_agent()
runtime_scope_echo.output_override = (
    f"{module._RUNTIME_FX_SCOPE_HEADER}\n"
    '{"shared_windows":[{"window_id":"runtime-shared-1"}]}'
)
runtime_scope_echo.set_parameter_value("prompt", visible_prompt)
list(runtime_scope_echo.process())
assert runtime_scope_echo.parameter_output_values["output"] == (
    runtime_scope_echo.output_override
)

runtime_memory = {
    "conversation_memory": {
        "runs": [
            {
                "input": (
                    f"{hmb_payload}\n{module._RUNTIME_FX_SCOPE_HEADER}\n"
                    '{"shared_windows":[{"window_id":"runtime-shared-1"}]}'
                )
            }
        ]
    }
}
module._strip_runtime_scope_from_agent_wrapper(runtime_memory)
assert runtime_memory["conversation_memory"]["runs"][0]["input"] == hmb_payload
assert module._RUNTIME_FX_SCOPE_HEADER not in json.dumps(runtime_memory)

sealed_state = {
    "rulesets": ["SERVER POLICY"],
    "system": "PRIVATE SYSTEM STATE",
    "nested": {"instructions": "PRIVATE INSTRUCTIONS"},
}
module._strip_sealed_state_from_agent_wrapper(sealed_state)
assert sealed_state["rulesets"] == []
assert sealed_state["system"] == module._PUBLIC_OUTPUT_BLOCKED
assert sealed_state["nested"]["instructions"] == module._PUBLIC_OUTPUT_BLOCKED

# Deterministic probabilistic cross-check: directly supplied internal structures
# remain detectable through randomized nesting, while serialized JSON and
# ordinary generator payloads are not interpreted by this lightweight boundary.
rng = random.Random(20260730)


state_keys = tuple(sorted(module._PUBLIC_OUTPUT_STATE_KEYS))
for case_index in range(4096):
    state_key = rng.choice(state_keys)
    leaked_value = {state_key: {"case": case_index, "runs": []}}
    if state_key in module._GENERIC_AGENT_STATE_KEYS:
        companion_key = "messages" if state_key != "messages" else "memory"
        leaked_value[companion_key] = []
    for _ in range(rng.randint(0, 5)):
        leaked_value = rng.choice(
            (
                {"payload": leaked_value},
                {"result": [leaked_value]},
                [leaked_value, {"case": case_index}],
            )
        )
    assert module._contains_public_output_state_leak(leaked_value)
    serialized_leak = json.dumps(leaked_value, ensure_ascii=False)
    assert not module._contains_public_output_state_leak(serialized_leak)
    assert not module._contains_public_output_state_leak(
        json.dumps(serialized_leak, ensure_ascii=False)
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
    assert not module._contains_public_output_state_leak(benign_value)
    assert not module._contains_public_output_state_leak(
        json.dumps(benign_value, ensure_ascii=False)
    )


# Sanitizer failure is fail-closed, and native exception details are replaced
# by the fixed public execution diagnostic.
sanitizer_failure = canonical_hmb_agent()
sanitizer_failure.set_parameter_value("prompt", visible_prompt)
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
sanitizer_failure_after_native_error.set_parameter_value("prompt", visible_prompt)
sanitizer_failure_after_native_error._secure_hmb_outputs = types.MethodType(
    lambda _self: (_ for _ in ()).throw(RuntimeError("simulated sanitizer failure")),
    sanitizer_failure_after_native_error,
)
try:
    list(sanitizer_failure_after_native_error.process())
except RuntimeError as exc:
    assert str(exc) == module._HMB_EXECUTION_FAILED_MESSAGE
else:
    raise AssertionError("The protected native failure did not fail closed.")
assert sanitizer_failure_after_native_error._hmb_policy == ""

# A native exception after publishing a partial wrapper must still execute the
# finally-path sanitizer before the exception escapes.
exceptional = canonical_hmb_agent()
exceptional.emit_hidden_rule = True
exceptional.raise_after_publish = True
exceptional.set_parameter_value("prompt", visible_prompt)
try:
    list(exceptional.process())
except RuntimeError as exc:
    assert str(exc) == module._HMB_EXECUTION_FAILED_MESSAGE
else:
    raise AssertionError("The protected native failure did not fail closed.")
assert exceptional.native_calls == 1
assert exceptional._hmb_rules_active is False
assert exceptional.parameter_output_values["output"] == (
    module._HMB_EXECUTION_FAILED_MESSAGE
)
assert exceptional.parameter_output_values["agent"] == {}
assert SEALED_TEST_FRAGMENT not in str(exceptional.parameter_output_values["agent"])

for obsolete in ("PROJECT", "project", "episode", "shot", "projects_root", "project_load_path", "Task"):
    assert obsolete not in node.parameters

module._prompt_policy_source_identity = actual_prompt_identity_reader

print("HMB native single-execution and runtime-state protection regression: PASS")
