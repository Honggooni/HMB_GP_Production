from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
POLICY_VERSION = "2026-08-27.agent-shot-quality.v4.5"
POLICY_CONTRACT_SHA256 = (
    "86852214d3e1a29eab12a2b0cff0302f6920d5d3ce3b00947d96ef1eb952c872"
)
RELEASE_LABEL = "v0.7.11"
RELEASE_VERSION = "0.7.11"
EXPECTED_RUNTIME_INSTALL_FILES = (
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
    "resources/tls/hmb_agent_broker_ca.pem",
)
EXPECTED_DISTRIBUTION_ONLY_FILES = (
    "Install_HMB_GP_Production.ps1",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
)
EXPECTED_SOURCE_FILES = (
    *EXPECTED_RUNTIME_INSTALL_FILES,
    *EXPECTED_DISTRIBUTION_ONLY_FILES,
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
    b"_BUNDLED_AGENT_POLICY_FILE",
    b"resources/agent/hmb_agent_core.dat",
    b"resources\\agent\\hmb_agent_core.dat",
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
    ROOT / "tools" / "package_runtime_release.py",
)

assert tuple(builder.RUNTIME_INSTALL_FILES) == EXPECTED_RUNTIME_INSTALL_FILES
assert tuple(builder.DISTRIBUTION_ONLY_FILES) == EXPECTED_DISTRIBUTION_ONLY_FILES
assert tuple(builder.SOURCE_FILES) == EXPECTED_SOURCE_FILES
assert len(EXPECTED_SOURCE_FILES) == (
    len(EXPECTED_RUNTIME_INSTALL_FILES) + len(EXPECTED_DISTRIBUTION_ONLY_FILES)
)
assert builder.RELEASE_LABEL == RELEASE_LABEL
assert builder.RELEASE_VERSION == RELEASE_VERSION
assert builder.release_version_parts(RELEASE_VERSION) == (0, 7, 11)
assert builder.release_label_for_version(RELEASE_VERSION) == RELEASE_LABEL
builder.validate_release_identity(RELEASE_LABEL, RELEASE_VERSION)
for invalid_version in (
    "0.7.01",
    "0.07.1",
    "00.7.1",
    "0.7.1-alpha",
    "0.7",
):
    try:
        builder.validate_release_identity(RELEASE_LABEL, invalid_version)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Invalid technical SemVer was accepted: {invalid_version}")
for mismatched_label in ("v0.7.011", "v0.7.10", "0.7.11"):
    try:
        builder.validate_release_identity(mismatched_label, RELEASE_VERSION)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Mismatched public release label was accepted: {mismatched_label}")
assert builder.ARCHIVE_NAME == "HMB_GP_Production_v0.7.11_Runtime.zip"
assert builder.ARCHIVE_NAME == f"HMB_GP_Production_{RELEASE_LABEL}_Runtime.zip"
assert builder.POLICY_VERSION == POLICY_VERSION
assert builder.POLICY_CONTRACT_SHA256 == POLICY_CONTRACT_SHA256
assert builder.POLICY_DELIVERY == "server-only"
for retired_name in ("POLICY_RELATIVE", "POLICY_SHA256", "POLICY_SIGNING_KEY_ID"):
    assert not hasattr(builder, retired_name)

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
sbom = json.loads((ROOT / "SBOM.spdx.json").read_text(encoding="utf-8"))
security_policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())
delivery = manifest["metadata"]["agent_policy_delivery"]
assert delivery["archive_source_count"] == len(EXPECTED_SOURCE_FILES)
assert "launcher_path" not in delivery
assert "bootstrap_marker" not in delivery
assert sbom["name"] == f"HMB_GP_Production-{RELEASE_VERSION}"
assert sbom["documentNamespace"].endswith(f"/{RELEASE_VERSION}")
assert next(
    item for item in sbom["packages"]
    if item["SPDXID"] == "SPDXRef-HMB-GP-Production"
)["versionInfo"] == RELEASE_VERSION
assert "http://192.168.203.245:8080" in security_policy
assert "Seedance 생성 Broker 내부망 예외" in security_policy
assert "Agent 정책 Broker" in security_policy
assert "서명 정책 조회나 정책 본문 전달에는 적용되지 않습니다" in security_policy
assert "임의의 외부 HTTP 주소" in security_policy
workflow_text = (ROOT / ".github" / "workflows" / "release-audit.yml").read_text(
    encoding="utf-8"
)
assert RELEASE_LABEL not in workflow_text
assert re.search(r"HMB_GP_Production_v\d+\.\d+\.\d+", workflow_text) is None
assert re.search(r"HMB GP Production v\d+\.\d+\.\d+", workflow_text) is None
assert "id: release_metadata" in workflow_text
assert "tomllib.load(open('pyproject.toml','rb'))" in workflow_text
assert "from tools.package_runtime_release import RELEASE_LABEL" in workflow_text
assert "Unsafe or unsupported package version" in workflow_text
assert "release_label=$releaseLabel" in workflow_text
assert "HMB_RELEASE_LABEL=$releaseLabel" in workflow_text
assert 'HMB_GP_Production_${releaseLabel}_Runtime.zip' in workflow_text
assert "steps.release_metadata.outputs.archive_name" in workflow_text
assert "needs.windows-release-audit.outputs.package_version" in workflow_text
assert "needs.windows-release-audit.outputs.release_label" in workflow_text
assert re.search(
    r"Even(?: technical)? patch version v?\$version is local-test-only",
    workflow_text,
)
assert re.search(
    r"Team releases require an odd(?: technical)? patch version",
    workflow_text,
)

release_version, records = builder.validate_sources()
record_paths = tuple(str(record["path"]) for record in records)
assert record_paths == EXPECTED_SOURCE_FILES
assert len(records) == len(EXPECTED_SOURCE_FILES)
assert release_version == manifest["metadata"]["library_version"]
assert release_version == RELEASE_VERSION
record_by_path = {str(record["path"]): record for record in records}
assert set(record_by_path) == set(EXPECTED_SOURCE_FILES)
assert all(
    record_by_path[path]["install"] is True
    for path in EXPECTED_RUNTIME_INSTALL_FILES
)
assert all(
    record_by_path[path]["install"] is False
    for path in EXPECTED_DISTRIBUTION_ONLY_FILES
)

release_records = builder.make_release_records(release_version, records)
builder.validate_release_inventory(release_version, release_records)
release_record_by_path = {
    str(record["path"]): record for record in release_records
}
closure_manifest = json.loads(
    release_record_by_path[builder.RELEASE_MANIFEST_PATH]["data"].decode("utf-8")
)
assert closure_manifest["release_label"] == RELEASE_LABEL
assert closure_manifest["release_version"] == RELEASE_VERSION
assert closure_manifest["file_count"] == len(EXPECTED_SOURCE_FILES)
assert closure_manifest["install_file_count"] == len(EXPECTED_RUNTIME_INSTALL_FILES)
assert closure_manifest["distribution_file_count"] == len(EXPECTED_DISTRIBUTION_ONLY_FILES)
closure_by_path = {
    str(record["path"]): record for record in closure_manifest["files"]
}
assert all(
    closure_by_path[path]["install"] is True
    for path in EXPECTED_RUNTIME_INSTALL_FILES
)
assert all(
    closure_by_path[path]["install"] is False
    for path in EXPECTED_DISTRIBUTION_ONLY_FILES
)

# Keep every other closure field and checksum internally consistent so this
# mutation is rejected specifically because the public label is not approved.
tampered_release_records = [dict(record) for record in release_records]
tampered_manifest_record = next(
    record
    for record in tampered_release_records
    if record["path"] == builder.RELEASE_MANIFEST_PATH
)
tampered_manifest = json.loads(tampered_manifest_record["data"].decode("utf-8"))
tampered_manifest["release_label"] = "v0.7.99"
tampered_manifest_data = (
    json.dumps(tampered_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
).encode("utf-8")
tampered_manifest_record.update(
    bytes=len(tampered_manifest_data),
    data=tampered_manifest_data,
    sha256=builder.digest(tampered_manifest_data),
)
tampered_checksum_record = next(
    record
    for record in tampered_release_records
    if record["path"] == builder.SHA256SUMS_PATH
)
tampered_checksum_data = (
    "\n".join(
        f'{record["sha256"]}  {record["path"]}'
        for record in tampered_release_records
        if record["path"] != builder.SHA256SUMS_PATH
    )
    + "\n"
).encode("utf-8")
tampered_checksum_record.update(
    bytes=len(tampered_checksum_data),
    data=tampered_checksum_data,
    sha256=builder.digest(tampered_checksum_data),
)
try:
    builder.validate_release_inventory(release_version, tampered_release_records)
except RuntimeError:
    pass
else:
    raise AssertionError("A mismatched release-manifest label was accepted.")

assert set(release_record_by_path) == {
    *EXPECTED_SOURCE_FILES,
    builder.RELEASE_MANIFEST_PATH,
    builder.SHA256SUMS_PATH,
}
archive_date_time = builder.current_zip_date_time()
first_archive = builder.make_archive(release_records, archive_date_time)
second_archive = builder.make_archive(release_records, archive_date_time)
assert first_archive == second_archive
builder.validate_archive(first_archive, release_records, archive_date_time)
assert abs((datetime.now() - datetime(*archive_date_time)).total_seconds()) < 5
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_VERSION"
) == "2026-08-27.agent-shot-quality.v4.5"
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_CONTRACT_SHA256"
) == POLICY_CONTRACT_SHA256
assert builder.module_string_constant(
    ROOT / "HMBPromptLibrary.py", "PROMPT_POLICY_CANDIDATE_STATUS"
) == "active"
check_result = builder.check()
assert check_result["validated"] is True
assert check_result["file_count"] == len(EXPECTED_SOURCE_FILES) + 2
assert check_result["source_file_count"] == len(EXPECTED_SOURCE_FILES)
assert check_result["install_file_count"] == len(EXPECTED_RUNTIME_INSTALL_FILES)
assert check_result["distribution_file_count"] == len(EXPECTED_DISTRIBUTION_ONLY_FILES)
assert check_result["policy_delivery"] == "server-only"
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
    assert len(infos) == len(release_records)
    assert archive.testzip() is None
    expected_names = [
        f"{builder.ARCHIVE_ROOT}/{record['path']}" for record in release_records
    ]
    assert [info.filename for info in infos] == expected_names
    assert {info.date_time for info in infos} == {archive_date_time}
    assert not any(
        PurePosixPath(info.filename).suffix.casefold() == ".dat" for info in infos
    )

    for info in infos:
        member = PurePosixPath(info.filename)
        lowered = info.filename.casefold()
        relative = member.relative_to(builder.ARCHIVE_ROOT).as_posix()
        # The authenticated Broker contract intentionally ships one pinned
        # public CA certificate.  Private keys and every other PEM remain
        # forbidden, including PEM files at look-alike paths.
        if relative == builder.PUBLIC_CA_MEMBER.as_posix():
            assert member.suffix.casefold() == ".pem"
        else:
            assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
        assert "/resources/agent/" not in f"/{lowered}"
        assert "/resources/policy/" not in f"/{lowered}"
        assert "/policies/" not in f"/{lowered}"
        assert not re.search(
            r"(^|/)(?:credentials|secrets)[^/]*\.json$",
            lowered,
        )
        assert not re.search(r"(^|/)(?:id_rsa|id_ed25519)[^/]*$", lowered)
        content = archive.read(info)
        assert content == release_record_by_path[relative]["data"]
        assert PRIVATE_KEY_HEADER.search(content) is None
        assert not any(pattern.search(content) for pattern in COMMON_TOKEN_PATTERNS)
        assert not any(secret in content for secret in configured_secret_values)
        assert not any(marker in content for marker in FORBIDDEN_PACKAGE_POLICY_MARKERS)
        assert not any(marker in content for marker in RETIRED_USAGE_MARKERS)
        assert not any(marker in content for marker in RETIRED_DIRECT_PROVIDER_MARKERS)

# The server-path contract is allowed in source, but no package layer may carry
# the signed data file or English/Korean policy documents. Inspect nested ZIPs
# because the team installer wraps the library ZIP in another ZIP.
safe_nested = zip_bytes({"docs/readme.txt": b"safe"})
builder.validate_no_policy_artifacts_in_zip(
    zip_bytes({"package/safe.zip": safe_nested})
)
assert_forbidden_archive(zip_bytes({"package/hmb_agent_core.dat": b"sealed"}))
try:
    builder.make_archive(
        [{"path": "resources/agent/hmb_agent_core.dat", "data": b"sealed"}],
        archive_date_time,
    )
except RuntimeError:
    pass
else:
    raise AssertionError("The archive builder accepted a direct .dat record.")
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
assert "!resources/agent/hmb_agent_core.dat" not in gitignore

print("HMB in-memory server-only release/credential boundary regression: PASS")
