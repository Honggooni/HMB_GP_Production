"""Restore the reviewed Rodong Mart entry after a same-version Editor repair."""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution, version
from pathlib import Path
import os
import subprocess
import tempfile
from typing import NamedTuple


STOCK_BUNDLE = "index-B4peacnU.js"
STOCK_DIGEST = "841b879c94cd6bb18601f5b360daf094508bdfbfa0ec88b830a1caaf0df5871e"
STOCK_ENTRY_DIGEST = "561a68840af19500274dbbb8ef2c46e9ac8a619564e246b8b285137e63569a82"
OVERLAY_DIGEST = "355e3f9500e457ae6834c0b92b89a6dadb8724d05366299a84522399507a25d9"
OVERLAY = f"index-hmb-rodong-{OVERLAY_DIGEST[:16]}.js"
STOCK_REF = f"./assets/{STOCK_BUNDLE}".encode("ascii")
STOCK_SCRIPT = b'<script type="module" crossorigin src="' + STOCK_REF + b'"></script>'
PREVIOUS_OVERLAYS = ("index-hmb-rodong-bab22aebf56f9e49.js", "index-hmb-rodong-1b074f20773f7dd8.js", "index-hmb-rodong-00b05e4e9d896b27.js", "index-hmb-rodong-41ceed4589468b95.js", "index-hmb-rodong-3d3154ee26258c1f.js", "index-hmb-rodong-d7ae10c4e1f1f06c.js", "index-hmb-rodong-f961eb45ea463026.js", "index-hmb-rodong-1ee2ad12c816e225.js", "index-hmb-rodong-3a2abb8b19e64fcf.js", "index-hmb-rodong-5fdfcae906f8b133.js", "index-hmb-rodong-34d6c10701394930.js", "index-hmb-rodong-2e01583c43cc2855.js", "index-hmb-rodong-8d2bb367e252aeb7.js",
                     "index-hmb-rodong-2bcf846ae6211a01.js")


class EditorProfile(NamedTuple):
    bundle: str
    stock_digest: str
    entry_digest: str
    overlay_digest: str

    @property
    def overlay(self):
        return f"index-hmb-rodong-{self.overlay_digest[:16]}.js"

    @property
    def ref(self):
        return f"./assets/{self.bundle}".encode("ascii")


EDITOR_1300 = EditorProfile(STOCK_BUNDLE, STOCK_DIGEST, STOCK_ENTRY_DIGEST, OVERLAY_DIGEST)
EDITOR_1302 = EditorProfile("index-DW0x78hS.js",
    "8433f4e108e2416707c6877354234607aaa2cb8b4e15fe080856fdd656771d17",
    "17312cf62335309843550d34f0b7eedd2ddd8dce0584eb9c116448e202abebc3",
    "ba1b96f56bc3c4651733677cc469c152d98d3cf47b8dd85f8693f4fe897c7b39")


def editor_profile(entry: bytes) -> EditorProfile:
    return EDITOR_1302 if EDITOR_1302.ref in entry else EDITOR_1300


def entry_for_overlay(stock_entry: bytes, overlay_name: str) -> bytes:
    profile = editor_profile(stock_entry)
    ref = profile.ref
    script = b'<script type="module" crossorigin src="' + ref + b'"></script>'
    if sha256(stock_entry).hexdigest() != profile.entry_digest or stock_entry.count(script) != 1:
        raise ValueError("Editor entry is outside the reviewed profile")
    overlay_ref = f"./assets/{overlay_name}".encode("ascii")
    mapping = b'<script type="importmap">{"imports":{"' + ref + b'":"' + overlay_ref + b'"}}</script>'
    return stock_entry.replace(script, mapping + b"\n    " + script.replace(ref, overlay_ref))


def stock_entry_from_active(entry: bytes, overlay_name: str) -> bytes:
    profile = editor_profile(entry)
    if sha256(entry).hexdigest() == profile.entry_digest:
        return entry
    previous = PREVIOUS_OVERLAYS if profile == EDITOR_1300 else ()
    for name in (overlay_name, *previous):
        overlay_ref = f"./assets/{name}".encode("ascii")
        ref = profile.ref
        mapping = b'<script type="importmap">{"imports":{"' + ref + b'":"' + overlay_ref + b'"}}</script>\n    '
        stock = entry.replace(mapping, b"", 1).replace(b'src="' + overlay_ref + b'"', b'src="' + ref + b'"', 1)
        if sha256(stock).hexdigest() == profile.entry_digest:
            return stock
    raise ValueError("Editor entry is outside the reviewed profile")


def atomic_write(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def griptape_running() -> bool:
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    bundle = Path(os.environ["LOCALAPPDATA"]) / "ai.griptape.nodes.desktop/current/resources/engine-bundle"
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-Command",
         """$ErrorActionPreference = 'Stop'
$engineBundle = $env:HMB_REPAIR_ENGINE_BUNDLE
$repairPid = [int]$env:HMB_REPAIR_PID
$active = Get-CimInstance Win32_Process -Filter "Name = 'griptape-nodes-desktop.exe' OR Name = 'python.exe' OR Name = 'pythonw.exe'" |
    Where-Object {
        $_.Name -eq 'griptape-nodes-desktop.exe' -or
        ($_.ProcessId -ne $repairPid -and $_.ExecutablePath -and
         $_.ExecutablePath.StartsWith($engineBundle, [StringComparison]::OrdinalIgnoreCase))
    } | Select-Object -First 1
if ($active) { [Console]::Write('active') }
"""],
        env={**os.environ, "HMB_REPAIR_ENGINE_BUNDLE": str(bundle) + os.sep,
             "HMB_REPAIR_PID": str(os.getpid())},
        capture_output=True, check=True, timeout=15,
    )
    return result.stdout.strip() == b"active"


def restore(editor: Path) -> str:
    entry = editor / "index-editor.html"
    original = entry.read_bytes()
    profile = editor_profile(original)
    stock = editor / "assets" / profile.bundle
    active = editor / "assets" / profile.overlay
    updated = entry_for_overlay(stock_entry_from_active(original, profile.overlay), profile.overlay)
    if sha256(stock.read_bytes()).hexdigest() != profile.stock_digest:
        raise ValueError("Stock Editor bundle is outside the reviewed profile")
    if updated == original and active.is_file() and sha256(active.read_bytes()).hexdigest() == profile.overlay_digest:
        return "already active"
    if griptape_running():
        return "Desktop or engine already running"
    # The packaged HMB UI can be rebuilt without relying on a previously
    # patched file surviving a Desktop repair.
    from hmb_rodong_editor_0130 import build
    overlay = build(stock.read_bytes())
    if sha256(overlay).hexdigest() != profile.overlay_digest:
        raise ValueError("HMB overlay sources differ from the reviewed build")
    if not active.is_file() or sha256(active.read_bytes()).hexdigest() != profile.overlay_digest:
        atomic_write(active, overlay)
    if griptape_running():
        return "Desktop or engine already running"
    if entry.read_bytes() != original:
        raise ValueError("Editor entry changed while preparing restore")
    atomic_write(entry, updated)
    return "restored reviewed Rodong Mart entry"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("editor", type=Path)
    args = parser.parse_args()
    try:
        editor_package = distribution("griptape-nodes-editor-dist")
        if (version("griptape-nodes"), editor_package.version) not in (("0.104.0", "0.130.0"), ("0.104.2", "0.130.2")):
            raise ValueError("SDK and Editor versions need isolated preflight")
        bundled_editor = Path(editor_package.locate_file("griptape_nodes_editor_dist/editor")).resolve()
        if args.editor.resolve() != bundled_editor:
            raise ValueError("Requested Editor is outside the bundled distribution")
        result = restore(args.editor)
        if result != "already active":
            print(result)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Rodong Mart entry restore skipped: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
