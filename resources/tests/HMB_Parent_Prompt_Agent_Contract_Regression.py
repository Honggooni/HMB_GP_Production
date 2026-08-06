from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable
import sys


ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    path = ROOT / f"{name}.py"
    module_name = f"_hmb_parent_contract_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


prompt = load("HMBPromptLibrary")
agent = load("HMBAgentLibrary")

# This topology/4+4 behavior test supplies synthetic policy documents, while
# the compiler and sealed runtime identity must remain the real synchronized v3
# release identity.
EXPECTED_V3_POLICY_IDENTITY = (
    "2026-08-06.animation-look-continuity.v3",
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93",
)
SIGNED_RUNTIME_POLICY_IDENTITY = (
    str(agent._hmb._AGENT_POLICY_VERSION),
    str(agent._hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
)
assert SIGNED_RUNTIME_POLICY_IDENTITY == EXPECTED_V3_POLICY_IDENTITY
assert agent._prompt_policy_source_identity() == EXPECTED_V3_POLICY_IDENTITY
assert agent._assert_prompt_policy_identity_matches_signed_runtime() == (
    EXPECTED_V3_POLICY_IDENTITY
)


def make_source(
    source_class: type,
    *,
    name: str = "renamed_parent_prompt",
    library: str = "HMB_GP_Production",
    node_type: str = "HMBPromptLibrary",
):
    source = object.__new__(source_class)
    source.name = name
    source.metadata = {
        "library": library,
        "node_type": node_type,
    }
    return source


def make_edge(
    *,
    source_node_name: str = "renamed_parent_prompt",
    source_parameter_name: str = "PROMPT_OUT",
    target_parameter_name: str = "prompt",
):
    return SimpleNamespace(
        source_node_name=source_node_name,
        source_parameter_name=source_parameter_name,
        target_parameter_name=target_parameter_name,
    )


def direct_contract_result(
    edges: list[Any],
    sources: dict[str, Any],
    *,
    expected_class: Any = None,
    connection_lookup: Callable[..., Any] | None = None,
    node_lookup: Callable[..., Any] | None = None,
    expected_class_lookup: Callable[..., Any] | None = None,
) -> bool:
    target = SimpleNamespace(name="renamed_hmb_agent")
    expected_class = expected_class or prompt.HMBPromptLibrary

    if connection_lookup is None:
        def connection_lookup(parameter_name: str, node_name: str):
            assert parameter_name == "prompt"
            assert node_name == target.name
            return SimpleNamespace(incoming_connections=list(edges))

    if node_lookup is None:
        def node_lookup(node_name: str):
            return sources[node_name]

    if expected_class_lookup is None:
        expected_class_lookup = lambda: expected_class

    return agent._is_direct_hmb_prompt_library_connection(
        target,
        connection_lookup=connection_lookup,
        node_lookup=node_lookup,
        expected_class_lookup=expected_class_lookup,
    )


# The only positive topology is the exact registered class and exact direct
# PROMPT_OUT -> prompt edge. Runtime node names are intentionally irrelevant.
canonical_source = make_source(prompt.HMBPromptLibrary)
canonical_edge = make_edge()
assert direct_contract_result(
    [canonical_edge],
    {canonical_source.name: canonical_source},
)


# No copied text, forged metadata, same-looking class, subclass, wrong library,
# wrong node type, wrong port, intermediary node, or malformed edge set may
# replace the registered HMBPromptLibrary parent.
assert not direct_contract_result([], {})
try:
    direct_contract_result(
        [canonical_edge, canonical_edge],
        {canonical_source.name: canonical_source},
    )
except RuntimeError as exc:
    assert "topology could not be verified" in str(exc)
else:
    raise AssertionError("Ambiguous duplicate Prompt edges were accepted.")
assert not direct_contract_result(
    [make_edge(source_parameter_name="output")],
    {canonical_source.name: canonical_source},
)
assert not direct_contract_result(
    [make_edge(target_parameter_name="additional_context")],
    {canonical_source.name: canonical_source},
)

SameLookingPrompt = type("HMBPromptLibrary", (), {})
same_looking_source = make_source(SameLookingPrompt)
assert not direct_contract_result(
    [canonical_edge],
    {same_looking_source.name: same_looking_source},
)


class PromptSubclass(prompt.HMBPromptLibrary):
    pass


subclass_source = make_source(PromptSubclass)
assert not direct_contract_result(
    [canonical_edge],
    {subclass_source.name: subclass_source},
)

wrong_library_source = make_source(
    prompt.HMBPromptLibrary,
    library="Foreign Prompt Library",
)
assert not direct_contract_result(
    [canonical_edge],
    {wrong_library_source.name: wrong_library_source},
)
wrong_type_source = make_source(
    prompt.HMBPromptLibrary,
    node_type="PromptReplacement",
)
assert not direct_contract_result(
    [canonical_edge],
    {wrong_type_source.name: wrong_type_source},
)

PassThrough = type("PassThrough", (), {})
copied_source = make_source(
    PassThrough,
    library="HMB_GP_Production",
    node_type="HMBPromptLibrary",
)
assert not direct_contract_result(
    [canonical_edge],
    {copied_source.name: copied_source},
)


def raises(*_args: Any, **_kwargs: Any):
    raise RuntimeError("simulated graph lookup failure")


for failing_lookup in (
    {"connection_lookup": raises},
    {"node_lookup": raises},
    {"expected_class_lookup": raises},
    {"expected_class_lookup": lambda: "HMBPromptLibrary"},
):
    try:
        direct_contract_result(
            [canonical_edge],
            {canonical_source.name: canonical_source},
            **failing_lookup,
        )
    except RuntimeError as exc:
        assert "topology could not be verified" in str(exc)
    else:
        raise AssertionError(f"Unverifiable Prompt topology was accepted: {failing_lookup}")
try:
    direct_contract_result(
        [canonical_edge],
        {canonical_source.name: canonical_source},
        connection_lookup=lambda *_args: SimpleNamespace(
            incoming_connections=None
        ),
    )
except RuntimeError as exc:
    assert "topology could not be verified" in str(exc)
else:
    raise AssertionError("Missing Prompt connection data was accepted as native.")
try:
    agent._is_direct_hmb_prompt_library_connection(
        SimpleNamespace(name=""),
        connection_lookup=lambda *_args: SimpleNamespace(
            incoming_connections=[]
        ),
        node_lookup=lambda *_args: None,
        expected_class_lookup=lambda: prompt.HMBPromptLibrary,
    )
except RuntimeError as exc:
    assert "topology could not be verified" in str(exc)
else:
    raise AssertionError("Missing Agent identity was accepted as native.")


policy_document, binding_document = agent.get_internal_policy_documents()
policy_rules = agent._split_behavior_rules(policy_document, 4)
binding_rules = agent._split_behavior_rules(binding_document, 4)


def exercise_agent_route(
    prompt_value: str,
    *,
    direct_prompt_edge: bool,
    policy_failure: bool = False,
) -> tuple[bool, bool, int, int, int, bool, int, int]:
    node = object.__new__(agent.HMBAgentLibrary)
    node._hmb_rules_active = False
    node._hmb_policy = "stale-policy" if policy_failure else ""
    node._hmb_binding = "stale-binding" if policy_failure else ""
    node._hmb_policy_rules = ["stale-project"] if policy_failure else []
    node._hmb_binding_rules = ["stale-shot"] if policy_failure else []
    node._hmb_goal_first_rules = ["stale-goal"] if policy_failure else []
    node._hmb_structured_rules_active = False
    node._hmb_native_calls_this_process = 0
    node.parameter_output_values = {
        "agent": {"stale": True},
        "output": "stale visible output",
    }
    observations: list[tuple[bool, bool, int, int, int]] = []
    secured: list[bool] = []
    policy_loads: list[bool] = []

    def native_once(self):
        observations.append(
            (
                bool(self._hmb_rules_active),
                bool(self._hmb_structured_rules_active),
                len(self._hmb_goal_first_rules),
                len(self._hmb_policy_rules),
                len(self._hmb_binding_rules),
            )
        )
        if False:
            yield None
        return "native-complete"

    def load_rules(_self):
        policy_loads.append(True)
        if policy_failure:
            raise RuntimeError("simulated mandatory policy failure")
        return (
            policy_document,
            binding_document,
            list(policy_rules),
            list(binding_rules),
        )

    node.get_parameter_value = MethodType(
        lambda _self, name: prompt_value if name == "prompt" else None,
        node,
    )
    node._has_canonical_hmb_prompt_connection = MethodType(
        lambda _self: direct_prompt_edge,
        node,
    )
    node._load_hmb_rules = MethodType(load_rules, node)
    node._run_native_agent_once = MethodType(native_once, node)
    node._secure_hmb_outputs = MethodType(
        lambda _self: secured.append(True),
        node,
    )

    iterator = node.process()
    try:
        while True:
            next(iterator)
    except RuntimeError as exc:
        if not policy_failure:
            raise
        assert exc.__cause__ is None
        assert str(exc) == agent._HMB_POLICY_UNAVAILABLE_MESSAGE
        assert observations == []
        assert node._hmb_native_calls_this_process == 0
        assert node.parameter_output_values == {
            "agent": {},
            "output": agent._HMB_POLICY_UNAVAILABLE_MESSAGE,
        }
        assert node._hmb_rules_active is False
        assert node._hmb_structured_rules_active is False
        assert node._hmb_policy == ""
        assert node._hmb_binding == ""
        assert node._hmb_policy_rules == []
        assert node._hmb_binding_rules == []
        assert node._hmb_goal_first_rules == []
        return (False, False, 0, 0, 0, False, len(policy_loads), 0)
    except StopIteration as stop:
        assert stop.value == "native-complete"

    assert len(observations) == 1
    active, structured, goal_count, project_count, shot_count = observations[0]
    assert node._hmb_rules_active is False
    assert node._hmb_structured_rules_active is False
    assert node._hmb_policy == ""
    assert node._hmb_binding == ""
    return (
        active,
        structured,
        goal_count,
        project_count,
        shot_count,
        bool(secured),
        len(policy_loads),
        len(observations),
    )


compiled_prompt_copy = prompt._build_prompt_package(prompt._default_widget_state())
native_route = (False, False, 0, 0, 0, False, 0, 1)
hmb_route = (True, True, 1, 4, 4, True, 1, 1)

assert exercise_agent_route(
    compiled_prompt_copy,
    direct_prompt_edge=False,
) == native_route
assert exercise_agent_route(
    "HMB_GP_Production\nTARGET GENERATOR:\nIMAGE SOURCE:\nVIDEO SOURCE:\n",
    direct_prompt_edge=False,
) == native_route
assert exercise_agent_route(
    "ordinary standalone Agent request",
    direct_prompt_edge=False,
) == native_route

# Topology alone activates HMB. A future Prompt wording change, a plain-looking
# package, or an empty transitional value cannot silently demote the exact edge.
for topology_owned_payload in (
    "",
    "future Prompt package with no legacy headings",
    compiled_prompt_copy,
):
    assert exercise_agent_route(
        topology_owned_payload,
        direct_prompt_edge=True,
    ) == hmb_route

# The canonical HMB route requires the signed policy and blocks before native.
assert exercise_agent_route(
    "future Prompt package",
    direct_prompt_edge=True,
    policy_failure=True,
) == (False, False, 0, 0, 0, False, 1, 0)


asset_payload = {
    "schema": "hmb-image-asset-library-binding",
    "mode": "image_asset",
    "selection_id": "parent-contract-asset",
    "ordered_images": [
        {
            "selected": True,
            "order_key": "external:hero",
            "source_uid": "external:hero",
            "image_name": "Hero.png",
            "selection_order": 1,
        }
    ],
    "verified_assets": [],
}
picker_payload = {
    "schema": "hmb-prompt-library-picker-binding",
    "mode": "maya",
    "run_id": "parent-contract-picker",
    "media_ready": True,
    "videos": [
        {
            "video_slot": 1,
            "video_path": "C:/shots/main.mp4",
            "camera": "renderCam",
        }
    ],
}


prompt_only = prompt._default_widget_state()
prompt_asset = prompt._apply_image_asset_payload(
    prompt._default_widget_state(),
    asset_payload,
    connected=True,
)
prompt_picker = prompt._apply_picker_payload(
    prompt._default_widget_state(),
    picker_payload,
    connected=True,
)
prompt_asset_picker = prompt._apply_picker_payload(
    prompt._apply_image_asset_payload(
        prompt._default_widget_state(),
        asset_payload,
        connected=True,
    ),
    picker_payload,
    connected=True,
)

four_prompt_modes = {
    "prompt": (prompt_only, (0, 0)),
    "prompt+asset": (prompt_asset, (1, 0)),
    "prompt+picker": (prompt_picker, (0, 1)),
    "prompt+asset+picker": (prompt_asset_picker, (1, 1)),
}
compiled_modes: dict[str, str] = {}
for mode_name, (state, expected_counts) in four_prompt_modes.items():
    status = state["status"]
    assert (
        int(status["active_images"]),
        int(status["active_videos"]),
    ) == expected_counts, mode_name
    compiled = prompt._build_prompt_package(state)
    assert compiled.startswith("HMB_GP_Production\n"), mode_name
    assert "[HMB VALIDATION ERROR]" not in compiled, mode_name
    compiled_modes[mode_name] = compiled

assert "@image1 = Hero.png" in compiled_modes["prompt+asset"]
assert "@video1 = main" in compiled_modes["prompt+picker"]
assert "@image1 = Hero.png" in compiled_modes["prompt+asset+picker"]
assert "@video1 = main" in compiled_modes["prompt+asset+picker"]
assert len(set(compiled_modes.values())) == 4


# Both semantic input ports use the engine's official `any` wildcard. The
# Prompt accepts arbitrary source classes and preserves foreign readable data
# as ordinary intent instead of pretending it came from Asset or Picker.
if not hasattr(prompt.DataNode, "after_incoming_connection"):
    setattr(
        prompt.DataNode,
        "after_incoming_connection",
        lambda _self, _source_node, _source_parameter, _target_parameter: None,
    )

prompt_node = prompt.HMBPromptLibrary(name="parent_prompt_any_ports")
for parameter_name in (
    prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    prompt.PICKER_INPUT_PARAMETER_NAME,
):
    parameter = prompt._get_parameter_obj(prompt_node, parameter_name)
    assert parameter is not None
    assert list(getattr(parameter, "input_types", [])) == ["any"]

foreign_asset_payload = {
    "schema": "third-party-asset-v9",
    "mode": "sibling-source",
    "creative_note": "KEEP_FOREIGN_ASSET_INTENT",
}
foreign_picker_payload = {
    "schema": "third-party-motion-v7",
    "mode": "other-source",
    "motion_note": "KEEP_FOREIGN_PICKER_INTENT",
}

foreign_asset_source = SimpleNamespace(
    parameter_output_values={"FOREIGN_OUT": foreign_asset_payload},
    parameter_values={},
)
foreign_picker_source = SimpleNamespace(
    parameter_output_values={"FOREIGN_OUT": foreign_picker_payload},
    parameter_values={},
)
source_parameter = SimpleNamespace(name="FOREIGN_OUT")
prompt_node.after_incoming_connection(
    foreign_asset_source,
    source_parameter,
    prompt._get_parameter_obj(
        prompt_node,
        prompt.IMAGE_ASSET_INPUT_PARAMETER_NAME,
    ),
)
prompt_node.after_incoming_connection(
    foreign_picker_source,
    source_parameter,
    prompt._get_parameter_obj(
        prompt_node,
        prompt.PICKER_INPUT_PARAMETER_NAME,
    ),
)

foreign_state = prompt._parse_state(
    prompt._get_parameter_raw(prompt_node, prompt.WIDGET_PARAMETER_NAME)
)
foreign_entries = foreign_state[prompt._SOURCE_INTENT_FALLBACKS_KEY]
foreign_blob = json.dumps(foreign_entries, ensure_ascii=False, sort_keys=True)
foreign_compiled = prompt_node.parameter_output_values["PROMPT_OUT"]
for preserved_token in (
    "KEEP_FOREIGN_ASSET_INTENT",
    "KEEP_FOREIGN_PICKER_INTENT",
):
    assert preserved_token in foreign_blob
    assert preserved_token in foreign_compiled
assert foreign_state["status"]["active_images"] == 0
assert foreign_state["status"]["active_videos"] == 0


# Known HMB payloads remain semantic while unknown extension fields survive in
# the same compiled Prompt, proving recognition and no-loss behavior coexist.
extended_asset = {
    **asset_payload,
    "vendor_extension": "KEEP_ASSET_EXTENSION",
}
extended_picker = {
    **picker_payload,
    "vendor_extension": "KEEP_PICKER_EXTENSION",
}
extended_state = prompt._apply_picker_payload(
    prompt._apply_image_asset_payload(
        prompt._default_widget_state(),
        extended_asset,
        connected=True,
    ),
    extended_picker,
    connected=True,
)
extended_compiled = prompt._build_prompt_package(extended_state)
assert extended_state["status"]["active_images"] == 1
assert extended_state["status"]["active_videos"] == 1
assert "KEEP_ASSET_EXTENSION" in extended_compiled
assert "KEEP_PICKER_EXTENSION" in extended_compiled


print(
    "HMB parent Prompt/Agent topology contract regression: PASS "
    "(exact class/edge, topology-only routing, four Prompt modes, any/foreign inputs)"
)
