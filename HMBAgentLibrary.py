from __future__ import annotations

from pathlib import Path
import asyncio
import copy
import hashlib
import hmac
import importlib.util
import json
import math
import re
import secrets
import sys
import threading
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
from _hmb_project import ProjectPolicyPendingError, project_from_asset_payload, resolve_project
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
_AGENT_INITIAL_NODE_WIDTH = 720
_AGENT_INITIAL_NODE_HEIGHT = 1100
_AGENT_SHOT_CONTEXT_SCHEMA = "hmb-agent-shot-context"
_AGENT_SHOT_CONTEXT_VERSION = 1
_AGENT_STATE_WARNING_NAME = "HMB_AGENT_STATE_DISPLAY_WARNING"
_HMB_POLICY_WARNING_NAME = "HMB_AGENT_POLICY_REQUIRED_WARNING"
_HMB_TOPOLOGY_WARNING_NAME = "HMB_AGENT_CONNECTION_CHECK_WARNING"
_AGENT_EXECUTION_RESULT_PARAMETER = "HMB_AGENT_EXECUTION_RESULT"
_AGENT_SHOT_STORE_PARAMETER = "HMB_AGENT_SHOT_STATES"
_AGENT_SHOT_STORE_SCHEMA = "hmb-agent-shot-states"
_AGENT_SHOT_ROW_PREFIX = "HMB_AGENT_SHOT_ROW_"
_AGENT_NATIVE_SETTING_KEYS = ("model_provider", "model", "agent", "include_details", "output_schema", "additional_context", "agent_memory", "prompt")
_AGENT_EXECUTION_FAILED_WARNING = "HMB_AGENT_EXECUTION_FAILED_WARNING"
_AGENT_CREATED_WARNING = "HMB_AGENT_CREATED_WARNING"
_AGENT_PROJECT_POLICY_ABSENT_WARNING = "HMB_AGENT_PROJECT_POLICY_ABSENT_WARNING"
_AGENT_PROJECT_POLICY_ABSENT_MESSAGE = (
    "선택한 프로젝트의 정책이 없습니다. 프로젝트 정책을 적용하지 않고 원본 샷 입력으로 계속 실행합니다. "
    "다른 프로젝트의 정책은 대신 적용하지 않습니다."
)
_AGENT_CREATED_MESSAGE = (
    "Agent 객체만 생성되었습니다. 모델 추론과 HMB 프로젝트 정책 적용은 실행되지 않았습니다. "
    "HMB 샷 작업은 해당 샷의 Prompt 연결과 프로젝트 정책 준비 상태를 확인하세요."
)
_FINAL_TEXT_DISPLAY_NAME = "FINAL TEXT · GENERATOR"
_AGENT_STATE_DISPLAY_NAME = "AGENT STATE · CHAIN ONLY"
_HMB_POLICY_UNAVAILABLE_MESSAGE = (
    "[HMB LOCAL POLICY REQUIRED] The signed local Agent policy is unavailable "
    "or invalid. Reinstall or update HMB_GP_Production from the approved "
    "package, then restart the official Griptape Desktop application."
)
_HMB_PROJECT_POLICY_PENDING_MESSAGE = (
    "[HMB PROJECT POLICY PENDING] 선택한 프로젝트의 정책이 준비 중입니다. "
    "다이노스터·까투리8 정책을 해당 프로젝트 폴더에 설치한 후 다시 실행하세요."
)
_HMB_SOURCE_CONTRACT_INVALID_MESSAGE = (
    "[HMB SOURCE CONTRACT INVALID] 구조화된 HMB 소스 데이터의 형식 또는 주소가 "
    "일치하지 않아 실행을 중단했습니다. Frame Range OFF/미설정, 선택 역할 미지정 "
    "및 emitter 미지정은 정상적인 선택 상태이며 이 오류의 원인이 아닙니다. "
    "HMBPromptLibrary와 HMBVideoPickerLibrary의 구조화 데이터 연결 상태를 확인하십시오."
)
_RUNTIME_FX_SCOPE_HEADER = "HMB VERIFIED FX/TIMING RUNTIME SCOPE (JSON):"
_AGENT_ENGLISH_OUTPUT_CONTRACT = (
    "HMB FINAL OUTPUT LANGUAGE CONTRACT:\n"
    "Write the complete final generator instruction in English, regardless of "
    "the language used in the source fields. Translate the source meaning "
    "faithfully without adding, omitting, weakening, or reinterpreting it. "
    "Preserve source addresses such as @imageN and @videoN, identifiers, proper "
    "nouns, numeric values, and exact quoted dialogue, lyrics, chants, or "
    "on-screen text when the source explicitly requires those words verbatim."
)
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
_REGISTERED_PROMPT_OWNER_ATTRIBUTE = "_hmb_registered_prompt_source_node"
_FROZEN_PROMPT_SHOT_ATTRIBUTE = "_hmb_frozen_prompt_shot_source"

_WEB_AUTHORITY_SEAL = object()
_EXECUTION_GATE_GUARD = threading.Lock()


class _HMBWebRerenderAuthority:
    """An engine-issued, process-local, single-use permission, never JSON input."""

    __slots__ = ("_seal", "agent", "generator", "request_id", "owner_key", "_claimed", "_lock")

    def __init__(self, seal, agent, generator, request_id, owner_key):
        if seal is not _WEB_AUTHORITY_SEAL:
            raise TypeError("Web rerender authority must be issued by the engine.")
        self._seal = seal
        self.agent = agent
        self.generator = generator
        self.request_id = request_id
        self.owner_key = owner_key
        self._claimed = False
        self._lock = threading.Lock()

    def _claim(self, agent):
        with self._lock:
            if self._seal is not _WEB_AUTHORITY_SEAL or self.agent is not agent or self._claimed:
                raise RuntimeError("Web rerender authority is unavailable or already used.")
            self._claimed = True

    def __reduce__(self):
        raise TypeError("Web rerender authority cannot be serialized.")


def _issue_hmb_web_rerender_authority(agent, *, request_id, generator, owner_key):
    """Called only by the authenticated engine worker after target validation.

    This is an in-process capability boundary, not a remotely exposed request or
    a marker accepted from a parameter. The worker owns authentication, target
    registration, Generator reservation and durable request deduplication.
    """
    if not isinstance(agent, HMBAgentLibrary) or generator is None:
        raise TypeError("Web rerender requires an HMB Agent and a reserved Generator.")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}", request_id):
        raise ValueError("Web rerender request identity is invalid.")
    if not isinstance(owner_key, str) or not owner_key or len(owner_key) > 512:
        raise ValueError("Web rerender owner identity is invalid.")
    return _HMBWebRerenderAuthority(_WEB_AUTHORITY_SEAL, agent, generator, request_id, owner_key)


def _agent_execution_gate(node):
    with _EXECUTION_GATE_GUARD:
        gate = getattr(node, "_hmb_execution_gate", None)
        if gate is None:
            gate = threading.Lock()
            node._hmb_execution_gate = gate
        return gate


async def _acquire_agent_execution_gate(node):
    gate = _agent_execution_gate(node)
    # A cancellable wait must never leave a to_thread(lock.acquire) pending;
    # that worker could acquire the lock after its cancelled waiter has gone.
    while not gate.acquire(blocking=False):
        await asyncio.sleep(0.05)
    return gate


async def _run_web_rerender_worker(execution, callback):
    """Keep native model I/O off the loop and drain before facade cleanup."""
    pending = asyncio.create_task(asyncio.to_thread(callback))
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        execution._hmb_web_cancelled = True
        # A native stream must not outlive its reservation and write into a
        # cleared facade. Repeated cancellation remains safe.
        while not pending.done():
            try:
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if pending.done() and not pending.cancelled():
            pending.exception()
        raise


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


def _hmb_execution_failure_message(code: str) -> str:
    """Describe an existing native failure without publishing provider payloads."""

    guidance = {
        "MODEL_TIMEOUT": (
            "The Agent model response timed out. This is not a local policy DAT "
            "error. Retry the Agent or check the selected model/provider. "
            "For generators with an existing task ID, retrieve that result before "
            "starting another render."
        ),
        "MODEL_CREDENTIAL": "Check the credentials for the selected Agent model provider.",
        "MODEL_ACCESS": "Check access to the selected Agent model with its provider.",
        "MODEL_RATE_LIMIT": "The Agent model provider reported a rate or quota limit.",
        "MODEL_NETWORK": "The Agent model connection failed. Check the provider connection.",
        "MODEL_PROVIDER": "The Agent model provider reported an execution failure.",
        "HOST_ADAPTER": "The native Agent or model adapter could not complete execution.",
        "EMPTY_OUTPUT": "The Agent model returned no final text.",
    }
    normalized = str(code or "").strip().upper()
    detail = guidance.get(normalized)
    if detail is None:
        return _HMB_EXECUTION_FAILED_MESSAGE
    return f"{_HMB_EXECUTION_FAILED_MESSAGE} Reason: {normalized}. {detail}"


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
    shot_manager: bool = True,
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
        "shot_manager": bool(shot_manager),
        "shot_editor_expanded": True,
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
                else "샷 선택"
            ),
        },
    }


def _configure_agent_widget_parameter(parameter: Any) -> None:
    if parameter is None:
        return
    height = _AGENT_WIDGET_HEIGHT
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
        parameter.default_value = _agent_widget_value(current_shot, current_catalog, shot_manager=bool(current.get("shot_manager")) if isinstance(current, dict) else False)
    except Exception:
        pass
    try:
        options = dict(getattr(parameter, "ui_options", {}) or {})
        options.update(
            {
                "display_name": "HMBAgentLibrary",
                "is_full_width": True,
                "height": height,
                "min_height": height,
                "max_height": height,
                "widget_height": height,
                "default_height": height,
                "preferred_height": height,
                "initial_height": height,
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


class _FrozenHMBPromptShotSource:
    """Read-only paired data from one verified registered Prompt manager."""
    def __init__(self, owner, document, agent_subscription):
        if not isinstance(document, dict) or document.get("schema") != "hmb-prompt-shot-document" or document.get("version") != 1:
            raise RuntimeError("HMB Prompt Shot document is invalid.")
        self._owner = owner
        self._document = copy.deepcopy(document)
        self._subscription = {**agent_subscription, "participant_kind": "prompt"}
        supplied = self._document.get("subscription")
        if not isinstance(supplied, dict) or any(supplied.get(key) != self._subscription.get(key) for key in ("schema", "version", "participant_kind", "enabled", "channel_uuid", "shot_uuid", "shot_number", "shot_name")):
            raise RuntimeError("HMB Prompt Shot document identity is invalid.")
        self.visible_prompt = self._document.get("visible_prompt")
        self.machine_prompt = self._document.get("machine_prompt")
        if not isinstance(self.visible_prompt, str) or not self.visible_prompt or not isinstance(self.machine_prompt, str) or not self.machine_prompt:
            raise RuntimeError("HMB Prompt Shot document is empty.")
        self._hmb_shot_route_status = {"ok": True, "code": "ready"}
    def _hmb_shot_channel_subscription(self):
        return copy.deepcopy(self._subscription)
    def _hmb_agent_prompt_snapshot(self, visible_prompt):
        if visible_prompt != self.visible_prompt:
            raise RuntimeError("HMB Prompt visible snapshot changed.")
        paired = copy.deepcopy(self._document.get("paired_snapshot"))
        if not isinstance(paired, dict) or paired.get("machine_prompt") != self.machine_prompt:
            raise RuntimeError("HMB Prompt paired snapshot is invalid.")
        return paired
    def _hmb_agent_shot_context(self, visible_prompt):
        if visible_prompt != self.visible_prompt:
            raise RuntimeError("HMB Prompt Shot context changed.")
        return copy.deepcopy(self._document.get("shot_context") or self._document.get("context") or {})
    def _hmb_agent_reference_media(self, machine_prompt):
        if machine_prompt != self.machine_prompt:
            raise RuntimeError("HMB Prompt media snapshot changed.")
        return copy.deepcopy(self._document.get("reference_media") or {})
    def _hmb_agent_generation_context(self, machine_prompt):
        if machine_prompt != self.machine_prompt:
            raise RuntimeError("HMB Prompt generation snapshot changed.")
        return copy.deepcopy(self._document.get("generation_context") or {})
    def _hmb_project_identity(self):
        return resolve_project(self._document.get("project_identity"), default_legacy=False)


def _is_prompt_shot_manager(source):
    enabled = getattr(source, "_hmb_shot_manager_enabled", None)
    return callable(enabled) and enabled() is True


def _prompt_transport_text(prompt_value: Any) -> str:
    value = getattr(prompt_value, "value", prompt_value)
    return str(value or "")


def _prompt_text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _with_english_agent_output_contract(final_prompt: Any) -> str:
    """Append one private output-language rule to the model-bound prompt."""

    prompt_text = str(getattr(final_prompt, "value", final_prompt) or "")
    if prompt_text.strip():
        return prompt_text.rstrip() + "\n\n" + _AGENT_ENGLISH_OUTPUT_CONTRACT
    return _AGENT_ENGLISH_OUTPUT_CONTRACT


def _run_native_with_literal_hmb_input(native_processor: Any, agent: Any, prompt: Any, *native_args: Any) -> Any:
    """Keep the exact verified request literal at the native Task boundary.

    Standard PromptTask renders every TextArtifact as Jinja, including text
    inside multimodal lists. The HMB envelope and reference labels are data,
    so only this request object bypasses that second interpretation. Other
    native inputs/templates keep the original processor, and the instance
    hook is restored when that native run finishes. A cancelled streaming UI
    may return before its native worker; the worker's own finish event retains
    protection through its final input/memory reads without delaying cancel.
    """

    task = None
    try:
        from griptape.artifacts import BaseArtifact, TextArtifact
        from griptape.events import EventListener, FinishStructureRunEvent, StartStructureRunEvent
        from griptape.tasks import PromptTask

        candidate = agent.tasks[0]
        if isinstance(candidate, PromptTask):
            original = candidate._process_task_input
            previous_instance_hook = candidate.__dict__.get("_process_task_input")

            def literal_input(value: Any) -> Any:
                if value is prompt:
                    return value if isinstance(value, BaseArtifact) else TextArtifact(value)
                return original(value)

            candidate._process_task_input = literal_input
            task = candidate
    except (ImportError, AttributeError, IndexError, TypeError):
        pass
    if task is None:
        return native_processor(agent, prompt, *native_args)
    run_started = False
    run_finished = False

    def restore_input() -> None:
        try:
            if task.__dict__.get("_process_task_input") is literal_input:
                if previous_instance_hook is None:
                    del task._process_task_input
                else:
                    task._process_task_input = previous_instance_hook
        except (AttributeError, TypeError):
            pass

    def observe_run(event: Any) -> Any:
        nonlocal run_started, run_finished
        if getattr(event, "structure_id", None) == agent.id:
            if isinstance(event, StartStructureRunEvent):
                run_started = True
            elif isinstance(event, FinishStructureRunEvent):
                run_finished = True
                restore_input()
                listener.__exit__(None, None, None)
        return event

    listener = EventListener(observe_run, event_types=[StartStructureRunEvent, FinishStructureRunEvent])
    listener.__enter__()
    try:
        return native_processor(agent, prompt, *native_args)
    finally:
        # EventBus uses context-local listener lists. Removing this listener
        # from the UI context leaves the native worker's copied context intact
        # until its matching finish event restores the hook after cancellation.
        listener.__exit__(None, None, None)
        if not run_started or run_finished:
            restore_input()


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
    HMB execution swaps in the exact authenticated Prompt bytes, lets the native
    Agent merge caller context, appends one private English-output contract to
    the final model-bound prompt, and appends the two sealed Behaviors; caller
    context, memory, rulesets, tools, schema, and native execution settings
    otherwise remain unchanged. Once the canonical HMB
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
        self._hmb_registered_prompt_source_node = None
        self._hmb_frozen_prompt_shot_source = None
        self._hmb_native_calls_this_process = 0
        self._hmb_native_inference_started = False
        self._hmb_native_run_completed = False
        self._hmb_run_hmb_source = False
        self._hmb_run_policy_applied = False
        self._hmb_policy_omitted = False
        self._hmb_run_policy_omitted = False
        self._hmb_run_project_identity: dict[str, str] = {}
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
        self._hmb_execution_result: dict[str, Any] = {}
        self._hmb_reference_observation: dict[str, Any] = {}
        self._hmb_reference_observation_run_id = ""
        self._hmb_shot_manager_mode = True
        self._hmb_shot_editor_expanded = True
        self._hmb_native_editor_elements = []
        self._hmb_native_editor_visibility = {}
        self._hmb_native_editor_collapsed = False
        self._hmb_row_syncing = False
        self._hmb_layout_syncing = False
        self._hmb_agent_migration_archives = {}
        self._hmb_shot_slots: dict[str, Any] = {}
        self._hmb_active_slot_key = "__hmb_only__"
        self._hmb_slot_switching = False
        self._hmb_shot_store_syncing = False
        self._hmb_shot_execution_locks: dict[str, Any] = {}
        self._hmb_shot_results: dict[str, Any] = {}
        self._hmb_shot_request_records: dict[str, Any] = {}
        self._hmb_shot_result_lock = threading.RLock()
        self._hmb_shot_run_status = {}
        self._hmb_shot_workers = {}
        self._hmb_shot_action_ids = set()
        self._hmb_shot_local_tasks = set()
        self._hmb_shot_context: dict[str, Any] = {}
        self._hmb_shot_catalog_snapshot: dict[str, Any] = {}
        # Instance-local execution authority.  Display widget writes and
        # same-flow route callbacks may interleave while several Agents run,
        # but they must not change the exact Shot being consumed by this run.
        self._hmb_execution_shot_binding: dict[str, Any] = {}
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_shot_clear_syncing = False
        self._hmb_shot_catalog_syncing = False
        self._hmb_initial_shot_autoclaim_pending = False
        self._hmb_initial_shot_preferred_uuid = ""
        # The router-owned SHOT_PROMPT_IN remains the only authoritative HMB
        # execution input.  These fields only mirror its public, user-readable
        # document into the native Agent prompt editor while a Shot is active.
        self._hmb_prompt_preview_syncing = False
        self._hmb_prompt_preview_active = False
        self._hmb_prompt_preview_value = ""
        self._hmb_prompt_before_preview = ""
        super().__init__(**kwargs)
        # Give newly created nodes room for the compact header, five Shot rows
        # and the stock editor. The official SDK setter preserves saved sizes;
        # this is a creation default, never a resize/hydration correction.
        initial_size_setter = getattr(self, "set_initial_node_size", None)
        if callable(initial_size_setter):
            initial_size_setter(width=_AGENT_INITIAL_NODE_WIDTH, height=_AGENT_INITIAL_NODE_HEIGHT)
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
        self._ensure_hmb_execution_result()
        self._ensure_hmb_shot_store()
        self._ensure_agent_shot_rows()

    def _hmb_widget_value(self, shot=None, shot_catalog=None, execution_phase="", shot_manager=None):
        value = _agent_widget_value(shot, shot_catalog, execution_phase,
                                   getattr(self, "_hmb_shot_manager_mode", False) if shot_manager is None else shot_manager)
        value["shot_editor_expanded"] = bool(getattr(self, "_hmb_shot_editor_expanded", True))
        value["shot_states"] = {
            key.split("\x1f", 1)[-1]: str(status)
            for key, status in getattr(self, "_hmb_shot_run_status", {}).items()
            if status in {"running", "succeeded", "failed", "cancelled"}
        }
        return value

    @staticmethod
    def _hmb_slot_key(channel_uuid="", shot_uuid=""):
        return f"{channel_uuid}\x1f{shot_uuid}" if channel_uuid and shot_uuid else "__hmb_only__"

    def _ensure_hmb_shot_store(self):
        if not _parameter_exists(self, _AGENT_SHOT_STORE_PARAMETER):
            self.add_parameter(Parameter(
                name=_AGENT_SHOT_STORE_PARAMETER, type="dict", default_value={},
                allowed_modes={ParameterMode.PROPERTY}, hide=True, hide_property=True,
                hide_label=True, ui_options={"hide": True, "hide_property": True, "hide_handles": True},
            ))
        self._hmb_restore_shot_store()

    def _hmb_restore_shot_store(self):
        if getattr(self, "_hmb_shot_store_syncing", False):
            return
        raw = self._native_parameter_value(_AGENT_SHOT_STORE_PARAMETER, {})
        if not isinstance(raw, dict) or raw.get("schema") != _AGENT_SHOT_STORE_SCHEMA or raw.get("version") != 1:
            return
        slots = raw.get("slots")
        if not isinstance(slots, dict):
            return
        self._hmb_shot_slots = copy.deepcopy(slots)
        self._hmb_shot_manager_mode = True
        self._hmb_shot_editor_expanded = raw.get("editor_expanded", True) is not False
        self._hmb_agent_migration_archives = copy.deepcopy(raw.get("migration_archives") or {})
        self._hmb_active_slot_key = str(raw.get("active") or "__hmb_only__")
        self._hmb_shot_results = copy.deepcopy(raw.get("results") or {})

    def _hmb_persist_shot_store(self):
        if getattr(self, "_hmb_shot_store_syncing", False) or getattr(self, "_hmb_node_deleted", False):
            return
        self._hmb_shot_store_syncing = True
        try:
            value = {"schema": _AGENT_SHOT_STORE_SCHEMA, "version": 1,
                     "manager": True,
                     "editor_expanded": bool(getattr(self, "_hmb_shot_editor_expanded", True)),
                     "migration_archives": copy.deepcopy(getattr(self, "_hmb_agent_migration_archives", {})),
                     "active": self._hmb_active_slot_key,
                     "slots": copy.deepcopy(self._hmb_shot_slots),
                     "results": copy.deepcopy(self._hmb_shot_results)}
            current = self._native_parameter_value(_AGENT_SHOT_STORE_PARAMETER, {})
            if current != value:
                super().set_parameter_value(_AGENT_SHOT_STORE_PARAMETER, value)
        finally:
            self._hmb_shot_store_syncing = False

    def _hmb_slot_list_children(self, name):
        parameter = _parameter_by_name(self, name)
        children = list(getattr(parameter, "children", []) or [])
        slots = getattr(self, "_hmb_shot_slots", {})
        known = set().union(*(set(slot.get("children", {})) for slot in slots.values() if isinstance(slot, dict))) if slots else set()
        active = slots.get(getattr(self, "_hmb_active_slot_key", "__hmb_only__"), {})
        active_names = set(active.get("children", {}))
        return [child for child in children if str(getattr(child, "name", "")) in active_names or str(getattr(child, "name", "")) not in known]

    def _hmb_slot_native_list_value(self, name):
        parameter = _parameter_by_name(self, name)
        connected = getattr(self, "_has_connected_whole_list_value", None)
        if parameter is not None and callable(connected) and connected(parameter):
            getter = getattr(super(), "get_parameter_list_value", None)
            return getter(name) if callable(getter) else []
        children = self._hmb_slot_list_children(name)
        all_children = list(getattr(parameter, "children", []) or [])
        if all_children:
            values = []
            for child in children:
                value = self._native_parameter_value(str(child.name), None)
                values.extend(value if isinstance(value, (list, tuple)) else [] if value is None else [value])
            return values
        getter = getattr(super(), "get_parameter_list_value", None)
        return getter(name) if callable(getter) else []

    def _hmb_native_slot_snapshot(self):
        values = {}
        for key in _AGENT_NATIVE_SETTING_KEYS:
            values[key] = copy.deepcopy(self._native_parameter_value(key, None))
        for key in ("tools", "rulesets"):
            values[key] = copy.deepcopy(self._hmb_slot_native_list_value(key))
        children = {}
        for key in ("tools", "rulesets"):
            parameter = _parameter_by_name(self, key)
            for child in self._hmb_slot_list_children(key):
                name = str(getattr(child, "name", "") or "")
                if name:
                    children[name] = copy.deepcopy(self._native_parameter_value(name, None))
        outputs = copy.deepcopy({key: getattr(self, "parameter_output_values", {}).get(key,
                    self._native_parameter_value(key, "")) for key in ("output", "logs", "agent")})
        return {"values": values, "children": children, "outputs": outputs,
                "result": copy.deepcopy(self._hmb_execution_result_snapshot())}

    def _hmb_capture_active_slot(self):
        if (getattr(self, "_hmb_slot_switching", False) or getattr(self, "_hmb_node_deleted", False)
                or not _parameter_exists(self, _AGENT_SHOT_STORE_PARAMETER)):
            return
        self._hmb_shot_slots[self._hmb_active_slot_key] = self._hmb_native_slot_snapshot()
        self._hmb_persist_shot_store()

    def _hmb_switch_native_slot(self, channel_uuid="", shot_uuid=""):
        target = self._hmb_slot_key(channel_uuid, shot_uuid)
        if not _parameter_exists(self, _AGENT_SHOT_STORE_PARAMETER):
            self._hmb_active_slot_key = target
            return
        if target == getattr(self, "_hmb_active_slot_key", "__hmb_only__") or getattr(self, "_hmb_slot_switching", False):
            return
        self._hmb_capture_active_slot()
        template = self._hmb_shot_slots.get("__hmb_default_settings__")
        if not isinstance(template, dict):
            template = self._hmb_native_slot_snapshot()
            template["values"]["prompt"] = ""
            template["values"]["agent"] = None
            template["values"]["agent_memory"] = {}
            template["values"]["tools"] = []
            template["values"]["rulesets"] = []
            template["children"] = {}
            template["outputs"] = {"output": "", "logs": "", "agent": None}
            template["result"] = {}
            self._hmb_shot_slots["__hmb_default_settings__"] = copy.deepcopy(template)
        slot = copy.deepcopy(self._hmb_shot_slots.get(target, template))
        self._hmb_slot_switching = True
        try:
            for key in _AGENT_NATIVE_SETTING_KEYS:
                if key in slot.get("values", {}):
                    super().set_parameter_value(key, copy.deepcopy(slot["values"][key]))
            for key in ("tools", "rulesets"):
                parameter = _parameter_by_name(self, key)
                desired = slot.get("values", {}).get(key, [])
                if parameter is not None:
                    setter = getattr(self, "set_parameter_list_value", None)
                    if callable(setter):
                        setter(key, copy.deepcopy(desired))
                    else:
                        super().set_parameter_value(key, copy.deepcopy(desired))
            for parent_name in ("tools", "rulesets"):
                parameter = _parameter_by_name(self, parent_name)
                for child in list(getattr(parameter, "children", []) or []):
                    active_child = str(getattr(child, "name", "")) in slot.get("children", {})
                    try:
                        child.hide = not active_child
                        child.hide_property = not active_child
                    except Exception:
                        pass
            for key, value in slot.get("children", {}).items():
                if _parameter_exists(self, key):
                    super().set_parameter_value(key, copy.deepcopy(value))
            for key, value in slot.get("outputs", {}).items():
                if key != "agent":
                    super().set_parameter_value(key, copy.deepcopy(value))
                self.parameter_output_values[key] = copy.deepcopy(value)
            self._hmb_execution_result = copy.deepcopy(slot.get("result") or {})
            self.parameter_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(self._hmb_execution_result)
            self.parameter_output_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(self._hmb_execution_result)
            self._hmb_active_slot_key = target
            self._hmb_prompt_preview_active = False
            self._hmb_prompt_preview_value = ""
            self._hmb_prompt_before_preview = str(slot.get("values", {}).get("prompt") or "")
            self._refresh_hmb_execution_result_messages()
        finally:
            self._hmb_slot_switching = False
        self._hmb_persist_shot_store()

    def _hmb_shot_manager_enabled(self):
        return bool(getattr(self, "_hmb_shot_manager_mode", False))

    def _hmb_shot_manager_paused_for(self, *, channel_uuid, shot_uuid):
        return False

    def _hmb_agent_shot_subscriptions(self):
        if not self._hmb_shot_manager_enabled():
            value = self._hmb_shot_channel_subscription()
            return [value] if value.get("enabled") else []
        catalog = getattr(self, "_hmb_shot_catalog_snapshot", {})
        channel = str(catalog.get("channel_uuid") or "")
        return [{"schema": "hmb-shot-channel-subscription", "version": 1,
                 "participant_kind": "agent", "enabled": True,
                 "channel_uuid": channel, "shot_uuid": item["shot_uuid"],
                 "shot_number": item["number"], "shot_name": item["name"]}
                for item in catalog.get("shots", [])] if channel else []

    def _hmb_manager_prompt_owner(self, *, channel_uuid, shot_uuid):
        from _hmb_shot_routing import resolve_shot_prompt_owner
        candidate = resolve_shot_prompt_owner(self, channel_uuid=channel_uuid, shot_uuid=shot_uuid)
        if not _is_direct_hmb_prompt_library_connection(self):
            raise RuntimeError("Connect the registered HMB Prompt manager before running this Shot.")
        if getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None) is not candidate:
            raise RuntimeError("The exact Shot Prompt owner does not match the managed input.")
        return candidate

    def _hmb_agent_shot_result(self, *, channel_uuid, shot_uuid, run_id=None, generator=None):
        key = self._hmb_slot_key(channel_uuid, shot_uuid)
        with self._hmb_shot_result_lock:
            if run_id is not None:
                ticket = getattr(self, "_hmb_shot_request_records", {}).get(str(run_id))
                if (not isinstance(ticket, dict) or generator is None or ticket.get("generator") is not generator
                        or ticket.get("key") != key):
                    return {}
                return copy.deepcopy(ticket["record"])
            return copy.deepcopy(self._hmb_shot_results.get(key) or {})

    def _hmb_release_agent_shot_result(self, *, channel_uuid, shot_uuid, run_id, generator):
        key = self._hmb_slot_key(channel_uuid, shot_uuid)
        with self._hmb_shot_result_lock:
            tickets = getattr(self, "_hmb_shot_request_records", {})
            ticket = tickets.get(str(run_id))
            if isinstance(ticket, dict) and ticket.get("generator") is generator and ticket.get("key") == key:
                tickets.pop(str(run_id), None)
                return True
            return False

    def _hmb_publish_shot_status(self):
        if getattr(self, "_hmb_node_deleted", False):
            return
        raw = self._native_parameter_value(_AGENT_WIDGET_PARAMETER, {})
        if not isinstance(raw, dict):
            return
        value = self._hmb_widget_value(raw.get("shot"), raw.get("shot_catalog"), raw.get("execution_phase", ""))
        if value != raw:
            self._hmb_execution_phase_syncing = True
            try:
                self.set_parameter_value(_AGENT_WIDGET_PARAMETER, value)
            finally:
                self._hmb_execution_phase_syncing = False

    def _hmb_publish_shot_failure(self, key, execution, *, cancelled=False):
        getter = getattr(execution, "_hmb_execution_result_snapshot", None)
        previous = getter() if callable(getter) else {}
        if not isinstance(previous, dict):
            previous = {}
        code = "CANCELLED" if cancelled else str(previous.get("code") or "SOURCE_UNAVAILABLE")
        message = ("[HMB EXECUTION CANCELLED] This Shot Agent was cancelled. No new render was submitted."
                   if cancelled else str(previous.get("message") or _HMB_TOPOLOGY_UNAVAILABLE_MESSAGE))
        result = {**previous, "status": "failed", "code": code, "message": message,
                  "run_id": str(previous.get("run_id") or secrets.token_hex(16)),
                  "output_sha256": _prompt_text_sha256(message)}
        slot = self._hmb_shot_slots.get(key)
        if not isinstance(slot, dict):
            slot = {"values": {}, "children": {}}
        slot["result"] = copy.deepcopy(result)
        slot["outputs"] = {"output": message, "logs": "", "agent": {}}
        self._hmb_shot_slots[key] = slot
        if self._hmb_active_slot_key == key and not self._hmb_node_deleted:
            self._hmb_slot_switching = True
            try:
                super().set_parameter_value("output", message)
                self.parameter_output_values["output"] = message
                self._hmb_execution_result = copy.deepcopy(result)
                self.parameter_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(result)
                self.parameter_output_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(result)
                self._refresh_hmb_execution_result_messages()
            finally:
                self._hmb_slot_switching = False
        self._hmb_persist_shot_store()

    async def _hmb_run_agent_shot(self, *, channel_uuid, shot_uuid, prompt_owner, generator=None):
        lifecycle_generation = int(getattr(self, "_hmb_lifecycle_generation", 0) or 0)
        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            raise asyncio.CancelledError()
        if not self._hmb_shot_manager_enabled():
            raise RuntimeError("Agent Shot manager is not enabled.")
        if self._hmb_manager_prompt_owner(channel_uuid=channel_uuid, shot_uuid=shot_uuid) is not prompt_owner:
            raise RuntimeError("Agent Shot Prompt owner changed.")
        subscriptions = self._hmb_agent_shot_subscriptions()
        matches = [item for item in subscriptions if item["channel_uuid"] == channel_uuid and item["shot_uuid"] == shot_uuid]
        if len(matches) != 1:
            raise RuntimeError("Agent Shot identity is unavailable.")
        subscription = copy.deepcopy(matches[0])
        key = self._hmb_slot_key(channel_uuid, shot_uuid)
        lock = self._hmb_shot_execution_locks.setdefault(key, threading.Lock())
        while not lock.acquire(blocking=False):
            if (not self._hmb_lifecycle_is_live(lifecycle_generation)
                    or (generator is not None and bool(getattr(generator, "is_cancellation_requested", False)))):
                raise asyncio.CancelledError()
            await asyncio.sleep(0.05)
        execution = None
        try:
            if not self._hmb_lifecycle_is_live(lifecycle_generation):
                raise asyncio.CancelledError()
            if self._hmb_active_slot_key == key:
                self._hmb_capture_active_slot()
            slot = copy.deepcopy(self._hmb_shot_slots.get(key) or self._hmb_shot_slots.get("__hmb_default_settings__") or self._hmb_native_slot_snapshot())
            document = prompt_owner._hmb_prompt_shot_document(channel_uuid=channel_uuid, shot_uuid=shot_uuid)
            execution = _HMBAgentShotExecution._from_owner(self, prompt_owner, document, subscription, slot, generator)
            self._hmb_shot_run_status[key] = "running"
            self._hmb_shot_workers[key] = execution
            self._hmb_publish_shot_status()
            # Reuse the complete canonical policy, model, media and sanitization
            # pipeline; only frozen native input getters differ from the editor.
            await execution._hmb_aprocess_locked()
            if not self._hmb_lifecycle_is_live(lifecycle_generation):
                # A replacement node can reuse the same visible name. A late
                # worker belongs to its old instance and must not publish a
                # result/ticket or a cancellation banner into that lifecycle.
                raise asyncio.CancelledError()
            result = execution._hmb_execution_result_snapshot()
            text = execution.parameter_output_values.get("output")
            record = {"text": str(text or ""), "result": copy.deepcopy(result),
                      "observation": execution._hmb_agent_reference_observation_snapshot(),
                      "policy_identity": copy.deepcopy(execution._hmb_shot_policy_identity),
                      "shot": copy.deepcopy(subscription)}
            if result.get("status") != "succeeded":
                raise RuntimeError(str(result.get("message") or "Agent Shot execution failed."))
            if result.get("output_sha256") != _prompt_text_sha256(record["text"]):
                raise RuntimeError("Agent Shot result identity is invalid.")
            with self._hmb_shot_result_lock:
                self._hmb_shot_results[key] = copy.deepcopy(record)
            # Editing another Shot or changing this Shot's future settings
            # must not be overwritten by the completed input snapshot.
            slot = copy.deepcopy(self._hmb_shot_slots.get(key) or slot)
            slot["outputs"] = {name: copy.deepcopy(execution.parameter_output_values.get(name)) for name in ("output", "logs", "agent")}
            slot["result"] = copy.deepcopy(result)
            self._hmb_shot_slots[key] = slot
            self._hmb_shot_run_status[key] = "succeeded"
            if self._hmb_active_slot_key == key and not self._hmb_node_deleted:
                self._hmb_slot_switching = True
                try:
                    for name, value in slot["outputs"].items():
                        if name != "agent":
                            super().set_parameter_value(name, copy.deepcopy(value))
                        self.parameter_output_values[name] = copy.deepcopy(value)
                    self._hmb_execution_result = copy.deepcopy(result)
                    self.parameter_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(result)
                    self.parameter_output_values[_AGENT_EXECUTION_RESULT_PARAMETER] = copy.deepcopy(result)
                    self._refresh_hmb_execution_result_messages()
                finally:
                    self._hmb_slot_switching = False
            self._hmb_persist_shot_store()
            if generator is not None:
                with self._hmb_shot_result_lock:
                    tickets = getattr(self, "_hmb_shot_request_records", None)
                    if tickets is None:
                        tickets = self._hmb_shot_request_records = {}
                    tickets[str(result["run_id"])] = {"key": key, "generator": generator, "record": copy.deepcopy(record)}
            return copy.deepcopy(record)
        except asyncio.CancelledError:
            if self._hmb_lifecycle_is_live(lifecycle_generation):
                self._hmb_shot_run_status[key] = "cancelled"
                with self._hmb_shot_result_lock:
                    self._hmb_shot_results.pop(key, None)
                self._hmb_publish_shot_failure(key, execution, cancelled=True)
            raise
        except Exception:
            if not self._hmb_lifecycle_is_live(lifecycle_generation):
                raise asyncio.CancelledError() from None
            self._hmb_shot_run_status[key] = "failed"
            # A failed new run must not leave the previous successful text as
            # an admissible result for this new Generator execution.
            with self._hmb_shot_result_lock:
                self._hmb_shot_results.pop(key, None)
            self._hmb_publish_shot_failure(key, execution)
            raise
        finally:
            if execution is not None:
                execution._hmb_shot_cancelled = True
                execution._clear_hmb_runtime_policy()
                execution.parameter_values.clear()
                execution.parameter_output_values.clear()
            self._hmb_shot_workers.pop(key, None)
            self._hmb_publish_shot_status()
            lock.release()

    def _hmb_handle_shot_action(self, action):
        if not isinstance(action, dict) or not self._hmb_shot_manager_enabled():
            return
        request_id = str(action.get("request_id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", request_id) or request_id in self._hmb_shot_action_ids:
            return
        self._hmb_shot_action_ids.add(request_id)
        if len(self._hmb_shot_action_ids) > 256:
            self._hmb_shot_action_ids = {request_id}
        selected = self._hmb_shot_channel_subscription()
        channel, shot = selected.get("channel_uuid"), selected.get("shot_uuid")
        if not channel or not shot:
            return
        key = self._hmb_slot_key(channel, shot)
        if action.get("kind") == "cancel_selected":
            worker = self._hmb_shot_workers.get(key)
            if worker is not None:
                worker._hmb_shot_cancelled = True
            return
        if action.get("kind") != "run_selected" or key in self._hmb_shot_workers:
            return
        owner = self._hmb_manager_prompt_owner(channel_uuid=channel, shot_uuid=shot)
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            from griptape_nodes.retained_mode.engine import engine_scope
            engine = GriptapeNodes.get_instance()
            loop = engine.event_manager.event_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                raise RuntimeError("engine_loop_unavailable")
        except Exception:
            self._hmb_shot_run_status[key] = "failed"
            self._set_hmb_execution_result("failed", code="ENGINE_LOOP_UNAVAILABLE",
                message="The Griptape execution loop is unavailable. Reopen this node in the running engine before Run Shot.")
            self._hmb_publish_shot_status()
            return
        async def run():
            with engine_scope(engine):
                try:
                    if engine.node_manager.get_node_by_name(self.name) is not self:
                        return
                    await self._hmb_run_agent_shot(channel_uuid=channel, shot_uuid=shot, prompt_owner=owner)
                except (Exception, asyncio.CancelledError):
                    pass  # Bounded per-Shot failure state is already published.
        future = asyncio.run_coroutine_threadsafe(run(), loop)
        self._hmb_shot_local_tasks.add(future)
        future.add_done_callback(self._hmb_shot_local_tasks.discard)

    def _ensure_agent_shot_rows(self):
        root = getattr(self, "root_ui_element", None)
        children = list(getattr(root, "children", []) or [])
        if not getattr(self, "_hmb_native_editor_elements", None):
            header_index = next((index for index, item in enumerate(children) if getattr(item, "name", "") == _AGENT_WIDGET_PARAMETER), len(children))
            self._hmb_native_editor_elements = [item for item in children[header_index + 1:]
                if (not str(getattr(item, "name", "")).startswith(("HMB_", "SHOT_"))
                    or getattr(item, "name", "") in {_AGENT_EXECUTION_FAILED_WARNING, _AGENT_CREATED_WARNING,
                        _AGENT_PROJECT_POLICY_ABSENT_WARNING, _HMB_POLICY_WARNING_NAME, _HMB_TOPOLOGY_WARNING_NAME})]
        for number in range(1, 6):
            name = _AGENT_SHOT_ROW_PREFIX + str(number)
            if _parameter_exists(self, name):
                continue
            options = {"is_full_width": True, "height": 42, "min_height": 42, "max_height": 42,
                "widget_height": 42, "default_height": 42, "preferred_height": 42, "initial_height": 42,
                "expandable": False, "resizable": False, "compact": True, "hide_handles": True}
            kwargs = {"name": name, "type": "dict", "default_value": {}, "allowed_modes": {ParameterMode.PROPERTY},
                "hide": True, "hide_property": True, "hide_label": True, "ui_options": options}
            if Widget is not None:
                kwargs["traits"] = {Widget(name=_AGENT_WIDGET_NAME, library=_AGENT_WIDGET_LIBRARY_NAME)}
            self.add_parameter(Parameter(**kwargs))
        self._hmb_layout_shot_editor()

    def _hmb_layout_shot_editor(self, *, restored_catalog=None):
        if getattr(self, "_hmb_layout_syncing", False) or getattr(self, "_hmb_node_deleted", False):
            return
        root = getattr(self, "root_ui_element", None)
        if root is None or not getattr(self, "_hmb_native_editor_elements", None):
            return
        self._hmb_layout_syncing = True
        try:
            raw = self._native_parameter_value(_AGENT_WIDGET_PARAMETER, {})
            selected = raw.get("shot", {}) if isinstance(raw, dict) else {}
            catalog = getattr(self, "_hmb_shot_catalog_snapshot", {})
            if not catalog and restored_catalog is not None:
                # Initial-setup values can arrive after the registered hydration
                # callback, before live Source discovery. Saved rows may place
                # the one SDK-owned body, but never become routing authority.
                saved = _agent_widget_shot_catalog(restored_catalog)
                if (saved and saved.get("channel_uuid") == selected.get("channel_uuid")
                        and any(item["shot_uuid"] == selected.get("shot_uuid")
                                for item in saved["shots"])):
                    catalog = saved
            rows = {int(item["number"]): item for item in catalog.get("shots", []) if isinstance(item, dict)}
            selected_uuid = str(selected.get("shot_uuid") or "")
            expanded = bool(selected_uuid and getattr(self, "_hmb_shot_editor_expanded", True))
            body = list(self._hmb_native_editor_elements)
            if not expanded and not self._hmb_native_editor_collapsed:
                self._hmb_native_editor_visibility = {str(item.name): bool((getattr(item, "ui_options", {}) or {}).get("hide", getattr(item, "hide", False))) for item in body}
            for item in body:
                options = dict(getattr(item, "ui_options", {}) or {})
                hidden = True if not expanded else self._hmb_native_editor_visibility.get(str(item.name), options.get("hide", False))
                if bool(options.get("hide", False)) != bool(hidden):
                    updater = getattr(item, "update_ui_options_key", None)
                    if callable(updater):
                        updater("hide", bool(hidden))
                    else:
                        item.ui_options = {**options, "hide": bool(hidden)}
            self._hmb_native_editor_collapsed = not expanded
            # Each row is a tiny SDK widget. Native controls stay one SDK-owned
            # set, immediately after the expanded row, with their original IDs.
            current = list(getattr(root, "children", []) or [])
            row_elements = []
            for number in range(1, 6):
                parameter = _parameter_by_name(self, _AGENT_SHOT_ROW_PREFIX + str(number))
                if parameter is None:
                    continue
                shot = rows.get(number)
                visible = shot is not None
                if bool((getattr(parameter, "ui_options", {}) or {}).get("hide", False)) == visible:
                    parameter.update_ui_options_key("hide", not visible)
                if getattr(parameter, "hide_property", False) == visible:
                    parameter.hide_property = not visible
                value = ({"schema": "hmb-agent-shot-row", "version": 1,
                    "shot": {"channel_uuid": catalog.get("channel_uuid", ""), **shot},
                    "selected": selected_uuid == shot["shot_uuid"],
                    "expanded": bool(expanded and selected_uuid == shot["shot_uuid"]),
                    "request_id": getattr(self, "_hmb_row_action_ack", {}).get(self._hmb_slot_key(catalog.get("channel_uuid"), shot["shot_uuid"]), ""),
                    "status": self._hmb_shot_run_status.get(self._hmb_slot_key(catalog.get("channel_uuid"), shot["shot_uuid"]), "")}
                    if shot else {"schema": "hmb-agent-shot-row", "version": 1, "shot": {}, "selected": False, "expanded": False, "status": ""})
                if self._native_parameter_value(parameter.name, {}) != value:
                    self._hmb_row_syncing = True
                    try:
                        self.set_parameter_value(parameter.name, value)
                    finally:
                        self._hmb_row_syncing = False
                row_elements.append(parameter)
            header = _parameter_by_name(self, _AGENT_WIDGET_PARAMETER)
            excluded = {id(item) for item in body + row_elements + ([header] if header else [])}
            before_header = current[:current.index(header)] if header in current else []
            prefix = [item for item in before_header if id(item) not in excluded]
            trailing = [item for item in current if id(item) not in excluded and item not in prefix]
            ordered = prefix + ([header] if header else [])
            inserted = False
            for row in row_elements:
                ordered.append(row)
                row_value = self._native_parameter_value(row.name, {})
                if row_value.get("selected"):
                    ordered.extend(body)
                    inserted = True
            if not inserted:
                ordered.extend(body)
            ordered.extend(trailing)
            if [id(item) for item in ordered] != [id(item) for item in current]:
                reorder = getattr(self, "reorder_elements", None)
                if callable(reorder):
                    reorder([item.name for item in ordered])
                elif isinstance(getattr(root, "children", None), list):
                    root.children[:] = ordered
        finally:
            self._hmb_layout_syncing = False

    def _set_parameter_visibility(self, names, *, visible):
        collapsed = bool(getattr(self, "_hmb_native_editor_collapsed", False))
        values = [names] if isinstance(names, str) else list(names)
        body_names = {str(item.name) for item in getattr(self, "_hmb_native_editor_elements", [])}
        parent = getattr(super(), "_set_parameter_visibility", None)
        for name in values:
            if collapsed and name in body_names:
                self._hmb_native_editor_visibility[name] = not visible
                if callable(parent):
                    parent(name, visible=False)
            elif callable(parent):
                parent(name, visible=visible)

    def _set_message_visibility(self, names, *, visible):
        collapsed = bool(getattr(self, "_hmb_native_editor_collapsed", False))
        values = [names] if isinstance(names, str) else list(names)
        body_names = {str(item.name) for item in getattr(self, "_hmb_native_editor_elements", [])}
        parent = getattr(super(), "_set_message_visibility", None)
        for name in values:
            if collapsed and name in body_names:
                self._hmb_native_editor_visibility[name] = not visible
                if callable(parent):
                    parent(name, visible=False)
            elif callable(parent):
                parent(name, visible=visible)

    def _hmb_handle_row_action(self, parameter, value):
        if getattr(self, "_hmb_row_syncing", False) or not isinstance(value, dict):
            return
        action = value.get("action")
        if not isinstance(action, dict) or action.get("kind") not in {"select", "run_selected", "cancel_selected", "refresh"}:
            return
        request_id = str(action.get("request_id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", request_id):
            return
        if action["kind"] == "select" and request_id in self._hmb_shot_action_ids:
            self._hmb_layout_shot_editor()
            return
        catalog = getattr(self, "_hmb_shot_catalog_snapshot", {})
        requested = value.get("shot", {})
        exact = [item for item in catalog.get("shots", []) if item.get("shot_uuid") == requested.get("shot_uuid")
            and _AGENT_SHOT_ROW_PREFIX + str(item.get("number")) == parameter.name]
        if len(exact) != 1 or requested.get("channel_uuid") != catalog.get("channel_uuid"):
            raise RuntimeError("Agent Shot row identity is unavailable.")
        if action["kind"] == "refresh":
            # Read the current editor, even if the missing action never applied.
            # No slot selection, input mutation, model or Run is replayed.
            if not hasattr(self, "_hmb_row_action_ack"):
                self._hmb_row_action_ack = {}
            self._hmb_row_action_ack[self._hmb_slot_key(catalog["channel_uuid"], exact[0]["shot_uuid"])] = request_id
            self._hmb_layout_shot_editor()
            return
        if action["kind"] == "select":
            self._hmb_shot_action_ids.add(request_id)
            if len(self._hmb_shot_action_ids) > 256:
                self._hmb_shot_action_ids = {request_id}
            self._hmb_legacy_saved_widget_value = None
        raw = self._native_parameter_value(_AGENT_WIDGET_PARAMETER, {})
        current = raw.get("shot", {}) if isinstance(raw, dict) else {}
        shot = exact[0]
        same = current.get("shot_uuid") == shot["shot_uuid"] and current.get("channel_uuid") == catalog["channel_uuid"]
        next_value = self._hmb_widget_value({"channel_uuid": catalog["channel_uuid"], **shot}, catalog)
        next_value["shot_editor_expanded"] = (
            action["expanded"] if action["kind"] == "select" and type(action.get("expanded")) is bool
            else not self._hmb_shot_editor_expanded if same and action["kind"] == "select" else True)
        if action["kind"] != "select":
            next_value["action"] = {"kind": action["kind"], "request_id": request_id}
        self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_value)
        # A transport promise is not proof that the native editor switched.
        # Publish this acknowledgement only after its exact Shot action applied.
        if not hasattr(self, "_hmb_row_action_ack"):
            self._hmb_row_action_ack = {}
        self._hmb_row_action_ack[self._hmb_slot_key(catalog["channel_uuid"], shot["shot_uuid"])] = request_id
        self._hmb_layout_shot_editor()

    @staticmethod
    def _hmb_authoring_digest(value):
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Agent migration contains unsupported live values; the original node must be kept.") from exc
        return hashlib.sha256(encoded).hexdigest()

    def _hmb_capture_saved_parameter_value(self, name, value, *, is_output=False):
        """Record raw saved identity before SDK value normalization; no UI work."""
        if is_output:
            return
        normalized_name = self._publication_parameter_name(name)
        if normalized_name == _AGENT_SHOT_PROMPT_INPUT_PARAMETER.casefold():
            if isinstance(getattr(value, "value", value), str) and str(getattr(value, "value", value) or "").strip():
                # Serialized Prompt edges can hydrate before the unique Prompt
                # manager exists. Unready projection is not a user disconnect.
                self._hmb_prompt_preview_hydration_pending = True
            return
        if not isinstance(value, dict):
            return
        if normalized_name == _AGENT_SHOT_STORE_PARAMETER.casefold() and value.get("schema") == _AGENT_SHOT_STORE_SCHEMA and value.get("version") == 1 and isinstance(value.get("slots"), dict):
            self._hmb_loaded_durable_shot_store = True
        elif normalized_name == _AGENT_WIDGET_PARAMETER.casefold() and value.get("shot_manager") is not True:
            self._hmb_legacy_saved_widget_value = copy.deepcopy(value)

    def _hmb_export_agent_authoring_state(self):
        slot = self._hmb_native_slot_snapshot()
        slots = copy.deepcopy(getattr(self, "_hmb_shot_slots", {}))
        subscription = copy.deepcopy(self._hmb_shot_channel_subscription())
        legacy_widget = getattr(self, "_hmb_legacy_saved_widget_value", None)
        if isinstance(legacy_widget, dict):
            legacy_shot = legacy_widget.get("shot") or {}
            channel = str(legacy_shot.get("channel_uuid") or "")
            shot_uuid = str(legacy_shot.get("shot_uuid") or "")
            subscription.update(enabled=bool(channel and shot_uuid), channel_uuid=channel,
                shot_uuid=shot_uuid, shot_number=int(legacy_shot.get("number") or 1),
                shot_name=str(legacy_shot.get("name") or ""))
            if not getattr(self, "_hmb_loaded_durable_shot_store", False):
                # Pre-manager files had one native authoring body. Any slots
                # created while loading their new editor are presentation
                # defaults, not additional authored Shots.
                slots = {}
        active = self._hmb_slot_key(subscription.get("channel_uuid"), subscription.get("shot_uuid"))
        slots[active] = copy.deepcopy(slot)
        children = {}
        for parent_name in ("tools", "rulesets"):
            parent = _parameter_by_name(self, parent_name)
            children[parent_name] = [{"name": str(child.name),
                "ui_options": copy.deepcopy(getattr(child, "ui_options", {}) or {}),
                "input_types": list(getattr(child, "input_types", []) or []),
                "type": getattr(child, "type", None),
                "allowed_modes": [str(getattr(mode, "value", mode)) for mode in (getattr(child, "allowed_modes", []) or [])],
                "default_value": copy.deepcopy(getattr(child, "default_value", None))}
                for child in list(getattr(parent, "children", []) or [])]
        data = {"schema": "hmb-agent-authoring-export", "version": 1, "source_node": str(self.name),
            "active_subscription": subscription, "active_slot_key": active, "native_slot": copy.deepcopy(slot),
            "slots": slots, "results": ({} if isinstance(legacy_widget, dict) and not getattr(self, "_hmb_loaded_durable_shot_store", False)
                else copy.deepcopy(getattr(self, "_hmb_shot_results", {}))),
            "child_parameters": children,
            "archives": copy.deepcopy(getattr(self, "_hmb_agent_migration_archives", {})),
            "legacy_widget": copy.deepcopy(legacy_widget),
            "loaded_durable_shot_store": bool(getattr(self, "_hmb_loaded_durable_shot_store", False)),
            "private_cache": {
                "slots": copy.deepcopy(getattr(self, "_hmb_shot_slots", {})),
                "results": copy.deepcopy(getattr(self, "_hmb_shot_results", {})),
                "archives": copy.deepcopy(getattr(self, "_hmb_agent_migration_archives", {})),
                "active_slot_key": str(getattr(self, "_hmb_active_slot_key", "__hmb_only__")),
                "legacy_widget": copy.deepcopy(legacy_widget),
                "loaded_durable_shot_store": bool(getattr(self, "_hmb_loaded_durable_shot_store", False))},
            "request_records": [copy.deepcopy(ticket["record"]) for ticket in getattr(self, "_hmb_shot_request_records", {}).values()]}
        data["digest"] = self._hmb_authoring_digest(data)
        return data

    def _hmb_restore_agent_authoring_state(self, exported):
        """Restore migration rollback caches after SDK restores native state."""
        if not isinstance(exported, dict) or exported.get("schema") != "hmb-agent-authoring-export" or exported.get("version") != 1:
            raise RuntimeError("Agent rollback document is invalid.")
        document = copy.deepcopy(exported)
        digest = str(document.pop("digest", ""))
        if not hmac.compare_digest(digest, self._hmb_authoring_digest(document)):
            raise RuntimeError("Agent rollback document digest does not match.")
        cache = document.get("private_cache")
        if not isinstance(cache, dict) or any(not isinstance(cache.get(key), dict) for key in ("slots", "results", "archives")):
            raise RuntimeError("Agent rollback private state is invalid.")
        self._hmb_shot_slots = cache["slots"]
        self._hmb_shot_results = cache["results"]
        self._hmb_agent_migration_archives = cache["archives"]
        self._hmb_active_slot_key = str(cache.get("active_slot_key") or "__hmb_only__")
        self._hmb_legacy_saved_widget_value = cache.get("legacy_widget")
        self._hmb_loaded_durable_shot_store = cache.get("loaded_durable_shot_store") is True
        return True

    def _hmb_import_agent_authoring_state(self, exported, *, source_alias=None):
        if not isinstance(exported, dict) or exported.get("schema") != "hmb-agent-authoring-export" or exported.get("version") != 1:
            raise RuntimeError("Agent migration document is invalid.")
        document = copy.deepcopy(exported)
        digest = str(document.pop("digest", ""))
        if not hmac.compare_digest(digest, self._hmb_authoring_digest(document)):
            raise RuntimeError("Agent migration document digest does not match.")
        source = str(source_alias or document.get("source_node") or "").strip()
        if not source or not isinstance(document.get("slots"), dict) or not isinstance(document.get("results"), dict):
            raise RuntimeError("Agent migration source identity is invalid.")
        slots = copy.deepcopy(getattr(self, "_hmb_shot_slots", {}))
        results = copy.deepcopy(getattr(self, "_hmb_shot_results", {}))
        archives = copy.deepcopy(getattr(self, "_hmb_agent_migration_archives", {}))
        aliases = {}
        planned_children = []
        for parent_name, specifications in document.get("child_parameters", {}).items():
            if parent_name not in {"tools", "rulesets"} or not isinstance(specifications, list):
                raise RuntimeError("Agent migration native child definition is invalid.")
            parent = _parameter_by_name(self, parent_name)
            if parent is None:
                raise RuntimeError("Agent migration native list is unavailable.")
            for specification in specifications:
                name = str(specification.get("name") or "")
                if not name or any(char.isspace() for char in name):
                    raise RuntimeError("Agent migration native child name is invalid.")
                existing = _parameter_by_name(self, name)
                target = name
                if existing is not None:
                    if str(getattr(existing, "parent_container_name", "")) == parent_name and source == self.name:
                        aliases[name] = name
                        continue
                    target = parent_name + "_HMBMigration_" + hashlib.sha256((source + "\x1f" + name).encode("utf-8")).hexdigest()[:20]
                    existing = _parameter_by_name(self, target)
                    if existing is not None:
                        if str(getattr(existing, "parent_container_name", "")) != parent_name:
                            raise RuntimeError("Agent migration native child identity conflicts.")
                        aliases[name] = target
                        continue
                aliases[name] = target
                planned_children.append((parent, target, specification))
        def remap_slot(slot):
            if not isinstance(slot, dict):
                raise RuntimeError("Agent migration Shot settings are invalid.")
            result = copy.deepcopy(slot)
            result["children"] = {aliases.get(name, name): value for name, value in (result.get("children") or {}).items()}
            return result
        for key, value in document["slots"].items():
            if "\x1f" not in str(key):
                continue
            incoming = remap_slot(value)
            if key in slots and slots[key] != incoming:
                raise RuntimeError("Two Agents contain different settings for the same Shot; both originals must be kept.")
            slots[key] = incoming
        for key, value in document["results"].items():
            if key in results and results[key] != value:
                raise RuntimeError("Two Agents contain different results for the same Shot; both originals must be kept.")
            results[key] = copy.deepcopy(value)
        # Unbound/old independent content is preserved without executing it.
        archive = {"native_slot": remap_slot(document["native_slot"]),
            "unbound_slots": {key: remap_slot(value) for key, value in document["slots"].items() if "\x1f" not in str(key)},
            "source_archives": copy.deepcopy(document.get("archives") or {}),
            "request_records": copy.deepcopy(document.get("request_records") or []),
            "legacy_widget": copy.deepcopy(document.get("legacy_widget")), "source_digest": digest}
        if source in archives and archives[source] != archive:
            raise RuntimeError("Agent migration archive already contains different original data.")
        archives[source] = archive
        before = (self._hmb_shot_slots, self._hmb_shot_results, self._hmb_agent_migration_archives,
            copy.deepcopy(dict(self.parameter_values)), copy.deepcopy(dict(self.parameter_output_values)))
        added = []
        self._hmb_slot_switching = True
        try:
            for parent, name, specification in planned_children:
                child = parent.add_child_parameter()
                added.append((parent, child))
                child.name = name
                child.default_value = copy.deepcopy(specification.get("default_value"))
                child.ui_options = {**dict(specification.get("ui_options") or {}), "hide": True}
            self._hmb_shot_slots = slots
            self._hmb_shot_results = results
            self._hmb_agent_migration_archives = archives
            self._hmb_persist_shot_store()
            if self._hmb_shot_slots != slots or self._hmb_shot_results != results or self._hmb_agent_migration_archives.get(source) != archive:
                raise RuntimeError("Agent migration verification failed.")
        except Exception:
            for parent, child in reversed(added):
                parent.remove_child(child)
            self._hmb_shot_slots, self._hmb_shot_results, self._hmb_agent_migration_archives = before[:3]
            self.parameter_values.clear(); self.parameter_values.update(before[3])
            self.parameter_output_values.clear(); self.parameter_output_values.update(before[4])
            raise
        finally:
            self._hmb_slot_switching = False
        return {"schema": "hmb-agent-authoring-import", "version": 1, "source_node": source,
            "source_digest": digest, "parameter_aliases": aliases, "slot_keys": sorted(slots),
            "state_digest": self._hmb_authoring_digest({"slots": slots, "results": results, "archives": archives})}

    def _ensure_hmb_execution_result(self) -> None:
        """Persist handled failure separately from text and private Agent state."""
        if not _parameter_exists(self, _AGENT_EXECUTION_RESULT_PARAMETER):
            self.add_parameter(Parameter(
                name=_AGENT_EXECUTION_RESULT_PARAMETER,
                type="dict", default_value={},
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                settable=False, hide=True, hide_property=True, hide_label=True,
                ui_options={"hide": True, "hide_property": True, "hide_handles": True},
            ))
        if ParameterMessage is not None:
            root = getattr(self, "root_ui_element", None)
            children = getattr(root, "children", None) or getattr(root, "_children", [])
            if not any(getattr(child, "name", "") == _AGENT_EXECUTION_FAILED_WARNING
                       for child in children):
                self.add_node_element(ParameterMessage(
                    name=_AGENT_EXECUTION_FAILED_WARNING,
                    title="Agent failed · other shots continue",
                    variant="error", hide=True,
                    value="This Agent failed. Its new render is skipped; independent shots continue. See FINAL TEXT for the reason.",
                ))
            if not any(getattr(child, "name", "") == _AGENT_CREATED_WARNING for child in children):
                self.add_node_element(ParameterMessage(
                    name=_AGENT_CREATED_WARNING,
                    title="Agent 객체 생성 · 모델 추론 없음",
                    variant="warning", hide=True, value=_AGENT_CREATED_MESSAGE,
                ))
            if not any(getattr(child, "name", "") == _AGENT_PROJECT_POLICY_ABSENT_WARNING for child in children):
                self.add_node_element(ParameterMessage(
                    name=_AGENT_PROJECT_POLICY_ABSENT_WARNING,
                    title="프로젝트 정책 없음 · 계속 실행",
                    variant="info", hide=True, value=_AGENT_PROJECT_POLICY_ABSENT_MESSAGE,
                ))
        self._refresh_hmb_execution_result_messages()

    def _hmb_execution_result_snapshot(self) -> dict[str, Any]:
        result = getattr(self, "_hmb_execution_result", None)
        if not isinstance(result, dict) or not result:
            result = getattr(self, "parameter_values", {}).get(_AGENT_EXECUTION_RESULT_PARAMETER)
        return copy.deepcopy(result) if isinstance(result, dict) else {}

    def _refresh_hmb_execution_result_messages(self) -> None:
        """Restore result advisories from saved facts, never displayed output."""
        result = self._hmb_execution_result_snapshot()
        created = (result.get("status") == "created" and result.get("code") == "AGENT_CREATED"
                   and result.get("inference_started") is False and result.get("policy_applied") is False)
        for name, visible in ((_AGENT_EXECUTION_FAILED_WARNING, result.get("status") == "failed"),
                              (_AGENT_CREATED_WARNING, created),
                              (_AGENT_PROJECT_POLICY_ABSENT_WARNING, result.get("policy_status") == "absent")):
            try:
                if visible:
                    self.show_message_by_name(name)
                else:
                    self.hide_message_by_name(name)
            except Exception:
                pass

    def _hmb_agent_reference_observation_snapshot(self) -> dict[str, Any]:
        """Read-only observations for the current Agent run, never source access."""
        report = getattr(self, "_hmb_reference_observation", {})
        return copy.deepcopy(report) if isinstance(report, dict) else {}

    def _begin_hmb_reference_observation(self, machine: str) -> str:
        result = self._hmb_execution_result_snapshot()
        run_id = str(result.get("run_id") or "") if result.get("status") == "running" else secrets.token_hex(16)
        self._hmb_reference_observation_run_id = run_id
        self._hmb_reference_observation = {
            "schema": "hmb-agent-reference-observation", "version": 1, "run_id": run_id,
            "machine_sha256": _prompt_text_sha256(machine), "status": "unobserved",
            "coverage": [], "skips": [], "groups": [], "budget_summary": {},
        }
        return run_id

    def _store_hmb_reference_observation(self, report: dict[str, Any], run_id: str,
                                         generation: int, machine_hash: str) -> None:
        if (not self._hmb_lifecycle_is_live(generation)
                or (bool(getattr(self, "is_cancellation_requested", False))
                    and (not isinstance(report, dict) or report.get("status") != "cancelled" or report.get("coverage")))
                or str(getattr(self, "_hmb_reference_observation_run_id", "")) != run_id
                or _prompt_text_sha256(str(getattr(self, "_hmb_runtime_prompt", "") or "")) != machine_hash
                or not isinstance(report, dict) or report.get("machine_sha256") != machine_hash
                or report.get("schema") != "hmb-agent-reference-observation" or report.get("version") != 1):
            return
        self._hmb_reference_observation = copy.deepcopy(report)
        self._hmb_reference_observation["run_id"] = run_id

    def _mark_hmb_reference_observation_submission(self, run_id: str, submitted: bool) -> None:
        report = getattr(self, "_hmb_reference_observation", {})
        if not run_id or not isinstance(report, dict) or report.get("run_id") != run_id:
            return
        if submitted:
            report["native_input_status"] = "passed_to_native_processor"
        else:
            report["native_input_status"] = "not_submitted"
            report["status"] = "cancelled"
            for row in report.get("coverage", []):
                report.setdefault("skips", []).append({**row, "reason": "cancelled_before_native_submission"})
            report["coverage"] = []
            report["groups"] = []
            report.setdefault("budget_summary", {})["attachments_delivered"] = 0

    def _set_hmb_execution_result(self, status: str, *, code: str = "", message: str = "") -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        output = str(getattr(self, "parameter_output_values", {}).get("output") or "").strip()
        previous = self._hmb_execution_result_snapshot()
        if status == "running":
            self._hmb_reference_observation = {}
            self._hmb_reference_observation_run_id = ""
        result = {
            "schema": "hmb-agent-execution-result", "version": 1,
            "status": status, "code": code, "message": message,
            "run_id": secrets.token_hex(16) if status == "running" else str(previous.get("run_id") or ""),
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest() if status == "succeeded" else "",
            "inference_started": bool(getattr(self, "_hmb_native_inference_started", False)),
            "policy_applied": bool(getattr(self, "_hmb_run_policy_applied", False)),
            "policy_status": ("absent" if getattr(self, "_hmb_run_policy_omitted", False)
                              else "applied" if getattr(self, "_hmb_run_policy_applied", False) else "not_applied"),
        }
        project = getattr(self, "_hmb_run_project_identity", {})
        if isinstance(project, dict) and project.get("project_id"):
            result.update(project_id=project["project_id"], project_name=project.get("project_name", ""))
        observation = self._hmb_agent_reference_observation_snapshot()
        if observation and observation.get("run_id") == result["run_id"]:
            observation["agent_status"] = status
            self._hmb_reference_observation = copy.deepcopy(observation)
            result["reference_observation"] = observation
        # The host clears output values before scheduling a new run. Preserve
        # the handled result in an instance-owned value and serializable property.
        self._hmb_execution_result = result
        self.parameter_values[_AGENT_EXECUTION_RESULT_PARAMETER] = dict(result)
        self.parameter_output_values[_AGENT_EXECUTION_RESULT_PARAMETER] = dict(result)
        self._refresh_hmb_execution_result_messages()

    def _hmb_issue_web_rerender_authority(self, *, request_id, generator, owner_key):
        return _issue_hmb_web_rerender_authority(
            self, request_id=request_id, generator=generator, owner_key=owner_key
        )

    def _hmb_web_rerender_busy(self, *, generator=None) -> bool:
        if self._hmb_shot_manager_enabled():
            if generator is None:
                return any(lock.locked() for lock in self._hmb_shot_execution_locks.values())
            getter = getattr(generator, "_hmb_shot_channel_subscription", None)
            subscription = getter() if callable(getter) else {}
            if not isinstance(subscription, dict) or not subscription.get("enabled"):
                return True
            key = self._hmb_slot_key(subscription.get("channel_uuid"), subscription.get("shot_uuid"))
            lock = self._hmb_shot_execution_locks.get(key)
            return bool(lock is not None and lock.locked())
        return _agent_execution_gate(self).locked()

    def _hmb_selected_project(self) -> dict[str, str]:
        """Resolve only the verified Prompt's connected ImageAsset identity."""
        source = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
        project_getter = getattr(source, "_hmb_project_identity", None)
        if callable(project_getter):
            return resolve_project(project_getter(), default_legacy=False)
        sources = getattr(source, "_hmb_connected_source_nodes", {})
        selected = []
        if isinstance(sources, dict):
            for key in ("SHOT_ASSET_IN", "IMAGE_ASSET_IN"):
                asset = sources.get(key)
                if asset is not None and not any(asset is other for other in selected):
                    selected.append(asset)
        if len(selected) > 1:
            raise ValueError("project_source_ambiguous")
        if selected:
            asset = selected[0]
            identity = getattr(asset, "_hmb_project_identity", None)
            if callable(identity):
                return resolve_project(identity(), default_legacy=False)
            getter = getattr(asset, "get_parameter_value", None)
            if not callable(getter):
                raise ValueError("project_source_unavailable")
            return project_from_asset_payload(getter("HMB_IMAGE_ASSET_STATE"), default_legacy=False)
        # Old Prompt-only workflows have no asset project. A legacy rich
        # ImageAsset input may still carry one; do not infer from user prose.
        getter = getattr(source, "get_parameter_value", None)
        projects = []
        if callable(getter):
            for key in ("SHOT_ASSET_IN", "IMAGE_ASSET_IN"):
                try:
                    value = getter(key)
                except Exception:
                    continue
                if value is None or value == "":
                    continue
                # Legacy IMAGE_ASSET_IN is a wildcard and may contain ordinary
                # media values/data URIs/lists, with no library identity at
                # all. Only object-shaped project payloads participate here;
                # malformed JSON objects still fail instead of becoming SW.
                if isinstance(value, str) and not value.lstrip().startswith("{"):
                    continue
                if isinstance(value, (list, tuple)):
                    project_fields = {"project_id", "project_name", "project_folder", "project_root", "project"}
                    if any(isinstance(item, dict) and project_fields.intersection(item) for item in value):
                        raise ValueError("project_payload_invalid")
                    continue
                if not isinstance(value, (dict, str)):
                    continue
                try:
                    projects.append(project_from_asset_payload(value, default_legacy=False))
                except ValueError as exc:
                    if str(exc) != "project_required":
                        raise
        if projects and any(item["project_id"] != projects[0]["project_id"] for item in projects):
            raise ValueError("project_identity_mismatch")
        return projects[0] if projects else resolve_project()

    def _hmb_web_rerender_policy_status(self, project_id=None) -> dict[str, Any]:
        """Read-only runtime usability and policy evidence; no session claim.

        The worker may call this in to_thread for heartbeat publication. This
        verifies any present artifact. Missing project rules are optional;
        web revision never reinjects them into the recorded parent prompt.
        """
        try:
            project = resolve_project(project_id) if project_id is not None else self._hmb_selected_project()
            state = _hmb._agent_policy_session_state(project["project_id"])
            if str(state).casefold() in {"failed", "closed"}:
                return {"ready": False, "version": "", "sha256": "", "reason": "policy_session_unavailable",
                        "policy_verified": False, "policy_status": "unavailable"}
            payload = _hmb._load_verified_agent_rule_payload(project["project_id"])
            return {
                "ready": True,
                "version": str(payload.get("final_policy_version") or ""),
                "sha256": str(payload.get("envelope_sha256") or ""),
                "reason": "",
                "policy_verified": True,
                "policy_status": "available",
            }
        except ProjectPolicyPendingError:
            return {"ready": True, "version": "", "sha256": "", "reason": "project_policy_pending",
                    "policy_verified": False, "policy_status": "absent"}
        except Exception:
            return {"ready": False, "version": "", "sha256": "", "reason": "policy_unavailable",
                    "policy_verified": False, "policy_status": "unavailable"}

    async def _hmb_run_web_rerender(
        self, prompt, media_snapshot, generation_settings, request_identity
    ) -> dict[str, Any]:
        """Run one authenticated web prompt without publishing or editing nodes.

        The engine worker reserves and verifies the exact Generator first. A
        local capability, never request JSON, authorizes revision of the
        already-policy-applied parent prompt. No HMB policy is loaded or
        reinjected. Original Prompt text and paired snapshots are intentionally
        not consulted. Ordinary editor execution retains its canonical edge gate.
        """
        if type(request_identity) is not _HMBWebRerenderAuthority:
            raise TypeError("Web rerender requires engine-issued authority.")
        request_identity._claim(self)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 54000:
            raise ValueError("Web rerender prompt must contain 1 to 54000 characters.")
        media, settings = _web_rerender_snapshots(media_snapshot, generation_settings, prompt)
        native_settings = None
        gate = None
        gate_owned = False
        execution = None
        try:
            if self._hmb_shot_manager_enabled():
                getter = getattr(request_identity.generator, "_hmb_shot_channel_subscription", None)
                subscription = getter() if callable(getter) else {}
                matches = [item for item in self._hmb_agent_shot_subscriptions() if isinstance(subscription, dict)
                           and all(item.get(key) == subscription.get(key) for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name"))]
                if len(matches) != 1:
                    raise RuntimeError("Web rerender Agent Shot identity is unavailable.")
                key = self._hmb_slot_key(subscription["channel_uuid"], subscription["shot_uuid"])
                gate = self._hmb_shot_execution_locks.setdefault(key, threading.Lock())
                while not gate.acquire(blocking=False):
                    await asyncio.sleep(0.05)
                gate_owned = True
                if self._hmb_active_slot_key == key:
                    self._hmb_capture_active_slot()
                slot = self._hmb_shot_slots.get(key) or self._hmb_shot_slots.get("__hmb_default_settings__") or self._hmb_native_slot_snapshot()
                native_settings = copy.deepcopy(slot.get("values") or {})
            else:
                gate = await _acquire_agent_execution_gate(self)
                gate_owned = True
            cancel_source = self if native_settings is None else request_identity.generator
            if not self._hmb_lifecycle_is_live() or bool(getattr(cancel_source, "is_cancellation_requested", False)):
                raise RuntimeError("Web rerender Agent is unavailable.")
            if bool(getattr(request_identity.generator, "_hmb_node_deleted", False)):
                raise RuntimeError("Web rerender Generator is unavailable.")
            execution = (_HMBWebRerenderExecution._from_owner(self, prompt, media, settings)
                         if native_settings is None else
                         _HMBWebRerenderExecution._from_owner(self, prompt, media, settings, native_settings=native_settings))
            if native_settings is not None:
                execution._hmb_web_cancel_source = request_identity.generator
            policy_identity = {"mode": "preserved_parent", "reinjected": False}
            run_id = secrets.token_hex(16)
            execution._hmb_execution_result = {"status": "running", "run_id": run_id}
            iterator = execution._run_native_agent_once()
            try:
                try:
                    step = next(iterator)
                    while True:
                        value = await _run_web_rerender_worker(execution, step)
                        step = iterator.send(value)
                except StopIteration:
                    pass
            finally:
                iterator.close()
            if not execution._hmb_lifecycle_is_live() or execution.is_cancellation_requested:
                raise asyncio.CancelledError()
            execution._secure_hmb_outputs()
            text = execution.parameter_output_values.get("output")
            if execution._hmb_last_sanitizer_status != "clean":
                raise RuntimeError(_HMB_EXECUTION_FAILED_MESSAGE)
            text = _web_rerender_instruction(text, prompt)
            return {
                "text": text,
                "run_id": run_id,
                "output_sha256": _prompt_text_sha256(text),
                "policy_identity": policy_identity,
                "observation": execution._hmb_agent_reference_observation_snapshot(),
            }
        except asyncio.CancelledError:
            raise
        except _HMBWebRerenderOutputContractError:
            raise _HMBWebRerenderOutputContractError(
                "WEB_RERENDER_OUTPUT_CONTRACT: The Agent did not return a valid final "
                "Generator instruction. No video generation was submitted."
            ) from None
        except Exception as exc:
            if str(exc) == _HMB_POLICY_UNAVAILABLE_MESSAGE:
                raise
            code = str(getattr(execution, "_hmb_native_failure_code", "") or _hmb_native_failure_code(exc))
            raise RuntimeError(_hmb_execution_failure_message(code)) from None
        finally:
            if execution is not None:
                execution._hmb_web_cancelled = True
                execution._clear_hmb_runtime_policy()
                execution.parameter_values.clear()
                execution.parameter_output_values.clear()
                execution._hmb_verified_prompt_source_node = None
            if gate_owned:
                gate.release()

    async def aprocess(self) -> None:
        if self._hmb_shot_manager_enabled():
            self._hmb_capture_active_slot()
            self._refresh_agent_shot_route(strict=True)
            return
        gate = await _acquire_agent_execution_gate(self)
        try:
            await self._hmb_aprocess_locked()
            self._hmb_capture_active_slot()
        finally:
            gate.release()

    async def _hmb_aprocess_locked(self) -> None:
        """Handle this Agent's failure without canceling independent host tasks.

        The synchronous process keeps its strict error contract. Only the host
        execution boundary handles it, publishes an explicit failure, and lets
        downstream generation skip the failed data dependency before a new submission.
        """
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        self._hmb_native_inference_started = False
        self._hmb_native_run_completed = False
        self._hmb_run_hmb_source = False
        self._hmb_run_policy_applied = False
        self._hmb_policy_omitted = False
        self._hmb_run_policy_omitted = False
        self._hmb_run_project_identity = {}
        self._set_hmb_execution_result("running")
        self._set_visible_output("")
        self.parameter_output_values["agent"] = {}
        self._last_raw_output = None
        try:
            await super().aprocess()
        except asyncio.CancelledError:
            if not bool(getattr(self, "_hmb_node_deleted", False)):
                message = "[HMB EXECUTION CANCELLED] Agent execution was cancelled. No new render was submitted."
                self._publish_hmb_execution_block(message)
                self._set_hmb_execution_result("failed", code="CANCELLED", message=message)
            raise  # Explicit user/host cancellation must still stop work.
        except Exception as exc:
            code = str(getattr(self, "_hmb_native_failure_code", "") or _hmb_native_failure_code(exc))
            known = {
                _HMB_POLICY_UNAVAILABLE_MESSAGE: "POLICY_UNAVAILABLE",
                _HMB_PROJECT_POLICY_PENDING_MESSAGE: "PROJECT_POLICY_PENDING",
                _HMB_TOPOLOGY_UNAVAILABLE_MESSAGE: "SOURCE_UNAVAILABLE",
                _HMB_SOURCE_CONTRACT_INVALID_MESSAGE: "SOURCE_UNAVAILABLE",
            }
            if str(exc) in known:
                message, code = str(exc), known[str(exc)]
            else:
                message = _hmb_execution_failure_message(code)
            self._publish_hmb_execution_block(message)
            self._set_hmb_execution_result("failed", code=code, message=message)
            return
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        if (getattr(self, "_hmb_native_run_completed", False)
                and not getattr(self, "_hmb_native_inference_started", False)):
            # Standard Agent completes its empty-prompt branch by constructing
            # an Agent object. Completion is observed at the native iterator;
            # final text never decides whether model inference actually ran.
            if not getattr(self, "_hmb_run_hmb_source", False):
                self._set_hmb_execution_result("created", code="AGENT_CREATED", message=_AGENT_CREATED_MESSAGE)
                return
            message = _hmb_execution_failure_message("EMPTY_OUTPUT")
            self._publish_hmb_execution_block(message)
            self._set_hmb_execution_result("failed", code="EMPTY_OUTPUT", message=message)
            return
        output = self.parameter_output_values.get("output")
        if not isinstance(output, str) or not output.strip() or output == _PUBLIC_OUTPUT_BLOCKED:
            code = "EMPTY_OUTPUT" if not output else "OUTPUT_UNAVAILABLE"
            message = _hmb_execution_failure_message(code) if code == "EMPTY_OUTPUT" else _PUBLIC_OUTPUT_BLOCKED
            self._publish_hmb_execution_block(message)
            self._set_hmb_execution_result("failed", code=code, message=message)
            return
        self._set_hmb_execution_result(
            "succeeded", code="NO_PROJECT_POLICY" if self._hmb_run_policy_omitted else "",
            message=_AGENT_PROJECT_POLICY_ABSENT_MESSAGE if self._hmb_run_policy_omitted else "",
        )

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
            next_ui = self._hmb_widget_value()
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

        # Unified managers discover the existing same-flow catalog even when
        # legacy independent-Agent autoclaim is intentionally disabled.
        if (
            bool(getattr(self, "_hmb_node_deleted", False))
            or (not self._hmb_shot_manager_enabled() and not bool(
                getattr(self, "_hmb_initial_shot_autoclaim_pending", False)
            ))
        ):
            return
        self._refresh_agent_shot_route()
        self._refresh_routed_prompt_preview()
        self._hmb_post_hydration_state_restore()

    def _hmb_post_hydration_state_restore(self) -> None:
        """Normalize saved root order on the existing registered next-turn seam.

        SDK initial_setup restores native values and root element order without
        calling after_value_set. A byte-identical catalog ACK need not rewrite
        the header, but the selected row must already own the one native body.
        """
        if (not bool(getattr(self, "_hmb_node_deleted", False))
                and bool(getattr(self, "_hmb_shot_catalog_snapshot", {}).get("shots"))):
            self._hmb_layout_shot_editor()

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
        if self._hmb_shot_manager_enabled():
            return _agent_widget_shot_catalog(snapshot)
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
        # One real Prompt manager owns a document for each declared Shot, even
        # while its single visible editor is displaying a different UUID. The
        # resolver retains registered same-flow identity and ambiguity checks;
        # ordinary individual Prompt/Agent ownership remains unchanged.
        try:
            from _hmb_shot_routing import resolve_shot_prompt_owner
            for item in snapshot["shots"]:
                shot_uuid = str(item.get("shot_uuid") or "")
                owner = resolve_shot_prompt_owner(self, channel_uuid=channel_uuid, shot_uuid=shot_uuid)
                if _is_prompt_shot_manager(owner):
                    prompt_owned.add(shot_uuid)
        except Exception:
            pass
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
            next_ui = self._hmb_widget_value({}, catalog)
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
        if self._hmb_shot_manager_enabled() and selected is None and shots:
            selected = shots[0]
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
            next_ui = self._hmb_widget_value(
                shot,
                self._hmb_available_agent_shot_catalog(
                    self._hmb_shot_catalog_snapshot
                ),
            )
            if current_ui != next_ui:
                self._hmb_shot_catalog_syncing = True
                try:
                    # Separate the five-row catalog from the native editor's
                    # active identity. A sibling rename/renumber or watermark
                    # ACK must not republish the whole header/native form.
                    # Keep the saved backend catalog current; the layout below
                    # emits only the row parameters whose values changed.
                    header_changed = not isinstance(current_ui, dict) or any(
                        current_ui.get(key) != next_ui.get(key)
                        for key in ("shot", "execution_phase", "shot_editor_expanded", "shot_manager")
                    )
                    self.set_parameter_value(_AGENT_WIDGET_PARAMETER, next_ui, emit_change=header_changed)
                    parameter.default_value = next_ui
                finally:
                    self._hmb_shot_catalog_syncing = False
            else:
                # The SDK may restore the header before a live catalog exists.
                # Its first identical canonical ACK still completes layout;
                # later ACKs retain every native element in the same place.
                self._hmb_layout_shot_editor()
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

    def _hmb_prompt_manager_document(self, source, *, subscription=None):
        if not _is_prompt_shot_manager(source):
            raise RuntimeError("HMB Prompt manager is unavailable.")
        selected = self._normalize_execution_shot_binding(subscription or self._hmb_shot_channel_subscription())
        if not selected:
            raise RuntimeError("HMB Agent Shot identity is unavailable.")
        previous_source = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
        try:
            if not _is_direct_hmb_prompt_library_connection(self) or getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None) is not source:
                raise RuntimeError("HMB Prompt manager connection is invalid.")
            from _hmb_shot_routing import resolve_shot_prompt_owner
            if resolve_shot_prompt_owner(self, channel_uuid=selected["channel_uuid"], shot_uuid=selected["shot_uuid"]) is not source:
                raise RuntimeError("HMB Prompt manager Shot owner is invalid.")
            document = source._hmb_prompt_shot_document(channel_uuid=selected["channel_uuid"], shot_uuid=selected["shot_uuid"])
            view = _FrozenHMBPromptShotSource(source, document, selected)
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, view)
            _paired_machine_prompt(self, view.visible_prompt)
            view._hmb_project_identity()
            return view
        finally:
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, previous_source)


    def _hmb_revalidate_prompt_manager_owner(self):
        view = getattr(self, _FROZEN_PROMPT_SHOT_ATTRIBUTE, None)
        if view is None:
            return
        owner = getattr(self, _REGISTERED_PROMPT_OWNER_ATTRIBUTE, None)
        try:
            if owner is None or bool(getattr(owner, "_hmb_node_deleted", False)):
                raise RuntimeError("HMB Prompt manager was removed.")
            if not _is_direct_hmb_prompt_library_connection(self) or getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None) is not owner:
                raise RuntimeError("HMB Prompt manager connection changed.")
            from _hmb_shot_routing import resolve_shot_prompt_owner
            shot = view._hmb_shot_channel_subscription()
            if resolve_shot_prompt_owner(self, channel_uuid=shot["channel_uuid"], shot_uuid=shot["shot_uuid"]) is not owner:
                raise RuntimeError("HMB Prompt manager Shot owner changed.")
        finally:
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, view)


    def _assert_exact_prompt_shot_route(self) -> dict[str, Any]:
        """Return the Agent identity only after its exact Prompt route is verified."""

        subscription = self._hmb_shot_channel_subscription()
        source_node = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
        if _is_prompt_shot_manager(source_node):
            verified = self._normalize_execution_shot_binding(subscription)
            if not verified:
                raise RuntimeError("HMB Agent Shot identity is invalid.")
            for participant in (self, source_node):
                status = getattr(participant, "_hmb_shot_route_status", None)
                if not isinstance(status, dict) or status.get("ok") is not True or status.get("code") != "ready":
                    raise RuntimeError("HMB Prompt manager Shot routing is not ready.")
            view = self._hmb_prompt_manager_document(source_node, subscription=verified)
            setattr(self, _REGISTERED_PROMPT_OWNER_ATTRIBUTE, source_node)
            setattr(self, _FROZEN_PROMPT_SHOT_ATTRIBUTE, view)
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, view)
            return verified
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
        if self._hmb_shot_manager_enabled():
            value = ""
            projection_ready = False
            if enabled:
                try:
                    selected = self._hmb_shot_channel_subscription()
                    owner = self._hmb_manager_prompt_owner(channel_uuid=selected["channel_uuid"], shot_uuid=selected["shot_uuid"])
                    document = owner._hmb_prompt_shot_document(channel_uuid=selected["channel_uuid"], shot_uuid=selected["shot_uuid"])
                    value = str(document.get("visible_prompt") or "")
                    projection_ready = bool(value)
                except Exception:
                    value = ""
            if not projection_ready and bool(getattr(self, "_hmb_prompt_preview_hydration_pending", False)):
                return
            if projection_ready:
                self._hmb_prompt_preview_hydration_pending = False
            if (value and bool(getattr(self, "_hmb_prompt_preview_active", False))
                    and value == str(getattr(self, "_hmb_prompt_preview_value", "") or "")
                    and not self._matches_active_private_runtime_prompt(
                        self._native_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, ""))):
                # Repeated source/catalog ACKs must not overwrite an in-progress
                # native text edit. Real selected-document text changes still
                # pass through the normal reversible preview projection.
                return
            self._set_native_prompt_preview(value, enabled=enabled)
            if not value and self._native_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, ""):
                self._hmb_prompt_preview_syncing = True
                try:
                    self.set_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, "")
                finally:
                    self._hmb_prompt_preview_syncing = False
            return
        value = self._native_parameter_value(
            _AGENT_SHOT_PROMPT_INPUT_PARAMETER, ""
        )
        view = getattr(self, _FROZEN_PROMPT_SHOT_ATTRIBUTE, None)
        if view is not None:
            value = view.visible_prompt
        elif enabled:
            try:
                from _hmb_shot_routing import resolve_shot_prompt_owner
                selected = self._hmb_shot_channel_subscription()
                owner = resolve_shot_prompt_owner(self, channel_uuid=selected["channel_uuid"], shot_uuid=selected["shot_uuid"])
                if _is_prompt_shot_manager(owner):
                    value = self._hmb_prompt_manager_document(owner).visible_prompt
            except Exception:
                if getattr(self, "_hmb_prompt_manager_source_hint", None) is not None:
                    value = ""
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
        if _is_prompt_shot_manager(source_node):
            try:
                value = self._hmb_prompt_manager_document(source_node).visible_prompt
                self._hmb_prompt_manager_source_hint = source_node
            except Exception:
                return False
        outputs = getattr(source_node, "parameter_output_values", {})
        if value is sentinel and isinstance(outputs, dict) and source_name in outputs:
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
            available_catalog = _agent_widget_shot_catalog(authoritative_catalog)
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
            requested_manager = True
            if requested_manager:
                available_catalog = _agent_widget_shot_catalog(authoritative_catalog)
                if not str((requested_shot or {}).get("shot_uuid") or "") and available_catalog.get("shots"):
                    first = available_catalog["shots"][0]
                    requested_shot = {"channel_uuid": available_catalog["channel_uuid"],
                                      "shot_uuid": first["shot_uuid"], "number": first["number"], "name": first["name"]}
            normalized = self._hmb_widget_value(
                requested_shot, available_catalog,
                value.get("execution_phase", "") if isinstance(value, dict) else "",
                shot_manager=requested_manager,
            )
        if parameter_name == _AGENT_WIDGET_PARAMETER and isinstance(value, dict):
            current_ui = self._native_parameter_value(_AGENT_WIDGET_PARAMETER, {})
            old_shot = current_ui.get("shot", {}) if isinstance(current_ui, dict) else {}
            new_shot = normalized.get("shot", {})
            # A catalog watermark covers every Shot. It does not establish a
            # change to this editor's Prompt document. The exact Prompt edge
            # separately notifies real content/media changes.
            self._hmb_ui_preview_required = any(
                old_shot.get(key) != new_shot.get(key)
                for key in ("channel_uuid", "shot_uuid")
            )
            normalized["shot_editor_expanded"] = value.get("shot_editor_expanded", getattr(self, "_hmb_shot_editor_expanded", True)) is not False
        if parameter_name == _AGENT_WIDGET_PARAMETER and isinstance(value, dict) and isinstance(value.get("action"), dict):
            self._hmb_pending_shot_action = copy.deepcopy(value["action"])
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
        if str(getattr(parameter, "name", "") or "").startswith(_AGENT_SHOT_ROW_PREFIX):
            self._hmb_handle_row_action(parameter, value)
            return result
        if str(getattr(parameter, "name", "") or "") == _AGENT_WIDGET_PARAMETER:
            self._hmb_shot_editor_expanded = value.get("shot_editor_expanded", True) is not False if isinstance(value, dict) else True
            authoritative_catalog = getattr(self, "_hmb_shot_catalog_snapshot", None)
            if not authoritative_catalog and isinstance(value, dict):
                authoritative_catalog = value.get("shot_catalog")
            available_catalog = _agent_widget_shot_catalog(authoritative_catalog)
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
            requested_manager = True
            if requested_manager:
                available_catalog = _agent_widget_shot_catalog(authoritative_catalog)
                if not str((requested_shot or {}).get("shot_uuid") or "") and available_catalog.get("shots"):
                    first = available_catalog["shots"][0]
                    requested_shot = {"channel_uuid": available_catalog["channel_uuid"],
                                      "shot_uuid": first["shot_uuid"], "number": first["number"], "name": first["name"]}
            normalized = self._hmb_widget_value(
                requested_shot, available_catalog,
                value.get("execution_phase", "") if isinstance(value, dict) else "",
                shot_manager=requested_manager,
            )
            self._hmb_shot_manager_mode = bool(normalized.get("shot_manager"))
            selected_slot = normalized.get("shot", {})
            if getattr(self, "_hmb_restore_widget_write", False):
                self._hmb_active_slot_key = self._hmb_slot_key(selected_slot.get("channel_uuid", ""), selected_slot.get("shot_uuid", ""))
            elif not getattr(self, "_hmb_slot_switching", False):
                self._hmb_switch_native_slot(selected_slot.get("channel_uuid", ""), selected_slot.get("shot_uuid", ""))
            try:
                if getattr(parameter, "default_value", None) != normalized:
                    parameter.default_value = normalized
                height = _AGENT_WIDGET_HEIGHT
                for option in ("height", "min_height", "max_height", "widget_height", "default_height", "preferred_height", "initial_height"):
                    updater = getattr(parameter, "update_ui_options_key", None)
                    if callable(updater) and (getattr(parameter, "ui_options", {}) or {}).get(option) != height:
                        updater(option, height)
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
                if not self._hmb_shot_manager_enabled():
                    self._refresh_agent_shot_route()
            if getattr(self, "_hmb_ui_preview_required", True):
                self._refresh_routed_prompt_preview()
            action = getattr(self, "_hmb_pending_shot_action", None)
            self._hmb_pending_shot_action = None
            if action is not None:
                self._hmb_handle_shot_action(action)
            self._hmb_layout_shot_editor()
            self._hmb_persist_shot_store()
        elif str(getattr(parameter, "name", "") or "") == _AGENT_SHOT_PROMPT_INPUT_PARAMETER:
            self._refresh_routed_prompt_preview()
        elif str(getattr(parameter, "name", "") or "") == _AGENT_SHOT_STORE_PARAMETER:
            self._hmb_restore_shot_store()
        elif not getattr(self, "_hmb_slot_switching", False) and not getattr(self, "_hmb_shot_store_syncing", False):
            name = str(getattr(parameter, "name", "") or "")
            if name in _AGENT_NATIVE_SETTING_KEYS or name in {"tools", "rulesets"} or name.startswith(("Behavior", "tools_", "rulesets_")):
                self._hmb_capture_active_slot()
        return result

    @staticmethod
    def _publication_parameter_name(value: Any) -> str:
        return str(getattr(value, "name", value) or "").strip().casefold()

    def set_parameter_value(self, name, value, *args, **kwargs):
        """Buffer protected output/log writes until final sanitization."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        normalized_name = self._publication_parameter_name(name)
        if kwargs.get("initial_setup"):
            self._hmb_capture_saved_parameter_value(name, value)
        if (normalized_name == _AGENT_SHOT_PROMPT_INPUT_PARAMETER.casefold()
                and self._hmb_shot_manager_enabled() and not kwargs.get("initial_setup")):
            # This shared dependency can publish another visible Prompt Shot.
            # Only the exact selected document may update the native editor;
            # the hidden shared string itself needs no whole-node UI event.
            if self._native_parameter_value(str(name), None) == value:
                if not getattr(self, "_hmb_prompt_preview_syncing", False):
                    self._refresh_routed_prompt_preview()
                return None
            kwargs["emit_change"] = False
        if (normalized_name == _AGENT_WIDGET_PARAMETER.casefold() or normalized_name.startswith(_AGENT_SHOT_ROW_PREFIX.casefold())) and not kwargs.get("initial_setup") and isinstance(value, dict) and "action" not in value:
            current = self._native_parameter_value(str(name), None)
            if current == value:
                return None
        if normalized_name == _AGENT_PROMPT_INPUT_PARAMETER.casefold():
            value = self._public_prompt_value_after_private_echo(value)
        if getattr(self, "_hmb_capture_publications", False) and normalized_name in {
            "output",
            "logs",
        }:
            self._hmb_publication_buffer[normalized_name] = str(value or "")
            return None
        self._hmb_restore_widget_write = bool(kwargs.get("initial_setup", False)) if normalized_name == _AGENT_WIDGET_PARAMETER.casefold() else getattr(self, "_hmb_restore_widget_write", False)
        try:
            result = super().set_parameter_value(name, value, *args, **kwargs)
        finally:
            if normalized_name == _AGENT_WIDGET_PARAMETER.casefold():
                self._hmb_restore_widget_write = False
        if (
            normalized_name == _AGENT_SHOT_STORE_PARAMETER.casefold()
            and bool(kwargs.get("initial_setup", False))
        ):
            # The SDK initial-setup setter deliberately skips after_value_set.
            # Restore the durable store now, before a later live source/native
            # callback can persist the constructor's empty/Only slot cache over
            # the saved multi-Shot document. This is a pure cache restore.
            self._hmb_restore_shot_store()
        if (bool(kwargs.get("initial_setup", False)) and normalized_name in {
                _AGENT_WIDGET_PARAMETER.casefold(), _AGENT_SHOT_STORE_PARAMETER.casefold()}):
            # SDK command replay restores these values after root element order
            # and skips after_value_set. Normalize only presentation here; a
            # later identical catalog ACK must not be the first body reattach.
            restored_ui = self._native_parameter_value(_AGENT_WIDGET_PARAMETER, {})
            if normalized_name == _AGENT_WIDGET_PARAMETER.casefold() and isinstance(restored_ui, dict):
                self._hmb_shot_editor_expanded = restored_ui.get("shot_editor_expanded", True) is not False
            self._hmb_layout_shot_editor(restored_catalog=(
                restored_ui.get("shot_catalog") if isinstance(restored_ui, dict) else None))
        if (
            normalized_name == _AGENT_SHOT_PROMPT_INPUT_PARAMETER.casefold()
            and not bool(getattr(self, "_hmb_prompt_preview_syncing", False))
            and (bool(kwargs.get("initial_setup", False)) or not self._hmb_shot_manager_enabled())
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
            # SDK removal callbacks are reentrant: the old source's outgoing
            # callback can already have connected a replacement Prompt before
            # this old incoming-removal callback runs. Read the canonical live
            # edge rather than letting the old callback erase its replacement.
            try:
                replacement = (getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
                    if _is_direct_hmb_prompt_library_connection(self) else None)
            except Exception:
                replacement = None
            if replacement is not None and not bool(getattr(replacement, "_hmb_node_deleted", False)):
                try:
                    self._hmb_hydrate_shot_prompt_from_source(replacement, _HMB_PROMPT_OUTPUT_PARAMETER)
                except Exception:
                    pass
                return result
            self._hmb_shot_context = {}
            setattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            self._hmb_prompt_preview_hydration_pending = False
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
            if hasattr(self, "_hmb_shot_request_records"):
                self._hmb_shot_request_records.clear()
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
        if normalized_name in {"tools", "rulesets"} and len(getattr(self, "_hmb_shot_slots", {})) > 1:
            parent_getter = lambda key: self._hmb_slot_native_list_value(key)
        if (normalized_name != "rulesets" or not self._hmb_rules_active
                or bool(getattr(self, "_hmb_policy_omitted", False))):
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
        view = getattr(self, _FROZEN_PROMPT_SHOT_ATTRIBUTE, None)
        if normalized_name == _AGENT_SHOT_PROMPT_INPUT_PARAMETER.casefold() and view is not None:
            return view.visible_prompt
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
        project_id = getattr(self, "_hmb_execution_project_id", "") or "superwings12"
        payload = _hmb._load_agent_rule_payload() if project_id == "superwings12" else _hmb._load_agent_rule_payload(project_id)
        policy = str(payload.get("policy") or "").strip()
        binding = str(payload.get("binding") or "").strip()
        if not policy or not binding:
            raise RuntimeError("HMBAgentLibrary internal Behavior 1 / Behavior 2 data is incomplete.")
        policy_rules = _split_behavior_rules(policy, 4)
        binding_rules = _split_behavior_rules(binding, 4)
        self._hmb_policy_identity = {
            "project_id": project_id,
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
        self._hmb_policy_omitted = False
        self._hmb_policy = ""
        self._hmb_binding = ""
        self._hmb_policy_rules = []
        self._hmb_binding_rules = []
        self._hmb_ruleset_names = ("", "")
        self._hmb_policy_identity = {}
        self._hmb_execution_project_id = ""
        self._hmb_runtime_prompt = ""
        self._hmb_native_prompt_read_active = False
        self._hmb_verified_prompt_source_node = None
        self._hmb_registered_prompt_source_node = None
        self._hmb_frozen_prompt_shot_source = None
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
        # These static banners describe only their exact failures. Native model
        # and source-contract failures already publish their own output/error;
        # showing the DAT banner for them falsely claims the policy is invalid.
        warning_name = {
            _HMB_TOPOLOGY_UNAVAILABLE_MESSAGE: _HMB_TOPOLOGY_WARNING_NAME,
            _HMB_POLICY_UNAVAILABLE_MESSAGE: _HMB_POLICY_WARNING_NAME,
        }.get(message)
        if warning_name is not None:
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
            next_ui = self._hmb_widget_value(
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

    def _handle_additional_context(self, prompt: str, additional_context: Any) -> str:
        """Keep verified HMB machine data literal; preserve ordinary Agent templates."""

        if (self._hmb_rules_active or isinstance(self, _HMBWebRerenderExecution)) and isinstance(additional_context, dict):
            # process() enables this flag only after validating the canonical
            # Prompt's paired snapshot. That machine envelope contains user data,
            # not a Jinja template: rendering it would consume literal {{...}}
            # or {%...%} text before the model ever receives the approved data.
            context_json = json.dumps(
                additional_context,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            return (
                prompt
                + "\n\nHMB ADDITIONAL CONTEXT DATA (JSON):\n"
                + context_json
                + "\nEND HMB ADDITIONAL CONTEXT DATA"
            )
        return super()._handle_additional_context(prompt, additional_context)

    def _process(self, agent: Any, prompt: Any, *native_args: Any) -> Any:
        """Use the Standard processor; constrain only canonical HMB output prose."""

        web_revision = isinstance(self, _HMBWebRerenderExecution)
        hmb_request = bool(self._hmb_rules_active) or web_revision
        native_processor = getattr(super(), "_process", None)
        if not callable(native_processor):
            # Import-only/test fallback. Official Griptape always supplies the
            # native processor; never emulate a second, HMB-specific model path.
            return agent
        if hmb_request:
            if not web_revision:
                self._hmb_revalidate_prompt_manager_owner()
            # Standard Agent has already merged any typed additional_context at
            # this point. Canonical HMB dictionaries are delimited literal data;
            # numeric/string context and non-HMB templates retain native behavior.
            lifecycle_generation = int(getattr(self, "_hmb_lifecycle_generation", 0) or 0)
            if (
                not self._hmb_lifecycle_is_live(lifecycle_generation)
                or bool(getattr(self, "is_cancellation_requested", False))
            ):
                return agent
            if not web_revision:
                prompt = _with_english_agent_output_contract(prompt)
            # Optional execution facts and reference pixels augment the same
            # native call. Their absence never invalidates the authenticated
            # source text, changes the user's model, or launches an analysis
            # Agent. Source getters revalidate the exact machine snapshot.
            source = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            machine = str(getattr(self, "_hmb_runtime_prompt", "") or "")
            observation_begin = getattr(self, "_begin_hmb_reference_observation", None)
            observation_run = observation_begin(machine) if callable(observation_begin) else ""
            observation_store = getattr(self, "_store_hmb_reference_observation", None)
            machine_hash = _prompt_text_sha256(machine)
            settings_getter = getattr(source, "_hmb_agent_generation_context", None)
            if callable(settings_getter):
                try:
                    settings = settings_getter(machine)
                    if isinstance(settings, dict) and settings:
                        heading = ("HMB RECORDED PARENT GENERATOR SETTINGS (READ-ONLY DATA):"
                                   if web_revision else "HMB CURRENT GENERATOR SETTINGS (READ-ONLY DATA):")
                        prompt += (
                            "\n\n" + heading + "\n"
                            + json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
                        )
                except Exception:
                    pass
            media_getter = getattr(source, "_hmb_agent_reference_media", None)
            if callable(media_getter):
                try:
                    from _hmb_agent_media import augment_prompt

                    media = media_getter(machine)
                    if (
                        isinstance(media, dict)
                        and media.get("machine_sha256") == _prompt_text_sha256(machine)
                    ):
                        prompt = augment_prompt(
                            prompt, media, agent,
                            is_live=lambda: self._hmb_lifecycle_is_live(lifecycle_generation)
                            and not bool(getattr(self, "is_cancellation_requested", False)),
                            report_sink=(lambda report: observation_store(report, observation_run,
                                lifecycle_generation, machine_hash)) if callable(observation_store) else None,
                        )
                except Exception:
                    pass
        if hmb_request:
            if (
                not self._hmb_lifecycle_is_live(lifecycle_generation)
                or bool(getattr(self, "is_cancellation_requested", False))
            ):
                marker = getattr(self, "_mark_hmb_reference_observation_submission", None)
                if callable(marker):
                    marker(observation_run, False)
                return agent
            marker = getattr(self, "_mark_hmb_reference_observation_submission", None)
            if callable(marker):
                marker(observation_run, True)
            self._hmb_native_inference_started = True
            self._hmb_run_policy_applied = bool(self._hmb_rules_active) and not bool(getattr(self, "_hmb_policy_omitted", False))
            return _run_native_with_literal_hmb_input(native_processor, agent, prompt, *native_args)
        self._hmb_native_inference_started = True
        return native_processor(agent, prompt, *native_args)

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
        if not self._hmb_rules_active and not isinstance(self, _HMBWebRerenderExecution):
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
                        self._hmb_native_run_completed = True
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
                    self._hmb_native_run_completed = True
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
        the available four project rules plus four shot rules. The Prompt owns all four
        valid source modes (Prompt only, +Asset, +Picker, +Asset+Picker), so the
        Agent does not infer its siblings from payload text. Once that canonical
        edge is present, missing project rules are reported and the verified
        source still runs. Present invalid policy and source verification
        failures are reported before native execution.
        """
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return None
        lifecycle_generation = int(
            getattr(self, "_hmb_lifecycle_generation", 0) or 0
        )
        self._hmb_native_calls_this_process = 0
        self._hmb_native_inference_started = False
        self._hmb_native_run_completed = False
        self._hmb_run_hmb_source = False
        self._hmb_run_policy_applied = False
        self._hmb_policy_omitted = False
        self._hmb_run_policy_omitted = False
        self._hmb_run_project_identity = {}
        self._hmb_last_sanitizer_status = "clean"
        self._hmb_reference_observation = {}
        self._hmb_reference_observation_run_id = ""
        self._hmb_suppress_visible_publication = False
        self._hmb_native_failure_stage = ""
        self._hmb_native_failure_code = ""
        self._clear_execution_shot_binding()
        setattr(self, _FROZEN_PROMPT_SHOT_ATTRIBUTE, None)
        setattr(self, _REGISTERED_PROMPT_OWNER_ATTRIBUTE, None)
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
            self._hmb_run_hmb_source = bool(is_hmb)
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
            selected_project = self._hmb_selected_project()
            self._hmb_execution_project_id = selected_project["project_id"]
            self._hmb_run_project_identity = {key: selected_project[key] for key in ("project_id", "project_name")}
            # Detect genuine absence before claiming any project's session.
            # A present invalid DAT or failed/closed authorization stays blocked,
            # including when an earlier valid policy was cached in this process.
            readiness = self._hmb_web_rerender_policy_status(self._hmb_execution_project_id)
            if readiness.get("reason") == "project_policy_pending":
                raise ProjectPolicyPendingError("Selected project policy has not been supplied.")
            if readiness.get("ready") is not True:
                raise RuntimeError("Selected project policy verification is unavailable.")
            if self._hmb_execution_project_id == "superwings12":
                _hmb._bootstrap_agent_policy_session()
            else:
                _hmb._bootstrap_agent_policy_session(self._hmb_execution_project_id)
        except ProjectPolicyPendingError:
            # A missing project DAT is informational. Continue with the same
            # verified source snapshot and host processing, without substituting
            # any other project's rules or consuming its authorization session.
            self._hmb_policy_omitted = True
            self._hmb_run_policy_omitted = True
            self._hmb_policy = self._hmb_binding = ""
            self._hmb_policy_rules = []
            self._hmb_binding_rules = []
            self._hmb_policy_identity = {}
            self._hmb_ruleset_names = ("", "")
            try:
                self.show_message_by_name(_AGENT_PROJECT_POLICY_ABSENT_WARNING)
            except Exception:
                pass
            print(f"[HMB_PRODUCTION][INFO] PROJECT_POLICY_ABSENT project_id={self._hmb_execution_project_id}")
        except Exception:
            self._publish_hmb_execution_block(_HMB_POLICY_UNAVAILABLE_MESSAGE)
            raise RuntimeError(_HMB_POLICY_UNAVAILABLE_MESSAGE) from None

        if not self._hmb_lifecycle_is_live(lifecycle_generation):
            self._set_agent_execution_phase("")
            self._clear_execution_shot_binding()
            return None
        self._set_agent_execution_phase("preparing")
        if not self._hmb_policy_omitted:
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
            if self._hmb_selected_project()["project_id"] != self._hmb_execution_project_id:
                raise RuntimeError("HMB selected project changed while preparing the Agent.")
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
            # selections before the model sees them. A private model-bound
            # instruction fixes the final generator document language to English;
            # it does not translate or mutate the paired source snapshot itself.
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
                # The authenticated policy, fixed English-output instruction,
                # and Agent model own final wording and meaning. The client does
                # not phrase-match, translate, or rewrite a valid result here.
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
            failure_message = _hmb_execution_failure_message(
                getattr(self, "_hmb_native_failure_code", "")
            )
            self._publish_hmb_execution_block(failure_message)
            raise RuntimeError(failure_message) from None
        return result


_WEB_RERENDER_OUTPUT_CONTRACT = "hmb-web-rerender-instruction-v1"
_WEB_RERENDER_OUTPUT_RULESET = "hmb-web-rerender-output-contract-v1"


class _HMBWebRerenderOutputContractError(RuntimeError):
    """A request-local output failed validation before the Generator can run."""
    _hmb_web_output_contract_failed = True
    _hmb_web_output_contract_code = "web_rerender_output_contract_invalid"


def _web_rerender_output_schema(prompt):
    """Use the installed Standard Agent's structured-output implementation."""
    return {
        "type": "object",
        "properties": {
            "contract": {"type": "string", "enum": [_WEB_RERENDER_OUTPUT_CONTRACT]},
            "source_sha256": {"type": "string", "enum": [_prompt_text_sha256(prompt)]},
            "instruction": {"type": "string", "minLength": 1, "maxLength": 50000,
                "description": "The complete revised final video Generator instruction, with no analysis or commentary."},
        },
        "required": ["contract", "source_sha256", "instruction"],
        "additionalProperties": False,
    }


def _web_rerender_output_rules(prompt):
    # This is a transport/output contract, not project policy. The recorded
    # parent already contains its approved policy; never reload or restate it.
    return {"name": _WEB_RERENDER_OUTPUT_RULESET, "rules": [
        "Revise the recorded final video Generator instruction using its appended Review. "
        "Return the complete revised Generator instruction ready for immediate video generation. "
        "Apply the review as an edit to that instruction; do not answer the reviewer, assess the "
        "feedback, explain your reasoning, or provide a recommendation or settings report. "
        "Preserve the parent instruction's established project treatment and every unaffected "
        "requirement. Use the connected reference media and the read-only recorded parent Generator settings; "
        "do not invent or change sources, settings, durations, or OFF/false/0 values. "
        "Preserve literal user text, names, Korean text, reference tokens and template-like text. "
        "If the review cannot justify a change, return the complete parent instruction unchanged. "
        "The required JSON envelope is an output protocol only. Return exactly contract, "
        "source_sha256, and instruction, with no surrounding prose or Markdown fence. "
        "Only instruction will be sent to the video Generator. Set contract to "
        + _WEB_RERENDER_OUTPUT_CONTRACT + " and copy the host-provided source_sha256 "
        + _prompt_text_sha256(prompt) + " exactly; do not calculate a hash yourself."
    ]}


def _web_rerender_instruction(value, prompt):
    """Fail closed on a prose answer or a malformed/mismatched envelope.

    No heading/language heuristic can establish that prose is a usable render
    instruction. Require the native structured contract instead, then publish
    only its instruction string without normalization or template expansion.
    """
    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise _HMBWebRerenderOutputContractError()
            result[key] = item
        return result

    # A non-BMP character can occupy twelve ASCII JSON characters as a
    # surrogate-pair escape, while still being one instruction character.
    if not isinstance(value, str) or not value.strip() or len(value) > 610000:
        raise _HMBWebRerenderOutputContractError()
    try:
        parsed = json.loads(value, object_pairs_hook=unique_object)
    except (ValueError, TypeError, RecursionError) as exc:
        raise _HMBWebRerenderOutputContractError() from exc
    if (not isinstance(parsed, dict)
            or set(parsed) != {"contract", "source_sha256", "instruction"}
            or parsed["contract"] != _WEB_RERENDER_OUTPUT_CONTRACT
            or parsed["source_sha256"] != _prompt_text_sha256(prompt)
            or not isinstance(parsed["instruction"], str)
            or not parsed["instruction"].strip()
            or len(parsed["instruction"]) > 50000):
        raise _HMBWebRerenderOutputContractError()
    return parsed["instruction"]


def _web_rerender_snapshots(media_snapshot, generation_settings, prompt):
    if (
        not isinstance(media_snapshot, dict)
        or media_snapshot.get("schema") != "hmb-agent-reference-media"
        or media_snapshot.get("version") != 1
        or not isinstance(generation_settings, dict)
    ):
        raise ValueError("Web rerender source snapshot is invalid.")
    media = copy.deepcopy(media_snapshot)
    for kind in ("image", "video"):
        records = media.get(kind + "s", [])
        if not isinstance(records, list) or len(records) > 64:
            raise ValueError("Web rerender source order is invalid.")
        for index, record in enumerate(records, 1):
            if (
                not isinstance(record, dict)
                or record.get("token") != f"@{kind}{index}"
                or not isinstance(record.get("source"), str)
                or not record["source"].strip()
            ):
                raise ValueError("Web rerender source identity is invalid.")
        media[kind + "s"] = records
    media["machine_sha256"] = _prompt_text_sha256(prompt)
    allowed = {
        "model", "model_id", "task", "input_mode", "quality", "omni_reference_task_type",
        "duration", "duration_seconds", "duration_mode", "execution_expires_after", "priority",
        "aspect_ratio", "ratio", "resolution", "output_format", "seed",
        "return_last_frame", "generate_audio", "camera_fixed", "watermark",
        "draft_action",
    }
    settings = {}
    boolean_fields = {"return_last_frame", "generate_audio", "camera_fixed", "watermark"}
    numeric_fields = {"duration", "duration_seconds", "execution_expires_after", "priority", "seed"}
    for key, value in generation_settings.items():
        if key not in allowed:
            continue
        if key in boolean_fields:
            valid = type(value) is bool
        elif key in numeric_fields:
            valid = type(value) in {int, float} and abs(value) <= 10**15 and math.isfinite(value)
        else:
            valid = isinstance(value, str) and 0 < len(value) <= 256
        if not valid:
            raise ValueError("Web rerender generation settings must contain bounded scalar values.")
        settings[key] = value
    # These snapshots cross no policy/auth boundary and contain data only. Do
    # not carry a client instance, credential or executable object to the LLM.
    json.dumps(media, ensure_ascii=False, allow_nan=False)
    json.dumps(settings, ensure_ascii=False, allow_nan=False)
    return media, settings


class _HMBWebRerenderSource:
    def __init__(self, prompt, media, settings):
        self.prompt = prompt
        self.media = media
        self.settings = settings

    def _hmb_agent_reference_media(self, expected_machine):
        if expected_machine != self.prompt:
            raise RuntimeError("Web rerender source snapshot changed.")
        return copy.deepcopy(self.media)

    def _hmb_agent_generation_context(self, expected_machine):
        if expected_machine != self.prompt:
            raise RuntimeError("Web rerender source snapshot changed.")
        return copy.deepcopy(self.settings)


class _HMBWebRerenderExecution(HMBAgentLibrary):
    """Unregistered execution facade; native setters never reach the editor."""

    @classmethod
    def _from_owner(cls, owner, prompt, media, settings, native_settings=None):
        node = object.__new__(cls)
        node.__dict__.update(owner.__dict__)
        for name in (
            "get_parameter_value", "get_parameter_list_value", "set_parameter_value",
            "append_value_to_parameter", "_set_visible_output", "show_message_by_name",
            "hide_message_by_name", "_hmb_lifecycle_is_live",
        ):
            node.__dict__.pop(name, None)
        node._hmb_web_owner = owner
        node._hmb_web_owner_generation = int(getattr(owner, "_hmb_lifecycle_generation", 0) or 0)
        node._hmb_web_cancelled = False
        node._hmb_web_cancel_source = None
        node.parameter_values = {}
        node.parameter_output_values = {}
        node.metadata = copy.deepcopy(getattr(owner, "metadata", {}))
        # Copy effective native settings, including connected values, without
        # ever reading Prompt/SHOT_PROMPT_IN or any previous Agent output.
        for key in (
            "model", "model_provider", "agent", "include_details", "output_schema",
            "additional_context", "agent_memory",
        ):
            node.parameter_values[key] = copy.deepcopy(native_settings.get(key) if isinstance(native_settings, dict) else owner.get_parameter_value(key))
        for key in ("tools", "rulesets"):
            node.parameter_values[key] = copy.deepcopy(native_settings.get(key) or [] if isinstance(native_settings, dict) else owner.get_parameter_list_value(key))
        # A stale owner execution may still expose its ephemeral HMB rule
        # scopes through the getter. Preserve caller rules, never carry these
        # runtime additions into revision of an already processed prompt.
        runtime_scopes = {name for name in getattr(owner, "_hmb_ruleset_names", ()) if name}
        if runtime_scopes:
            def caller_rules(values):
                return [value for value in values if (
                    value.get("name") if isinstance(value, dict) else getattr(value, "name", None)
                ) not in runtime_scopes]

            node.parameter_values["rulesets"] = caller_rules(node.parameter_values["rulesets"] or [])
            incoming_agent = node.parameter_values.get("agent")
            if isinstance(incoming_agent, dict) and isinstance(incoming_agent.get("rulesets"), list):
                incoming_agent["rulesets"] = caller_rules(incoming_agent["rulesets"])
        # The facade owns this output protocol. Preserve the retained node's
        # schema and rules while requiring a complete render instruction from
        # this background revision, rather than an unconstrained chat answer.
        node.parameter_values["output_schema"] = _web_rerender_output_schema(prompt)
        node.parameter_values["rulesets"] = list(node.parameter_values["rulesets"] or []) + [
            _web_rerender_output_rules(prompt)
        ]
        for key in ("_model_access", "_provider"):
            component = getattr(owner, key, None)
            if component is not None:
                component = copy.copy(component)
                if hasattr(component, "_node"):
                    component._node = node
                setattr(node, key, component)
        if getattr(node, "_provider", None) is not None and hasattr(node._provider, "_model_access"):
            node._provider._model_access = node._model_access
        node._clear_hmb_runtime_policy()
        node._hmb_runtime_prompt = prompt
        node._hmb_verified_prompt_source_node = _HMBWebRerenderSource(prompt, media, settings)
        node._hmb_native_calls_this_process = 0
        node._hmb_reference_observation = {}
        node._hmb_reference_observation_run_id = ""
        node._hmb_execution_shot_binding = {}
        node._hmb_shot_context = {}
        node._hmb_native_failure_stage = ""
        node._hmb_native_failure_code = ""
        node._last_raw_output = None
        node._hmb_suppress_visible_publication = True
        return node

    @property
    def is_cancellation_requested(self):
        source = getattr(self, "_hmb_web_cancel_source", None) or self._hmb_web_owner
        return self._hmb_web_cancelled or bool(getattr(source, "is_cancellation_requested", False))

    def _hmb_lifecycle_is_live(self, generation=None):
        return (
            not self._hmb_web_cancelled
            and self._hmb_web_owner._hmb_lifecycle_is_live(self._hmb_web_owner_generation)
            and (generation is None or generation == self._hmb_lifecycle_generation)
        )

    def get_parameter_value(self, name):
        if str(name).casefold() == "prompt":
            return self._hmb_runtime_prompt
        return self.parameter_values.get(name)

    def get_parameter_list_value(self, name):
        return list(self.parameter_values.get(name) or [])

    def _load_hmb_rules(self):
        raise RuntimeError("Web revision preserves parent policy; policy reload is unavailable.")

    def set_parameter_value(self, name, value, *args, **kwargs):
        key = self._publication_parameter_name(name)
        if self._hmb_capture_publications and key in {"output", "logs"}:
            self._hmb_publication_buffer[key] = str(value or "")
        else:
            self.parameter_values[str(name)] = value
            self.parameter_output_values[str(name)] = value

    def append_value_to_parameter(self, name, value=None, *args, **kwargs):
        key = self._publication_parameter_name(name)
        if self._hmb_capture_publications and key in {"output", "logs"}:
            self._hmb_publication_buffer[key] += str(value or "")
        else:
            self.set_parameter_value(name, str(self.parameter_output_values.get(str(name), "")) + str(value or ""))

    def _set_visible_output(self, value):
        self.parameter_output_values["output"] = value

    def show_message_by_name(self, *args, **kwargs):
        return None

    def hide_message_by_name(self, *args, **kwargs):
        return None


class _HMBAgentShotSource:
    """Frozen paired-data view whose registered owner was verified at creation."""

    def __init__(self, owner, document, subscription):
        if not isinstance(document, dict) or document.get("schema") != "hmb-prompt-shot-document" or document.get("version") != 1:
            raise RuntimeError("Prompt Shot document is invalid.")
        self.owner = owner
        self.document = copy.deepcopy(document)
        self.subscription = {**subscription, "participant_kind": "prompt"}
        supplied = self.document.get("subscription")
        for key in ("channel_uuid", "shot_uuid", "shot_number", "shot_name"):
            if not isinstance(supplied, dict) or supplied.get(key) != self.subscription.get(key):
                raise RuntimeError("Prompt Shot document identity does not match its registered owner.")
        self.visible = self.document.get("visible_prompt")
        self.machine = self.document.get("machine_prompt")
        self._hmb_shot_route_status = {"ok": True, "code": "ready"}
        self._hmb_agent_prompt_snapshot(self.visible)

    def _hmb_shot_channel_subscription(self):
        return copy.deepcopy(self.subscription)

    def _hmb_agent_prompt_snapshot(self, visible):
        if visible != self.visible:
            raise RuntimeError("Prompt Shot visible snapshot changed.")
        paired = copy.deepcopy(self.document.get("paired_snapshot"))
        if not isinstance(paired, dict) or paired.get("machine_prompt") != self.machine:
            raise RuntimeError("Prompt Shot paired snapshot is invalid.")
        return paired

    def _hmb_agent_reference_media(self, machine):
        if machine != self.machine:
            raise RuntimeError("Prompt Shot machine snapshot changed.")
        return copy.deepcopy(self.document.get("reference_media") or {})

    def _hmb_agent_generation_context(self, machine):
        if machine != self.machine:
            raise RuntimeError("Prompt Shot settings snapshot changed.")
        return copy.deepcopy(self.document.get("generation_context") or {})

    def _hmb_agent_shot_context(self, visible):
        if visible != self.visible:
            raise RuntimeError("Prompt Shot context snapshot changed.")
        return copy.deepcopy(self.document.get("shot_context") or self.document.get("context") or {})

    def _hmb_project_identity(self):
        return resolve_project(self.document.get("project_identity"), default_legacy=False)


class _HMBAgentShotExecution(HMBAgentLibrary):
    """Unregistered per-Shot native execution with the normal policy boundary.

    The constructor is used only after the retained Agent verified the exact
    registered same-flow Prompt owner.  This is separate from web revision,
    which intentionally preserves already-applied parent policy.
    """

    @classmethod
    def _from_owner(cls, owner, prompt_owner, document, subscription, slot, generator):
        node = object.__new__(cls)
        node.__dict__.update(owner.__dict__)
        for name in ("get_parameter_value", "get_parameter_list_value", "set_parameter_value",
                     "append_value_to_parameter", "_set_visible_output", "show_message_by_name",
                     "hide_message_by_name", "_hmb_lifecycle_is_live"):
            node.__dict__.pop(name, None)
        node._hmb_shot_owner = owner
        node._hmb_shot_prompt_owner = prompt_owner
        node._hmb_shot_owner_generation = int(owner._hmb_lifecycle_generation)
        node._hmb_shot_generator = generator
        node._hmb_shot_cancelled = False
        node._hmb_shot_manager_mode = False
        node._hmb_shot_source = _HMBAgentShotSource(prompt_owner, document, subscription)
        node._hmb_shot_subscription = copy.deepcopy(subscription)
        node._hmb_shot_route_status = {"ok": True, "code": "ready"}
        node.parameter_values = copy.deepcopy(slot.get("values") or {})
        node.parameter_output_values = {}
        node.parameter_values[_AGENT_SHOT_PROMPT_INPUT_PARAMETER] = document["visible_prompt"]
        node.parameter_values["prompt"] = document["visible_prompt"]
        node._hmb_execution_result = {}
        node._hmb_reference_observation = {}
        node._hmb_reference_observation_run_id = ""
        node._hmb_execution_shot_binding = {}
        node._hmb_shot_context = {}
        node._hmb_shot_policy_identity = {}
        node._hmb_native_failure_stage = ""
        node._hmb_native_failure_code = ""
        node._hmb_native_calls_this_process = 0
        node._last_raw_output = None
        node._hmb_execution_gate = threading.Lock()
        node.metadata = copy.deepcopy(getattr(owner, "metadata", {}))
        for key in ("_model_access", "_provider"):
            component = getattr(owner, key, None)
            if component is not None:
                component = copy.copy(component)
                if hasattr(component, "_node"):
                    component._node = node
                setattr(node, key, component)
        if getattr(node, "_provider", None) is not None and hasattr(node._provider, "_model_access"):
            node._provider._model_access = node._model_access
        node._clear_hmb_runtime_policy()
        return node

    @property
    def is_cancellation_requested(self):
        generator = self._hmb_shot_generator
        return (self._hmb_shot_cancelled or bool(getattr(self._hmb_shot_owner, "_hmb_node_deleted", False))
                or (generator is not None and (bool(getattr(generator, "_hmb_node_deleted", False))
                    or bool(getattr(generator, "is_cancellation_requested", False)))))

    def _hmb_lifecycle_is_live(self, generation=None):
        return (not self.is_cancellation_requested
                and self._hmb_shot_owner._hmb_lifecycle_is_live(self._hmb_shot_owner_generation)
                and not bool(getattr(self._hmb_shot_prompt_owner, "_hmb_node_deleted", False))
                and (generation is None or generation == self._hmb_lifecycle_generation))

    def _refresh_agent_shot_route(self, *, strict=False):
        return {"ok": True, "code": "ready"}

    def _has_canonical_hmb_prompt_connection(self):
        self._hmb_verified_prompt_source_node = self._hmb_shot_source
        return True

    def _hmb_shot_channel_subscription(self):
        return copy.deepcopy(self._hmb_shot_subscription)

    def _assert_exact_prompt_shot_route(self):
        _paired_machine_prompt(self, self.parameter_values[_AGENT_SHOT_PROMPT_INPUT_PARAMETER])
        return copy.deepcopy(self._hmb_shot_subscription)

    def _native_parameter_value(self, name, default=""):
        return self.parameter_values.get(name, default)

    def get_parameter_value(self, name):
        if str(name).casefold() == "prompt" and self._hmb_rules_active and self._hmb_native_prompt_read_active:
            return self._hmb_runtime_prompt
        return self.parameter_values.get(name)

    def get_parameter_list_value(self, name):
        values = copy.deepcopy(self.parameter_values.get(name) or [])
        if str(name).casefold() == "rulesets" and self._hmb_rules_active and not self._hmb_policy_omitted:
            project, shot = self._hmb_ruleset_names
            if not project or not shot or project == shot:
                raise RuntimeError("HMBAgentLibrary sealed rule scope is unavailable.")
            values.extend([{"name": project, "rules": list(self._hmb_policy_rules)},
                           {"name": shot, "rules": list(self._hmb_binding_rules)}])
        return values

    def _load_hmb_rules(self):
        value = super()._load_hmb_rules()
        self._hmb_shot_policy_identity = copy.deepcopy(self._hmb_policy_identity)
        return value

    def set_parameter_value(self, name, value, *args, **kwargs):
        key = self._publication_parameter_name(name)
        if self._hmb_capture_publications and key in {"output", "logs"}:
            self._hmb_publication_buffer[key] = str(value or "")
        else:
            self.parameter_values[str(name)] = value
            self.parameter_output_values[str(name)] = value

    def append_value_to_parameter(self, name, value=None, *args, **kwargs):
        key = self._publication_parameter_name(name)
        if self._hmb_capture_publications and key in {"output", "logs"}:
            self._hmb_publication_buffer[key] += str(value or "")
        else:
            self.set_parameter_value(name, str(self.parameter_output_values.get(str(name), "")) + str(value or ""))

    def _set_visible_output(self, value):
        self.parameter_output_values["output"] = value
        self.parameter_values["output"] = value

    def _set_agent_execution_phase(self, phase):
        return None

    def publish_update_to_parameter(self, *args, **kwargs):
        return None

    def show_message_by_name(self, *args, **kwargs):
        return None

    def hide_message_by_name(self, *args, **kwargs):
        return None
