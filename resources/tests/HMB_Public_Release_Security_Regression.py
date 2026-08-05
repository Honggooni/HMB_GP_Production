from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
RELEASE_MANIFEST = ROOT / "dist" / "release-manifest.json"
EXPECTED_SECRET_NAMES = {
    "ARK_API_KEY",
    "GT_CLOUD_API_KEY",
    "GT_CLOUD_BUCKET_ID",
    "TOS_ACCESS_KEY_ID",
    "TOS_SECRET_ACCESS_KEY",
    "TOS_BUCKET_NAME",
}
FORBIDDEN_SUFFIXES = {".env", ".jwk", ".key", ".p12", ".pem", ".pfx"}
PRIVATE_KEY_HEADER = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
COMMON_TOKEN_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"gh[opsu]_[A-Za-z0-9]{30,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
)


manifest = json.loads(
    (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
)
registered_secrets = manifest["settings"][0]["contents"]["secrets_to_register"]
assert set(registered_secrets) == EXPECTED_SECRET_NAMES
assert all(value == "" for value in registered_secrets.values())
assert not (ROOT / "resources" / "agent" / "hmb_agent_core.dat").exists()
release_manifest_bytes = RELEASE_MANIFEST.read_bytes()
release_manifest = json.loads(release_manifest_bytes.decode("utf-8"))
external_policy = release_manifest["external_agent_policy"]
assert external_policy == {
    "bundled": False,
    "envelope_schema": "hmb-agent-policy-envelope-v3",
    "maximum_decompressed_bytes": 512 * 1024,
    "maximum_envelope_bytes": 128 * 1024,
    "path_env": "HMB_AGENT_POLICY_PATH",
    "signature_algorithm": "RSASSA-PKCS1-v1_5-SHA256",
    "signing_key_id": "hmb-policy-release-2026-08",
}
assert "validated" not in external_policy
assert "envelope_sha256" not in external_policy

configured_secret_values = tuple(
    value.encode("utf-8")
    for name in EXPECTED_SECRET_NAMES
    if len(value := os.environ.get(name, "")) >= 8
)
configured_policy_path = os.environ.get("HMB_AGENT_POLICY_PATH", "").encode("utf-8")
if configured_policy_path:
    assert configured_policy_path not in release_manifest_bytes

archive_names = [str(item["name"]) for item in release_manifest["archives"]]
assert archive_names == ["HMB_GP_Production.zip"]
for archive_name in archive_names:
    assert Path(archive_name).name == archive_name
    archive_path = ROOT / "dist" / archive_name
    assert archive_path.is_file(), f"Release archive is missing: {archive_name}"
    with zipfile.ZipFile(archive_path, "r") as archive:
        infos = archive.infolist()
        assert len(infos) == 25
        assert not archive.testzip()
        for info in infos:
            member = PurePosixPath(info.filename)
            lowered = info.filename.casefold()
            assert member.name.casefold() != "hmb_agent_core.dat"
            assert member.suffix.casefold() not in FORBIDDEN_SUFFIXES
            assert "/resources/agent/" not in f"/{lowered}"
            content = archive.read(info)
            assert PRIVATE_KEY_HEADER.search(content) is None
            assert not any(pattern.search(content) for pattern in COMMON_TOKEN_PATTERNS)
            assert not any(secret in content for secret in configured_secret_values)

print("HMB public release policy/credential boundary regression: PASS")
