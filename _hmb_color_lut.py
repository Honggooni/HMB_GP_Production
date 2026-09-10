from __future__ import annotations

"""Bounded SDR display-domain grading and original-source video export.

The grading domain is full-range sRGB, with Rec.709/sRGB primaries. The source
matrix, range and supported SDR transfer are converted before the LUT. HEVC and
ProRes outputs convert back to limited-range BT.709; FFV1 stores full-range
16-bit RGB sRGB. FFV1 is lossless *at the encoder input*, not with respect to the
original compressed source or the preceding color conversion/quantization.
"""

import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from _hmb_video_tools import VideoMediaService, VideoToolError, _find_ffmpeg, _find_ffprobe


ColorLUTError = VideoToolError
STEP_KEYS = ("exposure", "temperature", "contrast", "saturation", "shadows", "highlights")
SETTINGS_PRECISION_VERSION = 2
STEP_SUBDIVISIONS = 4
CUBE_SIZE = 33
CODEC_EXTENSIONS = {"hevc10": ".mp4", "prores": ".mov", "ffv1": ".mkv"}
_UNKNOWN = {"", "unknown", "unspecified", "reserved", "N/A"}
_SDR_TRANSFERS = {"bt709", "smpte170m", "smpte240m", "bt470bg", "bt470m", "iec61966-2-1"}
_SDR_PRIMARIES = {"bt709", "bt470bg", "smpte170m", "smpte240m", "bt470m"}
_SDR_MATRICES = {"bt709", "bt470bg", "smpte170m", "smpte240m", "fcc", "gbr"}


def default_settings() -> dict[str, Any]:
    return {"enabled": False, "precision_version": SETTINGS_PRECISION_VERSION, **dict.fromkeys(STEP_KEYS, 0)}


def normalize_settings(value: Any) -> dict[str, Any]:
    result = default_settings()
    if not isinstance(value, Mapping):
        return result
    result["enabled"] = value.get("enabled") is True
    for key in STEP_KEYS:
        try:
            number = float(value.get(key, 0))
            if math.isfinite(number):
                # Keep the original grading-strength domain so saved looks and
                # endpoints do not shift. New UI steps map to 0.25 strength each.
                # Unversioned presets retain their original integer semantics.
                if value.get("precision_version") == SETTINGS_PRECISION_VERSION:
                    bounded = max(-3, min(3, number))
                    # Match browser Math.round, including negative half steps.
                    strength = math.floor(bounded * STEP_SUBDIVISIONS + 0.5) / STEP_SUBDIVISIONS
                else:
                    strength = int(number)
                result[key] = max(-3, min(3, strength))
        except (TypeError, ValueError, OverflowError):
            pass
    return result


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _cube_component(value: float) -> float:
    # Same half-up quantization as the preview. Python formatting alone uses
    # ties-to-even, which differs from JavaScript on exact half-grid values.
    return math.floor(value * 1_000_000_000 + 0.5) / 1_000_000_000


def _transform(r: float, g: float, b: float, settings: Mapping[str, Any]) -> tuple[float, float, float]:
    if not settings["enabled"]:
        return r, g, b
    exposure = 2.0 ** (0.22 * settings["exposure"])
    r, g, b = r * exposure, g * exposure, b * exposure
    temperature = (7.0 / 255.0) * settings["temperature"]
    r, b = r + temperature, b - temperature
    luma = _clamp(0.2126 * r + 0.7152 * g + 0.0722 * b)
    offset = 0.04 * settings["shadows"] * (1.0 - luma) ** 2 + 0.04 * settings["highlights"] * luma**2
    contrast = 1.0 + 0.13 * settings["contrast"]
    r, g, b = ((channel + offset - 0.5) * contrast + 0.5 for channel in (r, g, b))
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    saturation = 1.0 + 0.16 * settings["saturation"]
    return tuple(_clamp(luma + (channel - luma) * saturation) for channel in (r, g, b))


def transform_rgb(r: float, g: float, b: float, settings: Any) -> tuple[float, float, float]:
    """Evaluate the shared grading math on one finite, normalized RGB sample."""
    channels = tuple(float(channel) for channel in (r, g, b))
    if any(not math.isfinite(channel) or not 0.0 <= channel <= 1.0 for channel in channels):
        raise ColorLUTError("Color LUT samples must be finite RGB values between 0 and 1.")
    return _transform(*channels, normalize_settings(settings))


def _publish_exclusive(staging: Path, destination: Path) -> None:
    """Publish a completed file atomically without a check/replace collision race."""
    try:
        if os.name == "nt":
            # Unlike os.replace, Windows rename refuses an existing destination.
            os.rename(staging, destination)
        else:
            os.link(staging, destination)
            staging.unlink()
    except FileExistsError as exc:
        raise ColorLUTError("Output already exists; choose a new path. No file was overwritten.") from exc


def write_cube(path: str | Path, settings: Any, size: int = CUBE_SIZE) -> dict[str, Any]:
    """Write a deterministic .cube (red fastest), refusing existing destinations."""
    if isinstance(size, bool) or not isinstance(size, int) or not 2 <= size <= 65:
        raise ColorLUTError("LUT grid size must be an integer between 2 and 65.")
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".cube":
        raise ColorLUTError("LUT output must use the .cube extension.")
    if not destination.parent.is_dir():
        raise ColorLUTError("LUT output directory does not exist.")
    if destination.exists():
        raise ColorLUTError("Output already exists; choose a new path.")
    normalized = normalize_settings(settings)
    staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        with staging.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write('# HMB Color LUT: sRGB display-domain RGB; trilinear interpolation\n')
            stream.write('# Settings: ' + json.dumps(normalized, sort_keys=True, separators=(",", ":")) + '\n')
            stream.write(f'TITLE "HMB Color LUT"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n')
            for blue in range(size):
                for green in range(size):
                    for red in range(size):
                        rgb = _transform(red / (size - 1), green / (size - 1), blue / (size - 1), normalized)
                        stream.write(" ".join(f"{_cube_component(channel):.9f}" for channel in rgb) + "\n")
        _publish_exclusive(staging, destination)
        return {"path": str(destination), "size": size, "sample_count": size**3, "settings": normalized,
                "working_space": "sRGB", "interpolation": "trilinear"}
    finally:
        staging.unlink(missing_ok=True)


def resolve_source(reference: Any, *, remote: bool = False) -> Path:
    """Resolve an already-authorized local reference using the shared media rules."""
    if isinstance(reference, os.PathLike):
        reference = os.fspath(reference)
    return VideoMediaService._resolve_input(reference, remote=remote)


def _color_details(source: Path) -> dict[str, Any]:
    ffmpeg = _find_ffmpeg()
    ffprobe = _find_ffprobe(ffmpeg)
    if ffprobe:
        try:
            result = subprocess.run([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(source)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=True)
            payload = json.loads(result.stdout)
            videos = [item for item in payload.get("streams", []) if item.get("codec_type") == "video"]
            video = next((item for item in videos if not item.get("disposition", {}).get("attached_pic")), None)
            if video is None:
                raise ColorLUTError("Color LUT requires a video stream, not only a cover image.")
            return {**video, "audio_streams": [item for item in payload.get("streams", []) if item.get("codec_type") == "audio"],
                    "format_start_time": payload.get("format", {}).get("start_time", "0"),
                    "format_duration": payload.get("format", {}).get("duration", "0"), "probe_backend": "ffprobe"}
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ColorLUTError(f"Could not verify source color metadata: {exc}") from exc
    # Bundled imageio FFmpeg may not ship ffprobe. Its stream header still reports
    # matrix/primaries/transfer and HDR side data; retain those instead of relabeling.
    result = subprocess.run([ffmpeg, "-hide_banner", "-protocol_whitelist", "file,pipe", "-i", str(source)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    log = result.stderr or result.stdout
    line = next((line for line in log.splitlines() if "Video:" in line), "")
    if not line:
        raise ColorLUTError("Could not verify source color metadata.")
    match = re.search(r"\b(?:yuv\w+|gbr\w+|rgb\w+|bgr\w+|gray\w*)\(([^)]*)\)", line)
    details: dict[str, Any] = {"audio_streams": [], "raw_color_log": log[-32000:], "probe_backend": "ffmpeg"}
    dimensions = re.search(r"\b(\d+)x(\d+)\b", line)
    if dimensions:
        details.update(width=int(dimensions.group(1)), height=int(dimensions.group(2)))
    pixel_format = re.search(r"\b(yuv\w+|gbr\w+|rgb\w+|bgr\w+|gray\w*)", line)
    details["pix_fmt"] = pixel_format.group(1) if pixel_format else ""
    codec_match = re.search(r"Video:\s*([^,\s]+)", line)
    details["codec_name"] = codec_match.group(1) if codec_match else ""
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s+fps", line)
    details["avg_frame_rate"] = fps_match.group(1) if fps_match else "0"
    index_match = re.search(r"Stream #0:(\d+)", line)
    details["index"] = int(index_match.group(1)) if index_match else 0
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", log)
    if duration_match:
        details["duration"] = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    rotation_match = re.search(r"rotation of\s+(-?[\d.]+)\s+degrees", log)
    if rotation_match:
        details["side_data_list"] = [{"rotation": float(rotation_match.group(1))}]
    if match:
        fields = [field.strip() for field in match.group(1).split(",")]
        details["color_range"] = fields[0] if fields[0] in {"tv", "pc"} else ""
        color = next((field for field in fields if "/" in field or field in _SDR_MATRICES or field == "bt2020nc"), "")
        if "/" in color:
            parts = color.split("/")
            if len(parts) == 3:
                details.update(zip(("color_space", "color_primaries", "color_transfer"), parts))
        elif color:
            details.update({"color_space": color, "color_primaries": color, "color_transfer": color})
    for audio_line in (entry for entry in log.splitlines() if "Audio:" in entry):
        match_audio = re.search(r"Audio:\s*([^,\s]+)", audio_line)
        details["audio_streams"].append({"codec_name": match_audio.group(1) if match_audio else ""})
    return details


def _basic_probe(source: Path, details: Mapping[str, Any]) -> dict[str, Any]:
    """UTF-8-safe counterpart to the shared probe's public geometry/audio shape."""
    rate = str(details.get("avg_frame_rate") or details.get("r_frame_rate") or "0")
    try:
        if "/" in rate:
            numerator, denominator = rate.split("/", 1)
            frame_rate = float(numerator) / float(denominator)
        else:
            frame_rate = float(rate)
    except (ValueError, ZeroDivisionError):
        frame_rate = 0.0
    audio = (details.get("audio_streams") or [{}])[0]
    return {"path": str(source), "probe_backend": details.get("probe_backend"),
            "width": int(details.get("width") or 0), "height": int(details.get("height") or 0),
            "frame_rate": frame_rate, "duration": float(details.get("duration") or details.get("format_duration") or 0),
            "has_audio": bool(details.get("audio_streams")), "video_codec": str(details.get("codec_name") or ""),
            "pixel_format": str(details.get("pix_fmt") or ""), "video_profile": str(details.get("profile") or ""),
            "video_time_base": str(details.get("time_base") or ""), "audio_codec": str(audio.get("codec_name") or ""),
            "audio_sample_rate": int(audio.get("sample_rate") or 0), "audio_channels": int(audio.get("channels") or 0),
            "audio_channel_layout": str(audio.get("channel_layout") or "")}


def _color_contract(probe: Mapping[str, Any], details: Mapping[str, Any]) -> dict[str, Any]:
    transfer = str(details.get("color_transfer") or "")
    primaries = str(details.get("color_primaries") or "")
    matrix = str(details.get("color_space") or "")
    source_range = str(details.get("color_range") or "")
    evidence = json.dumps(details.get("side_data_list", [])) + str(details.get("raw_color_log", ""))
    if transfer in {"smpte2084", "arib-std-b67"} or any(marker in evidence.lower() for marker in (
        "mastering display", "content light level", "dovi", "dolby vision", "smpte2084", "arib-std-b67",
    )):
        raise ColorLUTError("HDR_UNSUPPORTED: PQ, HLG and Dolby Vision require an explicit HDR workflow; Color LUT v1 accepts SDR only.")
    pixel_format = str(probe.get("pixel_format") or "")
    is_rgb = pixel_format.startswith(("rgb", "bgr", "gbr"))
    assumptions = []
    if transfer in _UNKNOWN:
        transfer = "iec61966-2-1" if is_rgb else "bt709"
        assumptions.append(f"Untagged transfer interpreted as {transfer}.")
    if primaries in _UNKNOWN:
        primaries = "bt709"
        assumptions.append("Untagged primaries interpreted as BT.709/sRGB.")
    if matrix in _UNKNOWN:
        matrix = "gbr" if is_rgb else "bt709"
        assumptions.append(f"Untagged matrix interpreted as {matrix}.")
    if source_range in _UNKNOWN:
        source_range = "pc" if is_rgb or pixel_format.startswith("yuvj") else "tv"
        assumptions.append(f"Untagged range interpreted as {'full' if source_range == 'pc' else 'limited'}.")
    if transfer not in _SDR_TRANSFERS or primaries not in _SDR_PRIMARIES or matrix not in _SDR_MATRICES:
        raise ColorLUTError(f"COLORSPACE_UNSUPPORTED: Color LUT v1 supports SDR Rec.709/sRGB and common BT.601 sources; got {matrix}/{primaries}/{transfer}.")
    if source_range not in {"tv", "pc"}:
        raise ColorLUTError("COLOR_RANGE_UNSUPPORTED: source range must be limited or full.")
    if any(marker in pixel_format for marker in ("yuva", "gbrap", "rgba", "bgra", "argb", "abgr")):
        raise ColorLUTError("ALPHA_UNSUPPORTED: Color LUT v1 video exports do not preserve an alpha channel.")
    return {"color_space": matrix, "color_primaries": primaries, "color_transfer": transfer,
            "color_range": source_range, "working_space": "sRGB", "color_assumptions": assumptions}


def probe_source(reference: Any, *, remote: bool = False) -> dict[str, Any]:
    source = resolve_source(reference, remote=remote)
    details = _color_details(source)
    basic = _basic_probe(source, details)
    contract = _color_contract(basic, details)
    rotation = next((item.get("rotation", 0) for item in details.get("side_data_list", []) if "rotation" in item), 0)
    try:
        rotation = float(rotation or details.get("tags", {}).get("rotate") or 0)
    except (TypeError, ValueError):
        rotation = 0
    if rotation % 360:
        raise ColorLUTError("ROTATED_VIDEO_UNSUPPORTED: normalize the source display rotation before Color LUT export.")
    return {**basic, **contract, "audio_streams": details.get("audio_streams", []),
            "video_stream_index": int(details.get("index", 0)), "start_time": details.get("start_time", "0"),
            "format_start_time": details.get("format_start_time", "0"),
            "sample_aspect_ratio": str(details.get("sample_aspect_ratio") or ""),
            "frame_count": int(details.get("nb_frames") or 0) if str(details.get("nb_frames") or "0").isdigit() else 0}


def build_color_filter(source_probe: Mapping[str, Any], codec: str, *, cube_name: str = "grade.cube") -> str:
    """Shared color conversion/LUT graph; cube_name is a controlled relative file."""
    if cube_name != "grade.cube":
        raise ColorLUTError("The internal LUT filename must be grade.cube.")
    if codec not in CODEC_EXTENSIONS:
        raise ColorLUTError("Unknown Color LUT export codec.")
    matrix = source_probe["color_space"]
    primaries = source_probe["color_primaries"]
    transfer = source_probe["color_transfer"]
    source_range = source_probe["color_range"]
    filters = [f"zscale=matrixin={matrix}:primariesin={primaries}:transferin={transfer}:rangein={source_range}:"
               "matrix=gbr:primaries=bt709:transfer=iec61966-2-1:range=full:agamma=0",
               "format=gbrpf32le", "lut3d=file=grade.cube:interp=trilinear"]
    if codec == "ffv1":
        filters += ["zscale=matrixin=gbr:primariesin=bt709:transferin=iec61966-2-1:rangein=full:"
                    "matrix=gbr:primaries=bt709:transfer=iec61966-2-1:range=full:dither=none", "format=gbrp16le"]
    else:
        filters += ["zscale=matrixin=gbr:primariesin=bt709:transferin=iec61966-2-1:rangein=full:"
                    "matrix=bt709:primaries=bt709:transfer=bt709:range=limited:agamma=0:dither=error_diffusion",
                    "format=yuv420p10le" if codec == "hevc10" else "format=yuv422p10le"]
    return ",".join(filters)


def _audio_options(probe: Mapping[str, Any], codec: str) -> tuple[list[str], str]:
    audio = probe.get("audio_streams") or []
    if not audio and not probe.get("has_audio"):
        return ["-an"], "none"
    options = ["-map", "0:a?"]
    names = {str(item.get("codec_name") or "") for item in audio}
    if codec == "ffv1":
        return [*options, "-c:a", "copy"], "copy"
    accepted = {"aac", "mp3", "ac3", "eac3", "alac"}
    if codec == "prores":
        accepted |= {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_s16be", "pcm_s24be", "pcm_s32be"}
    if names and names <= accepted:
        return [*options, "-c:a", "copy"], "copy"
    if codec == "prores":
        return [*options, "-c:a", "pcm_s24le"], "pcm_s24le"
    return [*options, "-c:a", "aac", "-b:a", "320k"], "aac_320k"


def _notify(progress: Callable[[float], None] | None, value: float) -> None:
    if progress is not None:
        try:
            progress(max(0.0, min(1.0, value)))
        except Exception:
            pass  # UI observers must not corrupt a completed media operation.


def _run_export(command: list[str], cwd: Path, cancel_event: threading.Event | None,
                progress: Callable[[float], None] | None, duration: float, start_time: float) -> str:
    if cancel_event is not None and cancel_event.is_set():
        raise ColorLUTError("Color LUT export was cancelled.")
    with (cwd / "ffmpeg.log").open("w+", encoding="utf-8") as error_log:
        process = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=error_log, text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        latest = [0.0]

        def consume() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    try:
                        latest[0] = min(0.97, max(0.0, (float(line.split("=", 1)[1]) / 1_000_000 - start_time) / max(duration, 0.001)))
                    except ValueError:
                        pass

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        deadline = time.monotonic() + max(600.0, duration * 120.0)
        last = -1.0
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise ColorLUTError("Color LUT export was cancelled.")
                if time.monotonic() >= deadline:
                    raise ColorLUTError("Color LUT export exceeded its processing timeout.")
                if latest[0] != last:
                    last = latest[0]
                    _notify(progress, last)
                time.sleep(0.1)
            reader.join(timeout=3)
            if process.returncode:
                error_log.flush()
                error_log.seek(0, os.SEEK_END)
                error_log.seek(max(0, error_log.tell() - 32000))
                raise ColorLUTError(f"Color LUT FFmpeg export failed: {error_log.read().strip()}")
            return ""
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            reader.join(timeout=3)
            if process.stdout is not None:
                process.stdout.close()


def export_video(source_path: Any, output_path: str | Path, settings: Any, codec: str = "hevc10",
                 cancel_event: threading.Event | None = None, progress: Callable[[float], None] | None = None) -> dict[str, Any]:
    """Grade the original video in one encode, verify, then publish without overwrite."""
    if codec not in CODEC_EXTENSIONS:
        raise ColorLUTError("Export codec must be hevc10, prores or ffv1.")
    if cancel_event is not None and cancel_event.is_set():
        raise ColorLUTError("Color LUT export was cancelled.")
    source = resolve_source(source_path)
    output = Path(output_path).expanduser().resolve()
    if output == source or output.exists():
        raise ColorLUTError("Output already exists or matches the source; choose a new path.")
    if output.suffix.lower() != CODEC_EXTENSIONS[codec]:
        raise ColorLUTError(f"{codec} export requires {CODEC_EXTENSIONS[codec]}.")
    if not output.parent.is_dir():
        raise ColorLUTError("Output directory does not exist.")
    source_probe = probe_source(source)
    width, height = int(source_probe["width"]), int(source_probe["height"])
    if (codec == "hevc10" and (width % 2 or height % 2)) or (codec == "prores" and width % 2):
        raise ColorLUTError("The selected 4:2:0/4:2:2 codec cannot preserve these odd source dimensions; use FFV1.")
    normalized = normalize_settings(settings)
    staging = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.part{output.suffix}")
    source_stat = source.stat()
    _notify(progress, 0.0)
    try:
        with tempfile.TemporaryDirectory(prefix="hmb_color_lut_") as temp_dir:
            work = Path(temp_dir)
            write_cube(work / "grade.cube", normalized)
            audio, audio_mode = _audio_options(source_probe, codec)
            command = [_find_ffmpeg(), "-hide_banner", "-v", "error", "-xerror", "-nostdin", "-nostats", "-n", "-copyts",
                       "-protocol_whitelist", "file,pipe", "-noautorotate", "-i", str(source), "-map", f"0:{source_probe['video_stream_index']}",
                       *audio, "-map_metadata", "0", "-map_chapters", "0", "-vf", build_color_filter(source_probe, codec),
                       "-fps_mode", "passthrough", "-enc_time_base", "filter", "-avoid_negative_ts", "disabled"]
            if codec == "hevc10":
                command += ["-c:v", "libx265", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1",
                            "-x265-params", "log-level=error"]
            elif codec == "prores":
                command += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
            else:
                command += ["-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-slicecrc", "1", "-pix_fmt", "gbrp16le"]
            command += ["-color_primaries", "bt709", "-color_trc", "iec61966-2-1" if codec == "ffv1" else "bt709",
                        "-colorspace", "rgb" if codec == "ffv1" else "bt709", "-color_range", "pc" if codec == "ffv1" else "tv"]
            if codec != "ffv1":
                command += ["-movflags", "+faststart"]
            command += ["-progress", "pipe:1", str(staging)]
            _run_export(command, work, cancel_event, progress, float(source_probe.get("duration") or 0),
                        float(source_probe.get("format_start_time") or 0))
        if cancel_event is not None and cancel_event.is_set():
            raise ColorLUTError("Color LUT export was cancelled.")
        if not staging.is_file() or staging.stat().st_size <= 0:
            raise ColorLUTError("Color LUT export produced no video.")
        result_details = _color_details(staging)
        result_probe = _basic_probe(staging, result_details)
        if (result_probe["width"], result_probe["height"]) != (width, height):
            raise ColorLUTError("Color LUT output resolution changed unexpectedly.")
        if result_probe["has_audio"] != source_probe["has_audio"]:
            raise ColorLUTError("Color LUT output did not preserve the source audio presence.")
        if len(result_details.get("audio_streams", [])) != len(source_probe.get("audio_streams", [])):
            raise ColorLUTError("Color LUT output did not preserve all source audio streams.")
        result_count = str(result_details.get("nb_frames") or "")
        if source_probe["frame_count"] and result_count.isdigit() and int(result_count) != source_probe["frame_count"]:
            raise ColorLUTError("Color LUT output frame count changed unexpectedly.")
        expected_codec = {"hevc10": "hevc", "prores": "prores", "ffv1": "ffv1"}[codec]
        if result_probe.get("video_codec") != expected_codec:
            raise ColorLUTError("Color LUT output codec does not match the selected export mode.")
        current_stat = source.stat()
        if (current_stat.st_size, current_stat.st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
            raise ColorLUTError("The source changed during export; the result was not published.")
        if cancel_event is not None and cancel_event.is_set():
            raise ColorLUTError("Color LUT export was cancelled.")
        _publish_exclusive(staging, output)
        _notify(progress, 1.0)
        return {**result_probe, "path": str(output), "source_path": str(source), "operation": "color_lut", "codec": codec,
                "settings": normalized, "cube_size": CUBE_SIZE, "interpolation": "trilinear", "audio_mode": audio_mode,
                "encoding_lossless": codec == "ffv1", "working_space": "sRGB", "color_assumptions": source_probe["color_assumptions"],
                "quality_note": "Lossless encoding of graded 16-bit RGB pixels; source decoding and color conversion are not reversible."
                if codec == "ffv1" else "High-quality 10-bit export with lossy video compression.",
                "timestamp_policy": "Original timestamps passed through; container time-base precision may differ."}
    finally:
        staging.unlink(missing_ok=True)
