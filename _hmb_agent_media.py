"""Optional, bounded local reference pixels for the existing native Agent call.

Only the verified Prompt snapshot supplies sources. This module has no network
client, model invocation, arbitrary-path tool, or persistent media cache.
"""
from __future__ import annotations

from collections import OrderedDict
import copy
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable

MAX_ATTACHMENTS = 8
MAX_IMAGE_ATTACHMENTS = 4
MAX_EDGE = 768
MAX_INPUT_IMAGE_BYTES = 32 * 1024 * 1024
MAX_ENCODED_BYTES = 3 * 1024 * 1024
PREPARATION_SECONDS = 12.0
PER_DECODE_SECONDS = 2.0
_CACHE_BYTES_LIMIT = 24 * 1024 * 1024
_CACHE: OrderedDict[tuple, tuple[bytes, int, int, float | None]] = OrderedDict()
_PROBE_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_CACHE_LOCK = threading.Lock()
_PILLOW_DECODER = """
import io, sys
from PIL import Image, ImageOps
data = sys.stdin.buffer.read(33554433) if sys.argv[1] == '-' else open(sys.argv[1], 'rb').read(33554433)
if len(data) > 33554432: raise ValueError('input limit')
with Image.open(io.BytesIO(data)) as original:
    if original.width * original.height > 32000000: raise ValueError('pixel limit')
    image = ImageOps.exif_transpose(original)
    image.thumbnail((768, 768))
    image.convert('RGBA' if 'A' in image.getbands() else 'RGB').save(sys.stdout.buffer, format='PNG')
"""
_PNG_BUDGET_DECODER = """
import io, sys
from PIL import Image
blob = sys.stdin.buffer.read(3145729)
limit = int(sys.argv[1])
with Image.open(io.BytesIO(blob)) as original:
    image = original.copy()
    while True:
        output = io.BytesIO()
        image.save(output, format='PNG', optimize=True)
        encoded = output.getvalue()
        if len(encoded) <= limit:
            sys.stdout.buffer.write(encoded)
            break
        if min(image.size) <= 32: raise ValueError('encoded byte limit')
        image = image.resize((max(1, int(image.width * .8)), max(1, int(image.height * .8))), Image.Resampling.LANCZOS)
"""


def _uses_native_user_content(agent: Any) -> bool:
    """Recognize the installed Standard Agent's current native state type."""
    try:
        from griptape_nodes_library.llm.agent_state import AgentState

        return type(agent) is AgentState
    except (ImportError, AttributeError):
        return False


def driver_accepts_images(agent: Any) -> bool:
    """Use installed metadata, never a separate model-name allowlist."""
    try:
        from griptape_nodes.drivers.cloud_models import VISION_MODEL_CHOICES

        if _uses_native_user_content(agent):
            from griptape_nodes_library.llm.model_config import ModelProvider

            config = agent.model
            return (config is not None and config.provider == ModelProvider.GRIPTAPE_CLOUD
                    and not config.base_url and config.model in VISION_MODEL_CHOICES)
        from griptape.drivers.prompt.griptape_cloud_prompt_driver import GriptapeCloudPromptDriver

        driver = agent.tasks[0].prompt_driver
        # An OpenAI-compatible/custom endpoint can share a model name without
        # sharing its modalities. Unknown endpoints keep the native text path.
        return type(driver) is GriptapeCloudPromptDriver and driver.model in VISION_MODEL_CHOICES
    except Exception:
        return False


def _binaries() -> tuple[Path | None, Path | None]:
    candidates: list[Path] = []
    if os.environ.get("FFMPEG_PATH"):
        candidates.append(Path(os.environ["FFMPEG_PATH"]))
    try:
        import imageio_ffmpeg
        candidates.append(Path(imageio_ffmpeg.get_ffmpeg_exe()))
    except Exception:
        pass
    try:
        import static_ffmpeg
        root = Path(static_ffmpeg.__file__).resolve().parent
        for folder in ("win32", "win64", "linux", "darwin"):
            for name in ("ffmpeg.exe", "ffmpeg"):
                candidates.append(root / "bin" / folder / name)
    except Exception:
        pass
    if os.name == "nt":
        # Conventional explicit system install, not executable search via PATH.
        candidates.append(Path(os.environ.get("SystemDrive", "C:") + "/") / "ffmpeg/bin/ffmpeg.exe")
    def first_file(paths: list[Path]) -> Path | None:
        for candidate in paths:
            try:
                if candidate.is_absolute() and candidate.is_file():
                    return candidate
            except OSError:
                pass
        return None

    ffmpeg = first_file(candidates)
    # imageio commonly ships FFmpeg alone. Search probe independently so a
    # usable decoder does not hide the installed system/package FFprobe.
    probe_candidates: list[Path] = []
    if os.environ.get("FFPROBE_PATH"):
        probe_candidates.append(Path(os.environ["FFPROBE_PATH"]))
    probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    if ffmpeg is not None:
        probe_candidates.append(ffmpeg.with_name(probe_name))
    probe_candidates.extend(candidate.with_name(probe_name) for candidate in candidates)
    return ffmpeg, first_file(probe_candidates)


def _source(value: Any, kind: str) -> tuple[Path | bytes, tuple]:
    """Resolve a selected local/project reference without fetching remote URLs."""
    text = str(value or "").strip()
    if not text or len(text) > MAX_INPUT_IMAGE_BYTES * 2:
        raise ValueError("unavailable")
    if kind == "image" and text.startswith("data:image/"):
        header, payload = text.split(",", 1)
        if not header.endswith(";base64"):
            raise ValueError("unavailable")
        blob = base64.b64decode(payload, validate=True)
        if len(blob) > MAX_INPUT_IMAGE_BYTES:
            raise ValueError("input_limit")
        return blob, ("data", hashlib.sha256(blob).hexdigest())
    if text.startswith(("\\\\", "//")):
        raise ValueError("nonlocal")
    try:
        from griptape_nodes.files.file import File
        text = str(File(text).resolve())
    except Exception:
        # Absolute local paths work even without a loaded host project. Never
        # reinterpret a project-relative path against the engine working dir.
        if not Path(text).is_absolute():
            raise ValueError("unavailable") from None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text) or text.startswith(("\\\\", "//", "data:", "asset:")):
        raise ValueError("nonlocal")
    path = Path(text)
    if os.name == "nt" and path.anchor:
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) == 4:
            raise ValueError("nonlocal")
    if not path.is_absolute() or not path.is_file():
        raise ValueError("unavailable")
    stat = path.stat()
    if stat.st_size <= 0 or (kind == "image" and stat.st_size > MAX_INPUT_IMAGE_BYTES):
        raise ValueError("input_limit")
    return path, (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _run(args: list[str], deadline: float, data: bytes | None = None) -> subprocess.CompletedProcess:
    timeout = min(PER_DECODE_SECONDS, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError("budget")
    return subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _video_info(path: Path, probe: Path | None, deadline: float) -> dict:
    if probe is None:
        return {}
    try:
        result = _run([str(probe), "-v", "error", "-protocol_whitelist", "file,pipe",
                       "-show_entries", "format=duration,start_time:stream=codec_type,start_time,duration,duration_ts,time_base",
                       "-of", "json", str(path)], deadline)
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        video = next((v for v in data.get("streams", []) if v.get("codec_type") == "video"), {})
        duration = _number(video.get("duration"))
        if duration is None:
            ticks = _number(video.get("duration_ts"))
            try:
                numerator, denominator = (float(v) for v in str(video.get("time_base", "")).split("/"))
                duration = ticks * numerator / denominator if ticks is not None and denominator else None
            except (ValueError, ZeroDivisionError):
                pass
        if duration is None:
            duration = _number(fmt.get("duration"))
        start = _number(video.get("start_time", fmt.get("start_time")))
        return {"duration": duration if duration is not None and duration > 0 else None,
                "start_pts": start}
    except Exception:
        return {}


def _duration(path: Path, probe: Path | None, deadline: float) -> float | None:
    return _video_info(path, probe, deadline).get("duration")


def _decode(source: Path | bytes, identity: tuple, seek: float | None,
            ffmpeg: Path | None, deadline: float) -> tuple[bytes, int, int, float | None]:
    key = (*identity, seek, MAX_EDGE)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return cached
    actual_time = None
    if ffmpeg is not None:
        args = [str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "info", "-threads", "1",
                "-protocol_whitelist", "file,pipe", "-copyts"]
        if seek is not None:
            args += ["-ss", f"{seek:.6f}"]
        args += ["-i", "pipe:0" if isinstance(source, bytes) else str(source),
                 "-frames:v", "1", "-an", "-sn", "-dn", "-vf",
                 f"scale='min({MAX_EDGE},iw)':'min({MAX_EDGE},ih)':force_original_aspect_ratio=decrease,showinfo",
                 "-threads", "1", "-c:v", "png", "-f", "image2pipe", "pipe:1"]
        result = _run(args, deadline, source if isinstance(source, bytes) else None)
        blob = result.stdout
        if seek is not None:
            match = re.search(rb"\bn:\s*0\s+pts:.*?pts_time:([-+0-9.eE]+)", result.stderr)
            if match:
                value = float(match.group(1))
                if math.isfinite(value):
                    actual_time = value
    elif seek is None:
        # Keep the installed Pillow fallback behind the same killable decode
        # timeout as FFmpeg, including malformed compressed image input.
        import sys
        result = _run([sys.executable, "-c", _PILLOW_DECODER,
                       "-" if isinstance(source, bytes) else str(source)],
                      deadline, source if isinstance(source, bytes) else None)
        blob = result.stdout
    else:
        raise ValueError("decoder_unavailable")
    if len(blob) > MAX_ENCODED_BYTES or blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("decode_unavailable")
    width, height = int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")
    if not (0 < width <= MAX_EDGE and 0 < height <= MAX_EDGE):
        raise ValueError("dimensions")
    value = (blob, width, height, actual_time)
    with _CACHE_LOCK:
        _CACHE[key] = value
        _CACHE.move_to_end(key)
        total = sum(len(entry[0]) for entry in _CACHE.values())
        while total > _CACHE_BYTES_LIMIT and _CACHE:
            _, evicted = _CACHE.popitem(last=False)
            total -= len(evicted[0])
    return value


def _label(record: dict, kind: str) -> dict:
    # Source paths, URL credentials and private filesystem details stay local.
    allowed = ("token", "image", "video", "source_type", "image_main_type", "image_sub_type",
               "video_main_type", "video_sub_type", "target_id", "owner", "bindings",
               "control_role", "control_bindings", "frame_domain", "reference_scope", "frame_ranges")
    label = {key: record[key] for key in allowed if key in record}
    label["kind"] = kind
    return label


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _token(record: dict) -> str:
    value = str(record.get("token") or record.get("image") or record.get("video") or "")
    return value if re.fullmatch(r"@(image|video)[1-9][0-9]{0,2}", value) else ""


def _audit_id(value: Any) -> str:
    text = str(value or "")
    return text if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", text) else ""


def _observation_row(record: dict, kind: str) -> dict:
    # Keep review records free of source URLs, paths, prose and credentials.
    identity = record.get("identity") if isinstance(record.get("identity"), dict) else {}
    metadata = record.get("frame_metadata") if isinstance(record.get("frame_metadata"), dict) else {}
    return {"media_token": _token(record), "kind": kind, "observation_role": _role(record, kind),
            "video_uid": _audit_id(identity.get("video_uid") or metadata.get("video_uid")),
            "source_uid": _audit_id(identity.get("source_uid") or metadata.get("source_uid")),
            "bundle_run_id": _bundle(record)}


def _role(record: dict, kind: str) -> str:
    """Observation scheduling only; never change the record's source authority."""
    if kind == "image":
        return "character" if record.get("image_main_type") == "Character" or record.get("source_type") in {
            "Character Appearance", "Partial Character Detail", "Character Sheet"} else "image"
    subtype = str(record.get("video_sub_type") or "").casefold()
    return {"original preview": "original", "mask": "mask", "depth": "depth",
            "motion guide": "motion_guide"}.get(subtype, "video")


def _clock(record: dict) -> tuple[float, int, int] | None:
    metadata = record.get("frame_metadata")
    if not isinstance(metadata, dict) or metadata.get("conflict") or metadata.get("valid") is False:
        return None
    fps = _number(metadata.get("fps"))
    start, end = _number(metadata.get("start_frame")), _number(metadata.get("end_frame"))
    count = _number(metadata.get("frame_count"))
    if (fps is None or fps <= 0 or start is None or end is None or start != int(start)
            or end != int(end) or end < start or count != end - start + 1):
        return None
    return fps, int(start), int(end)


def _bundle(record: dict) -> str:
    metadata = record.get("frame_metadata")
    if not isinstance(metadata, dict):
        return ""
    # These IDs come from the paired Prompt's selected Picker provenance. Equal
    # paths, names, durations or frame domains never establish a shared capture.
    return _audit_id(metadata.get("bundle_run_id") or metadata.get("pair_run_id"))


def _sample_plan(records: list[dict], duration: float | None) -> list[dict]:
    """Choose authored event frames, then Range midpoints and boundaries."""
    clock = _clock(records[0])
    requests: list[dict] = []
    seen: set[float] = set()

    def add(seconds: float, reason: str, frame: float | None = None) -> None:
        if seconds < 0 or not math.isfinite(seconds) or (duration is not None and seconds >= duration):
            return
        key = round(seconds, 6)
        if key not in seen:
            seen.add(key)
            requests.append({"seek": key, "reason": reason, "requested_source_frame": frame})

    if clock:
        fps, start, end = clock
        segments: list[tuple[int, int]] = []
        for record in records:
            timing = record.get("timing") if isinstance(record.get("timing"), dict) else {}
            for cue in timing.get("authored_timing_cues", [])[:64]:
                if not isinstance(cue, dict):
                    continue
                frame = _number(cue.get("frame"))
                if frame is not None and frame == int(frame) and start <= frame <= end:
                    add((frame - start) / fps, "authored_event", int(frame))
            for binding in record.get("frame_ranges", [])[:64]:
                if not isinstance(binding, dict) or binding.get("enabled") is not True:
                    continue
                for segment in binding.get("segments", [])[:64]:
                    if not isinstance(segment, dict):
                        continue
                    left, right = _number(segment.get("start_frame")), _number(segment.get("end_frame"))
                    if (left is None or right is None or left != int(left) or right != int(right)
                            or left > right or right < start or left > end):
                        continue
                    pair = max(start, int(left)), min(end, int(right))
                    if pair not in segments:
                        segments.append(pair)
            # Older public timing envelopes already contain active range rows.
            for segment in timing.get("range_segments", [])[:64]:
                if not isinstance(segment, dict):
                    continue
                left, right = _number(segment.get("start_frame")), _number(segment.get("end_frame"))
                if (left is not None and right is not None and left == int(left) and right == int(right)
                        and left <= right and right >= start and left <= end):
                    pair = max(start, int(left)), min(end, int(right))
                    if pair not in segments:
                        segments.append(pair)
        for left, right in segments:
            frame = (left + right) // 2
            add((frame - start) / fps, "range_midpoint", frame)
        for left, right in segments:
            add((left - start) / fps, "range_start", left)
            add((right - start) / fps, "range_end", right)
        # Give active Ranges a slot even if a clip has many authored cues. The
        # first event and Range midpoints precede additional event/boundary
        # samples; no semantic importance is invented from source labels.
        events = [v for v in requests if v["reason"] == "authored_event"]
        midpoints = [v for v in requests if v["reason"] == "range_midpoint"]
        boundaries = [v for v in requests if v["reason"] in {"range_start", "range_end"}]
        requests = events[:1] + midpoints + events[1:] + boundaries
    if duration is None:
        add(0.0, "fallback_start", clock[1] if clock else None)
    else:
        for value, reason in [(0.0, "fallback_start"), (duration * .5, "fallback_middle"),
                              (max(0.0, duration - .1), "fallback_end")]:
            add(value, reason)
    return requests[:64]


def augment_prompt(prompt: str, snapshot: dict, agent: Any, *,
                   is_live: Callable[[], bool] = lambda: True,
                   report_sink: Callable[[dict], None] | None = None) -> Any:
    """Return a native ListArtifact, or the original text after optional failure.

    This runs within the native scheduler's worker step, never in the Picker UI
    import callback. Every text source remains in the unchanged original prompt.
    Sampled stills do not constitute continuous motion or frame-complete review.
    """
    records = []
    report = {"schema": "hmb-agent-reference-observation", "version": 1,
              "machine_sha256": (snapshot.get("machine_sha256") if isinstance(snapshot, dict)
                  and re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get("machine_sha256") or "")) else ""),
              "sampling_policy": "authored_event_range_aligned_roles_v1", "status": "unobserved",
              "coverage": [], "skips": [], "groups": [], "budget_summary": {}}
    started = time.monotonic()
    attachments: list[Any] = []
    encoded_bytes = 0
    count = 0
    image_count = 0

    def skip(record: dict, kind: str, reason: str, sample: dict | None = None) -> None:
        row = _observation_row(record, kind)
        row["reason"] = reason
        if sample:
            row.update({"requested_seek_seconds": sample["seek"], "sample_reason": sample["reason"],
                        "requested_source_frame": sample.get("requested_source_frame")})
        if len(report["skips"]) < 256:
            report["skips"].append(row)

    try:
        if not isinstance(snapshot, dict) or snapshot.get("schema") != "hmb-agent-reference-media" or snapshot.get("version") != 1:
            report["status"] = "invalid_snapshot"
            return prompt
        images = [v for v in snapshot.get("images", [])[:64] if isinstance(v, dict)]
        videos = [v for v in snapshot.get("videos", [])[:64] if isinstance(v, dict)]
        records = [(v, "image") for v in images] + [(v, "video") for v in videos]
        if not is_live() or not driver_accepts_images(agent):
            reason = "cancelled" if not is_live() else "no_vision_driver"
            for record, kind in records:
                skip(record, kind, reason)
            report["status"] = reason
            return prompt
        native_user_content = _uses_native_user_content(agent)
        if native_user_content:
            from pydantic_ai.messages import BinaryContent
        else:
            from griptape.artifacts import ImageArtifact, ListArtifact, TextArtifact
        deadline = started + PREPARATION_SECONDS
        ffmpeg, probe = _binaries()

        def unavailable_reason(exc: Exception) -> str:
            if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
                return "deadline" if time.monotonic() >= deadline else "decode_timeout"
            return str(exc) if isinstance(exc, ValueError) and str(exc) in {
                "nonlocal", "unavailable", "input_limit", "decoder_unavailable", "dimensions"} else "decode_unavailable"

        def append(record: dict, kind: str, sample: dict | None, group_id: str = "",
                   normalized_target: float | None = None) -> bool:
            nonlocal count, encoded_bytes, image_count
            reason = ("cancelled" if not is_live() else "deadline" if time.monotonic() >= deadline else
                      "attachment_cap" if count >= MAX_ATTACHMENTS else
                      "image_cap" if kind == "image" and image_count >= MAX_IMAGE_ATTACHMENTS else "")
            if reason:
                skip(record, kind, reason, sample)
                return False
            try:
                source, identity = _source(record.get("source"), kind)
                seek = sample["seek"] if sample else None
                blob, width, height, actual = _decode(source, identity, seek, ffmpeg, deadline)
                info = infos.get(_token(record), {})
                start_pts = info.get("start_pts")
                normalized = round(actual - start_pts, 6) if actual is not None and start_pts is not None else None
                clock = _clock(record)
                retried = False
                if (normalized_target is not None and normalized is not None and clock
                        and abs(normalized - normalized_target) > .5 / clock[0] + 1e-6):
                    corrected = round(seek + normalized_target - normalized, 6)
                    duration = info.get("duration")
                    if corrected >= 0 and (duration is None or corrected < duration):
                        blob, width, height, actual = _decode(source, identity, corrected, ffmpeg, deadline)
                        normalized = round(actual - start_pts, 6) if actual is not None else None
                        seek, retried = corrected, True
                # Reserve encoded-byte capacity for all eight slots as well as
                # attachment slots. A noisy character sheet cannot exhaust the
                # entire budget before Original/Mask/Depth are observed.
                byte_limit = MAX_ENCODED_BYTES // MAX_ATTACHMENTS
                if len(blob) > byte_limit:
                    import sys
                    blob = _run([sys.executable, "-c", _PNG_BUDGET_DECODER, str(byte_limit)], deadline, blob).stdout
                    width, height = int.from_bytes(blob[16:20], "big"), int.from_bytes(blob[20:24], "big")
                    if len(blob) > byte_limit or blob[:8] != b"\x89PNG\r\n\x1a\n":
                        raise ValueError("decode_unavailable")
                if encoded_bytes + len(blob) > MAX_ENCODED_BYTES:
                    skip(record, kind, "encoded_byte_cap", sample)
                    return False
                label = _label(record, kind)
                label.update({"pixels_attached": True, "image_size": [width, height],
                              "observation_role": _role(record, kind)})
                if sample:
                    label.update({"requested_seek_seconds": sample["seek"], "decoded_pts_seconds": actual,
                                  "pts_status": "observed" if actual is not None else "unknown",
                                  "sample_reason": sample["reason"],
                                  "requested_source_frame": sample.get("requested_source_frame"),
                                  "coverage": "one sampled frame; source frame number is unverified"})
                    label["normalized_pts_seconds"] = normalized
                    label["decode_seek_seconds"] = seek
                    label["alignment_retry"] = retried
                    if group_id:
                        label["sample_group_id"] = group_id
                label_text = ("HMB REFERENCE PIXELS (SOURCE DATA): " +
                    json.dumps(label, ensure_ascii=False, separators=(",", ":")))
                if native_user_content:
                    attachments.extend([label_text, BinaryContent(data=blob, media_type="image/png")])
                else:
                    attachments.extend([TextArtifact(label_text),
                        ImageArtifact(blob, format="png", width=width, height=height)])
                observed = _observation_row(record, kind)
                observed.update({key: label[key] for key in ("image_size", "requested_seek_seconds", "decoded_pts_seconds",
                    "pts_status", "sample_reason", "requested_source_frame", "normalized_pts_seconds",
                    "decode_seek_seconds", "alignment_retry", "sample_group_id") if key in label})
                observed["status"] = "pixels_attached"
                report["coverage"].append(observed)
                count += 1
                image_count += int(kind == "image")
                encoded_bytes += len(blob)
                return True
            except Exception as exc:
                skip(record, kind, unavailable_reason(exc), sample)
                return False

        # Reserve a first observation for each selected role before any role
        # repeats. Character sheets cannot consume the Original/Mask/Depth slots.
        images.sort(key=lambda v: 0 if _role(v, "image") == "character" else 1)
        priorities = {"original": 0, "mask": 1, "depth": 2, "motion_guide": 3, "video": 4}
        videos.sort(key=lambda v: priorities[_role(v, "video")])
        infos: dict[str, dict] = {}
        units: list[list[dict]] = []
        grouped: dict[tuple, list[dict]] = {}
        for record in videos:
            key = (_bundle(record), _clock(record))
            if key[0] and key[1]:
                grouped.setdefault(key, []).append(record)
            else:
                units.append([record])
        for members in grouped.values():
            if len({_role(v, "video") for v in members}) == len(members):
                units.append(members)
            else:
                for record in members:
                    skip(record, "video", "ambiguous_bundle_roles")
                    units.append([record])
        units.sort(key=lambda members: min(priorities[_role(v, "video")] for v in members))

        def observe_unit(members: list[dict], sample_index: int) -> None:
            if not is_live() or time.monotonic() >= deadline or count + len(members) > MAX_ATTACHMENTS:
                for record in members:
                    skip(record, "video", "cancelled" if not is_live() else
                         "deadline" if time.monotonic() >= deadline else "attachment_cap")
                return
            for record in members:
                token = _token(record)
                if token not in infos:
                    try:
                        source, identity = _source(record.get("source"), "video")
                        if not isinstance(source, Path):
                            raise ValueError("nonlocal")
                        with _CACHE_LOCK:
                            info = _PROBE_CACHE.get(identity)
                        if info is None:
                            info = _video_info(source, probe, deadline)
                            if info:
                                with _CACHE_LOCK:
                                    _PROBE_CACHE[identity] = dict(info)
                                    while len(_PROBE_CACHE) > 64:
                                        _PROBE_CACHE.popitem(last=False)
                        infos[token] = dict(info or {})
                    except Exception as exc:
                        infos[token] = {"error": unavailable_reason(exc)}
            duration_values = [infos[_token(v)].get("duration") for v in members]
            durations = [v for v in duration_values if v is not None]
            clock = _clock(members[0])
            if clock:
                durations.append((clock[2] - clock[1] + 1) / clock[0])
            duration = min(durations) if durations else None
            plan = _sample_plan(members, duration)
            if sample_index >= len(plan):
                return
            sample = plan[sample_index]
            # A shared frame-domain and capture ID permit scheduling a shared
            # time; actual matching PTS is checked after decoding, not assumed.
            group_id = hashlib.sha256((str(snapshot.get("machine_sha256") or "") + "|" +
                "|".join(_token(v) for v in members) + "|" + str(sample["seek"])).encode()).hexdigest()[:24] if len(members) > 1 else ""
            first = len(report["coverage"])
            anchor = None
            for record in members:
                if infos[_token(record)].get("error"):
                    skip(record, "video", infos[_token(record)]["error"], sample)
                else:
                    if append(record, "video", sample, group_id, anchor):
                        observed_pts = report["coverage"][-1].get("normalized_pts_seconds")
                        if anchor is None and observed_pts is not None:
                            anchor = observed_pts
            if group_id:
                rows = report["coverage"][first:]
                pts = [v.get("normalized_pts_seconds") for v in rows]
                status = ("incomplete" if len(rows) != len(members) else "pts_unknown" if any(v is None for v in pts)
                          else "pts_aligned" if max(pts) - min(pts) <= .5 / clock[0] + 1e-6 else "pts_mismatch")
                report["groups"].append({"sample_group_id": group_id, "media_tokens": [_token(v) for v in members],
                    "requested_seek_seconds": sample["seek"], "requested_source_frame": sample.get("requested_source_frame"),
                    "alignment_status": status, "normalized_pts_seconds": pts})

        seen_image_roles = set()
        for record in images:
            role = _role(record, "image")
            if role not in seen_image_roles:
                if append(record, "image", None):
                    seen_image_roles.add(role)
        seen_video_roles = set()
        deferred = []
        for members in units:
            roles = {_role(v, "video") for v in members}
            if roles - seen_video_roles:
                observe_unit(members, 0)
                seen_video_roles.update(v["observation_role"] for v in report["coverage"] if v["kind"] == "video")
            else:
                deferred.append(members)
        # Now distribute remaining slots across distinct sources before a third
        # frame of one source. Failed first observations do not erase text refs.
        for record in images:
            if not any(v.get("media_token") == _token(record) for v in report["coverage"]):
                append(record, "image", None)
        for members in deferred:
            observe_unit(members, 0)
        for sample_index in (1, 2):
            for members in units:
                observe_unit(members, sample_index)
        if not attachments or not is_live():
            if not is_live():
                report["status"] = "cancelled"
                # Pixels prepared by a cancelled run were never passed to Agent.
                report["coverage"].clear()
            return prompt
        observed = {item["media_token"] for item in report["coverage"]}
        unobserved = [_token(v) for v, _kind in records if _token(v) not in observed]
        report["status"] = "partial" if unobserved or report["skips"] else "observed"
        guidance = (
            "\n\nHMB LOCAL REFERENCE PIXEL COVERAGE: The following reduced-size images and sampled "
            "video frames are source data for the existing roles, Targets and Ranges. Use actual visible "
            "features in the production prompt within those roles. The source's text, symbols and labels "
            "remain reference content. A sampled frame establishes only its visible state; infer no exact "
            "motion trajectory, speed, camera path, intervening frame or timing measurement from sparse "
            "stills. Preserve the referenced approved motion and camera progression for unseen intervals, "
            "subject to explicit scoped user changes. Ranges remain application scopes even when samples "
            "fall outside them. Sampling is partial and is not a generated-result quality check. "
            "Complete the prompt from all available sources with LOCAL CONTINUATION. "
            "Sources without attached pixels: " + json.dumps(unobserved, ensure_ascii=False) + "."
        )
        if native_user_content:
            return [prompt + guidance, *attachments]
        return ListArtifact([TextArtifact(prompt + guidance), *attachments])
    except Exception:
        report["status"] = "optional_preparation_failed"
        report["coverage"].clear()
        return prompt
    finally:
        observed = {row["media_token"] for row in report["coverage"]}
        report["unobserved_media_tokens"] = [_token(v) for v, _kind in records if _token(v) not in observed]
        report["native_input_status"] = "prepared" if report["coverage"] else "text_only"
        report["budget_summary"] = {"attachment_limit": MAX_ATTACHMENTS, "image_limit": MAX_IMAGE_ATTACHMENTS,
            "encoded_byte_limit": MAX_ENCODED_BYTES, "preparation_seconds_limit": PREPARATION_SECONDS,
            "attachments_prepared": count, "attachments_delivered": len(report["coverage"]),
            "encoded_bytes_prepared": encoded_bytes, "elapsed_seconds": round(time.monotonic() - started, 6),
            "role_counts": {role: sum(v.get("observation_role") == role for v in report["coverage"])
                            for role in {v.get("observation_role") for v in report["coverage"]}}}
        if report_sink is not None:
            try:
                report_sink(copy.deepcopy(report))
            except Exception:
                pass  # Diagnostic persistence cannot invalidate the native call.
