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

from audit_regression_coverage import classify_result
from hmb_griptape_update_preflight import REVIEWED_HOSTS, inspect_editor_fixtures, source_tree_digest


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
    try:
        engine = importlib.metadata.version("griptape-nodes-engine")
    except importlib.metadata.PackageNotFoundError:
        engine = None
    try:
        editor = importlib.metadata.distribution("griptape-nodes-editor-dist")
    except importlib.metadata.PackageNotFoundError:
        editor = None
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    tests = list(TESTS)
    standard = Path(os.environ.get("HMB_GRIPTAPE_STANDARD_LIBRARY_PATH",
                                   Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard"))
    standard_manifest = standard / "griptape_nodes_library.json"
    standard_identity = None
    if standard_manifest.is_file():
        metadata = json.loads(standard_manifest.read_bytes())["metadata"]
        standard_identity = {"version": metadata["library_version"], "source_sha256": source_tree_digest(standard)}
    if editor is not None and editor.version == "0.132.0":
        tests.extend(("HMB_Desktop031_Workflow_Envelope_Host_Regression.py",
                      "HMB_Seedance_Standalone_Host_Regression.py"))
    for name in tests:
        command = [sys.executable, "-X", "utf8", "-B", str(ROOT / "resources/tests" / name)]
        if name == "HMB_Connected_Deletion_Guard_Host_Regression.py":
            command.extend(("--out", str(report_dir / Path(name).stem)))
        result = subprocess.run(
            command,
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180,
        )
        output = result.stdout + result.stderr
        (report_dir / (name + ".log")).write_text(output, encoding="utf-8")
        results[name] = classify_result({"required": True}, result.returncode, output)[0] == "passed"

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
    source = None
    if editor is not None:
        from hmb_rodong_editor_0130 import verify_installed
        from restore_rodong_local_editor import editor_profile

        directory = Path(editor.locate_file("griptape_nodes_editor_dist/editor"))
        entry = directory / "index-editor.html"
        host = REVIEWED_HOSTS.get((sdk, editor.version))
        editor_reviewed = False
        if host is not None and engine == host[0]:
            try:
                data = entry.read_bytes()
                profile = editor_profile(data)
                fixtures = host[1]
                inspect_editor_fixtures(directory / "assets", fixtures)
                if fixtures.get(profile.bundle) != profile.stock_digest:
                    raise ValueError("Editor entry and package identify different builds")
                if sha256(data).hexdigest() != profile.entry_digest:
                    verify_installed(directory)
                source = directory / "assets" / profile.bundle
                editor_reviewed = True
            except (OSError, ValueError):
                pass

    if source is not None:
        test = ROOT / "resources/tests/HMB_Native_Stock_Deletion_Safety_Browser_Regression.mjs"
        evidence = report_dir / "stock-editor-deletion.json"
        try:
            run = subprocess.run(
                ["node", str(test), "--evidence-path", str(evidence)],
                cwd=ROOT, env={**os.environ, "HMB_STOCK_EDITOR_0130_SOURCE": str(source)},
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            (report_dir / "stock-editor-deletion.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            stock_result = classify_result({"required": True}, run.returncode, run.stdout + run.stderr)[0] == "passed"
        except (OSError, subprocess.TimeoutExpired) as error:
            (report_dir / "stock-editor-deletion.log").write_text(str(error), encoding="utf-8")
            stock_result = False

    if standard_identity is not None and source_tree_digest(standard) != standard_identity["source_sha256"]:
        results["standard_source_unchanged_during_check"] = False
    report = {"sdk": sdk, "engine": engine, "standard": standard_identity,
              "sdk_checks": results, "editor_version": editor.version if editor else None,
              "editor_bundle_reviewed": editor_reviewed, "stock_deletion_safety": stock_result,
              "desktop_interaction_checked": False}
    (report_dir / "upgrade-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0 if all(results.values()) and editor_reviewed and stock_result is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
