from __future__ import annotations

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
    for forbidden_call in (
        "get_or_fetch_platform_executables_else_raise(",
        "add_paths(",
        "get_ffmpeg_exe(",
    ):
        assert forbidden_call not in helper_source

    generator_source = (ROOT / "HMBSeedanceGeneration.py").read_text(
        encoding="utf-8"
    )
    method = generator_source.index("async def _process_generation_impl")
    new_run_guard = generator_source.index("if not resume_generation_id", method)
    verifier = generator_source.index(
        "decode_verifier = await asyncio.to_thread", new_run_guard
    )
    broker = generator_source.index(
        "bridge = await self._ensure_broker_connected()", verifier
    )
    billable = generator_source.index("bridge.generate_seedance", broker)
    assert method < new_run_guard < verifier < broker < billable


assert_griptape_package_candidate_is_off_path()
assert_real_package_decode_without_path()
assert_no_runtime_fetch_and_prebilling_order()

print("HMB Seedance portable MP4 verifier regression: PASS")
