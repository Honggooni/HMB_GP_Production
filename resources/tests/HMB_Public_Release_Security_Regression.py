from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
RELEASE_MANIFEST = ROOT / "dist" / "release-manifest.json"
POLICY_RELATIVE = "resources/agent/hmb_agent_core.dat"
POLICY_SHA256 = "94533d84ab914971026f624634c2553a0c7abba298f6dd76242d996ee5c9137f"
POLICY_VERSION = "2026-08-01.goal-final-authority.v2"
POLICY_CONTRACT_SHA256 = (
    "a17809e4103628c1b0ab0b96081f6325faf9d16703a5fac57ef7d1eaa7d043bf"
)
EXPECTED_SECRET_NAMES = {
    "ARK_API_KEY",
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
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())
source_policy_path = ROOT / Path(POLICY_RELATIVE)
source_policy = source_policy_path.read_bytes()
assert digest(source_policy) == POLICY_SHA256
source_payload = common._decode_signed_agent_policy_envelope(source_policy)
common._validate_agent_policy_payload(source_payload)
assert source_payload["final_policy_version"] == POLICY_VERSION
assert source_payload["final_motion_look_policy_sha256"] == POLICY_CONTRACT_SHA256

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
    "path_env": "HMB_AGENT_POLICY_PATH",
    "policy_version": POLICY_VERSION,
    "resolution_order": ["external", "bundled"],
    "signature_algorithm": "RSASSA-PKCS1-v1_5-SHA256",
    "signing_key_id": "hmb-policy-release-2026-08",
    "validated": True,
}
assert release_manifest["release_version"] == "0.5.15"
assert release_manifest["policy_version"] == POLICY_VERSION
assert release_manifest["contract_sha256"] == POLICY_CONTRACT_SHA256
source_files = {
    str(item["path"]): item for item in release_manifest["source_files"]
}
assert len(source_files) == 26
assert source_files[POLICY_RELATIVE]["sha256"] == POLICY_SHA256

configured_secret_values = tuple(
    value.encode("utf-8")
    for name in EXPECTED_SECRET_NAMES
    if len(value := os.environ.get(name, "")) >= 8
)
configured_policy_path = os.environ.get("HMB_AGENT_POLICY_PATH", "").encode("utf-8")
if configured_policy_path:
    assert configured_policy_path not in release_manifest_bytes
source_policy_path_bytes = str(source_policy_path.resolve()).encode("utf-8")
assert source_policy_path_bytes not in release_manifest_bytes

archive_names = [str(item["name"]) for item in release_manifest["archives"]]
assert archive_names == ["HMB_GP_Production.zip"]
for archive_name in archive_names:
    assert Path(archive_name).name == archive_name
    archive_path = ROOT / "dist" / archive_name
    assert archive_path.is_file(), f"Release archive is missing: {archive_name}"
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos = archive.infolist()
        assert len(infos) == 26
        assert not archive.testzip()
        expected_policy_member = f"HMB_GP_Production/{POLICY_RELATIVE}"
        dat_members = [
            info.filename
            for info in infos
            if PurePosixPath(info.filename).suffix.casefold() == ".dat"
        ]
        assert dat_members == [expected_policy_member]
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

print("HMB bundled-policy release/credential boundary regression: PASS")
