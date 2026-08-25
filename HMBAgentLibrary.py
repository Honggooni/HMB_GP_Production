from __future__ import annotations

import ast
import base64
import codecs
from pathlib import Path
import hashlib
import hmac
import importlib.util
import json
import math
import re
import secrets
import sys
import urllib.parse
import zlib
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

_HMB_TITLE = "HMB_GP_Production"
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
_AGENT_GENERATOR_SNAPSHOT_SCHEMA = "hmb-agent-generator-shot-snapshot"
_AGENT_GENERATOR_SNAPSHOT_VERSION = 1
_AGENT_REMOTE_PROMPT_PUBLICATION_SCHEMA = "hmb-agent-remote-prompt-publication"
_AGENT_REMOTE_PROMPT_PUBLICATION_VERSION = 1
_AGENT_STATE_WARNING_NAME = "HMB_AGENT_STATE_DISPLAY_WARNING"
_HMB_POLICY_WARNING_NAME = "HMB_AGENT_POLICY_REQUIRED_WARNING"
_HMB_TOPOLOGY_WARNING_NAME = "HMB_AGENT_CONNECTION_CHECK_WARNING"
_FINAL_TEXT_DISPLAY_NAME = "FINAL TEXT · GENERATOR"
_AGENT_STATE_DISPLAY_NAME = "AGENT STATE · CHAIN ONLY"
_HMB_POLICY_UNAVAILABLE_MESSAGE = (
    "[HMB SERVER POLICY REQUIRED] Agent policy session is unavailable. "
    "Close Griptape completely, verify the existing FN AI Broker login and "
    "server connection, then restart the official Griptape Desktop application."
)
_HMB_POLICY_IDENTITY_MISMATCH_MESSAGE = (
    "[HMB POLICY CONTRACT MISMATCH] HMBPromptLibrary와 서버의 서명된 "
    "Agent 정책이 서로 호환되는 입력 계약을 사용하지 않습니다. "
    "HMB_GP_Production을 동일한 배포 버전으로 다시 설치하거나 업데이트한 뒤 "
    "Griptape를 다시 시작하고 재시도하십시오."
)
_HMB_SOURCE_CONTRACT_INVALID_MESSAGE = (
    "[HMB SOURCE CONTRACT INVALID] 구조화된 HMB 소스 데이터의 형식 또는 주소가 "
    "일치하지 않아 실행을 중단했습니다. Frame Range OFF/미설정, 선택 역할 미지정 "
    "및 emitter 미지정은 정상적인 선택 상태이며 이 오류의 원인이 아닙니다. "
    "HMBPromptLibrary와 HMBVideoPickerLibrary의 구조화 데이터 연결 상태를 확인하십시오."
)
_FX_TIMING_CONTRACT_HEADER = "FX/TIMING SOURCE DATA (JSON):"
_FX_TIMING_CONTRACT_SCHEMA = "hmb-fx-timing-source-facts"
_FX_TIMING_CONTRACT_VERSION = 3
_PUBLIC_JOB_CONTRACT_HEADER = "HMB JOB DATA (JSON):"
_PUBLIC_JOB_CONTRACT_SCHEMA = "hmb-public-job-data"
_PUBLIC_JOB_CONTRACT_VERSION = 2
_USER_DESCRIPTION_DATA_HEADER = "USER DESCRIPTION DATA (JSON):"
_RUNTIME_FX_SCOPE_HEADER = "HMB VERIFIED FX/TIMING RUNTIME SCOPE (JSON):"
_ENGLISH_GENERATOR_OUTPUT_CONTRACT_HEADER = (
    "HMB GENERATOR OUTPUT CONTRACT (ENGLISH ONLY):"
)
_ENGLISH_GENERATOR_OUTPUT_CONTRACT = (
    "Write the final video-generator instruction entirely in English. "
    "Translate every user-authored descriptive sentence into clear natural "
    "production English. Do not emit Korean prose, explanations, headings, "
    "or commands. Keep machine addresses such as @image1 and @video1 exact, "
    "but describe their visual and motion instructions in English. Return "
    "only the generator-ready instruction, without commentary about this "
    "language requirement."
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
_TIMING_CUE_PHASES = frozenset({"point", "onset", "peak", "falloff", "end"})
_LOCAL_POINT_UNITS = frozenset({
    "scene_unit", "millimeter", "centimeter", "meter", "inch", "foot"
})
_MAX_PUBLIC_JOB_CONTRACT_CHARS = 2_000_000
# Prompt can emit every Image/Color-Pick/Range binding into one FX source.
# A public identifier is at most 256 UI characters and quote/backslash escaping
# can double its JSON representation.  Four such repeated segment fields plus
# a bounded 256-character structural allowance cover the serialized record.
_MAX_PUBLIC_IDENTIFIER_CHARS = 256
_MAX_FX_RANGE_SEGMENTS_PER_SOURCE = 50 * 3 * 100
_MAX_FX_RANGE_SEGMENT_JSON_CHARS = (
    (4 * _MAX_PUBLIC_IDENTIFIER_CHARS * 2) + 256
)
_MAX_FX_TIMING_FIXED_JSON_CHARS = 1_000_000
_MAX_FX_TIMING_CONTRACT_CHARS = (
    _MAX_FX_RANGE_SEGMENTS_PER_SOURCE
    * _MAX_FX_RANGE_SEGMENT_JSON_CHARS
    + _MAX_FX_TIMING_FIXED_JSON_CHARS
)
# The remaining two JSON records are independently bounded.  User text has
# four 6,000-character fields plus one 20,000-character field; JSON escaping
# can double that data, and 4 KiB covers the fixed seven-record envelope.
_MAX_USER_DESCRIPTION_FIELD_CHARS = 6_000
_MAX_USER_VIDEO_VFX_CHARS = 20_000
_MAX_USER_DESCRIPTION_JSON_CHARS = (
    (4 * _MAX_USER_DESCRIPTION_FIELD_CHARS) + _MAX_USER_VIDEO_VFX_CHARS
) * 2
_MAX_HMB_PROMPT_ENVELOPE_CHARS = 4_096
_MAX_HMB_PROMPT_CHARS = (
    _MAX_PUBLIC_JOB_CONTRACT_CHARS
    + _MAX_FX_TIMING_CONTRACT_CHARS
    + _MAX_USER_DESCRIPTION_JSON_CHARS
    + _MAX_HMB_PROMPT_ENVELOPE_CHARS
)
_PUBLIC_IMAGE_SOURCE_TYPES = frozenset(
    str(value) for value in getattr(_hmb, "IMAGE_SOURCE_TYPE_CHOICES", ())
)
_PUBLIC_VIDEO_SOURCE_TYPES = frozenset({
    "Role Required / Select Video Type",
    "Ignore / Unused",
    "Maya Preview / Playblast",
    "Unified Shot-Control Video",
    "Motion Reference",
    "Camera / Layout Reference",
    "Depth / Spatial Reference",
    "Motion Guide / Retargeting Reference",
    "FX Reference",
    "Timing / Edit Reference",
    "Lighting / Look Reference",
    "Simulation Reference",
    "Mask / Control Reference",
    "Custom",
})
_PUBLIC_VIDEO_ROLES = frozenset({
    "",
    "Primary Unified Shot Control",
    "Timing Only",
    "Local Motion Detail Only",
    "Secondary Motion Only",
    "Spatial Alignment Verification Only",
    "Derived Motion Decoding Only",
    "FX Behavior Only",
    "Lighting / Look Only",
    "Local Composition Check Only",
    "Mask / Guide Only",
    "Context Only",
    "Custom Role",
})
_FRAME_RANGE_ERROR_CODES = frozenset({
    "video_inactive",
    "marker_missing",
    "frame_domain_invalid",
    "marker_unavailable",
    "domain_start_missing",
    "domain_end_missing",
    "domain_order_invalid",
    "segment_missing",
    "segment_order_invalid",
    "segment_out_of_domain",
    "binding_address_missing",
    "binding_invalid",
})


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
_HMB_EXECUTION_FAILED_MESSAGE = (
    "[HMB EXECUTION FAILED] The protected execution ended without a publishable result."
)
_HMB_ENGLISH_OUTPUT_REQUIRED_MESSAGE = (
    "[HMB ENGLISH OUTPUT REQUIRED] The Agent returned non-English generator "
    "instructions, so publication was stopped before the video generator."
)
_HMB_REQUIRED_MARKERS = (
    _PUBLIC_JOB_CONTRACT_HEADER,
    _FX_TIMING_CONTRACT_HEADER,
    _USER_DESCRIPTION_DATA_HEADER,
)
_HMB_ANY_BINDING_MARKERS = (
    _PUBLIC_JOB_CONTRACT_HEADER,
    _FX_TIMING_CONTRACT_HEADER,
    _USER_DESCRIPTION_DATA_HEADER,
)
_HMB_READABLE_PROMPT_MARKERS = (
    "TARGET GENERATOR:",
    "IMAGE SOURCE:",
    "VIDEO SOURCE:",
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
_HMB_ISOLATED_SCALAR_INPUTS = frozenset(
    {
        "additional_context",
        "agent",
        "agent_memory",
        "memory",
        "conversation_memory",
        "messages",
        "instructions",
        "output_schema",
        "system",
        "system_prompt",
    }
)
_HMB_ISOLATED_LIST_INPUTS = frozenset({"tool", "tools"})
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
_SANITIZER_SIGNATURE_CACHE_MAX = 8
# Process-local keyed digests let repeated output checks reuse the sealed
# document signatures without retaining policy plaintext in a module cache.
_SANITIZER_SIGNATURE_KEY = secrets.token_bytes(32)
_SANITIZER_ROLLING_BASE = 257 + (2 * secrets.randbelow(32_768))
_SANITIZER_ROLLING_MASK = (1 << 64) - 1
_SANITIZER_SIGNATURE_CACHE: dict[
    bytes,
    tuple[tuple[int, dict[int, frozenset[bytes]]], ...],
] = {}


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
    machine_envelope = all(marker in text for marker in _HMB_REQUIRED_MARKERS)
    readable_document = all(
        marker in text for marker in _HMB_READABLE_PROMPT_MARKERS
    )
    return bool(
        (machine_envelope and any(marker in text for marker in _HMB_ANY_BINDING_MARKERS))
        or readable_document
    )


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
    """Require the stable Prompt/Agent contract, not one policy revision label."""

    prompt_identity = _prompt_policy_source_identity()
    if not hmac.compare_digest(
        prompt_identity[1],
        str(_hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
    ):
        raise _HMBPolicyIdentityMismatchError(
            _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
        )
    return prompt_identity


def _prompt_policy_candidate_identity(
    source_path: Path | None = None,
) -> tuple[str, str]:
    """Read the reviewed candidate identity without importing Prompt code."""

    path = Path(source_path) if source_path is not None else _THIS_DIR / "HMBPromptLibrary.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as exc:
        raise RuntimeError("HMB Prompt candidate identity could not be read.") from exc
    wanted = {
        "PROMPT_POLICY_CANDIDATE_VERSION": "",
        "PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256": "",
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
                raise RuntimeError("Duplicate HMB Prompt candidate identity.")
            seen.add(target.id)
            try:
                value = ast.literal_eval(value_node)
            except Exception as exc:
                raise RuntimeError("HMB Prompt candidate identity is invalid.") from exc
            if not isinstance(value, str):
                raise RuntimeError("HMB Prompt candidate identity is invalid.")
            wanted[target.id] = value.strip()
    version = wanted["PROMPT_POLICY_CANDIDATE_VERSION"]
    contract = wanted["PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256"].lower()
    if not version or not re.fullmatch(r"[0-9a-f]{64}", contract):
        raise RuntimeError("HMB Prompt candidate identity is incomplete.")
    return version, contract


def _assert_fx_candidate_matches_signed_runtime(contract: Dict[str, Any]) -> None:
    """Keep reviewed FX/Timing facts inactive until their policy is signed."""

    sources = contract.get("sources") if isinstance(contract, dict) else None
    if not isinstance(sources, list) or not sources:
        return
    candidate_identity = _prompt_policy_candidate_identity()
    if not hmac.compare_digest(
        candidate_identity[1],
        str(_hmb._AGENT_POLICY_CONTRACT_SHA256).lower(),
    ):
        raise _HMBPolicyIdentityMismatchError(
            _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
        )


def _prompt_data_only_envelope(prompt_value: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse the fixed public envelope; any extra generated prose is rejected."""

    value = getattr(prompt_value, "value", prompt_value)
    text = str(value or "")
    if not text or len(text) > _MAX_HMB_PROMPT_CHARS:
        raise RuntimeError("HMB public job envelope size is invalid.")
    # PROMPT_OUT is a fixed LF-delimited envelope. Normalize the one legacy
    # transport variant we already accept (CRLF), then split only on LF so
    # valid Unicode content such as NEL, LINE SEPARATOR, and PARAGRAPH
    # SEPARATOR remains inside its JSON string instead of becoming a record
    # boundary. A lone structural CR is left in place and therefore fails the
    # exact header/JSON checks below.
    normalized_text = text.replace("\r\n", "\n")
    lines = [line.strip() for line in normalized_text.split("\n") if line.strip()]
    expected_headers = (
        _HMB_TITLE,
        _PUBLIC_JOB_CONTRACT_HEADER,
        _FX_TIMING_CONTRACT_HEADER,
        _USER_DESCRIPTION_DATA_HEADER,
    )
    if (
        len(lines) != 7
        or lines[0] != expected_headers[0]
        or lines[1] != expected_headers[1]
        or lines[3] != expected_headers[2]
        or lines[5] != expected_headers[3]
    ):
        raise RuntimeError("HMB public job envelope layout is invalid.")
    if (
        len(lines[2]) > _MAX_PUBLIC_JOB_CONTRACT_CHARS
        or len(lines[4]) > _MAX_FX_TIMING_CONTRACT_CHARS
    ):
        raise RuntimeError("HMB public job contract is oversized.")
    try:
        job_data = json.loads(lines[2])
        fx_data = json.loads(lines[4])
        user_data = json.loads(lines[6])
    except Exception as exc:
        raise RuntimeError("HMB public job envelope JSON is invalid.") from exc
    if not isinstance(job_data, dict) or not isinstance(fx_data, dict):
        raise RuntimeError("HMB public job contract must be an object.")
    if not isinstance(user_data, dict):
        raise RuntimeError("HMB user description data must be an object.")
    return job_data, user_data


def _public_identity_object(value: Any, allowed_keys: set[str]) -> bool:
    if (
        not isinstance(value, dict)
        or len(value) > len(allowed_keys)
        or not set(value).issubset(allowed_keys)
    ):
        return False
    return all(
        isinstance(key, str)
        and bool(key)
        and isinstance(item, (str, int, float, bool))
        and (not isinstance(item, float) or math.isfinite(item))
        for key, item in value.items()
    )


def _valid_public_typed_object(
    value: Any,
    *,
    string_keys: set[str] | None = None,
    integer_keys: set[str] | None = None,
    boolean_keys: set[str] | None = None,
    number_keys: set[str] | None = None,
) -> bool:
    strings = set(string_keys or set())
    integers = set(integer_keys or set())
    booleans = set(boolean_keys or set())
    numbers = set(number_keys or set())
    allowed = strings | integers | booleans | numbers
    if not _public_identity_object(value, allowed):
        return False
    return all(
        (key not in strings or isinstance(item, str))
        and (
            key not in integers
            or (isinstance(item, int) and not isinstance(item, bool))
        )
        and (key not in booleans or isinstance(item, bool))
        and (
            key not in numbers
            or (
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(float(item))
            )
        )
        for key, item in value.items()
    )


def _valid_public_reference_capabilities(value: Any) -> bool:
    identity_fields = (
        value.get("marker_instance_identity_fields")
        if isinstance(value, dict)
        else None
    )
    return bool(
        isinstance(value, dict)
        and set(value) == {
            "schema", "version", "frame_addressable", "exact_emitter_cues",
            "image_source_frame_ranges", "marker_instance_identity_fields",
        }
        and value.get("schema") == "hmb-video-reference-capabilities"
        and value.get("version") == 1
        and all(
            isinstance(value.get(key), bool)
            for key in (
                "frame_addressable", "exact_emitter_cues",
                "image_source_frame_ranges",
            )
        )
        and isinstance(identity_fields, list)
        and len(identity_fields) <= 5
        and len(identity_fields) == len(set(identity_fields))
        and all(
            field in {
                "marker_color", "asset_id", "subject_root", "maya_uuid",
                "full_dag_path",
            }
            for field in identity_fields
        )
    )


def _valid_public_frame_domain(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema", "version", "timebase", "start_frame", "end_frame",
        "frame_count", "range_addressable",
    }:
        return False
    start = value.get("start_frame")
    end = value.get("end_frame")
    count = value.get("frame_count")
    return bool(
        value.get("schema") == "hmb-video-frame-domain"
        and value.get("version") == 1
        and isinstance(value.get("timebase"), str)
        and all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in (start, end, count)
        )
        and start <= end
        and count == end - start + 1
        and isinstance(value.get("range_addressable"), bool)
    )



def _assert_public_job_data_contract(prompt_value: Any) -> Dict[str, Any]:
    """Validate source job data without importing or reconstructing policy text."""

    job, user_data = _prompt_data_only_envelope(prompt_value)
    if (
        set(job) != {
            "schema", "version", "images", "videos", "control_only_bindings",
            "frame_ranges", "connections",
        }
        or job.get("schema") != _PUBLIC_JOB_CONTRACT_SCHEMA
        or job.get("version") != _PUBLIC_JOB_CONTRACT_VERSION
    ):
        raise RuntimeError("HMB public job contract envelope is invalid.")
    images = job.get("images")
    videos = job.get("videos")
    controls = job.get("control_only_bindings")
    frame_ranges = job.get("frame_ranges")
    connections = job.get("connections")
    if (
        not isinstance(images, list) or len(images) > 50
        or not isinstance(videos, list) or len(videos) > 10
        or not isinstance(controls, list) or len(controls) > 256
        or not isinstance(frame_ranges, list) or len(frame_ranges) > 5_000
        or not isinstance(connections, dict)
        or set(connections) != {"image_asset", "picker"}
        or any(not isinstance(value, bool) for value in connections.values())
    ):
        raise RuntimeError("HMB public job collection is invalid.")

    seen_images: set[str] = set()
    image_binding_video_tokens: List[str] = []
    for image in images:
        if not isinstance(image, dict) or set(image) != {
            "image", "label", "image_main_type", "image_sub_type",
            "source_type", "source_scope", "custom_source_type", "target_id",
            "relationship_targets", "bindings", "identity",
        }:
            raise RuntimeError("HMB image source record is invalid.")
        token = image.get("image")
        strings = (
            image.get("label"), image.get("image_main_type"),
            image.get("image_sub_type"), image.get("source_type"),
            image.get("source_scope"),
            image.get("custom_source_type"), image.get("target_id"),
        )
        image_main_type = str(image.get("image_main_type") or "").strip()
        image_sub_type = str(image.get("image_sub_type") or "").strip()
        source_type = str(image.get("source_type") or "").strip()
        source_scope = str(image.get("source_scope") or "").strip()
        taxonomy_wire_pair = _hmb.image_taxonomy_wire_pair(
            image_main_type, image_sub_type
        )
        unclassified_main_type = str(
            getattr(_hmb, "IMAGE_MAIN_TYPE_UNCLASSIFIED", "Select Image Main Type")
        )
        unclassified_source_type = str(
            getattr(
                _hmb,
                "IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED",
                "Role Required / Select Source Type",
            )
        )
        taxonomy_valid = (
            image_main_type == unclassified_main_type
            and not image_sub_type
            and source_type == unclassified_source_type
            and not source_scope
        ) or (
            taxonomy_wire_pair is not None
            and (source_type, source_scope) == tuple(taxonomy_wire_pair)
        )
        relationships = image.get("relationship_targets")
        bindings = image.get("bindings")
        taxonomy_authority_valid = True
        if image_main_type == "Look Reference":
            expected_target = (
                "Camera / Composition"
                if image_sub_type in {"Scale", "Composition", "Scale / Composition"}
                else "Global Look"
            )
            # Look inputs are scene/camera-level authority by taxonomy, never a
            # character/prop target and never a color-marker/video binding.
            taxonomy_authority_valid = (
                str(image.get("target_id") or "").strip() == expected_target
                and isinstance(relationships, list)
                and not relationships
                and isinstance(bindings, list)
                and not bindings
            )
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"@image(?:[1-9]|[1-4][0-9]|50)", token)
            or token in seen_images
            or any(not isinstance(value, str) for value in strings)
            or image.get("source_type") not in _PUBLIC_IMAGE_SOURCE_TYPES
            or not taxonomy_valid
            or not taxonomy_authority_valid
            or not isinstance(relationships, list)
            or any(not isinstance(value, str) or not value for value in relationships)
            or len(relationships) != len(set(relationships))
            or not isinstance(bindings, list) or len(bindings) > 3
            or not _valid_public_typed_object(
                image.get("identity"),
                string_keys={
                    "asset_id", "asset_library_id", "source_uid", "project_uid",
                    "source_kind",
                },
                integer_keys={"selection_order"},
                boolean_keys={"verified"},
            )
        ):
            raise RuntimeError("HMB image source fields are invalid.")
        seen_images.add(token)
        for binding in bindings:
            if (
                not isinstance(binding, dict)
                or set(binding) != {"video", "marker_color", "target_scope"}
                or not re.fullmatch(
                    r"@video(?:10|[1-9])", str(binding.get("video") or "")
                )
                or not isinstance(binding.get("marker_color"), str)
                or not isinstance(binding.get("target_scope"), str)
            ):
                raise RuntimeError("HMB image binding address is invalid.")
            image_binding_video_tokens.append(str(binding.get("video") or ""))

    seen_videos: set[str] = set()
    for video in videos:
        required = {
            "video", "label", "source_type", "custom_source_type", "control_role",
            "custom_control_role", "control_role_explicit", "keep_out", "identity",
        }
        allowed = required | {"reference_capabilities", "frame_domain", "companion"}
        if not isinstance(video, dict) or not required.issubset(video) or not set(video).issubset(allowed):
            raise RuntimeError("HMB video source record is invalid.")
        token = video.get("video")
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"@video(?:10|[1-9])", token)
            or token in seen_videos
            or any(
                not isinstance(video.get(key), str)
                for key in (
                    "label", "source_type", "custom_source_type", "control_role", "keep_out"
                    , "custom_control_role"
                )
            )
            or video.get("source_type") not in _PUBLIC_VIDEO_SOURCE_TYPES
            or video.get("control_role") not in _PUBLIC_VIDEO_ROLES
            or not isinstance(video.get("control_role_explicit"), bool)
            or not _valid_public_typed_object(
                video.get("identity"),
                string_keys={"video_uid", "source_uid", "order_key"},
                integer_keys={"selection_order"},
            )
            or (
                "reference_capabilities" in video
                and not _valid_public_reference_capabilities(
                    video.get("reference_capabilities")
                )
            )
            or (
                "frame_domain" in video
                and not _valid_public_frame_domain(video.get("frame_domain"))
            )
            or (
                "companion" in video
                and not _valid_public_typed_object(
                    video.get("companion"),
                    string_keys={"kind", "source_uid"},
                    integer_keys={"source_slot"},
                    boolean_keys={"validated"},
                )
            )
        ):
            raise RuntimeError("HMB video source fields are invalid.")
        seen_videos.add(token)

    if any(token not in seen_videos for token in image_binding_video_tokens):
        raise RuntimeError("HMB image binding addresses an inactive video source.")

    for control in controls:
        if (
            not isinstance(control, dict)
            or set(control) != {
                "source_field", "line", "video", "target_id", "function",
                "marker_color", "boundary",
            }
            or control.get("source_field") not in {"SCENE_CONTEXT", "VIDEO_VFX"}
            or not isinstance(control.get("line"), int)
            or isinstance(control.get("line"), bool)
            or control.get("line") < 1
            or not re.fullmatch(r"@video(?:10|[1-9])", str(control.get("video") or ""))
            or control.get("video") not in seen_videos
            or any(
                not isinstance(control.get(key), str)
                for key in ("target_id", "function", "marker_color", "boundary")
            )
        ):
            raise RuntimeError("HMB control-only record is invalid.")

    for item in frame_ranges:
        video_token = item.get("video") if isinstance(item, dict) else None
        error_codes = item.get("error_codes") if isinstance(item, dict) else None
        missing_video_is_unresolved = bool(
            isinstance(video_token, str)
            and re.fullmatch(r"@video(?:10|[1-9])", video_token)
            and video_token not in seen_videos
            and item.get("valid") is False
            and isinstance(error_codes, list)
            and "video_inactive" in error_codes
            and item.get("segments") == []
        )
        if (
            not isinstance(item, dict)
            or set(item) != {
                "image", "video", "marker_color", "enabled", "origin", "domain",
                "segments", "unresolved_segments", "valid", "error_codes",
            }
            or item.get("image") not in seen_images
            or (
                video_token not in seen_videos
                and not missing_video_is_unresolved
            )
            or not isinstance(item.get("marker_color"), str)
            or item.get("enabled") is not True
            or not isinstance(item.get("origin"), str)
            or item.get("origin") not in {
                "manual", "picker", "picker_auto", "picker-authored"
            }
            or not _valid_public_typed_object(
                item.get("domain"),
                string_keys={"timebase"},
                integer_keys={"start_frame", "end_frame", "frame_count"},
                number_keys={"fps"},
            )
            or not isinstance(item.get("valid"), bool)
            or not isinstance(item.get("error_codes"), list)
            or any(
                not isinstance(code, str) or code not in _FRAME_RANGE_ERROR_CODES
                for code in item.get("error_codes", [])
            )
            or (item.get("valid") is False and not item.get("error_codes"))
        ):
            raise RuntimeError("HMB frame-range record is invalid.")
        segments = item.get("segments")
        if not isinstance(segments, list) or len(segments) > 100:
            raise RuntimeError("HMB frame-range segment list is invalid.")
        for segment in segments:
            start = segment.get("start_frame") if isinstance(segment, dict) else None
            end = segment.get("end_frame") if isinstance(segment, dict) else None
            if (
                not isinstance(segment, dict)
                or set(segment) != {"start_frame", "end_frame"}
                or not isinstance(start, int) or isinstance(start, bool)
                or not isinstance(end, int) or isinstance(end, bool)
            ):
                raise RuntimeError("HMB frame-range segment is invalid.")
        unresolved_segments = item.get("unresolved_segments")
        if not isinstance(unresolved_segments, list) or len(unresolved_segments) > 100:
            raise RuntimeError("HMB unresolved frame-range list is invalid.")
        for segment in unresolved_segments:
            if (
                not isinstance(segment, dict)
                or set(segment) != {"start_frame", "end_frame", "error_code"}
                or not isinstance(segment.get("start_frame"), int)
                or isinstance(segment.get("start_frame"), bool)
                or not isinstance(segment.get("end_frame"), int)
                or isinstance(segment.get("end_frame"), bool)
                or segment.get("error_code") not in {
                    "segment_order_invalid", "segment_out_of_domain"
                }
                or segment.get("error_code") not in item.get("error_codes", [])
            ):
                raise RuntimeError("HMB unresolved frame-range segment is invalid.")
        unresolved_codes = {
            segment["error_code"] for segment in unresolved_segments
        }
        declared_segment_codes = set(item.get("error_codes", [])) & {
            "segment_order_invalid", "segment_out_of_domain"
        }
        if (
            unresolved_codes != declared_segment_codes
            or (
                item.get("valid") is True
                and not set(item.get("error_codes", [])).issubset(
                    {"segment_order_invalid", "segment_out_of_domain"}
                )
            )
        ):
            raise RuntimeError("HMB frame-range error index is invalid.")
        domain = item.get("domain")
        domain_start = domain.get("start_frame")
        domain_end = domain.get("end_frame")
        domain_count = domain.get("frame_count")
        if (
            isinstance(domain_start, int)
            and not isinstance(domain_start, bool)
            and isinstance(domain_end, int)
            and not isinstance(domain_end, bool)
            and domain_start > domain_end
            and (
                item.get("valid") is True
                or "domain_order_invalid" not in item.get("error_codes", [])
            )
        ):
            raise RuntimeError("HMB frame-range domain order is invalid.")
        if (
            domain_count is not None
            and (
                not isinstance(domain_count, int)
                or isinstance(domain_count, bool)
                or not isinstance(domain_start, int)
                or isinstance(domain_start, bool)
                or not isinstance(domain_end, int)
                or isinstance(domain_end, bool)
                or domain_count != domain_end - domain_start + 1
            )
            and (
                item.get("valid") is True
                or "frame_domain_invalid" not in item.get("error_codes", [])
            )
        ):
            raise RuntimeError("HMB frame-range domain count is invalid.")
        if item.get("valid") is True:
            if (
                not segments
                or not isinstance(domain_start, int)
                or isinstance(domain_start, bool)
                or not isinstance(domain_end, int)
                or isinstance(domain_end, bool)
                or any(
                    segment["start_frame"] > segment["end_frame"]
                    or segment["start_frame"] < domain_start
                    or segment["end_frame"] > domain_end
                    for segment in segments
                )
            ):
                raise RuntimeError("HMB valid frame-range bounds are invalid.")
        elif segments:
            raise RuntimeError("HMB invalid frame-range record has active segments.")

    allowed_user_fields = {
        "PROJECT_STYLE_LOOK", "SCENE_CONTEXT", "EMOTION_INTENT", "VIDEO_VFX",
        "PRESERVED_TEXT",
    }
    if not set(user_data).issubset(allowed_user_fields):
        raise RuntimeError("HMB user description field is invalid.")
    for key, value in user_data.items():
        max_chars = (
            _MAX_USER_VIDEO_VFX_CHARS
            if key == "VIDEO_VFX"
            else _MAX_USER_DESCRIPTION_FIELD_CHARS
        )
        if not isinstance(value, str) or len(value) > max_chars:
            raise RuntimeError("HMB user description value is invalid.")
    return job



def _prompt_fx_timing_contract(prompt_value: Any) -> Dict[str, Any]:
    """Extract the single data-only FX/Timing contract from compiled Prompt text."""

    value = getattr(prompt_value, "value", prompt_value)
    text = str(value or "")
    # Keep the same fixed record boundary as the outer envelope parser. Unicode
    # NEL/LINE/PARAGRAPH separators are valid JSON string content, not headers.
    lines = text.replace("\r\n", "\n").split("\n")
    header_indexes = [
        index for index, line in enumerate(lines) if line.strip() == _FX_TIMING_CONTRACT_HEADER
    ]
    if len(header_indexes) != 1:
        raise RuntimeError("FX/Timing contract header count is invalid.")
    index = header_indexes[0] + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        raise RuntimeError("FX/Timing contract payload is missing.")
    encoded = lines[index].strip()
    if len(encoded) > _MAX_FX_TIMING_CONTRACT_CHARS:
        raise RuntimeError("FX/Timing contract payload is oversized.")
    try:
        payload = json.loads(encoded)
    except Exception as exc:
        raise RuntimeError("FX/Timing contract payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("FX/Timing contract payload must be an object.")
    return payload


def _valid_exact_local_point(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    kind = str(value.get("kind") or "").strip().casefold()
    if kind == "locator":
        return bool(
            set(value) == {"kind", "locator_id", "locator_path"}
            and isinstance(value.get("locator_id"), str)
            and isinstance(value.get("locator_path"), str)
            and (
            str(value.get("locator_id") or "").strip()
            or str(value.get("locator_path") or "").strip()
            )
        )
    if kind != "coordinates":
        return False
    xyz = value.get("xyz")
    return bool(
        set(value) == {"kind", "space", "unit", "xyz"}
        and str(value.get("space") or "").strip().casefold() in {"local", "object"}
        and str(value.get("unit") or "").strip().casefold() in _LOCAL_POINT_UNITS
        and isinstance(xyz, list)
        and len(xyz) == 3
        and all(
            not isinstance(component, bool)
            and isinstance(component, (int, float))
            and math.isfinite(float(component))
            for component in xyz
        )
    )


def _valid_exact_emitter(value: Any) -> bool:
    allowed = {
        "marker_color", "asset_id", "subject_root", "maya_uuid", "full_dag_path"
    }
    return bool(
        isinstance(value, dict)
        and bool(value)
        and set(value).issubset(allowed)
        and all(isinstance(item, str) and bool(item.strip()) for item in value.values())
        and bool(str(value.get("marker_color") or "").strip())
        and any(
            str(value.get(key) or "").strip()
            for key in ("asset_id", "subject_root", "maya_uuid", "full_dag_path")
        )
    )


def _cue_inside_contract_segments(
    cue: Dict[str, Any], segments: list[Dict[str, Any]]
) -> bool:
    frame = cue.get("frame")
    if not isinstance(frame, int) or isinstance(frame, bool):
        return False
    emitter = cue.get("emitter") if isinstance(cue.get("emitter"), dict) else {}
    marker = str(emitter.get("marker_color") or "").strip().casefold()
    if not marker:
        return False
    emitter_targets = {
        str(emitter.get(key) or "").strip().casefold()
        for key in ("asset_id", "subject_root", "full_dag_path")
        if str(emitter.get(key) or "").strip()
    }
    emitter_targets.update(
        target.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        for target in tuple(emitter_targets)
    )
    for segment in segments:
        start = segment.get("start_frame")
        end = segment.get("end_frame")
        if not (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and start <= frame <= end
        ):
            continue
        segment_marker = str(segment.get("marker_color") or "").strip().casefold()
        if not segment_marker or marker != segment_marker:
            continue
        segment_target = str(segment.get("target_id") or "").strip().casefold()
        if segment_target and not (
            segment_target in emitter_targets
            or segment_target.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
            in emitter_targets
        ):
            continue
        return True
    return False





def _assert_fx_timing_source_contract(prompt_value: Any) -> Dict[str, Any]:
    """Validate only public FX/Timing facts and their source addresses.

    Main-Type authority, appearance exclusions, Playblast precedence, timing
    meaning, and shared-range application are deliberately absent here.  They
    are applied only after the signed runtime has been loaded.
    """

    job_data = _assert_public_job_data_contract(prompt_value)
    job_videos = {
        str(item.get("video") or "").strip(): item
        for item in job_data.get("videos", [])
        if isinstance(item, dict)
    }
    job_images = {
        str(item.get("image") or "").strip(): item
        for item in job_data.get("images", [])
        if isinstance(item, dict)
    }
    job_ranges = [
        item
        for item in job_data.get("frame_ranges", [])
        if isinstance(item, dict)
    ]
    expected_videos = {
        token
        for token, item in job_videos.items()
        if item.get("source_type") in {"FX Reference", "Timing / Edit Reference"}
    }
    contract = _prompt_fx_timing_contract(prompt_value)
    contract_valid = contract.get("valid")
    contract_errors = contract.get("errors")
    allowed_validation_codes = {"range", "emitter_cue", "transport"}
    error_records_valid = isinstance(contract_errors, list) and all(
        isinstance(error, dict)
        and set(error) == {"video", "code"}
        and bool(re.fullmatch(r"@video(?:10|[1-9])", str(error.get("video") or "")))
        and error.get("code") in allowed_validation_codes
        for error in (contract_errors if isinstance(contract_errors, list) else [])
    )
    if (
        set(contract) != {"schema", "version", "valid", "errors", "sources"}
        or contract.get("schema") != _FX_TIMING_CONTRACT_SCHEMA
        or contract.get("version") != _FX_TIMING_CONTRACT_VERSION
        or not isinstance(contract_valid, bool)
        or not error_records_valid
        or len(contract_errors) > 2_000
        or contract_valid is bool(contract_errors)
        or len({(error["video"], error["code"]) for error in contract_errors})
        != len(contract_errors)
    ):
        raise RuntimeError("FX/Timing fact envelope is invalid.")

    sources = contract.get("sources")
    if not isinstance(sources, list) or len(sources) > 10:
        raise RuntimeError("FX/Timing fact source list is invalid.")

    seen_videos: set[str] = set()
    for source in sources:
        required_source_keys = {
            "video",
            "source_type",
            "selected_role",
            "role_selected",
            "validation_codes",
            "range_on",
            "range_segments",
            "emitter_binding_declared",
            "timing_cues",
        }
        if (
            not isinstance(source, dict)
            or not required_source_keys.issubset(source)
            or not set(source).issubset(required_source_keys | {"video_uid"})
            or (
                "video_uid" in source
                and (
                    not isinstance(source.get("video_uid"), str)
                    or not source.get("video_uid").strip()
                )
            )
        ):
            raise RuntimeError("FX/Timing source fact must be an object.")

        video = str(source.get("video") or "").strip()
        if not re.fullmatch(r"@video(?:10|[1-9])", video) or video in seen_videos:
            raise RuntimeError("FX/Timing video address is invalid or duplicated.")
        seen_videos.add(video)
        source_type = source.get("source_type")
        selected_role = source.get("selected_role")
        role_selected = source.get("role_selected")
        job_video = job_videos.get(video)
        if (
            source_type not in {"FX Reference", "Timing / Edit Reference"}
            or not isinstance(selected_role, str)
            or selected_role not in _PUBLIC_VIDEO_ROLES
            or not isinstance(role_selected, bool)
            or role_selected is not bool(selected_role)
            or not isinstance(job_video, dict)
            or job_video.get("source_type") != source_type
            or job_video.get("control_role") != selected_role
            or job_video.get("control_role_explicit") is not role_selected
        ):
            raise RuntimeError("FX/Timing source facts do not match job data.")

        validation_codes = source.get("validation_codes")
        if (
            not isinstance(validation_codes, list)
            or any(code not in allowed_validation_codes for code in validation_codes)
            or len(validation_codes) != len(set(validation_codes))
            or (validation_codes and contract_valid)
        ):
            raise RuntimeError("FX/Timing validation facts are invalid.")

        range_on = source.get("range_on")
        segments = source.get("range_segments")
        addressed_job_ranges = [
            item for item in job_ranges if item.get("video") == video
        ]
        valid_job_ranges = [
            item for item in addressed_job_ranges if item.get("valid") is True
        ]
        capabilities = job_video.get("reference_capabilities")
        manual_range_projection = bool(
            addressed_job_ranges
            and valid_job_ranges
            and len(valid_job_ranges) == len(addressed_job_ranges)
            and all(
                item.get("origin") == "manual"
                for item in addressed_job_ranges
            )
        )
        capability_range_problem = bool(
            range_on
            and not manual_range_projection
            and isinstance(capabilities, dict)
            and (
                capabilities.get("frame_addressable") is not True
                or capabilities.get("image_source_frame_ranges") is not True
            )
        )
        raw_range_problem = bool(
            range_on
            and (
                not segments
                or any(
                    item.get("valid") is not True
                    or bool(item.get("error_codes"))
                    for item in addressed_job_ranges
                )
                or capability_range_problem
            )
        )
        if (
            not isinstance(range_on, bool)
            or range_on is not bool(addressed_job_ranges)
            or not isinstance(segments, list)
            or len(segments) > _MAX_FX_RANGE_SEGMENTS_PER_SOURCE
            or (not range_on and segments)
            or (range_on and not segments and "range" not in validation_codes)
            or (("range" in validation_codes) is not raw_range_problem)
        ):
            raise RuntimeError("FX/Timing range facts are invalid.")

        seen_segments: set[str] = set()
        for segment in segments:
            required_segment_keys = {
                "segment_id",
                "image",
                "video",
                "marker_color",
                "target_id",
                "target_scope",
                "start_frame",
                "end_frame",
            }
            if (
                not isinstance(segment, dict)
                or not required_segment_keys.issubset(segment)
                or not set(segment).issubset(
                    required_segment_keys | {"image_source_uid", "image_asset_id"}
                )
                or any(
                    key in segment
                    and (
                        not isinstance(segment.get(key), str)
                        or not segment.get(key).strip()
                    )
                    for key in ("image_source_uid", "image_asset_id")
                )
            ):
                raise RuntimeError("FX/Timing range segment must be an object.")
            segment_id = str(segment.get("segment_id") or "").strip()
            start = segment.get("start_frame")
            end = segment.get("end_frame")
            if (
                not segment_id
                or segment_id in seen_segments
                or segment.get("video") != video
                or not re.fullmatch(
                    r"@image(?:[1-9]|[1-4][0-9]|50)",
                    str(segment.get("image") or ""),
                )
                or not str(segment.get("marker_color") or "").strip()
                or not isinstance(segment.get("target_id"), str)
                or not isinstance(segment.get("target_scope"), str)
                or not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or start > end
            ):
                raise RuntimeError("FX/Timing range segment address is invalid.")
            job_image = job_images.get(str(segment.get("image") or ""))
            if (
                not isinstance(job_image, dict)
                or segment.get("target_id") != job_image.get("target_id")
                or not any(
                    binding.get("video") == video
                    and str(binding.get("marker_color") or "").casefold()
                    == str(segment.get("marker_color") or "").casefold()
                    and binding.get("target_scope") == segment.get("target_scope")
                    for binding in job_image.get("bindings", [])
                )
                or not any(
                    item.get("image") == segment.get("image")
                    and item.get("video") == video
                    and str(item.get("marker_color") or "").casefold()
                    == str(segment.get("marker_color") or "").casefold()
                    and any(
                        int(job_segment["start_frame"])
                        <= int(start)
                        <= int(end)
                        <= int(job_segment["end_frame"])
                        for job_segment in item.get("segments", [])
                    )
                    for item in valid_job_ranges
                )
            ):
                raise RuntimeError("FX/Timing segment does not match raw Range data.")
            seen_segments.add(segment_id)

        cues = source.get("timing_cues")
        emitter_binding_declared = source.get("emitter_binding_declared")
        if (
            not isinstance(cues, list)
            or len(cues) > 256
            or not isinstance(emitter_binding_declared, bool)
            or (cues and not emitter_binding_declared)
            or (
                emitter_binding_declared
                and not cues
                and "emitter_cue" not in validation_codes
            )
        ):
            raise RuntimeError("FX/Timing cue facts are invalid.")
        seen_cues: set[str] = set()
        for cue in cues:
            required_cue_keys = {
                "schema",
                "version",
                "cue_id",
                "cue_type",
                "cue_phase",
                "frame",
                "emitter",
                "local_point",
            }
            if (
                not isinstance(cue, dict)
                or not required_cue_keys.issubset(cue)
                or not set(cue).issubset(required_cue_keys | {"description"})
                or (
                    "description" in cue
                    and not isinstance(cue.get("description"), str)
                )
            ):
                raise RuntimeError("FX/Timing cue must be an object.")
            cue_id = str(cue.get("cue_id") or "").strip()
            frame = cue.get("frame")
            if (
                cue.get("schema") != "hmb-video-emitter-timing-cue"
                or cue.get("version") != 1
                or not cue_id
                or cue_id in seen_cues
                or cue.get("cue_type") != "emitter_point"
                or cue.get("cue_phase") not in _TIMING_CUE_PHASES
                or not isinstance(frame, int)
                or isinstance(frame, bool)
                or not _valid_exact_emitter(cue.get("emitter"))
                or not _valid_exact_local_point(cue.get("local_point"))
            ):
                raise RuntimeError("FX/Timing emitter cue is invalid.")
            frame_domain = job_video.get("frame_domain")
            if (
                isinstance(frame_domain, dict)
                and not (
                    int(frame_domain["start_frame"])
                    <= int(frame)
                    <= int(frame_domain["end_frame"])
                )
            ):
                raise RuntimeError("FX/Timing cue is outside its source frame domain.")
            seen_cues.add(cue_id)

    if seen_videos != expected_videos:
        raise RuntimeError("FX/Timing source coverage is invalid.")
    expected_error_records = {
        (str(source.get("video") or "").strip(), str(code or "").strip())
        for source in sources
        for code in source.get("validation_codes", [])
    }
    actual_error_records = {
        (str(error.get("video") or "").strip(), str(error.get("code") or "").strip())
        for error in contract_errors
    }
    if actual_error_records != expected_error_records:
        raise RuntimeError("FX/Timing validation index is invalid.")
    return contract



def _derive_fx_timing_runtime_scope(
    contract: Dict[str, Any],
    *,
    policy_rules: list[str],
    binding_rules: list[str],
) -> Dict[str, Any]:
    """Derive shared FX/Timing scope only inside a loaded signed runtime.

    The returned structure is transient Agent state.  It is never written back
    to HMBPromptLibrary.PROMPT_OUT and contains no policy or binding prose.
    """

    if len(policy_rules) != 4 or len(binding_rules) != 4:
        raise RuntimeError("Signed FX/Timing runtime is not loaded.")
    raw_sources = contract.get("sources")
    if not isinstance(raw_sources, list):
        raise RuntimeError("FX/Timing runtime facts are unavailable.")

    runtime_sources: list[Dict[str, Any]] = []
    for source in raw_sources:
        range_on = source.get("range_on") is True
        segments = [
            dict(segment)
            for segment in source.get("range_segments", [])
            if isinstance(segment, dict)
        ]
        validation_codes = list(source.get("validation_codes", []))
        runtime_sources.append({
            "video": source.get("video"),
            "source_type": source.get("source_type"),
            "range_mode": (
                "selected_segments"
                if range_on and segments
                else "unresolved"
                if range_on
                else "full_video"
            ),
            "allowed_segments": segments,
            "timing_cues": [
                dict(cue)
                for cue in source.get("timing_cues", [])
                if isinstance(cue, dict)
            ],
            "validation_codes": validation_codes,
        })

    fx_sources = [
        source
        for source in runtime_sources
        if source.get("source_type") == "FX Reference"
        and source.get("range_mode") == "selected_segments"
    ]
    timing_sources = [
        source
        for source in runtime_sources
        if source.get("source_type") == "Timing / Edit Reference"
        and source.get("range_mode") == "selected_segments"
    ]
    RuntimeRangeKey = tuple[str, str, str, str, str]

    def range_key(
        source: Dict[str, Any], segment: Dict[str, Any], source_kind: str
    ) -> RuntimeRangeKey:
        return (
            str(source.get("video") or ""),
            str(segment.get("target_id") or "").strip().casefold(),
            str(segment.get("marker_color") or "").strip().casefold(),
            str(segment.get("target_scope") or "").strip().casefold(),
            source_kind,
        )

    allowed: Dict[RuntimeRangeKey, list[tuple[int, int]]] = {}
    conflicts: set[RuntimeRangeKey] = set()
    shared_windows: list[Dict[str, Any]] = []

    for fx_source in fx_sources:
        for timing_source in timing_sources:
            fx_segments = fx_source.get("allowed_segments", [])
            timing_segments = timing_source.get("allowed_segments", [])
            for fx_segment in fx_segments:
                target_key = str(
                    fx_segment.get("target_id") or ""
                ).strip().casefold()
                if not target_key:
                    continue
                for timing_segment in timing_segments:
                    if (
                        str(timing_segment.get("target_id") or "")
                        .strip()
                        .casefold()
                        != target_key
                    ):
                        continue
                    fx_scope = str(fx_segment.get("target_scope") or "").strip()
                    timing_scope = str(
                        timing_segment.get("target_scope") or ""
                    ).strip()
                    if (
                        fx_scope
                        and timing_scope
                        and fx_scope.casefold() != timing_scope.casefold()
                    ):
                        continue
                    fx_key = range_key(fx_source, fx_segment, "fx")
                    timing_key = range_key(
                        timing_source, timing_segment, "timing"
                    )
                    start = max(
                        int(fx_segment.get("start_frame")),
                        int(timing_segment.get("start_frame")),
                    )
                    end = min(
                        int(fx_segment.get("end_frame")),
                        int(timing_segment.get("end_frame")),
                    )
                    if start > end:
                        conflicts.update({fx_key, timing_key})
                        continue
                    shared_windows.append({
                        "window_id": f"runtime-shared-{len(shared_windows) + 1}",
                        "target_id": fx_segment.get("target_id"),
                        "target_scope": fx_scope or timing_scope,
                        "fx_video": fx_source.get("video"),
                        "fx_marker_color": fx_segment.get("marker_color"),
                        "timing_video": timing_source.get("video"),
                        "timing_marker_color": timing_segment.get("marker_color"),
                        "start_frame": start,
                        "end_frame": end,
                    })
                    allowed.setdefault(fx_key, []).append((start, end))
                    allowed.setdefault(timing_key, []).append((start, end))

    conflicts.difference_update(allowed.keys())
    for source in runtime_sources:
        if source.get("range_mode") != "selected_segments":
            continue
        source_kind = (
            "fx" if source.get("source_type") == "FX Reference" else "timing"
        )
        adjusted: list[Dict[str, Any]] = []
        for segment in source.get("allowed_segments", []):
            key = range_key(source, segment, source_kind)
            if key in conflicts:
                continue
            intervals = sorted(set(allowed.get(key, [])))
            if not intervals:
                adjusted.append(segment)
                continue
            for interval_index, (window_start, window_end) in enumerate(
                intervals, start=1
            ):
                start = max(int(segment.get("start_frame")), window_start)
                end = min(int(segment.get("end_frame")), window_end)
                if start > end:
                    continue
                clipped = dict(segment)
                clipped["segment_id"] = (
                    f"{str(segment.get('segment_id') or '')}-shared{interval_index}"
                )
                clipped["start_frame"] = start
                clipped["end_frame"] = end
                if clipped not in adjusted:
                    adjusted.append(clipped)
        source["allowed_segments"] = adjusted
        if not adjusted:
            source["range_mode"] = "unresolved"
            if "shared_window" not in source["validation_codes"]:
                source["validation_codes"].append("shared_window")

        cues = source.get("timing_cues", [])
        retained_cues = [
            cue
            for cue in cues
            if isinstance(cue, dict)
            and adjusted
            and _cue_inside_contract_segments(cue, adjusted)
        ]
        if len(retained_cues) != len(cues):
            if "emitter_cue_outside_range" not in source["validation_codes"]:
                source["validation_codes"].append("emitter_cue_outside_range")
        source["timing_cues"] = retained_cues

    deduplicated_windows: list[Dict[str, Any]] = []
    seen_window_signatures: set[str] = set()
    for window in shared_windows:
        signature = json.dumps(
            {key: value for key, value in window.items() if key != "window_id"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if signature in seen_window_signatures:
            continue
        seen_window_signatures.add(signature)
        window = dict(window)
        window["window_id"] = f"runtime-shared-{len(deduplicated_windows) + 1}"
        deduplicated_windows.append(window)
    return {
        "sources": runtime_sources,
        "shared_windows": deduplicated_windows,
    }


def _compose_hmb_runtime_prompt(
    prompt_value: Any, runtime_scope: Dict[str, Any]
) -> str:
    """Append private runtime facts and the fixed English output contract."""

    value = getattr(prompt_value, "value", prompt_value)
    public_prompt = str(value or "").rstrip()
    encoded_scope = json.dumps(
        runtime_scope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    appended_size = (
        len(encoded_scope)
        + len(_ENGLISH_GENERATOR_OUTPUT_CONTRACT_HEADER)
        + len(_ENGLISH_GENERATOR_OUTPUT_CONTRACT)
    )
    if not public_prompt or len(public_prompt) + appended_size > 6_000_000:
        raise RuntimeError("HMB runtime prompt size is invalid.")
    return "\n".join((
        public_prompt,
        _RUNTIME_FX_SCOPE_HEADER,
        encoded_scope,
        _ENGLISH_GENERATOR_OUTPUT_CONTRACT_HEADER,
        _ENGLISH_GENERATOR_OUTPUT_CONTRACT,
        "",
    ))


def _contains_korean_script(value: Any) -> bool:
    """Return whether a final generator instruction contains Korean script."""

    if not isinstance(value, str) or not value:
        return False
    return bool(re.search(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]", value))


def _is_private_hmb_runtime_prompt(value: Any) -> bool:
    """Recognize the private machine/runtime envelope at a public UI boundary."""

    text = str(getattr(value, "value", value) or "")
    if not text:
        return False
    folded = text.casefold()
    if _RUNTIME_FX_SCOPE_HEADER.casefold() in folded:
        return True
    return bool(
        text.lstrip().startswith("HMB_GP_Production")
        and _PUBLIC_JOB_CONTRACT_HEADER.casefold() in folded
        and _FX_TIMING_CONTRACT_HEADER.casefold() in folded
        and _USER_DESCRIPTION_DATA_HEADER.casefold() in folded
    )



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
    snapshot. Tests and legacy in-process mocks that bypass graph resolution
    have no retained source instance, so they may use the input itself only
    when it already passes the complete legacy seven-line machine contract.
    """

    visible_prompt = _prompt_transport_text(prompt_value)
    source_node = getattr(node, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
    if source_node is None:
        # Compatibility is deliberately narrow: readable prose, copied text,
        # and partially shaped JSON cannot become an HMB machine contract.
        _assert_public_job_data_contract(visible_prompt)
        _assert_fx_timing_source_contract(visible_prompt)
        return visible_prompt

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


def _ruleset_contains_any_rule(item: Any, rule_texts: list[str]) -> bool:
    return any(_ruleset_contains_exact_rule(item, text) for text in rule_texts)


def _normalized_leak_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _sanitizer_signature_digest(value: str) -> bytes:
    """Return a process-local, non-reversible signature for normalized text."""

    return hashlib.blake2s(
        value.encode("utf-8"),
        key=_SANITIZER_SIGNATURE_KEY,
        digest_size=16,
    ).digest()


def _rolling_text_windows(value: str, length: int):
    """Yield (offset, keyed-process rolling hash) for fixed-size text windows."""

    if length <= 0 or len(value) < length:
        return
    base = _SANITIZER_ROLLING_BASE
    mask = _SANITIZER_ROLLING_MASK
    high_factor = pow(base, length - 1, mask + 1)
    rolling = 0
    for character in value[:length]:
        rolling = ((rolling * base) + ord(character) + 1) & mask
    yield 0, rolling
    for index in range(length, len(value)):
        outgoing = ord(value[index - length]) + 1
        incoming = ord(value[index]) + 1
        rolling = (rolling - (outgoing * high_factor)) & mask
        rolling = ((rolling * base) + incoming) & mask
        yield index - length + 1, rolling


def _freeze_digest_buckets(
    buckets: dict[int, set[bytes]],
) -> dict[int, frozenset[bytes]]:
    return {key: frozenset(values) for key, values in buckets.items()}


def _secret_heading_signatures(
    policy: str, binding: str
) -> tuple[tuple[int, dict[int, frozenset[bytes]]], ...]:
    """Derive keyed exact-heading signatures for private output ports.

    FINAL TEXT may legitimately restate long production clauses required by the
    signed policy, so arbitrary fixed-length policy-window matching is not used.
    Exact internal headings remain protected independently. Only keyed digests
    are retained between calls; plaintext exists solely while the signed
    documents are already live.
    """

    cache_key = _sanitizer_signature_digest(
        "\x00".join((str(policy or ""), str(binding or "")))
    )
    cached = _SANITIZER_SIGNATURE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    heading_signatures: dict[int, dict[int, set[bytes]]] = {}
    for document in (policy, binding):
        for raw_part in re.split(r"[\r\n]+", str(document or "")):
            heading = re.sub(r"^\s*\d+\.\s*", "", raw_part).strip().rstrip(":")
            if (
                len(heading) >= 12
                and re.fullmatch(r"[A-Z][A-Z0-9_ /-]*", heading)
            ):
                normalized_heading = _normalized_leak_text(heading)
                _offset, rolling = next(
                    _rolling_text_windows(
                        normalized_heading, len(normalized_heading)
                    )
                )
                heading_signatures.setdefault(
                    len(normalized_heading), {}
                ).setdefault(rolling, set()).add(
                    _sanitizer_signature_digest(normalized_heading)
                )
    signatures = tuple(
        (length, _freeze_digest_buckets(buckets))
        for length, buckets in sorted(heading_signatures.items())
    )
    if len(_SANITIZER_SIGNATURE_CACHE) >= _SANITIZER_SIGNATURE_CACHE_MAX:
        _SANITIZER_SIGNATURE_CACHE.pop(next(iter(_SANITIZER_SIGNATURE_CACHE)))
    _SANITIZER_SIGNATURE_CACHE[cache_key] = signatures
    return signatures


def _normalized_text_matches_heading_signatures(
    normalized: str,
    heading_signatures: tuple[
        tuple[int, dict[int, frozenset[bytes]]], ...
    ],
) -> bool:
    """Match exact protected headings without arbitrary prose thresholds."""

    for length, buckets in heading_signatures:
        if len(normalized) < length:
            continue
        for index, rolling in _rolling_text_windows(normalized, length):
            digests = buckets.get(rolling)
            if digests and _sanitizer_signature_digest(
                normalized[index : index + length]
            ) in digests:
                return True
    return False


_ZERO_WIDTH_AND_BIDI_CONTROLS = re.compile(
    "[\\u200b-\\u200f\\u202a-\\u202e\\u2060-\\u206f\\ufeff]"
)


def _bounded_decompressed_values(value: bytes) -> list[bytes]:
    """Return complete bounded zlib/gzip/raw-deflate decodes only."""

    decoded_values: list[bytes] = []
    for window_bits in (zlib.MAX_WBITS, zlib.MAX_WBITS | 16, -zlib.MAX_WBITS):
        try:
            decoder = zlib.decompressobj(window_bits)
            decoded = decoder.decompress(value, _SANITIZER_MAX_JSON_CHARS + 1)
            if (
                len(decoded) > _SANITIZER_MAX_JSON_CHARS
                or decoder.unconsumed_tail
                or not decoder.eof
            ):
                continue
            decoded += decoder.flush()
            if 0 < len(decoded) <= _SANITIZER_MAX_JSON_CHARS:
                decoded_values.append(decoded)
        except Exception:
            continue
    return decoded_values


def _string_contains_internal_rule_text(
    value: str,
    heading_signatures: tuple[
        tuple[int, dict[int, frozenset[bytes]]], ...
    ],
    decode_budget: int = 2,
) -> bool:
    """Detect plaintext and bounded reversible encodings of sealed rules.

    Native models can return an otherwise exact rule fragment as base64, hex,
    or reversed text.  Decode only long, syntactically bounded string tokens and
    feed them back through the same in-memory fragment guard.  No decoded text is
    persisted, logged, or included in an exception.
    """

    text = str(value or "")
    normalized = _normalized_leak_text(text)
    if not normalized:
        return False
    if _normalized_text_matches_heading_signatures(normalized, heading_signatures):
        return True

    if decode_budget <= 0:
        return False

    # A model can serialize a fragment as a JSON character/code-point array.
    # Reconstruct only flat bounded arrays; arbitrary structured JSON remains
    # handled by the outer recursive state guard.
    stripped_json = text.strip()
    if stripped_json.startswith("[") and len(stripped_json) <= _SANITIZER_MAX_JSON_CHARS:
        try:
            decoded_json = json.loads(stripped_json)
        except Exception:
            decoded_json = None
        reconstructed_values: list[str] = []
        if isinstance(decoded_json, list) and decoded_json:
            if all(isinstance(item, str) for item in decoded_json):
                reconstructed_values.extend(
                    ("".join(decoded_json), " ".join(decoded_json))
                )
            elif all(
                isinstance(item, int)
                and not isinstance(item, bool)
                and 0 <= item <= 0x10FFFF
                for item in decoded_json
            ):
                try:
                    reconstructed_values.append(
                        "".join(chr(item) for item in decoded_json)
                    )
                except Exception:
                    reconstructed_values = []
        for reconstructed in reconstructed_values:
            if (
                reconstructed
                and reconstructed != text
                and _string_contains_internal_rule_text(
                    reconstructed,
                    heading_signatures,
                    decode_budget - 1,
                )
            ):
                return True

    # Invisible Unicode and bidi controls can make an exact policy fragment
    # render normally while defeating ordinary substring comparison.
    visible_text = _ZERO_WIDTH_AND_BIDI_CONTROLS.sub("", text)
    if visible_text != text and _string_contains_internal_rule_text(
        visible_text,
        heading_signatures,
        decode_budget - 1,
    ):
        return True

    # Percent escaping and ROT13 are reversible text encodings frequently used
    # to bypass exact-output guards. Decode them only within the same bounded
    # recursion budget and never persist the decoded value.
    if re.search(r"%[0-9A-Fa-f]{2}", text):
        try:
            percent_decoded = urllib.parse.unquote_to_bytes(text).decode("utf-8")
        except Exception:
            percent_decoded = ""
        if percent_decoded and percent_decoded != text and _string_contains_internal_rule_text(
            percent_decoded,
            heading_signatures,
            decode_budget - 1,
        ):
            return True
    try:
        rot13_text = codecs.decode(text, "rot_13")
    except Exception:
        rot13_text = text
    if rot13_text != text and _string_contains_internal_rule_text(
        rot13_text,
        heading_signatures,
        decode_budget - 1,
    ):
        return True

    reversed_text = text[::-1]
    if reversed_text != text and _string_contains_internal_rule_text(
        reversed_text,
        heading_signatures,
        0,
    ):
        return True

    encoded_candidates: list[str] = []
    stripped = text.strip()
    if 56 <= len(stripped) <= (_SANITIZER_MAX_JSON_CHARS * 2):
        encoded_candidates.append(stripped)
    for match in re.finditer(
        r"(?<![A-Za-z0-9+/_=-])[A-Za-z0-9+/_-]{56,}={0,2}(?![A-Za-z0-9+/_=-])",
        text,
    ):
        encoded_candidates.append(match.group(0))
        if len(encoded_candidates) >= 64:
            break
    if re.fullmatch(r"(?:[A-Za-z0-9+/_=-]+\s+)+[A-Za-z0-9+/_=-]+", stripped):
        encoded_candidates.append(re.sub(r"\s+", "", stripped))

    seen_candidates: set[str] = set()
    for candidate in encoded_candidates[:64]:
        if candidate in seen_candidates or len(candidate) > (_SANITIZER_MAX_JSON_CHARS * 2):
            continue
        seen_candidates.add(candidate)
        decoded_values: list[bytes] = []
        compact = re.sub(r"\s+", "", candidate)
        if (
            len(compact) >= 80
            and len(compact) % 2 == 0
            and re.fullmatch(r"[0-9A-Fa-f]+", compact)
        ):
            try:
                decoded_values.append(bytes.fromhex(compact))
            except Exception:
                pass
        if len(compact) >= 56 and re.fullmatch(r"[A-Za-z0-9+/_-]+={0,2}", compact):
            padded = compact + ("=" * ((-len(compact)) % 4))
            for altchars in (None, b"-_"):
                try:
                    decoded_values.append(
                        base64.b64decode(
                            padded.encode("ascii"),
                            altchars=altchars,
                            validate=True,
                        )
                    )
                except Exception:
                    continue
        if 56 <= len(compact) <= (_SANITIZER_MAX_JSON_CHARS * 2):
            try:
                decoded_values.append(base64.b85decode(compact.encode("ascii")))
            except Exception:
                pass
            try:
                decoded_values.append(
                    base64.a85decode(compact.encode("ascii"), adobe=False)
                )
            except Exception:
                pass
        for decoded_bytes in decoded_values:
            if not decoded_bytes or len(decoded_bytes) > _SANITIZER_MAX_JSON_CHARS:
                continue
            for decoded_candidate in [
                decoded_bytes,
                *_bounded_decompressed_values(decoded_bytes),
            ]:
                try:
                    decoded_text = decoded_candidate.decode("utf-8")
                except Exception:
                    continue
                if decoded_text == text:
                    continue
                if _string_contains_internal_rule_text(
                    decoded_text,
                    heading_signatures,
                    decode_budget - 1,
                ):
                    return True
    return False



def _value_contains_protected_headings(
    value: Any,
    heading_signatures: tuple[
        tuple[int, dict[int, frozenset[bytes]]], ...
    ],
) -> bool:
    """Boundedly inspect one arbitrary value for protected internal headings."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    inspected = 0
    aggregate_parts: list[str] = []
    while stack:
        item, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return True
        if isinstance(item, str):
            aggregate_parts.append(item)
            if _string_contains_internal_rule_text(
                item, heading_signatures
            ):
                return True
            continue
        if isinstance(item, dict):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            try:
                pairs = list(item.items())
            except Exception:
                return True
            for key, nested in reversed(pairs):
                stack.append((nested, depth + 1))
                stack.append((str(key), depth + 1))
        elif isinstance(item, (list, tuple)):
            item_id = id(item)
            if item_id in visited:
                continue
            visited.add(item_id)
            sequence = list(item)
            if sequence and all(isinstance(nested, str) for nested in sequence):
                for candidate in ("".join(sequence), " ".join(sequence)):
                    if _string_contains_internal_rule_text(
                        candidate, heading_signatures
                    ):
                        return True
            elif sequence and all(
                isinstance(nested, int)
                and not isinstance(nested, bool)
                and 0 <= nested <= 0x10FFFF
                for nested in sequence
            ):
                try:
                    candidate = "".join(chr(nested) for nested in sequence)
                except Exception:
                    return True
                if _string_contains_internal_rule_text(
                    candidate, heading_signatures
                ):
                    return True
            stack.extend((nested, depth + 1) for nested in reversed(sequence))
    if aggregate_parts:
        for candidate in ("".join(aggregate_parts), " ".join(aggregate_parts)):
            if _string_contains_internal_rule_text(
                candidate, heading_signatures
            ):
                return True
    return False


def _contains_internal_rule_text(value: Any, policy: str, binding: str) -> bool:
    heading_signatures = _secret_heading_signatures(policy, binding)
    return _value_contains_protected_headings(value, heading_signatures)


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
            if _AGENT_WRAPPER_KEY_PATTERN.search(text):
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
    """Detect native state shapes without treating policy wording as a leak.

    FINAL TEXT is the generator document. Signed policy may legitimately shape
    or appear in that result, so only runtime scope and Agent wrapper/state
    structures are private on this port. ``policy`` and ``binding`` remain in
    the call signature for compatibility with the strict Agent-port sanitizer.
    """
    if isinstance(value, (dict, list, tuple)):
        return _mapping_contains_agent_state(value)
    if not isinstance(value, str):
        return value is not None

    text = value.strip()
    if not text:
        return False
    if (
        _RUNTIME_FX_SCOPE_HEADER.casefold() in text.casefold()
        or "runtime-shared-" in text.casefold()
    ):
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


def _contains_complete_policy_document(value: Any, policy: str, binding: str) -> bool:
    """Detect a complete protected document without fixed-length fragments.

    Generator prose may reuse any policy-required clause, so partial matches are
    always allowed. A complete policy/binding document or its confidential
    metadata envelope is not generator content and remains blocked. JSON string
    wrappers are decoded at most twice; no arbitrary length threshold is used.
    """

    candidates: list[str] = []
    decoded = value
    for _ in range(3):
        if not isinstance(decoded, str):
            break
        text = decoded.strip()
        if not text or len(text) > _SANITIZER_MAX_JSON_CHARS:
            break
        candidates.append(text)
        if not text.startswith('"'):
            break
        try:
            nested = json.loads(text)
        except Exception:
            break
        if nested == decoded:
            break
        decoded = nested

    protected_documents = tuple(
        normalized
        for normalized in (
            _normalized_leak_text(policy),
            _normalized_leak_text(binding),
        )
        if normalized
    )
    for candidate in candidates:
        normalized_candidate = _normalized_leak_text(candidate)
        if any(
            document in normalized_candidate
            for document in protected_documents
        ):
            return True
        folded = candidate.casefold()
        if (
            "classification: confidential / internal use only" in folded
            and "policy_version:" in folded
        ):
            return True
    return False



def _strip_internal_rules_from_agent_wrapper(
    value: Any,
    policy_rules: list[str],
    binding_rules: list[str],
) -> Any:
    stack: list[tuple[Any, int]] = [(value, 0)]
    visited: set[int] = set()
    inspected = 0
    while stack:
        current, depth = stack.pop()
        inspected += 1
        if inspected > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            raise RuntimeError("Agent wrapper sanitization budget exceeded.")
        if isinstance(current, dict):
            current_id = id(current)
            if current_id in visited:
                continue
            visited.add(current_id)
            for key, nested in list(current.items()):
                if str(key or "").strip().casefold() == "rulesets":
                    if not isinstance(nested, list):
                        current[key] = []
                        continue
                    current[key] = [
                        item
                        for item in nested
                        if not _ruleset_contains_any_rule(item, policy_rules)
                        and not _ruleset_contains_any_rule(item, binding_rules)
                    ]
                    stack.extend(
                        (item, depth + 1) for item in current[key]
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


def _replace_leaked_strings(value: Any, policy: str, binding: str, replacement: str) -> Any:
    visited: set[int] = set()
    budget = [0]
    heading_signatures = _secret_heading_signatures(policy, binding)

    def scrub(item: Any, depth: int) -> Any:
        budget[0] += 1
        if budget[0] > _SANITIZER_MAX_NODES or depth > _SANITIZER_MAX_DEPTH:
            return replacement
        if isinstance(item, str):
            return (
                replacement
                if _string_contains_internal_rule_text(
                    item, heading_signatures
                )
                else item
            )
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
                normalized_key = str(key or "").strip().casefold()
                if normalized_key in _SEALED_POLICY_STATE_KEYS:
                    item[key] = [] if normalized_key == "rulesets" else replacement
                    continue
                item[key] = scrub(nested, depth + 1)
            return item
        return item

    return scrub(value, 0)


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
    HMB execution admits only PROMPT_OUT plus the two sealed Behaviors: caller
    context, memory, rulesets, and tools are not passed to the native run. Once
    the canonical HMB Prompt edge is present, a missing or
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
        self._hmb_shot_context: dict[str, Any] = {}
        self._hmb_shot_catalog_snapshot: dict[str, Any] = {}
        self._hmb_last_generator_snapshot: dict[str, Any] = {}
        # Instance-local execution authority.  Display widget writes and
        # same-flow route callbacks may interleave while several Agents run,
        # but they must not change the exact Shot being consumed by this run.
        self._hmb_execution_shot_binding: dict[str, Any] = {}
        self._hmb_remote_prompt_publication: dict[str, Any] = {}
        self._hmb_remote_prompt_revision = 0
        self._hmb_remote_prompt_source_token = secrets.token_hex(16)
        self._hmb_shot_route_status: dict[str, Any] = {}
        self._hmb_shot_clear_syncing = False
        self._hmb_shot_catalog_syncing = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._hmb_node_surface_prepared = False
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
        """Register node surface once per live node lifecycle."""

        if self._hmb_node_surface_prepared:
            return
        self._hmb_node_surface_prepared = True
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
        self._hmb_last_generator_snapshot = {}
        self._clear_execution_shot_binding()
        self._hmb_remote_prompt_publication = {}
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
        self._hmb_last_generator_snapshot = {}
        self._clear_execution_shot_binding()
        self._hmb_remote_prompt_publication = {}
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

    def _hmb_generator_shot_snapshot(self, expected_final_text: Any) -> dict[str, Any]:
        text = str(getattr(expected_final_text, "value", expected_final_text) or "")
        snapshot = dict(self._hmb_last_generator_snapshot)
        if (
            not text
            or set(snapshot) != {
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
                "final_text_sha256",
            }
            or snapshot.get("schema") != _AGENT_GENERATOR_SNAPSHOT_SCHEMA
            or snapshot.get("version") != _AGENT_GENERATOR_SNAPSHOT_VERSION
            or not hmac.compare_digest(
                str(snapshot.get("final_text_sha256") or ""),
                _prompt_text_sha256(text),
            )
        ):
            raise RuntimeError("HMB Agent Shot result snapshot is unavailable.")
        return snapshot

    def _hmb_generator_prompt_source_node(self, expected_final_text: Any) -> Any:
        """Return the exact Prompt node that supplied this Agent result.

        The verified source is instance-authoritative and should not be derived
        from payload text. The stored pointer can disappear after policy cleanup,
        so we re-verify the current canonical edge when needed.
        """

        self._hmb_generator_shot_snapshot(expected_final_text)
        source_node = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
        if source_node is None:
            if not _is_direct_hmb_prompt_library_connection(self):
                raise RuntimeError(
                    "Remote Agent result source is not a verified HMB Prompt."
                )
            source_node = getattr(self, _VERIFIED_PROMPT_SOURCE_ATTRIBUTE, None)
            if source_node is None:
                raise RuntimeError(
                    "Remote Agent source is unresolved."
                )
        return source_node

    def _hmb_commit_remote_prompt_publication(
        self,
        final_text: Any,
    ) -> dict[str, Any]:
        """Commit one successful FINAL TEXT as the selected Shot's remote authority.

        The publication is process-local and instance-owned.  It is deliberately
        separate from the visible ``output`` parameter so a generator node created
        after this Agent can still pull the exact successful result without a
        visible editor wire or a process-global payload registry.
        """

        text = str(getattr(final_text, "value", final_text) or "")
        snapshot = self._hmb_generator_shot_snapshot(text)
        revision = int(getattr(self, "_hmb_remote_prompt_revision", 0) or 0) + 1
        self._hmb_remote_prompt_revision = revision
        publication = {
            "schema": _AGENT_REMOTE_PROMPT_PUBLICATION_SCHEMA,
            "version": _AGENT_REMOTE_PROMPT_PUBLICATION_VERSION,
            "source_token": str(self._hmb_remote_prompt_source_token),
            "publication_revision": revision,
            **{
                key: snapshot[key]
                for key in (
                    "channel_uuid",
                    "shot_uuid",
                    "shot_number",
                    "shot_name",
                    "prompt_generation",
                    "visible_prompt_sha256",
                    "image_media_sha256",
                    "video_media_sha256",
                    "final_text_sha256",
                )
            },
            "final_text": text,
        }
        self._hmb_remote_prompt_publication = publication
        return dict(publication)

    def _hmb_invalidate_remote_prompt_publication(self) -> None:
        """Remove remote authority without changing the user's visible Agent output."""

        self._hmb_remote_prompt_publication = {}

    def _hmb_remote_prompt_publication_for_generator(self) -> dict[str, Any]:
        """Return the current exact-Shot publication, or no authority at all.

        The generator must already have the router-managed hidden dependency on this
        exact Agent instance.  This method additionally binds the publication to
        the Agent's current Shot selection and its immutable generator snapshot,
        preventing a stale Shot 2 result from being adopted by Shot 3.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return {}
        publication = getattr(self, "_hmb_remote_prompt_publication", None)
        if not isinstance(publication, dict):
            return {}
        required = {
            "schema",
            "version",
            "source_token",
            "publication_revision",
            "channel_uuid",
            "shot_uuid",
            "shot_number",
            "shot_name",
            "prompt_generation",
            "visible_prompt_sha256",
            "image_media_sha256",
            "video_media_sha256",
            "final_text_sha256",
            "final_text",
        }
        if (
            set(publication) != required
            or publication.get("schema") != _AGENT_REMOTE_PROMPT_PUBLICATION_SCHEMA
            or publication.get("version") != _AGENT_REMOTE_PROMPT_PUBLICATION_VERSION
            or not isinstance(publication.get("source_token"), str)
            or not hmac.compare_digest(
                str(publication.get("source_token")),
                str(getattr(self, "_hmb_remote_prompt_source_token", "")),
            )
            or not isinstance(publication.get("publication_revision"), int)
            or isinstance(publication.get("publication_revision"), bool)
            or int(publication["publication_revision"]) <= 0
            or not isinstance(publication.get("final_text"), str)
            or not publication["final_text"]
            or not hmac.compare_digest(
                str(publication.get("final_text_sha256") or ""),
                _prompt_text_sha256(publication["final_text"]),
            )
        ):
            return {}
        subscription = self._hmb_shot_channel_subscription()
        if (
            not subscription.get("enabled")
            or publication.get("channel_uuid") != subscription.get("channel_uuid")
            or publication.get("shot_uuid") != subscription.get("shot_uuid")
            or publication.get("shot_number") != subscription.get("shot_number")
            or publication.get("shot_name") != subscription.get("shot_name")
        ):
            return {}
        try:
            snapshot = self._hmb_generator_shot_snapshot(publication["final_text"])
        except RuntimeError:
            return {}
        snapshot_fields = required - {
            "schema",
            "version",
            "source_token",
            "publication_revision",
            "final_text",
        }
        if any(publication[key] != snapshot[key] for key in snapshot_fields):
            return {}
        return dict(publication)

    def _hmb_shot_routing_status(self, value: Any) -> None:
        if bool(getattr(self, "_hmb_node_deleted", False)):
            return
        if isinstance(value, dict):
            self._hmb_shot_route_status = dict(value)
            if bool(value.get("ok")) and str(value.get("code") or "") == "ready":
                claimed = self._hmb_offer_shot_to_generator_recipients()
                if claimed:
                    try:
                        from _hmb_shot_routing import schedule_post_hydration_reconcile

                        # The recipient changed from Remote waiting to a real
                        # Shot during this routing pass. A hydration pass (not
                        # registration-only polling) is required to create its
                        # Agent text and paired image/video dependencies.
                        schedule_post_hydration_reconcile(self)
                    except Exception:
                        pass

    def _hmb_offer_shot_to_generator_recipients(self) -> int:
        """Offer one complete Prompt/Agent Shot pair to blank generator recipients.

        The recipient owns the adoption policy. Keeping this callback generic
        preserves Agent/provider neutrality while making creation order
        irrelevant: a generator may appear before or after the active pair.
        """

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return 0
        try:
            from _hmb_shot_routing import _same_flow_nodes

            _flow_name, nodes = _same_flow_nodes(self)
        except Exception:
            return 0
        claimed = 0
        for candidate in nodes:
            if candidate is self or bool(getattr(candidate, "_hmb_node_deleted", False)):
                continue
            callback = getattr(candidate, "_hmb_consider_agent_shot_autoclaim", None)
            if not callable(callback):
                continue
            try:
                claimed += int(callback(self) is True)
            except Exception:
                continue
        return claimed

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
        current_is_private = _is_private_hmb_runtime_prompt(current)
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

        if not _is_private_hmb_runtime_prompt(value):
            return value
        candidates = (
            getattr(self, "_hmb_prompt_preview_value", ""),
            self._native_parameter_value(_AGENT_SHOT_PROMPT_INPUT_PARAMETER, ""),
            getattr(self, "_hmb_prompt_before_preview", ""),
            self._native_parameter_value(_AGENT_PROMPT_INPUT_PARAMETER, ""),
        )
        for candidate in candidates:
            candidate_value = getattr(candidate, "value", candidate)
            if candidate_value and not _is_private_hmb_runtime_prompt(candidate_value):
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
            previous = getattr(self, "_hmb_last_generator_snapshot", {})
            if not isinstance(previous, dict) or not previous:
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
                # A real Only/Shot change is authority-changing, unlike an
                # execution-phase display echo. Invalidate the old result now,
                # before the central router mutates managed edges.
                self._hmb_shot_context = {}
                self._hmb_last_generator_snapshot = {}
                self._hmb_invalidate_remote_prompt_publication()
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
            self._hmb_last_generator_snapshot = {}
            self._clear_execution_shot_binding()
            self._hmb_invalidate_remote_prompt_publication()
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
        """Expose only sealed rules and no caller tools during canonical HMB runs."""
        normalized_name = str(name or "").strip().casefold()
        if self._hmb_rules_active and normalized_name in _HMB_ISOLATED_LIST_INPUTS:
            return []
        if normalized_name != "rulesets" or not self._hmb_rules_active:
            return super().get_parameter_list_value(name)
        project_name, shot_name = self._hmb_ruleset_names
        if not project_name or not shot_name or project_name == shot_name:
            raise RuntimeError("HMBAgentLibrary sealed rule scope is unavailable.")
        return [
            {"name": project_name, "rules": list(self._hmb_policy_rules)},
            {"name": shot_name, "rules": list(self._hmb_binding_rules)},
        ]

    def get_parameter_value(self, name: str):
        """Keep canonical HMB execution stateless and free of external context."""

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
            if normalized_name in {"include_details", "stream", "streaming"}:
                return False
            if normalized_name in _HMB_ISOLATED_SCALAR_INPUTS:
                if normalized_name in {"agent", "output_schema"}:
                    return None
                if normalized_name in {
                    "additional_context", "instructions", "system", "system_prompt"
                }:
                    return ""
                if normalized_name == "messages":
                    return []
                return {}
            if normalized_name in _HMB_ISOLATED_LIST_INPUTS or normalized_name == "rulesets":
                return []
        return super().get_parameter_value(name)

    def _load_hmb_rules(self) -> tuple[str, str, list[str], list[str]]:
        # Every HMB execution reads the fixed server DAT again.  The decoded
        # policy exists only for this native call and is cleared immediately
        # afterward; no process-scoped policy session is retained.
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
                payload.get("final_motion_look_policy_sha256") or ""
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
        self._hmb_last_generator_snapshot = {}
        self._hmb_invalidate_remote_prompt_publication()
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

    def _run_protected_agent_non_streaming(self, agent: Any, prompt: Any) -> Any:
        """Run one protected HMB request without the Cloud SSE transport.

        Griptape Cloud's streaming endpoint can return an error event whose
        payload has no text delta.  The current Griptape driver retries that
        malformed event and ultimately raises ``KeyError('text')`` before any
        final answer exists.  HMB cannot expose partial stream fragments in any
        case, so its protected path uses the driver's ordinary single-response
        request.  Standalone/Only mode continues to use the native Agent path
        unchanged.
        """

        tasks = list(getattr(agent, "tasks", ()) or ())
        if not tasks:
            raise RuntimeError("Protected Agent has no prompt task.")
        task = tasks[0]
        prompt_driver = getattr(task, "prompt_driver", None)
        if prompt_driver is None:
            raise RuntimeError("Protected Agent prompt driver is unavailable.")
        try:
            prompt_driver.stream = False
        except Exception as exc:
            raise RuntimeError(
                "Protected Agent prompt driver cannot disable streaming."
            ) from exc

        runner = getattr(agent, "run", None)
        if not callable(runner):
            raise RuntimeError("Protected Agent synchronous runner is unavailable.")
        runner(*([prompt] if prompt else []))

        agent_output = getattr(agent, "output", None)
        output_value = getattr(agent_output, "value", agent_output)
        serializer = getattr(output_value, "model_dump_json", None)
        final_text = (
            str(serializer())
            if callable(serializer)
            else str(agent_output)
        )
        self._last_raw_output = final_text
        self.set_parameter_value("output", final_text)
        return agent

    def _process(self, agent: Any, prompt: Any) -> Any:
        """Keep native streaming for Only; use one response for protected HMB."""

        if bool(getattr(self, "_hmb_rules_active", False)):
            return self._run_protected_agent_non_streaming(agent, prompt)
        return super()._process(agent, prompt)

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
                        except Exception:
                            # The host scheduler would otherwise publish an
                            # exception containing provider/model data before
                            # this node's fixed-message failure path can run.
                            self._hmb_scheduler_step_failed = True
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
        """Sanitize public outputs and report an English-language violation."""

        if bool(getattr(self, "_hmb_node_deleted", False)):
            return False
        outputs = getattr(self, "parameter_output_values", None)
        if not isinstance(outputs, dict):
            return False

        blocked = _PUBLIC_OUTPUT_BLOCKED
        english_output_failed = False
        self._hmb_last_sanitizer_status = "sanitizer_error"
        try:
            for key, current in list(outputs.items()):
                if key == "agent" and isinstance(current, dict):
                    _strip_internal_rules_from_agent_wrapper(
                        current,
                        self._hmb_policy_rules,
                        self._hmb_binding_rules,
                    )
                    _strip_runtime_scope_from_agent_wrapper(current)
                if key == "output":
                    sanitized = current
                    english_output_failed = _contains_korean_script(sanitized)
                    if english_output_failed:
                        # Never forward Korean instructions to a downstream
                        # video generator. Translation is the model's job under
                        # the private contract above; the sanitizer does not
                        # guess at or rewrite production meaning.
                        sanitized = _HMB_ENGLISH_OUTPUT_REQUIRED_MESSAGE
                        leak_detected = False
                        self._hmb_last_sanitizer_status = "english"
                    else:
                        # Shot-tailored policy results and policy-required
                        # production language are valid FINAL TEXT. Fixed-length
                        # source-text matching is intentionally not a publication
                        # criterion; block only actual runtime/Agent-state shapes
                        # or a complete confidential policy document dump.
                        state_leak_detected = _contains_public_output_state_leak(
                            sanitized,
                            self._hmb_policy,
                            self._hmb_binding,
                        )
                        policy_document_detected = (
                            _contains_complete_policy_document(
                                sanitized,
                                self._hmb_policy,
                                self._hmb_binding,
                            )
                        )
                        leak_detected = (
                            state_leak_detected or policy_document_detected
                        )
                        self._hmb_last_sanitizer_status = (
                            "state"
                            if state_leak_detected
                            else "policy_document"
                            if policy_document_detected
                            else "clean"
                        )
                else:
                    sanitized = _replace_leaked_strings(
                        current,
                        self._hmb_policy,
                        self._hmb_binding,
                        blocked,
                    )
                    leak_detected = _contains_internal_rule_text(
                        sanitized, self._hmb_policy, self._hmb_binding
                    )
                    if key != "agent":
                        leak_detected = leak_detected or (
                            _contains_public_output_state_leak(
                                sanitized,
                                self._hmb_policy,
                                self._hmb_binding,
                            )
                        )
                if leak_detected:
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
            return english_output_failed
        except Exception:
            # A broken detector cannot establish that FINAL TEXT is free of
            # native state or a complete protected document. Fail closed.
            outputs["agent"] = {}
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
        self._hmb_last_generator_snapshot = {}
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
            # Authenticate and verify the signed Broker policy exactly once for
            # this packaged Griptape engine process. Library discovery remains
            # network-free; only a canonical HMB Prompt -> Agent execution can
            # initialize the protected session.
            self._set_agent_execution_phase("authorizing")
            _hmb._bootstrap_agent_policy_session()
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
            source_contract_stage = "public_job"
            _assert_public_job_data_contract(machine_prompt)
            source_contract_stage = "fx_contract"
            fx_timing_contract = _assert_fx_timing_source_contract(machine_prompt)
            source_contract_stage = "signed_candidate"
            _assert_fx_candidate_matches_signed_runtime(fx_timing_contract)
            # The paired machine contract contains only raw selections and
            # validated addresses. Human-readable PROMPT_OUT prose is never
            # parsed. Shared boundaries and range-scoped cues are derived only
            # now, after the signed 4+4 runtime has loaded successfully.
            source_contract_stage = "runtime_scope"
            runtime_scope = _derive_fx_timing_runtime_scope(
                fx_timing_contract,
                policy_rules=self._hmb_policy_rules,
                binding_rules=self._hmb_binding_rules,
            )
            source_contract_stage = "runtime_prompt"
            self._hmb_runtime_prompt = _compose_hmb_runtime_prompt(
                machine_prompt, runtime_scope
            )
        except _HMBPolicyIdentityMismatchError:
            self._publish_hmb_execution_block(
                _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
            )
            raise RuntimeError(
                _HMB_POLICY_IDENTITY_MISMATCH_MESSAGE
            ) from None
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
        english_output_failed = False
        sanitizer_ran = False
        self._hmb_suppress_visible_publication = True
        try:
            try:
                result = yield from self._run_native_agent_once()
            except Exception:
                # Native exceptions can contain model, memory, or tool payloads.
                # The canonical HMB edge therefore exposes only one fixed message.
                native_failed = True

            if not native_failed and self._hmb_lifecycle_is_live(
                lifecycle_generation
            ):
                english_output_failed = self._secure_hmb_outputs()
                sanitizer_ran = True
        finally:
            self._hmb_rules_active = False
            # The native Agent may publish a partial wrapper or tool trace before
            # raising. Always remove and scrub the temporary HMB rules in the same
            # finally path so an exceptional execution cannot bypass protection.
            try:
                if not self._hmb_lifecycle_is_live(lifecycle_generation):
                    return None
                if not sanitizer_ran:
                    english_output_failed = self._secure_hmb_outputs()
                outputs = getattr(self, "parameter_output_values", None)
                final_text = outputs.get("output") if isinstance(outputs, dict) else ""
                sanitizer_status = str(
                    getattr(self, "_hmb_last_sanitizer_status", "") or ""
                )
                self._hmb_suppress_visible_publication = False
                if isinstance(final_text, str):
                    self._set_visible_output(final_text)
                if (
                    not native_failed
                    and not english_output_failed
                    and sanitizer_status == "clean"
                    and self._hmb_shot_context
                    and isinstance(final_text, str)
                    and final_text
                    and final_text != _PUBLIC_OUTPUT_BLOCKED
                ):
                    self._hmb_last_generator_snapshot = {
                        "schema": _AGENT_GENERATOR_SNAPSHOT_SCHEMA,
                        "version": _AGENT_GENERATOR_SNAPSHOT_VERSION,
                        **{
                            key: self._hmb_shot_context[key]
                            for key in (
                                "channel_uuid",
                                "shot_uuid",
                                "shot_number",
                                "shot_name",
                                "prompt_generation",
                                "visible_prompt_sha256",
                                "image_media_sha256",
                                "video_media_sha256",
                            )
                        },
                        "final_text_sha256": _prompt_text_sha256(final_text),
                    }
                    self._hmb_commit_remote_prompt_publication(final_text)
                else:
                    self._hmb_last_generator_snapshot = {}
                    self._hmb_invalidate_remote_prompt_publication()
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
                self._hmb_last_generator_snapshot = {}
                self._hmb_invalidate_remote_prompt_publication()
            finally:
                self._hmb_suppress_visible_publication = False
                self._clear_hmb_runtime_policy()
                self._set_agent_execution_phase("")
                self._clear_execution_shot_binding()
        try:
            self._refresh_agent_shot_route()
        except Exception:
            pass
        if english_output_failed:
            self._publish_hmb_execution_block(
                _HMB_ENGLISH_OUTPUT_REQUIRED_MESSAGE
            )
            raise RuntimeError(
                _HMB_ENGLISH_OUTPUT_REQUIRED_MESSAGE
            ) from None
        if native_failed:
            self._publish_hmb_execution_block(_HMB_EXECUTION_FAILED_MESSAGE)
            raise RuntimeError(_HMB_EXECUTION_FAILED_MESSAGE) from None
        return result
