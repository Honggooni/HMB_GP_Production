"""Run the no-render SDK checks before rolling out a Griptape update."""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "HMB_Connected_Deletion_Guard_Host_Regression.py",
    "HMB_Prompt_Save_Roundtrip_Host_Regression.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    sdk = importlib.metadata.version("griptape-nodes")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    for name in TESTS:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", str(ROOT / "resources/tests" / name),
             "--out", str(report_dir / Path(name).stem)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
        (report_dir / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        results[name] = result.returncode == 0

    resources = Path(os.environ["LOCALAPPDATA"]) / "ai.griptape.nodes.desktop/current/resources"
    legacy_entry = resources / "editor-bundle/index-editor.html"
    if legacy_entry.is_file():
        sys.path.insert(0, str(ROOT))
        from tools import hmb_color_lut_native_header_patch as patcher
        try:
            descriptor, _ = patcher._release_descriptor()
            active = patcher._active_git_profile(descriptor)
            editor_reviewed = active is not None
            if active is not None and active[1] is not None:
                target, profile = active
                editor_reviewed = sha256(target.read_bytes()).hexdigest() in (
                    profile["source_sha256"], profile["candidate_sha256"],
                    *profile.get("previous_candidate_sha256", []),
                )
        except (OSError, ValueError):
            editor_reviewed = False
    else:
        editor_reviewed = False

    stock_result = None
    try:
        editor = importlib.metadata.distribution("griptape-nodes-editor-dist")
    except importlib.metadata.PackageNotFoundError:
        editor = None
    if editor is not None and editor.version == "0.130.0":
        source = editor.locate_file("griptape_nodes_editor_dist/editor/assets/index-B4peacnU.js")
        test = ROOT / "resources/tests/HMB_Native_Stock_Deletion_Safety_Browser_Regression.mjs"
        evidence = report_dir / "stock-editor-deletion.json"
        try:
            run = subprocess.run(
                ["node", str(test), "--evidence-path", str(evidence)],
                cwd=ROOT, env={**os.environ, "HMB_STOCK_EDITOR_0130_SOURCE": str(source)},
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            (report_dir / "stock-editor-deletion.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            stock_result = run.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            (report_dir / "stock-editor-deletion.log").write_text(str(error), encoding="utf-8")
            stock_result = False

    report = {"sdk": sdk, "sdk_checks": results, "editor_version": editor.version if editor else None,
              "editor_bundle_reviewed": editor_reviewed, "stock_deletion_safety": stock_result,
              "desktop_interaction_checked": False}
    (report_dir / "upgrade-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if all(results.values()) and editor_reviewed and stock_result is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
