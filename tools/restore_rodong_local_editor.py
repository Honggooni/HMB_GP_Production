"""Restore the reviewed Rodong Mart entry after a same-version Editor repair."""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution, version
from pathlib import Path
import os
import subprocess
import tempfile


STOCK_BUNDLE = "index-B4peacnU.js"
STOCK_DIGEST = "841b879c94cd6bb18601f5b360daf094508bdfbfa0ec88b830a1caaf0df5871e"
STOCK_ENTRY_DIGEST = "561a68840af19500274dbbb8ef2c46e9ac8a619564e246b8b285137e63569a82"
OVERLAY_DIGEST = "355e3f9500e457ae6834c0b92b89a6dadb8724d05366299a84522399507a25d9"
OVERLAY = f"index-hmb-rodong-{OVERLAY_DIGEST[:16]}.js"
STOCK_REF = f"./assets/{STOCK_BUNDLE}".encode("ascii")
STOCK_SCRIPT = b'<script type="module" crossorigin src="' + STOCK_REF + b'"></script>'
PREVIOUS_OVERLAYS = ("index-hmb-rodong-bab22aebf56f9e49.js", "index-hmb-rodong-1b074f20773f7dd8.js", "index-hmb-rodong-00b05e4e9d896b27.js", "index-hmb-rodong-41ceed4589468b95.js", "index-hmb-rodong-3d3154ee26258c1f.js", "index-hmb-rodong-d7ae10c4e1f1f06c.js", "index-hmb-rodong-f961eb45ea463026.js", "index-hmb-rodong-1ee2ad12c816e225.js", "index-hmb-rodong-3a2abb8b19e64fcf.js", "index-hmb-rodong-5fdfcae906f8b133.js", "index-hmb-rodong-34d6c10701394930.js", "index-hmb-rodong-2e01583c43cc2855.js", "index-hmb-rodong-8d2bb367e252aeb7.js",
                     "index-hmb-rodong-2bcf846ae6211a01.js")


def entry_for_overlay(stock_entry: bytes, overlay_name: str) -> bytes:
    if sha256(stock_entry).hexdigest() != STOCK_ENTRY_DIGEST or stock_entry.count(STOCK_SCRIPT) != 1:
        raise ValueError("Editor entry is outside the reviewed profile")
    overlay_ref = f"./assets/{overlay_name}".encode("ascii")
    # The Editor's lazy chunks import the stock entry by name. Resolve that
    # import to the active overlay so all chunks share one set of stores.
    mapping = b'<script type="importmap">{"imports":{"' + STOCK_REF + b'":"' + overlay_ref + b'"}}</script>'
    return stock_entry.replace(STOCK_SCRIPT, mapping + b"\n    " + STOCK_SCRIPT.replace(STOCK_REF, overlay_ref))


def stock_entry_from_active(entry: bytes, overlay_name: str) -> bytes:
    if sha256(entry).hexdigest() == STOCK_ENTRY_DIGEST:
        return entry
    for name in (overlay_name, *PREVIOUS_OVERLAYS):
        overlay_ref = f"./assets/{name}".encode("ascii")
        mapping = b'<script type="importmap">{"imports":{"' + STOCK_REF + b'":"' + overlay_ref + b'"}}</script>\n    '
        stock = entry.replace(mapping, b"", 1).replace(STOCK_SCRIPT.replace(STOCK_REF, overlay_ref), STOCK_SCRIPT, 1)
        if sha256(stock).hexdigest() == STOCK_ENTRY_DIGEST:
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
    stock = editor / "assets" / STOCK_BUNDLE
    active = editor / "assets" / OVERLAY
    original = entry.read_bytes()
    updated = entry_for_overlay(stock_entry_from_active(original, OVERLAY), OVERLAY)
    if sha256(stock.read_bytes()).hexdigest() != STOCK_DIGEST:
        raise ValueError("Stock Editor bundle is outside the reviewed profile")
    if updated == original and active.is_file() and sha256(active.read_bytes()).hexdigest() == OVERLAY_DIGEST:
        return "already active"
    if griptape_running():
        return "Desktop or engine already running"
    # The packaged HMB UI can be rebuilt without relying on a previously
    # patched file surviving a Desktop repair.
    from hmb_rodong_editor_0130 import build
    overlay = build(stock.read_bytes())
    if sha256(overlay).hexdigest() != OVERLAY_DIGEST:
        raise ValueError("HMB overlay sources differ from the reviewed build")
    if not active.is_file() or sha256(active.read_bytes()).hexdigest() != OVERLAY_DIGEST:
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
        if (version("griptape-nodes"), editor_package.version) != ("0.104.0", "0.130.0"):
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
