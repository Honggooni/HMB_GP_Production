from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE_LABEL = "v0.6.01"
RELEASE_VERSION = "0.6.1"
ARCHIVE_NAME = f"HMB_GP_Production_DEV_{RELEASE_VERSION}.zip"
ARCHIVE_PATH = DIST / ARCHIVE_NAME
ARCHIVE_ROOT = "HMB_GP_Production"
POLICY_VERSION = "2026-08-11.agent-shot-quality.v4.1"
POLICY_CONTRACT_SHA256 = (
    "26243936dddc34679aba57043e9ee583a0421e20c05f69fffd6c1ffe50192ff5"
)
POLICY_DELIVERY = "server-only"
REPRODUCIBLE_ZIP_DATE_TIME = (2020, 1, 1, 0, 0, 0)
REPRODUCIBLE_ZIP_MODE = 0o100644
MAX_NESTED_ARCHIVE_DEPTH = 3
MAX_NESTED_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096

SOURCE_FILES = (
    "__init__.py",
    "griptape-nodes-library.json",
    "pyproject.toml",
    "README.md",
    "SECURITY.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
    "HMBAgentLibrary.py",
    "HMBImageAssetLibrary.py",
    "HMBPromptLibrary.py",
    "HMBSeedanceGeneration.py",
    "HMBVideoPickerLibrary.py",
    "_hmb_common.py",
    "_hmb_screen_space.py",
    "widgets/HMBAgentLibraryWidget.js",
    "widgets/HMBImageAssetLibraryWidget.js",
    "widgets/HMBPromptLibraryScopedBindingWidget.js",
    "widgets/HMBVideoPickerCommandBridgeWidget_v032.js",
    "widgets/HMBVideoPickerLibraryWidget_v032.js",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/maya/HMB_Maya_Binding_Setup.py",
    "resources/maya/HMBVideoPicker_Maya_Guide.txt",
    "resources/picker/HMB_Marker_Catalog.json",
)
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
    b"_BUNDLED_AGENT_POLICY_FILE",
    b"resources/agent/hmb_agent_core.dat",
    b"resources\\agent\\hmb_agent_core.dat",
    b"resources/policy/HMB_GP_Production_Rule",
)
# A policy source must be rejected by filename even when an adversarial nested
# archive omits the usual ``resources/policy`` or ``policies`` directory. This
# deliberately covers English canonical names as well as local Korean reviews.
POLICY_DOCUMENT_NAME = re.compile(r"(?i)polic(?:y|ies)")
PRIVATE_KEY_HEADER = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
COMMON_TOKEN_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def assert_release_member_allowed(member: PurePosixPath) -> None:
    """Reject policy artifacts and review documents from every release layer."""

    relative = member.as_posix()
    lowered_parts = tuple(part.casefold() for part in member.parts)
    lowered_pairs = set(zip(lowered_parts, lowered_parts[1:]))
    if member.is_absolute() or ".." in member.parts or "\\" in relative:
        raise RuntimeError(f"Unsafe developer release path: {relative}")
    if member.suffix.casefold() in FORBIDDEN_SUFFIXES:
        raise RuntimeError(f"Forbidden developer release member: {relative}")
    if (
        ("resources", "agent") in lowered_pairs
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
    """Recursively reject .dat and policy documents, including nested ZIPs."""

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
        ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_SOURCE_VERSION"
    ) != POLICY_VERSION or module_string_constant(
        ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_SOURCE_CONTRACT_SHA256"
    ) != POLICY_CONTRACT_SHA256:
        raise RuntimeError("Prompt compiler and required server policy identities differ.")
    registered_secrets = library_manifest["settings"][0]["contents"][
        "secrets_to_register"
    ]
    if set(registered_secrets) != EXPECTED_SECRET_NAMES or any(
        value != "" for value in registered_secrets.values()
    ):
        raise RuntimeError("Library secret registration boundary mismatch.")

    records: list[dict[str, Any]] = []
    for relative in SOURCE_FILES:
        member = PurePosixPath(relative)
        assert_release_member_allowed(member)
        path = ROOT / Path(relative)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Missing or linked developer release member: {relative}")
        data = path.read_bytes()
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
                label=f"developer source::{relative}",
            )
        records.append(
            {
                "bytes": len(data),
                "data": data,
                "path": relative,
                "sha256": digest(data),
            }
        )
    return release_version, records


def make_archive(records: list[dict[str, Any]]) -> bytes:
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
                raise RuntimeError(f"Developer release data must be bytes: {relative}")
            if any(marker in data for marker in FORBIDDEN_RELEASE_CONTENT_MARKERS):
                raise RuntimeError(
                    f"Package-local or private policy reference remains in {relative}"
                )
            if member.suffix.casefold() == ".zip":
                validate_no_policy_artifacts_in_zip(
                    data,
                    label=f"developer record::{relative}",
                )
            info = zipfile.ZipInfo(
                f"{ARCHIVE_ROOT}/{relative}",
                REPRODUCIBLE_ZIP_DATE_TIME,
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


def validate_archive(encoded: bytes, records: list[dict[str, Any]]) -> None:
    validate_no_policy_artifacts_in_zip(encoded, label="developer archive")
    expected = {str(item["path"]): item for item in records}
    with zipfile.ZipFile(io.BytesIO(encoded), "r") as archive:
        infos = archive.infolist()
        if len(infos) != len(expected) or archive.testzip() is not None:
            raise RuntimeError("Developer archive member boundary mismatch.")
        seen: set[str] = set()
        for info in infos:
            member = PurePosixPath(info.filename)
            if not member.parts or member.parts[0] != ARCHIVE_ROOT:
                raise RuntimeError(f"Developer archive root mismatch: {info.filename}")
            relative = PurePosixPath(*member.parts[1:]).as_posix()
            if relative not in expected or relative in seen:
                raise RuntimeError(f"Unexpected developer archive member: {relative}")
            if info.date_time != REPRODUCIBLE_ZIP_DATE_TIME:
                raise RuntimeError(f"Developer archive timestamp mismatch: {relative}")
            if (info.external_attr >> 16) != REPRODUCIBLE_ZIP_MODE:
                raise RuntimeError(f"Developer archive mode mismatch: {relative}")
            content = archive.read(info)
            if content != expected[relative]["data"]:
                raise RuntimeError(f"Developer archive source mismatch: {relative}")
            seen.add(relative)
        if seen != set(expected):
            raise RuntimeError("Developer archive omitted an allowlisted member.")


def assert_release_policy_candidate_is_active() -> None:
    """Block packaging while reviewed policy source still awaits signing."""

    prompt_path = ROOT / "HMBPromptLibrary.py"
    candidate_version = module_string_constant(
        prompt_path, "PROMPT_POLICY_CANDIDATE_VERSION"
    )
    candidate_contract = module_string_constant(
        prompt_path, "PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256"
    )
    candidate_status = module_string_constant(
        prompt_path, "PROMPT_POLICY_CANDIDATE_STATUS"
    ).casefold()
    if (
        candidate_version != POLICY_VERSION
        or candidate_contract != POLICY_CONTRACT_SHA256
        or candidate_status != "active"
    ):
        raise RuntimeError(
            "Developer release is blocked: the reviewed policy candidate is not "
            "the active signed server policy."
        )


def build(output_path: Path = ARCHIVE_PATH) -> dict[str, Any]:
    assert_release_policy_candidate_is_active()
    release_version, records = validate_sources()
    first = make_archive(records)
    second = make_archive(records)
    if first != second:
        raise RuntimeError("Developer archive is not reproducible.")
    validate_archive(first, records)

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
        "archive_sha256": digest(first),
        "file_count": len(records),
        "policy_contract_sha256": POLICY_CONTRACT_SHA256,
        "policy_delivery": POLICY_DELIVERY,
        "policy_version": POLICY_VERSION,
        "release_label": RELEASE_LABEL,
        "release_version": release_version,
    }


def check() -> dict[str, Any]:
    assert_release_policy_candidate_is_active()
    release_version, records = validate_sources()
    first = make_archive(records)
    second = make_archive(records)
    if first != second:
        raise RuntimeError("Developer archive is not reproducible.")
    validate_archive(first, records)
    return {
        "file_count": len(records),
        "policy_contract_sha256": POLICY_CONTRACT_SHA256,
        "policy_delivery": POLICY_DELIVERY,
        "policy_version": POLICY_VERSION,
        "release_label": RELEASE_LABEL,
        "release_version": release_version,
        "validated": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic developer ZIP that uses server-only policy delivery."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate sources and the in-memory ZIP without writing an artifact.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ARCHIVE_PATH,
        help="Developer ZIP destination. The production release files are never modified.",
    )
    args = parser.parse_args()
    result = check() if args.check else build(args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
