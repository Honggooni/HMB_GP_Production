from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]


def load_asset_library():
    path = ROOT / "HMBImageAssetLibrary.py"
    spec = importlib.util.spec_from_file_location("hmb_asset_lock_regression", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if len(sys.argv) > 1 and sys.argv[1] == "--child":
    asset_library = load_asset_library()
    project_root = Path(sys.argv[2])
    ready_path = Path(sys.argv[3])
    release_path = Path(sys.argv[4])
    with asset_library._asset_manifest_process_lock(project_root):
        ready_path.write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + 10.0
        while not release_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not release_path.exists():
            raise TimeoutError("Parent did not release the lock regression child.")
    raise SystemExit(0)


asset_library = load_asset_library()
test_root = Path(tempfile.mkdtemp(prefix="hmb_asset_process_lock_", dir=ROOT / ".tmp"))
try:
    project_root = test_root / "Project"
    project_root.mkdir()
    ready_path = test_root / "ready"
    release_path = test_root / "release"
    child = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            str(project_root),
            str(ready_path),
            str(release_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10.0
    while not ready_path.exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert ready_path.exists(), child.communicate(timeout=2.0)

    previous_timeout = asset_library.ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS
    asset_library.ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS = 0.2
    try:
        try:
            with asset_library._asset_manifest_process_lock(project_root):
                raise AssertionError("A second process acquired an already-held manifest lock.")
        except TimeoutError:
            pass
    finally:
        asset_library.ASSET_MANIFEST_LOCK_TIMEOUT_SECONDS = previous_timeout

    release_path.write_text("release", encoding="utf-8")
    stdout, stderr = child.communicate(timeout=10.0)
    assert child.returncode == 0, (stdout, stderr)
    with asset_library._asset_manifest_process_lock(project_root):
        pass
    process_lock = (
        project_root
        / asset_library.ASSET_METADATA_DIRECTORY_NAME
        / asset_library.ASSET_MANIFEST_LOCK_NAME
    )
    assert process_lock.is_file() and process_lock.stat().st_size >= 1
    assert not (project_root / asset_library.ASSET_MANIFEST_LOCK_NAME).exists()
finally:
    try:
        if "child" in locals() and child.poll() is None:
            child.kill()
            child.wait(timeout=2.0)
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


print("HMB ImageAsset cross-process persistent manifest lock regression: PASS")
