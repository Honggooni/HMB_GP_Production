from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import zipfile
import zlib
from datetime import datetime
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
RELEASE_LABEL = "v0.7.25"
RELEASE_VERSION = "0.7.25"
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
    "resources/agent/hmb_agent_core.dat",
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
common = load_module(
    "_hmb_public_release_policy_verifier",
    ROOT / "_hmb_common.py",
)

assert tuple(builder.RUNTIME_INSTALL_FILES) == EXPECTED_RUNTIME_INSTALL_FILES
assert tuple(builder.DISTRIBUTION_ONLY_FILES) == EXPECTED_DISTRIBUTION_ONLY_FILES
assert tuple(builder.SOURCE_FILES) == EXPECTED_SOURCE_FILES
assert len(EXPECTED_SOURCE_FILES) == (
    len(EXPECTED_RUNTIME_INSTALL_FILES) + len(EXPECTED_DISTRIBUTION_ONLY_FILES)
)
assert builder.RELEASE_LABEL == RELEASE_LABEL
assert builder.RELEASE_VERSION == RELEASE_VERSION
assert builder.release_version_parts(RELEASE_VERSION) == (0, 7, 25)
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
for mismatched_label in ("v0.7.025", "v0.7.24", "0.7.25"):
    try:
        builder.validate_release_identity(mismatched_label, RELEASE_VERSION)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Mismatched public release label was accepted: {mismatched_label}")
assert builder.ARCHIVE_NAME == "HMB_GP_Production_v0.7.25_Runtime.zip"
assert builder.ARCHIVE_NAME == f"HMB_GP_Production_{RELEASE_LABEL}_Runtime.zip"
assert builder.POLICY_DELIVERY == "bundled-signed-dat"
for retired_name in (
    "POLICY_RELATIVE",
    "POLICY_SHA256",
    "POLICY_SIGNING_KEY_ID",
    "POLICY_VERSION",
    "POLICY_CONTRACT_SHA256",
    "assert_release_policy_candidate_is_active",
):
    assert not hasattr(builder, retired_name)
for retired_name in ("_AGENT_POLICY_VERSION", "_AGENT_POLICY_CONTRACT_SHA256"):
    assert not hasattr(common, retired_name)

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
assert delivery["mode"] == "bundled_signed_dat"
assert delivery["runtime_path"] == "resources/agent/hmb_agent_core.dat"
assert delivery["verification"] == "rsa3072_sha256_v3_contract_once_per_process"
assert "launcher_path" not in delivery
assert "bootstrap_marker" not in delivery

# The public runtime trusts the signed bundled envelope. Exercise the stable
# signature boundary and the two document digests independently of wording.
policy_document = "Behavior server revision\n1. SERVER_AUTHORED_POLICY"
binding_document = "Behavior server binding\n1. SERVER_AUTHORED_BINDING"
signed_policy_payload = {
    "schema": common._AGENT_POLICY_SCHEMA,
    "policy": policy_document,
    "policy_sha256": hashlib.sha256(policy_document.encode("utf-8")).hexdigest(),
    "binding": binding_document,
    "binding_sha256": hashlib.sha256(binding_document.encode("utf-8")).hexdigest(),
    "final_policy_version": "server-controlled-revision",
}
validated_policy_payload = common._validate_agent_policy_payload(
    signed_policy_payload
)
assert validated_policy_payload["final_policy_version"] == "server-controlled-revision"
assert validated_policy_payload["policy_sha256"] == signed_policy_payload["policy_sha256"]
assert validated_policy_payload["binding_sha256"] == signed_policy_payload["binding_sha256"]
assert validated_policy_payload["policy_pair_sha256"] == hashlib.sha256(
    policy_document.encode("utf-8") + b"\0" + binding_document.encode("utf-8")
).hexdigest()
for document_field in ("policy", "binding"):
    tampered_payload = dict(signed_policy_payload)
    tampered_payload[document_field] += "\nTAMPERED"
    try:
        common._validate_agent_policy_payload(tampered_payload)
    except RuntimeError:
        pass
    else:
        raise AssertionError(f"Tampered {document_field} document digest was accepted.")

compressed_payload = zlib.compress(common._canonical_json_bytes(signed_policy_payload))
trusted_signature = b"trusted-public-release-regression-signature"
signed_envelope = {
    "schema": common._AGENT_POLICY_ENVELOPE_SCHEMA,
    "algorithm": common._AGENT_POLICY_SIGNATURE_ALGORITHM,
    "key_id": common._AGENT_POLICY_SIGNING_KEY_ID,
    "payload_sha256": hashlib.sha256(compressed_payload).hexdigest(),
    "payload": base64.b64encode(compressed_payload).decode("ascii"),
    "signature": base64.b64encode(trusted_signature).decode("ascii"),
}
real_signature_verifier = common._verify_agent_policy_signature
try:
    common._verify_agent_policy_signature = lambda payload, signature: (
        payload == compressed_payload and signature == trusted_signature
    )
    assert common._decode_signed_agent_policy_envelope(
        common._canonical_json_bytes(signed_envelope)
    ) == signed_policy_payload
    for envelope_field, tampered_value in (
        ("signature", base64.b64encode(b"untrusted-signature").decode("ascii")),
        ("payload_sha256", "0" * 64),
    ):
        tampered_envelope = dict(signed_envelope)
        tampered_envelope[envelope_field] = tampered_value
        try:
            common._decode_signed_agent_policy_envelope(
                common._canonical_json_bytes(tampered_envelope)
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                f"Tampered policy envelope {envelope_field} was accepted."
            )
finally:
    common._verify_agent_policy_signature = real_signature_verifier

agent_model_ids = builder.node_model_usage_ids(manifest, "HMBAgentLibrary")
assert len(agent_model_ids) == 30
assert len(agent_model_ids) == len(set(agent_model_ids))
catalog_model_ids = builder.library_model_catalog_ids(manifest)
assert len(catalog_model_ids) == 30
assert set(agent_model_ids) == set(catalog_model_ids)
assert (
    builder.library_model_catalog_contract_sha256(manifest)
    == builder.STANDARD_AGENT_MODEL_CATALOG_SHA256
)
saved_standard_root = os.environ.get(builder.STANDARD_AGENT_LIBRARY_ENV)
synthetic_standard_root = ROOT / "_not_materialized_standard_library"
try:
    configured_manifest_shapes = (
        (synthetic_standard_root, synthetic_standard_root / builder.STANDARD_AGENT_MANIFEST_NAME),
        (
            synthetic_standard_root / "griptape_nodes_library",
            synthetic_standard_root / builder.STANDARD_AGENT_MANIFEST_NAME,
        ),
        (
            synthetic_standard_root / "griptape_nodes_library" / "agents" / "agent.py",
            synthetic_standard_root / builder.STANDARD_AGENT_MANIFEST_NAME,
        ),
        (
            synthetic_standard_root / builder.STANDARD_AGENT_MANIFEST_NAME,
            synthetic_standard_root / builder.STANDARD_AGENT_MANIFEST_NAME,
        ),
    )
    for configured_path, expected_manifest in configured_manifest_shapes:
        os.environ[builder.STANDARD_AGENT_LIBRARY_ENV] = str(configured_path)
        assert builder.standard_agent_manifest_candidates()[0] == expected_manifest
finally:
    if saved_standard_root is None:
        os.environ.pop(builder.STANDARD_AGENT_LIBRARY_ENV, None)
    else:
        os.environ[builder.STANDARD_AGENT_LIBRARY_ENV] = saved_standard_root
standard_manifest_path = builder.validate_standard_agent_model_parity(manifest)
if standard_manifest_path is not None:
    standard_manifest = json.loads(standard_manifest_path.read_text(encoding="utf-8"))
    assert agent_model_ids == builder.node_model_usage_ids(standard_manifest, "Agent")
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
assert "Require tested even-to-odd runtime parity" in workflow_text
assert (
    "python tools/package_runtime_release.py --check-parity-proof "
    ".github/hmb-release-parity.json"
) in workflow_text

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
for canonical_crlf_member in builder.CANONICAL_CRLF_SOURCE_FILES:
    canonical_record = next(
        record
        for record in records
        if record["path"] == canonical_crlf_member.as_posix()
    )
    canonical_data = canonical_record["data"]
    assert b"\r\n" in canonical_data
    assert b"\n" not in canonical_data.replace(b"\r\n", b"")
    assert builder.canonical_release_source_data(
        canonical_crlf_member,
        canonical_data.replace(b"\r\n", b"\n"),
    ) == canonical_data

previous_version_parts = builder.release_version_parts(RELEASE_VERSION)
previous_version = (
    f"{previous_version_parts[0]}.{previous_version_parts[1]}."
    f"{previous_version_parts[2] - 1}"
)
previous_source_records = []
for record in records:
    previous_record = dict(record)
    previous_data = bytes(record["data"])
    if record["path"] == "griptape-nodes-library.json":
        previous_payload = json.loads(previous_data.decode("utf-8"))
        previous_payload["metadata"]["library_version"] = previous_version
        previous_data = (
            json.dumps(previous_payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    elif record["path"] == "SBOM.spdx.json":
        previous_payload = json.loads(previous_data.decode("utf-8"))
        previous_payload["name"] = f"HMB_GP_Production-{previous_version}"
        previous_payload["documentNamespace"] = (
            f"https://hmb.local/spdx/HMB_GP_Production/{previous_version}"
        )
        next(
            item
            for item in previous_payload["packages"]
            if item["SPDXID"] == "SPDXRef-HMB-GP-Production"
        )["versionInfo"] = previous_version
        previous_data = (
            json.dumps(previous_payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    previous_record.update(
        bytes=len(previous_data),
        data=previous_data,
        sha256=builder.digest(previous_data),
    )
    previous_source_records.append(previous_record)
previous_release_records = builder.make_release_records(
    previous_version, previous_source_records
)
builder.validate_release_inventory(previous_version, previous_release_records)
previous_archive = builder.make_archive(previous_release_records, archive_date_time)
parity_result = builder.validate_release_pair_parity(
    previous_archive,
    RELEASE_VERSION,
    records,
)
assert parity_result["reference_version"] == previous_version
assert parity_result["current_version"] == RELEASE_VERSION
assert parity_result["functional_file_count"] == len(EXPECTED_SOURCE_FILES)

lf_previous_sources = [dict(record) for record in previous_source_records]
for lf_record in lf_previous_sources:
    member = PurePosixPath(str(lf_record["path"]))
    if member not in builder.CANONICAL_CRLF_SOURCE_FILES:
        continue
    lf_data = bytes(lf_record["data"]).replace(b"\r\n", b"\n")
    lf_record.update(
        bytes=len(lf_data),
        data=lf_data,
        sha256=builder.digest(lf_data),
    )
lf_previous_archive = builder.make_archive(
    builder.make_release_records(previous_version, lf_previous_sources),
    archive_date_time,
)
builder.validate_release_pair_parity(
    lf_previous_archive,
    RELEASE_VERSION,
    records,
)

tampered_previous_sources = [dict(record) for record in previous_source_records]
tampered_python_record = next(
    record
    for record in tampered_previous_sources
    if record["path"] == "HMBAgentLibrary.py"
)
tampered_python_data = bytes(tampered_python_record["data"]) + b"# parity mutation\n"
tampered_python_record.update(
    bytes=len(tampered_python_data),
    data=tampered_python_data,
    sha256=builder.digest(tampered_python_data),
)
tampered_previous_archive = builder.make_archive(
    builder.make_release_records(previous_version, tampered_previous_sources),
    archive_date_time,
)
try:
    builder.validate_release_pair_parity(
        tampered_previous_archive,
        RELEASE_VERSION,
        records,
    )
except RuntimeError:
    pass
else:
    raise AssertionError("Release parity accepted a Python behavior change.")
with tempfile.TemporaryDirectory(prefix="hmb-release-parity-") as temporary_root:
    temporary_path = Path(temporary_root)
    previous_archive_path = (
        temporary_path
        / f"HMB_GP_Production_{builder.release_label_for_version(previous_version)}"
        "_Runtime.zip"
    )
    previous_archive_path.write_bytes(previous_archive)
    checked_pair = builder.check_parity(
        previous_archive_path,
        builder.digest(previous_archive),
    )
    assert checked_pair["parity"] is True
    try:
        builder.check_parity(previous_archive_path, "0" * 64)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Release parity accepted the wrong trusted ZIP SHA256.")
    current_parts = builder.release_version_parts(RELEASE_VERSION)
    if current_parts[2] % 2 == 0:
        current_archive_path = temporary_path / builder.ARCHIVE_NAME
        current_archive_path.write_bytes(first_archive)
        proof_path = temporary_path / "hmb-release-parity.json"
        written_proof = builder.write_parity_proof(
            proof_path,
            current_archive_path,
        )
        assert written_proof["tested_even_version"] == RELEASE_VERSION
        target_odd_version = written_proof["target_odd_version"]
        proof_payload = json.loads(proof_path.read_text(encoding="utf-8"))
    else:
        tested_even_version = (
            f"{current_parts[0]}.{current_parts[1]}.{current_parts[2] - 1}"
        )
        target_odd_version = RELEASE_VERSION
        proof_payload = {
            "canonical_source_sha256": builder.canonical_source_fingerprint(records),
            "schema": builder.RELEASE_PARITY_PROOF_SCHEMA,
            "target_odd_release_label": builder.release_label_for_version(
                target_odd_version
            ),
            "target_odd_version": target_odd_version,
            "tested_even_archive_sha256": builder.digest(first_archive),
            "tested_even_release_label": builder.release_label_for_version(
                tested_even_version
            ),
            "tested_even_version": tested_even_version,
            "version": builder.RELEASE_PARITY_PROOF_VERSION,
        }
    validated_proof = builder.validate_parity_proof_payload(
        proof_payload,
        target_odd_version,
        records,
    )
    assert validated_proof["parity"] is True
    mutated_proof_sources = [dict(record) for record in records]
    mutated_proof_record = next(
        record
        for record in mutated_proof_sources
        if record["path"] == "HMBPromptLibrary.py"
    )
    mutated_proof_record["data"] = (
        bytes(mutated_proof_record["data"]) + b"# parity proof mutation\n"
    )
    try:
        builder.validate_parity_proof_payload(
            proof_payload,
            target_odd_version,
            mutated_proof_sources,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Parity proof accepted a behavior-surface mutation.")
check_result = builder.check()
assert check_result["validated"] is True
assert check_result["file_count"] == len(EXPECTED_SOURCE_FILES) + 2
assert check_result["source_file_count"] == len(EXPECTED_SOURCE_FILES)
assert check_result["install_file_count"] == len(EXPECTED_RUNTIME_INSTALL_FILES)
assert check_result["distribution_file_count"] == len(EXPECTED_DISTRIBUTION_ONLY_FILES)
assert check_result["policy_delivery"] == "bundled-signed-dat"
assert "policy_version" not in check_result
assert "policy_contract_sha256" not in check_result
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
    dat_members = [
        info for info in infos
        if PurePosixPath(info.filename).suffix.casefold() == ".dat"
    ]
    assert len(dat_members) == 1
    assert PurePosixPath(dat_members[0].filename).parts[-3:] == (
        "resources", "agent", "hmb_agent_core.dat"
    )

    for info in infos:
        member = PurePosixPath(info.filename)
        lowered = info.filename.casefold()
        relative = member.relative_to(builder.ARCHIVE_ROOT).as_posix()
        # The signed Agent DAT is the sole permitted policy artifact. Private
        # keys, PEM files, other DAT files and review/source documents remain
        # forbidden, including look-alike paths.
        if relative == builder.BUNDLED_AGENT_POLICY_MEMBER.as_posix():
            assert member.suffix.casefold() == ".dat"
            builder.verify_signed_agent_policy_bytes(archive.read(info))
        else:
            assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
        if "/resources/agent/" in f"/{lowered}":
            assert relative == builder.BUNDLED_AGENT_POLICY_MEMBER.as_posix()
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

# The exact signed runtime DAT is allowed, while all other DAT and policy
# documents remain forbidden. Inspect nested ZIPs because installers may wrap
# the library ZIP in another ZIP.
safe_nested = zip_bytes({"docs/readme.txt": b"safe"})
builder.validate_no_policy_artifacts_in_zip(
    zip_bytes({"package/safe.zip": safe_nested})
)
assert_forbidden_archive(zip_bytes({"package/hmb_agent_core.dat": b"sealed"}))
signed_dat = (ROOT / "resources" / "agent" / "hmb_agent_core.dat").read_bytes()
builder.verify_signed_agent_policy_bytes(signed_dat)
builder.make_archive(
    [{"path": "resources/agent/hmb_agent_core.dat", "data": signed_dat}],
    archive_date_time,
)
builder.validate_no_policy_artifacts_in_zip(
    zip_bytes(
        {
            "package/library.zip": zip_bytes(
                {"HMB_GP_Production/resources/agent/hmb_agent_core.dat": signed_dat}
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
assert "resources/policy/" in gitignore
assert "policies/" in gitignore
assert "**/hmb_agent_core.dat" in gitignore
assert "!resources/agent/hmb_agent_core.dat" in gitignore

print("HMB bundled signed-DAT release/credential boundary regression: PASS")
