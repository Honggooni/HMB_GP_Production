"""Run HMB upgrade checks against a staged Windows Desktop distribution."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from hmb_editor_0130_header import HEADER_SOURCE
from hmb_rodong_editor_0130 import STOCK_SHA256, build
from restore_rodong_local_editor import entry_for_overlay, stock_entry_from_active


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "resources/tests"
PYTHON_ROOT = Path("resources/engine-bundle/python")
STOCK_EDITOR_ASSET = "index-B4peacnU.js"
EDITOR_0130_FIXTURES = {
    STOCK_EDITOR_ASSET: STOCK_SHA256,
    "EngineContext-B0JaCG1N.js": "0eac023d9df0796c79a038ea8c37415fc7c97afb979bc7aa58bc730d1672e5e6",
    "react-Cwox1F5v.js": "0922625a90900001152ac5899de0daf62230d0c18bc54979e9cccb50dad13750",
    "rolldown-runtime-DSDNlrLa.js": "9642411c8411b70e62cea3e38c4093f5fcd4419ec151356d87dc835062db7b69",
    "index-CU0rDeoz.css": "0b9f857574a87b404d107677bd21a5d5cd1fb28f130385d62300e3055017fda9",
}
HEADER_CHECK = "HMB_Editor_0130_Integrated_Header_Regression.mjs"
DELETION_CHECK = "HMB_Native_Stock_Deletion_Safety_Browser_Regression.mjs"
CHECKS = (
    ("HMB_Library_Lifecycle_Order_Host_Regression.py", {}),
    ("HMB_CGT_Own_Task_Regression.py", {}),
    ("HMB_CGT_Thumbnail_Bridge_Mount_Host_Regression.py", {}),
    ("HMB_Image_Generation_Protocol_Regression.py", {}),
    ("HMB_Common_Connection_Management_Host_Regression.py", {}),
    ("HMB_Connected_Deletion_Guard_Host_Regression.py", {}),
    ("HMB_Prompt_Save_Roundtrip_Host_Regression.py", {}),
    ("HMB_Prompt_Scoped_Snapshot_Cold_Reload_Host_Regression.py", {}),
    ("HMB_Picker_Prompt_Agent_Live_Host_Regression.py", {}),
    ("HMB_Page_Only_Shot_Switch_Host_Regression.py", {}),
    ("HMB_Agent_Shot_Switch_Native_Host_Regression.py", {}),
    ("HMB_Analysis_Agent_Save_Reopen_Host_Regression.py", {}),
    ("HMB_Seedance_Execution_Mode_Host_Regression.py", {}),
    ("HMB_Sound_Automatic_Chain_Host_Regression.py", {}),
    ("HMB_Sound_Delta_Transport_Host_Regression.py", {}),
    ("HMB_Finish_Multishot_Consolidation_Host_Regression.py", {}),
    ("HMB_Image_Asset_Project_Root_Relocation_Regression.py", {}),
    ("HMB_Image_Bash_Host_Regression.py", {}),
    ("HMB_Image_Bash_Performance_Regression.py", {}),
    ("HMB_Image_Bash_Apply_Readiness_Host_Regression.py", {
        "HMB_BASH_APPLY_READINESS_REPORT_DIR": "bash", "HMB_BASH_APPLY_WORKER_REPORT_DIR": "bash-worker",
    }),
)
BROWSER_CHECKS = (
    HEADER_CHECK,
    DELETION_CHECK,
    "HMB_Image_Asset_Authority_Lifecycle_Regression.mjs",
    "HMB_Image_Bash_Owned_Editor_Browser_Regression.mjs",
    "HMB_CGT_Hierarchy_Widget_Regression.mjs",
    "HMB_Analysis_Agent_Widget_Regression.mjs",
    "HMB_Agent_Immediate_Page_Widget_Regression.mjs",
    "HMB_Library_Prepared_Switch_Regression.mjs",
    "HMB_Other_Widget_Stale_Shot_Echo_Regression.mjs",
    "HMB_Color_LUT_Web_Upload_Widget_Regression.mjs",
    "HMB_Finish_Look_Widget_Regression.mjs",
    "HMB_Prompt_Asset_Selection_Lifecycle_Regression.mjs",
    "HMB_Seedance_Render_Preflight_Regression.mjs",
    "HMB_Seedance_Cold_Surface_Regression.mjs",
    "HMB_Sound_Library_Regression.mjs",
    "HMB_VideoPicker_View_Transition_Lifecycle_Regression.mjs",
    "HMB_Shot_Basket_Creation_Widget_Regression.mjs",
)

# A release must cover every shipped library, including Local-only nodes.
LIBRARY_CHECKS = {
    "HMBImageAssetLibrary": "HMB_Image_Asset_Authority_Lifecycle_Regression.mjs",
    "HMBVideoPickerLibrary": "HMB_Picker_Prompt_Agent_Live_Host_Regression.py",
    "HMBPromptLibrary": "HMB_Prompt_Scoped_Snapshot_Cold_Reload_Host_Regression.py",
    "HMBAgentLibrary": "HMB_Agent_Immediate_Page_Widget_Regression.mjs",
    "HMBAnalysisAgent": "HMB_Analysis_Agent_Save_Reopen_Host_Regression.py",
    "HMBSeedanceGeneration": "HMB_Seedance_Execution_Mode_Host_Regression.py",
    "HMBImageGeneration": "HMB_Image_Generation_Protocol_Regression.py",
    "HMBSoundLibrary": "HMB_Sound_Automatic_Chain_Host_Regression.py",
    "HMBFinishLookLibrary": "HMB_Finish_Multishot_Consolidation_Host_Regression.py",
    "HMBColorLUTLibrary": "HMB_Color_LUT_Web_Upload_Widget_Regression.mjs",
    "HMBImageBash": "HMB_Image_Bash_Apply_Readiness_Host_Regression.py",
}
OUT_ARGUMENT_CHECKS = frozenset((
    "HMB_Connected_Deletion_Guard_Host_Regression.py", "HMB_Common_Connection_Management_Host_Regression.py",
    "HMB_Page_Only_Shot_Switch_Host_Regression.py", "HMB_Analysis_Agent_Save_Reopen_Host_Regression.py",
    "HMB_Seedance_Execution_Mode_Host_Regression.py",
))


def check_inventory() -> dict[str, str]:
    names = [name for name, _ in CHECKS] + list(BROWSER_CHECKS)
    if len(names) != len(set(names)) or set(LIBRARY_CHECKS.values()) - set(names):
        raise ValueError("Upgrade check coverage is duplicate or incomplete")
    for name in names:
        if not (TESTS / name).is_file():
            raise ValueError(f"Missing mandatory upgrade check: {name}")
    descriptor = json.loads((ROOT / "griptape-nodes-library.json").read_bytes())
    shipped = {item["class_name"] for item in descriptor["nodes"]}
    if shipped != set(LIBRARY_CHECKS):
        raise ValueError(f"Library check coverage differs from shipped nodes: {sorted(shipped ^ set(LIBRARY_CHECKS))}")
    return dict(LIBRARY_CHECKS)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def inspect_editor_fixtures(assets: Path) -> dict[str, str]:
    for name, expected_sha in EDITOR_0130_FIXTURES.items():
        if digest(assets / name) != expected_sha:
            raise ValueError(f"Editor asset does not match the reviewed 0.130 distribution: {name}")
    return dict(EDITOR_0130_FIXTURES)


def version(site: Path, package: str) -> str:
    metadata, = site.glob(f"{package}-*.dist-info/METADATA")
    return BytesParser().parsebytes(metadata.read_bytes(), headersonly=True)["Version"]


def source_tree_digest(root: Path) -> str:
    """Detect same-version SDK/Standard changes, without hashing caches or media."""
    files = []
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = [name for name in subdirs if name not in {".git", ".venv", "__pycache__", "node_modules", "reports"}]
        for name in names:
            path = Path(directory) / name
            if path.suffix in {".py", ".js", ".json", ".mjs"}:
                files.append((path.relative_to(root).as_posix(), digest(path)))
    if not files:
        raise ValueError(f"No runtime source files in {root}")
    return sha256(json.dumps(sorted(files), separators=(",", ":")).encode()).hexdigest()


def inspect_candidate(candidate: Path, *, header_source: Path = HEADER_SOURCE) -> dict:
    site = candidate / PYTHON_ROOT / "Lib/site-packages"
    sdk = version(site, "griptape_nodes")
    editor_version = version(site, "griptape_nodes_editor_dist")
    if (sdk, editor_version) != ("0.104.0", "0.130.0"):
        raise ValueError(f"Unreviewed SDK/Editor pair: {sdk}/{editor_version}")
    editor = site / "griptape_nodes_editor_dist/editor"
    entry = editor / "index-editor.html"
    fixture_sha = inspect_editor_fixtures(editor / "assets")
    stock = editor / "assets" / STOCK_EDITOR_ASSET
    patched_sha = sha256(build(stock.read_bytes(), header_source=header_source)).hexdigest()
    patched = stock.with_name(f"index-hmb-rodong-{patched_sha[:16]}.js")
    html = entry.read_bytes()
    stock_html = stock_entry_from_active(html, patched.name)
    if html == stock_html:
        active = stock
    elif html == entry_for_overlay(stock_html, patched.name):
        active = patched
        if digest(active) != patched_sha:
            raise ValueError("HMB Editor asset differs from the reviewed build")
    else:
        raise ValueError("Editor entry does not reference a reviewed asset")
    files = [candidate / "griptape-nodes-desktop.exe", candidate / "resources/app.asar",
             candidate / PYTHON_ROOT / "python.exe", entry, active]
    return {"sdk": sdk, "editor": editor_version, "editor_overlay": active == patched,
            "editor_fixture_sha256": fixture_sha, "compiled_overlay_sha256": patched_sha,
            "sdk_source_sha256": source_tree_digest(site / "griptape_nodes"),
            "files_sha256": {path.relative_to(candidate).as_posix(): digest(path) for path in files}}


def isolated_environment(folder: Path, standard: Path, editor: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("SystemRoot", "SystemDrive", "WINDIR", "COMSPEC", "PATH", "PATHEXT")
           if key in os.environ}
    for key in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                "XDG_CACHE_HOME", "GTN_ENGINE_CONFIG_DIR", "GTN_ENGINE_DATA_DIR", "GTN_ENGINE_STATE_DIR",
                "GTN_CONFIG_WORKSPACE_DIRECTORY"):
        path = folder / key.lower()
        path.mkdir()
        env[key] = str(path)
    home = folder / "home"
    home.mkdir()
    env.update(USERPROFILE=str(home), HOME=str(home), PYTHONUTF8="1",
               PYTHONIOENCODING="utf-8", GTN_DESKTOP_DISABLE_UPDATES="1",
               HMB_GRIPTAPE_STANDARD_LIBRARY_PATH=str(standard), HMB_IMAGE_BASH_STANDARD_LIBRARY_PATH=str(standard),
               HMB_IMAGE_BASH_EDITOR_BUNDLE_PATH=str(editor))
    return env


def product_digest() -> str:
    manifest = ROOT / "griptape-nodes-library.json"
    entries = json.loads(manifest.read_bytes())
    files = {manifest, *ROOT.glob("*.py"), *Path(__file__).parent.glob("*.py")}
    files.update(ROOT / item["path"] for item in entries.get("widgets", []))
    files.update(TESTS / script for script, _ in CHECKS)
    files.update(TESTS / script for script in BROWSER_CHECKS)
    files.add(TESTS / "_hmb_native_editor_fixture.mjs")
    files.update(path for path in (ROOT / "resources/editor").iterdir() if path.is_file())
    inventory = {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(files)}
    return sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()


def validate_deletion_evidence(proof: Path) -> None:
    report = json.loads(proof.read_bytes())
    if (not isinstance(report, dict)
            or report.get("schema") != "hmb-native-stock-deletion-safety/v1"
            or report.get("passed") is not True
            or report.get("editor_source_sha256") != STOCK_SHA256
            or not isinstance(report.get("cases"), list)
            or "editor_0130_link_identity_and_checked_deletion" not in report["cases"]
            or report.get("paid_calls") != 0
            or report.get("live_app_calls") != 0
            or report.get("external_requests") != 0):
        raise ValueError("Editor 0.130 deletion safety evidence is incomplete")


def validate_header_evidence(proof: Path, header_sha: str) -> None:
    report = json.loads(proof.read_bytes())
    if (not isinstance(report, dict)
            or report.get("passed") is not True
            or report.get("editor_source_sha256") != STOCK_SHA256
            or report.get("header_sha256") != header_sha
            or report.get("integrated_headers") != len(LIBRARY_CHECKS)):
        raise ValueError("Editor 0.130 integrated header evidence is incomplete")


def run(candidate: Path, standard: Path, output: Path, node: str, legacy_editor_fixture: Path | None = None,
        *, header_source: Path = HEADER_SOURCE) -> int:
    expected = {name for name, _ in CHECKS} | set(BROWSER_CHECKS)
    result = {"candidate": str(candidate), "status": "BLOCKED", "checks": {}, "desktop_interaction_checked": False,
              "activation_approved": False, "mandatory_checks": sorted(expected)}
    try:
        result["library_checks"] = check_inventory()
        result["header_source"] = str(header_source)
        result["header_source_sha256"] = digest(header_source)
        result["identity"] = inspect_candidate(candidate, header_source=header_source)
        result["hmb_source_sha256"] = product_digest()
        standard_manifest = standard / "griptape_nodes_library.json"
        result["standard_manifest_sha256"] = digest(standard_manifest)
        result["standard_source_sha256"] = source_tree_digest(standard)
        python = candidate / PYTHON_ROOT / "python.exe"
        editor = python.parent / "Lib/site-packages/griptape_nodes_editor_dist/editor"
        # Compile into evidence only. Never modify a staged or active Desktop to run a test.
        reviewed_header = output / "reviewed-header.js"
        stock = editor / "assets" / STOCK_EDITOR_ASSET
        reviewed_header.write_bytes(build(stock.read_bytes(), header_source=header_source))
        result["tested_header_sha256"] = digest(reviewed_header)
        if result["tested_header_sha256"] != result["identity"]["compiled_overlay_sha256"]:
            raise ValueError("Compiled Editor overlay differs from the inspected candidate")
        if legacy_editor_fixture is not None:
            result["legacy_fixture_sha256"] = digest(legacy_editor_fixture)
        for script, reports in CHECKS:
            folder = output / Path(script).stem
            folder.mkdir()
            env = isolated_environment(folder, standard, editor)
            env.update({key: str(folder / name) for key, name in reports.items()})
            with (folder / "test.log").open("wb") as log:
                try:
                    command = [str(python), "-B", str(TESTS / script)]
                    if script in OUT_ARGUMENT_CHECKS:
                        command += ["--out", str(folder / "evidence")]
                    check = subprocess.run(command, cwd=folder, env=env,
                                           stdout=log, stderr=subprocess.STDOUT, timeout=150, check=False)
                    result["checks"][script] = check.returncode
                except subprocess.TimeoutExpired:
                    result["checks"][script] = "timeout"
        bundled_node_modules = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
        for script in BROWSER_CHECKS:
            folder = output / Path(script).stem
            folder.mkdir()
            # Chromium adds long GPU-cache names under TEMP on Windows.
            # Keep its isolated profile short even when evidence paths are long.
            with TemporaryDirectory(prefix="hmbp-", ignore_cleanup_errors=True) as scratch:
                env = isolated_environment(Path(scratch), standard, editor)
                # Chrome needs the Windows shell's real profile variables to
                # recognize Playwright's separately supplied user-data-dir.
                env.update({key: os.environ[key] for key in ("USERPROFILE", "LOCALAPPDATA", "APPDATA")})
                env.update(NODE_PATH=os.environ.get("NODE_PATH", str(bundled_node_modules)),
                           HMB_LIFECYCLE_REPORT_DIR=str(folder), HMB_REGRESSION_PYTHON=str(python),
                           HMB_HEADER_0130_CANDIDATE=str(reviewed_header),
                           HMB_STOCK_EDITOR_0130_SOURCE=str(stock))
                if legacy_editor_fixture is not None:
                    env["HMB_NATIVE_HEADER_EDITOR_SOURCE"] = str(legacy_editor_fixture)
                command = [node, str(TESTS / script)]
                if script == DELETION_CHECK:
                    command += ["--evidence-path", str(folder / "native-safety.json")]
                with (folder / "test.log").open("wb") as log:
                    try:
                        check = subprocess.run(command, cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=60, check=False)
                        result["checks"][script] = check.returncode
                    except subprocess.TimeoutExpired:
                        result["checks"][script] = "timeout"
        if (inspect_candidate(candidate, header_source=header_source) != result["identity"]
                or digest(header_source) != result["header_source_sha256"]
                or product_digest() != result["hmb_source_sha256"]
                or digest(reviewed_header) != result["tested_header_sha256"]
                or digest(standard_manifest) != result["standard_manifest_sha256"]
                or source_tree_digest(standard) != result["standard_source_sha256"]
                or (legacy_editor_fixture is not None and digest(legacy_editor_fixture) != result["legacy_fixture_sha256"])):
            raise ValueError("Candidate or source identity changed while checks ran")
        proof = output / "HMB_Image_Bash_Apply_Readiness_Host_Regression/bash/APPLY-REOPEN-HOST-RESULT.json"
        if set(result["checks"]) == expected and all(code == 0 for code in result["checks"].values()):
            report = json.loads(proof.read_bytes())
            if (not isinstance(report, dict) or not report.get("two_sources")
                    or not report.get("native_sdk_save_reopen_preserves_owned_scene_and_two_wires")
                    or report.get("paid_calls") != 0):
                raise ValueError("Bash readiness evidence is incomplete")
            header_proof = output / Path(HEADER_CHECK).stem / "header-0130.json"
            validate_header_evidence(header_proof, result["tested_header_sha256"])
            deletion_proof = output / Path(DELETION_CHECK).stem / "native-safety.json"
            validate_deletion_evidence(deletion_proof)
            result["evidence_sha256"] = {
                path.relative_to(output).as_posix(): digest(path) for path in (proof, header_proof, deletion_proof)
            }
            result["status"] = "AUTOMATED_CHECKS_PASSED"
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        result["error"] = str(exc)
    passed = sum(code == 0 for code in result["checks"].values())
    result["check_counts"] = {
        "required": len(expected), "passed": passed, "failed": len(result["checks"]) - passed,
        "not_run": len(expected - result["checks"].keys()),
    }
    (output / "upgrade-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{result['status']}: {output / 'upgrade-check.json'}")
    return 0 if result["status"] == "AUTOMATED_CHECKS_PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--standard", type=Path, default=Path.home() / "Documents/GriptapeNodes/libraries/griptape-nodes-library-standard")
    parser.add_argument("--node", default=shutil.which("node"), help="Node.js executable for the isolated browser check")
    parser.add_argument("--legacy-editor-fixture", type=Path,
                        help="Hash-checked original editor fixture used for the existing native React test harness")
    parser.add_argument("--header-source", type=Path, default=HEADER_SOURCE,
                        help="Local Editor header source to compile and test in the staged candidate")
    parser.add_argument("--output", type=Path, required=True, help="New directory for isolated profiles and evidence")
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js is required for the editor check")
    candidate = args.candidate.resolve(strict=True)
    local = Path(os.environ["LOCALAPPDATA"]) / "ai.griptape.nodes.desktop"
    if candidate.is_relative_to(local.resolve()):
        parser.error("Use a staged Desktop distribution outside the live installation")
    standard = args.standard.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(candidate) or output.is_relative_to(local.resolve()):
        parser.error("Keep evidence outside the Desktop program files")
    output.mkdir(parents=True, exist_ok=False)
    return run(candidate, standard, output, args.node, args.legacy_editor_fixture,
               header_source=args.header_source.resolve())


if __name__ == "__main__":
    sys.exit(main())
