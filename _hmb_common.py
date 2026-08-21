from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import http.client
import importlib
import importlib.util
import json
import os
import re
import ssl
import stat
import sys
import zlib
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

try:
    from griptape_nodes.exe_types.core_types import Parameter, ParameterGroup, ParameterMode
    from griptape_nodes.exe_types.node_types import DataNode
except Exception:  # Local validation fallback only.
    ParameterMode = None

    class Parameter:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)
            self.name = kwargs.get("name")
            self.default_value = kwargs.get("default_value")
            self._children: List[Any] = []

        def add_trait(self, trait: Any) -> None:
            self._children.append(trait)

        def add_child(self, child: Any) -> None:
            self._children.append(child)

        def find_elements_by_type(
            self,
            element_type: Any,
            find_recursively: bool = True,
        ) -> List[Any]:
            return [child for child in self._children if isinstance(child, element_type)]

    class ParameterGroup:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)
            self.name = kwargs.get("name")

    class DataNode:
        def __init__(self, **kwargs: Any) -> None:
            self.parameters: Dict[str, Parameter] = {}
            self.parameter_output_values: Dict[str, Any] = {}
            self.name = kwargs.get("name", self.__class__.__name__)

        def add_parameter(self, parameter: Parameter) -> None:
            self.parameters[parameter.name] = parameter

        def get_parameter_value(self, name: str) -> Any:
            parameter = self.parameters.get(name)
            return getattr(parameter, "default_value", None)

        def set_parameter_value(self, name: str, value: Any) -> None:
            if name in self.parameters:
                self.parameters[name].default_value = value


ROOT = Path(__file__).resolve().parent
_AGENT_POLICY_BROKER_URL = "https://192.168.203.245:8443/api/v1/agent-core/dat"
_AGENT_POLICY_BROKER_HOST = "192.168.203.245"
_AGENT_POLICY_BROKER_PORT = 8443
_AGENT_POLICY_BROKER_PATH = "/api/v1/agent-core/dat"
_AGENT_POLICY_BROKER_CA_FILE = ROOT / "resources" / "tls" / "hmb_agent_broker_ca.pem"
_AGENT_POLICY_BROKER_CA_DER_SHA256 = (
    "3eb0a51f18c6b55866e3299585cabb29166b7b158a59bb9741b0bc98b6e96120"
)
_AGENT_POLICY_REQUEST_TIMEOUT_SECONDS = 15.0
_AGENT_POLICY_MAX_ENVELOPE_BYTES = 128 * 1024
_AGENT_POLICY_MAX_DECOMPRESSED_BYTES = 512 * 1024
_AGENT_POLICY_MAX_DPAPI_FILE_BYTES = 64 * 1024
_AGENT_POLICY_MAX_DPAPI_PLAINTEXT_BYTES = 16 * 1024
_AGENT_POLICY_MAX_BEARER_TOKEN_BYTES = 8192
_AGENT_POLICY_MAX_CA_PEM_BYTES = 64 * 1024
_AGENT_POLICY_WINDOWS_REPARSE_POINT = 0x400
_AGENT_POLICY_BEARER_TOKEN_BYTES = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-"
)
PATH_LOG_PREFIX = "[HMB_PRODUCTION][PATH]"
WARN_LOG_PREFIX = "[HMB_PRODUCTION][WARN]"
_AGENT_POLICY_LOG_PREFIX = "[HMB_PRODUCTION][AGENT_POLICY]"
_AGENT_POLICY_DIAGNOSTIC_STAGES = frozenset(
    {
        "bootstrap_enter",
        "bootstrap_state_empty",
        "bootstrap_state_loading",
        "bootstrap_state_ready",
        "bootstrap_state_failed",
        "bootstrap_state_closed",
        "bootstrap_state_unknown",
        "provenance_accepted",
        "provenance_platform_rejected",
        "provenance_layout_rejected",
        "provenance_argv_count_rejected",
        "provenance_executable_rejected",
        "provenance_argv0_rejected",
        "provenance_arguments_rejected",
        "provenance_parent_rejected",
        "provenance_probe_exception",
        "broker_fetch_enter",
        "broker_private_ssl_context_restored",
        "broker_tls_context_ready",
        "broker_connect_enter",
        "broker_connect_ok",
        "broker_connect_permission_denied",
        "broker_connect_refused",
        "broker_connect_timeout",
        "broker_connect_tls_failed",
        "broker_connect_http_failed",
        "broker_connect_os_failed",
        "broker_peer_certificate_missing",
        "broker_peer_pin_mismatch",
        "broker_tls_peer_verified",
        "broker_token_ready",
        "broker_http_200",
        "broker_http_401",
        "broker_http_403",
        "broker_http_429",
        "broker_http_other",
        "broker_headers_verified",
        "broker_envelope_received",
        "broker_fetch_failed",
        "policy_verify_enter",
        "policy_verified",
        "policy_verify_failed",
        "session_ready",
        "bootstrap_failed",
    }
)


def _agent_policy_log_stage(stage: str) -> None:
    """Emit one bounded diagnostic code without paths, tokens, or policy data."""

    if stage in _AGENT_POLICY_DIAGNOSTIC_STAGES:
        print(f"{_AGENT_POLICY_LOG_PREFIX} stage={stage}", flush=True)

_AGENT_POLICY_ENVELOPE_SCHEMA = "hmb-agent-policy-envelope-v3"
_AGENT_POLICY_SCHEMA = "hmb-agent-policy-v3"
# Current package/source baseline metadata. Runtime acceptance intentionally
# does not compare a signed payload's version to this value.
_AGENT_POLICY_VERSION = "2026-08-12.agent-shot-quality.v4.2"
_AGENT_POLICY_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
_AGENT_POLICY_SIGNATURE_ALGORITHM = "RSASSA-PKCS1-v1_5-SHA256"
_AGENT_POLICY_SIGNING_KEY_ID = "hmb-policy-local-2026-08-r1"
_AGENT_POLICY_TRUST_CERTIFICATE_SHA256 = (
    "65676e251c72b4d42424eaf2f920b35860b925242778289e8af81e698dfd2220"
)
_AGENT_POLICY_TRUST_MODULUS_SHA256 = (
    "38ae35e961efb8952dbbc72b9820601f1cdf1e0ad4b17b047ba92d4813ae7456"
)
_AGENT_POLICY_RSA_MODULUS_B64 = (
    "um+j6UoXL7VVQb+W5a7Xy0rdutX+H4yCW7sV+1U1ESZoUjMcPcYPQ8QKUKeVtdN1"
    "TwQ55DbOEw0SYfLQfLUff8J/k9J0/Ol1SjtnppRH+Vg5MANExv6j1tpqRXWSLjSvy"
    "YSNnfxMg0PvfEhToAj94zVi+a/7FifEftvDMaT/iiMmMwQBxAU9WqqyYf96DQfzNG"
    "aV7wlAM6+qWSTmyV/8/mk/8pWFJTWJuwXEnxlafWhXBCJkH4e5upy+0goRhoxlt5Z"
    "PRDSs5zw9CgiBjw1lrB+CYWMEOmNbt+FcbV7lgCGw8QNFl20FNa8r+SCEEwyUyFNb"
    "oPag5zu87WSs5rcwvi/xFrDBBcxCVWj185/tCG/j0ldKr4J71CVs42x+DHqmNvba9"
    "SR1JZ8QpDEIIupRbboNhfB+f64mPcFQRD0bRboF4oKhJBELEVEQabhTkyLYEKVOym"
    "sEbwcRei3wiLPkMpMG7MieR+E+ctRR5MSD49ojD+4GCW6DXkx2ZpR2tH3x"
)
_AGENT_POLICY_RSA_EXPONENT = 65537
_AGENT_POLICY_ENVELOPE_FIELDS = frozenset(
    {"schema", "algorithm", "key_id", "payload_sha256", "payload", "signature"}
)
_AGENT_POLICY_PAYLOAD_FIELDS = frozenset(
    {
        "schema",
        "policy",
        "policy_sha256",
        "binding",
        "binding_sha256",
        "final_policy_version",
        "final_motion_look_policy_clauses",
        "final_motion_look_policy_sha256",
        "video_appearance_isolation_clauses",
    }
)
_AGENT_POLICY_SHARED_MARKERS = (
    "HYBRID COMPOSITION INDEPENDENCE:",
    "MISSING SOURCE AUTHORITY:",
    "OPTIONAL VIDEO CONTROL:",
    "COLOR PLAYBLAST ISOLATION WITHOUT DEPENDENCY:",
    "ADAPTIVE CONFLICT RESOLUTION:",
    "FINAL OUTPUT CONTINUITY:",
)
_AGENT_POLICY_VERSION_PATTERN = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
    r"\.v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*"
)


def _load_agent_process_session_module() -> Any:
    """Load one process-stable memory cell across HMB library hot reloads."""

    module_path = (ROOT / "_hmb_agent_session.py").resolve(strict=True)
    module_name = "_hmb_gp_production_agent_session_" + hashlib.sha1(
        str(module_path).encode("utf-8")
    ).hexdigest()[:12]
    existing = sys.modules.get(module_name)
    if existing is not None:
        if Path(getattr(existing, "__file__", "")).resolve() != module_path:
            raise ImportError("HMB Agent process session identity mismatch")
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError("HMB Agent process session could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


_agent_process_session = _load_agent_process_session_module()

# Canonical image-source taxonomy.
#
# HMBPromptLibrary binds these values into its dashboard and
# HMBImageAssetLibrary uses the same objects to build its project asset tree.
# Keep all image Main Type / Sub Type additions here so the two libraries
# cannot silently drift.
# ``Role Required / Select Source Type`` is retained only as a serialized-state
# compatibility token.  New Image Asset UI/state uses the non-mandatory label;
# a missing creative role is ordinary unclassified metadata, never a gate.
IMAGE_SOURCE_TYPE_UNCLASSIFIED = "Select Source Type"
IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED = "Role Required / Select Source Type"

IMAGE_SOURCE_TYPE_CHOICES = [
    IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED,
    "Ignore / Unused",
    "Character Appearance",
    "Partial Character Detail",
    "Prop / Accessory",
    "Costume / Clothing",
    "Environment / Background",
    "Sky / Exterior Background",
    "Set / Structure",
    "Foreground / Ground",
    "Color / Look Reference",
    "Color + Look + Lighting Mood Reference",
    "Lighting / Atmosphere Reference",
    "Scale / Composition Reference",
    "Custom",
]

IMAGE_SCOPE_CHOICES = [
    "",
    "Full body / full appearance",
    "Head / face only",
    "Eye / expression detail",
    "Eyes / iris / pupil detail",
    "Hand / foot / body part detail",
    "Hair / fur detail",
    "Costume detail",
    "Full outfit / complete costume",
    "Handheld prop",
    "Attached accessory",
    "Interactive scene prop",
    "Independent scene prop",
    "Main background",
    "Sky / exterior area",
    "Set geometry / structure only",
    "Ground / floor",
    "Foreground element",
    "Color mood only",
    "Lighting mood only",
    "Render look only",
    "All color + look + lighting functions",
    "Scale only",
    "Composition only",
    "Scale + composition",
    "Custom scope",
]

IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE = {
    IMAGE_SOURCE_TYPE_LEGACY_UNCLASSIFIED: [""],
    IMAGE_SOURCE_TYPE_UNCLASSIFIED: [""],
    "Ignore / Unused": [""],
    "Character Appearance": [
        "",
        "Full body / full appearance",
        "Head / face only",
        "Custom scope",
    ],
    "Partial Character Detail": [
        "",
        "Head / face only",
        "Eye / expression detail",
        "Eyes / iris / pupil detail",
        "Hand / foot / body part detail",
        "Hair / fur detail",
        "Costume detail",
        "Custom scope",
    ],
    "Prop / Accessory": [
        "",
        "Handheld prop",
        "Attached accessory",
        "Interactive scene prop",
        "Independent scene prop",
        "Custom scope",
    ],
    "Costume / Clothing": [
        "",
        "Costume detail",
        "Full outfit / complete costume",
        "Custom scope",
    ],
    "Environment / Background": ["", "Main background", "Custom scope"],
    "Sky / Exterior Background": ["", "Sky / exterior area", "Custom scope"],
    "Set / Structure": ["", "Set geometry / structure only", "Custom scope"],
    "Foreground / Ground": [
        "",
        "Foreground element",
        "Ground / floor",
        "Custom scope",
    ],
    "Color / Look Reference": [
        "",
        "Color mood only",
        "Render look only",
        "Custom scope",
    ],
    "Color + Look + Lighting Mood Reference": [
        "",
        "All color + look + lighting functions",
        "Color mood only",
        "Lighting mood only",
        "Render look only",
        "Custom scope",
    ],
    "Lighting / Atmosphere Reference": [
        "",
        "Lighting mood only",
        "Custom scope",
    ],
    "Scale / Composition Reference": [
        "",
        "Scale only",
        "Composition only",
        "Scale + composition",
        "Custom scope",
    ],
    "Custom": list(IMAGE_SCOPE_CHOICES),
}

IMAGE_SYSTEM_TARGETS = {
    "Scene / Environment",
    "Camera / Composition",
    "Global Look",
    "None",
}
IMAGE_OWNER_CHOICES = [
    "",
    "Scene / Environment",
    "Camera / Composition",
    "Global Look",
    "None",
]

ACTOR_COLOR_PICK_CHOICES = [
    "Red",
    "Green",
    "Blue",
    "Yellow",
    "Orange",
    "Purple",
    "Pink",
]
GHOST_COLOR_PICK_CHOICES = [
    "Sky Blue",
    "Mint",
    "Beige",
]
PATTERN_COLOR_PICK_CHOICES = [
    "Direction Checker",
    "Sky Grid",
    "Floor Grid",
    "Position Pattern",
]
OBJECT_COLOR_PICK_CHOICES = GHOST_COLOR_PICK_CHOICES + PATTERN_COLOR_PICK_CHOICES
COLOR_PICK_CHOICES = ACTOR_COLOR_PICK_CHOICES + OBJECT_COLOR_PICK_CHOICES
ACTOR_COLOR_PICK_SOURCE_TYPES = {
    "Character Appearance",
    "Partial Character Detail",
    "Costume / Clothing",
}
OBJECT_COLOR_PICK_SOURCE_TYPES = {
    "Prop / Accessory",
    "Environment / Background",
    "Sky / Exterior Background",
    "Set / Structure",
    "Foreground / Ground",
    "Color / Look Reference",
    "Color + Look + Lighting Mood Reference",
    "Lighting / Atmosphere Reference",
    "Scale / Composition Reference",
}

# User-facing image taxonomy.  ``source_type``/``scope`` remain the stable
# public Agent wire contract; these compact fields are the only authoring
# authority shown by ImageAsset and Prompt.  Legacy selections are deliberately
# released instead of inferred or migrated.
IMAGE_MAIN_TYPE_UNCLASSIFIED = "Select Image Main Type"
IMAGE_MAIN_TYPE_CHOICES = [
    IMAGE_MAIN_TYPE_UNCLASSIFIED,
    "Character",
    "Character Prop",
    "Environment / Background",
    "Background Prop",
    "Look Reference",
    "Custom / Context",
]
IMAGE_SUB_TYPE_CHOICES = {
    "Character": [
        "Full Appearance",
        "Head / Face",
        "Eyes / Expression",
        "Body Part",
        "Hair / Fur",
        "Costume Detail",
        "Full Costume",
    ],
    "Character Prop": [
        "Handheld Prop",
        "Attached Accessory",
        "Character Interactive Prop",
    ],
    "Environment / Background": [
        "Main Background",
        "Sky / Exterior",
        "Ground / Floor",
        "Foreground",
    ],
    "Background Prop": [
        "Independent Scene Prop",
        "Interactive Scene Prop",
        "Set / Structure",
    ],
    "Look Reference": [
        "Color Mood",
        "Lighting / Atmosphere",
        "Render Look",
        "Color / Look / Lighting",
        "Scale",
        "Composition",
        "Scale / Composition",
    ],
    "Custom / Context": [
        "Context",
        "Custom",
    ],
}

IMAGE_TAXONOMY_WIRE_MAP = {
    ("Character", "Full Appearance"): (
        "Character Appearance",
        "Full body / full appearance",
    ),
    ("Character", "Head / Face"): (
        "Partial Character Detail",
        "Head / face only",
    ),
    ("Character", "Eyes / Expression"): (
        "Partial Character Detail",
        "Eye / expression detail",
    ),
    ("Character", "Body Part"): (
        "Partial Character Detail",
        "Hand / foot / body part detail",
    ),
    ("Character", "Hair / Fur"): (
        "Partial Character Detail",
        "Hair / fur detail",
    ),
    ("Character", "Costume Detail"): (
        "Costume / Clothing",
        "Costume detail",
    ),
    ("Character", "Full Costume"): (
        "Costume / Clothing",
        "Full outfit / complete costume",
    ),
    ("Character Prop", "Handheld Prop"): (
        "Prop / Accessory",
        "Handheld prop",
    ),
    ("Character Prop", "Attached Accessory"): (
        "Prop / Accessory",
        "Attached accessory",
    ),
    ("Character Prop", "Character Interactive Prop"): (
        "Prop / Accessory",
        "Interactive scene prop",
    ),
    ("Environment / Background", "Main Background"): (
        "Environment / Background",
        "Main background",
    ),
    ("Environment / Background", "Sky / Exterior"): (
        "Sky / Exterior Background",
        "Sky / exterior area",
    ),
    ("Environment / Background", "Ground / Floor"): (
        "Foreground / Ground",
        "Ground / floor",
    ),
    ("Environment / Background", "Foreground"): (
        "Foreground / Ground",
        "Foreground element",
    ),
    ("Background Prop", "Independent Scene Prop"): (
        "Prop / Accessory",
        "Independent scene prop",
    ),
    ("Background Prop", "Interactive Scene Prop"): (
        "Prop / Accessory",
        "Interactive scene prop",
    ),
    ("Background Prop", "Set / Structure"): (
        "Set / Structure",
        "Set geometry / structure only",
    ),
    ("Look Reference", "Color Mood"): (
        "Color / Look Reference",
        "Color mood only",
    ),
    ("Look Reference", "Lighting / Atmosphere"): (
        "Lighting / Atmosphere Reference",
        "Lighting mood only",
    ),
    ("Look Reference", "Render Look"): (
        "Color / Look Reference",
        "Render look only",
    ),
    ("Look Reference", "Color / Look / Lighting"): (
        "Color + Look + Lighting Mood Reference",
        "All color + look + lighting functions",
    ),
    ("Look Reference", "Scale"): (
        "Scale / Composition Reference",
        "Scale only",
    ),
    ("Look Reference", "Composition"): (
        "Scale / Composition Reference",
        "Composition only",
    ),
    ("Look Reference", "Scale / Composition"): (
        "Scale / Composition Reference",
        "Scale + composition",
    ),
    ("Custom / Context", "Context"): ("Custom", ""),
    ("Custom / Context", "Custom"): ("Custom", "Custom scope"),
}

IMAGE_CHARACTER_COLOR_MAIN_TYPES = {"Character", "Character Prop"}
IMAGE_BACKGROUND_COLOR_MAIN_TYPES = {
    "Environment / Background",
    "Background Prop",
}


def image_scope_choices_for_source_type(source_type: Any) -> List[str]:
    """Return a copy of the canonical Sub Type choices for one Main Type."""
    key = str(source_type or "").strip()
    choices = IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE.get(key, IMAGE_SCOPE_CHOICES)
    return list(choices)


def image_color_pick_choices_for_source_type(source_type: Any) -> List[str]:
    """Return the Video Picker Color Pick candidates allowed by a Main Type."""
    key = str(source_type or "").strip()
    if key in ACTOR_COLOR_PICK_SOURCE_TYPES:
        return list(ACTOR_COLOR_PICK_CHOICES + GHOST_COLOR_PICK_CHOICES)
    if key in OBJECT_COLOR_PICK_SOURCE_TYPES:
        return list(OBJECT_COLOR_PICK_CHOICES)
    if key == "Custom":
        return list(COLOR_PICK_CHOICES)
    return []


def image_sub_type_choices_for_main_type(main_type: Any) -> List[str]:
    """Return the user-facing Sub Type choices for one image Main Type."""
    return list(IMAGE_SUB_TYPE_CHOICES.get(str(main_type or "").strip(), []))


def image_taxonomy_wire_pair(main_type: Any, sub_type: Any) -> tuple[str, str] | None:
    """Project one authoring pair onto the unchanged public Agent schema."""
    return IMAGE_TAXONOMY_WIRE_MAP.get(
        (str(main_type or "").strip(), str(sub_type or "").strip())
    )


def image_color_pick_choices_for_taxonomy(
    main_type: Any,
    sub_type: Any = "",
) -> List[str]:
    """Return authoring colors without granting Look Reference marker authority."""
    main = str(main_type or "").strip()
    sub = str(sub_type or "").strip()
    if main in IMAGE_CHARACTER_COLOR_MAIN_TYPES:
        return list(ACTOR_COLOR_PICK_CHOICES)
    if main in IMAGE_BACKGROUND_COLOR_MAIN_TYPES:
        return list(OBJECT_COLOR_PICK_CHOICES)
    if main == "Custom / Context" and sub == "Custom":
        return list(COLOR_PICK_CHOICES)
    # Look Reference and Context intentionally describe the whole scene and
    # therefore never expose a per-marker Color Pick.
    return []


def _try_add(node: Any, element: Any) -> bool:
    try:
        node.add_parameter(element)
        return True
    except Exception:
        return False


def add_group(node: Any, name: str, tooltip: str = "", collapsed: bool = False) -> str:
    """Add a visual ParameterGroup when the runtime supports it."""
    try:
        group = ParameterGroup(
            name=name,
            tooltip=tooltip,
            ui_options={"collapsed": collapsed},
        )
        if _try_add(node, group):
            return name
    except Exception:
        pass
    return ""


def set_output(node: Any, name: str, value: Any) -> None:
    if hasattr(node, "parameter_output_values"):
        node.parameter_output_values[name] = value
    else:
        setattr(node, name, value)


def parameter_exists(node: Any, name: str) -> bool:
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


def _verify_rsa_pkcs1_v15_sha256(
    payload_bytes: bytes,
    signature: bytes,
    *,
    modulus_b64: str,
    exponent: int,
) -> bool:
    """Verify one RSA-3072/SHA-256 signature against an explicit public key."""

    try:
        modulus = int.from_bytes(
            base64.b64decode(modulus_b64, validate=True),
            "big",
        )
        key_size = (modulus.bit_length() + 7) // 8
        if key_size != 384 or exponent != 65537 or len(signature) != key_size:
            return False
        signature_int = int.from_bytes(signature, "big")
        if signature_int <= 0 or signature_int >= modulus:
            return False
        encoded = pow(
            signature_int,
            exponent,
            modulus,
        ).to_bytes(key_size, "big")
        digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(
            payload_bytes
        ).digest()
        padding_size = key_size - len(digest_info) - 3
        if padding_size < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
        return hmac.compare_digest(encoded, expected)
    except Exception:
        return False


def _verify_agent_policy_signature(payload_bytes: bytes, signature: bytes) -> bool:
    """Verify using the literal production trust anchor, not mutable metadata."""

    return _verify_rsa_pkcs1_v15_sha256(
        payload_bytes,
        signature,
        modulus_b64=(
            "um+j6UoXL7VVQb+W5a7Xy0rdutX+H4yCW7sV+1U1ESZoUjMcPcYPQ8QKUKeVtdN1"
            "TwQ55DbOEw0SYfLQfLUff8J/k9J0/Ol1SjtnppRH+Vg5MANExv6j1tpqRXWSLjSvy"
            "YSNnfxMg0PvfEhToAj94zVi+a/7FifEftvDMaT/iiMmMwQBxAU9WqqyYf96DQfzNG"
            "aV7wlAM6+qWSTmyV/8/mk/8pWFJTWJuwXEnxlafWhXBCJkH4e5upy+0goRhoxlt5Z"
            "PRDSs5zw9CgiBjw1lrB+CYWMEOmNbt+FcbV7lgCGw8QNFl20FNa8r+SCEEwyUyFNb"
            "oPag5zu87WSs5rcwvi/xFrDBBcxCVWj185/tCG/j0ldKr4J71CVs42x+DHqmNvba9"
            "SR1JZ8QpDEIIupRbboNhfB+f64mPcFQRD0bRboF4oKhJBELEVEQabhTkyLYEKVOym"
            "sEbwcRei3wiLPkMpMG7MieR+E+ctRR5MSD49ojD+4GCW6DXkx2ZpR2tH3x"
        ),
        exponent=65537,
    )


class _BrokerDataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class _AgentPolicyProcessBasicInformation(ctypes.Structure):
    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_size_t),
        ("InheritedFromUniqueProcessId", ctypes.c_size_t),
    ]


class _AgentPolicyGuid(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_AGENT_POLICY_ROAMING_APPDATA_GUID = _AgentPolicyGuid(
    0x3EB685DB,
    0x65F9,
    0x4CF6,
    (ctypes.c_ubyte * 8)(0xA0, 0x3A, 0xE3, 0xEF, 0x65, 0x72, 0x9F, 0x3D),
)


def _wipe_agent_policy_buffer(value: Optional[bytearray]) -> None:
    if isinstance(value, bytearray):
        for index in range(len(value)):
            value[index] = 0


def _agent_policy_roaming_appdata_path() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        path = Path(appdata)
        if path.is_absolute():
            return path
    if os.name != "nt":
        raise RuntimeError("The saved FN AI Broker login is unavailable.")

    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_AgentPolicyGuid),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHGetKnownFolderPath.restype = wintypes.LONG
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    allocated = ctypes.c_void_p()
    try:
        result = int(
            shell32.SHGetKnownFolderPath(
                ctypes.byref(_AGENT_POLICY_ROAMING_APPDATA_GUID),
                0,
                None,
                ctypes.byref(allocated),
            )
        )
        if result != 0 or not allocated.value:
            raise RuntimeError("The saved FN AI Broker login is unavailable.")
        resolved = Path(ctypes.wstring_at(allocated.value))
        if not resolved.is_absolute():
            raise RuntimeError("The saved FN AI Broker login is unavailable.")
        return resolved
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("The saved FN AI Broker login is unavailable.") from exc
    finally:
        if allocated.value:
            ole32.CoTaskMemFree(allocated)


def _agent_policy_token_paths() -> tuple[Path, Path]:
    root = _agent_policy_roaming_appdata_path()
    return (
        root / "FNAIBroker" / "access_token_v2.dpapi",
        root / "CompanyAIBroker" / "access_token_v2.dpapi",
    )


def _agent_policy_file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        int(getattr(value, "st_file_attributes", 0)),
    )


def _agent_policy_cross_view_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
        value.st_size, value.st_mtime_ns,
        int(getattr(value, "st_file_attributes", 0)),
    )


def _read_agent_policy_token_blob() -> bytes:
    for path in _agent_policy_token_paths():
        try:
            stream = path.open("rb")
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError("The saved FN AI Broker login is unavailable.") from exc
        try:
            with stream:
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_size <= 0
                    or before.st_size > _AGENT_POLICY_MAX_DPAPI_FILE_BYTES
                    or int(getattr(before, "st_file_attributes", 0))
                    & _AGENT_POLICY_WINDOWS_REPARSE_POINT
                ):
                    raise RuntimeError("The saved FN AI Broker login is unavailable.")
                encoded = stream.read(_AGENT_POLICY_MAX_DPAPI_FILE_BYTES + 1)
                after = os.fstat(stream.fileno())
            current = path.stat()
        except RuntimeError:
            raise
        except OSError as exc:
            raise RuntimeError("The saved FN AI Broker login is unavailable.") from exc
        if (
            _agent_policy_file_identity(before) != _agent_policy_file_identity(after)
            or _agent_policy_cross_view_identity(after)
            != _agent_policy_cross_view_identity(current)
            or not encoded
            or len(encoded) != before.st_size
            or len(encoded) > _AGENT_POLICY_MAX_DPAPI_FILE_BYTES
        ):
            raise RuntimeError("The saved FN AI Broker login is unavailable.")
        return encoded
    raise RuntimeError("FN AI Broker login is required.")


def _agent_policy_dpapi_unprotect(value: bytes) -> bytearray:
    if os.name != "nt" or not value or len(value) > _AGENT_POLICY_MAX_DPAPI_FILE_BYTES:
        raise RuntimeError("The saved FN AI Broker login is unavailable.")
    source_buffer = ctypes.create_string_buffer(value)
    source = _BrokerDataBlob(
        len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    destination = _BrokerDataBlob()
    try:
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 0x1,
            ctypes.byref(destination),
        ):
            raise RuntimeError("The saved FN AI Broker login is unavailable.")
        if (
            not destination.pbData
            or destination.cbData <= 0
            or destination.cbData > _AGENT_POLICY_MAX_DPAPI_PLAINTEXT_BYTES
        ):
            raise RuntimeError("The saved FN AI Broker login is unavailable.")
        return bytearray(ctypes.string_at(destination.pbData, destination.cbData))
    finally:
        if destination.pbData:
            ctypes.windll.kernel32.LocalFree(destination.pbData)


def _load_agent_policy_bearer_token() -> bytearray:
    plaintext: Optional[bytearray] = None
    token: Optional[bytearray] = None
    try:
        plaintext = _agent_policy_dpapi_unprotect(_read_agent_policy_token_blob())
        if not isinstance(plaintext, bytearray):
            raise TypeError("DPAPI plaintext must be mutable")
        start, end = 0, len(plaintext)
        whitespace = frozenset(b" \t\n\r\v\f")
        while start < end and plaintext[start] in whitespace:
            start += 1
        while end > start and plaintext[end - 1] in whitespace:
            end -= 1
        token = bytearray(plaintext[start:end])
        if (
            not token
            or len(token) > _AGENT_POLICY_MAX_BEARER_TOKEN_BYTES
            or any(item not in _AGENT_POLICY_BEARER_TOKEN_BYTES for item in token)
        ):
            raise ValueError("invalid Broker token")
        result, token = token, None
        return result
    except Exception as exc:
        raise RuntimeError("The saved FN AI Broker login is unavailable.") from exc
    finally:
        _wipe_agent_policy_buffer(plaintext)
        _wipe_agent_policy_buffer(token)


def _broker_load_bearer_token_readonly() -> str:
    """Seedance compatibility: reuse the same bounded CurrentUser token loader."""

    token: Optional[bytearray] = None
    try:
        token = _load_agent_policy_bearer_token()
        return token.decode("ascii")
    finally:
        _wipe_agent_policy_buffer(token)


def _agent_policy_exact_windows_path(value: str, expected: Path) -> bool:
    return bool(value and expected.is_absolute()) and os.path.normcase(
        os.path.abspath(value)
    ) == os.path.normcase(os.path.abspath(str(expected)))


def _agent_policy_parent_process_image() -> str:
    if os.name != "nt":
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    kernel32, ntdll = ctypes.windll.kernel32, ctypes.windll.ntdll
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ntdll.NtQueryInformationProcess.argtypes = [
        wintypes.HANDLE,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    ntdll.NtQueryInformationProcess.restype = wintypes.LONG
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    info = _AgentPolicyProcessBasicInformation()
    returned = wintypes.ULONG()
    status = ntdll.NtQueryInformationProcess(
        kernel32.GetCurrentProcess(), 0, ctypes.byref(info), ctypes.sizeof(info),
        ctypes.byref(returned),
    )
    if status != 0 or not info.InheritedFromUniqueProcessId:
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    handle = kernel32.OpenProcess(0x1000, False, int(info.InheritedFromUniqueProcessId))
    if not handle:
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    try:
        image = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(image))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise RuntimeError("HMB Agent launcher provenance is unavailable.")
        return image.value
    finally:
        kernel32.CloseHandle(handle)


def _agent_policy_process_command_line() -> tuple[str, ...]:
    if os.name != "nt":
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    kernel32, shell32 = ctypes.windll.kernel32, ctypes.windll.shell32
    kernel32.GetCommandLineW.argtypes = []
    kernel32.GetCommandLineW.restype = wintypes.LPWSTR
    shell32.CommandLineToArgvW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    command_line = kernel32.GetCommandLineW()
    if not command_line:
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    count = ctypes.c_int()
    arguments = shell32.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not arguments or count.value <= 0:
        raise RuntimeError("HMB Agent launcher provenance is unavailable.")
    try:
        return tuple(arguments[index] for index in range(count.value))
    finally:
        kernel32.LocalFree(ctypes.cast(arguments, wintypes.HLOCAL))


def _agent_policy_process_provenance_valid() -> bool:
    if os.name != "nt":
        _agent_policy_log_stage("provenance_platform_rejected")
        return False
    try:
        # Electron may construct the engine environment without LOCALAPPDATA.
        # Derive the immutable packaged root from the running executable, then
        # verify its exact directory shape, argv and immediate Desktop parent.
        # This is not a relaxed path: copied/arbitrary Python installations do
        # not satisfy the fixed ai.griptape.nodes.desktop/current structure.
        expected_python = Path(sys.executable)
        current = expected_python.parents[3]
        expected_parent = current / "griptape-nodes-desktop.exe"
        arguments = _agent_policy_process_command_line()
        if not (
            current.name.casefold() == "current"
            and current.parent.name.casefold() == "ai.griptape.nodes.desktop"
        ):
            _agent_policy_log_stage("provenance_layout_rejected")
            return False
        if len(arguments) != 3:
            _agent_policy_log_stage("provenance_argv_count_rejected")
            return False
        if not _agent_policy_exact_windows_path(sys.executable, expected_python):
            _agent_policy_log_stage("provenance_executable_rejected")
            return False
        if not _agent_policy_exact_windows_path(arguments[0], expected_python):
            _agent_policy_log_stage("provenance_argv0_rejected")
            return False
        if arguments[1:] != ("-m", "griptape_nodes_app"):
            _agent_policy_log_stage("provenance_arguments_rejected")
            return False
        if not _agent_policy_exact_windows_path(
            _agent_policy_parent_process_image(), expected_parent
        ):
            _agent_policy_log_stage("provenance_parent_rejected")
            return False
        _agent_policy_log_stage("provenance_accepted")
        return True
    except Exception:
        _agent_policy_log_stage("provenance_probe_exception")
        return False


def _agent_policy_path_is_reparse(value: os.stat_result) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        int(getattr(value, "st_file_attributes", 0))
        & _AGENT_POLICY_WINDOWS_REPARSE_POINT
    )


def _agent_policy_ca_path_chain() -> tuple[Path, ...]:
    expected = ROOT / "resources" / "tls" / "hmb_agent_broker_ca.pem"
    if not _agent_policy_exact_windows_path(str(_AGENT_POLICY_BROKER_CA_FILE), expected):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    target, root = Path(os.path.abspath(str(expected))), Path(os.path.abspath(str(ROOT)))
    chain: list[Path] = []
    current = target
    while True:
        chain.append(current)
        if _agent_policy_exact_windows_path(str(current), root):
            return tuple(chain)
        if current.parent == current:
            raise RuntimeError("HMB Agent Broker CA is unavailable.")
        current = current.parent


def _agent_policy_lstat_ca_chain(chain: tuple[Path, ...]) -> tuple[os.stat_result, ...]:
    values: list[os.stat_result] = []
    for index, path in enumerate(chain):
        value = path.lstat()
        if (
            _agent_policy_path_is_reparse(value)
            or (index == 0 and not stat.S_ISREG(value.st_mode))
            or (index != 0 and not stat.S_ISDIR(value.st_mode))
        ):
            raise RuntimeError("HMB Agent Broker CA is unavailable.")
        values.append(value)
    return tuple(values)


def _canonical_agent_policy_ca_pem(encoded: bytes) -> bytes:
    if re.search(rb"\r(?!\n)", encoded) is not None:
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    lf_count, crlf_count = encoded.count(b"\n"), encoded.count(b"\r\n")
    if crlf_count not in (0, lf_count):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    normalized = encoded.replace(b"\r\n", b"\n")
    if not normalized.endswith(b"\n"):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    try:
        normalized.decode("ascii")
    except UnicodeError as exc:
        raise RuntimeError("HMB Agent Broker CA is unavailable.") from exc
    lines = normalized[:-1].split(b"\n")
    if (
        len(lines) < 3
        or lines[0] != b"-----BEGIN CERTIFICATE-----"
        or lines[-1] != b"-----END CERTIFICATE-----"
    ):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    body = lines[1:-1]
    if (
        not body
        or any(
            len(line) != 64
            or re.fullmatch(rb"[A-Za-z0-9+/]{64}", line) is None
            for line in body[:-1]
        )
        or not 4 <= len(body[-1]) <= 64
        or len(body[-1]) % 4 != 0
        or re.fullmatch(rb"[A-Za-z0-9+/]+={0,2}", body[-1]) is None
    ):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    try:
        if not base64.b64decode(b"".join(body), validate=True):
            raise ValueError("empty certificate")
    except (ValueError, TypeError) as exc:
        raise RuntimeError("HMB Agent Broker CA is unavailable.") from exc
    return normalized


def _read_agent_policy_broker_ca_pem() -> bytes:
    try:
        chain = _agent_policy_ca_path_chain()
        before_chain = _agent_policy_lstat_ca_chain(chain)
        before_path = before_chain[0]
        if not 0 < before_path.st_size <= _AGENT_POLICY_MAX_CA_PEM_BYTES:
            raise RuntimeError("HMB Agent Broker CA is unavailable.")
        with chain[0].open("rb") as stream:
            before_handle = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before_handle.st_mode)
                or not 0 < before_handle.st_size <= _AGENT_POLICY_MAX_CA_PEM_BYTES
                or _agent_policy_cross_view_identity(before_handle)
                != _agent_policy_cross_view_identity(before_path)
            ):
                raise RuntimeError("HMB Agent Broker CA is unavailable.")
            encoded = stream.read(_AGENT_POLICY_MAX_CA_PEM_BYTES + 1)
            after_handle = os.fstat(stream.fileno())
        after_chain = _agent_policy_lstat_ca_chain(chain)
    except RuntimeError:
        raise
    except OSError as exc:
        raise RuntimeError("HMB Agent Broker CA is unavailable.") from exc
    if (
        _agent_policy_file_identity(before_handle) != _agent_policy_file_identity(after_handle)
        or tuple(map(_agent_policy_file_identity, before_chain))
        != tuple(map(_agent_policy_file_identity, after_chain))
        or _agent_policy_cross_view_identity(after_handle)
        != _agent_policy_cross_view_identity(after_chain[0])
        or not encoded
        or len(encoded) != before_handle.st_size
        or len(encoded) > _AGENT_POLICY_MAX_CA_PEM_BYTES
    ):
        raise RuntimeError("HMB Agent Broker CA is unavailable.")
    return _canonical_agent_policy_ca_pem(encoded)


def _agent_policy_tls_context() -> ssl.SSLContext:
    ca_pem = _read_agent_policy_broker_ca_pem()
    try:
        ca_text = ca_pem.decode("ascii")
        ca_der = ssl.PEM_cert_to_DER_cert(ca_text)
    except (UnicodeError, ValueError, ssl.SSLError) as exc:
        raise RuntimeError("HMB Agent Broker CA is unavailable.") from exc
    if not hmac.compare_digest(
        hashlib.sha256(ca_der).hexdigest(), _AGENT_POLICY_BROKER_CA_DER_SHA256
    ):
        raise RuntimeError("HMB Agent Broker CA integrity check failed.")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        original_context_super: Optional[super] = None
        # Griptape Desktop globally injects truststore.SSLContext at app start.
        # On Windows, truststore rejects our deliberately self-signed pinned
        # server certificate (CA:FALSE) before the independent DER pin can run.
        # Restore only this private Broker context to the original CPython SSL
        # class; do not mutate Griptape's process-wide SSL configuration.
        if getattr(ssl.SSLContext, "__module__", "") == "truststore._api":
            constants = importlib.import_module("truststore._ssl_constants")
            original_context_type = getattr(constants, "_original_SSLContext", None)
            original_context_super = getattr(
                constants, "_original_super_SSLContext", None
            )
            if (
                not isinstance(original_context_type, type)
                or getattr(original_context_type, "__module__", "") != "ssl"
                or getattr(original_context_type, "__name__", "") != "SSLContext"
                or not isinstance(original_context_super, super)
            ):
                raise RuntimeError("HMB Agent Broker TLS context is unavailable.")
            context = original_context_type(ssl.PROTOCOL_TLS_CLIENT)
            if type(context) is not original_context_type:
                raise RuntimeError("HMB Agent Broker TLS context is unavailable.")
            _agent_policy_log_stage("broker_private_ssl_context_restored")
        if original_context_super is None:
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        else:
            # ssl.py property setters refer to the process-global SSLContext
            # name. After truststore injection that name would recurse, so use
            # the captured original C descriptors for this original instance.
            original_context_super.verify_mode.__set__(context, ssl.CERT_REQUIRED)
            original_context_super.check_hostname.__set__(context, True)
            original_context_super.minimum_version.__set__(
                context, ssl.TLSVersion.TLSv1_2
            )
        context.load_verify_locations(cadata=ca_text)
        return context
    except (OSError, ssl.SSLError) as exc:
        raise RuntimeError("HMB Agent Broker CA is unavailable.") from exc


def _fetch_agent_policy_envelope() -> bytes:
    _agent_policy_log_stage("broker_fetch_enter")
    if (
        _AGENT_POLICY_BROKER_URL
        != "https://192.168.203.245:8443/api/v1/agent-core/dat"
        or _AGENT_POLICY_BROKER_HOST != "192.168.203.245"
        or _AGENT_POLICY_BROKER_PORT != 8443
        or _AGENT_POLICY_BROKER_PATH != "/api/v1/agent-core/dat"
    ):
        raise RuntimeError("HMB Agent policy delivery is unavailable.")
    context = _agent_policy_tls_context()
    _agent_policy_log_stage("broker_tls_context_ready")
    connection = http.client.HTTPSConnection(
        _AGENT_POLICY_BROKER_HOST, _AGENT_POLICY_BROKER_PORT,
        timeout=_AGENT_POLICY_REQUEST_TIMEOUT_SECONDS, context=context,
    )
    token: Optional[bytearray] = None
    authorization: Optional[str] = None
    response: Optional[http.client.HTTPResponse] = None
    try:
        _agent_policy_log_stage("broker_connect_enter")
        try:
            connection.connect()
        except ssl.SSLError:
            _agent_policy_log_stage("broker_connect_tls_failed")
            raise
        except TimeoutError:
            _agent_policy_log_stage("broker_connect_timeout")
            raise
        except OSError as exc:
            winerror = int(getattr(exc, "winerror", 0) or 0)
            if winerror == 10013:
                _agent_policy_log_stage("broker_connect_permission_denied")
            elif winerror == 10061:
                _agent_policy_log_stage("broker_connect_refused")
            elif winerror == 10060:
                _agent_policy_log_stage("broker_connect_timeout")
            else:
                _agent_policy_log_stage("broker_connect_os_failed")
            raise
        except http.client.HTTPException:
            _agent_policy_log_stage("broker_connect_http_failed")
            raise
        _agent_policy_log_stage("broker_connect_ok")
        verified_socket = connection.sock
        peer_der = verified_socket.getpeercert(binary_form=True) if verified_socket else None
        if not peer_der:
            _agent_policy_log_stage("broker_peer_certificate_missing")
            raise RuntimeError("HMB Agent Broker certificate pin mismatch.")
        if not hmac.compare_digest(
            hashlib.sha256(peer_der).hexdigest(), _AGENT_POLICY_BROKER_CA_DER_SHA256
        ):
            _agent_policy_log_stage("broker_peer_pin_mismatch")
            raise RuntimeError("HMB Agent Broker certificate pin mismatch.")
        _agent_policy_log_stage("broker_tls_peer_verified")
        token = _load_agent_policy_bearer_token()
        _agent_policy_log_stage("broker_token_ready")
        authorization = "Bearer " + token.decode("ascii")
        _wipe_agent_policy_buffer(token)
        token = None
        if connection.sock is not verified_socket:
            raise RuntimeError("HMB Agent policy delivery is unavailable.")
        connection.putrequest("GET", _AGENT_POLICY_BROKER_PATH, skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", "192.168.203.245:8443")
        connection.putheader("Accept", "application/octet-stream")
        connection.putheader("Accept-Encoding", "identity")
        connection.putheader("Authorization", authorization)
        connection.putheader("Cache-Control", "no-store")
        connection.endheaders()
        authorization = None
        if connection.sock is not verified_socket:
            raise RuntimeError("HMB Agent policy delivery is unavailable.")
        response = connection.getresponse()
        status = int(getattr(response, "status", 0))
        if status != 200:
            if status == 401:
                _agent_policy_log_stage("broker_http_401")
                raise RuntimeError("FN AI Broker login is required.")
            if status == 403:
                _agent_policy_log_stage("broker_http_403")
                raise RuntimeError("FN AI Broker Agent policy access is denied.")
            if status == 429:
                _agent_policy_log_stage("broker_http_429")
                raise RuntimeError("FN AI Broker Agent policy delivery is busy; retry later.")
            _agent_policy_log_stage("broker_http_other")
            raise RuntimeError("HMB Agent policy delivery is unavailable.")
        _agent_policy_log_stage("broker_http_200")
        names = (
            "Content-Type", "Content-Disposition", "Cache-Control", "Content-Encoding",
            "Content-Length", "Transfer-Encoding", "Accept-Ranges",
            "X-Content-Type-Options", "X-Request-Id",
        )
        values = {name: response.headers.get_all(name, []) for name in names}
        required = (
            "Content-Type", "Content-Disposition", "Cache-Control", "Content-Length",
            "Accept-Ranges", "X-Content-Type-Options", "X-Request-Id",
        )
        vary_values = response.headers.get_all("Vary", [])
        vary_tokens = {
            item.strip().casefold() for value in vary_values
            for item in str(value).split(",") if item.strip()
        }
        if (
            any(len(values[name]) != 1 for name in required)
            or any(len(values[name]) != 0 for name in ("Content-Encoding", "Transfer-Encoding"))
            or len(vary_values) == 0
        ):
            raise RuntimeError("FN AI Broker returned an invalid Agent policy response.")
        _agent_policy_log_stage("broker_headers_verified")
        length_text = str(values["Content-Length"][0]).strip()
        if (
            str(values["Content-Type"][0]).strip().casefold() != "application/octet-stream"
            or str(values["Content-Disposition"][0]).strip()
            != 'attachment; filename="hmb_agent_core.dat"'
            or str(values["Cache-Control"][0]).strip().casefold()
            != "private, no-store, no-transform"
            or str(values["Accept-Ranges"][0]).strip().casefold() != "none"
            or str(values["X-Content-Type-Options"][0]).strip().casefold() != "nosniff"
            or re.fullmatch(r"[0-9a-f]{24}", str(values["X-Request-Id"][0]).strip().casefold()) is None
            or vary_tokens != {"authorization"}
            or re.fullmatch(r"[1-9][0-9]*", length_text) is None
        ):
            raise RuntimeError("FN AI Broker returned an invalid Agent policy response.")
        length = int(length_text)
        if length > _AGENT_POLICY_MAX_ENVELOPE_BYTES:
            raise RuntimeError("FN AI Broker returned an invalid Agent policy response.")
        encoded = response.read(_AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)
        if not encoded or len(encoded) != length:
            raise RuntimeError("FN AI Broker returned an invalid Agent policy response.")
        _agent_policy_log_stage("broker_envelope_received")
        return encoded
    except RuntimeError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise RuntimeError("HMB Agent policy delivery is unavailable.") from exc
    finally:
        if response is not None:
            response.close()
        _wipe_agent_policy_buffer(token)
        token = None
        authorization = None
        request_buffer = getattr(connection, "_buffer", None)
        if isinstance(request_buffer, list):
            request_buffer.clear()
        connection.close()


def _read_agent_policy_envelope() -> bytes:
    """Compatibility name for the one pinned authenticated transport."""
    return _fetch_agent_policy_envelope()


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _strict_json_bytes(encoded: bytes) -> Any:
    text = encoded.decode("utf-8")
    return json.loads(
        text,
        object_pairs_hook=_json_object_without_duplicates,
        parse_constant=_reject_json_constant,
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strict_base64(value: str) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("non-canonical base64")
    return decoded


def _decode_signed_agent_policy_envelope(encoded: bytes) -> Dict[str, Any]:
    if not encoded or len(encoded) > 128 * 1024:
        raise RuntimeError("HMB_GP_Agent_Library policy envelope has an invalid size.")
    try:
        envelope = _strict_json_bytes(encoded)
        if type(envelope) is not dict or encoded != _canonical_json_bytes(envelope):
            raise TypeError("policy envelope must be an object")
        if (
            set(envelope)
            != {
                "schema",
                "algorithm",
                "key_id",
                "payload_sha256",
                "payload",
                "signature",
            }
            or envelope.get("schema") != "hmb-agent-policy-envelope-v3"
            or envelope.get("algorithm") != "RSASSA-PKCS1-v1_5-SHA256"
            or envelope.get("key_id") != "hmb-policy-local-2026-08-r1"
        ):
            raise ValueError("policy envelope identity mismatch")
        payload_hash = envelope.get("payload_sha256")
        if (
            not isinstance(payload_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload_hash)
        ):
            raise ValueError("policy payload digest is missing")
        if not isinstance(envelope.get("payload"), str) or not isinstance(
            envelope.get("signature"), str
        ):
            raise TypeError("policy envelope binary fields must be strings")
        payload_bytes = _strict_base64(envelope["payload"])
        signature = _strict_base64(envelope["signature"])
        if not hmac.compare_digest(hashlib.sha256(payload_bytes).hexdigest(), payload_hash):
            raise ValueError("policy payload digest mismatch")
        if not _verify_agent_policy_signature(payload_bytes, signature):
            raise ValueError("policy signature mismatch")
        decompressor = zlib.decompressobj()
        decompressed = decompressor.decompress(
            payload_bytes,
            512 * 1024 + 1,
        )
        if (
            len(decompressed) > 512 * 1024
            or decompressor.unconsumed_tail
            or not decompressor.eof
            or decompressor.unused_data
        ):
            raise ValueError("policy payload compression boundary mismatch")
        payload = _strict_json_bytes(decompressed)
        if type(payload) is not dict or decompressed != _canonical_json_bytes(payload):
            raise TypeError("signed policy payload must be an object")
        return payload
    except Exception as exc:
        raise RuntimeError(
            "HMB_GP_Agent_Library signed rule payload could not be verified."
        ) from exc


def _validate_agent_policy_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Accept a trusted-signer revision only inside the stable v3 contract."""
    if set(payload) != {
        "schema",
        "policy",
        "policy_sha256",
        "binding",
        "binding_sha256",
        "final_policy_version",
        "final_motion_look_policy_clauses",
        "final_motion_look_policy_sha256",
        "video_appearance_isolation_clauses",
    }:
        raise RuntimeError("HMB_GP_Agent_Library internal rule payload is incomplete.")
    policy = payload.get("policy")
    binding = payload.get("binding")
    final_policy_version = payload.get("final_policy_version")
    final_clause_items = payload.get("final_motion_look_policy_clauses")
    isolation_clause_items = payload.get("video_appearance_isolation_clauses")
    if (
        payload.get("schema") != "hmb-agent-policy-v3"
        or not isinstance(policy, str)
        or not policy
        or policy != policy.strip()
        or not isinstance(binding, str)
        or not binding
        or binding != binding.strip()
        or not isinstance(final_policy_version, str)
        or len(final_policy_version) > 128
        or _AGENT_POLICY_VERSION_PATTERN.fullmatch(final_policy_version) is None
        or not isinstance(final_clause_items, list)
        or not isinstance(isolation_clause_items, list)
        or len(final_clause_items) != len(_AGENT_POLICY_SHARED_MARKERS)
        or len(isolation_clause_items) != 2
        or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in final_clause_items + isolation_clause_items
        )
    ):
        raise RuntimeError("HMB_GP_Agent_Library internal rule payload is incomplete.")
    final_clauses = tuple(final_clause_items)
    isolation_clauses = tuple(isolation_clause_items)
    if (
        tuple(item.split(":", 1)[0] + ":" for item in final_clauses)
        != _AGENT_POLICY_SHARED_MARKERS
        or isolation_clauses != final_clauses[2:4]
    ):
        raise RuntimeError("HMB_GP_Agent_Library internal rule payload is incomplete.")
    expected_policy_hash = payload.get("policy_sha256")
    expected_binding_hash = payload.get("binding_sha256")
    if (
        not isinstance(expected_policy_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_policy_hash)
        or not hmac.compare_digest(
            hashlib.sha256(policy.encode("utf-8")).hexdigest(),
            expected_policy_hash,
        )
    ):
        raise RuntimeError(
            "HMB_GP_Agent_Library internal project rule integrity check failed."
        )
    if (
        not isinstance(expected_binding_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_binding_hash)
        or not hmac.compare_digest(
            hashlib.sha256(binding.encode("utf-8")).hexdigest(),
            expected_binding_hash,
        )
    ):
        raise RuntimeError(
            "HMB_GP_Agent_Library internal shot rule integrity check failed."
        )
    final_block = "\n\n".join(final_clauses)
    expected_final_hash = payload.get("final_motion_look_policy_sha256")
    if (
        not isinstance(expected_final_hash, str)
        or not hmac.compare_digest(
            expected_final_hash,
            _AGENT_POLICY_CONTRACT_SHA256,
        )
        or not hmac.compare_digest(
            hashlib.sha256(final_block.encode("utf-8")).hexdigest(),
            expected_final_hash,
        )
        or not _has_exact_behavior_structure(policy, 1)
        or not _has_exact_behavior_structure(binding, 2)
        or len(final_clauses) != len(set(final_clauses))
        or len(isolation_clauses) != len(set(isolation_clauses))
        or any(policy.count(clause) != 1 for clause in final_clauses)
        or any(binding.count(clause) != 1 for clause in final_clauses)
        or any(clause not in final_clauses for clause in isolation_clauses)
    ):
        raise RuntimeError(
            "HMB_GP_Agent_Library final motion/look policy integrity check failed."
        )
    return {
        "policy": policy,
        "binding": binding,
        "binding_sha256": expected_binding_hash,
        "final_policy_version": final_policy_version,
        "final_motion_look_policy_sha256": expected_final_hash,
        "policy_sha256": expected_policy_hash,
    }


def _has_exact_behavior_structure(document: str, behavior_number: int) -> bool:
    """Require one canonical Behavior header and exactly four non-empty rules."""
    lines = document.splitlines()
    if not lines or lines[0] != f"Behavior {behavior_number}":
        return False
    body = "\n".join(lines[1:]).strip()
    matches = list(
        re.finditer(r"(?m)^(\d+)\. ([A-Z][A-Z0-9_]+)$", body)
    )
    if (
        not matches
        or matches[0].start() != 0
        or [match.group(1) for match in matches] != ["1", "2", "3", "4"]
    ):
        return False
    return all(
        body[
            match.end() : matches[index + 1].start()
            if index + 1 < len(matches)
            else len(body)
        ].strip()
        for index, match in enumerate(matches)
    )


def _fetch_verified_agent_rule_payload() -> Dict[str, Any]:
    """Perform the process's sole authenticated DAT GET and verification."""

    try:
        encoded = bytearray(_fetch_agent_policy_envelope())
    except Exception:
        _agent_policy_log_stage("broker_fetch_failed")
        raise
    try:
        _agent_policy_log_stage("policy_verify_enter")
        validated = _validate_agent_policy_payload(
            _decode_signed_agent_policy_envelope(encoded)
        )
        validated["envelope_sha256"] = hashlib.sha256(encoded).hexdigest()
        _agent_policy_log_stage("policy_verified")
        return validated
    except Exception:
        _agent_policy_log_stage("policy_verify_failed")
        raise
    finally:
        _wipe_agent_policy_buffer(encoded)


def _load_agent_rule_payload() -> Dict[str, Any]:
    """Copy READY state only; Agent execution never performs a policy fetch."""

    try:
        return _agent_process_session.read_ready()
    except Exception as exc:
        raise RuntimeError(
            "HMB_GP_Agent_Library internal rule payload could not be loaded."
        ) from exc


def _bootstrap_agent_policy_session() -> None:
    """Initialize once inside the exact packaged Griptape engine process.

    Exact executable, command-line and parent-process provenance is the sole
    bootstrap authority. An arbitrary Python child cannot initialize the
    session or reach transport.
    """

    _agent_policy_log_stage("bootstrap_enter")
    state = str(_agent_process_session._status_for_regression()[0]).casefold()
    _agent_policy_log_stage(
        f"bootstrap_state_{state}"
        if state in {"empty", "loading", "ready", "failed", "closed"}
        else "bootstrap_state_unknown"
    )
    try:
        # Claim EMPTY -> LOADING using exact packaged-process provenance. The
        # authenticated Broker GET and signature verification then run outside
        # the shared condition so status/READY readers do not freeze behind a
        # 15-second network wait.
        _agent_process_session.bootstrap_once_authorized(
            _agent_policy_process_provenance_valid,
            _fetch_verified_agent_rule_payload,
        )
        _agent_policy_log_stage("session_ready")
    except Exception as exc:
        _agent_policy_log_stage("bootstrap_failed")
        raise RuntimeError("HMB Agent policy session bootstrap failed.") from exc


def _agent_policy_session_state() -> str:
    return str(_agent_process_session._status_for_regression()[0]).upper()


def _shutdown_agent_policy_session() -> None:
    _agent_process_session._expire_for_process_shutdown()


def _load_verified_behavior_documents() -> tuple[str, str]:
    """Return the two documents from the immutable process-scoped snapshot."""
    payload = _load_agent_rule_payload()
    return str(payload["policy"]), str(payload["binding"])


def get_internal_policy_identity() -> Dict[str, str]:
    payload = _load_agent_rule_payload()
    return {
        "version": str(payload["final_policy_version"]),
        "contract_sha256": str(payload["final_motion_look_policy_sha256"]),
        "envelope_sha256": str(payload["envelope_sha256"]),
    }


def _configured_standard_library_root() -> Optional[Path]:
    """Return only the explicitly configured Standard Library package root."""
    explicit = os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", "").strip()
    if not explicit:
        return None
    try:
        configured = Path(explicit).expanduser().resolve(strict=True)
        if configured.is_file():
            if configured.name.casefold() != "agent.py":
                raise ValueError("configured file is not the canonical Agent module")
            configured = configured.parents[2]
        elif configured.name.casefold() == "griptape_nodes_library":
            configured = configured.parent
        agent_file = (
            configured / "griptape_nodes_library" / "agents" / "agent.py"
        ).resolve(strict=True)
        if not agent_file.is_file():
            raise FileNotFoundError(agent_file)
        return configured
    except Exception as exc:
        try:
            print(
                f"{WARN_LOG_PREFIX} Ignoring invalid "
                f"HMB_GRIPTAPE_STANDARD_LIBRARY_PATH: {exc}"
            )
        except Exception:
            pass
        return None


def _validated_registered_standard_library_root(candidate: Path) -> Optional[Path]:
    """Validate a host-reported Standard Library manifest/root and Agent file."""
    try:
        resolved = candidate.expanduser().resolve(strict=True)
        if resolved.is_file():
            manifest_path = resolved
            root = manifest_path.parent
        else:
            root = resolved
            manifest_path = (root / "griptape_nodes_library.json").resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Standard Library root is not a directory")
        if not manifest_path.is_file() or manifest_path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("invalid Standard Library manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("name") != "Griptape Nodes Library":
            raise ValueError("unexpected Standard Library manifest name")
        canonical_relative = "griptape_nodes_library/agents/agent.py"
        if not any(
            isinstance(record, dict)
            and record.get("class_name") == "Agent"
            and str(record.get("file_path") or "").replace("\\", "/")
            == canonical_relative
            for record in manifest.get("nodes", [])
        ):
            raise ValueError("canonical Agent registration is missing")
        agent_file = (root / Path(canonical_relative)).resolve(strict=True)
        agent_file.relative_to(root)
        if not agent_file.is_file():
            raise FileNotFoundError(agent_file)
        return root
    except Exception:
        return None


def _registered_standard_library_root_from_host() -> Optional[Path]:
    """Resolve the Standard Library through Griptape's discovery metadata."""
    try:
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes  # type: ignore
    except Exception:
        return None
    try:
        library_info = GriptapeNodes.LibraryManager().get_library_info_by_library_name(
            "Griptape Nodes Library"
        )
        if library_info is None or not getattr(library_info, "library_path", None):
            return None
        if getattr(library_info, "enabled", True) is False:
            raise ValueError("host Standard Library registration is disabled")
        lifecycle = getattr(library_info, "lifecycle_state", None)
        lifecycle_name = str(getattr(lifecycle, "name", lifecycle) or "").upper()
        if lifecycle_name == "FAILURE":
            raise ValueError("host Standard Library registration failed")
        root = _validated_registered_standard_library_root(
            Path(str(library_info.library_path))
        )
        if root is None:
            raise ValueError("host-reported Standard Library failed validation")
        return root
    except Exception as exc:
        try:
            print(f"{WARN_LOG_PREFIX} Ignoring invalid host Standard Library path: {exc}")
        except Exception:
            pass
        return None


def _is_canonical_agent_module(module: Any, explicit_root: Optional[Path]) -> bool:
    try:
        module_file = Path(str(getattr(module, "__file__", ""))).resolve(strict=True)
        canonical_tail = tuple(
            part.casefold()
            for part in ("griptape_nodes_library", "agents", "agent.py")
        )
        if tuple(part.casefold() for part in module_file.parts[-3:]) != canonical_tail:
            return False
        if explicit_root is not None:
            expected = (
                explicit_root / "griptape_nodes_library" / "agents" / "agent.py"
            ).resolve(strict=True)
            return module_file == expected
        # The HMB library must never satisfy its own Standard Agent dependency.
        try:
            module_file.relative_to(ROOT)
        except ValueError:
            return True
        return False
    except Exception:
        return False


def find_builtin_agent_class() -> Optional[Type[Any]]:
    """Load the canonical registered or explicitly configured Standard Agent."""
    explicit_requested = bool(
        os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH", "").strip()
    )
    explicit_root = _configured_standard_library_root()
    if explicit_requested and explicit_root is None:
        return None
    def is_node_agent_class(candidate: Any) -> bool:
        try:
            if not isinstance(candidate, type) or candidate.__name__ != "Agent":
                return False
            if not (
                hasattr(candidate, "add_parameter")
                or any(
                    hasattr(base, "add_parameter")
                    for base in getattr(candidate, "__mro__", ())
                )
            ):
                return False
            return hasattr(candidate, "process")
        except Exception:
            return False

    def load_from(expected_root: Optional[Path]) -> Optional[Type[Any]]:
        try:
            module = importlib.import_module("griptape_nodes_library.agents.agent")
            candidate = getattr(module, "Agent", None)
            if _is_canonical_agent_module(module, expected_root) and is_node_agent_class(candidate):
                return candidate
        except Exception:
            pass
        return None

    def load_from_registry(expected_root: Optional[Path]) -> Optional[Type[Any]]:
        try:
            from griptape_nodes.node_library.library_registry import LibraryRegistry  # type: ignore

            library = LibraryRegistry.get_library("Griptape Nodes Library")
            candidate = library.get_node_class("Agent")
            module = importlib.import_module(str(candidate.__module__))
            if _is_canonical_agent_module(module, expected_root) and is_node_agent_class(candidate):
                return candidate
        except Exception:
            pass
        return None

    if explicit_root is not None:
        text_path = str(explicit_root)
        if text_path not in sys.path:
            # Explicit configuration is an administrator/user decision. Append it
            # so it cannot shadow already configured host packages at sys.path[0].
            sys.path.append(text_path)
        importlib.invalidate_caches()
        candidate = load_from(explicit_root)
        if candidate is not None:
            return candidate
        try:
            print(
                f"{WARN_LOG_PREFIX} The explicitly configured Standard Agent "
                f"could not be loaded from {explicit_root}."
            )
        except Exception:
            pass
        return None

    registered_root = _registered_standard_library_root_from_host()

    # First honor the exact Agent class already registered by the host.
    candidate = load_from_registry(registered_root)
    if candidate is not None:
        return candidate

    # During startup the manager has metadata for all discovered libraries even
    # when the Standard Library loads after HMB.  Trust only that registered
    # root; never infer a sibling or scan the user's home directory.
    if registered_root is not None:
        text_path = str(registered_root)
        if text_path not in sys.path:
            sys.path.append(text_path)
        importlib.invalidate_caches()
        candidate = load_from(registered_root)
        if candidate is not None:
            try:
                print(
                    f"{PATH_LOG_PREFIX} Loaded the registered Standard Agent "
                    f"from {registered_root}"
                )
            except Exception:
                pass
            return candidate

    try:
        print(
            f"{WARN_LOG_PREFIX} Built-in Griptape Agent node class was not found "
            "at the registered host path. Check the Standard Library or set "
            "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH to its exact package root."
        )
    except Exception:
        pass
    return None


# The signed Agent policy session is opened by HMBAgentLibrary.process() only
# after a canonical HMB Prompt edge has been proven. Importing this shared
# module from Seedance or during library discovery must remain network-free and
# must not turn a transient startup/login race into a process-sticky failure.
