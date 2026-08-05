from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBVideoPickerLibrary as picker  # noqa: E402


def _static_tool(name: str) -> Path | None:
    try:
        import static_ffmpeg  # type: ignore

        root = Path(static_ffmpeg.__file__).resolve().parent
        for platform in ("win32", "win64", "linux", "darwin"):
            for executable in (f"{name}.exe", name):
                candidate = root / "bin" / platform / executable
                if candidate.is_file():
                    return candidate
    except Exception:
        return None
    return None


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )


def _metric(stderr: str, pattern: str, label: str) -> float:
    matches = re.findall(pattern, stderr)
    if not matches:
        raise AssertionError(f"{label} summary was not found in FFmpeg output.")
    return float(matches[-1])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Encode decoded frames from a reference MP4 with the Picker proxy "
            "profile and verify exact CFR timing, BT.709 metadata, and visual quality."
        )
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("--frames", type=int, default=198)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    args = parser.parse_args()

    reference = args.reference.resolve()
    if not reference.is_file():
        raise FileNotFoundError(reference)
    frame_limit = max(2, int(args.frames))
    ffmpeg = (args.ffmpeg or _static_tool("ffmpeg") or picker._find_ffmpeg()).resolve()
    ffprobe = (args.ffprobe or _static_tool("ffprobe")).resolve()
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise FileNotFoundError("Both FFmpeg and FFprobe are required for proxy validation.")

    reference_probe = json.loads(
        _run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_frames",
                "-of",
                "json",
                str(reference),
            ],
            capture=True,
        ).stdout
    )
    reference_stream = reference_probe["streams"][0]
    width = int(reference_stream["width"])
    height = int(reference_stream["height"])
    rate = picker.Fraction(reference_stream["avg_frame_rate"])
    fps = float(rate)
    available_frames = int(reference_stream.get("nb_frames") or 0)
    frame_count = min(frame_limit, available_frames) if available_frames > 0 else frame_limit

    with tempfile.TemporaryDirectory(prefix="HMB_Proxy_Encoding_") as temp_dir:
        temp_root = Path(temp_dir)
        frame_pattern = temp_root / "reference.%06d.png"
        output_path = temp_root / "hmb-proxy.mp4"
        _run(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(reference),
                "-start_number",
                "0",
                "-frames:v",
                str(frame_count),
                str(frame_pattern),
            ],
            capture=True,
        )
        encode_command = picker._build_ffmpeg_encode_command(
            ffmpeg=ffmpeg,
            frame_pattern=frame_pattern,
            output_path=output_path,
            source_fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
        )
        _run(encode_command, capture=True)

        output_probe = json.loads(
            _run(
                [
                    str(ffprobe),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    (
                        "stream=codec_name,profile,level,pix_fmt,color_range,color_space,"
                        "color_transfer,color_primaries,avg_frame_rate,nb_frames,duration"
                    ),
                    "-show_entries",
                    "format=duration,size,bit_rate",
                    "-of",
                    "json",
                    str(output_path),
                ],
                capture=True,
            ).stdout
        )
        stream = output_probe["streams"][0]
        assert stream["codec_name"] == "h264"
        assert stream["profile"] == "High"
        assert int(stream["level"]) == 42
        assert stream["pix_fmt"] == "yuv420p"
        assert stream["color_range"] == "tv"
        assert stream["color_space"] == "bt709"
        assert stream["color_transfer"] == "bt709"
        assert stream["color_primaries"] == "bt709"
        assert picker.Fraction(stream["avg_frame_rate"]) == rate
        assert int(stream["nb_frames"]) == frame_count
        expected_duration = frame_count / fps
        assert abs(float(stream["duration"]) - expected_duration) <= 1e-6
        assert abs(float(output_probe["format"]["duration"]) - expected_duration) <= 1e-6

        pts_output = _run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "csv=p=0",
                str(output_path),
            ],
            capture=True,
        ).stdout
        pts = [
            float(line.strip().strip(","))
            for line in pts_output.splitlines()
            if line.strip().strip(",")
        ]
        assert len(pts) == frame_count
        assert abs(pts[0]) <= 1e-9
        expected_delta = 1.0 / fps
        assert all(abs((right - left) - expected_delta) <= 1e-6 for left, right in zip(pts, pts[1:]))

        source_input = [
            "-framerate",
            picker._fps_timebase(fps),
            "-start_number",
            "0",
            "-i",
            str(frame_pattern),
            "-i",
            str(output_path),
            "-frames:v",
            str(frame_count),
        ]
        psnr_result = _run(
            [
                str(ffmpeg),
                "-v",
                "info",
                *source_input,
                "-lavfi",
                "psnr",
                "-f",
                "null",
                "NUL" if sys.platform.startswith("win") else "/dev/null",
            ],
            capture=True,
        )
        ssim_result = _run(
            [
                str(ffmpeg),
                "-v",
                "info",
                *source_input,
                "-lavfi",
                "ssim",
                "-f",
                "null",
                "NUL" if sys.platform.startswith("win") else "/dev/null",
            ],
            capture=True,
        )
        psnr = _metric(psnr_result.stderr, r"average:([0-9.]+)", "PSNR")
        ssim = _metric(ssim_result.stderr, r"All:([0-9.]+)", "SSIM")
        assert psnr >= 50.0, psnr
        assert ssim >= 0.999, ssim

        report = {
            "reference": str(reference),
            "frames": frame_count,
            "fps": picker._fps_timebase(fps),
            "resolution": f"{width}x{height}",
            "duration_seconds": expected_duration,
            "profile": stream["profile"],
            "level": stream["level"],
            "pixel_format": stream["pix_fmt"],
            "color": "BT.709 limited",
            "size_bytes": int(output_probe["format"]["size"]),
            "bit_rate": int(output_probe["format"]["bit_rate"]),
            "psnr_db": psnr,
            "ssim": ssim,
            "result": "PASS",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
