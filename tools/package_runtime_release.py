from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import tomllib
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE_LABEL = "v0.7.35"
RELEASE_VERSION = "0.7.35"
ARCHIVE_NAME = f"HMB_GP_Production_{RELEASE_LABEL}_Runtime.zip"
ARCHIVE_PATH = DIST / ARCHIVE_NAME
ARCHIVE_ROOT = "HMB_GP_Production"
POLICY_DELIVERY = "bundled-signed-dat"
SHOT_ROUTING_PROTOCOL_VERSION = "2026-08-20.shot-routing.v1"
RELEASE_MANIFEST_PATH = "release-manifest.json"
SHA256SUMS_PATH = "SHA256SUMS"
REPRODUCIBLE_ZIP_MODE = 0o100644
RELEASE_PARITY_PROOF_SCHEMA = "hmb-release-pair-parity"
RELEASE_PARITY_PROOF_VERSION = 1
MAX_NESTED_ARCHIVE_DEPTH = 3
MAX_NESTED_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
STRICT_SEMVER_PATTERN = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
)

RUNTIME_INSTALL_FILES = (
    "__init__.py",
    "griptape-nodes-library.json",
    "HMBAgentLibrary.py",
    "HMBImageAssetLibrary.py",
    "HMBPromptLibrary.py",
    "HMBSeedanceGeneration.py",
    "HMBVideoPickerLibrary.py",
    "_hmb_agent_session.py",
    "_hmb_shot_routing.py",
    "_hmb_mp4_verify.py",
    "_hmb_common.py",
    "_hmb_screen_space.py",
    "widgets/HMBAgentLibraryWidget.js",
    "widgets/HMBImageAssetLibraryWidget.js",
    "widgets/HMBImageAssetThumbnailPatchBridgeWidget.js",
    "widgets/HMBPromptLibraryScopedBindingWidget.js",
    "widgets/HMBSeedanceGenerationWidget.js",
    "widgets/HMBVideoPickerCommandBridgeWidget_v032.js",
    "widgets/HMBVideoPickerLibraryWidget_v032.js",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/picker/HMB_Marker_Catalog.json",
    "resources/agent/hmb_agent_core.dat",
)
DISTRIBUTION_ONLY_FILES = (
    "Install_HMB_GP_Production.ps1",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
)
SOURCE_FILES = (*RUNTIME_INSTALL_FILES, *DISTRIBUTION_ONLY_FILES)
CANONICAL_CRLF_SOURCE_FILES = {
    PurePosixPath("Install_HMB_GP_Production.ps1"),
}
if len(RUNTIME_INSTALL_FILES) != 22 or len(DISTRIBUTION_ONLY_FILES) != 4:
    raise RuntimeError("Runtime/distribution release boundary count mismatch.")
if set(RUNTIME_INSTALL_FILES) & set(DISTRIBUTION_ONLY_FILES):
    raise RuntimeError("Runtime and distribution-only release files overlap.")
EXPECTED_SECRET_NAMES = {
    "GT_CLOUD_API_KEY",
    "GT_CLOUD_BUCKET_ID",
    "TOS_ACCESS_KEY_ID",
    "TOS_SECRET_ACCESS_KEY",
    "TOS_BUCKET_NAME",
}
FORBIDDEN_SUFFIXES = {
    ".dat",
    ".env",
    ".jwk",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".secret",
    ".token",
}
FORBIDDEN_RELEASE_CONTENT_MARKERS = (
    b"resources/policy/HMB_GP_Production_Rule",
)
# A policy source must be rejected by filename even when an adversarial nested
# archive omits the usual ``resources/policy`` or ``policies`` directory. This
# deliberately covers English canonical names as well as local Korean reviews.
POLICY_DOCUMENT_NAME = re.compile(r"(?i)polic(?:y|ies)")
PRIVATE_KEY_HEADER = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
BUNDLED_AGENT_POLICY_MEMBER = PurePosixPath("resources/agent/hmb_agent_core.dat")
AGENT_POLICY_SOURCE_ENV = "HMB_AGENT_POLICY_SOURCE_PATH"
DEFAULT_AGENT_POLICY_SOURCE = Path(
    r"D:\AI\HMB_Agent_Core_Manager\build\hmb_agent_core.dat"
)
COMMON_TOKEN_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
)
STANDARD_AGENT_LIBRARY_ENV = "HMB_GRIPTAPE_STANDARD_LIBRARY_PATH"
STANDARD_AGENT_MANIFEST_NAME = "griptape_nodes_library.json"
STANDARD_AGENT_MODEL_CATALOG_SHA256 = (
    "7ce86d43b7039126a51d433d72563aefc7bec3aaf86a5a3f88f362da987e39ed"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_signed_agent_policy_bytes(encoded: bytes) -> dict[str, str]:
    """Verify the bundled policy with the same production trust implementation."""

    module_path = ROOT / "_hmb_common.py"
    spec = importlib.util.spec_from_file_location(
        "_hmb_release_policy_verifier", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Production Agent policy verifier is unavailable.")
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    payload = common._validate_agent_policy_payload(
        common._decode_signed_agent_policy_envelope(encoded)
    )
    return {
        "envelope_sha256": digest(encoded),
        "final_policy_version": str(payload["final_policy_version"]),
        "policy_pair_sha256": str(payload["policy_pair_sha256"]),
    }


def synchronize_bundled_agent_policy() -> dict[str, str]:
    """Mirror the approved Manager build DAT into the runtime package.

    Developer builds use the canonical Manager output (or the explicit CI
    override). Public/isolated validation may use the already mirrored DAT
    when that external build tree is unavailable. In both cases the exact
    production RSA verifier runs before packaging.
    """

    override = os.environ.get(AGENT_POLICY_SOURCE_ENV, "").strip()
    source = Path(override) if override else DEFAULT_AGENT_POLICY_SOURCE
    destination = ROOT / Path(BUNDLED_AGENT_POLICY_MEMBER.as_posix())
    encoded: bytes
    if source.exists():
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("Canonical Agent policy source is invalid.")
        encoded = source.read_bytes()
        if not encoded or len(encoded) > 128 * 1024:
            raise RuntimeError("Canonical Agent policy source has an invalid size.")
        verify_signed_agent_policy_bytes(encoded)
        destination.parent.mkdir(parents=True, exist_ok=True)
        current = destination.read_bytes() if destination.is_file() else None
        if current != encoded:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=destination.name + ".",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
    else:
        if not destination.is_file() or destination.is_symlink():
            raise RuntimeError(
                "Canonical Agent policy source and bundled fallback are unavailable."
            )
        encoded = destination.read_bytes()
    if (
        not destination.is_file()
        or destination.is_symlink()
        or destination.read_bytes() != encoded
    ):
        raise RuntimeError("Bundled Agent policy mirror is invalid.")
    return verify_signed_agent_policy_bytes(encoded)


def canonical_release_source_data(member: PurePosixPath, data: bytes) -> bytes:
    """Make audited Windows text payloads checkout-independent."""

    if member not in CANONICAL_CRLF_SOURCE_FILES:
        return data
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return normalized.replace(b"\n", b"\r\n")


def release_version_parts(release_version: str) -> tuple[int, int, int]:
    """Parse the exact Griptape-compatible technical SemVer triplet."""

    match = STRICT_SEMVER_PATTERN.fullmatch(release_version)
    if match is None:
        raise RuntimeError(
            "Technical release version must be strict major.minor.patch SemVer "
            "without leading zeroes."
        )
    return tuple(int(part) for part in match.groups())


def release_label_for_version(release_version: str) -> str:
    """Return the public label, padding only a one-digit technical patch."""

    major, minor, patch = release_version_parts(release_version)
    return f"v{major}.{minor}.{patch:02d}"


def validate_release_identity(
    release_label: str = RELEASE_LABEL,
    release_version: str = RELEASE_VERSION,
) -> None:
    expected_label = release_label_for_version(release_version)
    if release_label != expected_label:
        raise RuntimeError(
            "Public release label does not match the approved technical SemVer: "
            f"expected {expected_label}, got {release_label}."
        )


def module_string_constant(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            raise RuntimeError(f"{name} must be a string literal in {path.name}.")
        matches.append(value.value)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} assignment in {path.name}.")
    return matches[0]


def node_model_usage_ids(
    library_manifest: dict[str, Any],
    class_name: str,
) -> tuple[str, ...]:
    """Return one node's exact, unique model-usage declaration."""

    nodes = library_manifest.get("nodes")
    if not isinstance(nodes, list):
        raise RuntimeError("Library node declarations are missing or invalid.")
    matches = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("class_name") == class_name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {class_name} node declaration.")
    metadata = matches[0].get("metadata")
    declarations = metadata.get("declarations") if isinstance(metadata, dict) else None
    usages = [
        item
        for item in declarations if isinstance(item, dict) and item.get("type") == "model_usage"
    ] if isinstance(declarations, list) else []
    if len(usages) != 1:
        raise RuntimeError(f"Expected one {class_name} model-usage declaration.")
    raw_ids = usages[0].get("model_ids")
    if (
        not isinstance(raw_ids, list)
        or not raw_ids
        or any(not isinstance(item, str) or not item.strip() for item in raw_ids)
        or len(raw_ids) != len(set(raw_ids))
    ):
        raise RuntimeError(f"{class_name} model-usage declaration is invalid.")
    return tuple(raw_ids)


def library_model_catalog_providers(
    library_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Return the sole library model catalog's provider mapping."""

    metadata = library_manifest.get("metadata")
    declarations = metadata.get("declarations") if isinstance(metadata, dict) else None
    catalogs = [
        item
        for item in declarations if isinstance(item, dict) and item.get("type") == "model_catalog"
    ] if isinstance(declarations, list) else []
    if len(catalogs) != 1:
        raise RuntimeError("Expected one library model catalog declaration.")
    providers = catalogs[0].get("providers")
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError("Library model catalog providers are missing or invalid.")
    return providers


def library_model_catalog_ids(
    library_manifest: dict[str, Any],
) -> tuple[str, ...]:
    """Return the exact unique model ids declared by this library's catalog."""

    providers = library_model_catalog_providers(library_manifest)
    ids: list[str] = []
    for provider in providers.values():
        models = provider.get("models") if isinstance(provider, dict) else None
        if not isinstance(models, dict) or not models:
            raise RuntimeError("Library model catalog provider is missing models.")
        ids.extend(str(model_id) for model_id in models)
    if any(not model_id.strip() for model_id in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("Library model catalog contains invalid or duplicate ids.")
    return tuple(ids)


def library_model_catalog_contract_sha256(
    library_manifest: dict[str, Any],
) -> str:
    """Hash every provider and model field in the pinned Agent catalog subset."""

    providers = library_model_catalog_providers(library_manifest)
    canonical = json.dumps(
        providers,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return digest(canonical)


def standard_agent_manifest_candidates() -> tuple[Path, ...]:
    """Return explicit and conventional installed Standard Agent manifests."""

    candidates: list[Path] = []
    configured = str(os.environ.get(STANDARD_AGENT_LIBRARY_ENV, "") or "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.suffix.casefold() == ".json":
            candidates.append(configured_path)
        elif configured_path.name.casefold() == "agent.py":
            candidates.append(configured_path.parents[2] / STANDARD_AGENT_MANIFEST_NAME)
        elif configured_path.name.casefold() == "griptape_nodes_library":
            candidates.append(configured_path.parent / STANDARD_AGENT_MANIFEST_NAME)
        else:
            candidates.append(configured_path / STANDARD_AGENT_MANIFEST_NAME)
    candidates.append(
        Path.home()
        / "Documents"
        / "GriptapeNodes"
        / "libraries"
        / "griptape-nodes-library-standard"
        / STANDARD_AGENT_MANIFEST_NAME
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return tuple(unique)


def validate_standard_agent_model_parity(
    library_manifest: dict[str, Any],
) -> Path | None:
    """Keep HMB's host declaration equal to the installed stock Agent surface.

    ``model_usage`` is the Griptape permission/accounting declaration required
    before a model call; it is not an HMB content allowlist.  Public CI may not
    have the Standard Library checkout, so the HMB declaration is always
    validated for shape and uniqueness, and exact stock parity is additionally
    enforced whenever the canonical installed manifest is available.
    """

    hmb_ids = node_model_usage_ids(library_manifest, "HMBAgentLibrary")
    catalog_ids = library_model_catalog_ids(library_manifest)
    catalog_contract_sha256 = library_model_catalog_contract_sha256(library_manifest)
    if catalog_contract_sha256 != STANDARD_AGENT_MODEL_CATALOG_SHA256:
        raise RuntimeError(
            "HMBAgentLibrary pinned Standard Agent model catalog contract changed "
            f"({catalog_contract_sha256})."
        )
    if set(hmb_ids) != set(catalog_ids):
        unresolved = sorted(set(hmb_ids) - set(catalog_ids))
        unused = sorted(set(catalog_ids) - set(hmb_ids))
        raise RuntimeError(
            "HMBAgentLibrary model usage does not resolve inside its own catalog "
            f"(unresolved={unresolved}, unused={unused})."
        )
    for candidate in standard_agent_manifest_candidates():
        if not candidate.is_file():
            continue
        try:
            standard_manifest = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Installed Standard Agent manifest is invalid: {candidate}"
            ) from exc
        standard_ids = node_model_usage_ids(standard_manifest, "Agent")
        if hmb_ids != standard_ids:
            missing = sorted(set(standard_ids) - set(hmb_ids))
            extra = sorted(set(hmb_ids) - set(standard_ids))
            raise RuntimeError(
                "HMBAgentLibrary model declaration differs from the installed "
                f"Standard Agent (missing={missing}, extra={extra})."
            )
        hmb_providers = library_model_catalog_providers(library_manifest)
        standard_providers = library_model_catalog_providers(standard_manifest)
        for provider_id, hmb_provider in hmb_providers.items():
            standard_provider = standard_providers.get(provider_id)
            if not isinstance(hmb_provider, dict) or not isinstance(standard_provider, dict):
                raise RuntimeError(
                    f"Standard Agent model provider mismatch: {provider_id}."
                )
            hmb_provider_metadata = {
                key: value for key, value in hmb_provider.items() if key != "models"
            }
            standard_provider_metadata = {
                key: value for key, value in standard_provider.items() if key != "models"
            }
            if hmb_provider_metadata != standard_provider_metadata:
                raise RuntimeError(
                    f"Standard Agent model provider metadata mismatch: {provider_id}."
                )
            hmb_models = hmb_provider.get("models")
            standard_models = standard_provider.get("models")
            if not isinstance(hmb_models, dict) or not isinstance(standard_models, dict):
                raise RuntimeError(
                    f"Standard Agent model provider payload mismatch: {provider_id}."
                )
            for model_id, hmb_model in hmb_models.items():
                if standard_models.get(model_id) != hmb_model:
                    raise RuntimeError(
                        "Standard Agent model catalog field mismatch: "
                        f"{provider_id}/{model_id}."
                    )
        return candidate
    return None


def assert_release_member_allowed(member: PurePosixPath) -> None:
    """Allow only the signed runtime DAT; reject all other policy artifacts."""

    relative = member.as_posix()
    lowered_parts = tuple(part.casefold() for part in member.parts)
    lowered_pairs = set(zip(lowered_parts, lowered_parts[1:]))
    if member.is_absolute() or ".." in member.parts or "\\" in relative:
        raise RuntimeError(f"Unsafe runtime release path: {relative}")
    is_bundled_agent_policy = tuple(
        part.casefold() for part in member.parts[-3:]
    ) == tuple(
        part.casefold() for part in BUNDLED_AGENT_POLICY_MEMBER.parts
    )
    if (
        member.suffix.casefold() in FORBIDDEN_SUFFIXES
        and not is_bundled_agent_policy
    ):
        raise RuntimeError(f"Forbidden runtime release member: {relative}")
    if (
        (("resources", "agent") in lowered_pairs and not is_bundled_agent_policy)
        or ("resources", "policy") in lowered_pairs
        or "policy" in lowered_parts
        or "policies" in lowered_parts
        or POLICY_DOCUMENT_NAME.search(member.name) is not None
    ):
        raise RuntimeError(f"Policy material must remain outside the release: {relative}")


def validate_no_policy_artifacts_in_zip(
    encoded: bytes,
    *,
    label: str = "release archive",
    depth: int = 0,
) -> None:
    """Allow the signed runtime DAT and reject every other policy artifact."""

    if not encoded or len(encoded) > MAX_NESTED_ARCHIVE_BYTES:
        raise RuntimeError(f"{label} has an invalid size.")
    try:
        with zipfile.ZipFile(io.BytesIO(encoded), "r") as archive:
            infos = archive.infolist()
            if (
                len(infos) > MAX_ARCHIVE_MEMBERS
                or sum(info.file_size for info in infos)
                > MAX_ARCHIVE_UNCOMPRESSED_BYTES
            ):
                raise RuntimeError(f"{label} member boundary mismatch.")
            for info in infos:
                member = PurePosixPath(info.filename)
                assert_release_member_allowed(member)
                if info.is_dir():
                    continue
                if info.file_size > MAX_NESTED_ARCHIVE_BYTES:
                    raise RuntimeError(f"{label} member is too large: {info.filename}")
                is_bundled_agent_policy = tuple(
                    part.casefold() for part in member.parts[-3:]
                ) == tuple(
                    part.casefold() for part in BUNDLED_AGENT_POLICY_MEMBER.parts
                )
                if is_bundled_agent_policy:
                    verify_signed_agent_policy_bytes(archive.read(info))
                    continue
                if member.suffix.casefold() != ".zip":
                    continue
                if depth >= MAX_NESTED_ARCHIVE_DEPTH:
                    raise RuntimeError(f"Nested ZIP depth exceeded in {label}.")
                validate_no_policy_artifacts_in_zip(
                    archive.read(info),
                    label=f"{label}::{info.filename}",
                    depth=depth + 1,
                )
            if archive.testzip() is not None:
                raise RuntimeError(f"{label} member boundary mismatch.")
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{label} is not a valid ZIP archive.") from exc


def validate_sources() -> tuple[str, list[dict[str, Any]]]:
    policy_identity = synchronize_bundled_agent_policy()
    validate_release_identity()
    library_manifest = json.loads(
        (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
    )
    release_version = str(
        library_manifest.get("metadata", {}).get("library_version", "")
    ).strip()
    if not release_version:
        raise RuntimeError("Library release version is missing.")
    if release_version != RELEASE_VERSION:
        raise RuntimeError(
            "Library release version does not match the approved technical version."
        )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if str(project.get("project", {}).get("version", "")).strip() != release_version:
        raise RuntimeError("Manifest and package release versions differ.")
    sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
    sbom_package = next(
        (
            item
            for item in sbom.get("packages", [])
            if item.get("SPDXID") == "SPDXRef-HMB-GP-Production"
        ),
        None,
    )
    expected_sbom_name = f"HMB_GP_Production-{release_version}"
    expected_sbom_namespace = (
        f"https://hmb.local/spdx/HMB_GP_Production/{release_version}"
    )
    if (
        sbom.get("name") != expected_sbom_name
        or sbom.get("documentNamespace") != expected_sbom_namespace
        or not isinstance(sbom_package, dict)
        or sbom_package.get("versionInfo") != release_version
    ):
        raise RuntimeError("SBOM and technical release versions differ.")
    if module_string_constant(
        ROOT / "_hmb_shot_routing.py", "SHOT_ROUTING_PROTOCOL_VERSION"
    ) != SHOT_ROUTING_PROTOCOL_VERSION:
        raise RuntimeError("Shot-routing protocol and release bundle identities differ.")
    registered_secrets = library_manifest["settings"][0]["contents"][
        "secrets_to_register"
    ]
    if set(registered_secrets) != EXPECTED_SECRET_NAMES or any(
        value != "" for value in registered_secrets.values()
    ):
        raise RuntimeError("Library secret registration boundary mismatch.")
    validate_standard_agent_model_parity(library_manifest)
    delivery = library_manifest.get("metadata", {}).get("agent_policy_delivery", {})
    if (
        not isinstance(delivery, dict)
        or delivery.get("archive_source_count") != len(SOURCE_FILES)
        or delivery.get("mode") != "bundled_signed_dat"
        or delivery.get("runtime_path") != BUNDLED_AGENT_POLICY_MEMBER.as_posix()
        or delivery.get("policy_version")
        != policy_identity["final_policy_version"]
        or delivery.get("envelope_sha256")
        != policy_identity["envelope_sha256"]
        or delivery.get("contract_sha256")
        != policy_identity["policy_pair_sha256"]
        or delivery.get("verification")
        != "rsa3072_sha256_v3_contract_once_per_process"
    ):
        raise RuntimeError("Bundled Agent policy delivery metadata mismatch.")

    declared_widget_paths = {
        str(item.get("path") or "").strip()
        for item in library_manifest.get("widgets", [])
        if isinstance(item, dict)
    }
    if "" in declared_widget_paths or not declared_widget_paths:
        raise RuntimeError("Library widget declarations are missing or invalid.")
    omitted_widgets = declared_widget_paths - set(RUNTIME_INSTALL_FILES)
    if omitted_widgets:
        raise RuntimeError(
            "Runtime release omits declared widgets: "
            + ", ".join(sorted(omitted_widgets))
        )

    records: list[dict[str, Any]] = []
    for relative in SOURCE_FILES:
        member = PurePosixPath(relative)
        assert_release_member_allowed(member)
        path = ROOT / Path(relative)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Missing or linked runtime release member: {relative}")
        data = canonical_release_source_data(member, path.read_bytes())
        if member == BUNDLED_AGENT_POLICY_MEMBER:
            verified = verify_signed_agent_policy_bytes(data)
            if verified != policy_identity:
                raise RuntimeError("Bundled Agent policy identity mismatch.")
        if PRIVATE_KEY_HEADER.search(data) is not None:
            raise RuntimeError(f"Private signing key material remains in {relative}")
        if any(pattern.search(data) for pattern in COMMON_TOKEN_PATTERNS):
            raise RuntimeError(f"Credential-like token remains in {relative}")
        if any(marker in data for marker in FORBIDDEN_RELEASE_CONTENT_MARKERS):
            raise RuntimeError(
                f"Package-local or private policy reference remains in {relative}"
            )
        if member.suffix.casefold() == ".zip":
            validate_no_policy_artifacts_in_zip(
                data,
                label=f"runtime source::{relative}",
            )
        records.append(
            {
                "bytes": len(data),
                "data": data,
                "install": relative in RUNTIME_INSTALL_FILES,
                "path": relative,
                "sha256": digest(data),
            }
        )
    return release_version, records


def make_release_records(
    release_version: str,
    source_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append a deterministic release manifest and checksum inventory."""

    release_label = release_label_for_version(release_version)

    source_inventory = [
        {
            "bytes": int(record["bytes"]),
            "install": record["install"],
            "path": str(record["path"]),
            "sha256": str(record["sha256"]),
        }
        for record in source_records
    ]
    manifest = {
        "bundle_id": f"hmb-gp-production/{release_version}",
        "distribution_file_count": len(DISTRIBUTION_ONLY_FILES),
        "file_count": len(source_inventory),
        "files": source_inventory,
        "install_file_count": len(RUNTIME_INSTALL_FILES),
        "library": "HMB_GP_Production",
        "release_label": release_label,
        "release_version": release_version,
        "schema": "hmb-release-closure",
        "shot_routing_protocol": SHOT_ROUTING_PROTOCOL_VERSION,
        "version": 1,
    }
    manifest_data = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest_record = {
        "bytes": len(manifest_data),
        "data": manifest_data,
        "path": RELEASE_MANIFEST_PATH,
        "sha256": digest(manifest_data),
    }
    checksummed_records = [*source_records, manifest_record]
    checksum_data = (
        "".join(
            f'{record["sha256"]}  {record["path"]}\n'
            for record in checksummed_records
        )
    ).encode("utf-8")
    checksum_record = {
        "bytes": len(checksum_data),
        "data": checksum_data,
        "path": SHA256SUMS_PATH,
        "sha256": digest(checksum_data),
    }
    return [*checksummed_records, checksum_record]


def validate_release_inventory(
    release_version: str,
    records: list[dict[str, Any]],
) -> None:
    release_label = release_label_for_version(release_version)
    by_path = {str(record["path"]): record for record in records}
    if set((RELEASE_MANIFEST_PATH, SHA256SUMS_PATH)) - set(by_path):
        raise RuntimeError("Runtime release closure inventory is missing.")
    manifest = json.loads(by_path[RELEASE_MANIFEST_PATH]["data"].decode("utf-8"))
    source_paths = [str(path) for path in SOURCE_FILES]
    manifest_paths = [str(item.get("path") or "") for item in manifest.get("files", [])]
    manifest_install_flags = [item.get("install") for item in manifest.get("files", [])]
    expected_install_flags = [path in RUNTIME_INSTALL_FILES for path in SOURCE_FILES]
    if (
        manifest.get("schema") != "hmb-release-closure"
        or manifest.get("version") != 1
        or manifest.get("release_label") != release_label
        or manifest.get("release_version") != release_version
        or manifest.get("shot_routing_protocol") != SHOT_ROUTING_PROTOCOL_VERSION
        or manifest.get("file_count") != len(SOURCE_FILES)
        or manifest.get("install_file_count") != len(RUNTIME_INSTALL_FILES)
        or manifest.get("distribution_file_count") != len(DISTRIBUTION_ONLY_FILES)
        or manifest_paths != source_paths
        or manifest_install_flags != expected_install_flags
        or any(type(flag) is not bool for flag in manifest_install_flags)
    ):
        raise RuntimeError("Runtime release closure manifest is inconsistent.")
    for item in manifest["files"]:
        record = by_path.get(str(item["path"]))
        if (
            not record
            or int(item.get("bytes", -1)) != int(record["bytes"])
            or item.get("install") is not record.get("install")
            or str(item.get("sha256") or "") != str(record["sha256"])
        ):
            raise RuntimeError(f'Runtime release manifest mismatch: {item["path"]}')
    checksum_lines = by_path[SHA256SUMS_PATH]["data"].decode("utf-8").splitlines()
    expected_lines = [
        f'{record["sha256"]}  {record["path"]}'
        for record in records
        if str(record["path"]) != SHA256SUMS_PATH
    ]
    if checksum_lines != expected_lines:
        raise RuntimeError("Runtime release checksum inventory is inconsistent.")


def parity_normalized_source_data(relative: str, data: bytes) -> bytes:
    """Normalize only the approved odd/even release-version metadata."""

    data = canonical_release_source_data(PurePosixPath(relative), data)
    if relative == "griptape-nodes-library.json":
        payload = json.loads(data.decode("utf-8"))
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("library_version"), str
        ):
            raise RuntimeError("Parity manifest version field is missing.")
        metadata["library_version"] = "<VERSION>"
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    if relative == "SBOM.spdx.json":
        payload = json.loads(data.decode("utf-8"))
        packages = payload.get("packages")
        if not isinstance(packages, list):
            raise RuntimeError("Parity SBOM package inventory is missing.")
        package = next(
            (
                item
                for item in packages
                if isinstance(item, dict)
                and item.get("SPDXID") == "SPDXRef-HMB-GP-Production"
            ),
            None,
        )
        if not isinstance(package, dict):
            raise RuntimeError("Parity SBOM HMB package is missing.")
        payload["name"] = "HMB_GP_Production-<VERSION>"
        payload["documentNamespace"] = (
            "https://hmb.local/spdx/HMB_GP_Production/<VERSION>"
        )
        package["versionInfo"] = "<VERSION>"
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    return data


def canonical_source_fingerprint(source_records: list[dict[str, Any]]) -> str:
    """Hash the installed/distributed behavior surface with versions masked."""

    by_path = {
        str(record["path"]): bytes(record["data"])
        for record in source_records
    }
    expected_paths = [str(path) for path in SOURCE_FILES]
    if set(by_path) != set(expected_paths):
        raise RuntimeError("Release parity fingerprint source inventory differs.")
    state = hashlib.sha256()
    for relative in expected_paths:
        path_bytes = relative.encode("utf-8")
        data = parity_normalized_source_data(relative, by_path[relative])
        state.update(len(path_bytes).to_bytes(4, "big"))
        state.update(path_bytes)
        state.update(len(data).to_bytes(8, "big"))
        state.update(data)
    return state.hexdigest()


def read_validated_release_archive(encoded: bytes) -> tuple[str, dict[str, bytes]]:
    """Validate and read an audited release without assuming its version."""

    validate_no_policy_artifacts_in_zip(encoded, label="release parity reference")
    expected_paths = [
        *(str(path) for path in SOURCE_FILES),
        RELEASE_MANIFEST_PATH,
        SHA256SUMS_PATH,
    ]
    expected_members = {f"{ARCHIVE_ROOT}/{path}" for path in expected_paths}
    with zipfile.ZipFile(io.BytesIO(encoded), "r") as archive:
        infos = archive.infolist()
        if archive.testzip() is not None:
            raise RuntimeError("Release parity reference ZIP is corrupt.")
        member_names = [info.filename for info in infos]
        if len(member_names) != len(set(member_names)) or set(member_names) != expected_members:
            raise RuntimeError("Release parity reference member boundary mismatch.")
        date_times = {info.date_time for info in infos}
        if len(date_times) != 1:
            raise RuntimeError("Release parity reference timestamps are inconsistent.")
        contents = {
            PurePosixPath(*PurePosixPath(info.filename).parts[1:]).as_posix(): archive.read(info)
            for info in infos
        }

    manifest = json.loads(contents[RELEASE_MANIFEST_PATH].decode("utf-8"))
    reference_version = str(manifest.get("release_version") or "")
    reference_label = str(manifest.get("release_label") or "")
    validate_release_identity(reference_label, reference_version)
    source_paths = [str(path) for path in SOURCE_FILES]
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        raise RuntimeError("Release parity reference inventory is missing.")
    manifest_paths = [str(item.get("path") or "") for item in manifest_files]
    manifest_install_flags = [item.get("install") for item in manifest_files]
    expected_install_flags = [path in RUNTIME_INSTALL_FILES for path in SOURCE_FILES]
    if (
        manifest.get("schema") != "hmb-release-closure"
        or manifest.get("version") != 1
        or manifest.get("file_count") != len(SOURCE_FILES)
        or manifest.get("install_file_count") != len(RUNTIME_INSTALL_FILES)
        or manifest.get("distribution_file_count") != len(DISTRIBUTION_ONLY_FILES)
        or manifest.get("shot_routing_protocol") != SHOT_ROUTING_PROTOCOL_VERSION
        or manifest_paths != source_paths
        or manifest_install_flags != expected_install_flags
        or any(type(flag) is not bool for flag in manifest_install_flags)
    ):
        raise RuntimeError("Release parity reference manifest is inconsistent.")
    for item in manifest_files:
        relative = str(item["path"])
        data = contents.get(relative)
        if (
            data is None
            or int(item.get("bytes", -1)) != len(data)
            or str(item.get("sha256") or "") != digest(data)
        ):
            raise RuntimeError(f"Release parity reference hash mismatch: {relative}")
    checksum_lines = contents[SHA256SUMS_PATH].decode("utf-8").splitlines()
    expected_checksum_lines = [
        *(f"{digest(contents[path])}  {path}" for path in source_paths),
        f"{digest(contents[RELEASE_MANIFEST_PATH])}  {RELEASE_MANIFEST_PATH}",
    ]
    if checksum_lines != expected_checksum_lines:
        raise RuntimeError("Release parity reference checksum inventory is inconsistent.")

    library_manifest = json.loads(contents["griptape-nodes-library.json"].decode("utf-8"))
    if library_manifest.get("metadata", {}).get("library_version") != reference_version:
        raise RuntimeError("Release parity reference library version is inconsistent.")
    sbom = json.loads(contents["SBOM.spdx.json"].decode("utf-8"))
    sbom_package = next(
        (
            item
            for item in sbom.get("packages", [])
            if isinstance(item, dict)
            and item.get("SPDXID") == "SPDXRef-HMB-GP-Production"
        ),
        None,
    )
    if (
        sbom.get("name") != f"HMB_GP_Production-{reference_version}"
        or sbom.get("documentNamespace")
        != f"https://hmb.local/spdx/HMB_GP_Production/{reference_version}"
        or not isinstance(sbom_package, dict)
        or sbom_package.get("versionInfo") != reference_version
    ):
        raise RuntimeError("Release parity reference SBOM version is inconsistent.")
    return reference_version, {path: contents[path] for path in source_paths}


def validate_release_pair_parity(
    reference_encoded: bytes,
    current_release_version: str,
    current_source_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require adjacent odd/even releases to differ only by version metadata."""

    reference_version, reference_sources = read_validated_release_archive(
        reference_encoded
    )
    reference_parts = release_version_parts(reference_version)
    current_parts = release_version_parts(current_release_version)
    if (
        current_parts[:2] != reference_parts[:2]
        or current_parts[2] != reference_parts[2] + 1
    ):
        raise RuntimeError(
            "Release parity requires the immediately preceding technical version."
        )
    current_sources = {
        str(record["path"]): bytes(record["data"])
        for record in current_source_records
    }
    if set(current_sources) != set(reference_sources):
        raise RuntimeError("Release parity source inventory differs.")
    mismatches = [
        relative
        for relative in SOURCE_FILES
        if parity_normalized_source_data(
            str(relative), reference_sources[str(relative)]
        )
        != parity_normalized_source_data(
            str(relative), current_sources[str(relative)]
        )
    ]
    if mismatches:
        raise RuntimeError(
            "Release pair contains non-version changes: " + ", ".join(mismatches)
        )
    return {
        "current_version": current_release_version,
        "functional_file_count": len(SOURCE_FILES),
        "reference_version": reference_version,
        "version_only_files": ["griptape-nodes-library.json", "SBOM.spdx.json"],
    }


def check_parity(
    reference_path: Path,
    expected_reference_sha256: str | None = None,
) -> dict[str, Any]:
    """Compare current sources with an independently validated prior ZIP."""

    release_version, source_records = validate_sources()
    release_records = make_release_records(release_version, source_records)
    validate_release_inventory(release_version, release_records)
    archive_date_time = current_zip_date_time()
    first = make_archive(release_records, archive_date_time)
    second = make_archive(release_records, archive_date_time)
    if first != second:
        raise RuntimeError("Runtime archive is not reproducible.")
    validate_archive(first, release_records, archive_date_time)
    reference = reference_path.resolve()
    if not reference.is_file():
        raise RuntimeError(f"Release parity reference is missing: {reference}")
    reference_encoded = reference.read_bytes()
    reference_sha256 = digest(reference_encoded)
    if expected_reference_sha256 is not None:
        expected_digest = expected_reference_sha256.strip().casefold()
        if re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
            raise RuntimeError("Expected release parity SHA256 is invalid.")
        if reference_sha256 != expected_digest:
            raise RuntimeError("Release parity reference SHA256 differs.")
    result = validate_release_pair_parity(
        reference_encoded, release_version, source_records
    )
    expected_name = (
        f"HMB_GP_Production_{release_label_for_version(result['reference_version'])}"
        "_Runtime.zip"
    )
    if reference.name != expected_name:
        raise RuntimeError(
            f"Release parity reference filename mismatch; expected {expected_name}."
        )
    return {
        "current_release_label": RELEASE_LABEL,
        "current_release_version": release_version,
        "functional_file_count": result["functional_file_count"],
        "parity": True,
        "reference_archive": str(reference),
        "reference_release_version": result["reference_version"],
        "reference_sha256": reference_sha256,
        "version_only_files": result["version_only_files"],
    }


def write_parity_proof(proof_path: Path, tested_archive_path: Path) -> dict[str, Any]:
    """Bind an audited local even ZIP to its unchanged next odd team release."""

    release_version, source_records = validate_sources()
    major, minor, patch = release_version_parts(release_version)
    if patch % 2 != 0:
        raise RuntimeError("Parity proof creation requires an even local-test version.")
    archive_result = check_output(tested_archive_path)
    archive = tested_archive_path.resolve()
    tested_archive_sha256 = digest(archive.read_bytes())
    target_version = f"{major}.{minor}.{patch + 1}"
    payload = {
        "canonical_source_sha256": canonical_source_fingerprint(source_records),
        "schema": RELEASE_PARITY_PROOF_SCHEMA,
        "target_odd_release_label": release_label_for_version(target_version),
        "target_odd_version": target_version,
        "tested_even_archive_sha256": tested_archive_sha256,
        "tested_even_release_label": release_label_for_version(release_version),
        "tested_even_version": release_version,
        "version": RELEASE_PARITY_PROOF_VERSION,
    }
    proof = proof_path.resolve()
    proof.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=proof.name + ".",
        suffix=".tmp",
        dir=proof.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, proof)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        **payload,
        "proof": str(proof),
        "tested_archive": archive_result["archive"],
    }


def validate_parity_proof_payload(
    payload: Any,
    release_version: str,
    source_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate one proof against a candidate odd release behavior surface."""

    major, minor, patch = release_version_parts(release_version)
    if patch % 2 != 1 or patch == 0:
        raise RuntimeError("Parity proof validation requires an odd team version.")
    expected_keys = {
        "canonical_source_sha256",
        "schema",
        "target_odd_release_label",
        "target_odd_version",
        "tested_even_archive_sha256",
        "tested_even_release_label",
        "tested_even_version",
        "version",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise RuntimeError("Release parity proof boundary is invalid.")
    even_version = f"{major}.{minor}.{patch - 1}"
    if (
        payload.get("schema") != RELEASE_PARITY_PROOF_SCHEMA
        or payload.get("version") != RELEASE_PARITY_PROOF_VERSION
        or payload.get("tested_even_version") != even_version
        or payload.get("tested_even_release_label")
        != release_label_for_version(even_version)
        or payload.get("target_odd_version") != release_version
        or payload.get("target_odd_release_label")
        != release_label_for_version(release_version)
    ):
        raise RuntimeError("Release parity proof version pair is invalid.")
    tested_archive_sha256 = str(payload.get("tested_even_archive_sha256") or "")
    canonical_sha256 = str(payload.get("canonical_source_sha256") or "")
    if (
        re.fullmatch(r"[0-9a-f]{64}", tested_archive_sha256) is None
        or re.fullmatch(r"[0-9a-f]{64}", canonical_sha256) is None
    ):
        raise RuntimeError("Release parity proof digest is invalid.")
    actual_canonical_sha256 = canonical_source_fingerprint(source_records)
    if canonical_sha256 != actual_canonical_sha256:
        raise RuntimeError(
            "Team release differs from the tested even-version behavior surface."
        )
    return {
        "canonical_source_sha256": actual_canonical_sha256,
        "parity": True,
        "release_label": release_label_for_version(release_version),
        "release_version": release_version,
        "tested_even_archive_sha256": tested_archive_sha256,
        "tested_even_version": even_version,
    }


def check_parity_proof(proof_path: Path) -> dict[str, Any]:
    """Fail a team release unless it matches the tested local even build."""

    check()
    release_version, source_records = validate_sources()
    proof = proof_path.resolve()
    if not proof.is_file():
        raise RuntimeError(f"Release parity proof is missing: {proof}")
    payload = json.loads(proof.read_text(encoding="utf-8"))
    result = validate_parity_proof_payload(
        payload,
        release_version,
        source_records,
    )
    return {**result, "proof": str(proof)}


def current_zip_date_time() -> tuple[int, int, int, int, int, int]:
    """Return the actual local build time at ZIP's two-second resolution."""

    now = datetime.now()
    return (
        now.year,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second - (now.second % 2),
    )


def format_zip_date_time(value: tuple[int, int, int, int, int, int]) -> str:
    return datetime(*value).isoformat(sep=" ")


def archive_zip_date_time(encoded: bytes) -> tuple[int, int, int, int, int, int]:
    with zipfile.ZipFile(io.BytesIO(encoded), "r") as archive:
        infos = archive.infolist()
        if not infos:
            raise RuntimeError("Runtime archive has no timestamped members.")
        return infos[0].date_time


def make_archive(
    records: list[dict[str, Any]],
    archive_date_time: tuple[int, int, int, int, int, int] | None = None,
) -> bytes:
    if archive_date_time is None:
        archive_date_time = current_zip_date_time()
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for record in records:
            relative = str(record["path"])
            member = PurePosixPath(relative)
            assert_release_member_allowed(member)
            data = record["data"]
            if not isinstance(data, bytes):
                raise RuntimeError(f"Runtime release data must be bytes: {relative}")
            if any(marker in data for marker in FORBIDDEN_RELEASE_CONTENT_MARKERS):
                raise RuntimeError(
                    f"Package-local or private policy reference remains in {relative}"
                )
            if member == BUNDLED_AGENT_POLICY_MEMBER:
                verify_signed_agent_policy_bytes(data)
            if member.suffix.casefold() == ".zip":
                validate_no_policy_artifacts_in_zip(
                    data,
                    label=f"runtime record::{relative}",
                )
            info = zipfile.ZipInfo(
                f"{ARCHIVE_ROOT}/{relative}",
                archive_date_time,
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = REPRODUCIBLE_ZIP_MODE << 16
            archive.writestr(
                info,
                data,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def validate_archive(
    encoded: bytes,
    records: list[dict[str, Any]],
    archive_date_time: tuple[int, int, int, int, int, int] | None = None,
) -> None:
    validate_no_policy_artifacts_in_zip(encoded, label="runtime archive")
    expected = {str(item["path"]): item for item in records}
    with zipfile.ZipFile(io.BytesIO(encoded), "r") as archive:
        infos = archive.infolist()
        if len(infos) != len(expected) or archive.testzip() is not None:
            raise RuntimeError("Runtime archive member boundary mismatch.")
        if archive_date_time is None:
            if not infos:
                raise RuntimeError("Runtime archive has no timestamped members.")
            archive_date_time = infos[0].date_time
        seen: set[str] = set()
        for info in infos:
            member = PurePosixPath(info.filename)
            if not member.parts or member.parts[0] != ARCHIVE_ROOT:
                raise RuntimeError(f"Runtime archive root mismatch: {info.filename}")
            relative = PurePosixPath(*member.parts[1:]).as_posix()
            if relative not in expected or relative in seen:
                raise RuntimeError(f"Unexpected runtime archive member: {relative}")
            if info.date_time != archive_date_time:
                raise RuntimeError(f"Runtime archive timestamp mismatch: {relative}")
            if (info.external_attr >> 16) != REPRODUCIBLE_ZIP_MODE:
                raise RuntimeError(f"Runtime archive mode mismatch: {relative}")
            content = archive.read(info)
            if content != expected[relative]["data"]:
                raise RuntimeError(f"Runtime archive source mismatch: {relative}")
            seen.add(relative)
        if seen != set(expected):
            raise RuntimeError("Runtime archive omitted an allowlisted member.")


def build(output_path: Path = ARCHIVE_PATH) -> dict[str, Any]:
    release_version, source_records = validate_sources()
    records = make_release_records(release_version, source_records)
    validate_release_inventory(release_version, records)
    archive_date_time = current_zip_date_time()
    first = make_archive(records, archive_date_time)
    second = make_archive(records, archive_date_time)
    if first != second:
        raise RuntimeError("Runtime archive is not reproducible.")
    validate_archive(first, records, archive_date_time)

    output = output_path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=output.name + ".",
        suffix=".tmp",
        dir=output.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(first)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return {
        "archive": str(output),
        "archive_built_at_local": format_zip_date_time(archive_date_time),
        "archive_sha256": digest(first),
        "distribution_file_count": len(DISTRIBUTION_ONLY_FILES),
        "file_count": len(records),
        "install_file_count": len(RUNTIME_INSTALL_FILES),
        "policy_delivery": POLICY_DELIVERY,
        "release_label": RELEASE_LABEL,
        "release_version": release_version,
        "shot_routing_protocol": SHOT_ROUTING_PROTOCOL_VERSION,
        "source_file_count": len(SOURCE_FILES),
    }


def check() -> dict[str, Any]:
    release_version, source_records = validate_sources()
    records = make_release_records(release_version, source_records)
    validate_release_inventory(release_version, records)
    archive_date_time = current_zip_date_time()
    first = make_archive(records, archive_date_time)
    second = make_archive(records, archive_date_time)
    if first != second:
        raise RuntimeError("Runtime archive is not reproducible.")
    validate_archive(first, records, archive_date_time)
    return {
        "file_count": len(records),
        "archive_built_at_local": format_zip_date_time(archive_date_time),
        "distribution_file_count": len(DISTRIBUTION_ONLY_FILES),
        "install_file_count": len(RUNTIME_INSTALL_FILES),
        "policy_delivery": POLICY_DELIVERY,
        "release_label": RELEASE_LABEL,
        "release_version": release_version,
        "shot_routing_protocol": SHOT_ROUTING_PROTOCOL_VERSION,
        "source_file_count": len(SOURCE_FILES),
        "validated": True,
    }


def check_output(output_path: Path = ARCHIVE_PATH) -> dict[str, Any]:
    """Verify existing timestamped artifact contents against current sources."""

    release_version, source_records = validate_sources()
    records = make_release_records(release_version, source_records)
    validate_release_inventory(release_version, records)
    output = output_path.resolve()
    if not output.is_file():
        raise RuntimeError(f"Runtime release artifact is missing: {output}")
    actual = output.read_bytes()
    archive_date_time = archive_zip_date_time(actual)
    validate_archive(actual, records, archive_date_time)
    expected = make_archive(records, archive_date_time)
    if actual != expected:
        raise RuntimeError("Runtime release artifact is stale or source-mismatched.")
    return {
        "archive": str(output),
        "archive_built_at_local": format_zip_date_time(archive_date_time),
        "archive_sha256": digest(actual),
        "distribution_file_count": len(DISTRIBUTION_ONLY_FILES),
        "file_count": len(records),
        "install_file_count": len(RUNTIME_INSTALL_FILES),
        "release_label": RELEASE_LABEL,
        "release_version": release_version,
        "shot_routing_protocol": SHOT_ROUTING_PROTOCOL_VERSION,
        "source_file_count": len(SOURCE_FILES),
        "validated": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a verified runtime ZIP with the approved signed Agent DAT."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate sources and the in-memory ZIP without writing an artifact.",
    )
    parser.add_argument(
        "--check-output",
        action="store_true",
        help="Verify that --output has current source contents and a uniform build time.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ARCHIVE_PATH,
        help="Runtime ZIP destination. The production release files are never modified.",
    )
    parser.add_argument(
        "--parity-with",
        type=Path,
        help=(
            "Validate that current sources differ from the immediately preceding "
            "audited ZIP only by approved release-version metadata."
        ),
    )
    parser.add_argument(
        "--reference-sha256",
        help="Require the --parity-with ZIP to match this trusted SHA256.",
    )
    parser.add_argument(
        "--write-parity-proof",
        type=Path,
        help=(
            "Write a CI proof binding the validated even --output ZIP to the "
            "next odd team release."
        ),
    )
    parser.add_argument(
        "--check-parity-proof",
        type=Path,
        help="Validate a tested even-to-odd parity proof for the current release.",
    )
    args = parser.parse_args()
    primary_modes = (
        args.check,
        args.check_output,
        args.write_parity_proof,
        args.check_parity_proof,
    )
    if sum(bool(item) for item in primary_modes) > 1:
        parser.error(
            "--check, --check-output, --write-parity-proof, and "
            "--check-parity-proof are mutually exclusive"
        )
    if args.reference_sha256 and not args.parity_with:
        parser.error("--reference-sha256 requires --parity-with")
    if args.parity_with and not args.reference_sha256:
        parser.error("--parity-with requires --reference-sha256")
    if args.parity_with and not (args.check or args.check_output):
        parser.error("--parity-with requires --check or --check-output")
    if args.parity_with and (args.write_parity_proof or args.check_parity_proof):
        parser.error("--parity-with cannot be combined with parity proof modes")
    if args.write_parity_proof:
        result = write_parity_proof(args.write_parity_proof, args.output)
    elif args.check_parity_proof:
        result = check_parity_proof(args.check_parity_proof)
    elif args.check_output:
        result = check_output(args.output)
    elif args.check:
        result = check()
    else:
        result = build(args.output)
    if args.parity_with:
        result["release_pair_parity"] = check_parity(
            args.parity_with,
            args.reference_sha256,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
