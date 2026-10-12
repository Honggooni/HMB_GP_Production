"""Explicit regression inventory and honest CI coverage results.

Discovery only verifies registration; it never opts new scripts into execution.
Native SDK/DCC checks need an explicit entry and are never inferred from a mock
test passing. Required browser checks cannot silently exit zero after SKIP.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ".github/hmb-regression-coverage.json"
COVERAGE_TYPES = {"python_contract", "javascript_contract", "host_browser", "installed_sdk", "native_maya", "native_blender"}
# A status occupies a complete result line (or the final browser clause).
# Narrative checks such as "required browser skip fails" are passing-test
# descriptions, not runtime availability outcomes.
_SKIP = re.compile(
    r"(?mi)(?:^\s*(?:[^\r\n:=]+[:=]\s*)?(?:SKIP|NOT[ _]RUN)(?:\s+(?:browser|host|native))?"
    r"\s*(?:\([^\r\n]*\)|[:-]\s*[^\r\n]*)?\s*$"
    r"|(?:^|;)\s*browser\s+SKIP\s*(?:\([^\r\n]*\)|[:-]\s*[^\r\n]*)?\s*$)"
)


def _configure_console() -> None:
    # A UTF-8 child can legally emit a replacement character or emoji that a
    # Windows cp949 parent cannot print. This is a runner transport concern,
    # never a reason to hide a test's actual failure or skip.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def validate_registry(root: Path = ROOT, registry: str = REGISTRY) -> list[dict[str, Any]]:
    payload = json.loads((root / registry).read_text(encoding="utf-8"))
    if payload.get("schema") != "hmb-regression-coverage" or payload.get("version") != 1:
        raise ValueError("Unsupported regression coverage registry")
    rows = payload.get("tests")
    if not isinstance(rows, list):
        raise ValueError("Coverage tests must be an explicit list")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid coverage entry")
        name = row.get("name")
        if (not isinstance(name, str) or not re.fullmatch(r"HMB_[A-Za-z0-9_]+\.(?:py|mjs)", name)
                or name in seen or row.get("coverage") not in COVERAGE_TYPES
                or row.get("mode") not in {"ci", "manual"} or type(row.get("required")) is not bool):
            raise ValueError(f"Invalid or duplicate coverage entry: {name}")
        if row["mode"] == "manual" and not str(row.get("reason") or "").strip():
            raise ValueError(f"Manual coverage needs a reason: {name}")
        extensions = row.get("manual_extensions", [])
        if not isinstance(extensions, list):
            raise ValueError(f"Invalid native extensions: {name}")
        for extension in extensions:
            if (not isinstance(extension, dict) or extension.get("coverage") not in {"native_maya", "native_blender", "installed_sdk"}
                    or not isinstance(extension.get("args"), list) or not extension["args"]
                    or not all(isinstance(arg, str) and arg.startswith("--") for arg in extension["args"])
                    or not str(extension.get("reason") or "").strip()):
                raise ValueError(f"Invalid manual native extension: {name}")
        seen.add(name)
    discovered = {path.name for path in (root / "resources/tests").iterdir()
                  if path.is_file() and path.name.startswith("HMB_") and path.suffix in {".py", ".mjs"}}
    missing, stale = sorted(discovered - seen), sorted(seen - discovered)
    if missing or stale:
        raise ValueError(f"Regression registration mismatch: unregistered={missing}; missing_files={stale}")
    return rows


def classify_result(row: dict[str, Any], returncode: int, output: str) -> tuple[str, str]:
    if returncode:
        return "failed", "nonzero_exit"
    if _SKIP.search(output):
        return ("failed", "required_coverage_skipped") if row["required"] else ("not_run", "optional_runtime_unavailable")
    return "passed", "exit_zero_without_skip"


def run_registered(root: Path, rows: list[dict[str, Any]], language: str,
                   report: Path, *, node: str = "node") -> int:
    _configure_console()
    suffix = ".py" if language == "python" else ".mjs"
    selected = [row for row in rows if row["name"].endswith(suffix)]
    results = [{"name": row["name"], "coverage": row["coverage"], "status": "not_run",
                "reason": row.get("reason", "earlier_test_failed"), "required": row["required"]} for row in selected]
    failed = False
    for index, row in enumerate(selected):
        if row["mode"] == "manual" or failed:
            continue
        command = [sys.executable if language == "python" else node, str(root / "resources/tests" / row["name"])]
        start = time.monotonic()
        try:
            child_env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            completed = subprocess.run(command, cwd=root, text=True, encoding="utf-8", errors="replace",
                                       capture_output=True, timeout=900, env=child_env)
            output = completed.stdout + completed.stderr
            # Existing scripts remain the source of detailed failure output.
            # The machine-readable receipt contains only bounded status data.
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
            status, reason = classify_result(row, completed.returncode, output)
            code = completed.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            status, reason, code = "failed", type(error).__name__, -1
        results[index].update(status=status, reason=reason, exit_code=code, elapsed_seconds=round(time.monotonic() - start, 3))
        failed = status == "failed"
        print(f"HMB_COVERAGE {row['coverage']} {status} {row['name']}", flush=True)
    for row in selected:
        for extension in row.get("manual_extensions", []):
            results.append({"name": row["name"], "coverage": extension["coverage"], "status": "not_run",
                            "reason": extension["reason"], "args": extension["args"], "required": False})
    summary = {status: sum(item["status"] == status for item in results) for status in ("passed", "failed", "not_run")}
    payload = {"schema": "hmb-regression-results", "version": 1, "language": language,
               "registered_file_count": len(selected), "summary": summary, "results": results}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"HMB_COVERAGE_SUMMARY {language} {json.dumps(summary, sort_keys=True)}", flush=True)
    return 1 if failed else 0


def main() -> int:
    _configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", choices=("python", "javascript"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", default=REGISTRY)
    args = parser.parse_args()
    rows = validate_registry(args.root, args.registry)
    print(f"HMB_REGRESSION_INVENTORY_OK files={len(rows)}")
    if args.run:
        if args.report is None:
            parser.error("--run requires --report")
        return run_registered(args.root, rows, args.run, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
