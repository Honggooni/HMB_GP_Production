from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ARCHIVE = DIST / "HMB_GP_Production.zip"
MANIFEST = DIST / "release-manifest.json"
CHECKSUMS = DIST / "SHA256SUMS"
POLICY_RELATIVE = "resources/agent/hmb_agent_core.dat"
POLICY_SHA256 = "6152355dd51d68da33d4df197e6ac52f2c13b37d9644aa50efd9ba8c2cf13619"
POLICY_VERSION = "2026-08-06.animation-look-continuity.v3"
POLICY_CONTRACT_SHA256 = (
    "ab5b63a42717293cc097d51bf3048b5309c0ff52644bd0121b3045f6eeadae93"
)
POLICY_SIGNING_KEY_ID = "hmb-policy-release-2026-08-r2"
RETIRED_SHARE_MARKER = b"".join((b"00", b".", b"CompSource"))
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
    POLICY_RELATIVE,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_policy_verifier():
    spec = importlib.util.spec_from_file_location(
        "_hmb_release_policy_verifier", ROOT / "_hmb_common.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Bundled policy verifier could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_sources() -> tuple[str, list[dict[str, object]]]:
    library_manifest = json.loads(
        (ROOT / "griptape-nodes-library.json").read_text(encoding="utf-8")
    )
    release_version = str(
        library_manifest.get("metadata", {}).get("library_version", "")
    ).strip()
    if not release_version:
        raise RuntimeError("Library release version is missing.")
    records: list[dict[str, object]] = []
    for relative in SOURCE_FILES:
        member = PurePosixPath(relative)
        if member.is_absolute() or ".." in member.parts or "\\" in relative:
            raise RuntimeError(f"Unsafe release path: {relative}")
        path = ROOT / Path(relative)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Missing or linked release member: {relative}")
        data = path.read_bytes()
        if RETIRED_SHARE_MARKER in data:
            raise RuntimeError(f"Retired source-share reference in {relative}")
        records.append(
            {"bytes": len(data), "path": relative, "sha256": sha256(data)}
        )
    policy = (ROOT / POLICY_RELATIVE).read_bytes()
    if sha256(policy) != POLICY_SHA256:
        raise RuntimeError("Bundled policy envelope SHA-256 mismatch.")
    verifier = load_policy_verifier()
    payload = verifier._decode_signed_agent_policy_envelope(policy)
    verifier._validate_agent_policy_payload(payload)
    if (
        payload.get("final_policy_version") != POLICY_VERSION
        or payload.get("final_motion_look_policy_sha256")
        != POLICY_CONTRACT_SHA256
    ):
        raise RuntimeError("Bundled policy identity mismatch.")
    return release_version, records


def write_archive(records: list[dict[str, object]]) -> None:
    with zipfile.ZipFile(
        ARCHIVE,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for record in records:
            relative = str(record["path"])
            data = (ROOT / Path(relative)).read_bytes()
            info = zipfile.ZipInfo(
                f"HMB_GP_Production/{relative}", (2020, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> None:
    release_version, records = validate_sources()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    write_archive(records)
    archive_bytes = ARCHIVE.read_bytes()
    manifest = {
        "agent_policy": {
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
        },
        "archives": [
            {
                "bytes": len(archive_bytes),
                "name": ARCHIVE.name,
                "sha256": sha256(archive_bytes),
            }
        ],
        "contract_sha256": POLICY_CONTRACT_SHA256,
        "policy_version": POLICY_VERSION,
        "release_version": release_version,
        "reproducible_zip": {
            "compression": "deflate-9",
            "member_mode": "100644",
            "member_timestamp": "2020-01-01T00:00:00Z",
        },
        "schema": "hmb-release-manifest-v1",
        "source_files": records,
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    CHECKSUMS.write_text(
        f"{sha256(archive_bytes)}  {ARCHIVE.name}\n"
        f"{sha256(MANIFEST.read_bytes())}  {MANIFEST.name}\n",
        encoding="ascii",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "archive_sha256": sha256(archive_bytes),
                "file_count": len(records),
                "release_version": release_version,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
