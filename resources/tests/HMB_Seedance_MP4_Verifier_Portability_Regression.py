from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import _hmb_mp4_verify as verifier_target


def assert_griptape_package_candidate_is_off_path() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        package_root = Path(temporary) / "static_ffmpeg"
        binary_root = package_root / "bin" / (
            "win32" if os.name == "nt" else "linux"
        )
        binary_root.mkdir(parents=True)
        module_file = package_root / "__init__.py"
        module_file.write_text("", encoding="utf-8")
        executable = binary_root / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        executable.write_bytes(b"package-local verifier fixture")
        fake_package = SimpleNamespace(__file__=str(module_file))

        original_import = verifier_target.importlib.import_module

        def import_package(name: str):
            if name == "static_ffmpeg":
                return fake_package
            return original_import(name)

        with mock.patch.object(
            verifier_target.importlib,
            "import_module",
            side_effect=import_package,
        ), mock.patch.dict(os.environ, {"PATH": ""}):
            candidates = list(verifier_target._static_ffmpeg_verifier_candidates())
        assert candidates[0] == verifier_target.MP4DecodeVerifier(
            "ffprobe", executable.resolve()
        )


def assert_real_package_decode_without_path() -> None:
    malicious_override = str(ROOT / ".tmp" / "untrusted-ffmpeg.exe")
    try:
        import imageio_ffmpeg
    except ImportError:
        import static_ffmpeg

        package_root = Path(static_ffmpeg.__file__).resolve().parent
        with mock.patch.object(
            verifier_target,
            "_imageio_ffmpeg_verifier_candidates",
            return_value=iter(()),
        ), mock.patch.object(
            verifier_target,
            "_system_verifier_candidates",
            return_value=iter(()),
        ), mock.patch.dict(
            os.environ,
            {"PATH": "", "IMAGEIO_FFMPEG_EXE": malicious_override},
        ):
            selected = verifier_target.resolve_mp4_decode_verifier()
        creator = selected.executable.with_name(
            "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        )
    else:
        package_root = Path(imageio_ffmpeg.__file__).resolve().parent
        with mock.patch.object(
            verifier_target,
            "_static_ffmpeg_verifier_candidates",
            return_value=iter(()),
        ), mock.patch.object(
            verifier_target,
            "_system_verifier_candidates",
            return_value=iter(()),
        ), mock.patch.dict(
            os.environ,
            {"PATH": "", "IMAGEIO_FFMPEG_EXE": malicious_override},
        ):
            selected = verifier_target.resolve_mp4_decode_verifier()
        assert selected.backend == "ffmpeg"
        creator = selected.executable

    selected.executable.relative_to(package_root)
    assert selected.executable != Path(malicious_override)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        valid = root / "한글 portable verifier.mp4"
        with mock.patch.dict(
            os.environ,
            {"PATH": "", "IMAGEIO_FFMPEG_EXE": malicious_override},
        ):
            create = subprocess.run(
                [
                    str(creator),
                    "-y",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=16x16:d=0.1",
                    "-frames:v",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                    str(valid),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            assert create.returncode == 0, type(create.stderr).__name__
            verifier_target.validate_decodable_mp4_file(valid, selected)

            corrupt = root / "corrupt.mp4"
            corrupt.write_bytes(b"not a decodable MP4")
            try:
                verifier_target.validate_decodable_mp4_file(corrupt, selected)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Corrupt MP4 passed the portable decode verifier")


def assert_no_runtime_fetch_and_prebilling_order() -> None:
    helper_source = (ROOT / "_hmb_mp4_verify.py").read_text(encoding="utf-8")
    forbidden_calls = {
        "get_or_fetch_platform_executables_else_raise", "add_paths", "get_ffmpeg_exe",
    }

    def name(expression: ast.expr) -> str:
        if isinstance(expression, ast.Name):
            return expression.id
        if isinstance(expression, ast.Attribute):
            return expression.attr
        return ""

    helper_tree = ast.parse(helper_source)
    for expression in ast.walk(helper_tree):
        if isinstance(expression, ast.Call):
            assert name(expression.func) not in forbidden_calls, (
                "Decode verifier must use installed executables without runtime fetch."
            )

    generator_source = (ROOT / "HMBSeedanceGeneration.py").read_text(
        encoding="utf-8"
    )
    generator_tree = ast.parse(generator_source)
    generator_class = next(expression for expression in generator_tree.body
                           if isinstance(expression, ast.ClassDef)
                           and expression.name == "HMBSeedanceGeneration")
    method = next(expression for expression in generator_class.body
                  if isinstance(expression, ast.AsyncFunctionDef)
                  and expression.name == "_process_generation_impl")

    def calls(target: str) -> list[ast.Call]:
        # Blocking work is passed as the first positional argument rather than
        # called directly. Inspect its actual dispatch, not a source substring
        # that could match comments, another method or a reordered output block.
        return sorted((expression for expression in ast.walk(method)
                       if isinstance(expression, ast.Call) and (
                           name(expression.func) == target
                           or (name(expression.func) in {"_run_blocking_generation_stage", "to_thread",
                                                         "_await_submission_result"}
                               and expression.args and name(expression.args[0]) == target))),
                      key=lambda expression: (expression.lineno, expression.col_offset))

    def first_line(target: str) -> int:
        matches = calls(target)
        assert matches, "Required generation boundary is missing: " + target
        return matches[0].lineno

    def guards_call(guard: ast.If, target: ast.Call) -> bool:
        # The call must occur in the guarded true branch; an else-only resolver
        # would incorrectly verify existing-task retrieval instead of new work.
        return any(target is expression for statement in guard.body
                   for expression in ast.walk(statement))

    shot_resolution = first_line("_resolve_exact_shot_generation_inputs")
    shot_calls = calls("_resolve_exact_shot_generation_inputs")
    expected_shot_guard = ast.parse(
        "not params['resume_generation_id'] and not draft_final", mode="eval",
    ).body
    expected_guard_terms = {ast.dump(term) for term in expected_shot_guard.values}
    assert len(shot_calls) == 1 and any(
        isinstance(expression, ast.If)
        and isinstance(expression.test, ast.BoolOp)
        and isinstance(expression.test.op, ast.And)
        and {ast.dump(term) for term in expression.test.values} == expected_guard_terms
        and guards_call(expression, shot_calls[0])
        for expression in ast.walk(method)
    ), "Live Shot inputs must be resolved only for new ordinary/Draft preview renders."
    validation = first_line("_validate_parameters")
    verifier_calls = calls("_resolve_mp4_decode_verifier")
    assert len(verifier_calls) == 1, "New submissions require exactly one verifier resolution."
    verifier = verifier_calls[0].lineno
    assert any(isinstance(expression, ast.If)
               and isinstance(expression.test, ast.UnaryOp)
               and isinstance(expression.test.op, ast.Not)
               and name(expression.test.operand) == "resume_generation_id"
               and guards_call(expression, verifier_calls[0])
               for expression in ast.walk(method)), (
        "Local decode verifier must guard new work without gating existing-task retrieval."
    )
    broker = first_line("_ensure_broker_connected")
    destination = first_line("_build_generation_output_destination")
    output_preflight = first_line("_preflight_output_destination")
    media_preparation = first_line("_prepare_video_references_for_run")
    billable = first_line("generate_seedance")
    assert (
        shot_resolution
        < validation
        < verifier
        < broker
        < media_preparation
        < billable
    ), "Inputs and installed decode verification must precede Broker, uploads and billable create."
    assert destination < output_preflight < media_preparation < billable, (
        "The selected output destination must be writable before uploads or billable create."
    )


assert_griptape_package_candidate_is_off_path()
assert_real_package_decode_without_path()
assert_no_runtime_fetch_and_prebilling_order()

print("HMB Seedance portable MP4 verifier regression: PASS")
