"""Project-confined sound catalog and immutable Shot sound snapshots.

This module does not invoke a model, move source files, or create project folders.
The caller proves the retained publisher/edge. A snapshot is data, not a signed
authorization; execution additionally verifies each selected original's bytes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

SCHEMA = "hmb-sound-library-snapshot"
VERSION = 1
ROLES = ("Dialogue", "SFX", "Ambience", "Music")
PURPOSES = ("reference", "mix", "both")
EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".ogg"})
REFERENCE_EXTENSIONS = frozenset({".wav", ".mp3"})
MAX_TRACKS = 64
MAX_CATALOG_FILES = 20000
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
DEFAULT_PROJECTS_ROOT = "//192.168.200.19/v/projects"


class SoundError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SoundPreparingError(SoundError):
    hmb_sound_preparing = True

    def __init__(self):
        super().__init__("SOUND_PREPARING", "선택한 사운드 원본을 준비 중입니다. 준비가 끝난 뒤 실행합니다.")


def _text(value: Any, maximum: int = 4096, *, literal: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise SoundError("SOUND_INVALID_DATA", "사운드 입력 형식이나 길이를 확인하세요.")
    return value if literal else value.strip()


def _number(value: Any, default: float = 0, *, low: float = 0, high: float = 86400) -> float:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
        raise SoundError("SOUND_INVALID_TIMING", "사운드의 시작·사용 구간·볼륨 값을 확인하세요.")
    return float(value)


def _boolean(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        raise SoundError("SOUND_INVALID_DATA", "사운드 사용 설정이 올바르지 않습니다.")
    return value


def project_uid(root: Path) -> str:
    return str(uuid5(NAMESPACE_URL, "hmb-sound-project:" + str(absolute_path(root)).replace("\\", "/").casefold()))


def absolute_path(value: str | Path) -> Path:
    """Normalize authored absolute spelling without opening an SMB path."""
    return Path(os.path.abspath(os.path.normpath(os.fspath(value))))


def source_uid(root: Path, relative_path: str) -> str:
    return "sound:" + hashlib.sha256((project_uid(root) + "\n" + relative_path.casefold()).encode("utf-8")).hexdigest()


def _reject_reparse_path(path: Path) -> None:
    """Inspect authored components before resolve can hide a link/junction."""
    current = path.absolute()
    while current.name:
        try:
            info = current.lstat()
        except OSError:
            # A saved offline project remains authoring data. Actual execution
            # separately requires a readable file and its exact selected hash.
            pass
        else:
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "링크·정션 대신 프로젝트 안의 실제 음원 폴더를 선택하세요.")
        current = current.parent


def relative_audio_path(root: Path, relative: str) -> Path:
    """Pure lexical join for already cataloged presentation; no file reads."""
    if not isinstance(relative, str):
        raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "프로젝트 사운드 폴더 안의 음원을 선택하세요.")
    relative = relative.replace("\\", "/")
    if not relative or relative.startswith("/") or ":" in relative or any(p in {"", ".", ".."} for p in relative.split("/")):
        raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "프로젝트 사운드 폴더 안의 음원을 선택하세요.")
    path = root.joinpath(*relative.split("/"))
    if path.suffix.casefold() not in EXTENSIONS:
        raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "프로젝트 사운드 폴더 안의 지원 음원을 선택하세요.")
    return path


def _source_path(root: Path, relative: str) -> Path:
    path = relative_audio_path(root, relative)
    _reject_reparse_path(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved.suffix.casefold() not in EXTENSIONS:
        raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "프로젝트 사운드 폴더 안의 지원 음원을 선택하세요.")
    return resolved


def media_signature(path: Path) -> str:
    try:
        before = path.stat()
        if not path.is_file() or not 0 < before.st_size <= MAX_SOURCE_BYTES:
            raise OSError()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            for part in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(part)
            finished = os.fstat(stream.fileno())
        after = path.stat()
        facts = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
        if not facts(before) == facts(opened) == facts(finished) == facts(after):
            raise OSError()
        return digest.hexdigest()
    except OSError:
        raise SoundError("SOUND_SOURCE_UNAVAILABLE", "선택한 음원을 읽을 수 없거나 읽는 동안 변경되었습니다. 사운드 목록을 새로고침하세요.") from None


def probe_sound(path: Path) -> dict[str, Any]:
    from _hmb_video_tools import _find_ffmpeg, _find_ffprobe
    try:
        ffmpeg = _find_ffmpeg()
        try:
            probe = _find_ffprobe(ffmpeg)
        except (OSError, ValueError):
            probe = None
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if probe:
            completed = subprocess.run([str(probe), "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams", "-of", "json", str(path)],
                capture_output=True, timeout=20, check=True, creationflags=flags)
            data = json.loads(completed.stdout)
            audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
            if not audio:
                raise ValueError()
            duration = float(audio.get("duration") or data.get("format", {}).get("duration") or 0)
            return {"duration_seconds": _number(duration, low=0.000001), "sample_rate": int(audio.get("sample_rate") or 0), "channels": int(audio.get("channels") or 0)}
        completed = subprocess.run([str(ffmpeg), "-nostdin", "-hide_banner", "-protocol_whitelist", "file,pipe", "-i", str(path)],
            capture_output=True, timeout=20, creationflags=flags)
        log = completed.stderr.decode("utf-8", "replace")
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", log)
        if "Audio:" not in log or not match:
            raise ValueError()
        hours, minutes, seconds = map(float, match.groups())
        return {"duration_seconds": _number(hours * 3600 + minutes * 60 + seconds, low=0.000001), "sample_rate": 0, "channels": 0}
    except SoundError:
        raise
    except Exception:
        raise SoundError("SOUND_DECODE_UNAVAILABLE", "음원 길이·오디오 스트림을 확인하지 못했습니다. 파일 형식과 로컬 FFmpeg를 확인하세요.") from None


def discover_sound_projects(projects_root: str | Path = DEFAULT_PROJECTS_ROOT) -> list[dict[str, str]]:
    _reject_reparse_path(Path(projects_root))
    root = Path(projects_root).resolve()
    try:
        return [{"project_id": child.name, "project_root": str(child / "Ai_Ct_audio").replace("\\", "/")}
            for child in sorted(root.iterdir(), key=lambda p: p.name.casefold())
            if child.is_dir() and not child.is_symlink() and (child / "Ai_Ct_audio").is_dir()
            and (child / "Ai_Ct_audio").resolve().is_relative_to(root)]
    except OSError:
        raise SoundError("SOUND_PROJECT_ROOT_UNAVAILABLE", "프로젝트 공유 경로에 연결할 수 없습니다. 사운드 폴더와 네트워크 연결을 확인하세요.") from None


def scan_sound_project(project_root: str | Path) -> list[dict[str, Any]]:
    _reject_reparse_path(Path(project_root))
    root = Path(project_root).resolve()
    if root.name.casefold() != "ai_ct_audio" or not root.is_dir():
        raise SoundError("SOUND_PROJECT_ROOT_UNAVAILABLE", "선택한 프로젝트의 Ai_Ct_audio 폴더를 확인하세요.")
    assets = []
    try:
        for directory, children, files in os.walk(root, followlinks=False):
            children[:] = sorted([v for v in children if not Path(directory, v).is_symlink()], key=str.casefold)
            for name in sorted(files, key=str.casefold):
                candidate = Path(directory, name)
                if candidate.suffix.casefold() not in EXTENSIONS or candidate.is_symlink():
                    continue
                relative = candidate.relative_to(root).as_posix()
                path = _source_path(root, relative)
                stat = path.stat()
                role = next((r for r in ROLES if r.casefold() in [p.casefold() for p in candidate.relative_to(root).parts[:-1]]), "SFX")
                assets.append({"source_uid": source_uid(root, relative), "relative_path": relative, "name": candidate.stem,
                    "role": role, "extension": candidate.suffix.casefold(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
                if len(assets) > MAX_CATALOG_FILES:
                    raise SoundError("SOUND_CATALOG_LIMIT", "사운드 파일이 너무 많습니다. 프로젝트 폴더를 나누세요.")
    except OSError:
        raise SoundError("SOUND_SCAN_INCOMPLETE", "사운드 폴더 확인이 끝나지 않았습니다. 연결을 확인하고 새로고침하세요.") from None
    return assets


def make_sound_track(root: str | Path, relative: str, *, channel_uuid: str = "", shot_uuid: str = "") -> dict[str, Any]:
    _reject_reparse_path(Path(root))
    root = Path(root).resolve()
    path = _source_path(root, relative)
    identity = media_signature(path)
    info = probe_sound(path)
    if media_signature(path) != identity:
        raise SoundError("SOUND_SOURCE_CHANGED", "음원이 준비 중 변경되었습니다. 다시 선택하세요.")
    role = next((r for r in ROLES if r.casefold() in [p.casefold() for p in Path(relative).parts[:-1]]), "SFX")
    return {"instance_id": str(uuid5(NAMESPACE_URL, source_uid(root, relative) + "\n" + channel_uuid + "\n" + shot_uuid)),
        "source_uid": source_uid(root, relative), "relative_path": relative, "path": str(path), "media_signature": identity,
        "name": path.stem, "role": role, "purpose": "both" if path.suffix.casefold() in REFERENCE_EXTENSIONS else "mix",
        "transcript": "", "target": "", "in_seconds": 0.0, "out_seconds": None, "start_seconds": 0.0,
        "gain_db": 0.0, "enabled": True, "loop": False, "lipsync": False, **info,
        "channel_uuid": channel_uuid, "shot_uuid": shot_uuid}


def normalize_sound_snapshot(value: Any) -> dict[str, Any]:
    if value is None or value == {} or value == "":
        return {}
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or type(value.get("version")) is not int or value["version"] != VERSION:
        raise SoundError("SOUND_SNAPSHOT_INVALID", "사운드 라이브러리 연결 데이터가 올바르지 않습니다.")
    root_text = _text(value.get("project_root"))
    if not root_text or not Path(root_text).is_absolute():
        raise SoundError("SOUND_PROJECT_INVALID", "사운드 프로젝트 경로가 올바르지 않습니다.")
    root = absolute_path(root_text)
    pid = _text(value.get("project_id"), 256)
    if root.name.casefold() != "ai_ct_audio" or not pid or root.parent.name.casefold() != pid.casefold():
        raise SoundError("SOUND_PROJECT_INVALID", "사운드 프로젝트 식별자가 일치하지 않습니다.")
    uid = _text(value.get("project_uid"), 128)
    try:
        if str(UUID(uid)) != uid:
            raise ValueError()
    except (ValueError, AttributeError):
        raise SoundError("SOUND_PROJECT_INVALID", "사운드 프로젝트 식별자가 올바르지 않습니다.") from None
    channel = _text(value.get("channel_uuid"), 128)
    revision = value.get("revision", 0)
    if type(revision) is not int or revision < 0 or revision > (1 << 53) - 1:
        raise SoundError("SOUND_SNAPSHOT_INVALID", "사운드 갱신 번호가 올바르지 않습니다.")
    tracks = value.get("tracks", [])
    if not isinstance(tracks, list) or len(tracks) > MAX_TRACKS:
        raise SoundError("SOUND_TRACK_LIMIT", "선택한 사운드 트랙 수를 확인하세요.")
    output = []
    seen = set()
    for row in tracks:
        if not isinstance(row, dict):
            raise SoundError("SOUND_SNAPSHOT_INVALID", "사운드 트랙 형식이 올바르지 않습니다.")
        relative = _text(row.get("relative_path"))
        path = relative_audio_path(root, relative)
        identity = "sound:" + hashlib.sha256((uid + "\n" + relative.casefold()).encode("utf-8")).hexdigest()
        signature = _text(row.get("media_signature"), 64)
        instance = _text(row.get("instance_id"), 128)
        row_channel, shot = _text(row.get("channel_uuid"), 128), _text(row.get("shot_uuid"), 128)
        if row.get("source_uid") != identity or not re.fullmatch(r"[a-f0-9]{64}", signature) or not instance or instance in seen:
            raise SoundError("SOUND_SOURCE_IDENTITY_INVALID", "사운드 원본·인스턴스 식별자가 올바르지 않습니다.")
        if (row_channel and row_channel != channel) or bool(row_channel) != bool(shot):
            raise SoundError("SOUND_SHOT_MISMATCH", "사운드의 프로젝트·샷 연결이 일치하지 않습니다.")
        if _text(row.get("path")) and absolute_path(row["path"]) != path:
            raise SoundError("SOUND_SOURCE_OUTSIDE_PROJECT", "사운드 원본 경로가 프로젝트와 일치하지 않습니다.")
        role, purpose = row.get("role", "SFX"), row.get("purpose", "both")
        if role not in ROLES or purpose not in PURPOSES:
            raise SoundError("SOUND_ROLE_INVALID", "사운드 역할·사용 용도를 확인하세요.")
        duration = _number(row.get("duration_seconds"), low=0.000001)
        start = _number(row.get("start_seconds"))
        begin = _number(row.get("in_seconds"))
        end = None if row.get("out_seconds") is None else _number(row.get("out_seconds"))
        if begin >= duration or (end is not None and (end <= begin or end > duration + 0.05)):
            raise SoundError("SOUND_INVALID_TIMING", "사운드 사용 구간이 원본 길이 범위를 벗어났습니다.")
        seen.add(instance)
        output.append({"instance_id": instance, "source_uid": identity, "relative_path": relative, "path": str(path), "media_signature": signature,
            "name": _text(row.get("name"), 512), "role": role, "purpose": purpose, "transcript": _text(row.get("transcript"), 20000, literal=True),
            "target": _text(row.get("target"), 512), "in_seconds": begin, "out_seconds": end, "start_seconds": start,
            "gain_db": _number(row.get("gain_db"), low=-60, high=12), "enabled": _boolean(row.get("enabled"), True),
            "loop": _boolean(row.get("loop"), False), "lipsync": _boolean(row.get("lipsync"), False), "duration_seconds": duration,
            "channel_uuid": row_channel, "shot_uuid": shot})
    preparation_error = value.get("preparation_error", "")
    if preparation_error not in ("", "SOUND_PREPARATION_FAILED"):
        raise SoundError("SOUND_SNAPSHOT_INVALID", "사운드 준비 상태가 올바르지 않습니다.")
    return {"schema": SCHEMA, "version": VERSION, "project_id": pid, "project_root": str(root), "project_uid": uid,
        "channel_uuid": channel, "revision": revision, "tracks": output,
        **({"preparing": True} if _boolean(value.get("preparing"), False) else {}),
        **({"preparation_error": preparation_error} if preparation_error else {})}


def resolve_sound_tracks(snapshot: Any, *, channel_uuid: str = "", shot_uuid: str = "", project_id: str = "") -> list[dict[str, Any]]:
    normalized = normalize_sound_snapshot(snapshot)
    if not normalized:
        return []
    if normalized.get("preparing") is True:
        raise SoundPreparingError()
    if normalized.get("preparation_error"):
        raise SoundError("SOUND_PREPARATION_FAILED", "선택한 사운드 준비에 실패했습니다. 취소하거나 원본을 확인하고 다시 선택하세요.")
    if project_id and normalized["project_id"].casefold() != str(project_id).casefold():
        raise SoundError("SOUND_PROJECT_MISMATCH", "다른 프로젝트의 사운드를 현재 샷에 사용할 수 없습니다.")
    if channel_uuid and normalized["channel_uuid"] != channel_uuid:
        raise SoundError("SOUND_SHOT_MISMATCH", "사운드 라이브러리의 샷 연결을 확인하세요.")
    selected = [row for row in normalized["tracks"] if row["enabled"] and row["channel_uuid"] == channel_uuid and row["shot_uuid"] == shot_uuid]
    if not selected:
        return []
    declared_root = Path(normalized["project_root"])
    _reject_reparse_path(declared_root)
    root = declared_root.resolve()
    if not root.is_dir() or project_uid(root) != normalized["project_uid"]:
        raise SoundError("SOUND_PROJECT_INVALID", "사운드 프로젝트 경로·식별자가 현재 원본과 일치하지 않습니다.")
    for row in selected:
        path = _source_path(declared_root, row["relative_path"])
        if media_signature(path) != row["media_signature"]:
            raise SoundError("SOUND_SOURCE_CHANGED", "선택한 사운드 원본이 변경되었습니다. 사운드를 다시 선택하세요.")
        row["path"] = str(path)
    return copy.deepcopy(selected)


def public_sound_directions(snapshot: Any, *, channel_uuid: str = "", shot_uuid: str = "") -> list[dict[str, Any]]:
    """Public authored intent only: never expose local paths, hashes or policy."""
    normalized = normalize_sound_snapshot(snapshot)
    result, reference_index, mix_index = [], 0, 0
    for row in normalized.get("tracks", []):
        if not row["enabled"] or row["channel_uuid"] != channel_uuid or row["shot_uuid"] != shot_uuid:
            continue
        if row["purpose"] in {"reference", "both"}:
            reference_index += 1
            token = ("@audio" if channel_uuid and shot_uuid else "@sound") + str(reference_index)
        else:
            mix_index += 1
            token = "@mix" + str(mix_index)
        result.append({"audio": token, **{key: row[key] for key in ("name", "role", "purpose", "transcript", "target", "in_seconds", "out_seconds", "start_seconds", "gain_db", "loop", "lipsync")}})
    return result
