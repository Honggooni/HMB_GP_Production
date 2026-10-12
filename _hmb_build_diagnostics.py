"""Read-only build identity; never reads credentials, policy source or media.

Hashes are observations of this directory, not proof of a GitHub publication.
The installer receipt is an unsigned local observation. Signed policy trust is
reported independently using the production verifier, never inferred from a hash.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import hmac
import json
import re
import zlib
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "hmb-build-diagnostics"
RECEIPT_NAME = ".hmb-install-receipt.json"
RUNTIME_FILE_PATHS = (
    "__init__.py", "griptape-nodes-library.json", "HMBAgentLibrary.py",
    "HMBColorLUTLibrary.py", "HMBFinishLookLibrary.py", "HMBImageAssetLibrary.py",
    "HMBPromptLibrary.py", "HMBSeedanceGeneration.py", "HMBVideoPickerLibrary.py",
    "_hmb_agent_media.py", "_hmb_agent_session.py", "_hmb_build_diagnostics.py",
    "_hmb_library_bootstrap.py", "_hmb_review.py", "_hmb_shot_routing.py", "_hmb_mp4_verify.py", "_hmb_common.py",
    "_hmb_color_lut.py", "_hmb_screen_space.py", "_hmb_video_tools.py",
    "widgets/HMBAgentLibraryWidget.js", "widgets/HMBColorLUTLibraryWidget.js",
    "widgets/HMBFinishLookLibraryWidget.js", "widgets/HMBImageAssetLibraryWidget.js",
    "widgets/HMBImageAssetThumbnailPatchBridgeWidget.js",
    "widgets/HMBPromptLibraryScopedBindingWidget.js", "widgets/HMBSeedanceGenerationWidget.js",
    "widgets/HMBVideoPickerCommandBridgeWidget_v032.js",
    "widgets/HMBVideoPickerLibraryWidget_v032.js",
    "resources/maya/HMB_Maya_Background_Preview.py",
    "resources/blender/HMB_Blender_Background_Preview.py",
    "resources/picker/HMB_Marker_Catalog.json", "resources/agent/hmb_agent_core.dat",
)
_MAX_FILE_BYTES = 16 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")


def inventory_fingerprint(records: list[dict[str, Any]]) -> str:
    """Hash a sorted path/size/hash inventory without timestamps or machine paths."""
    rows = sorted(
        ({"path": str(r["path"]), "bytes": int(r["bytes"]), "sha256": str(r["sha256"])}
         for r in records), key=lambda row: row["path"],
    )
    data = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _read(root: Path, relative: str, limit: int = _MAX_FILE_BYTES) -> bytes:
    path = root / relative
    # Refuse linked directories too: diagnostics must not follow an arbitrary
    # installed link into credentials or an unrelated library.
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part.is_symlink() or getattr(part.stat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("linked_member")
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("invalid_member")
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("oversized_member")
    return data


def _json(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads(_read(root, relative, 2 * 1024 * 1024).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("invalid_document")
    return value


def _sha(value: Any) -> str:
    value = str(value or "").lower()
    return value if _HEX.fullmatch(value) else ""


def _expected_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("invalid_inventory")
    rows, seen = [], set()
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("invalid_record")
        name = str(row.get("path") or "")
        member = PurePosixPath(name)
        if (name not in RUNTIME_FILE_PATHS or member.is_absolute() or ":" in name
                or "\\" in name or ".." in member.parts or name in seen
                or type(row.get("bytes")) is not int or row["bytes"] < 0
                or not _sha(row.get("sha256"))):
            raise ValueError("invalid_record")
        seen.add(name)
        rows.append({"path": name, "bytes": row["bytes"], "sha256": _sha(row["sha256"])})
    if seen != set(RUNTIME_FILE_PATHS):
        raise ValueError("incomplete_inventory")
    return rows


def _verify_policy(root: Path, encoded: bytes) -> dict[str, str]:
    # Execute only the production pure trust functions, byte-for-byte as AST
    # definitions. Do not import SDK, create .pyc, initialize a policy session,
    # fetch a DAT or read the credential helpers in this shared module.
    names = {"_json_object_without_duplicates", "_reject_json_constant", "_strict_json_bytes",
             "_canonical_json_bytes", "_strict_base64", "_verify_rsa_pkcs1_v15_sha256",
             "_verify_agent_policy_signature", "_decode_signed_agent_policy_envelope",
             "_validate_agent_policy_payload"}
    # The optional diagnostic target is data, not executable trust code. Always
    # use the verifier shipped beside this helper, including when inspecting a
    # different installed directory or historical archive.
    trusted_root = Path(__file__).resolve().parent
    tree = ast.parse(_read(trusted_root, "_hmb_common.py").decode("utf-8-sig"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in functions} != names or len(functions) != len(names):
        raise RuntimeError("verifier_unavailable")
    definitions = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])
    ast.fix_missing_locations(definitions)
    namespace: dict[str, Any] = {"base64": base64, "hashlib": hashlib, "hmac": hmac,
                                 "json": json, "re": re, "zlib": zlib, "Any": Any, "Dict": dict}
    exec(compile(definitions, "<production-policy-verifier>", "exec"), namespace)
    payload = namespace["_validate_agent_policy_payload"](namespace["_decode_signed_agent_policy_envelope"](encoded))
    return {"policy_version": str(payload["final_policy_version"]),
            "policy_pair_sha256": str(payload["policy_pair_sha256"])}


def get_build_diagnostics(root: str | Path | None = None, *, verify_policy: bool = True) -> dict[str, Any]:
    """Return bounded JSON diagnostics without writes or external requests."""
    directory = Path(root) if root is not None else Path(__file__).resolve().parent
    directory = directory.absolute()
    records, missing, unreadable, hashes = [], [], [], {}
    for relative in RUNTIME_FILE_PATHS:
        try:
            data = _read(directory, relative)
        except FileNotFoundError:
            missing.append(relative)
            continue
        except (OSError, ValueError):
            unreadable.append(relative)
            continue
        digest = hashlib.sha256(data).hexdigest()
        hashes[relative] = digest
        records.append({"path": relative, "bytes": len(data), "sha256": digest})
    fingerprint = inventory_fingerprint(records) if not missing and not unreadable else ""
    try:
        metadata = _json(directory, "griptape-nodes-library.json").get("metadata", {})
    except (OSError, ValueError, UnicodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    version = str(metadata.get("library_version") or "")[:80]
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
    channel = ("local_even" if int(match[3]) % 2 == 0 else "team_odd") if match else "unknown"
    delivery = metadata.get("agent_policy_delivery", {})
    if not isinstance(delivery, dict):
        delivery = {}
    policy = {"envelope_sha256": hashes.get("resources/agent/hmb_agent_core.dat", ""),
              "signature_status": "not_checked", "policy_version": "", "policy_pair_sha256": "",
              "declared_version": str(delivery.get("policy_version") or "")[:120],
              "declared_contract_sha256": _sha(delivery.get("contract_sha256")),
              "status": "not_checked", "source_status": "not_inspected",
              "verification_basis": "diagnostic_bundle_production_trust_anchor"}
    if verify_policy:
        try:
            encoded = _read(directory, "resources/agent/hmb_agent_core.dat", 128 * 1024)
            policy.update(_verify_policy(directory, encoded))
            policy["signature_status"] = "verified"
            policy["status"] = ("verified" if policy["policy_version"] == policy["declared_version"]
                                and policy["policy_pair_sha256"] == policy["declared_contract_sha256"]
                                and policy["envelope_sha256"] == _sha(delivery.get("envelope_sha256"))
                                else "metadata_mismatch")
        except FileNotFoundError:
            policy["signature_status"] = policy["status"] = "unavailable"
        except Exception:
            # Error text can contain decoded policy. Return a stable code only.
            policy["signature_status"] = policy["status"] = "invalid_or_verifier_unavailable"
    package = {"manifest_status": "not_available", "verification_status": "not_checked",
               "declared_fingerprint_sha256": "", "build_fingerprint_sha256": "", "mismatch_paths": []}
    install = {"receipt_status": "not_available", "installed_at": "", "source_manifest_sha256": ""}
    observations = [("release-manifest.json", "manifest"), (RECEIPT_NAME, "receipt")]
    for name, kind in observations:
        try:
            document = _json(directory, name)
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError):
            if kind == "receipt":
                install["receipt_status"] = "invalid"
            else:
                package["manifest_status"] = "invalid"
            continue
        try:
            if kind == "receipt":
                if document.get("schema") != "hmb-install-receipt" or document.get("version") != 1:
                    raise ValueError("invalid_receipt")
                rows = _expected_records(document.get("runtime_files"))
                install.update(receipt_status="observed", installed_at=str(document.get("installed_at") or "")[:80],
                               source_manifest_sha256=_sha(document.get("source_manifest_sha256")))
            else:
                if document.get("schema") != "hmb-release-closure" or document.get("version") != 1:
                    raise ValueError("invalid_manifest")
                rows = _expected_records([r for r in document.get("files", []) if isinstance(r, dict) and r.get("install") is True])
                package["manifest_status"] = "observed"
            declared = _sha(document.get("runtime_fingerprint_sha256"))
            if declared != inventory_fingerprint(rows) or document.get("release_version") != version:
                raise ValueError("identity_mismatch")
            differences = sorted(r["path"] for r in rows if hashes.get(r["path"]) != r["sha256"])
            package.update(declared_fingerprint_sha256=declared,
                           build_fingerprint_sha256=_sha(document.get("build_fingerprint_sha256")),
                           mismatch_paths=differences,
                           verification_status="matches_recorded_inventory" if not differences else "mismatch")
            if kind == "receipt":
                install["receipt_status"] = "matches_recorded_inventory" if not differences else "mismatch"
            # A package manifest has the same authority as a local receipt:
            # both are unsigned. Do not label either verified publisher trust.
        except (ValueError, TypeError, KeyError):
            if kind == "receipt":
                install["receipt_status"] = "invalid"
            else:
                package["manifest_status"] = "invalid"
    return {"schema": SCHEMA, "version": 1, "library_version": version, "channel": channel,
            "runtime": {"fingerprint_sha256": fingerprint, "file_count": len(RUNTIME_FILE_PATHS),
                        "present_count": len(records), "file_sha256": hashes,
                        "missing_paths": missing, "unreadable_paths": unreadable},
            "policy": policy, "package": package, "install": install}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read-only HMB build and signed-policy diagnostics")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--skip-policy-verification", action="store_true")
    args = parser.parse_args()
    print(json.dumps(get_build_diagnostics(args.root, verify_policy=not args.skip_policy_verification), ensure_ascii=False, sort_keys=True, indent=2))
