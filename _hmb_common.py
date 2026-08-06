from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import os
import sys
import zlib
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
_BUNDLED_AGENT_POLICY_FILE = (
    ROOT / "resources" / "agent" / "hmb_agent_core.dat"
)
_AGENT_POLICY_MAX_ENVELOPE_BYTES = 128 * 1024
_AGENT_POLICY_MAX_DECOMPRESSED_BYTES = 512 * 1024
PATH_LOG_PREFIX = "[HMB_PRODUCTION][PATH]"
WARN_LOG_PREFIX = "[HMB_PRODUCTION][WARN]"

_AGENT_POLICY_ENVELOPE_SCHEMA = "hmb-agent-policy-envelope-v3"
_AGENT_POLICY_SCHEMA = "hmb-agent-policy-v3"
_AGENT_POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
_AGENT_POLICY_CONTRACT_SHA256 = (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
_AGENT_POLICY_SIGNATURE_ALGORITHM = "RSASSA-PKCS1-v1_5-SHA256"
_AGENT_POLICY_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
_AGENT_POLICY_RSA_MODULUS_B64 = (
    "qxFfkj7CcIH0dsYioONQF7NGo75tSNqj6RxN6rqC72zph7ghqImGb+gQPcdOy3ui"
    "hALs3D2wkcqqw3B9qhp3Or1PLtO7tIyIvMIfjK4uXyzGxirYdF0b/zlxOl5SKsdz"
    "gB+rY9uvKgFEngIc5aSKcEVPebIhv77AGe6/AS39YV7kidShQvQPG9XRAGbm7ca/G"
    "gqXk0kTFnGpx4nsPaQNdv/oh71t1qzQbUSZRpSqzz2/RCXc2So9ywo+l6DY0uuA4"
    "rPj6U/7k4R6pwWyN/xgYDXHcTLXG6iZ8pUIS+4gLLCwyMBYmy3mFGcLif9MLZKZ9"
    "7Rp6cxLixm9X6iaf0vBOt4CvoFTPcqXyl+uJTzRcjD1RnZHBmcDR5toCNIRU4myoN"
    "6gu4M9Xs573/ipfqya2aWYSitCuj0pU/uAvhTcywZGmR3rgS/dZC4fNymykYoiD/t"
    "7isLt+2LE2v8ADkeZszbJLQuh6jyqyINxirwlddIBEIR6rWqmK0qEm9pJ0uvV"
)
_AGENT_POLICY_RSA_EXPONENT = 65537

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
OBJECT_COLOR_PICK_CHOICES = [
    "Sky Blue",
    "Mint",
    "Beige",
    "Direction Checker",
    "Sky Grid",
    "Floor Grid",
    "Position Pattern",
]
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


def image_scope_choices_for_source_type(source_type: Any) -> List[str]:
    """Return a copy of the canonical Sub Type choices for one Main Type."""
    key = str(source_type or "").strip()
    choices = IMAGE_SCOPE_CHOICES_BY_SOURCE_TYPE.get(key, IMAGE_SCOPE_CHOICES)
    return list(choices)


def image_color_pick_choices_for_source_type(source_type: Any) -> List[str]:
    """Return the Video Picker Color Pick candidates allowed by a Main Type."""
    key = str(source_type or "").strip()
    if key in ACTOR_COLOR_PICK_SOURCE_TYPES:
        return list(ACTOR_COLOR_PICK_CHOICES)
    if key in OBJECT_COLOR_PICK_SOURCE_TYPES:
        return list(OBJECT_COLOR_PICK_CHOICES)
    if key == "Custom":
        return list(COLOR_PICK_CHOICES)
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


def _verify_agent_policy_signature(payload_bytes: bytes, signature: bytes) -> bool:
    """Verify a SHA-256 RSA PKCS#1 v1.5 signature using the release public key."""
    try:
        modulus = int.from_bytes(
            base64.b64decode(_AGENT_POLICY_RSA_MODULUS_B64, validate=True),
            "big",
        )
        key_size = (modulus.bit_length() + 7) // 8
        if key_size < 384 or len(signature) != key_size:
            return False
        signature_int = int.from_bytes(signature, "big")
        if signature_int <= 0 or signature_int >= modulus:
            return False
        encoded = pow(
            signature_int,
            _AGENT_POLICY_RSA_EXPONENT,
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


def _read_agent_policy_envelope() -> bytes:
    """Bound the only policy read to the signed file shipped with the library."""
    with _BUNDLED_AGENT_POLICY_FILE.open("rb") as stream:
        encoded = stream.read(_AGENT_POLICY_MAX_ENVELOPE_BYTES + 1)
    if not encoded or len(encoded) > _AGENT_POLICY_MAX_ENVELOPE_BYTES:
        raise RuntimeError("HMB_GP_Agent_Library policy envelope has an invalid size.")
    return encoded


def _decode_signed_agent_policy_envelope(encoded: bytes) -> Dict[str, Any]:
    if not encoded or len(encoded) > _AGENT_POLICY_MAX_ENVELOPE_BYTES:
        raise RuntimeError("HMB_GP_Agent_Library policy envelope has an invalid size.")
    try:
        envelope = json.loads(encoded.decode("utf-8"))
        if not isinstance(envelope, dict):
            raise TypeError("policy envelope must be an object")
        if (
            envelope.get("schema") != _AGENT_POLICY_ENVELOPE_SCHEMA
            or envelope.get("algorithm") != _AGENT_POLICY_SIGNATURE_ALGORITHM
            or envelope.get("key_id") != _AGENT_POLICY_SIGNING_KEY_ID
        ):
            raise ValueError("policy envelope identity mismatch")
        payload_hash = str(envelope.get("payload_sha256", "")).strip().lower()
        if len(payload_hash) != 64:
            raise ValueError("policy payload digest is missing")
        payload_bytes = base64.b64decode(
            str(envelope.get("payload", "")),
            validate=True,
        )
        signature = base64.b64decode(
            str(envelope.get("signature", "")),
            validate=True,
        )
        if not hmac.compare_digest(hashlib.sha256(payload_bytes).hexdigest(), payload_hash):
            raise ValueError("policy payload digest mismatch")
        if not _verify_agent_policy_signature(payload_bytes, signature):
            raise ValueError("policy signature mismatch")
        decompressor = zlib.decompressobj()
        decompressed = decompressor.decompress(
            payload_bytes,
            _AGENT_POLICY_MAX_DECOMPRESSED_BYTES + 1,
        )
        if (
            len(decompressed) > _AGENT_POLICY_MAX_DECOMPRESSED_BYTES
            or decompressor.unconsumed_tail
            or not decompressor.eof
            or decompressor.unused_data
        ):
            raise ValueError("policy payload compression boundary mismatch")
        payload = json.loads(decompressed.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("signed policy payload must be an object")
        return payload
    except Exception as exc:
        raise RuntimeError(
            "HMB_GP_Agent_Library signed rule payload could not be verified."
        ) from exc


def _validate_agent_policy_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the signed policy contract without changing its creative meaning."""
    policy = str(payload.get("policy", "")).strip()
    binding = str(payload.get("binding", "")).strip()
    final_policy_version = str(payload.get("final_policy_version", "")).strip()
    final_clauses = tuple(
        str(item).strip()
        for item in payload.get("final_motion_look_policy_clauses", ())
        if str(item).strip()
    )
    isolation_clauses = tuple(
        str(item).strip()
        for item in payload.get("video_appearance_isolation_clauses", ())
        if str(item).strip()
    )
    if (
        payload.get("schema") != _AGENT_POLICY_SCHEMA
        or not policy
        or not binding
        or final_policy_version != _AGENT_POLICY_VERSION
        or not final_clauses
        or not isolation_clauses
    ):
        raise RuntimeError("HMB_GP_Agent_Library internal rule payload is incomplete.")
    expected_policy_hash = str(payload.get("policy_sha256", "")).strip().lower()
    expected_binding_hash = str(payload.get("binding_sha256", "")).strip().lower()
    if (
        len(expected_policy_hash) != 64
        or hashlib.sha256(policy.encode("utf-8")).hexdigest() != expected_policy_hash
    ):
        raise RuntimeError(
            "HMB_GP_Agent_Library internal project rule integrity check failed."
        )
    if (
        len(expected_binding_hash) != 64
        or hashlib.sha256(binding.encode("utf-8")).hexdigest() != expected_binding_hash
    ):
        raise RuntimeError(
            "HMB_GP_Agent_Library internal shot rule integrity check failed."
        )
    final_block = "\n\n".join(final_clauses)
    expected_final_hash = str(
        payload.get("final_motion_look_policy_sha256", "")
    ).strip().lower()
    if (
        expected_final_hash != _AGENT_POLICY_CONTRACT_SHA256
        or hashlib.sha256(final_block.encode("utf-8")).hexdigest()
        != expected_final_hash
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
        "final_policy_version": final_policy_version,
        "final_motion_look_policy_sha256": expected_final_hash,
    }


def _load_agent_rule_payload() -> Dict[str, Any]:
    """Load, verify, and validate the one policy shipped with the library."""
    try:
        encoded = _read_agent_policy_envelope()
        return _validate_agent_policy_payload(
            _decode_signed_agent_policy_envelope(encoded)
        )
    except Exception as exc:
        raise RuntimeError(
            "HMB_GP_Agent_Library internal rule payload could not be loaded."
        ) from exc


def get_internal_policy_rules() -> str:
    return str(_load_agent_rule_payload()["policy"])


def get_internal_binding_rules() -> str:
    return str(_load_agent_rule_payload()["binding"])


def get_internal_policy_documents() -> tuple[str, str]:
    """Verify once and return the two temporary Behavior documents together."""
    payload = _load_agent_rule_payload()
    return str(payload["policy"]), str(payload["binding"])


def get_internal_policy_identity() -> Dict[str, str]:
    payload = _load_agent_rule_payload()
    return {
        "version": str(payload["final_policy_version"]),
        "contract_sha256": str(payload["final_motion_look_policy_sha256"]),
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
