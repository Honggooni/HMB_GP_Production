from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker


MAYA_RUNNER = ROOT / "resources" / "maya" / "HMB_Maya_Background_Preview.py"
MAYA_COMMAND = picker._maya_runner_command()
MEDIA_SUFFIXES = {".avi", ".mov", ".mp4", ".png"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "scene"


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _source_fingerprint(path: Path) -> Tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return payload


def _log_tail(path: Path, limit_bytes: int = 65536, line_count: int = 30) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    text = data[-limit_bytes:].decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-line_count:])


def _normalise_warnings(payload: Dict[str, Any]) -> List[str]:
    raw = payload.get("warnings")
    if not isinstance(raw, list):
        return [_clean(raw)] if _clean(raw) else []
    return [_clean(item) for item in raw if _clean(item)]


def _validate_result(payload: Dict[str, Any], case_root: Path) -> Tuple[Dict[str, bool], List[str]]:
    outliner = payload.get("outliner_nodes")
    cameras = payload.get("cameras")
    start_frame = payload.get("start_frame")
    current_frame = payload.get("current_frame")
    end_frame = payload.get("end_frame")
    fps = payload.get("fps")

    checks = {
        "ok": payload.get("ok") is True,
        "operation_scan": payload.get("operation") == "scan",
        "outliner": isinstance(outliner, list) and bool(outliner),
        "cameras": isinstance(cameras, list) and bool(cameras),
        "range": (
            _finite_number(start_frame)
            and _finite_number(current_frame)
            and _finite_number(end_frame)
            and float(end_frame) >= float(start_frame)
        ),
        "fps": _finite_number(fps) and float(fps) > 0.0,
        "original_frame_count_zero": (
            not isinstance(payload.get("original_frame_count"), bool)
            and payload.get("original_frame_count") == 0
        ),
        "original_frames_folder_empty": not _clean(payload.get("original_frames_folder")),
        "original_output_name_empty": (
            not _clean(payload.get("original_output_name"))
            and not _clean(payload.get("output_name"))
        ),
        "original_frame_map_empty": not (payload.get("original_frame_map") or []),
        "no_temp_render_artifacts": not any(
            path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
            for path in case_root.rglob("*")
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return checks, failures


def _run_case(
    index: int,
    source_arg: Path,
    matrix_root: Path,
    mayabatch: Optional[Path],
    maya_version: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    started = time.perf_counter()
    source_scene = source_arg.expanduser().resolve()
    case_root = matrix_root / f"{index:02d}_{_safe_name(source_scene.stem)}"
    case_root.mkdir(parents=True, exist_ok=False)
    job_path = case_root / "scan.job.json"
    result_path = case_root / "scan.result.json"
    progress_path = case_root / "scan.progress.json"
    log_path = case_root / "mayabatch.log"

    record: Dict[str, Any] = {
        "scene": str(source_scene),
        "status": "FAIL",
        "elapsed_seconds": 0.0,
        "warnings": [],
        "error": "",
        "return_code": None,
        "checks": {},
        "metadata": {},
    }
    before_fingerprint: Optional[Tuple[int, int]] = None

    try:
        if not source_scene.is_file() or source_scene.suffix.lower() not in {".ma", ".mb"}:
            raise FileNotFoundError(f"A Maya .ma or .mb scene is required: {source_scene}")
        if not MAYA_RUNNER.is_file():
            raise FileNotFoundError(f"Maya background runner was not found: {MAYA_RUNNER}")
        if mayabatch is None:
            raise FileNotFoundError(
                "No mayabatch installation was found. Install Maya or set MAYA_LOCATION/PATH."
            )

        before_fingerprint = _source_fingerprint(source_scene)
        job = {
            "operation": "scan",
            "scene_path": str(source_scene),
            "result_path": str(result_path),
            "progress_path": str(progress_path),
            "generate_original_video": False,
            "original_frames_folder": "",
            "original_output_name": "",
            "camera": "",
            "expected_maya_major": maya_version if maya_version.isdigit() else "",
        }
        job_path.write_text(
            json.dumps(job, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        command = [str(mayabatch)]
        # The source project is read only and is used solely to resolve relative
        # references. Every job, result, progress file, log, and working path is
        # rooted in case_root; this test never creates an output beside the scene.
        maya_project = picker._find_maya_project(source_scene)
        if maya_project is not None:
            command.extend(["-proj", str(maya_project)])
        command.extend(["-command", MAYA_COMMAND])

        env = picker._maya_subprocess_environment(job_path)
        creationflags = picker._creation_flags()
        with log_path.open("wb") as log_handle:
            completed = subprocess.run(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(case_root),
                creationflags=creationflags,
                timeout=timeout_seconds,
                check=False,
            )
        record["return_code"] = completed.returncode

        if not result_path.is_file():
            raise RuntimeError(
                f"mayabatch exited with code {completed.returncode} without a result JSON."
            )
        payload = _read_json(result_path)
        record["warnings"] = _normalise_warnings(payload)
        checks, failures = _validate_result(payload, case_root)
        checks["mayabatch_exit_zero"] = completed.returncode == 0
        if completed.returncode != 0:
            failures.append("mayabatch_exit_zero")
        checks["source_scene_unchanged"] = _source_fingerprint(source_scene) == before_fingerprint
        if not checks["source_scene_unchanged"]:
            failures.append("source_scene_unchanged")

        record["checks"] = checks
        record["metadata"] = {
            "maya_version": payload.get("maya_version"),
            "outliner_count": len(payload.get("outliner_nodes") or []),
            "camera_count": len(payload.get("cameras") or []),
            "selected_camera": payload.get("selected_camera"),
            "start_frame": payload.get("start_frame"),
            "current_frame": payload.get("current_frame"),
            "end_frame": payload.get("end_frame"),
            "fps": payload.get("fps"),
            "original_frame_count": payload.get("original_frame_count"),
            "original_frames_folder": payload.get("original_frames_folder"),
            "original_output_name": payload.get("original_output_name"),
        }
        if failures:
            payload_error = _clean(payload.get("error"))
            failure_text = ", ".join(failures)
            record["error"] = (
                f"{payload_error}; failed checks: {failure_text}"
                if payload_error
                else f"Failed checks: {failure_text}"
            )
        else:
            record["status"] = "PASS"
    except subprocess.TimeoutExpired:
        record["status"] = "TIMEOUT"
        record["error"] = f"mayabatch exceeded {timeout_seconds:g} seconds."
    except Exception as exc:
        record["error"] = f"{exc.__class__.__name__}: {exc}"
    finally:
        if (
            before_fingerprint is not None
            and source_scene.is_file()
            and _source_fingerprint(source_scene) != before_fingerprint
        ):
            record["status"] = "FAIL"
            suffix = "Source scene size or modification time changed during READ."
            record["error"] = f"{record['error']}; {suffix}".strip("; ")
            record.setdefault("checks", {})["source_scene_unchanged"] = False
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        if record["status"] != "PASS":
            tail = _log_tail(log_path)
            if tail:
                record["mayabatch_log_tail"] = tail
            if progress_path.is_file():
                try:
                    record["last_progress"] = _read_json(progress_path)
                except Exception:
                    pass

    return record


def _table_text(results: Sequence[Dict[str, Any]]) -> str:
    rows: List[Tuple[str, str, str, str]] = []
    for result in results:
        scene_name = Path(_clean(result.get("scene"))).name or _clean(result.get("scene"))
        warning_items = list(result.get("warnings") or [])
        if result.get("error"):
            warning_items.append("ERROR: " + _clean(result["error"]))
        warning_text = " | ".join(
            item.replace("\r", " ").replace("\n", " ") for item in warning_items
        ) or "-"
        if len(warning_text) > 140:
            warning_text = warning_text[:137] + "..."
        rows.append(
            (
                scene_name,
                f"{float(result.get('elapsed_seconds') or 0.0):.3f}",
                _clean(result.get("status")) or "FAIL",
                warning_text,
            )
        )

    headers = ("SCENE", "ELAPSED(S)", "STATUS", "WARNINGS")
    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]
    separator = "-+-".join("-" * width for width in widths)
    lines = [
        " | ".join(headers[column].ljust(widths[column]) for column in range(len(headers))),
        separator,
    ]
    lines.extend(
        " | ".join(row[column].ljust(widths[column]) for column in range(len(headers)))
        for row in rows
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run metadata-only HMBVideoPicker READ scans across Maya scenes without "
            "creating original playblast frames or writing beside the source scenes."
        )
    )
    parser.add_argument("scenes", nargs="+", type=Path, help="Maya .ma/.mb scene paths.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=900.0,
        help="Per-scene mayabatch timeout (default: 900).",
    )
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be a finite number greater than zero.")

    mayabatch = picker._find_mayabatch()
    maya_version = picker._maya_display_version(mayabatch) if mayabatch else ""
    matrix_started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="HMB_VideoPicker_Fast_Read_") as temp_text:
        matrix_root = Path(temp_text)
        results = [
            _run_case(
                index=index,
                source_arg=scene,
                matrix_root=matrix_root,
                mayabatch=mayabatch,
                maya_version=maya_version,
                timeout_seconds=args.timeout_seconds,
            )
            for index, scene in enumerate(args.scenes, start=1)
        ]

        passed = sum(1 for item in results if item.get("status") == "PASS")
        failed = len(results) - passed
        summary = {
            "schema": "hmb-video-picker-fast-read-scene-matrix",
            "ok": failed == 0,
            "mayabatch": str(mayabatch or ""),
            "maya_version": maya_version,
            "runner": str(MAYA_RUNNER),
            "scene_count": len(results),
            "passed": passed,
            "failed": failed,
            "elapsed_seconds": round(time.perf_counter() - matrix_started, 3),
            "temp_only": True,
            "results": results,
        }

        print(_table_text(results))
        print("\nHMB_FAST_READ_SUMMARY_JSON")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
