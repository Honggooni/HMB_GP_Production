from __future__ import annotations

"""Shared local media engine; independent of node/UI and Prompt routing."""

import copy
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

MAX_PROCESS_LOG_CHARS = 32_000
VIDEO_PROCESS_TIMEOUT_SECONDS = 600.0

class VideoToolError(ValueError):
    """A requested media operation could not be completed safely."""


def default_picker_tools_state() -> dict[str, Any]:
    return {
        "schema_version": 1, "revision": 0, "active_tool": "preview", "panel_height": 330,
        "concatenate": {"inputs": [], "input_uids": [], "output_path": "", "manual_output_enabled": False, "output_format": "mp4",
                        "video_codec": "libx264", "audio_codec": "aac",
                        "output_frame_rate": "auto", "processing_speed": "balanced"},
        "crop": {"input": "", "source_uid": "", "output_path": "", "manual_output_enabled": False, "crop_size": "Custom",
                 "crop_position": "center", "custom_width": 0, "custom_height": 0,
                 "custom_left": 0, "custom_top": 0, "processing_speed": "balanced", "zoom": 1.0},
        "crop_by_source": {},
        "external_sources": [],
    }


def normalize_picker_tools_state(value: Any) -> dict[str, Any]:
    """Keep authored edit drafts independent of the Picker's selection order."""
    result = default_picker_tools_state()
    source = value if isinstance(value, Mapping) else {}
    try:
        result["revision"] = max(0, int(source.get("revision") or 0))
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        result["panel_height"] = max(160, min(900, int(source.get("panel_height", 330))))
    except (TypeError, ValueError, OverflowError):
        pass
    if source.get("active_tool") in ("preview", "concatenate", "crop"):
        result["active_tool"] = source["active_tool"]
    for operation in ("concatenate", "crop"):
        raw = source.get(operation) if isinstance(source.get(operation), Mapping) else {}
        settings = result[operation]
        for key, default in settings.items():
            if key in ("inputs", "input_uids"):
                settings[key] = [str(item).strip() for item in raw.get(key, []) if isinstance(item, str)][:50] if isinstance(raw.get(key), list) else []
            elif key == "manual_output_enabled":
                settings[key] = raw.get(key) is True
            elif key.startswith("custom_"):
                try:
                    settings[key] = max(0, min(100000, int(raw.get(key) or 0)))
                except (TypeError, ValueError, OverflowError):
                    pass
            elif key == "zoom":
                try:
                    number = float(raw.get(key, 1.0))
                    settings[key] = max(1.0, min(3.0, number)) if math.isfinite(number) else 1.0
                except (TypeError, ValueError, OverflowError):
                    pass
            elif isinstance(raw.get(key), str):
                settings[key] = raw[key].strip()
        choices = {"output_format": OUTPUT_FORMAT_CHOICES, "video_codec": VIDEO_CODEC_CHOICES,
                   "audio_codec": AUDIO_CODEC_CHOICES, "output_frame_rate": FRAME_RATE_CHOICES,
                   "processing_speed": PROCESSING_SPEED_CHOICES, "crop_size": CROP_SIZE_CHOICES,
                   "crop_position": CROP_POSITION_CHOICES}
        for key, allowed in choices.items():
            if key in settings and settings[key] not in allowed:
                settings[key] = default_picker_tools_state()[operation][key]
        if operation == "concatenate":
            raw_paths = raw.get("inputs") if isinstance(raw.get("inputs"), list) else []
            raw_uids = raw.get("input_uids") if isinstance(raw.get("input_uids"), list) else []
            pairs = [(path.strip(), raw_uids[index].strip() if index < len(raw_uids) and isinstance(raw_uids[index], str) else "")
                     for index, path in enumerate(raw_paths) if isinstance(path, str) and path.strip()][:50]
            settings["inputs"] = [path for path, _uid in pairs]
            settings["input_uids"] = [uid for _path, uid in pairs]
    histories = source.get("crop_by_source")
    if isinstance(histories, Mapping):
        for uid, settings in list(histories.items())[-50:]:
            if isinstance(uid, str) and uid.strip() and isinstance(settings, Mapping):
                result["crop_by_source"][uid] = normalize_picker_tools_state({"crop": settings})["crop"]
    external_sources = source.get("external_sources")
    if isinstance(external_sources, list):
        seen = set()
        for raw in external_sources[:100]:
            if not isinstance(raw, Mapping):
                continue
            uid, path = str(raw.get("source_uid") or "").strip(), str(raw.get("local_path") or "").strip()
            if not uid or not path or uid in seen:
                continue
            seen.add(uid)
            item = {key: str(raw.get(key) or "").strip() for key in ("source_uid", "local_path", "label", "browser_url", "thumbnail_url")}
            for key in ("width", "height", "duration", "frame_rate", "frame_count"):
                try:
                    number = float(raw.get(key) or 0)
                    item[key] = max(0.0, number) if math.isfinite(number) else 0.0
                except (TypeError, ValueError, OverflowError):
                    item[key] = 0.0
            result["external_sources"].append(item)
    return result


def default_picker_tools_status(workspace_uuid: str = "") -> dict[str, Any]:
    return {"schema_version": 1, "picker_shot_uuid": workspace_uuid, "job_id": "",
            "operation": "", "status": "idle", "progress": 0.0, "output": None, "error": None}

CROP_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
    "Square": (1080, 1080),
    "Portrait": (1080, 1920),
    "4:3": (1440, 1080),
}
CROP_SIZE_CHOICES: tuple[str, ...] = (*CROP_RESOLUTIONS.keys(), "Custom")
CROP_POSITION_CHOICES: tuple[str, ...] = (
    "center",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "top-center",
    "bottom-center",
    "left-center",
    "right-center",
    "Custom",
)
OUTPUT_FORMAT_CHOICES = ("mp4", "avi", "mov", "mkv", "webm")
VIDEO_CODEC_CHOICES = ("libx264", "libx265", "libvpx-vp9", "copy")
AUDIO_CODEC_CHOICES = ("aac", "mp3", "libmp3lame", "libopus", "copy")
FRAME_RATE_CHOICES = ("auto", "24", "25", "29.97", "30", "50", "59.94", "60")
PROCESSING_SPEED_CHOICES = ("fast", "balanced", "quality")


def format_number(value: float) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _media_reference(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("path", "value", "video_path", "video_url"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    raw = getattr(value, "value", None)
    return raw.strip() if isinstance(raw, str) else ""


def _find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg  # type: ignore

        executable = imageio_ffmpeg.get_ffmpeg_exe()
        if executable and Path(executable).is_file():
            return str(Path(executable).resolve())
    except Exception:
        pass
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    raise VideoToolError("FFmpeg is not available.")


def _find_ffprobe(ffmpeg: str | None = None) -> str:
    executable = shutil.which("ffprobe")
    if executable:
        return executable
    if ffmpeg:
        path = Path(ffmpeg)
        candidates = (path.with_name("ffprobe.exe"), path.with_name("ffprobe"))
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return ""


def _bounded_process_text(value: str) -> str:
    return value[-MAX_PROCESS_LOG_CHARS:] if len(value) > MAX_PROCESS_LOG_CHARS else value


def _ffmpeg_audio_channel_count(layout: str) -> int:
    normalized = layout.strip().lower()
    named = {
        "mono": 1,
        "stereo": 2,
        "quad": 4,
        "quad(side)": 4,
        "hexagonal": 6,
        "octagonal": 8,
    }
    if normalized in named:
        return named[normalized]
    explicit = re.match(r"(\d+)\s+channels?\b", normalized)
    if explicit:
        return int(explicit.group(1))
    surround = re.match(r"(\d+)\.(\d+)", normalized)
    if surround:
        return int(surround.group(1)) + int(surround.group(2))
    return 0


def probe_video(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    ffmpeg = _find_ffmpeg()
    ffprobe = _find_ffprobe(ffmpeg)
    if ffprobe:
        completed = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        payload = json.loads(completed.stdout)
        streams = payload.get("streams") if isinstance(payload, dict) else []
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        if not isinstance(video, dict):
            raise VideoToolError(f"No video stream found in {source.name}.")
        rate_text = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
        try:
            numerator, denominator = rate_text.split("/", 1)
            frame_rate = float(numerator) / float(denominator)
        except Exception:
            frame_rate = 0.0
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        duration_raw = video.get("duration") or payload.get("format", {}).get("duration") or 0
        return {
            "probe_backend": "ffprobe",
            "path": str(source),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "frame_rate": frame_rate,
            "duration": float(duration_raw or 0),
            "has_audio": isinstance(audio, dict),
            "video_codec": str(video.get("codec_name") or ""),
            "pixel_format": str(video.get("pix_fmt") or ""),
            "video_profile": str(video.get("profile") or ""),
            "video_time_base": str(video.get("time_base") or ""),
            "audio_codec": str(audio.get("codec_name") or "") if isinstance(audio, dict) else "",
            "audio_sample_rate": int(audio.get("sample_rate") or 0) if isinstance(audio, dict) else 0,
            "audio_channels": int(audio.get("channels") or 0) if isinstance(audio, dict) else 0,
            "audio_channel_layout": str(audio.get("channel_layout") or "") if isinstance(audio, dict) else "",
        }
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(source)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    details = completed.stderr or completed.stdout
    size = re.search(r"Video:.*?\b(\d{2,6})x(\d{2,6})\b", details)
    if size is None:
        raise VideoToolError(f"Could not probe {source.name}.")
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    duration = 0.0
    if duration_match:
        duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    fps_match = re.search(r"(\d+(?:\.\d+)?)\s+fps", details)
    nominal_rate_match = re.search(r"(\d+(?:\.\d+)?)\s+tbr", details)
    video_codec_match = re.search(r"Video:\s*([^,\s]+)", details)
    pixel_format_match = re.search(r"Video:.*?,\s*([^,\s]+)(?:\([^)]*\))?,\s*\d{2,6}x\d{2,6}", details)
    audio_codec_match = re.search(r"Audio:\s*([^,\s]+)", details)
    audio_rate_match = re.search(r"Audio:.*?,\s*(\d+)\s+Hz", details)
    audio_layout_match = re.search(r"Audio:.*?,\s*\d+\s+Hz,\s*([^,\r\n]+)", details)
    audio_layout = audio_layout_match.group(1).strip() if audio_layout_match else ""
    pixel_format = pixel_format_match.group(1) if pixel_format_match else ""
    pixel_format = pixel_format.split("(", 1)[0]
    return {
        "probe_backend": "ffmpeg",
        "path": str(source),
        "width": int(size.group(1)),
        "height": int(size.group(2)),
        "frame_rate": (
            float(nominal_rate_match.group(1))
            if nominal_rate_match
            else float(fps_match.group(1)) if fps_match else 0.0
        ),
        "duration": duration,
        "has_audio": "Audio:" in details,
        "video_codec": video_codec_match.group(1) if video_codec_match else "",
        "pixel_format": pixel_format,
        "video_profile": "",
        "video_time_base": "",
        "audio_codec": audio_codec_match.group(1) if audio_codec_match else "",
        "audio_sample_rate": int(audio_rate_match.group(1)) if audio_rate_match else 0,
        "audio_channels": _ffmpeg_audio_channel_count(audio_layout),
        "audio_channel_layout": audio_layout,
    }


def calculate_crop_rectangle(
    video_width: int,
    video_height: int,
    settings: Mapping[str, Any],
) -> tuple[int, int, int, int]:
    if video_width < 2 or video_height < 2:
        raise VideoToolError("Video dimensions must be at least 2x2.")
    crop_size = str(settings.get("crop_size") or "Custom")
    if crop_size == "Custom":
        requested_width = int(settings.get("custom_width") or video_width)
        requested_height = int(settings.get("custom_height") or video_height)
    elif crop_size in CROP_RESOLUTIONS:
        requested_width, requested_height = CROP_RESOLUTIONS[crop_size]
    else:
        raise VideoToolError(f"Unsupported crop size: {crop_size}.")
    width = min(max(2, requested_width), video_width)
    height = min(max(2, requested_height), video_height)
    width = max(2, (width // 2) * 2)
    height = max(2, (height // 2) * 2)
    position = str(settings.get("crop_position") or "center")
    positions = {
        "center": ((video_width - width) // 2, (video_height - height) // 2),
        "top-left": (0, 0),
        "top-right": (video_width - width, 0),
        "bottom-left": (0, video_height - height),
        "bottom-right": (video_width - width, video_height - height),
        "top-center": ((video_width - width) // 2, 0),
        "bottom-center": ((video_width - width) // 2, video_height - height),
        "left-center": (0, (video_height - height) // 2),
        "right-center": (video_width - width, (video_height - height) // 2),
    }
    if position == "Custom":
        left = int(settings.get("custom_left") or 0)
        top = int(settings.get("custom_top") or 0)
    elif position in positions:
        left, top = positions[position]
    else:
        raise VideoToolError(f"Unsupported crop position: {position}.")
    left = max(0, min(left, video_width - width))
    top = max(0, min(top, video_height - height))
    return width, height, left, top


def _speed_options(speed: str) -> tuple[str, str]:
    return {
        "fast": ("veryfast", "20"),
        "balanced": ("medium", "18"),
        "quality": ("slow", "16"),
    }[speed]


def _video_encoder_options(settings: Mapping[str, Any]) -> list[str]:
    codec = str(settings["video_codec"])
    if codec == "copy":
        return []
    preset, crf = _speed_options(str(settings["processing_speed"]))
    if codec == "libvpx-vp9":
        cpu_used = {"fast": "6", "balanced": "4", "quality": "2"}[
            str(settings["processing_speed"])
        ]
        return [
            "-deadline",
            "good",
            "-cpu-used",
            cpu_used,
            "-crf",
            crf,
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
        ]
    return ["-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]


def _audio_encoder_name(codec: Any) -> str:
    value = str(codec)
    return "libmp3lame" if value == "mp3" else value


def _concat_frame_rate(settings: Mapping[str, Any], probes: Sequence[Mapping[str, Any]]) -> str:
    requested = str(settings["output_frame_rate"])
    if requested != "auto":
        return requested
    measured = float(probes[0].get("frame_rate") or 0.0) if probes else 0.0
    if measured <= 0.0 or not math.isfinite(measured):
        measured = 24.0
    return f"{measured:.6f}".rstrip("0").rstrip(".")


def _concat_copy_signature(probe: Mapping[str, Any]) -> tuple[Any, ...]:
    signature: tuple[Any, ...] = (
        str(probe.get("video_codec") or ""),
        int(probe.get("width") or 0),
        int(probe.get("height") or 0),
        str(probe.get("pixel_format") or ""),
        str(probe.get("video_profile") or ""),
        str(probe.get("video_time_base") or ""),
        round(float(probe.get("frame_rate") or 0.0), 6),
        bool(probe.get("has_audio")),
    )
    if probe.get("has_audio"):
        signature += (
            str(probe.get("audio_codec") or ""),
            int(probe.get("audio_sample_rate") or 0),
            int(probe.get("audio_channels") or 0),
            str(probe.get("audio_channel_layout") or ""),
        )
    return signature


def _validate_concat_codecs(
    settings: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
) -> bool:
    """Validate the selected mux/codec combination; return whether stream copy is needed."""
    output_format = str(settings["output_format"])
    video_codec = str(settings["video_codec"])
    audio_codec = str(settings["audio_codec"])
    has_audio = any(bool(probe.get("has_audio")) for probe in probes)
    copy_requested = video_codec == "copy" or (has_audio and audio_codec == "copy")

    if output_format == "webm":
        if video_codec == "copy":
            if any(str(probe.get("video_codec") or "") not in {"vp8", "vp9", "av1"} for probe in probes):
                raise VideoToolError("WebM stream copy requires VP8, VP9, or AV1 video inputs.")
        elif video_codec != "libvpx-vp9":
            raise VideoToolError("WebM output requires the libvpx-vp9 video codec.")
        if has_audio:
            if audio_codec == "copy":
                if any(str(probe.get("audio_codec") or "") not in {"opus", "vorbis"} for probe in probes):
                    raise VideoToolError("WebM audio stream copy requires Opus or Vorbis inputs.")
            elif audio_codec != "libopus":
                raise VideoToolError("WebM output with audio requires the libopus audio codec.")
    elif audio_codec == "libopus" and output_format != "mkv":
        raise VideoToolError("libopus audio is supported only for WebM or MKV output.")

    if not copy_requested:
        return False
    if video_codec == "copy" and str(settings["output_frame_rate"]) != "auto":
        raise VideoToolError("Video stream copy requires Output Frame Rate to remain auto.")
    if not probes or any(
        probe.get("probe_backend") != "ffprobe"
        or not str(probe.get("video_codec") or "")
        or not str(probe.get("pixel_format") or "")
        or not str(probe.get("video_time_base") or "")
        or float(probe.get("frame_rate") or 0.0) <= 0.0
        for probe in probes
    ):
        raise VideoToolError("Stream copy requires complete FFprobe stream metadata.")
    first_signature = _concat_copy_signature(probes[0])
    if any(_concat_copy_signature(probe) != first_signature for probe in probes[1:]):
        raise VideoToolError(
            "Stream copy requires matching video codec, resolution, frame rate, time base, pixel format, and audio layout."
        )
    return True


def build_crop_ffmpeg_command(
    ffmpeg: str,
    input_path: str,
    output_path: str,
    rectangle: tuple[int, int, int, int],
    *,
    has_audio: bool,
    processing_speed: str = "balanced",
) -> list[str]:
    width, height, left, top = rectangle
    preset, crf = _speed_options(processing_speed)
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        input_path,
        "-map",
        "0:v:0",
    ]
    if has_audio:
        command.extend(["-map", "0:a?", "-c:a", "copy"])
    else:
        command.append("-an")
    command.extend(
        [
            "-vf",
            f"crop={width}:{height}:{left}:{top}",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-pix_fmt",
            "yuv420p",
            "-crf",
            crf,
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    return command


def build_concat_ffmpeg_command(
    ffmpeg: str,
    concat_list_path: str,
    output_path: str,
    settings: Mapping[str, Any],
    *,
    has_audio: bool = True,
) -> list[str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_path,
        "-map",
        "0:v:0",
        "-c:v",
        str(settings["video_codec"]),
    ]
    if has_audio:
        command.extend(["-map", "0:a:0?", "-c:a", _audio_encoder_name(settings["audio_codec"])])
    else:
        command.append("-an")
    command.extend(["-map_metadata", "-1", "-map_chapters", "-1"])
    frame_rate = str(settings["output_frame_rate"])
    if frame_rate != "auto":
        command.extend(["-r", frame_rate])
    command.extend(_video_encoder_options(settings))
    if str(settings["output_format"]) in {"mp4", "mov"}:
        command.extend(["-movflags", "+faststart"])
    command.append(output_path)
    return command


def build_filter_concat_ffmpeg_command(
    ffmpeg: str,
    input_paths: Sequence[str],
    output_path: str,
    settings: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
) -> list[str]:
    if len(input_paths) < 2 or len(input_paths) != len(probes):
        raise VideoToolError("Filtered concatenation requires matching input and probe lists.")
    width = int(probes[0].get("width") or 0)
    height = int(probes[0].get("height") or 0)
    if width < 2 or height < 2:
        raise VideoToolError("Concatenate Videos could not determine a valid output resolution.")
    width = max(2, width - (width % 2))
    height = max(2, height - (height % 2))
    frame_rate = _concat_frame_rate(settings, probes)
    has_audio = any(bool(probe.get("has_audio")) for probe in probes)
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, probe in enumerate(probes):
        duration = float(probe.get("duration") or 0.0)
        if duration <= 0.0 or not math.isfinite(duration):
            raise VideoToolError("Every concatenated input must have a measurable positive duration.")
        duration_text = f"{duration:.6f}".rstrip("0").rstrip(".")
        filters.append(
            f"[{index}:v:0]trim=duration={duration_text},setpts=PTS-STARTPTS,fps={frame_rate},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,settb=AVTB[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
        if not has_audio:
            continue
        if probe.get("has_audio"):
            filters.append(
                f"[{index}:a:0]aresample=48000:async=1:first_pts=0,"
                f"aformat=sample_rates=48000:channel_layouts=stereo,atrim=duration={duration_text},"
                f"apad=whole_dur={duration_text},asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filters.append(
                f"anullsrc=r=48000:cl=stereo:d={duration_text},asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs.append(f"[a{index}]")
    video_map = "[vout]"
    audio_map = "[aout]"
    filters.append(
        "".join(concat_inputs)
        + f"concat=n={len(input_paths)}:v=1:a={1 if has_audio else 0}"
        + video_map
        + (audio_map if has_audio else "")
    )
    command = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    for path in input_paths:
        command.extend(["-i", path])
    command.extend(["-filter_complex", ";".join(filters), "-map", video_map])
    if has_audio:
        command.extend(["-map", audio_map, "-c:a", _audio_encoder_name(settings["audio_codec"])])
    else:
        command.append("-an")
    command.extend(["-map_metadata", "-1", "-map_chapters", "-1"])
    command.extend(["-c:v", str(settings["video_codec"])])
    command.extend(_video_encoder_options(settings))
    if str(settings["output_format"]) in {"mp4", "mov"}:
        command.extend(["-movflags", "+faststart"])
    command.append(output_path)
    return command


def _default_output_path(input_path: Path, suffix: str, extension: str) -> Path:
    base = input_path.with_name(f"{input_path.stem}{suffix}.{extension}")
    if not base.exists():
        return base
    for index in range(1, 10_000):
        candidate = input_path.with_name(f"{input_path.stem}{suffix}_{index}.{extension}")
        if not candidate.exists():
            return candidate
    raise VideoToolError("Could not allocate a non-conflicting output path.")


def _resolved_output_path(raw: str, first_input: Path, suffix: str, extension: str) -> Path:
    if raw.strip():
        output = Path(raw).expanduser().resolve()
        if output.suffix.lower() != f".{extension.lower()}":
            raise VideoToolError(f"Output path must use .{extension}.")
        if not output.parent.is_dir():
            raise VideoToolError("Output directory does not exist.")
    else:
        output = _default_output_path(first_input, suffix, extension)
    if output.exists():
        raise VideoToolError("Output already exists; choose a new path.")
    return output


def _is_within(path: Path, roots: Sequence[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _remote_media_roots() -> tuple[Path, ...]:
    roots = [Path.cwd().resolve()]
    raw = os.environ.get("HMB_FINISH_LOOK_MEDIA_ROOTS", "")
    if raw:
        for item in raw.split(os.pathsep):
            if item.strip():
                candidate = Path(item.strip()).expanduser().resolve()
                if candidate.is_dir():
                    roots.append(candidate)
    return tuple(dict.fromkeys(roots))


class VideoMediaService:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._process_lock = threading.RLock()

    def cancel(self) -> None:
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _run(
        self,
        command: Sequence[str],
        cancel_event: threading.Event | None = None,
        *,
        timeout: float = VIDEO_PROCESS_TIMEOUT_SECONDS,
    ) -> str:
        if cancel_event is not None and cancel_event.is_set():
            raise VideoToolError("Video operation was cancelled.")
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with self._process_lock:
            self._process = process
        deadline = time.monotonic() + max(1.0, float(timeout))
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise VideoToolError("Video operation was cancelled.")
                if time.monotonic() >= deadline:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise VideoToolError(
                        f"Video operation exceeded the {format_number(timeout)} second timeout."
                    )
                try:
                    stdout, stderr = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                details = _bounded_process_text((stderr or stdout or "").strip())
                raise VideoToolError(f"FFmpeg failed with exit code {process.returncode}: {details}")
            return _bounded_process_text((stderr or stdout or "").strip())
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

    @staticmethod
    def _resolve_input(reference: Any, *, remote: bool) -> Path:
        text = _media_reference(reference)
        if not text:
            raise VideoToolError("A local video input is required.")
        if text.lower().startswith(("http://", "https://", "data:")):
            raise VideoToolError("Video Tools accepts verified local files only.")
        try:
            path = Path(text).expanduser().resolve(strict=True)
        except OSError as exc:
            raise VideoToolError(f"Source video is missing or unavailable: {text}") from exc
        if not path.is_file():
            raise VideoToolError(f"Video input is not a file: {path.name}.")
        if remote and not _is_within(path, _remote_media_roots()):
            raise VideoToolError("Remote video input is outside the allowed media roots.")
        return path

    @staticmethod
    def _authorize_output(path: Path, *, remote: bool) -> None:
        if remote and not _is_within(path.parent, _remote_media_roots()):
            raise VideoToolError("Remote output is outside the allowed media roots.")

    def concatenate(
        self,
        settings: Mapping[str, Any],
        *,
        remote: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        inputs = [self._resolve_input(item, remote=remote) for item in settings.get("inputs", [])]
        if len(inputs) < 2:
            raise VideoToolError("Concatenate Videos requires at least two inputs.")
        probes = [probe_video(path) for path in inputs]
        input_durations = [float(probe.get("duration") or 0.0) for probe in probes]
        if any(duration <= 0.0 or not math.isfinite(duration) for duration in input_durations):
            raise VideoToolError("Every concatenated input must have a measurable positive duration.")
        copy_requested = _validate_concat_codecs(settings, probes)
        extension = str(settings["output_format"])
        output = _resolved_output_path(str(settings.get("output_path") or ""), inputs[0], "_concatenated", extension)
        self._authorize_output(output, remote=remote)
        temp_output = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.part{output.suffix}")
        try:
            ffmpeg = _find_ffmpeg()
            if copy_requested:
                with tempfile.TemporaryDirectory(prefix="hmb_concat_") as temp_dir:
                    concat_list = Path(temp_dir) / "inputs.txt"
                    lines = []
                    for path in inputs:
                        escaped = str(path).replace("\\", "/").replace("'", "'\\''")
                        lines.append(f"file '{escaped}'")
                    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
                    command = build_concat_ffmpeg_command(
                        ffmpeg,
                        str(concat_list),
                        str(temp_output),
                        settings,
                        has_audio=bool(probes[0]["has_audio"]),
                    )
                    process_log = self._run(command, cancel_event)
            else:
                command = build_filter_concat_ffmpeg_command(
                    ffmpeg,
                    [str(path) for path in inputs],
                    str(temp_output),
                    settings,
                    probes,
                )
                process_log = self._run(command, cancel_event)
            if not temp_output.is_file() or temp_output.stat().st_size <= 0:
                raise VideoToolError("FFmpeg produced an empty concatenated video.")
            result_probe = probe_video(temp_output)
            expected_duration = math.fsum(input_durations)
            result_duration = float(result_probe.get("duration") or 0.0)
            target_rate = float(_concat_frame_rate(settings, probes))
            duration_tolerance = min(
                2.0,
                max(0.25, 2.0 / max(target_rate, 1.0), 0.05 * len(inputs)),
            )
            if (
                result_duration <= 0.0
                or not math.isfinite(result_duration)
                or abs(result_duration - expected_duration) > duration_tolerance
            ):
                raise VideoToolError(
                    "FFmpeg produced an incomplete concatenation: "
                    f"expected {expected_duration:.3f}s, got {result_duration:.3f}s."
                )
            expected_audio = any(bool(probe.get("has_audio")) for probe in probes)
            if bool(result_probe.get("has_audio")) != expected_audio:
                raise VideoToolError("FFmpeg output did not preserve the expected audio-stream layout.")
            expected_width = int(probes[0]["width"])
            expected_height = int(probes[0]["height"])
            if not copy_requested:
                expected_width -= expected_width % 2
                expected_height -= expected_height % 2
            if (int(result_probe.get("width") or 0), int(result_probe.get("height") or 0)) != (
                expected_width,
                expected_height,
            ):
                raise VideoToolError("FFmpeg output did not preserve the normalized output resolution.")
            if not copy_requested and abs(float(result_probe.get("frame_rate") or 0.0) - target_rate) > 0.05:
                raise VideoToolError("FFmpeg output did not preserve the normalized output frame rate.")
            selected_video_codec = str(settings["video_codec"])
            expected_video_codec = (
                str(probes[0].get("video_codec") or "")
                if selected_video_codec == "copy"
                else {"libx264": "h264", "libx265": "hevc", "libvpx-vp9": "vp9"}[selected_video_codec]
            )
            if str(result_probe.get("video_codec") or "") != expected_video_codec:
                raise VideoToolError("FFmpeg output video codec does not match the selected codec.")
            if expected_audio:
                selected_audio_codec = str(settings["audio_codec"])
                expected_audio_codec = (
                    str(probes[0].get("audio_codec") or "")
                    if selected_audio_codec == "copy"
                    else {
                        "aac": "aac",
                        "mp3": "mp3",
                        "libmp3lame": "mp3",
                        "libopus": "opus",
                    }[selected_audio_codec]
                )
                if str(result_probe.get("audio_codec") or "") != expected_audio_codec:
                    raise VideoToolError("FFmpeg output audio codec does not match the selected codec.")
                if not copy_requested and (
                    int(result_probe.get("audio_sample_rate") or 0) != 48_000
                    or int(result_probe.get("audio_channels") or 0) != 2
                ):
                    raise VideoToolError("FFmpeg output audio was not normalized to 48 kHz stereo.")
            if output.exists():
                raise VideoToolError("Output appeared during processing; it was not overwritten.")
            if cancel_event is not None and cancel_event.is_set():
                raise VideoToolError("Video operation was cancelled.")
            os.replace(temp_output, output)
            return {
                "path": str(output),
                "operation": "concatenate",
                "input_count": len(inputs),
                "width": result_probe["width"],
                "height": result_probe["height"],
                "duration": result_probe["duration"],
                "has_audio": result_probe["has_audio"],
                "log": process_log,
            }
        finally:
            try:
                if temp_output.exists():
                    temp_output.unlink()
            except OSError:
                pass

    def crop(
        self,
        settings: Mapping[str, Any],
        *,
        remote: bool = False,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        source = self._resolve_input(settings.get("input"), remote=remote)
        source_probe = probe_video(source)
        rectangle = calculate_crop_rectangle(source_probe["width"], source_probe["height"], settings)
        output = _resolved_output_path(str(settings.get("output_path") or ""), source, "_crop", "mp4")
        self._authorize_output(output, remote=remote)
        temp_output = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.part{output.suffix}")
        try:
            command = build_crop_ffmpeg_command(
                _find_ffmpeg(),
                str(source),
                str(temp_output),
                rectangle,
                has_audio=bool(source_probe["has_audio"]),
                processing_speed=str(settings["processing_speed"]),
            )
            process_log = self._run(command, cancel_event)
            if not temp_output.is_file() or temp_output.stat().st_size <= 0:
                raise VideoToolError("FFmpeg produced an empty cropped video.")
            if output.exists():
                raise VideoToolError("Output appeared during processing; it was not overwritten.")
            if cancel_event is not None and cancel_event.is_set():
                raise VideoToolError("Video operation was cancelled.")
            os.replace(temp_output, output)
            result_probe = probe_video(output)
            return {
                "path": str(output),
                "operation": "crop",
                "source_width": source_probe["width"],
                "source_height": source_probe["height"],
                "width": result_probe["width"],
                "height": result_probe["height"],
                "left": rectangle[2],
                "top": rectangle[3],
                "duration": result_probe["duration"],
                "has_audio": result_probe["has_audio"],
                "log": process_log,
            }
        finally:
            try:
                if temp_output.exists():
                    temp_output.unlink()
            except OSError:
                pass
