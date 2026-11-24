"""Select an approved Local library and pinned Desktop through one stable Windows launcher."""
from __future__ import annotations

import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile

PRODUCT = "HMB_GP_Production"
RECEIPT = ".hmb-install-receipt.json"
STABLE = "Start-HMB.cmd"
MARKER = b"@rem HMB approved Local release launcher\r\n"
RUNNER = "verify_and_start.py"
SPEC = "release.json"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def check_library(selection):
    library = Path(selection["library"])
    receipt = json.loads((library / RECEIPT).read_bytes())
    for key in ("release_version", "stage_local_archive_sha256", "source_manifest_sha256"):
        if receipt.get(key) != selection[key]:
            raise ValueError(f"The Local install receipt changed ({key}).")
    for row in selection["files"]:
        file = library / row["path"]
        if (file.resolve() != file or not file.is_relative_to(library)
                or file.stat().st_size != row["bytes"] or digest(file) != row["sha256"]):
            raise ValueError(f"The approved HMB file changed: {row['path']}")


def select(gold, library, archive, archive_sha256):
    gold, library = gold.absolute(), library.absolute()
    if (not re.fullmatch(r"desktop-\d+\.\d+\.\d+-[0-9a-f]{8}-[0-9a-f]{8}", gold.name)
            or gold.resolve() != gold or gold.parent.name != "hosts"
            or gold.parent.parent.name != PRODUCT or library.resolve() != library):
        raise ValueError("The installation path is not a regular HMB installation.")
    if digest(archive) != archive_sha256:
        raise ValueError("Local release ZIP differs from the approved SHA-256.")
    record = json.loads((gold / "hmb-host.json").read_bytes())
    for name in ("hmb_start_desktop.py", "resources\\engine-bundle\\python\\python.exe"):
        if digest(gold / name) != record["files"][name]:
            raise ValueError(f"Private Desktop launcher changed: {name}")
    with ZipFile(archive) as release:
        raw = release.read(f"{PRODUCT}/release-manifest.json")
    manifest = json.loads(raw)
    version = manifest["release_version"]
    if manifest["library"] != PRODUCT or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Unrecognized release manifest.")
    # Release ZIP documentation and its one-shot installer do not belong to the live library.
    distribution_only = {"Install_HMB_GP_Production.ps1", "SBOM.spdx.json", "THIRD_PARTY_NOTICES.md", "LICENSE"}
    files = [row for row in manifest["files"] if row["path"] not in distribution_only]
    receipt = json.loads((library / RECEIPT).read_bytes())
    owned = {row["path"]: row["sha256"] for key in ("runtime_files", "editor_support_files") for row in receipt[key]}
    if owned != {row["path"]: row["sha256"] for row in files}:
        raise ValueError("The approved ZIP and owned installed files differ.")
    selection = {"library": str(library), "gold": gold.name, "release_version": version, "files": files,
                 "stage_local_archive_sha256": archive_sha256, "source_manifest_sha256": sha256(raw).hexdigest()}
    check_library(selection)
    encoded = (json.dumps(selection, indent=2, ensure_ascii=False) + "\n").encode()
    implementation = Path(__file__).read_bytes()
    identity = sha256(implementation + encoded).hexdigest()[:16]
    home = gold.parent.parent
    launchers = home / "launchers"
    target = launchers / f"v{version}-{identity}"
    stable = home / STABLE
    if stable.exists() and not stable.read_bytes().startswith(MARKER):
        raise ValueError("The existing Start-HMB.cmd is not owned by the HMB launcher.")
    launchers.mkdir(exist_ok=True)
    if launchers.resolve() != launchers or stable.resolve() != stable:
        raise ValueError("The launcher path is redirected.")
    if not target.exists():
        with TemporaryDirectory(dir=launchers) as temp:
            candidate = Path(temp) / "selected"
            candidate.mkdir()
            (candidate / RUNNER).write_bytes(implementation)
            (candidate / SPEC).write_bytes(encoded)
            try:
                candidate.rename(target)
            except FileExistsError:
                pass
    if target.resolve() != target or (target / RUNNER).read_bytes() != implementation or (target / SPEC).read_bytes() != encoded:
        raise ValueError("The selected private launcher differs from its receipt.")
    batch = MARKER + (
        '@echo off\r\nsetlocal\r\n'
        f'"%~dp0hosts\\{gold.name}\\resources\\engine-bundle\\python\\python.exe" -I -B '
        f'"%~dp0launchers\\{target.name}\\{RUNNER}"\r\n'
        'if not errorlevel 1 exit /b 0\r\npause\r\nexit /b 1\r\n'
    ).encode("ascii")
    with NamedTemporaryFile(dir=home, prefix=".select-", delete=False) as output:
        temporary = Path(output.name)
        output.write(batch)
    try:
        os.replace(temporary, stable)
    finally:
        temporary.unlink(missing_ok=True)
    return stable


def run_selected():
    selected = Path(__file__).resolve().parent
    baseline = (selected / SPEC).read_bytes()
    selection = json.loads(baseline)
    identity = sha256(Path(__file__).read_bytes() + baseline).hexdigest()[:16]
    if selected.name != f"v{selection['release_version']}-{identity}":
        raise ValueError("The selected launcher's release record changed.")
    check_library(selection)
    gold = selected.parents[1] / "hosts" / selection["gold"]
    interpreter = gold / "resources/engine-bundle/python/python.exe"
    if interpreter.resolve() != Path(sys.executable).resolve():
        raise ValueError("The selected Desktop Python changed.")
    return subprocess.run([str(interpreter), "-I", "-B", str(gold / "hmb_start_desktop.py")], check=False).returncode


if __name__ == "__main__":
    if Path(__file__).name == RUNNER:
        try:
            sys.exit(run_selected())
        except (KeyError, OSError, ValueError) as error:
            sys.exit(f"HMB was not started. {error}\nRestore the approved Local ZIP using the HMB installer.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    print(select(**vars(parser.parse_args())))
