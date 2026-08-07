from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
RELEASE_MANIFEST = DIST / "release-manifest.json"
RELEASE_ARCHIVE = DIST / "HMB_GP_Production.zip"
RELEASE_CHECKSUMS = DIST / "SHA256SUMS"
POLICY_RELATIVE = "resources/agent/hmb_agent_core.dat"
POLICY_SHA256 = "6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619"
POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
POLICY_CONTRACT_SHA256 = (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
POLICY_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
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


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


common_spec = importlib.util.spec_from_file_location(
    "_hmb_public_release_policy_verifier",
    ROOT / "_hmb_common.py",
)
assert common_spec is not None and common_spec.loader is not None
common = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common)

manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
assert manifest["metadata"]["library_version"] == "0.5.21"
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())

# The two full Seedance transport regressions require a live Griptape host. Keep
# their critical output-macro boundary enforced in source-only CI as well:
# normal generation and Refresh must both use the shared preflight, and only the
# engine-assigned {_index} variable may be deferred until the write stage.
seedance_source = (ROOT / "HMBSeedance20VideoGeneration.py").read_text(
    encoding="utf-8"
)
seedance_tree = ast.parse(seedance_source, filename="HMBSeedance20VideoGeneration.py")
seedance_class = next(
    node
    for node in seedance_tree.body
    if isinstance(node, ast.ClassDef)
    and node.name == "HMBSeedance20VideoGeneration"
)
seedance_methods = {
    node.name: node
    for node in seedance_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
preflight_method = seedance_methods["_preflight_output_destination"]
preflight_source = ast.get_source_segment(seedance_source, preflight_method) or ""
assert 'marker = "missing required variables:"' in preflight_source
assert 'if missing != {"_index"}:' in preflight_source
assert sum(
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and node.func.attr == "resolve"
    for node in ast.walk(preflight_method)
) == 1
for execution_method_name in ("_refresh_async", "_process_generation_impl"):
    execution_method = seedance_methods[execution_method_name]
    assert sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_preflight_output_destination"
        for node in ast.walk(execution_method)
    ) == 1
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
        for node in ast.walk(execution_method)
    )

source_policy_path = ROOT / Path(POLICY_RELATIVE)
source_policy = source_policy_path.read_bytes()
assert digest(source_policy) == POLICY_SHA256
assert common._AGENT_POLICY_VERSION == POLICY_VERSION
assert common._AGENT_POLICY_CONTRACT_SHA256 == POLICY_CONTRACT_SHA256
assert common._AGENT_POLICY_SIGNING_KEY_ID == POLICY_SIGNING_KEY_ID
assert Path(common._BUNDLED_AGENT_POLICY_FILE).resolve() == source_policy_path.resolve()
assert common._read_agent_policy_envelope() == source_policy
source_payload = common._decode_signed_agent_policy_envelope(source_policy)
common._validate_agent_policy_payload(source_payload)
assert source_payload["final_policy_version"] == POLICY_VERSION
assert source_payload["final_motion_look_policy_sha256"] == POLICY_CONTRACT_SHA256

configured_secret_values = tuple(
    value.encode("utf-8")
    for name in EXPECTED_SECRET_NAMES
    if len(value := os.environ.get(name, "")) >= 8
)
source_policy_path_bytes = str(source_policy_path.resolve()).encode("utf-8")

# A clean checkout has no generated dist directory. Validate the immutable
# source boundary in that mode, and additionally validate every release output
# whenever a complete local build is present.
release_outputs = (RELEASE_MANIFEST, RELEASE_ARCHIVE, RELEASE_CHECKSUMS)
output_presence = tuple(path.is_file() for path in release_outputs)
assert not any(output_presence) or all(output_presence), (
    "Release outputs must be either absent or present as a complete set."
)
archive_verified = False
if all(output_presence):
    release_manifest_bytes = RELEASE_MANIFEST.read_bytes()
    release_manifest = json.loads(release_manifest_bytes.decode("utf-8"))
    agent_policy = release_manifest["agent_policy"]
    assert agent_policy == {
        "bundled": True,
        "bundled_path": POLICY_RELATIVE,
        "contract_sha256": POLICY_CONTRACT_SHA256,
        "envelope_schema": "hmb-agent-policy-envelope-v3",
        "envelope_sha256": POLICY_SHA256,
        "maximum_decompressed_bytes": 512 * 1024,
        "maximum_envelope_bytes": 128 * 1024,
        "policy_version": POLICY_VERSION,
        "resolution_order": ["bundled"],
        "signature_algorithm": "RSASSA-PKCS1-v1_5-SHA256",
        "signing_key_id": POLICY_SIGNING_KEY_ID,
        "validated": True,
    }
    assert release_manifest["release_version"] == "0.5.21"
    assert release_manifest["policy_version"] == POLICY_VERSION
    assert release_manifest["contract_sha256"] == POLICY_CONTRACT_SHA256
    source_files = {
        str(item["path"]): item for item in release_manifest["source_files"]
    }
    assert len(source_files) == 25
    assert source_files[POLICY_RELATIVE]["sha256"] == POLICY_SHA256
    assert "CHANGELOG.md" not in source_files
    assert "resources/build_release.py" not in source_files
    assert not any(
        PurePosixPath(path).name.casefold() == "build_release.py"
        for path in source_files
    )
    assert source_policy_path_bytes not in release_manifest_bytes

    archive_names = [str(item["name"]) for item in release_manifest["archives"]]
    assert archive_names == [RELEASE_ARCHIVE.name]
    with zipfile.ZipFile(RELEASE_ARCHIVE, "r") as archive:
        infos = archive.infolist()
        assert len(infos) == 25
        assert not archive.testzip()
        expected_policy_member = f"HMB_GP_Production/{POLICY_RELATIVE}"
        dat_members = [
            info.filename
            for info in infos
            if PurePosixPath(info.filename).suffix.casefold() == ".dat"
        ]
        assert dat_members == [expected_policy_member]
        assert "HMB_GP_Production/CHANGELOG.md" not in {
            info.filename for info in infos
        }
        assert not any(
            PurePosixPath(info.filename).name.casefold() == "build_release.py"
            for info in infos
        )
        for info in infos:
            member = PurePosixPath(info.filename)
            lowered = info.filename.casefold()
            assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
            if "/resources/agent/" in f"/{lowered}":
                assert info.filename == expected_policy_member
            assert not re.search(
                r"(^|/)(?:credentials|secrets)[^/]*\.json$",
                lowered,
            )
            assert not re.search(r"(^|/)(?:id_rsa|id_ed25519)[^/]*$", lowered)
            content = archive.read(info)
            assert PRIVATE_KEY_HEADER.search(content) is None
            assert not any(pattern.search(content) for pattern in COMMON_TOKEN_PATTERNS)
            assert not any(secret in content for secret in configured_secret_values)
            assert source_policy_path_bytes not in content
        archived_policy = archive.read(expected_policy_member)
        assert archived_policy == source_policy
        assert digest(archived_policy) == POLICY_SHA256
        archived_payload = common._decode_signed_agent_policy_envelope(
            archived_policy
        )
        common._validate_agent_policy_payload(archived_payload)
        assert archived_payload["final_policy_version"] == POLICY_VERSION
        assert (
            archived_payload["final_motion_look_policy_sha256"]
            == POLICY_CONTRACT_SHA256
        )

    checksum_records = {}
    for line in RELEASE_CHECKSUMS.read_text(encoding="utf-8").splitlines():
        expected_hash, filename = line.split("  ", 1)
        checksum_records[filename] = expected_hash
    assert set(checksum_records) == {
        RELEASE_ARCHIVE.name,
        RELEASE_MANIFEST.name,
    }
    for filename, expected_hash in checksum_records.items():
        assert digest((DIST / filename).read_bytes()) == expected_hash
    archive_verified = True

mode = "source and 25-file archive" if archive_verified else "source-only"
print(f"HMB bundled-policy release/credential boundary regression: PASS ({mode})")
