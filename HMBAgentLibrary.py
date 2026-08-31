from __future__ import annotations

from pathlib import Path
import hashlib
import hmac
import importlib.util
import json
import re
import secrets
import sys
from typing import Any


_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


def _load_hmb_common():
    module_path = _THIS_DIR / "_hmb_common.py"
    module_name = "_hmb_gp_production_common"
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

_HMB_LIBRARY_NAME = "HMB_GP_Production"
_HMB_PROMPT_NODE_TYPE = "HMBPromptLibrary"
_HMB_PROMPT_OUTPUT_PARAMETER = "PROMPT_OUT"
_AGENT_PROMPT_INPUT_PARAMETER = "prompt"
_AGENT_SHOT_PROMPT_INPUT_PARAMETER = "SHOT_PROMPT_IN"
_AGENT_WIDGET_NAME = "HMBAgentLibraryWidget"
_AGENT_WIDGET_LIBRARY_NAME = "HMB_GP_Production"
_AGENT_WIDGET_PARAMETER = "HMB_AGENT_UI"
_AGENT_WIDGET_HEIGHT = 64
_AGENT_SHOT_CONTEXT_SCHEMA = "hmb-agent-shot-context"
_AGENT_SHOT_CONTEXT_VERSION = 1
_AGENT_STATE_WARNING_NAME = "HMB_AGENT_STATE_DISPLAY_WARNING"
_HMB_POLICY_WARNING_NAME = "HMB_AGENT_POLICY_REQUIRED_WARNING"
_HMB_TOPOLOGY_WARNING_NAME = "HMB_AGENT_CONNECTION_CHECK_WARNING"
_FINAL_TEXT_DISPLAY_NAME = "FINAL TEXT · GENERATOR"
_AGENT_STATE_DISPLAY_NAME = "AGENT STATE · CHAIN ONLY"
_HMB_POLICY_UNAVAILABLE_MESSAGE = (
    "[HMB LOCAL POLICY REQUIRED] The signed local Agent policy is unavailable "
    "or invalid. Reinstall or update HMB_GP_Production from the approved "
    "package, then restart the official Griptape Desktop application."
)
_HMB_SOURCE_CONTRACT_INVALID_MESSAGE = (
    "[HMB SOURCE CONTRACT INVALID] 구조화된 HMB 소스 데이터의 형식 또는 주소가 "
    "일치하지 않아 실행을 중단했습니다. Frame Range OFF/미설정, 선택 역할 미지정 "
    "및 emitter 미지정은 정상적인 선택 상태이며 이 오류의 원인이 아닙니다. "
    "HMBPromptLibrary와 HMBVideoPickerLibrary의 구조화 데이터 연결 상태를 확인하십시오."
)
_RUNTIME_FX_SCOPE_HEADER = "HMB VERIFIED FX/TIMING RUNTIME SCOPE (JSON):"
_PAIRED_PROMPT_SNAPSHOT_SCHEMA = "hmb-prompt-paired-snapshot"
_PAIRED_PROMPT_SNAPSHOT_VERSION = 1
_PAIRED_PROMPT_SNAPSHOT_KEYS = frozenset({
    "schema",
    "version",
    "generation",
    "visible_sha256",
    "machine_sha256",
    "machine_prompt",
})
_VERIFIED_PROMPT_SOURCE_ATTRIBUTE = "_hmb_verified_prompt_source_node"


_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE = (
    "[HMB CONNECTION CHECK FAILED] Prompt 연결 상태를 안전하게 확인할 수 없어 "
    "Agent 실행을 중단했습니다. 연결 상태를 확인한 뒤 재시도하십시오."
)
_PUBLIC_OUTPUT_BLOCKED = (
    "[HMB OUTPUT BLOCKED] Internal Agent state was detected. "
    "Use FINAL TEXT · GENERATOR for display."
)
_HMB_EXECUTION_FAILED_MESSAGE = (
    "[HMB EXECUTION FAILED] The protected execution ended without a publishable result."
)

_HMB_NATIVE_FAILURE_CODES = frozenset({
    "MODEL_CREDENTIAL",
    "MODEL_ACCESS",
    "MODEL_RATE_LIMIT",
    "MODEL_TIMEOUT",
    "MODEL_NETWORK",
    "MODEL_PROVIDER",
    "HOST_ADAPTER",
    "EMPTY_OUTPUT",
})


def _hmb_native_failure_code(exc: BaseException) -> str:
    """Reduce a native/Cloud exception to a policy-free operational code."""

    status = None
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(exc, "code", None),
    ):
        try:
            status = int(candidate)
            break
        except (TypeError, ValueError, OverflowError):
            continue
    if status == 401:
        return "MODEL_CREDENTIAL"
    if status == 403:
        return "MODEL_ACCESS"
    if status == 429:
        return "MODEL_RATE_LIMIT"
    if status in {408, 504}:
        return "MODEL_TIMEOUT"
    if isinstance(status, int) and status >= 500:
        return "MODEL_PROVIDER"

    # The message is inspected only in memory and is never logged or exposed.
    # Provider SDKs do not consistently surface an HTTP status attribute.
    folded = " ".join((
        exc.__class__.__name__,
        str(exc or ""),
    )).casefold()
    if any(token in folded for token in (
        "api key", "apikey", "credential", "unauthorized", "401",
    )):
        return "MODEL_CREDENTIAL"
    if any(token in folded for token in (
        "forbidden", "permission", "entitlement", "model access", "403",
    )):
        return "MODEL_ACCESS"
    if any(token in folded for token in (
        "rate limit", "too many requests", "quota", "429",
    )):
        return "MODEL_RATE_LIMIT"
    if any(token in folded for token in (
        "timeout", "timed out", "deadline exceeded",
    )):
        return "MODEL_TIMEOUT"
    if any(token in folded for token in (
        "connection", "network", "dns", "socket", "tls", "ssl",
    )):
        return "MODEL_NETWORK"
    if isinstance(exc, (AttributeError, KeyError, TypeError, StopIteration)):
        return "HOST_ADAPTER"
    return "MODEL_PROVIDER"


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
        "memory",
        "conversation_memory",
        "messages",
        "internal_policy",
        "policy_injection",
        "policy_vault",
        "rulesets",
        "instructions",
        "system",
        "system_prompt",
        "tool",
        "tools",
        "tool_call",
        "tool_calls",
        "tool_result",
        "tool_results",
        "trace",
        "traces",
        "runtime_scope",
        "shared_windows",
        "allowed_segments",
    }
)
# These names are either sealed-policy containers or HMB-derived runtime
# addresses. Their presence is independently sufficient evidence of private
# state. The remaining names are common in legitimate generator documents and
# require a compound Agent-wrapper shape before they are blocked.
_HMB_UNIQUE_RUNTIME_STATE_KEYS = frozenset(
    {
        "internal_policy",
        "policy_injection",
        "policy_vault",
        "rulesets",
        "runtime_scope",
        "shared_windows",
        "allowed_segments",
    }
)
_GENERIC_AGENT_STATE_KEYS = _PUBLIC_OUTPUT_STATE_KEYS - _HMB_UNIQUE_RUNTIME_STATE_KEYS
_SEALED_POLICY_STATE_KEYS = frozenset(
    {
        "internal_policy",
        "policy_injection",
        "policy_vault",
        "rulesets",
        "instructions",
        "system",
        "system_prompt",
    }
)
_SANITIZER_MAX_DEPTH = 64
_SANITIZER_MAX_NODES = 10_000


def _safe_parameter_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "")).strip("_")
    return value or "parameter"


def _parameter_exists(node: Any, name: str) -> bool:
    return _parameter_by_name(node, name) is not None


def _parameter_by_name(node: Any, name: str) -> Any:
    try:
        getter = getattr(node, "get_parameter_by_name", None)
        if callable(getter):
            parameter = getter(name)
            if parameter is not None:
                return parameter
    except Exception:
        pass
    parameters = getattr(node, "parameters", {})
    if isinstance(parameters, dict):
        return parameters.get(name)
    try:
        return next(
            (
                parameter
                for parameter in parameters
                if getattr(parameter, "name", "") == name
            ),
            None,
        )
    except Exception:
        return None


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


def _agent_widget_shot_catalog(value: Any) -> dict[str, Any]:
    """Normalize the bounded catalog already accepted by same-flow Python routing."""

    required = {
        "schema",
        "version",
        "publisher_instance_uuid",
        "channel_uuid",
        "generation",
        "metadata_sha256",
        "shots",
    }
    if not isinstance(value, dict) or set(value) != required:
        return {}
    if value.get("schema") != "hmb-shot-routing-catalog" or value.get("version") != 1:
        return {}
    publisher = str(value.get("publisher_instance_uuid") or "").strip()
    channel = str(value.get("channel_uuid") or "").strip()
    metadata_sha256 = str(value.get("metadata_sha256") or "").strip().casefold()
    generation = value.get("generation")
    raw_shots = value.get("shots")
    if (
        not publisher
        or len(publisher) > 128
        or not channel
        or len(channel) > 128
        or not isinstance(generation, int)
        or isinstance(generation, bool)
        or not 1 <= generation <= (1 << 53) - 1
        or re.fullmatch(r"[0-9a-f]{64}", metadata_sha256) is None
        or not isinstance(raw_shots, list)
        or not 1 <= len(raw_shots) <= 5
    ):
        return {}
    shots: list[dict[str, Any]] = []
    shot_ids: set[str] = set()
    shot_numbers: set[int] = set()
    for raw in raw_shots:
        if not isinstance(raw, dict) or set(raw) != {
            "shot_uuid",
            "number",
            "name",
            "revision",
        }:
            return {}
        shot_uuid = str(raw.get("shot_uuid") or "").strip()
        name = " ".join(str(raw.get("name") or "").split())
        number = raw.get("number")
        revision = raw.get("revision")
        if (
            not shot_uuid
            or len(shot_uuid) > 128
            or shot_uuid in shot_ids
            or not name
            or len(name) > 128
            or not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= 5
            or number in shot_numbers
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or not 0 <= revision <= (1 << 53) - 1
        ):
            return {}
        shot_ids.add(shot_uuid)
        shot_numbers.add(number)
        shots.append(
            {
                "shot_uuid": shot_uuid,
                "number": number,
                "name": name,
                "revision": revision,
            }
        )
    shots.sort(key=lambda item: (item["number"], item["shot_uuid"]))
    return {
        "schema": "hmb-shot-routing-catalog",
        "version": 1,
        "publisher_instance_uuid": publisher,
        "channel_uuid": channel,
        "generation": generation,
        "metadata_sha256": metadata_sha256,
        "shots": shots,
    }


def _strict_agent_shot_catalog(value: Any) -> dict[str, Any]:
    """Validate one router-owned catalog or fail closed before state mutation."""

    normalized = _agent_widget_shot_catalog(value)
    if not normalized:
        raise RuntimeError("HMB Agent Shot catalog is invalid.")
    raw_shots = value.get("shots") if isinstance(value, dict) else None
    if not isinstance(raw_shots, list) or any(
        not isinstance(raw, dict)
        or raw.get("shot_uuid") != normalized_shot["shot_uuid"]
        or raw.get("number") != normalized_shot["number"]
        or raw.get("name") != normalized_shot["name"]
        or raw.get("revision") != normalized_shot["revision"]
        for raw, normalized_shot in zip(raw_shots, normalized["shots"])
    ):
        raise RuntimeError("HMB Agent Shot catalog is non-canonical.")
    numbers = [int(item["number"]) for item in normalized["shots"]]
    if numbers != list(range(1, len(numbers) + 1)):
        raise RuntimeError("HMB Agent Shot catalog numbering is invalid.")
    metadata_document = {
        "channel_uuid": normalized["channel_uuid"],
        "generation": normalized["generation"],
        "shots": normalized["shots"],
    }
    expected_hash = hashlib.sha256(
        json.dumps(
            metadata_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(normalized["metadata_sha256"], expected_hash):
        raise RuntimeError("HMB Agent Shot catalog metadata hash does not match.")
    return normalized


def _agent_widget_value(
    shot: dict[str, Any] | None = None,
    shot_catalog: Any = None,
    execution_phase: Any = "",
) -> dict[str, Any]:
    """Return display-only state. Internal policy text must never enter widget data."""
    shot_value = shot if isinstance(shot, dict) else {}
    shot_uuid = str(shot_value.get("shot_uuid") or "").strip()[:128]
    channel_uuid = str(shot_value.get("channel_uuid") or "").strip()[:128]
    bound = bool(shot_uuid and channel_uuid)
    try:
        shot_number = (
            max(1, min(5, int(shot_value.get("number") or 1)))
            if bound
            else 1
        )
    except (TypeError, ValueError, OverflowError):
        shot_number = 1
    catalog = _agent_widget_shot_catalog(shot_catalog)
    if catalog and bound and catalog["channel_uuid"] != channel_uuid:
        catalog = {}
    phase = str(execution_phase or "").strip().casefold()
    if phase not in {"", "authorizing", "preparing", "running"}:
        phase = ""
    return {
        "schema": "hmb-agent-ui",
        "schema_version": 2,
        "native_agent": True,
        "policy_vault": "sealed",
        "policy_injection": "runtime_only",
        "output_sanitizer": True,
        "execution_phase": phase,
        # Selector options are supplied only by the backend same-flow
        # reconciler. Browser-global discovery events never become authority.
        "shot_catalog": catalog,
        "shot": {
            "channel_uuid": channel_uuid if bound else "",
            "shot_uuid": shot_uuid if bound else "",
            "number": shot_number,
            "name": (
                " ".join(
                    str(
                        shot_value.get("name") or f"Shot {shot_number}"
                    ).split()
                )[:128]
                or f"Shot {shot_number}"
                if bound
                else "Only"
            ),
        },
    }


def _configure_agent_widget_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    try:
        current = None
        try:
            current = node_value = getattr(parameter, "value", None)
            if not isinstance(node_value, dict):
                current = getattr(parameter, "default_value", None)
        except Exception:
            current = getattr(parameter, "default_value", None)
        current_shot = current.get("shot") if isinstance(current, dict) else None
        current_catalog = (
            current.get("shot_catalog") if isinstance(current, dict) else None
        )
        parameter.default_value = _agent_widget_value(current_shot, current_catalog)
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
        parameter = _parameter_by_name(node, _AGENT_WIDGET_PARAMETER)
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
    ``HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.SHOT_PROMPT_IN``. Upstream nodes
    remain unrestricted because HMBPromptLibrary is responsible for accepting
    and composing them before this boundary.

    Host lookup failures raise instead of being mistaken for a verified absence
    of the HMB Prompt edge. The caller blocks execution with a visible error.
    Optional lookup callables make this graph contract independently testable.
    """

    try:
        # Never let a source retained by an earlier verification survive a
        # missing, foreign, or malformed edge on the next execution.
        setattr(node, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
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

        result = connection_lookup(_AGENT_SHOT_PROMPT_INPUT_PARAMETER, node_name)
        incoming = getattr(result, "incoming_connections", None)
        if incoming is None:
            raise RuntimeError("Prompt connection lookup result is unavailable.")
        if not isinstance(incoming, (list, tuple)):
            raise RuntimeError("Prompt connection lookup returned malformed data.")

        prompt_connections = [
            connection
            for connection in incoming
            if str(getattr(connection, "target_parameter_name", "") or "")
            == _AGENT_SHOT_PROMPT_INPUT_PARAMETER
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
        verified = (
            str(metadata.get("library") or "") == _HMB_LIBRARY_NAME
            and str(metadata.get("node_type") or "") == _HMB_PROMPT_NODE_TYPE
        )
        if not verified:
            return False
        # The exact registered source instance is the private paired-data
        # transport. PROMPT_OUT itself remains an ordinary human-readable str.
        setattr(node, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, source_node)
        return True
    except Exception as exc:
        raise RuntimeError(
            "HMBAgentLibrary Prompt connection topology could not be verified."
        ) from exc


def _prompt_transport_text(prompt_value: Any) -> str:
    value = getattr(prompt_value, "value", prompt_value)
    return str(value or "")


def _prompt_text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _paired_machine_prompt(node: Any, prompt_value: Any) -> str:
    """Return the machine envelope paired with one visible ``PROMPT_OUT``.

    A verified live HMB Prompt source must provide an exact, hashed paired
    snapshot. Content markers are not provenance and never activate a fallback
    transport path.
    """

    visible_prompt = _prompt_transport_text(prompt_value)
    source_node = getattr(node, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
    if source_node is None:
        raise RuntimeError("HMB Prompt paired snapshot source is unavailable.")

    snapshot_getter = getattr(source_node, "_hmb_agent_prompt_snapshot", None)
    if not callable(snapshot_getter):
        raise RuntimeError("HMB Prompt paired snapshot is unavailable.")
    snapshot = snapshot_getter(visible_prompt)
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != _PAIRED_PROMPT_SNAPSHOT_KEYS
        or snapshot.get("schema") != _PAIRED_PROMPT_SNAPSHOT_SCHEMA
        or snapshot.get("version") != _PAIRED_PROMPT_SNAPSHOT_VERSION
        or not isinstance(snapshot.get("generation"), int)
        or isinstance(snapshot.get("generation"), bool)
        or snapshot.get("generation") < 1
    ):
        raise RuntimeError("HMB Prompt paired snapshot shape is invalid.")

    visible_sha256 = snapshot.get("visible_sha256")
    machine_sha256 = snapshot.get("machine_sha256")
    machine_prompt = snapshot.get("machine_prompt")
    if (
        not visible_prompt
        or not isinstance(visible_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", visible_sha256) is None
        or not isinstance(machine_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", machine_sha256) is None
        or not isinstance(machine_prompt, str)
        or not machine_prompt
    ):
        raise RuntimeError("HMB Prompt paired snapshot fields are invalid.")
    if not hmac.compare_digest(
        visible_sha256,
        _prompt_text_sha256(visible_prompt),
    ):
        raise RuntimeError("HMB Prompt visible snapshot identity is invalid.")
    if not hmac.compare_digest(
        machine_sha256,
        _prompt_text_sha256(machine_prompt),
    ):
        raise RuntimeError("HMB Prompt machine snapshot identity is invalid.")
    return machine_prompt


def _split_behavior_rules(value: str, expected_count: int = 4) -> list[str]:
    """Split one Behavior document into the exact native rule-list entries."""
    text = str(value or "").lstrip("\ufeff").strip()
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




def _mapping_contains_agent_state(value: Any) -> bool:
    """Return whether a directly supplied structure resembles native Agent state.

    This lightweight boundary does not inspect prose or decode serialized,
    encoded, compressed, split, or otherwise transformed text.
    """
    stack: list[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    inspected = 0
    while stack:
        item, depth = stack.pop()
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
            if keys & _HMB_UNIQUE_RUNTIME_STATE_KEYS:
                return True
            if len(keys & _GENERIC_AGENT_STATE_KEYS) >= 2:
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
                (nested, depth + 1)
                for _key, nested in normalized_items
            )
            continue
        if isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend(
                (nested, depth + 1) for nested in item
            )
    return False


def _contains_public_output_state_leak(value: Any) -> bool:
    """Detect only directly supplied native Agent/runtime structures."""
    if isinstance(value, (dict, list, tuple)):
        return _mapping_contains_agent_state(value)
    return False


def _exact_policy_fragments(*documents: Any) -> tuple[str, ...]:
    """Return exact long server-policy strings for the no-exposure boundary.

    This is deliberately not a semantic, encoded, translated, or fuzzy output
    check.  It blocks only verbatim policy documents/rules and long verbatim
    policy lines that are present in memory for the current protected call.
    """

    fragments: set[str] = set()
    for document in documents:
        values = document if isinstance(document, (list, tuple)) else [document]
        for value in values:
            text = str(value or "").replace("\r\n", "\n").strip()
            if len(text) >= 32:
                fragments.add(text)
            for line in text.splitlines():
                exact_line = line.strip()
                if len(exact_line) >= 80:
                    fragments.add(exact_line)
    return tuple(sorted(fragments, key=len, reverse=True))


def _contains_exact_policy_text(
    value: Any,
    fragments: tuple[str, ...],
) -> bool:
    """Detect direct verbatim policy disclosure in a bounded output object."""

    if not fragments:
        return False
    stack: list[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    inspected = 0
    while stack:
        item, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return True
        if isinstance(item, str):
            candidate = item.replace("\r\n", "\n")
            if any(fragment in candidate for fragment in fragments):
                return True
            continue
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend((nested, depth + 1) for nested in item.values())
            continue
        if isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            stack.extend((nested, depth + 1) for nested in item)
    return False


def _is_native_error_artifact(value: Any) -> bool:
    """Recognize an error wrapper without reading or exposing its payload."""

    if isinstance(value, BaseException):
        return True
    if value is None:
        return False
    if "error" in value.__class__.__name__.casefold():
        return True
    try:
        return bool(getattr(value, "is_error", False))
    except Exception:
        return True







def _strip_sealed_state_from_agent_wrapper(value: Any) -> Any:
    """Remove private native state fields without inspecting policy text."""

    visited: set[int] = set()
    stack: list[tuple[Any, int]] = [(value, 0)]
    inspected = 0
    while stack:
        current, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            raise RuntimeError("Agent state sanitization budget exceeded.")
        if isinstance(current, dict):
            current_id = id(current)
            if current_id in visited:
                continue
            visited.add(current_id)
            for key, nested in list(current.items()):
                normalized_key = str(key or "").strip().casefold()
                if normalized_key in _SEALED_POLICY_STATE_KEYS:
                    current[key] = (
                        []
                        if normalized_key == "rulesets"
                        else _PUBLIC_OUTPUT_BLOCKED
                    )
                else:
                    stack.append((nested, depth + 1))
        elif isinstance(current, (list, tuple)):
            current_id = id(current)
            if current_id in visited:
                continue
            visited.add(current_id)
            stack.extend((item, depth + 1) for item in current)
    return value


def _strip_runtime_scope_from_agent_wrapper(value: Any) -> Any:
    """Remove transient derived scope while retaining public Prompt memory."""

    visited: set[int] = set()
    budget = [0]

    def scrub(item: Any, depth: int) -> Any:
        budget[0] += 1
        if budget[0] > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return _PUBLIC_OUTPUT_BLOCKED
        if isinstance(item, str):
            if _RUNTIME_FX_SCOPE_HEADER not in item:
                return item
            return item.split(_RUNTIME_FX_SCOPE_HEADER, 1)[0].rstrip()
        if isinstance(item, list):
            item_id = id(item)
            if item_id in visited:
                return _PUBLIC_OUTPUT_BLOCKED
            visited.add(item_id)
            for index, nested in enumerate(list(item)):
                item[index] = scrub(nested, depth + 1)
            return item
        if isinstance(item, tuple):
            item_id = id(item)
            if item_id in visited:
                return _PUBLIC_OUTPUT_BLOCKED
            visited.add(item_id)
            return tuple(scrub(nested, depth + 1) for nested in item)
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                return _PUBLIC_OUTPUT_BLOCKED
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
    requires those upstream sources itself. The model, schema, output handling,
    and Agent wire format remain owned by the Standard Library Agent. Canonical
    HMB execution swaps only the authenticated Prompt bytes and appends the two
    sealed Behaviors; caller context, memory, rulesets, tools, schema, and native
    execution settings otherwise remain unchanged. Once the canonical HMB
    Prompt edge is present, a missing or
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
        # Base Agent construction dispatches lifecycle callbacks through this
        # subclass. Initialize every field those callbacks can inspect before
        # calling ``super().__init__`` so the real Griptape host can instantiate
        # the node (the lightweight regression double does not expose this
        # ordering constraint).
        self._hmb_node_deleted = False
        self._hmb_lifecycle_generation = 1
        self._hmb_delete_parent_called = False
        self._hmb_rules_active = False
        self._hmb_policy = ""
        self._hmb_binding = ""
        self._hmb_policy_rules: list[str] = []
        self._hmb_binding_rules: list[str] = []
        self._hmb_ruleset_names: tuple[str, str] = ("", "")
        self._hmb_policy_identity: dict[str, str] = {}
        self._hmb_runtime_prompt = ""
        # The public prompt getter must never expose the private machine
        # envelope to host serialization/UI refreshes. It is readable only
        # while the native Agent generator is synchronously consuming inputs.
        self._hmb_native_prompt_read_active = False
        self._hmb_verified_prompt_source_node = None
        self._hmb_native_calls_this_process = 0
        self._hmb_last_sanitizer_status = "clean"
        self._hmb_suppress_visible_publication = False
        self._hmb_capture_publications = False
        self._hmb_publication_buffer: dict[str, str] = {
            "output": "",
            "logs": "",
        }
        self._hmb_scheduler_step_failed = False
        self._hmb_native_failure_stage = ""
        self._hmb_native_failure_code = ""
        self._hmb_shot_context: dict[str, Any] = {}
        self._hmb_shot_catalog_snapshot: dict[str, Any] = {}
        # Instance-local execution authority.  Display widget writes and
        # same-flow route callbacks may interleave while several Agents run,
        # but they must not change the exact Shot being consumed by this run.
        self._hmb_execution_shot_binding: dict[str, Any] = {}
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_shot_clear_syncing = False
        self._hmb_shot_catalog_syncing = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        # The router-owned SHOT_PROMPT_IN remains the only authoritative HMB
        # execution input.  These fields only mirror its public, user-readable
        # document into the native Agent prompt editor while a Shot is active.
        self._hmb_prompt_preview_syncing = False
        self._hmb_prompt_preview_active = False
        self._hmb_prompt_preview_value = ""
        self._hmb_prompt_before_preview = ""
        super().__init__(**kwargs)
        self.category = "HMB_GP_Production"
        self.description = "HMBAgentLibrary"
        self._prepare_hmb_node_surface()
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile

            schedule_post_registration_reconcile(self)
        except Exception:
            pass

    def _prepare_hmb_node_surface(self) -> None:
        """Register or restore the idempotent node surface for this lifecycle."""

        # Saved workflows may restore stale native labels and custom-widget UI
        # options after construction. Every deserialize must therefore run the
        # idempotent surface normalizers again instead of being skipped by a
        # construction-only guard.
        self._ensure_hmb_shot_prompt_input()
        self._remove_legacy_hmb_elements()
        _configure_native_output_ports(self)
        _ensure_agent_state_warning(self)
        _ensure_hmb_policy_warning(self)
        _ensure_hmb_topology_warning(self)
        _ensure_agent_widget(self)

    def _ensure_hmb_shot_prompt_input(self) -> None:
        """Register the private, router-owned Prompt dependency port.

        The built-in public ``prompt`` parameter stays untouched so an Agent
        without a routed Shot is byte-for-byte the Standard Agent path. Runtime
        values on this hidden port are never serialized; hydration recreates
        only the graph edge from authoritative Shot identity.
        """

        try:
            existing = self.get_parameter_by_name(_AGENT_SHOT_PROMPT_INPUT_PARAMETER)
        except Exception:
            existing = None
        hidden_ui = {
            "display_name": "",
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "hide_handles": True,
            "height": 1,
            "min_height": 0,
            "max_height": 1,
            "is_full_width": True,
        }
        if existing is not None:
            try:
                existing.ui_options = {
                    **dict(getattr(existing, "ui_options", {}) or {}),
                    **hidden_ui,
                }
            except Exception:
                pass
            return
        kwargs: dict[str, Any] = {
            "name": _AGENT_SHOT_PROMPT_INPUT_PARAMETER,
            "type": "str",
            "input_types": ["str"],
            "default_value": "",
            "tooltip": "Hidden Prompt dependency for the selected production Shot.",
            "hide": True,
            "hide_property": True,
            "hide_label": True,
            "serializable": False,
            "ui_options": hidden_ui,
        }
        if ParameterMode is not None:
            kwargs["allowed_modes"] = {ParameterMode.INPUT}
        else:
            kwargs.update({
                "allow_input": True,
                "allow_property": False,
                "allow_output": False,
            })
        self.add_parameter(Parameter(**kwargs))

    @staticmethod
    def _normalize_shot_context(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        required = {
            "schema",
            "version",
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
            "prompt_generation",
            "visible_prompt_sha256",
            "image_media_sha256",
            "video_media_sha256",
        }
        if set(value) != required:
            return {}
        if (
            value.get("schema") != _AGENT_SHOT_CONTEXT_SCHEMA
            or value.get("version") != _AGENT_SHOT_CONTEXT_VERSION
        ):
            return {}
        hashes = (
            value.get("visible_prompt_sha256"),
            value.get("image_media_sha256"),
            value.get("video_media_sha256"),
        )
        if any(not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None for item in hashes):
            return {}
        channel_uuid = str(value.get("channel_uuid") or "").strip()
        shot_uuid = str(value.get("shot_uuid") or "").strip()
        if not channel_uuid or not shot_uuid:
            return {}
        try:
            raw_shot_number = value.get("shot_number")
            if isinstance(raw_shot_number, bool):
                return {}
            shot_number = int(raw_shot_number)
            generation = int(value.get("prompt_generation"))
        except (TypeError, ValueError, OverflowError):
            return {}
        if not (1 <= shot_number <= 5 and generation >= 1):
            return {}
        return {
            "schema": _AGENT_SHOT_CONTEXT_SCHEMA,
            "version": _AGENT_SHOT_CONTEXT_VERSION,
            "channel_uuid": channel_uuid[:128],
            "shot_uuid": shot_uuid[:128],
            "shot_number": shot_number,
            "shot_name": " ".join(str(value.get("shot_name") or f"Shot {shot_number}").split())[:128],
            "prompt_generation": generation,
            "visible_prompt_sha256": str(hashes[0]),
            "image_media_sha256": str(hashes[1]),
            "video_media_sha256": str(hashes[2]),
        }

    @staticmethod
    def _normalize_execution_shot_binding(value: Any) -> dict[str, Any]:
        """Return one strict, instance-owned Agent subscription or no binding."""

        required = {
            "schema",
            "version",
            "participant_kind",
            "enabled",
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
        }
        if (
            not isinstance(value, dict)
            or set(value) != required
            or value.get("schema") != "hmb-shot-channel-subscription"
            or value.get("version") != 1
            or value.get("participant_kind") != "agent"
            or value.get("enabled") is not True
        ):
            return {}
        channel_uuid = str(value.get("channel_uuid") or "").strip()[:128]
        shot_uuid = str(value.get("shot_uuid") or "").strip()[:128]
        if not channel_uuid or not shot_uuid:
            return {}
        try:
            shot_number = int(value.get("shot_number"))
        except (TypeError, ValueError, OverflowError):
            return {}
        if not 1 <= shot_number <= 5:
            return {}
        shot_name = " ".join(
            str(value.get("shot_name") or f"Shot {shot_number}").split()
        )[:128] or f"Shot {shot_number}"
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "agent",
            "enabled": True,
            "channel_uuid": channel_uuid,
            "shot_uuid": shot_uuid,
            "shot_number": shot_number,
            "shot_name": shot_name,
        }

    def _capture_execution_shot_binding(
        self,
        verified_subscription: Any = None,
    ) -> dict[str, Any]:
        """Freeze the strict Shot selected when protected execution starts."""

        self._hmb_execution_shot_binding = {}
        binding = self._normalize_execution_shot_binding(
            self._hmb_shot_channel_subscription()
            if verified_subscription is None
            else verified_subscription
        )
        if not binding:
            raise RuntimeError("HMB Agent execution Shot identity is unavailable.")
        self._hmb_execution_shot_binding = dict(binding)
        return dict(binding)

    def _clear_execution_shot_binding(self) -> None:
        self._hmb_execution_shot_binding = {}

    def _adopt_verified_execution_shot_binding(
        self,
        verified_subscription: Any,
    ) -> dict[str, Any]:
        """Adopt a verified Shot, while preserving canonical HMB Prompt Only."""

        if verified_subscription == {}:
            self._clear_execution_shot_binding()
            return {}
        return self._capture_execution_shot_binding(verified_subscription)

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return {
                "schema": "hmb-shot-channel-subscription",
                "version": 1,
                "participant_kind": "agent",
                "enabled": False,
                "channel_uuid": "",
                "shot_uuid": "",
                "shot_number": 1,
                "shot_name": "Only",
            }
        execution_binding = self._normalize_execution_shot_binding(
            getattr(self, "_hmb_execution_shot_binding", {})
        )
        if execution_binding:
            return execution_binding
        context = getattr(self, "_hmb_shot_context", {})
        if not isinstance(context, dict):
            context = {}
        shot = {}
        widget_authoritative = False
        try:
            parameter = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            if parameter is None:
                raise LookupError(_AGENT_WIDGET_PARAMETER)
            try:
                raw = super().get_parameter_value(_AGENT_WIDGET_PARAMETER)
            except Exception:
                raw = getattr(parameter, "default_value", None)
            if isinstance(raw, dict) and isinstance(raw.get("shot"), dict):
                shot = raw["shot"]
                widget_authoritative = True
        except Exception:
            pass
        channel_uuid = str(
            (
                shot.get("channel_uuid")
                if widget_authoritative
                else context.get("channel_uuid")
            )
            or ""
        )[:128]
        shot_uuid = str(
            (
                shot.get("shot_uuid")
                if widget_authoritative
                else context.get("shot_uuid")
            )
            or ""
        )[:128]
        bound = bool(channel_uuid and shot_uuid)
        try:
            number = max(
                1,
                min(
                    5,
                    int(
                        (shot.get("number") if widget_authoritative else context.get("shot_number"))
                        or 1
                    ),
                ),
            )
        except (TypeError, ValueError, OverflowError):
            number = 1
        name = (
            " ".join(
                str(
                    (shot.get("name") if widget_authoritative else context.get("shot_name"))
                    or f"Shot {number}"
                ).split()
            )[:128]
            if bound
            else "Only"
        )
        return {
            "schema": "hmb-shot-channel-subscription",
            "version": 1,
            "participant_kind": "agent",
            "enabled": bound,
            "channel_uuid": channel_uuid if bound else "",
            "shot_uuid": shot_uuid if bound else "",
            "shot_number": number if bound else 1,
            "shot_name": name if bound else "Only",
        }

    def _hmb_clear_shot_routing_catalog(
        self, reason: str = "publisher_unavailable"
    ) -> dict[str, Any]:
        """Return to independent Only mode without touching native Agent output."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()

        self._hmb_shot_catalog_snapshot = {}
        self._hmb_shot_context = {}
        self._clear_execution_shot_binding()
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "publisher_unavailable")[:128],
        }
        try:
            parameter = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            if parameter is None:
                raise LookupError(_AGENT_WIDGET_PARAMETER)
            try:
                current_ui = super().get_parameter_value(
                    _AGENT_WIDGET_PARAMETER
                )
            except Exception:
                current_ui = getattr(parameter, "default_value", None)
            next_ui = _agent_widget_value()
            if current_ui != next_ui:
                self._hmb_shot_clear_syncing = True
                try:
                    self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_ui)
                    parameter.default_value = next_ui
                finally:
                    self._hmb_shot_clear_syncing = False
        except Exception:
            self._hmb_shot_clear_syncing = False
        self._set_native_prompt_preview("", enabled=False)
        return self._hmb_shot_channel_subscription()

    def _hmb_post_registration_shot_discovery(self) -> None:
        """Discover an already-running Prompt Shot for a newly added Agent."""

        if (
            bool(getattr(self, "_hmb_node_deleted", False))
            or not bool(
                getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
            )
        ):
            return
        self._refresh_agent_shot_route()
        self._refresh_routed_prompt_preview()

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        """Capture one unambiguous existing Prompt UUID before catalog adoption."""

        if not bool(
            getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
        ):
            return
        current = self._hmb_shot_channel_subscription()
        if current.get("enabled"):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            return
        self._hmb_initial_shot_preferred_uuid = str(shot_uuid or "").strip()[:128]

    def _hmb_available_agent_shot_catalog(
        self,
        snapshot: Any,
        current_shot: Any = None,
    ) -> dict[str, Any]:
        """Expose only Prompt-owned Shots not claimed by another Agent.

        ImageAsset owns the signed five-Shot catalog, but Agent can execute a
        remote Shot only when one exact Prompt node owns that UUID.  Projecting
        the catalog through the live same-flow Prompt subscriptions keeps the
        selector useful and prevents options that would immediately fail with
        ``prompt_unavailable``.  This Agent's current Shot stays visible while
        another Agent cannot claim it.
        """

        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("shots"), list):
            return {}
        channel_uuid = str(snapshot.get("channel_uuid") or "")
        current = (
            current_shot
            if isinstance(current_shot, dict)
            else self._hmb_shot_channel_subscription()
        )
        claimed: set[str] = set()
        prompt_owned: set[str] = set()
        try:
            from _hmb_shot_routing import _same_flow_nodes

            _flow_name, nodes = _same_flow_nodes(self)
        except Exception:
            nodes = []
        for candidate in nodes:
            if candidate is self or bool(getattr(candidate, "_hmb_node_deleted", False)):
                continue
            getter = getattr(candidate, "_hmb_shot_channel_subscription", None)
            if not callable(getter):
                continue
            try:
                subscription = getter()
            except Exception:
                continue
            if not isinstance(subscription, dict):
                continue
            participant_kind = str(
                subscription.get("participant_kind") or ""
            )
            subscription_uuid = str(subscription.get("shot_uuid") or "")
            if (
                subscription.get("enabled")
                and subscription.get("channel_uuid") == channel_uuid
                and subscription_uuid
            ):
                if participant_kind == "prompt":
                    prompt_owned.add(subscription_uuid)
                elif participant_kind == "agent":
                    claimed.add(subscription_uuid)
        current_uuid = (
            str(current.get("shot_uuid") or "")
            if current.get("channel_uuid") == channel_uuid
            else ""
        )
        shots = [
            dict(item)
            for item in snapshot["shots"]
            if isinstance(item, dict)
            and str(item.get("shot_uuid") or "") in prompt_owned
            and (
                str(item.get("shot_uuid") or "") not in claimed
                or str(item.get("shot_uuid") or "") == current_uuid
            )
        ]
        return {**snapshot, "shots": shots} if shots else {}

    def _hmb_reject_duplicate_shot_selection(
        self, reason: str = "duplicate_agent_shot"
    ) -> dict[str, Any]:
        """Return this Agent to Only while retaining its validated Shot list."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return self._hmb_shot_channel_subscription()
        self._hmb_shot_context = {}
        self._clear_execution_shot_binding()
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_shot_route_status = {
            "ok": False,
            "code": str(reason or "duplicate_agent_shot")[:128],
        }
        try:
            parameter = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            if parameter is None:
                raise LookupError(_AGENT_WIDGET_PARAMETER)
            catalog = self._hmb_available_agent_shot_catalog(
                self._hmb_shot_catalog_snapshot,
                {},
            )
            next_ui = _agent_widget_value({}, catalog)
            self._hmb_shot_clear_syncing = True
            try:
                self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_ui)
                parameter.default_value = next_ui
            finally:
                self._hmb_shot_clear_syncing = False
        except Exception:
            self._hmb_shot_clear_syncing = False
        self._set_native_prompt_preview("", enabled=False)
        return self._hmb_shot_channel_subscription()

    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        """Adopt only the compact active-shot identity from an ImageAsset catalog."""
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        # Router delivery is a trust boundary.  Returning silently on malformed
        # input made the central reconciler report success while this Agent kept
        # a stale selector and hidden edge.  Validate before touching any local
        # state and raise so the router can mark this participant
        # ``catalog_rejected`` and clear its managed dependencies.
        snapshot = _strict_agent_shot_catalog(snapshot)
        if (
            not isinstance(snapshot, dict)
            or set(snapshot) != {
                "schema",
                "version",
                "publisher_instance_uuid",
                "channel_uuid",
                "generation",
                "metadata_sha256",
                "shots",
            }
            or snapshot.get("schema") != "hmb-shot-routing-catalog"
            or snapshot.get("version") != 1
        ):
            return
        publisher_uuid = str(snapshot.get("publisher_instance_uuid") or "")
        channel_uuid = str(snapshot.get("channel_uuid") or "")
        shots = snapshot.get("shots")
        if (
            not publisher_uuid
            or len(publisher_uuid) > 128
            or publisher_uuid != publisher_uuid.strip()
            or not channel_uuid
            or len(channel_uuid) > 128
            or channel_uuid != channel_uuid.strip()
            or not isinstance(snapshot.get("generation"), int)
            or isinstance(snapshot.get("generation"), bool)
            or not 1 <= snapshot["generation"] <= (1 << 53) - 1
            or not isinstance(shots, list)
            or not 1 <= len(shots) <= 5
            or any(
                not isinstance(item, dict)
                or set(item) != {"shot_uuid", "number", "name", "revision"}
                or not isinstance(item.get("shot_uuid"), str)
                or not item["shot_uuid"]
                or len(item["shot_uuid"]) > 128
                or item["shot_uuid"] != item["shot_uuid"].strip()
                or not isinstance(item.get("number"), int)
                or isinstance(item.get("number"), bool)
                or not 1 <= item["number"] <= 5
                or not isinstance(item.get("revision"), int)
                or isinstance(item.get("revision"), bool)
                or not 0 <= item["revision"] <= (1 << 53) - 1
                or not isinstance(item.get("name"), str)
                or not item["name"]
                or len(item["name"]) > 128
                or item["name"] != " ".join(item["name"].split())
                for item in shots
            )
            or len({str(item["shot_uuid"]) for item in shots}) != len(shots)
            or len({int(item["number"]) for item in shots}) != len(shots)
            or sorted(int(item["number"]) for item in shots)
            != list(range(1, len(shots) + 1))
        ):
            return
        catalog_document = {
            "channel_uuid": channel_uuid,
            "generation": snapshot["generation"],
            "shots": shots,
        }
        canonical = json.dumps(
            catalog_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if not hmac.compare_digest(
            str(snapshot.get("metadata_sha256") or "").casefold(),
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        ):
            return
        previous = getattr(self, "_hmb_shot_catalog_snapshot", None)
        if isinstance(previous, dict) and previous.get("channel_uuid") == channel_uuid:
            previous_generation = int(previous.get("generation") or 0)
            if snapshot["generation"] < previous_generation:
                return
            if (
                snapshot["generation"] == previous_generation
                and snapshot["metadata_sha256"]
                != previous.get("metadata_sha256")
            ):
                return
        self._hmb_shot_catalog_snapshot = {
            "schema": snapshot["schema"],
            "version": snapshot["version"],
            "publisher_instance_uuid": publisher_uuid,
            "channel_uuid": channel_uuid,
            "generation": snapshot["generation"],
            "metadata_sha256": snapshot["metadata_sha256"],
            "shots": [dict(item) for item in shots],
        }
        current = self._hmb_shot_channel_subscription()
        selected = next(
            (item for item in shots if isinstance(item, dict) and str(item.get("shot_uuid") or "") == current["shot_uuid"]),
            None,
        )
        initial_autoclaim = bool(
            selected is None
            and not current.get("channel_uuid")
            and not current.get("shot_uuid")
            and getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
            and getattr(self, "_hmb_initial_shot_preferred_uuid", "")
        )
        if initial_autoclaim:
            preferred_uuid = str(
                getattr(self, "_hmb_initial_shot_preferred_uuid", "") or ""
            )
            selected = next(
                (
                    item
                    for item in shots
                    if isinstance(item, dict)
                    and str(item.get("shot_uuid") or "") == preferred_uuid
                ),
                None,
            )
        if isinstance(selected, dict):
            try:
                number = max(1, min(5, int(selected.get("number") or 1)))
            except (TypeError, ValueError, OverflowError):
                return
            shot = {
                "channel_uuid": channel_uuid,
                "shot_uuid": str(selected.get("shot_uuid") or "")[:128],
                "number": number,
                "name": " ".join(
                    str(selected.get("name") or f"Shot {number}").split()
                )[:128],
            }
            if not shot["shot_uuid"]:
                return
            if initial_autoclaim:
                self._hmb_initial_shot_autoclaim_pending = False
                self._hmb_initial_shot_preferred_uuid = ""
        else:
            # A catalog is an option source only. Blank recipients stay Only,
            # and deletion of the active UUID safely returns to Only while the
            # renumbered remote choices remain visible.
            shot = {
                "channel_uuid": "",
                "shot_uuid": "",
                "number": 1,
                "name": "Only",
            }
        try:
            parameter = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            if parameter is None:
                raise LookupError(_AGENT_WIDGET_PARAMETER)
            try:
                current_ui = super().get_parameter_value(_AGENT_WIDGET_PARAMETER)
            except Exception:
                current_ui = getattr(parameter, "default_value", None)
            next_ui = _agent_widget_value(
                shot,
                self._hmb_available_agent_shot_catalog(
                    self._hmb_shot_catalog_snapshot
                ),
            )
            if current_ui != next_ui:
                self._hmb_shot_catalog_syncing = True
                try:
                    self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_ui)
                    parameter.default_value = next_ui
                finally:
                    self._hmb_shot_catalog_syncing = False
        except Exception:
            self._hmb_shot_catalog_syncing = False
            pass

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        if isinstance(value, dict):
            self._hmb_shot_route_status = dict(value)

    def _refresh_agent_shot_route(self, *, strict: bool = False) -> dict[str, Any]:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return {"ok": False, "code": "deleted", "changed": 0}
        try:
            enabled = bool(self._hmb_shot_channel_subscription().get("enabled"))
        except Exception:
            enabled = False
        try:
            from _hmb_shot_routing import reconcile_shot_routing

            result = reconcile_shot_routing(self)
        except Exception:
            if strict and enabled:
                raise RuntimeError("HMB Agent Shot routing is unavailable.") from None
            return {"ok": False, "code": "unavailable", "changed": 0}
        if strict and enabled:
            if not isinstance(result, dict):
                raise RuntimeError("HMB Agent Shot routing is incomplete.")
            prefix = str(getattr(self, "name", "") or "") + ":"
            failures = result.get("failures")
            own_failures = [
                str(item)
                for item in (
                    failures if isinstance(failures, (list, tuple)) else ()
                )
                if str(item).startswith(prefix)
            ]
            if own_failures:
                raise RuntimeError("HMB Agent Shot routing is incomplete.")
        return result if isinstance(result, dict) else {
            "ok": False,
            "code": "invalid_result",
            "changed": 0,
        }

    def _assert_exact_prompt_shot_route(self) -> dict[str, Any]:
        """Return the Agent identity only after its exact Prompt route is verified."""

        subscription = self._hmb_shot_channel_subscription()
        source_node = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
        getter = getattr(source_node, "_hmb_shot_channel_subscription", None)
        try:
            source_subscription = getter() if callable(getter) else None
        except Exception as exc:
            raise RuntimeError("HMB Prompt Shot identity is unavailable.") from exc
        exact_fields = (
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
        )
        if not isinstance(source_subscription, dict):
            # Compatibility with Prompt-only policy tests/older Prompt nodes is
            # allowed only while this Agent is also in independent Only mode.
            if subscription.get("enabled"):
                raise RuntimeError("HMB Prompt Shot identity is unavailable.")
            return {}
        if source_subscription.get("participant_kind") != "prompt":
            raise RuntimeError("HMB Prompt Shot identity is invalid.")
        source_enabled = bool(source_subscription.get("enabled"))
        agent_enabled = bool(subscription.get("enabled"))
        if source_enabled != agent_enabled:
            raise RuntimeError("HMB Prompt and Agent Shot identities do not match.")
        if not agent_enabled:
            return {}
        verified_subscription = HMBAgentLibrary._normalize_execution_shot_binding(
            subscription
        )
        if not verified_subscription:
            raise RuntimeError("HMB Agent Shot identity is invalid.")
        status = getattr(self, "_hmb_shot_route_status", None)
        if (
            not isinstance(status, dict)
            or not status.get("ok")
            or str(status.get("code") or "") != "ready"
            or any(
                source_subscription.get(key) != subscription.get(key)
                for key in exact_fields
            )
        ):
            raise RuntimeError("HMB Agent Shot routing is not ready.")
        source_status = getattr(source_node, "_hmb_shot_route_status", None)
        if (
            not isinstance(source_status, dict)
            or not source_status.get("ok")
            or str(source_status.get("code") or "") != "ready"
        ):
            raise RuntimeError("HMB Prompt Shot routing is not ready.")
        routed_prompt = self._native_parameter_value(
            _AGENT_SHOT_PROMPT_INPUT_PARAMETER,
            "",
        )
        if not str(getattr(routed_prompt, "value", routed_prompt) or ""):
            raise RuntimeError("HMB Prompt Shot value is unavailable.")
        return verified_subscription

    def _native_parameter_value(self, name: str, default: Any = "") -> Any:
        """Read a native value without the protected-runtime prompt override."""

        try:
            return super().get_parameter_value(name)
        except Exception:
            parameter = _parameter_by_name(self, name)
            return getattr(parameter, "default_value", default) if parameter else default

    def _matches_active_private_runtime_prompt(self, value: Any) -> bool:
        """Match only this execution's exact private prompt bytes.

        Content markers alone are not sufficient: an Only-mode user is free to
        author text that happens to resemble the HMB machine envelope.
        """

        runtime_prompt = str(getattr(self, "_hmb_runtime_prompt", "") or "")
        candidate = str(getattr(value, "value", value) or "")
        return bool(
            runtime_prompt
            and candidate
            and hmac.compare_digest(candidate, runtime_prompt)
        )

    def _set_native_prompt_preview(self, value: Any, *, enabled: bool) -> None:
        """Show the routed Prompt document without changing HMB execution input.

        The hidden SHOT_PROMPT_IN edge remains the authority used by process().
        The public prompt field is a reversible display mirror: entering Shot
        mode saves the user's Only-mode prompt, and leaving restores it unless
        the user deliberately edited the public field while the mirror was up.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)) or bool(
            getattr(self, "_hmb_prompt_preview_syncing", False)
        ):
            return
        preview = str(value or "") if enabled else ""
        current = str(
            self._native_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, "") or ""
        )
        active = bool(getattr(self, "_hmb_prompt_preview_active", False))
        previous_preview = str(
            getattr(self, "_hmb_prompt_preview_value", "") or ""
        )
        current_is_private = self._matches_active_private_runtime_prompt(current)
        target = current
        if preview:
            if not active:
                # A restored workflow can already contain the last mirrored
                # value.  Do not mistake that value for the user's manual
                # Only-mode prompt.
                self._hmb_prompt_before_preview = (
                    "" if current == preview or current_is_private else current
                )
            elif current != previous_preview and not current_is_private:
                # Preserve a deliberate edit made while the Shot was active.
                self._hmb_prompt_before_preview = current
            target = preview
            self._hmb_prompt_preview_active = True
            self._hmb_prompt_preview_value = preview
        else:
            if active and (current == previous_preview or current_is_private):
                target = str(
                    getattr(self, "_hmb_prompt_before_preview", "") or ""
                )
            elif current_is_private:
                target = ""
            self._hmb_prompt_preview_active = False
            self._hmb_prompt_preview_value = ""
            self._hmb_prompt_before_preview = ""

        if target == current or _parameter_by_name(
            self, _AGENT_PROMPT_INPUT_PARAMETER
        ) is None:
            return
        self._hmb_prompt_preview_syncing = True
        try:
            self.set_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, target)
        finally:
            self._hmb_prompt_preview_syncing = False

    def _public_prompt_value_after_private_echo(self, value: Any) -> Any:
        """Replace a host echo of the private runtime envelope with safe UI text."""

        if not self._matches_active_private_runtime_prompt(value):
            return value
        candidates = (
            getattr(self, "_hmb_prompt_preview_value", ""),
            self._native_parameter_value(_AGENT_SHOT_PROMPT_INPUT_PARAMETER, ""),
            getattr(self, "_hmb_prompt_before_preview", ""),
            self._native_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, ""),
        )
        for candidate in candidates:
            candidate_value = getattr(candidate, "value", candidate)
            if candidate_value and not self._matches_active_private_runtime_prompt(
                candidate_value
            ):
                return candidate_value
        return ""

    def _refresh_routed_prompt_preview(self) -> None:
        """Project the selected Shot's visible Prompt into the native editor."""

        try:
            enabled = bool(
                self._hmb_shot_channel_subscription().get("enabled")
            )
        except Exception:
            enabled = False
        value = self._native_parameter_value(
            _AGENT_SHOT_PROMPT_INPUT_PARAMETER, ""
        )
        self._set_native_prompt_preview(value, enabled=enabled)

    def _hmb_hydrate_shot_prompt_from_source(
        self,
        source_node: Any,
        source_parameter_name: str = _HMB_PROMPT_OUTPUT_PARAMETER,
    ) -> bool:
        """Copy one exact Prompt output into the non-serializable routed input.

        Connection creation normally invokes ``after_incoming_connection``.
        Deserialization of an already-existing managed edge does not, so the
        central router also calls this idempotent method after proving the exact
        same-Shot source.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        source_name = str(source_parameter_name or "").strip()
        if source_name != _HMB_PROMPT_OUTPUT_PARAMETER or source_node is None:
            return False
        sentinel = object()
        value: Any = sentinel
        outputs = getattr(source_node, "parameter_output_values", {})
        if isinstance(outputs, dict) and source_name in outputs:
            value = outputs[source_name]
        if value is sentinel:
            values = getattr(source_node, "parameter_values", {})
            if isinstance(values, dict) and source_name in values:
                value = values[source_name]
        if value is sentinel:
            getter = getattr(source_node, "get_parameter_value", None)
            if callable(getter):
                try:
                    value = getter(source_name)
                except Exception:
                    value = sentinel
        if value is sentinel:
            return False
        self.set_parameter_value(_AGENT_SHOT_PROMPT_INPUT_PARAMETER, value)
        self._refresh_routed_prompt_preview()
        return True

    def before_value_set(self, parameter, value):
        """Keep the backend-accepted Shot catalog authoritative over widget echoes."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return value
        normalized = value
        parameter_name = str(getattr(parameter, "name", "") or "")
        if parameter_name == _AGENT_PROMPT_INPUT_PARAMETER:
            normalized = self._public_prompt_value_after_private_echo(value)
        elif parameter_name == _AGENT_WIDGET_PARAMETER:
            authoritative_catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
            if not authoritative_catalog and isinstance(value, dict):
                authoritative_catalog = value.get("shot_catalog")
            available_catalog = self._hmb_available_agent_shot_catalog(
                authoritative_catalog
            )
            requested_shot = (
                value.get("shot") if isinstance(value, dict) else None
            )
            execution_binding = self._normalize_execution_shot_binding(
                getattr(self, "_hmb_execution_shot_binding", {})
            )
            if execution_binding:
                # The selector is disabled during execution, but retained-mode
                # echoes and route callbacks can still write its display dict.
                # Preserve the exact per-node binding captured at process start.
                requested_shot = {
                    "channel_uuid": execution_binding["channel_uuid"],
                    "shot_uuid": execution_binding["shot_uuid"],
                    "number": execution_binding["shot_number"],
                    "name": execution_binding["shot_name"],
                }
            requested_uuid = str(
                requested_shot.get("shot_uuid")
                if isinstance(requested_shot, dict)
                else ""
            )
            available_uuids = {
                str(item.get("shot_uuid") or "")
                for item in available_catalog.get("shots", [])
            }
            if requested_uuid and requested_uuid not in available_uuids:
                current = self._hmb_shot_channel_subscription()
                requested_shot = {
                    "channel_uuid": current.get("channel_uuid", ""),
                    "shot_uuid": current.get("shot_uuid", ""),
                    "number": current.get("shot_number", 1),
                    "name": current.get("shot_name", "Only"),
                }
            normalized = _agent_widget_value(
                requested_shot,
                available_catalog,
                value.get("execution_phase", "")
                if isinstance(value, dict)
                else "",
            )
        parent = getattr(super(), "before_value_set", None)
        if callable(parent):
            parent_value = parent(parameter, normalized)
            if parent_value is not None:
                normalized = parent_value
        return normalized

    def after_value_set(self, parameter, value):
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        parent = getattr(super(), "after_value_set", None)
        result = parent(parameter, value) if callable(parent) else None
        if str(getattr(parameter, "name", "") or "") == _AGENT_WIDGET_PARAMETER:
            authoritative_catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
            if not authoritative_catalog and isinstance(value, dict):
                authoritative_catalog = value.get("shot_catalog")
            available_catalog = self._hmb_available_agent_shot_catalog(
                authoritative_catalog
            )
            requested_shot = (
                value.get("shot") if isinstance(value, dict) else None
            )
            requested_uuid = str(
                requested_shot.get("shot_uuid")
                if isinstance(requested_shot, dict)
                else ""
            )
            available_uuids = {
                str(item.get("shot_uuid") or "")
                for item in available_catalog.get("shots", [])
            }
            if requested_uuid and requested_uuid not in available_uuids:
                current = self._hmb_shot_channel_subscription()
                requested_shot = {
                    "channel_uuid": current.get("channel_uuid", ""),
                    "shot_uuid": current.get("shot_uuid", ""),
                    "number": current.get("shot_number", 1),
                    "name": current.get("shot_name", "Only"),
                }
            normalized = _agent_widget_value(
                requested_shot,
                available_catalog,
                value.get("execution_phase", "")
                if isinstance(value, dict)
                else "",
            )
            try:
                parameter.default_value = normalized
            except Exception:
                pass
            execution_binding = self._normalize_execution_shot_binding(
                getattr(self, "_hmb_execution_shot_binding", {})
            )
            selected = normalized.get("shot", {})
            previous = getattr(self, "_hmb_shot_context", {})
            if (
                not execution_binding
                and isinstance(previous, dict)
                and previous.get("channel_uuid")
                and any(
                    previous.get(key) != selected.get(selected_key)
                    for key, selected_key in (
                        ("channel_uuid", "channel_uuid"),
                        ("shot_uuid", "shot_uuid"),
                        ("shot_number", "number"),
                        ("shot_name", "name"),
                    )
                )
            ):
                # A real Only/Shot change clears only the former route context;
                # FINAL TEXT remains an ordinary public Agent result.
                self._hmb_shot_context = {}
                setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            if (
                not getattr(self, "_hmb_shot_clear_syncing", False)
                and not getattr(self, "_hmb_execution_phase_syncing", False)
            ):
                if not getattr(self, "_hmb_shot_catalog_syncing", False):
                    self._hmb_initial_shot_autoclaim_pending = False
                    self._hmb_initial_shot_preferred_uuid = ""
                self._refresh_agent_shot_route()
            self._refresh_routed_prompt_preview()
        elif str(getattr(parameter, "name", "") or "") == _AGENT_SHOT_PROMPT_INPUT_PARAMETER:
            self._refresh_routed_prompt_preview()
        return result

    @staticmethod
    def _publication_parameter_name(value: Any) -> str:
        return str(getattr(value, "name", value) or "").strip().casefold()

    def set_parameter_value(self, name, value, *args, **kwargs):
        """Buffer protected output/log writes until final sanitization."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        normalized_name = self._publication_parameter_name(name)
        if normalized_name == _AGENT_PROMPT_INPUT_PARAMETER.casefold():
            value = self._public_prompt_value_after_private_echo(value)
        if getattr(self, "_hmb_capture_publications", False) and normalized_name in {
            "output",
            "logs",
        }:
            self._hmb_publication_buffer[normalized_name] = str(value or "")
            return None
        result = super().set_parameter_value(name, value, *args, **kwargs)
        if (
            normalized_name == _AGENT_SHOT_PROMPT_INPUT_PARAMETER.casefold()
            and not bool(getattr(self, "_hmb_prompt_preview_syncing", False))
        ):
            self._refresh_routed_prompt_preview()
        if (
            normalized_name == _AGENT_WIDGET_PARAMETER.casefold()
            and bool(kwargs.get("initial_setup", False))
        ):
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_initial_shot_preferred_uuid = ""
            try:
                from _hmb_shot_routing import schedule_post_hydration_reconcile

                schedule_post_hydration_reconcile(self)
            except Exception:
                pass
        return result

    def append_value_to_parameter(self, name, value=None, *args, **kwargs):
        """Keep native stream chunks private during a protected execution."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        normalized_name = self._publication_parameter_name(name)
        if getattr(self, "_hmb_capture_publications", False) and normalized_name in {
            "output",
            "logs",
        }:
            self._hmb_publication_buffer[normalized_name] = (
                self._hmb_publication_buffer.get(normalized_name, "")
                + str(value or "")
            )
            return None
        return super().append_value_to_parameter(name, value, *args, **kwargs)

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
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        parent = getattr(super(), "after_deserialize", None)
        result = parent(*args, **kwargs) if callable(parent) else None
        self._prepare_hmb_node_surface()
        try:
            from _hmb_shot_routing import schedule_post_hydration_reconcile

            schedule_post_hydration_reconcile(self)
        except Exception:
            pass
        self._refresh_agent_shot_route()
        self._refresh_routed_prompt_preview()
        return result

    def after_incoming_connection(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        """Immediately hydrate the routed Prompt and its visible mirror."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        parent = getattr(super(), "after_incoming_connection", None)
        try:
            result = (
                parent(source_node, source_parameter, target_parameter)
                if callable(parent)
                else None
            )
        except Exception:
            result = None
        if str(getattr(target_parameter, "name", "") or "") != (
            _AGENT_SHOT_PROMPT_INPUT_PARAMETER
        ):
            return result

        try:
            self._hmb_hydrate_shot_prompt_from_source(
                source_node,
                str(getattr(source_parameter, "name", "") or ""),
            )
        except Exception:
            # The strict execution pass revalidates the exact source and blocks
            # if a host callback supplied an unreadable value.
            self._refresh_routed_prompt_preview()
        return result

    def after_incoming_connection_removed(
        self,
        source_node: Any,
        source_parameter: Any,
        target_parameter: Any,
    ) -> Any:
        """Clear a disconnected Shot document and restore the manual prompt."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        parent = getattr(super(), "after_incoming_connection_removed", None)
        try:
            result = (
                parent(source_node, source_parameter, target_parameter)
                if callable(parent)
                else None
            )
        except Exception:
            result = None
        if str(getattr(target_parameter, "name", "") or "") == (
            _AGENT_SHOT_PROMPT_INPUT_PARAMETER
        ):
            self._hmb_shot_context = {}
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            try:
                self.set_parameter_value(_AGENT_SHOT_PROMPT_INPUT_PARAMETER, "")
            except Exception:
                pass
            self._set_native_prompt_preview("", enabled=False)
        return result

    def after_outgoing_connection(
        self,
        source_parameter,
        target_node,
        target_parameter,
    ):
        """Warn about Agent-state display without rewriting saved graph topology."""
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
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
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
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

    def _hmb_lifecycle_is_live(self, generation: int | None = None) -> bool:
        """Return whether callbacks still belong to this retained node instance."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        if generation is None:
            return True
        try:
            return int(generation) == int(
                getattr(self, "_hmb_lifecycle_generation", 0) or 0
            )
        except (TypeError, ValueError, OverflowError):
            return False

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        """Invalidate deferred routing/model work without blocking host deletion."""

        if not bool(getattr(self, "_hmb_node_deleted", False)):
            self._hmb_node_deleted = True
            self._hmb_lifecycle_generation = (
                int(getattr(self, "_hmb_lifecycle_generation", 0) or 0) + 1
            )
            # These are private, instance-owned caches only.  User-authored
            # prompt text and already-published native outputs are intentionally
            # left untouched while a late scheduler callback loses ownership.
            self._clear_hmb_runtime_policy()
            self._hmb_shot_catalog_snapshot = {}
            self._hmb_shot_context = {}
            self._clear_execution_shot_binding()
            self._hmb_shot_route_status = {
                "ok": False,
                "code": "deleted",
            }
            self._hmb_shot_clear_syncing = False
            self._hmb_native_calls_this_process = 0
            try:
                from _hmb_shot_routing import schedule_post_deletion_reconcile

                schedule_post_deletion_reconcile(self)
            except Exception:
                pass
        if bool(getattr(self, "_hmb_delete_parent_called", False)):
            return None
        self._hmb_delete_parent_called = True
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None

    def get_parameter_list_value(self, name: str):
        """Add sealed policy rules without changing Standard Agent inputs."""
        normalized_name = str(name or "").strip().casefold()
        parent_getter = getattr(super(), "get_parameter_list_value", None)
        if normalized_name != "rulesets" or not self._hmb_rules_active:
            return parent_getter(name) if callable(parent_getter) else []
        project_name, shot_name = self._hmb_ruleset_names
        if not project_name or not shot_name or project_name == shot_name:
            raise RuntimeError("HMBAgentLibrary sealed rule scope is unavailable.")
        caller_rulesets = parent_getter(name) if callable(parent_getter) else []
        if caller_rulesets in (None, ""):
            merged_rulesets = []
        elif isinstance(caller_rulesets, (list, tuple)):
            merged_rulesets = list(caller_rulesets)
        else:
            merged_rulesets = [caller_rulesets]
        merged_rulesets.extend([
            {"name": project_name, "rules": list(self._hmb_policy_rules)},
            {"name": shot_name, "rules": list(self._hmb_binding_rules)},
        ])
        return merged_rulesets

    def get_parameter_value(self, name: str):
        """Swap only the authenticated prompt; preserve Standard Agent values."""

        normalized_name = str(name or "").strip().casefold()
        if self._hmb_rules_active:
            if normalized_name == _AGENT_PROMPT_INPUT_PARAMETER.casefold():
                runtime_prompt = str(
                    getattr(self, "_hmb_runtime_prompt", "") or ""
                )
                if runtime_prompt and bool(
                    getattr(self, "_hmb_native_prompt_read_active", False)
                ):
                    return runtime_prompt
        return super().get_parameter_value(name)

    def _load_hmb_rules(self) -> tuple[str, str, list[str], list[str]]:
        # The signed policy session supplies the bundled DAT. Decoded
        # rule text exists only for this native call and is cleared immediately
        # afterward; no plaintext policy is persisted on the node.
        payload = _hmb._load_agent_rule_payload()
        policy = str(payload.get("policy") or "").strip()
        binding = str(payload.get("binding") or "").strip()
        if not policy or not binding:
            raise RuntimeError("HMBAgentLibrary internal Behavior 1 / Behavior 2 data is incomplete.")
        policy_rules = _split_behavior_rules(policy, 4)
        binding_rules = _split_behavior_rules(binding, 4)
        self._hmb_policy_identity = {
            "version": str(payload.get("final_policy_version") or ""),
            "contract_sha256": str(
                payload.get("policy_pair_sha256") or ""
            ),
            "envelope_sha256": str(payload.get("envelope_sha256") or ""),
        }
        return policy, binding, policy_rules, binding_rules

    def _set_visible_output(self, value: str) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        try:
            self.set_parameter_value("output", value)
        except Exception:
            pass
        outputs = getattr(self, "parameter_output_values", None)
        if isinstance(outputs, dict):
            outputs["output"] = value

    def _clear_hmb_runtime_policy(self) -> None:
        """Discard all expanded policy text immediately after one native call."""
        self._hmb_capture_publications = False
        self._hmb_rules_active = False
        self._hmb_policy = ""
        self._hmb_binding = ""
        self._hmb_policy_rules = []
        self._hmb_binding_rules = []
        self._hmb_ruleset_names = ("", "")
        self._hmb_policy_identity = {}
        self._hmb_runtime_prompt = ""
        self._hmb_native_prompt_read_active = False
        self._hmb_verified_prompt_source_node = None
        self._hmb_publication_buffer = {"output": "", "logs": ""}
        self._hmb_scheduler_step_failed = False
        self._hmb_last_sanitizer_status = "clean"
        self._hmb_suppress_visible_publication = False

    def _begin_hmb_publication_capture(self) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        self._hmb_publication_buffer = {"output": "", "logs": ""}
        self._hmb_scheduler_step_failed = False
        outputs = getattr(self, "parameter_output_values", None)
        if isinstance(outputs, dict):
            outputs["output"] = ""
            if "logs" in outputs:
                outputs["logs"] = ""

    def _stage_hmb_publications_for_sanitization(self) -> None:
        """Move private native text into the sanitizer without UI callbacks."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        outputs = getattr(self, "parameter_output_values", None)
        if not isinstance(outputs, dict):
            return
        outputs["output"] = self._hmb_publication_buffer.get("output", "")
        if "logs" in outputs or self._hmb_publication_buffer.get("logs"):
            outputs["logs"] = self._hmb_publication_buffer.get("logs", "")

    def _hide_hmb_policy_warning(self) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
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
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        self._set_agent_execution_phase("")
        self._clear_execution_shot_binding()
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
        try:
            self._refresh_agent_shot_route()
        except Exception:
            pass

    def _set_agent_execution_phase(self, phase: str) -> None:
        """Publish one bounded, policy-free progress phase to the small widget."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        normalized_phase = str(phase or "").strip().casefold()
        if normalized_phase not in {"", "authorizing", "preparing", "running"}:
            normalized_phase = ""
        try:
            parameter = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            if parameter is None:
                return
            try:
                current = super().get_parameter_value(_AGENT_WIDGET_PARAMETER)
            except Exception:
                current = getattr(parameter, "default_value", None)
            current = current if isinstance(current, dict) else {}
            execution_binding = self._normalize_execution_shot_binding(
                getattr(self, "_hmb_execution_shot_binding", {})
            )
            shot = current.get("shot")
            if execution_binding:
                shot = {
                    "channel_uuid": execution_binding["channel_uuid"],
                    "shot_uuid": execution_binding["shot_uuid"],
                    "number": execution_binding["shot_number"],
                    "name": execution_binding["shot_name"],
                }
            next_ui = _agent_widget_value(
                shot,
                current.get("shot_catalog"),
                normalized_phase,
            )
            if current == next_ui:
                return
            self._hmb_execution_phase_syncing = True
            try:
                self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_ui)
                parameter.default_value = next_ui
            finally:
                self._hmb_execution_phase_syncing = False
        except Exception:
            self._hmb_execution_phase_syncing = False

    def _record_hmb_native_failure(
        self,
        stage: str,
        exc: BaseException | None = None,
        *,
        code: str = "",
    ) -> None:
        """Retain only bounded diagnostics; never retain provider payload text."""

        normalized_stage = str(stage or "native_process").strip().casefold()
        if normalized_stage not in {
            "build_agent",
            "invoke_model",
            "capture_output",
            "node_finalize",
            "native_step",
            "native_process",
        }:
            normalized_stage = "native_process"
        normalized_code = str(code or "").strip().upper()
        if normalized_code not in _HMB_NATIVE_FAILURE_CODES:
            normalized_code = (
                _hmb_native_failure_code(exc)
                if isinstance(exc, BaseException)
                else "MODEL_PROVIDER"
            )
        self._hmb_native_failure_stage = normalized_stage
        self._hmb_native_failure_code = normalized_code
        try:
            print(
                "[HMB_PRODUCTION][ERROR] "
                f"AGENT_EXECUTION_STAGE={normalized_stage} "
                f"CODE={normalized_code}"
            )
        except Exception:
            pass

    def _process(self, agent: Any, prompt: Any) -> Any:
        """Use the Standard Agent processor in both Only and HMB modes."""

        native_processor = getattr(super(), "_process", None)
        if not callable(native_processor):
            # Import-only/test fallback. Official Griptape always supplies the
            # native processor; never emulate a second, HMB-specific model path.
            return agent
        return native_processor(agent, prompt)

    def _run_native_agent_once(self, lifecycle_generation: int | None = None):
        if lifecycle_generation is None:
            lifecycle_generation = int(
                getattr(self, "_hmb_lifecycle_generation", 1) or 1
            )
        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            return None
        call_index = int(self._hmb_native_calls_this_process or 0)
        if call_index >= 1:
            raise RuntimeError(
                "HMBAgentLibrary blocked an additional native Agent execution."
            )
        self._hmb_native_calls_this_process += 1
        native_iterator = super().process()
        if not self._hmb_rules_active:
            send_value: Any = None
            first_step = True
            try:
                while self._hmb_lifecycle_is_live(lifecycle_generation):
                    try:
                        if first_step:
                            pending = next(native_iterator)
                            first_step = False
                        else:
                            pending = native_iterator.send(send_value)
                    except StopIteration as stop:
                        return stop.value
                    if callable(pending):

                        def owned_step(
                            callable_step=pending,
                            generation=lifecycle_generation,
                        ):
                            if not self._hmb_lifecycle_is_live(generation):
                                return None
                            return callable_step()

                        send_value = yield owned_step
                    else:
                        send_value = yield pending
                return None
            finally:
                if not self._hmb_lifecycle_is_live(lifecycle_generation):
                    close = getattr(native_iterator, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass

        # The Griptape scheduler requires each yielded value to be a callable and
        # sends that callable's return value back into the node generator. Keep
        # this contract intact, but execute each native step behind publication
        # capture so streamed text/log chunks cannot escape before sanitization.
        self._begin_hmb_publication_capture()
        try:
            send_value: Any = None
            first_step = True
            while self._hmb_lifecycle_is_live(lifecycle_generation):
                try:
                    self._hmb_capture_publications = True
                    self._hmb_native_prompt_read_active = True
                    if first_step:
                        pending = next(native_iterator)
                        first_step = False
                    else:
                        pending = native_iterator.send(send_value)
                except StopIteration as stop:
                    return stop.value
                finally:
                    self._hmb_native_prompt_read_active = False
                    self._hmb_capture_publications = False

                if not callable(pending):
                    self._hmb_scheduler_step_failed = True

                    def protected_step():
                        return None
                else:

                    def protected_step(
                        callable_step=pending,
                        generation=lifecycle_generation,
                    ):
                        if not self._hmb_lifecycle_is_live(generation):
                            return None
                        self._hmb_capture_publications = True
                        try:
                            return callable_step()
                        except Exception as exc:
                            # The host scheduler would otherwise publish an
                            # exception containing provider/model data before
                            # this node's fixed-message failure path can run.
                            self._hmb_scheduler_step_failed = True
                            self._record_hmb_native_failure(
                                str(
                                    getattr(
                                        self,
                                        "_hmb_native_failure_stage",
                                        "native_step",
                                    )
                                    or "native_step"
                                ),
                                exc,
                            )
                            return None
                        finally:
                            self._hmb_capture_publications = False

                send_value = yield protected_step
                if not self._hmb_lifecycle_is_live(lifecycle_generation):
                    return None
                if self._hmb_scheduler_step_failed:
                    raise RuntimeError("Protected native Agent scheduler step failed.")
        finally:
            self._hmb_native_prompt_read_active = False
            self._hmb_capture_publications = False
            if self._hmb_lifecycle_is_live(lifecycle_generation):
                self._stage_hmb_publications_for_sanitization()
            close = getattr(native_iterator, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def _has_canonical_hmb_prompt_connection(self) -> bool:
        """Return whether the host graph has the one registered Prompt edge."""

        return _is_direct_hmb_prompt_library_connection(self)

    def _secure_hmb_outputs(self) -> bool:
        """Remove private native state without judging final-text language or meaning.

        The boolean return value remains for compatibility with older host/test
        adapters and is always ``False`` now that client-side language blocking
        has been removed.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        outputs = getattr(self, "parameter_output_values", None)
        if not isinstance(outputs, dict):
            return False

        blocked = _PUBLIC_OUTPUT_BLOCKED
        policy_fragments = _exact_policy_fragments(
            getattr(self, "_hmb_policy", ""),
            getattr(self, "_hmb_binding", ""),
            getattr(self, "_hmb_policy_rules", []),
            getattr(self, "_hmb_binding_rules", []),
        )
        self._hmb_last_sanitizer_status = "sanitizer_error"
        try:
            for key, current in list(outputs.items()):
                if key == "agent" and isinstance(current, dict):
                    _strip_sealed_state_from_agent_wrapper(current)
                    _strip_runtime_scope_from_agent_wrapper(current)
                sanitized = current
                leak_detected = key != "agent" and (
                    _contains_public_output_state_leak(sanitized)
                )
                policy_leak_detected = _contains_exact_policy_text(
                    sanitized,
                    policy_fragments,
                )
                if key == "output":
                    # Authenticated policy instructions may be rendered in any
                    # natural language or wording. Only direct native state and
                    # verbatim server-policy disclosure are private here; no
                    # semantic/translated/encoded phrase matching is performed.
                    self._hmb_last_sanitizer_status = (
                        "policy"
                        if policy_leak_detected
                        else "state"
                        if leak_detected
                        else "clean"
                    )
                if leak_detected or policy_leak_detected:
                    sanitized = {} if key == "agent" else blocked
                outputs[key] = sanitized
            visible_output = outputs.get("output")
            if (
                isinstance(visible_output, str)
                and not bool(
                    getattr(self, "_hmb_suppress_visible_publication", False)
                )
            ):
                # Only now may the native result cross the public parameter
                # callback boundary; streaming writes were privately buffered.
                self._set_visible_output(visible_output)
            return False
        except Exception:
            # A broken detector cannot establish that FINAL TEXT is free of
            # native Agent/runtime state. Fail closed.
            outputs["agent"] = {}
            outputs["output"] = blocked
            if "logs" in outputs:
                outputs["logs"] = ""
            self._hmb_last_sanitizer_status = "sanitizer_error"
            if not bool(
                getattr(self, "_hmb_suppress_visible_publication", False)
            ):
                self._set_visible_output(blocked)
            try:
                print("[HMB_PRODUCTION][WARN] Agent output sanitizer failed closed.")
            except Exception:
                pass
            return False

    def process(self):
        """Execute the native Agent exactly once.

        A plain/native prompt is a stock Standard Library Agent execution: the
        sealed HMB policy is not read, injected, filtered, or used to rewrite its
        output.  Only the direct registered
        ``HMBPromptLibrary.PROMPT_OUT -> HMBAgentLibrary.SHOT_PROMPT_IN`` edge opts into
        the four project rules plus four shot rules.  The Prompt owns all four
        valid source modes (Prompt only, +Asset, +Picker, +Asset+Picker), so the
        Agent does not infer its siblings from payload text. Once that canonical
        edge is present, policy availability and verification are mandatory: a
        failure is reported and native execution is not attempted.
        """
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        lifecycle_generation = int(
            getattr(self, "_hmb_lifecycle_generation", 0) or 0
        )
        self._hmb_native_calls_this_process = 0
        self._hmb_last_sanitizer_status = "clean"
        self._hmb_suppress_visible_publication = False
        self._hmb_native_failure_stage = ""
        self._hmb_native_failure_code = ""
        self._clear_execution_shot_binding()
        # The selector is cable-free in the editor, but the router establishes
        # the same-flow hidden Prompt edge before topology validation so the
        # native scheduler still observes the real dependency.
        # Topology is the contract.  HMBPromptLibrary owns its four valid modes
        # (Prompt only, +Asset, +Picker, +Asset+Picker), so headings or payload
        # wording may evolve without silently disabling its parent Agent path.
        try:
            self._refresh_agent_shot_route(strict=True)
            if not self._hmb_lifecycle_is_live(lifecycle_generation):
                return None
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

        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            return None
        try:
            verified_subscription = self._assert_exact_prompt_shot_route()
            self._adopt_verified_execution_shot_binding(verified_subscription)
        except Exception:
            self._publish_hmb_execution_block(_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_TOPOLOGY_UNAVAILABLE_MESSAGE) from None
        try:
            # Read and verify the bundled signed policy exactly once for this
            # packaged Griptape engine process. Only a canonical HMB Prompt ->
            # Agent execution can initialize the protected in-memory session.
            self._set_agent_execution_phase("authorizing")
            _hmb._bootstrap_agent_policy_session()
        except Exception:
            self._publish_hmb_execution_block(_HMB_POLICY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE) from None

        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            self._set_agent_execution_phase("")
            self._clear_execution_shot_binding()
            return None
        self._set_agent_execution_phase("preparing")
        try:
            (
                self._hmb_policy,
                self._hmb_binding,
                self._hmb_policy_rules,
                self._hmb_binding_rules,
            ) = self._load_hmb_rules()
            self._hmb_ruleset_names = (secrets.token_hex(16), secrets.token_hex(16))
        except Exception:
            self._publish_hmb_execution_block(_HMB_POLICY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE) from None

        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            self._clear_hmb_runtime_policy()
            self._set_agent_execution_phase("")
            self._clear_execution_shot_binding()
            return None
        source_contract_stage = "paired_snapshot"
        try:
            prompt_value = self.get_parameter_value(
                _AGENT_SHOT_PROMPT_INPUT_PARAMETER
            )
            machine_prompt = _paired_machine_prompt(self, prompt_value)
            source_node = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            context_getter = getattr(source_node, "_hmb_agent_shot_context", None)
            if callable(context_getter):
                try:
                    raw_shot_context = context_getter(prompt_value)
                except RuntimeError:
                    raw_shot_context = {}
                self._hmb_shot_context = self._normalize_shot_context(
                    raw_shot_context
                )
                prompt_subscription_getter = getattr(
                    source_node, "_hmb_shot_channel_subscription", None
                )
                prompt_shot_enabled = False
                if callable(prompt_subscription_getter):
                    prompt_subscription = prompt_subscription_getter()
                    prompt_shot_enabled = bool(
                        isinstance(prompt_subscription, dict)
                        and prompt_subscription.get("enabled")
                    )
                if prompt_shot_enabled and not self._hmb_shot_context:
                    raise RuntimeError("HMB Prompt Shot context is invalid.")
            elif self._hmb_shot_channel_subscription().get("enabled"):
                raise RuntimeError("HMB Prompt Shot context is unavailable.")
            else:
                self._hmb_shot_context = {}
            # Treat the verified Prompt snapshot as opaque source data. Prompt
            # owns taxonomy and shot authoring; Generator owns model/media
            # limits. Agent adds the authenticated hidden policy and must not
            # reject, clip, renumber, reinterpret, or delete image/video/FX
            # selections before the model sees them.
            source_contract_stage = "opaque_prompt"
            self._hmb_runtime_prompt = str(machine_prompt)
        except Exception:
            # Do not echo parser details, runtime derivations, or job payload
            # fragments. The public message is fixed and policy-free; the
            # bounded stage code is safe operational evidence for future bugs.
            print(
                "[HMB_PRODUCTION][ERROR] "
                f"SOURCE_CONTRACT_STAGE={source_contract_stage}"
            )
            self._publish_hmb_execution_block(_HMB_SOURCE_CONTRACT_INVALID_MESSAGE)
            raise RuntimeError(_HMB_SOURCE_CONTRACT_INVALID_MESSAGE) from None
        self._hide_hmb_policy_warning()
        self._hmb_rules_active = True
        self._set_agent_execution_phase("running")

        result = None
        native_failed = False
        sanitizer_ran = False
        self._hmb_suppress_visible_publication = True
        try:
            try:
                result = yield from self._run_native_agent_once()
            except Exception as exc:
                # Native exceptions can contain model, memory, or tool payloads.
                # The canonical HMB edge therefore exposes only one fixed message.
                native_failed = True
                if not str(getattr(self, "_hmb_native_failure_code", "") or ""):
                    self._record_hmb_native_failure(
                        "native_process",
                        exc,
                    )

            if not native_failed and self._hmb_lifecycle_is_live(
                lifecycle_generation
            ):
                try:
                    self._secure_hmb_outputs()
                    sanitizer_ran = True
                except Exception:
                    # A future/replaced sanitizer must not leak its exception
                    # details through the scheduler. Publish the fixed blocked
                    # result and let native failures keep their own fixed error.
                    sanitizer_ran = True
                    outputs = getattr(self, "parameter_output_values", None)
                    if isinstance(outputs, dict):
                        outputs["agent"] = {}
                        outputs["output"] = _PUBLIC_OUTPUT_BLOCKED
                        if "logs" in outputs:
                            outputs["logs"] = ""
                    self._hmb_last_sanitizer_status = "sanitizer_error"
        finally:
            self._hmb_rules_active = False
            # The native Agent may publish a partial wrapper or tool trace before
            # raising. Always remove and scrub the temporary HMB rules in the same
            # finally path so an exceptional execution cannot bypass protection.
            try:
                if not self._hmb_lifecycle_is_live(lifecycle_generation):
                    return None
                if not sanitizer_ran:
                    self._secure_hmb_outputs()
                outputs = getattr(self, "parameter_output_values", None)
                final_text = outputs.get("output") if isinstance(outputs, dict) else ""
                sanitizer_status = str(
                    getattr(self, "_hmb_last_sanitizer_status", "") or ""
                )
                if (
                    not native_failed
                    and sanitizer_status == "clean"
                    and (
                        not isinstance(final_text, str)
                        or not final_text.strip()
                    )
                ):
                    # Empty/non-text native results are execution failures, not
                    # semantic-policy failures.
                    native_failed = True
                    self._record_hmb_native_failure(
                        "capture_output",
                        code="EMPTY_OUTPUT",
                    )
                    final_text = _HMB_EXECUTION_FAILED_MESSAGE
                    if isinstance(outputs, dict):
                        outputs["agent"] = {}
                        outputs["output"] = final_text
                        if "logs" in outputs:
                            outputs["logs"] = ""
                # The authenticated policy and the Agent model own final
                # wording and meaning.  The client does not phrase-match or
                # rewrite a valid natural-language result at this boundary.
                self._hmb_suppress_visible_publication = False
                if isinstance(final_text, str):
                    self._set_visible_output(final_text)
            except Exception:
                # A replaced/future sanitizer can still raise outside its own
                # guard. Without a completed state check, fail closed.
                try:
                    self._set_visible_output(_PUBLIC_OUTPUT_BLOCKED)
                    outputs = getattr(self, "parameter_output_values", None)
                    if isinstance(outputs, dict):
                        outputs["agent"] = {}
                        if "logs" in outputs:
                            outputs["logs"] = ""
                    print(
                        "[HMB_PRODUCTION][WARN] Agent output sanitizer failed closed."
                    )
                except Exception:
                    pass
            finally:
                self._hmb_suppress_visible_publication = False
                self._clear_hmb_runtime_policy()
                self._set_agent_execution_phase("")
                self._clear_execution_shot_binding()
        try:
            self._refresh_agent_shot_route()
        except Exception:
            pass
        if native_failed:
            self._publish_hmb_execution_block(_HMB_EXECUTION_FAILED_MESSAGE)
            raise RuntimeError(_HMB_EXECUTION_FAILED_MESSAGE) from None
        return result
