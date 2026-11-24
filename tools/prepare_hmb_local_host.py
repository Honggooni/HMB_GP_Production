"""Prepare a private, versioned Windows host from the locally cached official package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

EXECUTABLE = "griptape-nodes-desktop.exe"
VENDOR = "ai.griptape.nodes.desktop"
EDITOR = Path("resources/engine-bundle/python/Lib/site-packages/griptape_nodes_editor_dist/editor")
RECEIPT = "hmb-host.json"
LAUNCHER = "Start-HMB.cmd"
LAUNCH_HELPER = "hmb_start_desktop.py"

# These settings are inherited by this process tree only. Desktop uses a
# single-instance lock. Sending the user to an already running stock editor
# would defeat the private host selection.
LAUNCH = """@echo off
setlocal
"%~dp0resources\\engine-bundle\\python\\python.exe" -I -B "%~dp0hmb_start_desktop.py"
if not errorlevel 1 (
  exit /b 0
)
pause
exit /b 1
"""
LAUNCH_BYTES = LAUNCH.replace("\n", "\r\n").encode("ascii")
BUNDLE = Path("resources/engine-bundle")
HOST_FILES = (Path(LAUNCHER), Path(LAUNCH_HELPER), Path(EXECUTABLE), Path("resources/app.asar"),
              EDITOR / "index-editor.html", BUNDLE / "python/python.exe", BUNDLE / ".distributions",
              BUNDLE / ".engine-version", BUNDLE / ".editor-version", BUNDLE / ".version")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_host(target, record):
    overlay = record["overlay_sha256"]
    if not re.fullmatch("[0-9a-f]{64}", overlay):
        raise ValueError("Invalid editor identity")
    assets = EDITOR / "assets" / f"index-hmb-rodong-{overlay[:16]}.js"
    if (set(record["files"]) != {str(file) for file in HOST_FILES}
            or (target / RECEIPT).resolve() != target / RECEIPT
            or json.loads((target / RECEIPT).read_bytes()) != record):
        raise ValueError(f"Unexpected Desktop identity: {target}")
    expected_files = {**record["files"], str(assets): overlay}
    for file, expected in expected_files.items():
        path = target / file
        if path.resolve() != path or digest(path) != expected:
            raise ValueError(f"Reviewed Desktop file changed: {path}")


def stage_runtime(gold, desktop):
    """A real sibling makes Desktop resolve its original top-level protocol executable."""
    if gold.resolve() != gold or desktop.resolve() != desktop or not re.fullmatch(
            r"desktop-\d+\.\d+\.\d+-[0-9a-f]{8}-[0-9a-f]{8}", gold.name):
        raise ValueError("Unrecognized private host location")
    if desktop.name != VENDOR or not (desktop / EXECUTABLE).is_file():
        raise ValueError("The installed Griptape Desktop launcher is missing")
    record = json.loads((gold / RECEIPT).read_bytes())
    target = desktop / ("HMB-pinned-" + gold.name)
    if not target.exists():
        verified_host(gold, record)
        with TemporaryDirectory(dir=desktop, prefix=".hmb-prepare-") as tmp:
            pending = Path(tmp) / "host"
            shutil.copytree(gold, pending)
            verified_host(pending, record)
            try:
                pending.rename(target)
            except FileExistsError:
                pass  # A concurrent launcher finished its own identical copy.
    verified_host(target, record)
    return target


def verify_protocol(desktop):
    """Mirror Electron's Windows command comparison without changing any registry key."""
    import winreg

    stub = desktop / EXECUTABLE
    if not stub.is_file() or stub.resolve() != stub:
        raise ValueError("The original Griptape protocol launcher is unavailable")
    command = f'"{stub}" "%1"'
    for root, scheme, access in (
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\gtn", winreg.KEY_ALL_ACCESS),
            (winreg.HKEY_CLASSES_ROOT, "gtn", winreg.KEY_READ)):
        # Electron 43 opens both existing HKCU keys with KEY_ALL_ACCESS even for its query.
        # Opening an existing key does not write or create it.
        with winreg.OpenKey(root, scheme, access=access) as key:
            winreg.QueryValueEx(key, "URL Protocol")
        with winreg.OpenKey(root, scheme + r"\shell\open\command", access=access) as key:
            if winreg.QueryValueEx(key, "")[0] != command:
                raise ValueError("The gtn: default is different. Use the existing Desktop shortcut.")
    choice = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\gtn\UserChoice"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, choice)
    except FileNotFoundError:
        return
    with key:
        if winreg.QueryValueEx(key, "ProgId")[0].lower() != "gtn":
            raise ValueError("A different default app is selected for gtn: links.")


def ensure_desktop_closed():
    tasklist = Path(os.environ["SystemRoot"]) / "System32/tasklist.exe"
    tasks = subprocess.check_output([str(tasklist), "/fi", f"IMAGENAME eq {EXECUTABLE}", "/fo", "csv", "/nh"])
    if f'"{EXECUTABLE}"'.encode("ascii") in tasks.lower():
        raise RuntimeError("Save your work and close the running Griptape Desktop before starting HMB.")


def launch():
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    desktop = local / VENDOR
    gold = Path(__file__).resolve().parent
    if gold.parent != local / "HMB_GP_Production" / "hosts":
        raise ValueError("Run Start-HMB.cmd from the HMB installation in your local profile.")
    settings = Path(os.environ["APPDATA"]) / "Griptape Nodes/settings.json"
    if settings.exists() and json.loads(settings.read_bytes()).get("localEnginePath"):
        raise ValueError("Desktop is configured for a custom engine. Use the existing Desktop shortcut.")
    ensure_desktop_closed()
    verify_protocol(desktop)
    target = stage_runtime(gold, desktop)
    # Copying a missing runtime can take time. Recheck directly before launch.
    ensure_desktop_closed()
    verify_protocol(desktop)
    child_env = {**os.environ, "GTN_DESKTOP_DISABLE_UPDATES": "1",
                 "GRIPTAPE_NODES_EDITOR_DIST": str((target / EDITOR).parent)}
    subprocess.Popen([str(target / EXECUTABLE)], cwd=target, env=child_env)


def prepare(package: Path, parent: Path) -> Path:
    from hmb_review_upstream import DESKTOP, DESKTOP_SHA256
    from hmb_rodong_editor_0130 import build
    from restore_rodong_local_editor import EDITOR_1320, entry_for_overlay

    if digest(package) != DESKTOP_SHA256:
        raise ValueError("Desktop package differs from the reviewed official Windows release.")
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    launcher_version = hashlib.sha256(Path(__file__).read_bytes() + LAUNCH_BYTES).hexdigest()[:8]
    target = parent.resolve() / f"desktop-{DESKTOP}-{EDITOR_1320.overlay_digest[:8]}-{launcher_version}"
    if target.exists():
        record = json.loads((target / RECEIPT).read_bytes())
        if (record["package_sha256"] != DESKTOP_SHA256 or record["overlay_sha256"] != EDITOR_1320.overlay_digest
                or (target / LAUNCHER).read_bytes() != LAUNCH_BYTES
                or (target / LAUNCH_HELPER).read_bytes() != Path(__file__).read_bytes()):
            raise ValueError(f"Installed private host differs from its receipt: {target}")
        verified_host(target, record)
        return target
    with TemporaryDirectory(dir=parent, prefix=".prepare-") as directory:
        pending = Path(directory) / "host"
        pending.mkdir()
        with ZipFile(package) as archive:
            for entry in archive.infolist():
                member = PurePosixPath(entry.filename)
                if member.parts[:2] != ("lib", "app") or entry.is_dir():
                    continue
                path = pending.joinpath(*member.parts[2:])
                if not path.resolve().is_relative_to(pending) or path == pending:
                    raise ValueError(f"Invalid package member: {member}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, path.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
        editor = pending / EDITOR
        stock = editor / "assets" / EDITOR_1320.bundle
        html = editor / "index-editor.html"
        if digest(html) != EDITOR_1320.entry_digest or digest(stock) != EDITOR_1320.stock_digest:
            raise ValueError("Stock editor does not match the reviewed profile.")
        overlay = build(stock.read_bytes())
        if hashlib.sha256(overlay).hexdigest() != EDITOR_1320.overlay_digest:
            raise ValueError("HMB editor overlay differs from the reviewed build.")
        (editor / "assets" / EDITOR_1320.overlay).write_bytes(overlay)
        html.write_bytes(entry_for_overlay(html.read_bytes(), EDITOR_1320.overlay))
        (pending / LAUNCHER).write_bytes(LAUNCH_BYTES)
        shutil.copyfile(__file__, pending / LAUNCH_HELPER)
        identity = {str(file): digest(pending / file) for file in HOST_FILES}
        receipt = {"desktop": DESKTOP, "sdk": "0.106.0", "engine": "0.113.0", "editor": "0.132.0",
                   "package_sha256": DESKTOP_SHA256, "overlay_sha256": EDITOR_1320.overlay_digest,
                   "files": identity}
        (pending / RECEIPT).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        pending.rename(target)
    return target


def main():
    from hmb_review_upstream import DESKTOP

    local = Path(os.environ["LOCALAPPDATA"])
    parser = argparse.ArgumentParser(description=__doc__)
    archive = f"ai.griptape.nodes.desktop-{DESKTOP}-win-x64-stable-full.nupkg"
    parser.add_argument("--package", type=Path, default=local / VENDOR / "packages" / archive)
    parser.add_argument("--hosts", type=Path, default=local / "HMB_GP_Production/hosts")
    parser.add_argument("--desktop-root", type=Path, help="Prestage the pinned sibling alongside the installed Desktop")
    args = parser.parse_args()
    gold = prepare(args.package, args.hosts)
    if args.desktop_root:
        print(stage_runtime(gold, args.desktop_root.absolute()))
    print(gold)


if __name__ == "__main__":
    if Path(__file__).name == LAUNCH_HELPER:
        try:
            launch()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            sys.exit(f"HMB Desktop was not started: {error}")
    else:
        main()
