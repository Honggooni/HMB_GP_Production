from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
POLICY_VERSION = "2026-08-12.agent-shot-quality.v4.2"
POLICY_CONTRACT_SHA256 = (
    "7a40ddf71c115ddef29b3bc428ccd9024649d9fac5af607b96173c1cf77b2199"
)
POLICY_RELATIVE = "resources/agent/hmb_agent_core.dat"
POLICY_SHA256 = "7171bef7169df8894ed24ae7a9b4d9d145957c5110c963b7435372b2695fd251"
RELEASE_LABEL = "v0.6.25"
RELEASE_VERSION = "0.6.25"
EXPECTED_SOURCE_FILES = (
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
    "_hmb_mp4_verify.py",
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
    POLICY_RELATIVE,
)
EXPECTED_SECRET_NAMES = {
    "GT_CLOUD_API_KEY",
    "GT_CLOUD_BUCKET_ID",
    "TOS_ACCESS_KEY_ID",
    "TOS_SECRET_ACCESS_KEY",
    "TOS_BUCKET_NAME",
}
FORBIDDEN_SUFFIXES = {
    ".env",
    ".jwk",
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".secret",
    ".token",
}
PRIVATE_KEY_HEADER = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
COMMON_TOKEN_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
)
FORBIDDEN_PACKAGE_POLICY_MARKERS = (
    b"resources/policy/HMB_GP_Production_Rule",
)
RETIRED_USAGE_MARKERS = (
    b"00" + bytes((46,)) + b"CompSource",
    b"USAGE_LEDGER_ROOT",
    b"USAGE_LOCAL_QUEUE_ROOT",
    b"USAGE_PRICE_CNY_PER_MILLION",
    b"_prepare_usage_tracking",
    b"_record_usage_task",
    b"_record_current_usage_status",
    b"_build_usage_event",
    b"_flush_usage_queue",
)
RETIRED_DIRECT_PROVIDER_MARKERS = (
    b"ARK_API_KEY_SECRET",
    b"ARK_BASE_URL",
    b"CREATE_TASK_PATH",
    b"POST_REQUEST_TIMEOUT_SECONDS",
    b"VolcengineAPIError",
    b"_build_payload",
    b"_get_api_key",
    b"_provider_error_detail",
    b"_network_error_phase",
    b"_submission_diagnostic",
    b"_refresh_direct_async",
    b"_process_direct_generation_impl",
    b"ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zip_bytes(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


def assert_forbidden_archive(encoded: bytes) -> None:
    try:
        builder.validate_no_policy_artifacts_in_zip(encoded)
    except RuntimeError:
        return
    raise AssertionError("A policy artifact or policy document entered a release ZIP.")


builder = load_module(
    "_hmb_public_release_in_memory_builder",
    ROOT / "resources" / "build_release.py",
)

assert tuple(builder.SOURCE_FILES) == EXPECTED_SOURCE_FILES
assert len(EXPECTED_SOURCE_FILES) == 26
assert builder.RELEASE_LABEL == RELEASE_LABEL
assert builder.RELEASE_VERSION == RELEASE_VERSION
assert builder.ARCHIVE_NAME == "HMB_GP_Production.zip"
assert builder.POLICY_VERSION == POLICY_VERSION
assert builder.POLICY_CONTRACT_SHA256 == POLICY_CONTRACT_SHA256
assert builder.POLICY_DELIVERY == "bundled"
assert builder.POLICY_RELATIVE == POLICY_RELATIVE
assert builder.POLICY_SHA256 == POLICY_SHA256

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())
assert sbom["name"] == f"HMB_GP_Production-{RELEASE_VERSION}"
assert sbom["documentNamespace"].endswith(f"/{RELEASE_VERSION}")
assert next(
    item for item in sbom["packages"]
    if item["SPDXID"] == "SPDXRef-HMB-GP-Production"
)["versionInfo"] == RELEASE_VERSION
assert f"## {RELEASE_VERSION} - 2026-08-12" in changelog

release_version, records = builder.validate_sources()
record_paths = tuple(str(record["path"]) for record in records)
assert record_paths == EXPECTED_SOURCE_FILES
assert len(records) == len(EXPECTED_SOURCE_FILES)
assert release_version == manifest["metadata"]["library_version"]
assert release_version == RELEASE_VERSION
record_by_path = {str(record["path"]): record for record in records}
assert set(record_by_path) == set(EXPECTED_SOURCE_FILES)
assert record_by_path[POLICY_RELATIVE]["sha256"] == POLICY_SHA256

first_archive = builder.make_archive(records)
second_archive = builder.make_archive(records)
assert first_archive == second_archive
builder.validate_archive(first_archive, records)
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_VERSION"
) == "2026-08-12.agent-shot-quality.v4.2"
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256"
) == POLICY_CONTRACT_SHA256
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_STATUS"
) == "active"
check_result = builder.check()
assert check_result["validated"] is True
assert check_result["policy_delivery"] == "bundled"
assert check_result["policy_version"] == POLICY_VERSION
assert check_result["policy_contract_sha256"] == POLICY_CONTRACT_SHA256
assert check_result["release_label"] == RELEASE_LABEL
assert check_result["release_version"] == RELEASE_VERSION

configured_secret_values = tuple(
    value.encode("utf-8")
    for name in EXPECTED_SECRET_NAMES
    if len(value := os.environ.get(name, "")) >= 8
)

with zipfile.ZipFile(io.BytesIO(first_archive), "r") as archive:
    infos = archive.infolist()
    assert len(infos) == len(EXPECTED_SOURCE_FILES)
    assert archive.testzip() is None
    expected_names = [
        f"{builder.ARCHIVE_ROOT}/{relative}" for relative in EXPECTED_SOURCE_FILES
    ]
    assert [info.filename for info in infos] == expected_names
    dat_members = [
        info for info in infos
        if PurePosixPath(info.filename).suffix.casefold() == ".dat"
    ]
    assert [info.filename for info in dat_members] == [
        f"{builder.ARCHIVE_ROOT}/{POLICY_RELATIVE}"
    ]
    assert builder.digest(archive.read(dat_members[0])) == POLICY_SHA256

    for info in infos:
        member = PurePosixPath(info.filename)
        lowered = info.filename.casefold()
        relative = member.relative_to(builder.ARCHIVE_ROOT).as_posix()
        if relative != POLICY_RELATIVE:
            assert member.suffix.casefold() != ".dat"
            assert "/resources/agent/" not in f"/{lowered}"
        assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
        assert "/resources/policy/" not in f"/{lowered}"
        assert "/policies/" not in f"/{lowered}"
        assert not re.search(
            r"(^|/)(?:credentials|secrets)[^/]*\.json$",
            lowered,
        )
        assert not re.search(r"(^|/)(?:id_rsa|id_ed25519)[^/]*$", lowered)
        content = archive.read(info)
        assert content == record_by_path[relative]["data"]
        assert PRIVATE_KEY_HEADER.search(content) is None
        assert not any(pattern.search(content) for pattern in COMMON_TOKEN_PATTERNS)
        assert not any(secret in content for secret in configured_secret_values)
        assert not any(marker in content for marker in FORBIDDEN_PACKAGE_POLICY_MARKERS)
        assert not any(marker in content for marker in RETIRED_USAGE_MARKERS)
        assert not any(marker in content for marker in RETIRED_DIRECT_PROVIDER_MARKERS)

# Exactly one direct signed data file is allowed. English/Korean policy documents
# and additional or nested .dat artifacts remain forbidden.
safe_nested = zip_bytes({"docs/readme.txt": b"safe"})
builder.validate_no_policy_artifacts_in_zip(
    zip_bytes({"package/safe.zip": safe_nested})
)
assert_forbidden_archive(zip_bytes({"package/hmb_agent_core.dat": b"sealed"}))
builder.assert_release_member_allowed(
    PurePosixPath(POLICY_RELATIVE),
    allow_bundled_policy=True,
)
try:
    builder.assert_release_member_allowed(PurePosixPath(POLICY_RELATIVE))
except RuntimeError:
    pass
else:
    raise AssertionError("The generic boundary accepted an unapproved .dat record.")
assert_forbidden_archive(
    zip_bytes(
        {
            "package/library.zip": zip_bytes(
                {"HMB_GP_Production/resources/agent/hmb_agent_core.dat": b"sealed"}
            )
        }
    )
)
assert_forbidden_archive(
    zip_bytes(
        {
            "package/library.zip": zip_bytes(
                {"policies/HMB_Agent_Policies_8_KO.txt": b"review"}
            )
        }
    )
)
assert_forbidden_archive(
    zip_bytes({"resources/policy/canonical/HMB_Agent_Policies_8_EN.txt": b"source"})
)
assert_forbidden_archive(zip_bytes({"package/policy/canonical.txt": b"source"}))
assert_forbidden_archive(zip_bytes({"HMB_Agent_Policies_8_EN.txt": b"source"}))
assert_forbidden_archive(zip_bytes({"HMB_Agent_Policy.txt": b"source"}))
assert_forbidden_archive(
    zip_bytes(
        {
            "package/library.zip": zip_bytes(
                {"HMB_Agent_Policies_8_EN.txt": b"source"}
            )
        }
    )
)

gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
assert "resources/agent/" in gitignore
assert "resources/policy/" in gitignore
assert "policies/" in gitignore
assert "**/hmb_agent_core.dat" in gitignore
assert "!resources/agent/hmb_agent_core.dat" in gitignore

print("HMB in-memory bundled-policy release/credential boundary regression: PASS")
