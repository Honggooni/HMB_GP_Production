"""Registration mutation, required browser skips and unexecuted native proof."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("hmb_coverage", ROOT/"tools/audit_regression_coverage.py")
assert spec and spec.loader
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)

with tempfile.TemporaryDirectory(prefix="hmb-coverage-inventory-") as directory:
    root = Path(directory)
    (root/"resources/tests").mkdir(parents=True)
    (root/".github").mkdir()
    test = root/"resources/tests/HMB_Example_Regression.py"
    test.write_text("import os, sys\nfrom pathlib import Path\nassert os.environ['PYTHONUTF8']=='1'\nassert os.environ['PYTHONIOENCODING']=='utf-8'\nassert Path(os.environ['HMB_REGRESSION_PYTHON']).resolve()==Path(sys.executable).resolve()\nprint('PASS 한글 😀 \\ufffd fixture')", encoding="utf-8")
    row = {"name": test.name, "mode": "ci", "coverage": "python_contract", "required": True,
           "manual_extensions": [{"coverage": "native_maya", "args": ["--live-maya"], "reason": "Maya not part of hostless CI"}]}
    registry = root/coverage.REGISTRY
    registry.write_text(json.dumps({"schema": "hmb-regression-coverage", "version": 1, "tests": [row]}), encoding="utf-8")
    rows = coverage.validate_registry(root)
    report = root/"result.json"
    assert coverage.run_registered(root, rows, "python", report) == 0
    result = json.loads(report.read_text())
    assert result["summary"] == {"passed": 1, "failed": 0, "not_run": 1}
    assert result["results"][1]["coverage"] == "native_maya"
    unknown = root/"resources/tests/HMB_New_Regression.py"
    unknown.write_text("raise AssertionError('must not run automatically')", encoding="utf-8")
    try:
        coverage.validate_registry(root)
        raise AssertionError("Unregistered Python regression accepted")
    except ValueError as error:
        assert "unregistered" in str(error) and unknown.name in str(error)
    unknown.unlink()
    unknown_cjs = root/"resources/tests/HMB_Unknown_Regression.cjs"
    unknown_cjs.write_text("throw Error('unregistered must not run')", encoding="utf-8")
    try:
        coverage.validate_registry(root)
        raise AssertionError("Unregistered CommonJS regression accepted")
    except ValueError as error:
        assert "unregistered" in str(error) and unknown_cjs.name in str(error)
    unknown_cjs.unlink()
    test.unlink()
    try:
        coverage.validate_registry(root)
        raise AssertionError("Stale registration accepted")
    except ValueError as error:
        assert "missing_files" in str(error)

with tempfile.TemporaryDirectory(prefix="hmb-coverage-javascript-") as directory:
    root = Path(directory)
    (root/"resources/tests").mkdir(parents=True)
    (root/".github").mkdir()
    node = os.environ.get("HMB_REGRESSION_NODE") or shutil.which("node")
    assert node, "Node is required to verify CommonJS/ESM execution, not only registration"
    scripts = {
        "HMB_CommonJS_Regression.cjs": "const a=require('node:assert/strict');a.ok(process.env.HMB_TEST_PYTHON);a.equal(process.env.HMB_TEST_PYTHON,process.env.HMB_REGRESSION_PYTHON);console.log('PASS CommonJS fixture');",
        "HMB_ESM_Regression.mjs": "import a from 'node:assert/strict';a.ok(process.env.HMB_TEST_PYTHON);a.equal(process.env.HMB_TEST_PYTHON,process.env.HMB_REGRESSION_PYTHON);console.log('PASS ESM fixture');",
    }
    rows = [{"name": name, "mode": "ci", "coverage": "javascript_contract", "required": True}
            for name in scripts]
    for name, content in scripts.items():
        (root/"resources/tests"/name).write_text(content, encoding="utf-8")
    registry = root/coverage.REGISTRY
    registry.write_text(json.dumps({"schema": "hmb-regression-coverage", "version": 1, "tests": rows}), encoding="utf-8")
    assert coverage.validate_registry(root) == rows
    report = root/"javascript.json"
    assert coverage.run_registered(root, rows, "javascript", report, node=node) == 0
    result = json.loads(report.read_text("utf-8"))
    assert result["registered_file_count"] == 2
    assert result["summary"] == {"passed": 2, "failed": 0, "not_run": 0}
    assert {r["name"] for r in result["results"]} == set(scripts)
    (root/"resources/tests"/rows[0]["name"]).write_text("process.exitCode=7;", encoding="utf-8")
    assert coverage.run_registered(root, rows, "javascript", report, node=node) == 1
    result = json.loads(report.read_text("utf-8"))
    assert result["summary"] == {"passed": 0, "failed": 1, "not_run": 1}
    assert result["results"][0]["exit_code"] == 7
    rows[0].update(mode="manual", required=False, reason="Deliberate nonexecuted fixture")
    assert coverage.run_registered(root, rows, "javascript", report, node=node) == 0
    result = json.loads(report.read_text("utf-8"))
    assert result["summary"] == {"passed": 1, "failed": 0, "not_run": 1}
    assert result["results"][0]["reason"] == "Deliberate nonexecuted fixture"

browser = {"required": True}
assert coverage.classify_result(browser, 0, "PASS snapshot state; browser SKIP (unavailable)") == ("failed", "required_coverage_skipped")
assert coverage.classify_result(browser, 0, "Widget: SKIP (browser unavailable)") == ("failed", "required_coverage_skipped")
assert coverage.classify_result(browser, 0, "Picker: SKIP browser (draft checks passed)") == ("failed", "required_coverage_skipped")
assert coverage.classify_result(browser, 0, "SKIP") == ("failed", "required_coverage_skipped")
assert coverage.classify_result(browser, 0, "ImageAsset full mount Chrome: NOT RUN (browser unavailable)") == ("failed", "required_coverage_skipped")
assert coverage.classify_result({"required": False}, 0, "HOST=NOT_RUN (SDK absent)") == ("not_run", "optional_runtime_unavailable")
assert coverage.classify_result({"required": False}, 0, "HOST=SKIP (SDK absent)") == ("not_run", "optional_runtime_unavailable")
assert coverage.classify_result(browser, 0, "PASS legitimate skipped-input behavior") == ("passed", "exit_zero_without_skip")
assert coverage.classify_result(browser, 0, "HMB regression coverage inventory: PASS (missing/stale registration fails; required browser skip fails; native is not_run)") == ("passed", "exit_zero_without_skip")
assert coverage.classify_result(browser, 0, "PASS: SKIP detection rejects missing runtimes") == ("passed", "exit_zero_without_skip")
assert coverage.classify_result(browser, 0, "PASS: NOT RUN detection rejects missing runtimes") == ("passed", "exit_zero_without_skip")
assert coverage.classify_result(browser, 1, "PASS earlier checks") == ("failed", "nonzero_exit")
coverage.validate_registry(ROOT)
print("HMB regression coverage inventory: PASS (missing/stale registration fails; required browser skip fails; native is not_run)")
