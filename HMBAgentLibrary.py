from __future__ import annotations

import ast
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys
from typing import Any


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
    module_path = _THIS_DIR / "_hmb_common.py"
    module_key = f"{module_path.resolve()}:{module_path.stat().st_mtime_ns}"
    module_name = "_hmb_gp_production_common_" + hashlib.sha1(module_key.encode("utf-8")).hexdigest()[:12]
    existing = sys.modules.get(module_name)
    if existing is not None and Path(getattr(existing, "__file__", "")).resolve() == module_path.resolve():
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load HMB common module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_hmb = _load_hmb_common()
DataNode = _hmb.DataNode
Parameter = _hmb.Parameter
ParameterMode = _hmb.ParameterMode
find_builtin_agent_class = _hmb.find_builtin_agent_class
get_internal_policy_rules = _hmb.get_internal_policy_rules
get_internal_binding_rules = _hmb.get_internal_binding_rules
get_internal_policy_documents = _hmb.get_internal_policy_documents

try:
    from griptape_nodes.traits.widget import Widget  # type: ignore
except Exception:
    Widget = None  # type: ignore

try:
    from griptape_nodes.exe_types.core_types import ParameterMessage  # type: ignore
except Exception:
    ParameterMessage = None  # type: ignore

_BuiltinAgent = find_builtin_agent_class()
_BaseAgent = _BuiltinAgent or DataNode

_HMB_TITLE = "HMB_GP_Production"
_HMB_LIBRARY_NAME = "HMB_GP_Production"
_HMB_PROMPT_NODE_TYPE = "HMBPromptLibrary"
_HMB_PROMPT_OUTPUT_PARAMETER = "PROMPT_OUT"
_AGENT_PROMPT_INPUT_PARAMETER = "prompt"
_AGENT_WIDGET_NAME = "HMBAgentLibraryWidget"
_AGENT_WIDGET_LIBRARY_NAME = "HMB_GP_Production"
_AGENT_WIDGET_PARAMETER = "HMB_AGENT_UI"
_AGENT_WIDGET_HEIGHT = 64
_AGENT_STATE_WARNING_NAME = "HMB_AGENT_STATE_DISPLAY_WARNING"
_HMB_POLICY_WARNING_NAME = "HMB_AGENT_POLICY_REQUIRED_WARNING"
_HMB_TOPOLOGY_WARNING_NAME = "HMB_AGENT_CONNECTION_CHECK_WARNING"
_FINAL_TEXT_DISPLAY_NAME = "FINAL TEXT · GENERATOR"
_AGENT_STATE_DISPLAY_NAME = "AGENT STATE · CHAIN ONLY"
_HMB_POLICY_UNAVAILABLE_MESSAGE = (
    "[HMB LOCAL POLICY REQUIRED] 사용자 로컬에 동봉된 hmb_agent_core.dat가 "
    "누락되었거나 손상되어 검증할 수 없습니다. HMBPromptLibrary가 연결된 실행은 "
    "순정 Agent로 대체하지 않고 중단했습니다. HMB_GP_Production을 다시 설치하거나 "
    "업데이트한 뒤 Griptape를 다시 시작하고 재시도하십시오."
)
_HMB_POLICY_IDENTITY_MISMATCH_MESSAGE = (
    "[HMB POLICY VERSION MISMATCH] HMBPromptLibrary의 정책 소스와 "
    "서명된 Agent 런타임 정책 버전이 일치하지 않습니다. "
    "HMB_GP_Production을 동일한 배포 버전으로 다시 설치하거나 업데이트한 뒤 "
    "Griptape를 다시 시작하고 재시도하십시오."
)


class _HMBPolicyIdentityMismatchError(RuntimeError):
    """Internal typed signal for the public fail-closed version diagnostic."""


_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE = (
    "[HMB CONNECTION CHECK FAILED] Prompt 연결 상태를 안전하게 확인할 수 없어 "
    "Agent 실행을 중단했습니다. 연결 상태를 확인한 뒤 재시도하십시오."
)
_PUBLIC_OUTPUT_BLOCKED = (
    "[HMB OUTPUT BLOCKED] Internal Agent state was detected. "
    "Use FINAL TEXT · GENERATOR for display."
)
_HMB_REQUIRED_MARKERS = (
    "TARGET GENERATOR:",
    "IMAGE SOURCE:",
    "VIDEO SOURCE:",
)
_HMB_ANY_BINDING_MARKERS = (
    "REPLACEMENT BINDING:",
    "TARGET FUNCTION BINDING:",
    "VIDEO SOURCE:",
    "VIDEO ROLE MAP:",
    "USER DESCRIPTION DATA (JSON):",
)
_HMB_HYBRID_INDEPENDENCE_MARKERS = (
    "HYBRID COMPOSITION INDEPENDENCE:",
    "MISSING SOURCE AUTHORITY:",
    "OPTIONAL VIDEO CONTROL:",
    "COLOR PLAYBLAST ISOLATION WITHOUT DEPENDENCY:",
    "ADAPTIVE CONFLICT RESOLUTION:",
    "FINAL OUTPUT CONTINUITY:",
)
_HMB_GOAL_FIRST_RULESET_NAME = "hmb_goal_first_contract"
_HMB_GOAL_FIRST_RULE_HEADING = "GOAL_FIRST_NO_PREREQUISITE_CONTRACT"
_INTERNAL_RULE_MARKERS = (
    _HMB_GOAL_FIRST_RULE_HEADING,
    "PROJECT_IDENTITY_SOURCE_AUTHORITY_AND_LANGUAGE",
    "PROJECT_AUTHORITATIVE_SHOT_STATE_VIDEO_ARCHITECTURE_AND_PROXY_ISOLATION",
    "PROJECT_ADDITIVE_DESCRIPTION_VFX_CONTINUITY_AND_EXCLUSION",
    "PROJECT_CROSS_VALIDATION_AND_FINAL_OUTPUT",
    "SHOT_ACTIVATION_IDENTIFIERS_IMAGE_AND_MARKER_BINDING",
    "SHOT_VIDEO_BINDING_AUXILIARY_COMBINATIONS_AND_AUTHORIZED_CONTROL",
    "SHOT_DESCRIPTION_VFX_SCENE_CONTEXT_KEEP_OUT_AND_EFFECT_INTERACTION",
    "SHOT_SEMANTIC_VALIDATION_AND_FINAL_OUTPUT",
)
_LEGACY_HMB_ELEMENTS = {
    "PROJECT",
    "projects_root",
    "project",
    "episode",
    "shot",
    "project_load_path",
    "Task",
}
_PUBLIC_OUTPUT_STATE_KEYS = frozenset(
    {
        "agent_memory",
        "conversation_memory",
        "internal_policy",
        "policy_injection",
        "policy_vault",
        "rulesets",
        "system",
        "system_prompt",
    }
)
_PUBLIC_OUTPUT_STATE_KEY_PATTERN = re.compile(
    r"""(?ix)
    (?:
        ["']\s*
        (?:
            agent_memory|conversation_memory|internal_policy|policy_injection|
            policy_vault|rulesets|system|system_prompt
        )
        \s*["']
        |
        \b(?:agent_memory|conversation_memory|internal_policy|policy_injection|
        policy_vault|rulesets|system_prompt)\b
    )
    \s*:
    """
)
_AGENT_WRAPPER_KEY_PATTERN = re.compile(
    r"""(?ix)
    ["']\s*agent\s*["']\s*:\s*
    (?:
        \{
        |
        ["']?\s*\[
        |
        ["']?\s*(?:griptapenodesagent|agent)\b
    )
    """
)
_SANITIZER_MAX_DEPTH = 64
_SANITIZER_MAX_NODES = 10_000
_SANITIZER_MAX_JSON_CHARS = 1_000_000


def _safe_parameter_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "")).strip("_")
    return value or "parameter"


def _parameter_exists(node: Any, name: str) -> bool:
    try:
        getter = getattr(node, "get_parameter_by_name", None)
        if callable(getter):
            return getter(name) is not None
    except Exception:
        pass
    parameters = getattr(node, "parameters", {})
    if isinstance(parameters, dict):
        return name in parameters
    try:
        return any(getattr(parameter, "name", "") == name for parameter in parameters)
    except Exception:
        return False


def _configure_native_output_ports(node: Any) -> None:
    """Clarify the two native outputs without changing their wire names or types."""
    port_options = {
        "output": (
            _FINAL_TEXT_DISPLAY_NAME,
            "Model final response for Display Text or a downstream generator.",
        ),
        "agent": (
            _AGENT_STATE_DISPLAY_NAME,
            "Native Agent wrapper for Agent-to-Agent chaining only. Do not connect to Display Text.",
        ),
    }
    for name, (display_name, tooltip) in port_options.items():
        try:
            parameter = node.get_parameter_by_name(name)
        except Exception:
            parameter = None
        if parameter is None:
            continue
        try:
            options = dict(getattr(parameter, "ui_options", {}) or {})
            options.update(
                {
                    "display_name": display_name,
                    "tooltip": tooltip,
                }
            )
            parameter.ui_options = options
        except Exception:
            pass
        try:
            parameter.tooltip = tooltip
        except Exception:
            pass
        updater = getattr(parameter, "update_ui_options_key", None)
        if callable(updater):
            for key, value in (
                ("display_name", display_name),
                ("tooltip", tooltip),
            ):
                try:
                    updater(key, value)
                except Exception:
                    pass


def _ensure_agent_state_warning(node: Any) -> None:
    """Install one hidden advisory without changing or deleting graph edges."""
    if ParameterMessage is None:
        return
    try:
        root = getattr(node, "root_ui_element", None)
        children = getattr(root, "children", None) if root is not None else None
        if children is None and root is not None:
            children = getattr(root, "_children", None)
        if isinstance(children, list) and any(
            getattr(child, "name", "") == _AGENT_STATE_WARNING_NAME
            for child in children
        ):
            return
        node.add_node_element(
            ParameterMessage(
                name=_AGENT_STATE_WARNING_NAME,
                title="Agent State is chain-only",
                variant="warning",
                value=(
                    "This connection carries private Agent continuation state. "
                    "Connect FINAL TEXT · GENERATOR to Display Text or a generator."
                ),
                hide=True,
            )
        )
    except Exception:
        # Older engines and lightweight regression stubs may not expose
        # ParameterMessage. Port labels and final-output validation remain active.
        return


def _ensure_hmb_policy_warning(node: Any) -> None:
    """Install one hidden fail-closed policy diagnostic for HMB Prompt runs."""
    if ParameterMessage is None:
        return
    try:
        root = getattr(node, "root_ui_element", None)
        children = getattr(root, "children", None) if root is not None else None
        if children is None and root is not None:
            children = getattr(root, "_children", None)
        if isinstance(children, list) and any(
            getattr(child, "name", "") == _HMB_POLICY_WARNING_NAME
            for child in children
        ):
            return
        node.add_node_element(
            ParameterMessage(
                name=_HMB_POLICY_WARNING_NAME,
                title="HMB Agent policy required",
                variant="warning",
                value=_HMB_POLICY_UNAVAILABLE_MESSAGE,
                hide=True,
            )
        )
    except Exception:
        # RuntimeError and FINAL TEXT still carry the diagnostic on older hosts.
        return


def _ensure_hmb_topology_warning(node: Any) -> None:
    """Install one hidden fail-closed graph-topology diagnostic."""
    if ParameterMessage is None:
        return
    try:
        root = getattr(node, "root_ui_element", None)
        children = getattr(root, "children", None) if root is not None else None
        if children is None and root is not None:
            children = getattr(root, "_children", None)
        if isinstance(children, list) and any(
            getattr(child, "name", "") == _HMB_TOPOLOGY_WARNING_NAME
            for child in children
        ):
            return
        node.add_node_element(
            ParameterMessage(
                name=_HMB_TOPOLOGY_WARNING_NAME,
                title="HMB Agent connection check failed",
                variant="warning",
                value=_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE,
                hide=True,
            )
        )
    except Exception:
        # RuntimeError and FINAL TEXT still carry the diagnostic on older hosts.
        return


def _target_accepts_agent_state(target_parameter: Any) -> bool:
    try:
        input_types = list(getattr(target_parameter, "input_types", None) or [])
    except Exception:
        input_types = []
    return any(str(item or "").strip().casefold() == "agent" for item in input_types)


def _agent_widget_value() -> dict[str, Any]:
    """Return display-only state. Internal policy text must never enter widget data."""
    return {
        "schema": "hmb-agent-ui",
        "schema_version": 1,
        "native_agent": True,
        "policy_vault": "sealed",
        "policy_injection": "runtime_only",
        "output_sanitizer": True,
    }


def _configure_agent_widget_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    try:
        parameter.default_value = _agent_widget_value()
    except Exception:
        pass
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update(
            {
                "display_name": "HMBAgentLibrary",
                "is_full_width": True,
                "height": _AGENT_WIDGET_HEIGHT,
                "min_height": _AGENT_WIDGET_HEIGHT,
                "max_height": _AGENT_WIDGET_HEIGHT,
                "widget_height": _AGENT_WIDGET_HEIGHT,
                "default_height": _AGENT_WIDGET_HEIGHT,
                "preferred_height": _AGENT_WIDGET_HEIGHT,
                "initial_height": _AGENT_WIDGET_HEIGHT,
                # Griptape classifies every custom widget as an expandable row
                # unless this is explicitly false. An expandable row consumes
                # the node's remaining height even when the widget itself is
                # only 64 px tall, leaving a large black gap above provider.
                "expandable": False,
                "resizable": False,
                "compact": True,
            }
        )
        parameter.ui_options = options
        updater = getattr(parameter, "update_ui_options_key", None)
        if callable(updater):
            for key in (
                "height",
                "min_height",
                "max_height",
                "widget_height",
                "default_height",
                "preferred_height",
                "initial_height",
                "expandable",
                "resizable",
                "compact",
            ):
                try:
                    updater(key, options[key])
                except Exception:
                    pass
    except Exception:
        pass
    if Widget is not None:
        has_widget = False
        try:
            finder = getattr(parameter, "find_elements_by_type", None)
            if callable(finder):
                has_widget = bool(finder(Widget, find_recursively=True))
        except Exception:
            has_widget = False
        if not has_widget:
            try:
                parameter.add_trait(
                    Widget(name=_AGENT_WIDGET_NAME, library=_AGENT_WIDGET_LIBRARY_NAME)
                )
            except Exception:
                pass


def _move_agent_widget_below_ports(node: Any) -> None:
    """Place the branded header after native flow/Agent ports and before controls."""
    try:
        root = getattr(node, "root_ui_element", None)
        children = getattr(root, "children", None) if root is not None else None
        if children is None and root is not None:
            children = getattr(root, "_children", None)
        if not isinstance(children, list):
            return
        widget = next(
            (child for child in children if getattr(child, "name", "") == _AGENT_WIDGET_PARAMETER),
            None,
        )
        if widget is None:
            return
        children.remove(widget)
        agent_index = next(
            (index for index, child in enumerate(children) if getattr(child, "name", "") == "agent"),
            1,
        )
        children.insert(min(len(children), agent_index + 1), widget)
    except Exception:
        pass


def _ensure_agent_widget(node: Any) -> None:
    if _parameter_exists(node, _AGENT_WIDGET_PARAMETER):
        parameter = node.get_parameter_by_name(_AGENT_WIDGET_PARAMETER)
        _configure_agent_widget_parameter(parameter)
        _move_agent_widget_below_ports(node)
        return

    kwargs: dict[str, Any] = {
        "name": _AGENT_WIDGET_PARAMETER,
        "default_value": _agent_widget_value(),
        "type": "dict",
        "input_types": ["dict"],
        "tooltip": "Protected HMB Agent runtime status. Native Agent controls remain authoritative.",
        "ui_options": {
            "display_name": "HMBAgentLibrary",
            "is_full_width": True,
            "height": _AGENT_WIDGET_HEIGHT,
            "min_height": _AGENT_WIDGET_HEIGHT,
            "max_height": _AGENT_WIDGET_HEIGHT,
            "widget_height": _AGENT_WIDGET_HEIGHT,
            "default_height": _AGENT_WIDGET_HEIGHT,
            "preferred_height": _AGENT_WIDGET_HEIGHT,
            "initial_height": _AGENT_WIDGET_HEIGHT,
            "expandable": False,
            "resizable": False,
            "compact": True,
        },
    }
    if ParameterMode is not None:
        try:
            kwargs["allowed_modes"] = {ParameterMode.PROPERTY}
        except Exception:
            pass
    else:
        kwargs.update(
            {
                "allow_input": False,
                "allow_output": False,
                "allow_property": True,
            }
        )
    try:
        if Widget is not None:
            parameter = Parameter(
                **{
                    **kwargs,
                    "traits": {
                        Widget(name=_AGENT_WIDGET_NAME, library=_AGENT_WIDGET_LIBRARY_NAME)
                    },
                }
            )
        else:
            parameter = Parameter(**kwargs)
    except Exception:
        parameter = Parameter(**kwargs)
        if Widget is not None:
            try:
                parameter.add_trait(
                    Widget(name=_AGENT_WIDGET_NAME, library=_AGENT_WIDGET_LIBRARY_NAME)
                )
            except Exception:
                pass
    node.add_parameter(parameter)
    _configure_agent_widget_parameter(parameter)
    _move_agent_widget_below_ports(node)


def _is_hmb_prompt_library_payload(value: Any) -> bool:
    """Recognize compiled Prompt text for format diagnostics only.

    This helper is deliberately not an Agent activation gate. Text can be
    copied or forged; runtime policy selection uses the canonical graph edge
    and exact registered Prompt class in
    :func:`_is_direct_hmb_prompt_library_connection`.
    """

    text = str(value or "").strip()
    if not text or not text.startswith(_HMB_TITLE):
        return False
    if not all(marker in text for marker in _HMB_REQUIRED_MARKERS):
        return False
    return any(marker in text for marker in _HMB_ANY_BINDING_MARKERS)


def _prompt_policy_source_identity(
    source_path: Path | None = None,
) -> tuple[str, str]:
    """Read the Prompt compiler's declared policy identity without importing it.

    HMBPromptLibrary can advance to a reviewed source candidate before the
    authorized signer produces a matching runtime envelope. Reading the two
    literal assignments through the AST avoids circular imports and prevents a
    comment or unrelated legacy digest from satisfying the runtime guard.
    """

    path = Path(source_path) if source_path is not None else _THIS_DIR / "HMBPromptLibrary.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        raise RuntimeError("HMB Prompt policy source identity could not be read.") from exc
    wanted = {
        "PROMPT_POLICY_SOURCE_VERSION": "",
        "PROMPT_POLICY_SOURCE_CONTRACT_SHA256": "",
    }
    seen: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        if value_node is None:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in wanted:
                continue
            if target.id in seen:
                raise RuntimeError(f"Duplicate HMB Prompt policy identity: {target.id}")
            seen.add(target.id)
            try:
                value = ast.literal_eval(value_node)
            except Exception as exc:
                raise RuntimeError(
                    f"HMB Prompt policy identity is not a string literal: {target.id}"
                ) from exc
            if not isinstance(value, str):
                raise RuntimeError(
                    f"HMB Prompt policy identity is not a string literal: {target.id}"
                )
            wanted[target.id] = value.strip()
    version = wanted["PROMPT_POLICY_SOURCE_VERSION"]
    contract = wanted["PROMPT_POLICY_SOURCE_CONTRACT_SHA256"].lower()
    if not version or not re.fullmatch(r"[0-9a-f]{64}", contract):
        raise RuntimeError("HMB Prompt policy source identity is incomplete.")
    return version, contract


def _assert_prompt_policy_identity_matches_signed_runtime() -> tuple[str, str]:
    """Fail closed before one HMB execution can mix compiler/policy versions."""

    prompt_identity = _prompt_policy_source_identity()
    runtime_identity = (
        str(_hmb._AGENT_POLICY_VERSION),
        str(_hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
    )
    if prompt_identity != runtime_identity:
        raise _HMBPolicyIdentityMismatchError(
            _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
        )
    return prompt_identity


def _is_direct_hmb_prompt_library_connection(
    node: Any,
    *,
    connection_lookup: Any = None,
    node_lookup: Any = None,
    expected_class_lookup: Any = None,
) -> bool:
    """Verify the one canonical Prompt -> Agent edge from host graph data.

    Payload text alone is not provenance: Asset, Picker, a native Prompt, or an
    unrelated node may all produce readable strings.  HMB automation belongs to
    HMBPromptLibrary, so it activates only for the direct registered edge
    ``HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt``.  Upstream nodes
    remain unrestricted because HMBPromptLibrary is responsible for accepting
    and composing them before this boundary.

    Host lookup failures raise instead of being mistaken for a verified absence
    of the HMB Prompt edge. The caller blocks execution with a visible error.
    Optional lookup callables make this graph contract independently testable.
    """

    try:
        node_name = str(getattr(node, "name", "") or "").strip()
        if not node_name:
            raise RuntimeError("Agent node identity is unavailable.")

        if (
            connection_lookup is None
            or node_lookup is None
            or expected_class_lookup is None
        ):
            from griptape_nodes.retained_mode.retained_mode import RetainedMode  # type: ignore
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
            from griptape_nodes.node_library.library_registry import LibraryRegistry  # type: ignore

            if connection_lookup is None:
                connection_lookup = RetainedMode.get_connections_for_parameter
            if node_lookup is None:
                node_lookup = GriptapeNodes.NodeManager().get_node_by_name
            if expected_class_lookup is None:
                expected_class_lookup = lambda: LibraryRegistry.get_library(
                    _HMB_LIBRARY_NAME
                ).get_node_class(_HMB_PROMPT_NODE_TYPE)

        result = connection_lookup(_AGENT_PROMPT_INPUT_PARAMETER, node_name)
        incoming = getattr(result, "incoming_connections", None)
        if incoming is None:
            raise RuntimeError("Prompt connection lookup result is unavailable.")
        if not isinstance(incoming, (list, tuple)):
            raise RuntimeError("Prompt connection lookup returned malformed data.")

        prompt_connections = [
            connection
            for connection in incoming
            if str(getattr(connection, "target_parameter_name", "") or "")
            == _AGENT_PROMPT_INPUT_PARAMETER
        ]
        if not prompt_connections:
            return False
        if len(prompt_connections) > 1:
            raise RuntimeError("Prompt connection topology is ambiguous.")

        connection = prompt_connections[0]
        if (
            str(getattr(connection, "source_parameter_name", "") or "")
            != _HMB_PROMPT_OUTPUT_PARAMETER
        ):
            return False
        source_node_name = str(
            getattr(connection, "source_node_name", "") or ""
        ).strip()
        if not source_node_name:
            raise RuntimeError("Prompt connection source identity is missing.")

        source_node = node_lookup(source_node_name)
        if source_node is None:
            raise RuntimeError("Prompt connection source node is unavailable.")
        expected_class = expected_class_lookup()
        if not isinstance(expected_class, type):
            raise RuntimeError("Registered HMB Prompt class is unavailable.")
        if type(source_node) is not expected_class:
            return False
        metadata = getattr(source_node, "metadata", None)
        if not isinstance(metadata, dict):
            return False
        return (
            str(metadata.get("library") or "") == _HMB_LIBRARY_NAME
            and str(metadata.get("node_type") or "") == _HMB_PROMPT_NODE_TYPE
        )
    except Exception as exc:
        raise RuntimeError(
            "HMBAgentLibrary Prompt connection topology could not be verified."
        ) from exc


def _ruleset_contains_exact_rule(item: Any, rule_text: str) -> bool:
    expected = str(rule_text or "").strip()
    if not expected:
        return False
    if isinstance(item, str):
        return item.strip() == expected
    if isinstance(item, dict):
        rules = item.get("rules", [])
        if isinstance(rules, (list, tuple)):
            return any(str(rule or "").strip() == expected for rule in rules)
    try:
        rules = getattr(item, "rules", None)
        if rules is not None:
            for rule in rules:
                candidate = getattr(rule, "value", rule)
                if str(candidate or "").strip() == expected:
                    return True
    except Exception:
        pass
    return False


def _ruleset_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name", "") or "").strip()
    try:
        return str(getattr(item, "name", "") or "").strip()
    except Exception:
        return ""


def _split_behavior_rules(value: str, expected_count: int = 4) -> list[str]:
    """Split one Behavior document into the exact native rule-list entries."""
    text = str(value or "").replace("﻿", "").strip()
    if not text:
        raise RuntimeError("HMB Behavior data is empty.")
    lines = text.splitlines()
    if lines and re.fullmatch(r"Behavior\s+\d+", lines[0].strip(), re.IGNORECASE):
        text = "\n".join(lines[1:]).strip()
    pattern = re.compile(r"(?m)^\s*(\d+)\.\s+([A-Z][A-Z0-9_]+)\s*$")
    matches = list(pattern.finditer(text))
    numbers = [int(match.group(1)) for match in matches]
    if len(matches) != expected_count or numbers != list(range(1, expected_count + 1)):
        raise RuntimeError(
            f"Each HMB Behavior must contain exactly {expected_count} numbered rules in order."
        )
    rules: list[str] = []
    for index, match in enumerate(matches):
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():section_end].strip()
        rule = match.group(2) if not body else f"{match.group(2)}\n\n{body}"
        rules.append(rule.strip())
    return rules


def _extract_goal_first_rule(policy: str, binding: str) -> str:
    """Build the shared goal-first contract from sealed Behavior documents.

    The rule text stays in the signed sealed resource at rest. At runtime we
    select the six shared goal-first clauses from the verified payload instead
    of duplicating policy prose in this public module. Plain/native Agent
    requests do not call this helper; the canonical direct HMBPromptLibrary
    output edge opts into the full 4+4 Behaviors that contain the same shared
    contract.
    """
    paragraphs = [
        paragraph.strip()
        for document in (policy, binding)
        for paragraph in re.split(r"\n\s*\n", str(document or ""))
        if paragraph.strip()
    ]
    selected: list[str] = []
    for marker in _HMB_HYBRID_INDEPENDENCE_MARKERS:
        clause = next(
            (paragraph for paragraph in paragraphs if paragraph.startswith(marker)),
            "",
        )
        if not clause:
            raise RuntimeError(
                f"HMBAgentLibrary sealed goal-first clause is missing: {marker}"
            )
        selected.append(clause)
    return f"{_HMB_GOAL_FIRST_RULE_HEADING}\n\n" + "\n\n".join(selected)


def _ruleset_contains_any_rule(item: Any, rule_texts: list[str]) -> bool:
    return any(_ruleset_contains_exact_rule(item, text) for text in rule_texts)


def _is_hmb_ruleset(item: Any, expected_name: str, rule_texts: list[str]) -> bool:
    return _ruleset_name(item) == expected_name or _ruleset_contains_any_rule(item, rule_texts)


def _contains_internal_rule_text(value: Any, policy: str, binding: str) -> bool:
    stack: list[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    inspected = 0
    normalized_rules = tuple(
        " ".join(str(rule_text or "").split())
        for rule_text in (policy, binding)
    )
    while stack:
        item, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return True
        if isinstance(item, str):
            text = item
            if any(
                marker in text
                for marker in (*_INTERNAL_RULE_MARKERS, *_HMB_HYBRID_INDEPENDENCE_MARKERS)
            ):
                return True
            normalized = " ".join(text.split())
            if any(
                len(rule_normalized) >= 160 and rule_normalized[:160] in normalized
                for rule_normalized in normalized_rules
            ):
                return True
            continue
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend((nested, depth + 1) for nested in item.values())
        elif isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend((nested, depth + 1) for nested in item)
    return False


def _mapping_contains_agent_state(value: Any, decode_budget: int = 2) -> bool:
    """Return whether decoded structured output resembles native Agent state.

    Display nodes can JSON-encode a native wrapper more than once. Inspect
    string values nested inside otherwise benign dictionaries as well, while
    bounding decoding so ordinary prose is never recursively interpreted.
    """
    stack: list[tuple[Any, int, int]] = [(value, max(0, int(decode_budget)), 0)]
    visited: set[int] = set()
    inspected = 0
    while stack:
        item, remaining_decodes, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return True
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            try:
                normalized_items = [
                    (str(key or "").strip().casefold(), nested)
                    for key, nested in item.items()
                ]
            except Exception:
                return True
            keys = {key for key, _nested in normalized_items}
            if keys & _PUBLIC_OUTPUT_STATE_KEYS:
                return True
            if "agent" in keys:
                agent_value = next(
                    (nested for key, nested in normalized_items if key == "agent"),
                    None,
                )
                if isinstance(agent_value, (dict, list, tuple)):
                    return True
                if "griptapenodesagent" in str(agent_value or "").casefold():
                    return True
            stack.extend(
                (nested, remaining_decodes, depth + 1)
                for _key, nested in normalized_items
            )
            continue
        if isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend(
                (nested, remaining_decodes, depth + 1) for nested in item
            )
            continue
        if isinstance(item, str):
            text = item.strip()
            if _PUBLIC_OUTPUT_STATE_KEY_PATTERN.search(text) or _AGENT_WRAPPER_KEY_PATTERN.search(text):
                return True
            if (
                remaining_decodes > 0
                and len(text) <= _SANITIZER_MAX_JSON_CHARS
                and text.startswith(("{", "[", '"'))
            ):
                try:
                    decoded = json.loads(text)
                except Exception:
                    continue
                if decoded != item:
                    stack.append((decoded, remaining_decodes - 1, depth + 1))
    return False


def _contains_public_output_state_leak(value: Any, policy: str, binding: str) -> bool:
    """Fail closed only for internal state mistakenly published as final text."""
    if _contains_internal_rule_text(value, policy, binding):
        return True
    if isinstance(value, (dict, list, tuple)):
        return _mapping_contains_agent_state(value)
    if not isinstance(value, str):
        return value is not None

    text = value.strip()
    if not text:
        return False
    if _PUBLIC_OUTPUT_STATE_KEY_PATTERN.search(text):
        return True
    if _AGENT_WRAPPER_KEY_PATTERN.search(text):
        return True

    # Native wrappers may be serialized once or wrapped inside a JSON string by
    # Display Text. Decode at most twice; never execute or normalize model text.
    decoded: Any = text
    for _ in range(2):
        try:
            decoded = json.loads(decoded)
        except Exception:
            break
        if _mapping_contains_agent_state(decoded):
            return True
        if not isinstance(decoded, str):
            break
    return False


def _strip_internal_rules_from_agent_wrapper(
    value: Any,
    policy_rules: list[str],
    binding_rules: list[str],
    goal_first_rules: list[str] | None = None,
) -> Any:
    if not isinstance(value, dict):
        return value
    rulesets = value.get("rulesets")
    if isinstance(rulesets, list):
        value["rulesets"] = [
            item
            for item in rulesets
            if not _is_hmb_ruleset(item, "hmb_project_behavior", policy_rules)
            and not _is_hmb_ruleset(item, "hmb_shot_behavior", binding_rules)
            and not _is_hmb_ruleset(
                item,
                _HMB_GOAL_FIRST_RULESET_NAME,
                list(goal_first_rules or []),
            )
        ]
    return value


def _replace_leaked_strings(value: Any, policy: str, binding: str, replacement: str) -> Any:
    visited: set[int] = set()
    budget = [0]

    def scrub(item: Any, depth: int) -> Any:
        budget[0] += 1
        if budget[0] > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return replacement
        if isinstance(item, str):
            return replacement if _contains_internal_rule_text(item, policy, binding) else item
        if isinstance(item, list):
            item_id = id(item)
            if item_id in visited:
                return replacement
            visited.add(item_id)
            for index, nested in enumerate(list(item)):
                item[index] = scrub(nested, depth + 1)
            return item
        if isinstance(item, tuple):
            item_id = id(item)
            if item_id in visited:
                return replacement
            visited.add(item_id)
            return tuple(scrub(nested, depth + 1) for nested in item)
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                return replacement
            visited.add(item_id)
            for key, nested in list(item.items()):
                item[key] = scrub(nested, depth + 1)
            return item
        return item

    return scrub(value, 0)


class HMBAgentLibrary(_BaseAgent):
    """Native Griptape Agent with temporary HMB Behavior 1 / Behavior 2 injection.

    Standalone text and direct Image/Video requests remain stock native Agent
    executions with no sealed-policy read or injection. When the prompt input is
    directly connected to the exact registered HMBPromptLibrary PROMPT_OUT, the
    full internal Behaviors are represented by exactly four native rules each
    for that one execution. Prompt-only, Prompt+Asset, Prompt+Picker, and
    Prompt+Asset+Picker are equally valid; the Agent neither identifies nor
    requires those upstream sources itself. The prompt, memory, tools, model,
    schema, output handling, and Agent wire format remain owned by the Standard
    Library Agent. Once the canonical HMB Prompt edge is present, a missing or
    invalid policy blocks execution and reports the configuration error instead
    of silently falling back to a stock native execution.
    """

    def add_parameter(self, parameter):
        """Preserve native parameters; only normalize generated Behavior labels.

        Some Griptape restores reject spaces in dynamically generated ParameterList
        child names. This changes the internal key only and keeps the visible label.
        """
        try:
            original = getattr(parameter, "name", "")
            if isinstance(original, str) and original.startswith("Behavior "):
                ui = getattr(parameter, "ui_options", None) or {}
                if isinstance(ui, dict):
                    ui = dict(ui)
                    ui.setdefault("display_name", original)
                    parameter.ui_options = ui
                parameter.name = _safe_parameter_name(original)
        except Exception:
            pass
        return super().add_parameter(parameter)

    def __init__(self, **kwargs):
        if _BuiltinAgent is None:
            raise RuntimeError(
                "HMBAgentLibrary requires the installed Griptape Standard Library Agent. "
                "Refresh the Standard Library or set HMB_GRIPTAPE_STANDARD_LIBRARY_PATH."
            )
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.description = "HMBAgentLibrary"
        self._hmb_rules_active = False
        self._hmb_policy = ""
        self._hmb_binding = ""
        self._hmb_policy_rules: list[str] = []
        self._hmb_binding_rules: list[str] = []
        self._hmb_goal_first_rules: list[str] = []
        self._hmb_structured_rules_active = False
        self._hmb_native_calls_this_process = 0
        self._remove_legacy_hmb_elements()
        _configure_native_output_ports(self)
        _ensure_agent_state_warning(self)
        _ensure_hmb_policy_warning(self)
        _ensure_hmb_topology_warning(self)
        _ensure_agent_widget(self)

    def _remove_parameter(self, name: str) -> None:
        parameter = None
        try:
            parameter = self.get_parameter_by_name(name)
        except Exception:
            parameters = getattr(self, "parameters", None)
            if isinstance(parameters, dict):
                parameter = parameters.get(name)
        if parameter is None:
            return
        for method_name in ("remove_parameter", "delete_parameter", "remove_parameter_by_name"):
            method = getattr(self, method_name, None)
            if not callable(method):
                continue
            try:
                try:
                    method(name)
                except TypeError:
                    method(parameter)
                return
            except Exception:
                continue
        parameters = getattr(self, "parameters", None)
        if isinstance(parameters, dict):
            parameters.pop(name, None)

    def _remove_legacy_hmb_elements(self) -> None:
        """Remove project/save UI left by earlier HMBAgentLibrary builds."""
        for name in sorted(_LEGACY_HMB_ELEMENTS - {"PROJECT"}):
            self._remove_parameter(name)
        try:
            root = getattr(self, "root_ui_element", None)
            children = getattr(root, "children", None) if root is not None else None
            if children is None and root is not None:
                children = getattr(root, "_children", None)
            if isinstance(children, list):
                children[:] = [
                    child
                    for child in children
                    if getattr(child, "name", None) not in _LEGACY_HMB_ELEMENTS
                ]
        except Exception:
            pass

    def after_deserialize(self, *args, **kwargs):
        parent = getattr(super(), "after_deserialize", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._remove_legacy_hmb_elements()
        _configure_native_output_ports(self)
        _ensure_agent_state_warning(self)
        _ensure_hmb_policy_warning(self)
        _ensure_hmb_topology_warning(self)
        _ensure_agent_widget(self)
        return result

    def after_outgoing_connection(
        self,
        source_parameter,
        target_node,
        target_parameter,
    ):
        """Warn about Agent-state display without rewriting saved graph topology."""
        parent = getattr(super(), "after_outgoing_connection", None)
        result = (
            parent(source_parameter, target_node, target_parameter)
            if callable(parent)
            else None
        )
        if (
            getattr(source_parameter, "name", "") == "agent"
            and not _target_accepts_agent_state(target_parameter)
        ):
            try:
                self.show_message_by_name(_AGENT_STATE_WARNING_NAME)
            except Exception:
                pass
        return result

    def after_outgoing_connection_removed(
        self,
        source_parameter,
        target_node,
        target_parameter,
    ):
        parent = getattr(super(), "after_outgoing_connection_removed", None)
        result = (
            parent(source_parameter, target_node, target_parameter)
            if callable(parent)
            else None
        )
        if (
            getattr(source_parameter, "name", "") == "agent"
            and not _target_accepts_agent_state(target_parameter)
        ):
            try:
                self.hide_message_by_name(_AGENT_STATE_WARNING_NAME)
            except Exception:
                pass
        return result

    def get_parameter_list_value(self, name: str):
        """Prepend temporary sealed rules without storing them on the node."""
        values = super().get_parameter_list_value(name)
        if name != "rulesets" or not self._hmb_rules_active:
            return values
        existing = list(values or [])
        filtered = [
            item
            for item in existing
            if not _is_hmb_ruleset(item, "hmb_project_behavior", self._hmb_policy_rules)
            and not _is_hmb_ruleset(item, "hmb_shot_behavior", self._hmb_binding_rules)
            and not _is_hmb_ruleset(
                item,
                _HMB_GOAL_FIRST_RULESET_NAME,
                self._hmb_goal_first_rules,
            )
        ]
        if self._hmb_structured_rules_active:
            injected = [
                {"name": "hmb_project_behavior", "rules": list(self._hmb_policy_rules)},
                {"name": "hmb_shot_behavior", "rules": list(self._hmb_binding_rules)},
            ]
        else:
            injected = [
                {
                    "name": _HMB_GOAL_FIRST_RULESET_NAME,
                    "rules": list(self._hmb_goal_first_rules),
                }
            ]
        return [*injected, *filtered]

    def _load_hmb_rules(self) -> tuple[str, str, list[str], list[str]]:
        policy_document, binding_document = get_internal_policy_documents()
        policy = str(policy_document or "").strip()
        binding = str(binding_document or "").strip()
        if not policy or not binding:
            raise RuntimeError("HMBAgentLibrary internal Behavior 1 / Behavior 2 data is incomplete.")
        if any(
            marker not in policy or marker not in binding
            for marker in _HMB_HYBRID_INDEPENDENCE_MARKERS
        ):
            raise RuntimeError(
                "HMBAgentLibrary sealed hybrid-composition policy is stale or incomplete."
            )
        policy_rules = _split_behavior_rules(policy, 4)
        binding_rules = _split_behavior_rules(binding, 4)
        return policy, binding, policy_rules, binding_rules

    def _set_visible_output(self, value: str) -> None:
        try:
            self.set_parameter_value("output", value)
        except Exception:
            pass
        outputs = getattr(self, "parameter_output_values", None)
        if isinstance(outputs, dict):
            outputs["output"] = value

    def _clear_hmb_runtime_policy(self) -> None:
        """Discard all expanded policy text immediately after one native call."""
        self._hmb_rules_active = False
        self._hmb_structured_rules_active = False
        self._hmb_policy = ""
        self._hmb_binding = ""
        self._hmb_policy_rules = []
        self._hmb_binding_rules = []
        self._hmb_goal_first_rules = []

    def _hide_hmb_policy_warning(self) -> None:
        for warning_name in (
            _HMB_POLICY_WARNING_NAME,
            _HMB_TOPOLOGY_WARNING_NAME,
        ):
            try:
                self.hide_message_by_name(warning_name)
            except Exception:
                pass

    def _publish_hmb_execution_block(self, message: str) -> None:
        """Publish only a safe diagnostic; no policy text or path may escape."""
        self._clear_hmb_runtime_policy()
        outputs = getattr(self, "parameter_output_values", None)
        if isinstance(outputs, dict):
            outputs["agent"] = {}
        self._set_visible_output(message)
        self._hide_hmb_policy_warning()
        warning_name = (
            _HMB_TOPOLOGY_WARNING_NAME
            if message == _HMB_TOPOLOGY_UNAVAILABLE_MESSAGE
            else _HMB_POLICY_WARNING_NAME
        )
        try:
            self.show_message_by_name(warning_name)
        except Exception:
            pass
        try:
            print(f"[HMB_PRODUCTION][ERROR] {message}")
        except Exception:
            pass

    def _run_native_agent_once(self):
        if self._hmb_native_calls_this_process >= 1:
            raise RuntimeError("HMBAgentLibrary blocked an additional native Agent execution.")
        self._hmb_native_calls_this_process += 1
        return (yield from super().process())

    def _has_canonical_hmb_prompt_connection(self) -> bool:
        """Return whether the host graph has the one registered Prompt edge."""

        return _is_direct_hmb_prompt_library_connection(self)

    def _secure_hmb_outputs(self) -> None:
        outputs = getattr(self, "parameter_output_values", None)
        if not isinstance(outputs, dict):
            return

        blocked = _PUBLIC_OUTPUT_BLOCKED
        try:
            wrapper = outputs.get("agent")
            if isinstance(wrapper, dict):
                # Remove injected rulesets before recursive sanitization so shared
                # native rule objects are not mutated, then scrub nested traces.
                _strip_internal_rules_from_agent_wrapper(
                    wrapper,
                    self._hmb_policy_rules,
                    self._hmb_binding_rules,
                    self._hmb_goal_first_rules,
                )
                outputs["agent"] = _replace_leaked_strings(
                    wrapper,
                    self._hmb_policy,
                    self._hmb_binding,
                    blocked,
                )

            visible = outputs.get("output", "")
            if _contains_public_output_state_leak(
                visible,
                self._hmb_policy,
                self._hmb_binding,
            ):
                self._set_visible_output(blocked)
        except Exception as exc:
            # Sanitizer bugs must neither expose partial state nor replace the
            # native Agent result/exception with a second failure.
            outputs["agent"] = {}
            self._set_visible_output(blocked)
            try:
                print(f"[HMB_PRODUCTION][WARN] Agent output sanitizer failed closed: {exc}")
            except Exception:
                pass

    def process(self):
        """Execute the native Agent exactly once.

        A plain/native prompt is a stock Standard Library Agent execution: the
        sealed HMB policy is not read, injected, filtered, or used to rewrite its
        output.  Only the direct registered
        ``HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.prompt`` edge opts into
        the four project rules plus four shot rules.  The Prompt owns all four
        valid source modes (Prompt only, +Asset, +Picker, +Asset+Picker), so the
        Agent does not infer its siblings from payload text. Once that canonical
        edge is present, policy availability and verification are mandatory: a
        failure is reported and native execution is not attempted.
        """
        self._hmb_native_calls_this_process = 0
        # Topology is the contract.  HMBPromptLibrary owns its four valid modes
        # (Prompt only, +Asset, +Picker, +Asset+Picker), so headings or payload
        # wording may evolve without silently disabling its parent Agent path.
        try:
            is_hmb = self._has_canonical_hmb_prompt_connection()
        except Exception:
            self._publish_hmb_execution_block(_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE) from None

        # No canonical HMB Prompt edge means no HMB policy work at all. Asset,
        # Picker, copied HMB-shaped text, and every ordinary Prompt stay on the
        # Standard Library execution path.
        if not is_hmb:
            self._clear_hmb_runtime_policy()
            self._hide_hmb_policy_warning()
            return (yield from self._run_native_agent_once())

        try:
            _assert_prompt_policy_identity_matches_signed_runtime()
        except _HMBPolicyIdentityMismatchError:
            self._publish_hmb_execution_block(
                _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
            )
            raise RuntimeError(
                _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
            ) from None
        except Exception:
            self._publish_hmb_execution_block(_HMB_POLICY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE) from None

        try:
            (
                self._hmb_policy,
                self._hmb_binding,
                self._hmb_policy_rules,
                self._hmb_binding_rules,
            ) = self._load_hmb_rules()
            self._hmb_goal_first_rules = [
                _extract_goal_first_rule(self._hmb_policy, self._hmb_binding)
            ]
        except Exception:
            self._publish_hmb_execution_block(_HMB_POLICY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE) from None
        self._hide_hmb_policy_warning()
        self._hmb_structured_rules_active = True
        self._hmb_rules_active = True

        result = None
        try:
            result = yield from self._run_native_agent_once()
        finally:
            self._hmb_rules_active = False
            self._hmb_structured_rules_active = False
            # The native Agent may publish a partial wrapper or tool trace before
            # raising. Always remove and scrub the temporary HMB rules in the same
            # finally path so an exceptional execution cannot bypass protection.
            try:
                self._secure_hmb_outputs()
            except Exception as exc:
                # Preserve the native return value or native exception even if a
                # future sanitizer implementation unexpectedly raises.
                try:
                    self._set_visible_output(_PUBLIC_OUTPUT_BLOCKED)
                    outputs = getattr(self, "parameter_output_values", None)
                    if isinstance(outputs, dict):
                        outputs["agent"] = {}
                    print(
                        "[HMB_PRODUCTION][WARN] Agent output sanitizer failed "
                        f"without masking native execution: {exc}"
                    )
                except Exception:
                    pass
            finally:
                self._clear_hmb_runtime_policy()
        return result
