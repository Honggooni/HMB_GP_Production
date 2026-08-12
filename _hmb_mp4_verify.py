from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


MP4_DECODE_PROBE_TIMEOUT_SECONDS = 20.0
MP4_DECODE_VERIFIER_START_TIMEOUT_SECONDS = 5.0
MP4_DECODE_PROBE_MAX_OUTPUT_BYTES = 64 * 1024
MP4_DECODE_PROBE_PACKET_LIMIT = 128


@dataclass(frozen=True)
class MP4DecodeVerifier:
    backend: str
    executable: Path


def _trusted_package_executable(
    candidate: Path,
    *,
    package_root: Path,
) -> Path | None:
    """Resolve a package-owned binary without following it outside the package."""

    try:
        trusted_root = package_root.resolve(strict=True)
        executable = candidate.resolve(strict=True)
        executable.relative_to(trusted_root)
    except (OSError, ValueError):
        return None
    return executable if executable.is_file() else None


def _platform_static_ffmpeg_folders() -> tuple[str, ...]:
    machine = platform.machine().casefold()
    is_arm = machine in {"arm64", "aarch64"}
    if os.name == "nt":
        return ("win32", "win64")
    if sys.platform == "darwin":
        return ("darwin_arm64", "darwin") if is_arm else ("darwin",)
    if sys.platform.startswith("linux"):
        return ("linux_arm64", "linux") if is_arm else ("linux",)
    return ()


def _static_ffmpeg_verifier_candidates() -> Iterator[MP4DecodeVerifier]:
    """Yield already-installed Griptape binaries without calling fetch helpers."""

    try:
        package = importlib.import_module("static_ffmpeg")
        module_file = getattr(package, "__file__", None)
        if not module_file:
            return
        package_root = Path(module_file).resolve(strict=True).parent
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return

    names = {
        "ffprobe": ("ffprobe.exe", "ffprobe") if os.name == "nt" else ("ffprobe",),
        "ffmpeg": ("ffmpeg.exe", "ffmpeg") if os.name == "nt" else ("ffmpeg",),
    }
    for backend in ("ffprobe", "ffmpeg"):
        for platform_folder in _platform_static_ffmpeg_folders():
            for executable_name in names[backend]:
                executable = _trusted_package_executable(
                    package_root / "bin" / platform_folder / executable_name,
                    package_root=package_root,
                )
                if executable is not None:
                    yield MP4DecodeVerifier(backend, executable)


def _imageio_package_roots() -> Iterator[Path]:
    """Yield only imported or library-venv package roots; never use env/PATH APIs."""

    seen: set[str] = set()
    candidates: list[Path] = []
    try:
        package = importlib.import_module("imageio_ffmpeg")
        module_file = getattr(package, "__file__", None)
        if module_file:
            candidates.append(Path(module_file).resolve(strict=True).parent)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass

    library_root = Path(__file__).resolve().parent
    candidates.append(
        library_root / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg"
    )
    candidates.extend(
        (library_root / ".venv" / "lib").glob(
            "python*/site-packages/imageio_ffmpeg"
        )
    )
    for candidate in candidates:
        try:
            package_root = candidate.resolve(strict=True)
        except OSError:
            continue
        if not (package_root / "__init__.py").is_file():
            continue
        key = os.path.normcase(str(package_root))
        if key in seen:
            continue
        seen.add(key)
        yield package_root


def _imageio_ffmpeg_verifier_candidates() -> Iterator[MP4DecodeVerifier]:
    """Yield pinned wheel binaries by containment, without ambient resolver APIs."""

    seen: set[str] = set()
    for package_root in _imageio_package_roots():
        binary_root = package_root / "binaries"
        try:
            candidates = tuple(
                candidate
                for candidate in sorted(binary_root.iterdir())
                if candidate.name.casefold().startswith("ffmpeg-")
                and (os.name != "nt" or candidate.suffix.casefold() == ".exe")
            )
        except OSError:
            continue
        for candidate in candidates:
            executable = _trusted_package_executable(
                candidate,
                package_root=package_root,
            )
            if executable is None:
                continue
            key = os.path.normcase(str(executable))
            if key in seen:
                continue
            seen.add(key)
            yield MP4DecodeVerifier("ffmpeg", executable)


def _system_verifier_candidates() -> Iterator[MP4DecodeVerifier]:
    """Retain an installed system tool only as the final compatibility fallback."""

    for backend in ("ffprobe", "ffmpeg"):
        discovered = shutil.which(backend)
        if not discovered:
            continue
        try:
            executable = Path(discovered).resolve(strict=True)
        except OSError:
            continue
        if executable.is_file():
            yield MP4DecodeVerifier(backend, executable)


def verify_mp4_decode_verifier_start(verifier: MP4DecodeVerifier) -> None:
    """Prove the selected executable starts before a billable request."""

    try:
        completed = subprocess.run(
            [str(verifier.executable), "-version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=MP4_DECODE_VERIFIER_START_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("MP4 decode verifier could not start.") from exc
    if completed.returncode != 0:
        raise RuntimeError("MP4 decode verifier could not start.")


def resolve_mp4_decode_verifier() -> MP4DecodeVerifier:
    """Resolve and launch-check a local verifier without downloads or PATH changes."""

    failures = False
    seen: set[tuple[str, str]] = set()
    candidate_groups = (
        _static_ffmpeg_verifier_candidates(),
        _imageio_ffmpeg_verifier_candidates(),
        _system_verifier_candidates(),
    )
    for group in candidate_groups:
        for verifier in group:
            key = (verifier.backend, os.path.normcase(str(verifier.executable)))
            if key in seen:
                continue
            seen.add(key)
            try:
                verify_mp4_decode_verifier_start(verifier)
            except RuntimeError:
                failures = True
                continue
            return verifier
    detail = (
        "The installed MP4 decode verifier could not start"
        if failures
        else "MP4 decode verifier is unavailable"
    )
    raise RuntimeError(f"{detail}; generated result was not published.")


def validate_decodable_mp4_file(
    path: str | Path,
    verifier: MP4DecodeVerifier | None = None,
) -> None:
    """Decode one bounded video sample before a staged MP4 is published."""

    try:
        source = Path(path).resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            "Generated result could not be staged for MP4 decode verification."
        ) from exc
    if not source.is_file() or source.stat().st_size <= 0:
        raise RuntimeError(
            "Generated result could not be staged for MP4 decode verification."
        )

    selected = verifier or resolve_mp4_decode_verifier()
    if selected.backend == "ffprobe":
        command = [
            str(selected.executable),
            "-v",
            "error",
            "-threads",
            "1",
            "-select_streams",
            "v:0",
            "-read_intervals",
            f"%+#{MP4_DECODE_PROBE_PACKET_LIMIT}",
            "-show_frames",
            "-show_entries",
            "frame=media_type,width,height",
            "-of",
            "json",
            "-i",
            str(source),
        ]
    elif selected.backend == "ffmpeg":
        command = [
            str(selected.executable),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-threads",
            "1",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    else:
        raise RuntimeError(
            "MP4 decode verifier returned an invalid response; generated result was not published."
        )

    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=MP4_DECODE_PROBE_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "MP4 decode verification timed out; generated result was not published."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "MP4 decode verifier could not start; generated result was not published."
        ) from exc

    stdout = completed.stdout
    stderr = completed.stderr
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        raise RuntimeError(
            "MP4 decode verifier returned an invalid response; generated result was not published."
        )
    if completed.returncode != 0 or bool(stderr.strip()):
        raise RuntimeError(
            "Generated result failed MP4 decode verification and was not published."
        )
    if selected.backend == "ffmpeg":
        if len(stdout) != 3:
            raise RuntimeError(
                "Generated result contains no decodable video frame and was not published."
            )
        return
    if len(stdout) + len(stderr) > MP4_DECODE_PROBE_MAX_OUTPUT_BYTES:
        raise RuntimeError(
            "MP4 decode verifier returned an invalid response; generated result was not published."
        )
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "MP4 decode verifier returned an invalid response; generated result was not published."
        ) from exc
    frames = payload.get("frames") if isinstance(payload, dict) else None
    if not isinstance(frames, list) or not any(
        isinstance(frame, dict)
        and frame.get("media_type") == "video"
        and isinstance(frame.get("width"), int)
        and not isinstance(frame.get("width"), bool)
        and frame["width"] > 0
        and isinstance(frame.get("height"), int)
        and not isinstance(frame.get("height"), bool)
        and frame["height"] > 0
        for frame in frames
    ):
        raise RuntimeError(
            "Generated result contains no decodable video frame and was not published."
        )


__all__ = [
    "MP4DecodeVerifier",
    "MP4_DECODE_PROBE_MAX_OUTPUT_BYTES",
    "MP4_DECODE_PROBE_PACKET_LIMIT",
    "MP4_DECODE_PROBE_TIMEOUT_SECONDS",
    "MP4_DECODE_VERIFIER_START_TIMEOUT_SECONDS",
    "resolve_mp4_decode_verifier",
    "validate_decodable_mp4_file",
    "verify_mp4_decode_verifier_start",
]
