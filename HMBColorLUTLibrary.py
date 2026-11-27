from __future__ import annotations

"""Local, post-generation color finishing. Commands never execute upstream nodes."""

import copy
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import contextvars
import json
import hashlib
import logging
import os
import re
import stat
import subprocess
import threading
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit

from _hmb_node_controls import (
    DataNode, _add_parameter, _add_widget_parameter, _hidden_transport_ui_options,
    _hide_transport_parameter, _mode, _normalize_shot_catalog,
    _normalize_shot_selection, _raw_parameter, _set_parameter_silently,
    _shot_only, set_output,
)
from _hmb_color_lut import CODEC_EXTENSIONS, default_settings, normalize_settings, normalize_audio_mix, probe_source, export_video, write_cube
from _hmb_color_lut import UnsupportedGrade, make_mov_preview
from _hmb_deletion_guard import hmb_binding_mutation
from _hmb_project import project_display_name

UI = "HMB_COLOR_LUT_UI_STATE"
COMMAND = "HMB_COLOR_LUT_COMMAND"
SOURCE = "COLOR_LUT_SOURCE_IN"
SOUND_IN = "SOUND_IN"
# Leave room for Griptape's title, flow row and video_url output around the widget.
COLOR_LUT_NODE_WIDTH = 1220
COLOR_LUT_NODE_HEIGHT = 1160
COLOR_LUT_WIDGET_WIDTH = 1120
COLOR_LUT_WIDGET_HEIGHT = 900
COLOR_LUT_NATIVE_GEOMETRY_HINT = "hmb_color_lut_native_initial_geometry"
_COLOR_LUT_NATIVE_FACTORY_REQUEST = "hmb_color_lut_native_factory_request"


def _native_initial_geometry_hint(metadata: Any) -> dict[str, Any] | None:
    """Opt in only for a fresh, prototype-editor placement without authored size.

    The SDK does not forward CreateNodeRequest.initial_setup to constructors.
    Its editor placement paths therefore supply an explicit, transient marker;
    deserialization and duplication never pass through those placement paths.
    Existing size/expanded dimensions and all other authored metadata win.
    """
    if not isinstance(metadata, Mapping) or set(metadata) - {
            "position", "tempId", _COLOR_LUT_NATIVE_FACTORY_REQUEST,
            "library_node_metadata", "library", "node_type"}:
        return None
    if ("library" in metadata and metadata["library"] != "HMB_GP_Production"
            or "node_type" in metadata and metadata["node_type"] != "HMBColorLUTLibrary"):
        return None
    request = metadata.get(_COLOR_LUT_NATIVE_FACTORY_REQUEST)
    temp_id = metadata.get("tempId")
    if (not isinstance(request, Mapping) or request.get("schema") != "hmb-color-lut-native-factory-request-v1"
            or not isinstance(temp_id, str) or not 1 <= len(temp_id) <= 160 or request.get("temp_id") != temp_id):
        return None
    return {"schema": "hmb-color-lut-native-initial-geometry-v1", "version": 1,
            "width": 1225, "height": 1057, "factory_width": COLOR_LUT_NODE_WIDTH,
            "factory_height": COLOR_LUT_NODE_HEIGHT, "token": uuid.uuid4().hex, "status": "pending"}


LOGGER = logging.getLogger("griptape_nodes")
_PROFILE_LOCK = threading.RLock()
_UPLOAD_LOCK = threading.RLock()
_UPLOAD_ACTIVE: set[str] = set()
_USAGE_LOCK = threading.RLock()
_USAGE_ACTIVE: set[str] = set()
COLOR_LUT_UPLOAD_SCHEMA = "hmb-color-lut-upload"
COLOR_LUT_MANUAL_UPLOAD_SCHEMA = "hmb-color-lut-manual-upload"
COLOR_LUT_MANUAL_UPLOAD_PATH = "/api/v1/reviews/color-lut/manual"
_MANUAL_EPISODES_PATH = COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects/{group_id}/{project_id}/episodes"


def _advertised_api_path_matches(value: Any, expected: str, server_url: str) -> bool:
    """Accept the fixed API path with at most this Broker's exact mount prefix.

    Advertised paths are validation evidence only. Requests keep using the
    fixed backend-relative path so the shared Bridge adds the gateway once.
    """
    if type(value) is not str:
        return False
    from _hmb_broker_config import normalize_broker_base_url
    try:
        prefix = urlsplit(normalize_broker_base_url(server_url)).path
    except (TypeError, ValueError):
        return False
    return value == expected or bool(prefix and value == prefix + expected)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _file_digest(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            if cancel is not None and cancel.is_set():
                raise ValueError("Upload cancelled.")
            digest.update(block)
    return digest.hexdigest()


def _upload_receipt_path(identity: str) -> Path:
    if not isinstance(identity, str) or re.fullmatch(r"[a-f0-9]{64}", identity) is None:
        raise ValueError("Invalid Color LUT receipt identity.")
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "HMB_GP_Production" / "color-lut" / "web-uploads" / (identity + ".json")


def _write_upload_receipt(identity: str, value: dict[str, Any]) -> None:
    destination = _upload_receipt_path(identity)
    with _UPLOAD_LOCK:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(uuid.uuid4().hex + ".tmp")
        try:
            temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)


def _read_upload_receipt(identity: str) -> dict[str, Any]:
    try:
        path = _upload_receipt_path(identity)
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _bound_upload_id(context: Mapping[str, Any]) -> str:
    identity = ("hmb-color-lut-upload-v1", context["source_task_id"], context["sha256"],
                context["settings_sha256"], context["shot_uuid"])
    return hashlib.sha256("\n".join(identity).encode("utf-8")).hexdigest()


def _confirmed_publication(context: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    if not context.get("shot_uuid") or context.get("manual") or receipt.get("schema") != COLOR_LUT_UPLOAD_SCHEMA:
        return False
    response, metadata = receipt.get("response"), receipt.get("metadata")
    if not isinstance(response, dict) or not isinstance(metadata, dict):
        return False
    fields = ("source_task_id", "project_id", "project_name", "channel_uuid", "shot_uuid", "sha256", "shot_name")
    return (receipt.get("phase") == "complete" and receipt.get("upload_id") == context["upload_id"]
            and (receipt.get("publication_stamp") == context.get("publication_stamp")
                 if "publication_stamp" in receipt else context.get("legacy_publication_matches_grade") is True)
            and metadata.get("source_revision") == context["source_revision"]
            and metadata.get("settings_sha256") == context["settings_sha256"]
            and metadata.get("export_sha256") == context["sha256"]
            and response.get("schema") == "hmb-color-lut-upload-result" and response.get("version") == 1
            and response.get("display_name") == "HMB Color LUT" and response.get("source_kind") == "HMB Color LUT"
            and bool(response.get("derived_task_id")) and bool(response.get("asset_id"))
            and type(response.get("created")) is bool and response.get("bytes") == context["size"]
            and all(response.get(key) == context[key] for key in fields))


def _upload_bridge(origin: str) -> Any:
    # Use the shared origin-scoped credentials and redirect protections.
    # Opening a Color LUT never starts device login or upstream generation.
    bridge = _usage_bridge(origin)
    if bridge is None:
        raise ValueError("브로커 로그인이 필요합니다. Generator에서 로그인한 뒤 다시 확인하세요.")
    return bridge


def _upload_error_status(error: Exception) -> int | None:
    # HTTPError delegates unknown attributes to its response stream. A closed
    # or absent stream must not turn error reporting into a second failure.
    for name in ("code", "status_code"):
        try:
            value = getattr(error, name, None)
        except (AttributeError, KeyError, TypeError):
            continue
        if type(value) is int:
            return value
    return None


def _upload_failure_summary(error: Exception) -> str:
    """Explain the observed failure without exposing credentials or raw responses."""
    # The Broker wraps HTTP transport and missing-token failures in its own
    # exception types; inspect types/status only, never exception text.
    try:
        from _hmb_broker_transport import _BrokerAuthenticationError, _BrokerUnavailableError
    except ImportError:
        _BrokerAuthenticationError = _BrokerUnavailableError = ()
    code = _upload_error_status(error)
    if vars(error).get("lut_error_code") == "color_lut_storage_unavailable":
        return f"브로커가 업로드 저장소를 사용할 수 없습니다 (HTTP {code})."
    prefix = ("브로커 로그인이 만료되었습니다. 다시 로그인하세요. " if code == 401 else
              "브로커 로그인이 필요합니다. 로그인한 뒤 다시 확인하세요. " if isinstance(error, _BrokerAuthenticationError) else
              "브로커가 업로드 권한을 거부했습니다 (HTTP 403). " if code == 403 else
              f"브로커 서버 오류가 발생했습니다 (HTTP {code}). " if type(code) is int and 500 <= code <= 599 else
              f"브로커가 업로드 요청을 거부했습니다 (HTTP {code}). " if type(code) is int and 400 <= code <= 499 else
              "브로커 연결이 끊겼거나 응답 시간이 초과되었습니다. "
              if isinstance(error, (TimeoutError, ConnectionError, URLError)) or isinstance(error, _BrokerUnavailableError) else "")
    return prefix.strip()


def _unknown_upload_reason(error: Exception) -> str:
    return " ".join(filter(None, (_upload_failure_summary(error), _UPLOAD_PENDING_REASON)))


_UPLOAD_ABSENT_REASON = "완료된 업로드 기록을 찾지 못했습니다. 다시 업로드를 누르면 같은 ID로 전송합니다."
_UPLOAD_PENDING_REASON = "이전 업로드의 완료 여부를 확인하세요. 상태 확인은 파일을 전송하지 않습니다."
_GROUP_READ_ONLY_NOTICE = "이 그룹은 조회 전용입니다. 업로드하려면 로그인 계정의 소속 그룹 또는 My Box를 선택하세요."


def _upload_broker_offline(error: Exception) -> bool:
    try:
        from _hmb_broker_transport import _BrokerUnavailableError
    except ImportError:
        _BrokerUnavailableError = ()
    code = _upload_error_status(error)
    return isinstance(error, (TimeoutError, ConnectionError, URLError)) or isinstance(error, _BrokerUnavailableError) or (
        type(code) is int and 500 <= code <= 599)


def _usage_bridge(origin: str) -> Any:
    """Use an existing login only; optional statistics never change that login."""
    from _hmb_broker_transport import _HMBAIBrokerBridge, _broker_load_token
    bridge = _HMBAIBrokerBridge(server_url=origin)
    token = _broker_load_token(server_url=bridge.server_url)
    if not token:
        return None
    # A queued observation stays with the same authentication identity even
    # if another operation changes the active login. No token is persisted here.
    bridge._load_access_token = lambda: token
    bridge._clear_access_token = lambda: None
    return bridge


def _usage_record_path(identity: str) -> Path:
    if re.fullmatch(r"[a-f0-9]{64}", identity) is None:
        raise ValueError("Invalid LUT usage identity.")
    return _profiles_path().parent / "usage-events" / (identity + ".json")


def _write_usage_record(identity: str, value: dict[str, Any]) -> None:
    destination = _usage_record_path(identity)
    _validate_profiles_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_profiles_path(destination)
    temporary = destination.with_name(uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_profiles_path(destination)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _read_usage_record(identity: str) -> dict[str, Any]:
    path = _usage_record_path(identity)
    _validate_profiles_path(path)
    try:
        if path.stat().st_size > 16384:
            raise ValueError("Invalid LUT usage receipt.")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Invalid LUT usage receipt.")
    return value


def _verified_export_hash(path: Path, cancel: threading.Event) -> dict[str, Any]:
    """One bounded streaming read, tied to the verified output file identity."""
    def identity(info: Any) -> tuple[Any, ...]:
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise ValueError("Verified export is unavailable.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("Export identity changed.")
        remaining = before.st_size
        while remaining:
            if cancel.is_set():
                raise ValueError("Export observation cancelled.")
            block = stream.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("Export identity changed.")
            digest.update(block)
            remaining -= len(block)
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("Export identity changed.")
    if cancel.is_set() or identity(path.stat()) != identity(before):
        raise ValueError("Export identity changed.")
    return {"sha256": digest.hexdigest(), "size": before.st_size, "mtime_ns": before.st_mtime_ns,
            "device": before.st_dev, "inode": before.st_ino}


def _profiles_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "HMB_GP_Production" / "color-lut" / "personal-presets.json"


def _profiles(value: Any = None) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    ids = Counter(_profile_id(p.get("id")) for p in rows if isinstance(p, Mapping))
    return [{"id": _profile_id(p.get("id")), "name": str(p["name"])[:80],
             "project_id": str(p.get("project_id") or ""), "settings": normalize_settings(p.get("settings")),
             "deletable": _profile_deletable(p) and ids[_profile_id(p.get("id"))] == 1}
            for p in rows if isinstance(p, Mapping) and p.get("name")]


def _profile_id(value: Any) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else ""


def _profile_deletable(row: Mapping[str, Any], *, allow_missing_id: bool = False) -> bool:
    # This file is the current OS user's personal store. Older locally authored
    # rows have no scope metadata; imported/protected rows must not gain rights
    # merely because the UI projects only their name and settings.
    missing_id = row.get("id") in (None, "")
    if ((not _profile_id(row.get("id")) and not (allow_missing_id and missing_id))
            or not isinstance(row.get("name"), str)
            or not row["name"] or len(row["name"]) > 80
            or not isinstance(row.get("project_id", ""), str)):
        return False
    metadata = row.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        return False
    for fields in (row, metadata or {}):
        for flag in ("readonly", "read_only", "readOnly", "protected", "is_default", "default", "system", "is_system", "shared", "is_shared", "builtin", "built_in"):
            if fields.get(flag) not in (None, False, ""):
                return False
        if ("deletable" in fields and fields["deletable"] is not True
                or "user_created" in fields and fields["user_created"] is not True):
            return False
        if any(fields.get(key) not in (None, "") for key in ("owner", "owner_id", "owner_user_id", "user_id")):
            return False  # No cross-account ownership system is inferred locally.
        if any(key in fields and fields[key] not in ("local_user", "personal", "user") for key in ("scope", "source")):
            return False
    return True


def _validate_profiles_path(destination: Path) -> None:
    if not destination.is_absolute():
        raise ValueError("Personal preset storage must be a local absolute path.")
    for path in (destination, *destination.parents):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Personal preset storage cannot use a symbolic link or reparse point.")


def _read_profile_rows() -> list[Any]:
    destination = _profiles_path()
    _validate_profiles_path(destination)
    try:
        rows = json.loads(destination.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(rows, list):
        raise ValueError("Personal preset storage is invalid; no presets were changed.")
    return rows


def _write_profile_rows(rows: list[Any]) -> None:
    destination = _profiles_path()
    _validate_profiles_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _validate_profiles_path(destination)
    temp = destination.with_name(f".{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with temp.open("x", encoding="utf-8") as stream:
            created = True
            json.dump(rows, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_profiles_path(destination)
        os.replace(temp, destination)
    finally:
        if created:
            temp.unlink(missing_ok=True)


def _read_profiles() -> list[dict[str, Any]]:
    try:
        with _PROFILE_LOCK:
            return _profiles(_read_profile_rows())
    except (OSError, ValueError):
        return _profiles()


def default_state() -> dict[str, Any]:
    return {"schema_version": 1, "revision": 0, "language": "ko", "shot": _shot_only(),
            "shot_catalog": {}, "project_id": "", "project": {}, "manual_project": {}, "manual_episode": "",
            "manual_group_id": "", "manual_group_owner": "", "preset_name": "", "preset_id": "", "profiles": _read_profiles(),
            "settings": default_settings(), "audio_mix": normalize_audio_mix({}), "sound": {"connected": False, "revision": ""}, "source": {}, "output": {
                "codec": "hevc10", "manual_output_enabled": False, "path": ""},
            "status": {"phase": "idle", "message": "", "progress": 0}, "result": {}, "shot_states": {}}


def _selection_key(state: Mapping[str, Any]) -> str:
    shot = state.get("shot") if isinstance(state.get("shot"), Mapping) else {}
    return json.dumps([state.get("project_id", ""), shot.get("channel_uuid", ""), shot.get("shot_uuid", "")], ensure_ascii=False)


def _export_selection(state: Mapping[str, Any]) -> str:
    # A manual export's pixels do not change when its upload destination changes.
    return _selection_key(state) if state.get("shot", {}).get("shot_uuid") else "manual"


def _audio_mix_identity(state: Mapping[str, Any]) -> dict[str, Any]:
    settings = normalize_audio_mix(state.get("audio_mix"))
    return {**settings, "sound_revision": str(state.get("sound", {}).get("revision") or "")} if settings["enabled"] else settings


def _episode_code(value: Any) -> str:
    code = str(value or "").strip().lower()
    return code if re.fullmatch(r"e[0-9]{3}", code) and code != "e000" else ""


def _episode_filename(name: str, episode: str) -> str:
    if not episode:
        return name
    if re.match(r"^e[0-9]{3}(?![0-9])", name, re.IGNORECASE):
        return episode + name[4:]
    suffix = Path(name).suffix
    prefix = episode + "_"
    return prefix + name[:-len(suffix)][:128 - len(prefix) - len(suffix)] + suffix


def _upload_project(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    identity, name = value.get("project_id", value.get("id")), value.get("project_name", value.get("name"))
    if (not isinstance(identity, str) or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}", identity) is None
            or not isinstance(name, str) or not name.strip() or len(name) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        return {}
    return {"id": identity, "name": name}


def _writable_upload_groups(rows, projects):
    """Validate the authenticated manual-upload destinations, including their project assignments."""
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("서버의 업로드 가능 그룹 목록을 확인하세요.")
    allowed_projects = {p["id"] for p in projects if p["id"] != "my-box"}
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("서버의 업로드 가능 그룹 정보를 확인하세요.")
        key, name, ids = row.get("id"), row.get("name"), row.get("project_ids")
        if (not isinstance(key, str) or not re.fullmatch(r"grp-[a-f0-9]{32}", key) or key in result
                or not isinstance(name, str) or not 1 <= len(name.strip()) <= 64
                or not isinstance(ids, list) or any(not isinstance(p, str) for p in ids)):
            raise ValueError("서버의 업로드 가능 그룹 정보를 확인하세요.")
        result[key] = {"id": key, "name": name, "project_ids": allowed_projects.intersection(ids)}
    return result


def _upload_company_scope(bridge: Any, capabilities: Mapping[str, Any], me=None):
    """Read the same membership and project assignments as the operating page."""
    if capabilities.get("company_groups_supported") is not True:
        return "legacy", {}, {}, False
    try:
        catalog = bridge._request_json("GET", "/api/company-groups", payload=None, timeout=5)
    except Exception as exc:
        status = _upload_error_status(exc)
        if not (status in {429, 500, 502, 503, 504} or status is None and _upload_broker_offline(exc)):
            raise
        # An unavailable list of display names must not change the write scope.
        user = me if me is not None else bridge._request_json("GET", "/api/me", payload=None, timeout=5)
        identity = user.get("company_group_id")
        if "company_group_id" in user and identity is None:
            return "unassigned", {"id": "ungrouped", "name": ""}, {}, False
        if isinstance(identity, str) and re.fullmatch(r"grp-[0-9a-f]{32}", identity):
            return "confirmed", {"id": identity, "name": ""}, {}, False
        raise ValueError("서버에서 소속 그룹을 확인할 수 없습니다.") from exc
    member = catalog.get("membership")
    groups = catalog.get("items")
    if (catalog.get("schema") != "hmb-company-groups-v1" or not isinstance(member, dict)
            or member.get("enabled") is not True or "group_id" not in member
            or not isinstance(groups, list) or len(groups) > 1000):
        raise ValueError("서버에서 소속 그룹을 확인할 수 없습니다.")
    identity = member["group_id"]
    if me is not None and ("company_group_id" not in me or me["company_group_id"] != identity):
        raise ValueError("서버의 소속 그룹이 변경되었습니다.")
    selectable = catalog.get("can_view_all") is True
    available = {}
    if selectable or identity is None:
        available["ungrouped"] = {"id": "ungrouped", "name": "", "project_ids": None}
    for row in groups:
        if not isinstance(row, dict):
            raise ValueError("서버 그룹 목록을 확인할 수 없습니다.")
        key, name, projects = row.get("id"), row.get("name"), row.get("project_ids")
        if not selectable and key != identity:
            continue
        if (not isinstance(key, str) or not re.fullmatch(r"grp-[0-9a-f]{32}", key) or key in available
                or not isinstance(name, str) or not 0 < len(name.strip()) <= 64
                or not isinstance(projects, list) or any(not isinstance(p, str) for p in projects)):
            raise ValueError("서버 그룹 목록을 확인할 수 없습니다.")
        available[key] = {"id": key, "name": name, "project_ids": frozenset(projects)}
    own = available.get(identity if identity is not None else "ungrouped")
    if not own:
        raise ValueError("서버에서 소속 그룹을 확인할 수 없습니다.")
    return "unassigned" if identity is None else "confirmed", {"id": own["id"], "name": own["name"]}, available, selectable


def _source_identity(source: Any) -> tuple[str, str, str]:
    source = source if isinstance(source, Mapping) else {}
    # Probing resolves short Windows paths and aliases. Retain the received
    # reference for identity instead of treating that resolution as a new video.
    return (str(source.get("_reference_path") or source.get("path") or ""), str(source.get("generation_id") or source.get("task_id") or ""),
            str(source.get("result_revision") or source.get("revision") or ""))


def _output(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return {"codec": raw.get("codec") if isinstance(raw.get("codec"), str) and raw.get("codec") in CODEC_EXTENSIONS else "hevc10",
            "manual_output_enabled": raw.get("manual_output_enabled") is True, "path": str(raw.get("path") or "")}


def _media_url(path: Path) -> str:
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    base = str(GriptapeNodes.StaticFilesManager().static_server_base_url).rstrip("/")
    raw = str(path.resolve())
    external = raw if raw.startswith("\\\\") else raw.replace("\\", "/").lstrip("/")
    return f"{base}/external/{quote(external, safe='/:')}?v={path.stat().st_mtime_ns}"


def _browse() -> str:
    # A dedicated native dialog process avoids Tk cross-thread ownership in the host.
    if os.name == "nt":
        script = "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='Video|*.mp4;*.mov;*.mkv;*.avi;*.webm'; if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; [Console]::Write($d.FileName)}"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                                encoding="utf-8-sig", timeout=600, creationflags=0x08000000)
        if result.returncode:
            raise RuntimeError("Could not open the video file browser.")
        return result.stdout.strip()
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    try:
        return str(filedialog.askopenfilename(parent=root, filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm")]) or "")
    finally:
        root.destroy()


def _workflow_data_directory() -> Path:
    """Use the current workflow's actual save folder, never the media folder."""
    from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
    from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
    workspace = Path(GriptapeNodes.ConfigManager().workspace_path)
    context = GriptapeNodes.ContextManager()
    if context.has_current_workflow():
        workflow = WorkflowRegistry.get_workflow_by_name(context.get_current_workflow_name())
        if workflow.file_path:
            path = Path(workflow.file_path)
            return (path if path.is_absolute() else workspace / path).resolve().parent / "data"
    # A new unsaved canvas has no file yet; use Griptape's configured save root.
    return workspace.resolve() / "data"


class HMBColorLUTLibrary(DataNode):
    def __init__(self, **kwargs: Any) -> None:
        native_geometry_hint = _native_initial_geometry_hint(kwargs.get("metadata"))
        if isinstance(kwargs.get("metadata"), Mapping) and _COLOR_LUT_NATIVE_FACTORY_REQUEST in kwargs["metadata"]:
            kwargs = {**kwargs, "metadata": {key: value for key, value in kwargs["metadata"].items()
                                            if key != _COLOR_LUT_NATIVE_FACTORY_REQUEST}}
        super().__init__(**kwargs)
        # Use the native initial-size contract once. Saved/manual sizes remain
        # authoritative and updates, shot binding and reset must not resize them.
        initial_size_setter = getattr(self, "set_initial_node_size", None)
        if callable(initial_size_setter):
            initial_size_setter(width=COLOR_LUT_NODE_WIDTH, height=COLOR_LUT_NODE_HEIGHT)
        else:
            self.metadata = dict(getattr(self, "metadata", None) or kwargs.get("metadata") or {})
            self.metadata.setdefault("size", {"width": COLOR_LUT_NODE_WIDTH, "height": COLOR_LUT_NODE_HEIGHT})
        if native_geometry_hint is not None:
            self.metadata[COLOR_LUT_NATIVE_GEOMETRY_HINT] = native_geometry_hint
        elif isinstance(self.metadata.get(COLOR_LUT_NATIVE_GEOMETRY_HINT), Mapping):
            prior_hint = self.metadata[COLOR_LUT_NATIVE_GEOMETRY_HINT]
            if prior_hint.get("status") == "pending":
                # Even a workflow saved before the editor's acknowledgement is
                # state to restore, never permission to resize on reopening.
                self.metadata[COLOR_LUT_NATIVE_GEOMETRY_HINT] = {**prior_hint, "status": "restored"}
        self.category = "HMB_GP_Production"
        self.description = "Local SDR color preview, project LUT, final export and explicit project web upload."
        self._lock = threading.RLock()
        # BaseNode._state is Griptape's NodeResolutionState, not dashboard data.
        # Keep our state namespaced across registration, invalidation and reset.
        self._hmb_color_lut_state = default_state()
        self._sound_snapshot: dict[str, Any] = {}
        self._syncing = False
        self._hydrated = False
        self._project_authoritative = False
        self._bound_project: dict[str, Any] = {}
        self._manual_projects: list[dict[str, str]] = []
        self._manual_projects_origin = ""
        self._upload_group: dict[str, str] = {}
        self._upload_group_status = ""
        self._member_group_id = ""
        self._group_catalog = {}
        self._all_manual_projects = []
        self._group_selectable = False
        self._explicit_upload_groups = False
        self._group_owner = ""
        self._catalog_generation = 0
        self._manual_projects_worker: threading.Thread | None = None
        self._manual_projects_checked = 0.0
        self._projects_notice = ""
        self._episode_worker: threading.Thread | None = None
        self._episode_key: tuple[str, str, str] | None = None
        self._episode_codes: list[str] = []
        self._episode_cache: dict[tuple[str, str, str], tuple[float, list[str]]] = {}
        self._episode_prefetch: list[str] = []
        self._episodes_checked = 0.0
        self._episodes_status = ""
        self._hmb_node_deleted = False
        self._hmb_initial_shot_autoclaim_pending = True
        self._hmb_initial_shot_preferred_uuid = ""
        self._seen_commands: list[str] = []
        self._source_token = 0
        self._pending_source_key: tuple[Any, ...] | None = None
        self._source_pending: tuple[Any, ...] | None = None
        self._restoring_source: dict[str, Any] = {}
        self._source_worker: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._job_id = ""
        self._web_upload: dict[str, Any] = {"enabled": False, "phase": "unavailable", "reason": "영상과 업로드할 프로젝트를 선택하세요."}
        self._upload_source_facts: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._web_upload_context: dict[str, Any] = {}
        self._web_upload_worker: threading.Thread | None = None
        self._web_upload_probe: threading.Thread | None = None
        self._web_upload_probe_key = ""
        self._web_node_id = uuid.uuid4().hex
        self._web_upload_epoch = 0
        self._web_upload_pending: dict[str, Any] | None = None
        self._web_upload_wake = threading.Event()
        self._setup_parameters()
        self._publish()
        try:
            from _hmb_shot_routing import schedule_post_registration_reconcile
            schedule_post_registration_reconcile(self)
        except Exception:
            LOGGER.debug("Color LUT registration deferred", exc_info=True)

    def _setup_parameters(self) -> None:
        _add_widget_parameter(self, widget_name="HMBColorLUTLibraryWidget", name=UI, default_value=self._hmb_color_lut_state,
            type="dict", input_types=["dict"], allow_input=False, allow_output=False, allow_property=True,
            allowed_modes=_mode("PROPERTY"), ui_options={"display_name": "HMB Color LUT", "is_full_width": True,
                "width": COLOR_LUT_WIDGET_WIDTH, "height": COLOR_LUT_WIDGET_HEIGHT, "min_width": 760, "min_height": 640,
                "expandable": True, "resizable": True, "compact": False, "hide": False, "hide_property": False})
        for name, kind, default, modes in ((COMMAND, "str", "", ("PROPERTY",)), (SOURCE, "dict", {}, ("INPUT",))):
            parameter = _add_parameter(self, name=name, type=kind, default_value=default, input_types=[kind],
                allow_input="INPUT" in modes, allow_output=False, allow_property="PROPERTY" in modes,
                allowed_modes=_mode(*modes), ui_options=_hidden_transport_ui_options())
            _hide_transport_parameter(parameter)
        _add_parameter(self, name=SOUND_IN, type="dict", default_value={}, input_types=["dict"],
            allow_input=True, allow_output=False, allow_property=False, allowed_modes=_mode("INPUT"),
            ui_options={"display_name": "Sound Library", "hide_property": True, "hide": False, "hide_handles": False})
        _add_parameter(self, name="video_url", type="str", default_value="", output_type="str",
            allow_input=False, allow_output=True, allow_property=False, allowed_modes=_mode("OUTPUT"),
            ui_options={"display_name": "video_url"})

    def _publish(self) -> None:
        if self._hmb_node_deleted:
            return
        with self._lock:
            self._syncing = True
            try:
                state = copy.deepcopy(self._hmb_color_lut_state)
                state["web_upload"] = self._upload_projection()
                project = state["project"]
                state["project_display_name"] = project_display_name(project.get("id"), project.get("name"))
                manual = state["manual_project"]
                state["upload_group"] = dict(self._upload_group)
                state["upload_group_status"] = self._upload_group_status
                state["upload_groups"] = [{"id": row["id"], "name": row["name"]} for row in self._group_catalog.values()]
                state["upload_group_selectable"] = self._group_selectable and not state["shot"].get("shot_uuid")
                state["upload_destination_readonly"] = self._read_only_group(state)
                if state["shot"].get("shot_uuid"):
                    # Bound results may live on a different broker to manual uploads.
                    context = self._web_upload_context
                    state["upload_group"] = dict(context.get("upload_group", {}))
                    state["upload_group_status"] = context.get("upload_group_status", "")
                state["upload_projects_notice"] = self._projects_notice
                episode_key = (self._manual_projects_origin, self._upload_group.get("id", ""), manual.get("id"))
                state["upload_episodes"] = list(self._episode_codes) if self._episode_key == episode_key else []
                state["upload_episodes_status"] = self._episodes_status if self._episode_key == episode_key else ""
                state["manual_project_display_name"] = project_display_name(manual.get("id"), manual.get("name"))
                state["upload_projects"] = [
                    {**row, "display_name": project_display_name(row["id"], row["name"])}
                    for row in self._manual_projects
                ]
                state["_web_node_id"] = self._web_node_id
                _set_parameter_silently(self, UI, state)
                publisher = getattr(self, "publish_update_to_parameter", None)
                if callable(publisher):
                    publisher(UI, state)
            finally:
                self._syncing = False

    def _upload_state_stamp(self, state: Mapping[str, Any]) -> str:
        """Small local invalidation key; no graph/network/hash work on a UI edit."""
        result = state.get("result") if isinstance(state.get("result"), Mapping) else {}
        return _digest([_selection_key(state), _source_identity(state.get("source")),
                        normalize_settings(state.get("settings")), _audio_mix_identity(state), result.get("path"), result.get("job_id"),
                        (state.get("manual_group_id"), state.get("manual_group_owner"), state.get("manual_episode"))
                        if not state["shot"].get("shot_uuid") else ""])

    def _receive_sound(self, value: Any, *, publish: bool = True) -> None:
        # The published digest is UI/proof invalidation only. Execution reads the
        # registered source object and never accepts a browser's track list.
        snapshot = copy.deepcopy(value) if isinstance(value, Mapping) else {}
        digest = _digest(snapshot) if snapshot else ""
        with self._lock:
            if self._sound_snapshot == snapshot:
                return
            old_audio = _audio_mix_identity(self._hmb_color_lut_state)
            self._sound_snapshot = snapshot
            self._hmb_color_lut_state["sound"] = {"connected": bool(snapshot), "revision": digest}
            self._hmb_color_lut_state["revision"] += 1
            refresh_upload = old_audio != _audio_mix_identity(self._hmb_color_lut_state)
        if refresh_upload:
            # A previous readiness worker may already have exited. Schedule the
            # new read rather than just waking the old worker.
            self._schedule_upload_probe()
        if publish:
            self._publish()

    def _capture_sound_snapshot(self, state: Mapping[str, Any]) -> dict[str, Any]:
        from _hmb_shot_routing import _same_flow_nodes, _incoming_connections
        import inspect
        from _hmb_sound import normalize_sound_snapshot
        flow, nodes = _same_flow_nodes(self)
        edges = [edge for edge in _incoming_connections(self) if edge.target_parameter_name == SOUND_IN
                 and edge.source_parameter_name in {"SOUND_OUT", "SHOT_SOUND_OUT"}]
        if not flow or self not in nodes or len(edges) != 1:
            raise ValueError("Audio Mix requires one connected Sound Library output.")
        sources = [node for node in nodes if str(getattr(node, "name", "")) == edges[0].source_node_name]
        if len(sources) != 1:
            raise ValueError("The Sound Library connection is no longer available.")
        source = sources[0]
        metadata = getattr(source, "metadata", {}) or {}
        try:
            source_file = Path(inspect.getfile(type(source))).resolve()
        except (TypeError, OSError):
            source_file = None
        if (type(source).__name__ != "HMBSoundLibrary" or source_file != Path(__file__).with_name("HMBSoundLibrary.py").resolve()
                or metadata.get("library") != "HMB_GP_Production" or metadata.get("node_type") != "HMBSoundLibrary"
                or getattr(source, "_hmb_node_deleted", False) or not callable(getattr(source, "_hmb_sound_snapshot_for", None))):
            raise ValueError("The Sound Library connection is no longer available.")
        shot = state["shot"]
        snapshot = normalize_sound_snapshot(source._hmb_sound_snapshot_for(
            channel_uuid=shot.get("channel_uuid", ""), shot_uuid=shot.get("shot_uuid", "")))
        if not snapshot:
            raise ValueError("The selected Shot has no valid Sound Library snapshot.")
        project_root = str(state.get("project", {}).get("root") or "")
        if shot.get("shot_uuid") and project_root:
            image_root = Path(project_root)
            if image_root.name.casefold() != "ai_ct_image" or snapshot["project_id"].casefold() != image_root.parent.name.casefold():
                raise ValueError("The Sound Library project does not match this Shot's image project.")
        # Reject stale UI state before capture; a delayed click must not silently
        # export newly selected sounds under its older visible configuration.
        expected = str(state.get("sound", {}).get("revision") or "")
        received = normalize_sound_snapshot(self._sound_snapshot) if self._sound_snapshot else {}
        if expected and expected != _digest(self._sound_snapshot):
            raise ValueError("Sound selection changed; review the current sounds before exporting.")
        if received and _digest(snapshot) != _digest(received):
            raise ValueError("Sound Library selection is still updating. Try again after it is ready.")
        plan_source = normalize_audio_mix(state.get("audio_mix"))["source"]
        if plan_source == "rendered" and not shot.get("shot_uuid"):
            raise ValueError("생성 당시 사운드는 완료된 Generator 샷 연결이 필요합니다. 현재 샷 사운드를 선택하세요.")
        if shot.get("shot_uuid"):
            effective = self._bound_sound_contract(state, nodes, source) if plan_source == "rendered" else self._current_shot_sound_contract(state, nodes, source)
            if effective is not None:
                snapshot = normalize_sound_snapshot(effective)
                if (snapshot and (snapshot.get("channel_uuid") != shot["channel_uuid"]
                        or snapshot.get("project_id", "").casefold() != str(source._hmb_sound_snapshot_for()["project_id"]).casefold())):
                    raise ValueError("The finishing sound contract belongs to another Shot project.")
        return copy.deepcopy(snapshot)

    def _current_shot_sound_contract(self, state: Mapping[str, Any], nodes: list[Any], sound_source: Any) -> dict[str, Any] | None:
        """Explicit finishing uses current exact-Shot Prompt edits when present."""
        import inspect
        from _hmb_sound import SoundError, normalize_sound_snapshot
        shot, candidates = state["shot"], []
        base = normalize_sound_snapshot(sound_source._hmb_sound_snapshot_for(channel_uuid=shot["channel_uuid"], shot_uuid=shot["shot_uuid"]))
        base_sources = {row["instance_id"]: tuple(row.get(key) for key in ("source_uid", "path", "media_signature", "channel_uuid", "shot_uuid")) for row in base.get("tracks", [])}
        for node in nodes:
            metadata = getattr(node, "metadata", {}) or {}
            if (type(node).__name__ != "HMBPromptLibrary" or metadata.get("library") != "HMB_GP_Production"
                    or metadata.get("node_type") != "HMBPromptLibrary" or getattr(node, "_hmb_node_deleted", False)):
                continue
            try:
                if Path(inspect.getfile(type(node))).resolve() != Path(__file__).with_name("HMBPromptLibrary.py").resolve():
                    continue
            except (TypeError, OSError):
                continue
            source_getter = getattr(node, "_registered_sound_source", None)
            getter = getattr(node, "_hmb_sound_snapshot_for", None)
            if not callable(source_getter) or not callable(getter) or source_getter() is not sound_source:
                continue
            try:
                candidate = normalize_sound_snapshot(getter(channel_uuid=shot["channel_uuid"], shot_uuid=shot["shot_uuid"]))
            except SoundError as exc:
                if exc.code == "SOUND_SHOT_MISMATCH":
                    continue
                raise
            if {row["instance_id"]: tuple(row.get(key) for key in ("source_uid", "path", "media_signature", "channel_uuid", "shot_uuid")) for row in candidate.get("tracks", [])} != base_sources:
                raise ValueError("Prompt sound direction no longer matches the connected Sound originals.")
            candidates.append(candidate)
        if len(candidates) > 1:
            raise ValueError("More than one Prompt owns sound direction for this Shot. Keep one exact Prompt binding.")
        return copy.deepcopy(candidates[0]) if candidates else None

    def _bound_sound_contract(self, state: Mapping[str, Any], nodes: list[Any], sound_source: Any) -> dict[str, Any]:
        """Read only the completed video's plan, never today's mutable Prompt."""
        from _hmb_shot_routing import _incoming_connections
        import inspect
        def actual(node: Any, kind: str) -> bool:
            metadata = getattr(node, "metadata", {}) or {}
            try:
                path = Path(inspect.getfile(type(node))).resolve()
            except (TypeError, OSError):
                return False
            return (type(node).__name__ == kind and path == Path(__file__).with_name(kind + ".py").resolve()
                and metadata.get("library") == "HMB_GP_Production" and metadata.get("node_type") == kind
                and not getattr(node, "_hmb_node_deleted", False))
        shot, src = state["shot"], state["source"]
        edges = [edge for edge in _incoming_connections(self) if edge.target_parameter_name == SOURCE]
        if not edges:
            raise ValueError("Shot Audio Mix requires the exact completed Generator video connection.")
        if edges:
            if len(edges) != 1 or edges[0].source_parameter_name != "HMB_GENERATED_VIDEO_SOURCE":
                raise ValueError("The finishing video requires its exact completed Generator source.")
            matches = [node for node in nodes if str(getattr(node, "name", "")) == edges[0].source_node_name]
            if len(matches) != 1 or not actual(matches[0], "HMBSeedanceGeneration"):
                raise ValueError("The finishing Generator is no longer available.")
            generator = matches[0]
            current = generator._hmb_generated_video_source_snapshot()
            required = ("channel_uuid", "shot_uuid", "generation_id", "result_revision", "source_node_instance_id")
            if (not isinstance(current, dict) or current.get("completed") is not True
                    or not src.get("generation_id") or _source_identity(current) != _source_identity(src)
                    or any(current.get(key) != src.get(key) for key in required)
                    or (current.get("channel_uuid"), current.get("shot_uuid")) != (shot["channel_uuid"], shot["shot_uuid"])):
                raise ValueError("The finishing video and captured Generator job no longer match.")
            getter = getattr(generator, "_hmb_sound_finishing_snapshot", None)
            captured = getter() if callable(getter) else {}
            if captured:
                origin = captured.get("origin") or {}
                if (captured.get("generation_id") != src["generation_id"]
                        or any(origin.get(key) != shot.get(key) for key in ("channel_uuid", "shot_uuid"))):
                    raise ValueError("The completed video's sound contract belongs to a different job or Shot.")
                if isinstance(captured.get("snapshot"), dict) and captured["snapshot"]:
                    return copy.deepcopy(captured["snapshot"])
        raise ValueError("이 완료 영상에는 생성 당시 사운드 기록이 없습니다. 현재 샷 사운드를 선택하세요.")

    def _upload_projection(self) -> dict[str, Any]:
        view = copy.deepcopy(self._web_upload)
        context = self._web_upload_context
        current = self._hmb_color_lut_state
        if self._read_only_group(current):
            return {"enabled": False, "phase": "unavailable", "reason": _GROUP_READ_ONLY_NOTICE}
        if not current["shot"].get("shot_uuid") and not _upload_project(current.get("manual_project")):
            return {"enabled": False, "phase": "unavailable", "reason": "업로드할 프로젝트를 선택하세요."}
        if context.get("state_stamp") != self._upload_state_stamp(current):
            return {"enabled": False, "phase": "unavailable", "reason": "현재 영상의 업로드 연결을 확인하는 중입니다."}
        if (context.get("source_token") != self._source_token or context.get("route_epoch") != self._web_upload_epoch
                or getattr(context.get("generator"), "_hmb_node_deleted", False)
                or getattr(context.get("asset"), "_hmb_node_deleted", False)):
            return {"enabled": False, "phase": "unavailable", "reason": "원본 샷 연결이 변경되었습니다."}
        if self._hmb_node_deleted:
            view["enabled"] = False
        if (context.get("publication_stamp") != _digest([context.get("state_stamp"), _output(current["output"])])
                or current["status"].get("phase") not in ("idle", "complete")):
            view.pop("published_shot", None)
        if context.get("manual"):
            from _hmb_broker_config import load_broker_base_url
            try:
                same_origin = context.get("server_url") == load_broker_base_url()
            except ValueError:
                same_origin = False
            if not same_origin:
                return {"enabled": False, "phase": "unavailable", "reason": "브로커 주소가 변경되었습니다. 프로젝트를 다시 확인하세요."}
        return view

    def _read_only_group(self, state):
        selected = state.get("manual_group_id")
        if self._explicit_upload_groups:
            return bool(selected and not state["shot"].get("shot_uuid") and state["manual_project"].get("id") != "my-box"
                        and (selected not in self._group_catalog or state.get("manual_group_owner") != self._group_owner))
        return bool(not state["shot"].get("shot_uuid") and state["manual_project"].get("id") != "my-box"
                    and selected and (selected != self._member_group_id or not self._group_owner))

    def _apply_group_view(self, member_group, status):
        state = self._hmb_color_lut_state
        selected = state.get("manual_group_id") or self._member_group_id
        row = self._group_catalog.get(selected)
        if row:
            self._upload_group = {"id": selected, "name": row["name"]}
            self._upload_group_status = "unassigned" if selected == "ungrouped" else "confirmed"
            projects = row["project_ids"]
        elif selected == self._member_group_id and not self._explicit_upload_groups:
            self._upload_group, self._upload_group_status = dict(member_group), status
            projects = None
        else:
            self._upload_group, self._upload_group_status = {}, "unavailable"
            projects = ()
        self._manual_projects = [p for p in self._all_manual_projects
                                 if p["id"] == "my-box" or projects is None or p["id"] in projects]
        self._episode_prefetch = [p["id"] for p in self._manual_projects if p["id"] != "my-box"]

    def _schedule_manual_projects(self, *, force: bool = False) -> None:
        """Authenticated advisory reads off the editor thread; never log in or upload."""
        with self._lock:
            if self._hmb_node_deleted or self._manual_projects_worker is not None and self._manual_projects_worker.is_alive():
                return
            if not force and time.monotonic() - self._manual_projects_checked < (30 if self._manual_projects and not self._projects_notice else 2):
                return
            self._manual_projects_checked = time.monotonic()
        def load() -> None:
            origin, projects, notice = "", [], "unavailable"
            group_status, group = "unavailable", {}
            available, selectable, owner = {}, False, ""
            explicit = False
            try:
                from _hmb_broker_config import load_broker_base_url
                origin = load_broker_base_url()
                bridge = _usage_bridge(origin)  # Existing protected login only.
                if bridge is None:
                    notice = "login"
                    raise ValueError("브로커 로그인이 필요합니다.")
                capabilities = bridge.review_capabilities()
                cap = capabilities.get("color_lut_manual_upload", {})
                if (not isinstance(cap, dict) or cap.get("schema") != COLOR_LUT_MANUAL_UPLOAD_SCHEMA
                        or type(cap.get("version")) is not int or cap["version"] != 1
                        or not _advertised_api_path_matches(cap.get("projects_path"), COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects", origin)):
                    raise ValueError("서버 업데이트 후 프로젝트를 선택할 수 있습니다.")
                explicit = cap.get("group_destination") == "group-v1"
                projects, group_rows = self._manual_upload_catalog(bridge, explicit=explicit)
                if explicit and not _advertised_api_path_matches(cap.get("episodes_path"), _MANUAL_EPISODES_PATH, origin):
                    raise ValueError("서버의 LUT 에피소드 경로를 확인하세요.")
                me = None
                if explicit or capabilities.get("company_groups_supported") is True:
                    me = bridge._request_json("GET", "/api/me", payload=None, timeout=5)
                    if not me.get("id"):
                        raise ValueError("브로커 로그인 계정을 확인하세요.")
                    owner = _digest([origin, str(me["id"])])
                if explicit:
                    writable = _writable_upload_groups(group_rows, projects)
                    member = me.get("company_group_id") or "ungrouped"
                    group = {"id": member, "name": writable.get(member, {}).get("name", "")}
                    group_status = "unassigned" if member == "ungrouped" else "confirmed"
                    available, selectable = writable, bool(writable)
                else:
                    group_status, group, available, selectable = _upload_company_scope(bridge, capabilities, me)
                notice = "" if projects else "empty"
            except Exception:
                LOGGER.debug("Color LUT manual projects unavailable")
            with self._lock:
                if self._hmb_node_deleted:
                    return
                state = self._hmb_color_lut_state
                old_group_id = self._member_group_id
                if (not state["shot"].get("shot_uuid") and state["manual_project"].get("id") not in {None, "", "my-box"}
                        and (old_group_id and group.get("id") and old_group_id != group["id"] or
                             self._group_owner and owner and self._group_owner != owner)):
                    self._web_upload_epoch += 1
                if (self._manual_projects_origin != origin or self._all_manual_projects != projects
                        or self._group_catalog != available or self._member_group_id != group.get("id", "")
                        or self._group_owner != owner or self._group_selectable != selectable
                        or self._explicit_upload_groups != explicit):
                    self._catalog_generation += 1
                    self._episode_cache.clear()
                    self._episode_key, self._episode_codes = None, []
                    self._episodes_checked = 0.0
                self._group_catalog, self._group_selectable, self._group_owner = available, selectable, owner
                self._explicit_upload_groups = explicit
                self._all_manual_projects, self._manual_projects_origin = projects, origin
                self._member_group_id = group.get("id", "")
                saved = state.get("manual_group_id")
                if saved and (owner and state.get("manual_group_owner") != owner
                              or available and (not selectable or saved not in available)):
                    state.update(manual_group_id="", manual_group_owner="", manual_episode="")
                self._apply_group_view(group, group_status)
                if (available and not state["shot"].get("shot_uuid") and state["manual_project"].get("id")
                        and not any(p["id"] == state["manual_project"]["id"] for p in self._manual_projects)):
                    state.update(manual_episode="", manual_project={}, project={}, project_id="", preset_id="")
                    self._web_upload_epoch += 1
                self._projects_notice = notice
                self._hmb_color_lut_state["revision"] += 1
                self._web_upload_probe_key = ""
            self._publish()
            self._schedule_upload_probe()
            self._schedule_episodes()
        self._manual_projects_worker = threading.Thread(target=contextvars.copy_context().run, args=(load,), name="HMB LUT projects", daemon=True)
        self._manual_projects_worker.start()

    def _schedule_episodes(self, *, skip_selected: bool = False) -> None:
        with self._lock:
            state = self._hmb_color_lut_state
            if self._hmb_node_deleted:
                return
            origin = self._manual_projects_origin
            group_id = self._upload_group.get("id", "")
            explicit = self._explicit_upload_groups
            generation = self._catalog_generation
            selected = state["manual_project"].get("id") if not state["shot"].get("shot_uuid") else None
            allowed = {row["id"] for row in self._manual_projects if row["id"] != "my-box"}
            if not origin or self._upload_group_status == "unavailable":
                return
            selected_key = (origin, group_id, selected) if selected in allowed else None
            cached = self._episode_cache.get(selected_key)
            if selected_key and selected_key != self._episode_key:
                self._episode_key = selected_key
                self._episodes_checked, self._episode_codes = cached or (0.0, [])
                self._episodes_status = "complete" if cached else "loading"
                self._hmb_color_lut_state["revision"] += 1
                self._publish()
            if self._episode_worker is not None:
                return
            now = time.monotonic()
            project_id = selected if selected_key and not skip_selected and now - self._episodes_checked >= 30 else None
            if not project_id:
                while self._episode_prefetch:
                    candidate = self._episode_prefetch.pop(0)
                    if candidate in allowed and now - self._episode_cache.get((origin, group_id, candidate), (0.0, []))[0] >= 30:
                        project_id = candidate
                        break
            if not project_id:
                return
            if project_id in self._episode_prefetch:
                self._episode_prefetch.remove(project_id)
            key = (origin, group_id, project_id)
            if key == selected_key:
                self._episodes_status = "loading"
                self._hmb_color_lut_state["revision"] += 1
                self._publish()

            def still_allowed() -> bool:
                return (not self._hmb_node_deleted and origin == self._manual_projects_origin
                        and generation == self._catalog_generation
                        and group_id == self._upload_group.get("id", "")
                        and any(row["id"] == project_id for row in self._manual_projects))

            def load() -> None:
                codes: set[str] = set()
                complete = False
                try:
                    bridge = _usage_bridge(key[0])
                    if bridge is None:
                        return
                    query = (_MANUAL_EPISODES_PATH.format(group_id=quote(group_id, safe=""), project_id=quote(project_id, safe=""))
                             if explicit else "/api/v1/reviews/episodes?paged=true&project_id=" + quote(project_id, safe=""))
                    if group_id and not explicit:
                        query += "&group_id=" + quote(group_id, safe="")
                    path, cursors = query, set()
                    while path:
                        with self._lock:
                            if not still_allowed():
                                return
                        for attempt in range(3):
                            try:
                                page = bridge._request_json("GET", path, payload=None, timeout=12)
                                break
                            except Exception as exc:
                                status = _upload_error_status(exc)
                                if attempt == 2 or not (status in {429, 502, 503, 504} or _upload_broker_offline(exc)):
                                    raise
                                time.sleep(0.4 * (attempt + 1))
                                with self._lock:
                                    if not still_allowed():
                                        return
                        if (not isinstance(page.get("items"), list)
                                or (explicit and (page.get("group_id"), page.get("project_id")) != (group_id, project_id))
                                or (not explicit and page.get("schema") != "hmb-review-episodes-v1")):
                            return
                        previous_count = len(codes)
                        codes.update(code for row in page["items"] if isinstance(row, dict) and (code := _episode_code(row.get("episode"))))
                        if len(codes) != previous_count:
                            with self._lock:
                                if not still_allowed():
                                    return
                                if self._episode_key == key:
                                    self._episode_codes = sorted(codes.union(self._episode_codes))
                                    self._hmb_color_lut_state["revision"] += 1
                                    self._publish()
                        if explicit or not page.get("has_more"):
                            complete = True
                            break
                        cursor = page.get("next_cursor")
                        if not isinstance(cursor, str) or not cursor or len(cursor) > 2048 or cursor in cursors:
                            return
                        cursors.add(cursor)
                        path = query + "&scan_cursor=" + quote(cursor, safe="")
                except Exception:
                    LOGGER.debug("Color LUT episode suggestions unavailable")
                finally:
                    with self._lock:
                        self._episode_worker = None
                        valid = still_allowed()
                        if valid and complete:
                            self._episode_cache[key] = (time.monotonic(), sorted(codes))
                        current = valid and self._episode_key == key
                        if current:
                            self._episodes_status = "complete" if complete else "partial" if self._episode_codes else "unavailable"
                            if complete:
                                self._episodes_checked = time.monotonic()
                                self._episode_codes = sorted(codes)
                                if explicit and self._hmb_color_lut_state.get("manual_episode"):
                                    self._web_upload_probe_key = ""
                                    self._schedule_upload_probe()
                            self._hmb_color_lut_state["revision"] += 1
                            self._publish()
                        self._schedule_episodes(skip_selected=current and not complete)
            self._episode_worker = threading.Thread(target=contextvars.copy_context().run, args=(load,), name="HMB LUT episodes", daemon=True)
            self._episode_worker.start()

    @staticmethod
    def _manual_upload_catalog(bridge: Any, *, explicit: bool):
        reply = bridge._request_json("GET", COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects", payload=None, timeout=5)
        if reply.get("schema") != "hmb-color-lut-manual-projects" or type(reply.get("version")) is not int or reply["version"] != 1:
            raise ValueError("서버 프로젝트 목록을 확인할 수 없습니다.")

        def projects(key):
            rows = reply.get(key)
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError("서버 프로젝트 목록을 확인할 수 없습니다.")
            result = [_upload_project(row) for row in rows]
            if any(not row for row in result) or len({row["id"] for row in result}) != len(result):
                raise ValueError("서버 프로젝트 목록이 올바르지 않습니다.")
            return result

        choices = projects("projects")
        if explicit and "upload_projects" in reply:
            # Public LUT registration and private gallery visibility are distinct.
            # Only the legacy list can advertise the account's private My Box.
            public = [row for row in projects("upload_projects") if row["id"] != "my-box"]
            choices = public + [row for row in choices if row["id"] == "my-box"]
        return choices, reply.get("upload_groups")

    def _check_upload_company(self, bridge, capabilities, context, me, state, writable=None):
        if context["project_id"] == "my-box":
            return
        if writable is not None:
            # Re-read the server's write grants at submission, independently of
            # browse permissions, the saved widget and the current cached list.
            member = me.get("company_group_id") if "company_group_id" in me else ""
            selected = state.get("manual_group_id") or ("ungrouped" if member is None else member)
            account = _digest([context["server_url"], str(me.get("id") or "")])
            with self._lock:
                same_choice = (self._explicit_upload_groups and account == self._group_owner
                               and self._manual_projects_origin == context["server_url"]
                               and self._upload_group.get("id") == selected
                               and (not state.get("manual_group_id") or state.get("manual_group_owner") == account))
                if not same_choice or selected not in writable or context["project_id"] not in writable[selected]["project_ids"]:
                    raise ValueError("서버에서 업로드 가능한 그룹과 프로젝트를 다시 선택하세요.")
                episode = _episode_code(state.get("manual_episode"))
                if (not episode or self._episode_key != (context["server_url"], selected, context["project_id"])
                        or self._episodes_status != "complete" or episode not in self._episode_codes):
                    context["upload_destination_issue"] = "현재 그룹과 프로젝트의 에피소드 목록에서 선택하세요."
                context.update(group_id=selected, episode=episode,
                               upload_group={"id": selected, "name": writable[selected]["name"]},
                               upload_group_status="confirmed")
            return
        if capabilities.get("company_groups_supported") is not True:
            if context.get("manual") and state.get("manual_group_id"):
                raise ValueError("현재 서버에서 선택한 그룹으로 업로드할 수 없습니다.")
            context["upload_group_status"] = "legacy"
            return
        # The broker freezes the authenticated uploader's membership on intake.
        # A UI value, project name, and administrator read access cannot assign it.
        if "company_group_id" not in me:
            context.update(upload_group_status="unavailable", upload_destination_issue="로그인 계정의 소속 그룹을 다시 확인하세요.")
            return
        expected = me["company_group_id"] if me["company_group_id"] is not None else "ungrouped"
        if not isinstance(expected, str) or not re.fullmatch(r"ungrouped|grp-[a-f0-9]{32}", expected):
            context.update(upload_group_status="unavailable", upload_destination_issue="서버의 소속 그룹 정보를 확인하세요.")
            return
        group = {"id": expected, "name": ""}
        status = "unassigned" if expected == "ungrouped" else "confirmed"
        if not context.get("manual") and self._manual_projects_origin != context["server_url"] and expected != "ungrouped":
            try:
                _, bound_group, _, _ = _upload_company_scope(bridge, capabilities, me)
                if bound_group.get("id") == expected:
                    group = bound_group
            except Exception:
                LOGGER.debug("Bound LUT group display name unavailable")
        with self._lock:
            same_server = self._manual_projects_origin == context["server_url"]
            cached_id = self._upload_group.get("id") if same_server else None
            if cached_id == expected:
                group = dict(self._upload_group)
            elif same_server and expected in self._group_catalog:
                group = {"id": expected, "name": self._group_catalog[expected]["name"]}
            context.update(upload_group=group, upload_group_status=status)
            if not context.get("manual"):
                # Eligibility and original shot remain authoritative on this origin.
                return
            if state.get("manual_group_id") and state["manual_group_id"] != expected:
                raise ValueError(_GROUP_READ_ONLY_NOTICE)
            if not _episode_code(state.get("manual_episode")):
                context["upload_destination_issue"] = "업로드할 에피소드를 선택하세요."
            elif cached_id and cached_id != expected:
                context["upload_destination_issue"] = "로그인 계정의 소속 그룹이 변경되었습니다. 업로드 위치를 다시 확인하세요."
                self._schedule_manual_projects()
            elif (cached_id == expected and self._episode_key == (context["server_url"], expected, context["project_id"])
                    and self._episodes_status == "complete" and self._episode_codes
                    and state.get("manual_episode") and state["manual_episode"] not in self._episode_codes):
                context["upload_destination_issue"] = "현재 그룹과 프로젝트의 에피소드 목록에서 다시 선택하세요."

    def _upload_source_context(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if state["shot"].get("shot_uuid"):
            return self._upload_graph_context(state)
        if self._read_only_group(state):
            raise ValueError(_GROUP_READ_ONLY_NOTICE)
        from _hmb_broker_config import load_broker_base_url
        from _hmb_shot_routing import _same_flow_nodes
        project = _upload_project(state.get("manual_project"))
        flow, nodes = _same_flow_nodes(self)
        if not flow or self not in nodes or self._hmb_node_deleted or not state["source"].get("path"):
            raise ValueError("먼저 영상을 불러오세요.")
        if state["source"].get("shot_uuid") or state["source"].get("channel_uuid"):
            raise ValueError("Only 영상의 샷 연결이 남아 있습니다. 영상을 다시 불러오세요.")
        if not project:
            raise ValueError("업로드할 프로젝트를 선택하세요.")
        # Source names come from the probed local file, never widget/title input.
        name = Path(state["source"]["path"]).name
        if (not name or len(name) > 128 or any(c in name for c in '/\\:*?"<>|') or name.endswith((".", " ")) or not Path(name).suffix
                or any(unicodedata.category(c) in {"Cc", "Cs"} or unicodedata.bidirectional(c) in
                       {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"} for c in name)):
            raise ValueError("업로드할 원본 파일명을 확인하세요. (최대 128자)")
        return {"manual": True, "flow": flow, "server_url": load_broker_base_url(),
                "project_id": project["id"], "project_name": project["name"],
                "file_name": _episode_filename(name, _episode_code(state.get("manual_episode")) if project["id"] != "my-box" else ""),
                "source_identity": list(_source_identity(state["source"])),
                "source_token": self._source_token, "route_epoch": self._web_upload_epoch}

    def _upload_graph_context(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve provenance from registered objects and physical data edges."""
        from _hmb_shot_routing import _same_flow_nodes, _incoming_connections, _subscription_for
        import _hmb_review as review
        source_token, route_epoch = self._source_token, self._web_upload_epoch
        flow, nodes = _same_flow_nodes(self)
        shot, src = state["shot"], state["source"]
        if not flow or self not in nodes or self._hmb_node_deleted or not shot.get("shot_uuid"):
            raise ValueError("Only / 영상 불러오기는 웹 업로드를 지원하지 않습니다.")
        assets = []
        for node in nodes:
            sub = _subscription_for(node)
            if sub is not None and sub.kind == "image_asset" and not getattr(node, "_hmb_node_deleted", False):
                catalog = node._hmb_shot_routing_catalog()
                match = next((item for item in catalog.get("shots", []) if item.get("shot_uuid") == shot["shot_uuid"]), None)
                if catalog.get("channel_uuid") == shot.get("channel_uuid") and match:
                    assets.append((node, match, node._hmb_project_identity()))
        if len(assets) != 1:
            raise ValueError("같은 플로우의 이미지 라이브러리 샷·프로젝트 연결을 확인하세요.")
        _asset, selected, project = assets[0]
        if not project.get("project_id") or not project.get("project_name"):
            raise ValueError("프로젝트를 선택하세요.")
        edges = [edge for edge in _incoming_connections(self)
                 if edge.target_parameter_name == SOURCE and edge.source_parameter_name == "HMB_GENERATED_VIDEO_SOURCE"]
        if len(edges) != 1:
            raise ValueError("샷에 바인딩된 Generator의 완료 영상 연결이 필요합니다.")
        generators = [node for node in nodes if str(getattr(node, "name", "")) == edges[0].source_node_name]
        if len(generators) != 1 or getattr(generators[0], "_hmb_node_deleted", False):
            raise ValueError("원본 Generator 연결이 해제되었습니다.")
        generator = generators[0]
        sub = _subscription_for(generator)
        if (sub is None or sub.kind != "seedance" or not sub.enabled
                or (sub.channel_uuid, sub.shot_uuid) != (shot.get("channel_uuid"), shot.get("shot_uuid"))):
            raise ValueError("Only Generator에서는 웹 업로드할 수 없습니다.")
        actual = generator._hmb_generated_video_source_snapshot()
        required = ("channel_uuid", "shot_uuid", "task_id", "generation_id", "source_node_instance_id", "result_revision")
        if (not isinstance(actual, dict) or actual.get("completed") is not True or not actual.get("task_id")
                or actual.get("task_id") != actual.get("generation_id")
                or any(actual.get(key) != src.get(key) for key in required)
                or _source_identity(actual) != _source_identity(src)):
            raise ValueError("현재 보정 영상의 Generator·Task·샷 정보가 일치하지 않습니다.")
        task = actual["task_id"]
        origin = review.task_origin(task)
        if not origin or review.task_project(task) != project:
            raise ValueError("원본 Task의 서버·프로젝트 기록을 확인할 수 없습니다.")
        name = review._public_shot_name(selected.get("name"))
        if not name:
            raise ValueError("유효한 라이브러리 샷 이름이 필요합니다.")
        return {"flow": flow, "generator": generator, "asset": _asset, "source_task_id": task, "server_url": origin,
                "project_id": project["project_id"], "project_name": project["project_name"],
                "channel_uuid": shot["channel_uuid"], "shot_uuid": shot["shot_uuid"], "shot_name": name,
                "source_node_instance_id": actual["source_node_instance_id"], "source_identity": list(_source_identity(actual)),
                "source_token": source_token, "route_epoch": route_epoch}

    def _capture_usage_operation(self, state: dict[str, Any]) -> None:
        from _hmb_broker_config import load_broker_base_url
        classification = "custom"
        try:
            matches = [p for p in _read_profiles() if p["id"] == state.get("preset_id") and p["id"]
                       and p["project_id"] == state["project_id"] and p["name"] == state.get("preset_name")
                       and p["deletable"] and p["settings"] == normalize_settings(state["settings"])]
            if len(matches) == 1:
                classification = "personal"
        except Exception:
            pass
        origin = load_broker_base_url()
        try:
            bridge = _usage_bridge(origin)
        except Exception:
            bridge = None
        state["_usage_export"] = {"operation_id": str(uuid.uuid4()), "preset_classification": classification,
                                  "origin": origin, "bridge": bridge}

    def _capture_usage_artifact(self, state: dict[str, Any], result: dict[str, Any], cancel: threading.Event) -> dict[str, Any]:
        captured = state.get("_usage_export")
        if not isinstance(captured, dict):
            return {}
        artifact = _verified_export_hash(Path(result["path"]), cancel)
        captured["artifact"] = artifact
        import _hmb_color_lut_usage as usage
        event = usage.build_event(export_operation_id=captured["operation_id"], stage="local_export",
            settings=normalize_settings(state["settings"]), codec=state["output"]["codec"],
            preset_classification=captured["preset_classification"], export_sha256=artifact["sha256"])
        captured["event"] = event
        result["usage_collection"] = {"export_operation_id": captured["operation_id"],
                                     "local_export": {"phase": "pending", "reason": "awaiting_existing_login"}}
        return event

    def _usage_status(self, operation_id: str, stage: str, phase: str, reason: str) -> None:
        # Advisory metadata only; never overwrite video success or UI selection.
        with self._lock:
            states = [self._hmb_color_lut_state, *self._hmb_color_lut_state["shot_states"].values()]
            for state in states:
                if not isinstance(state, dict):
                    continue
                result = state.get("result")
                collection = result.get("usage_collection") if isinstance(result, dict) else None
                if isinstance(collection, dict) and collection.get("export_operation_id") == operation_id:
                    collection[stage] = {"phase": phase, "reason": reason}
        try:
            self._publish()
        except Exception:
            LOGGER.debug("Color LUT optional usage status notification unavailable")

    def _queue_usage_event(self, event: dict[str, Any], origin: str, *, expected_owner: str = "",
                           captured_bridge: Any = None, captured_login: bool = False) -> None:
        """Send immutable metadata in the background, at most one POST per scope."""
        import _hmb_color_lut_usage as usage
        frozen = usage.validate_event(copy.deepcopy(event))
        operation, stage = frozen["export_operation_id"], frozen["stage"]
        def collect() -> None:
            identity, claimed, sent = "", False, False
            try:
                if self._hmb_node_deleted:
                    self._usage_status(operation, stage, "not_collected", "node_deleted")
                    return
                bridge = captured_bridge if captured_login else _usage_bridge(origin)
                if bridge is None:
                    self._usage_status(operation, stage, "not_collected", "existing_login_required")
                    return
                me = bridge._request_json("GET", "/api/me", payload=None, timeout=5)
                owner = me.get("id", me.get("user_id", (me.get("user") or {}).get("id")))
                if type(owner) is not int or owner <= 0 or expected_owner and str(owner) != expected_owner:
                    self._usage_status(operation, stage, "not_collected", "account_identity_mismatch")
                    return
                scope = _digest([bridge.server_url, owner])
                identity = _digest([operation, stage])
                with _USAGE_LOCK:
                    if identity in _USAGE_ACTIVE:
                        return
                    _USAGE_ACTIVE.add(identity)
                    claimed = True
                    previous = _read_usage_record(identity)
                    if previous and previous.get("scope_sha256") != scope:
                        self._usage_status(operation, stage, "not_collected", "account_identity_mismatch")
                        return
                    if previous and (previous.get("schema") != "hmb-color-lut-local-usage-v1"
                                     or type(previous.get("version")) is not int or previous["version"] != 1
                                     or previous.get("phase") not in {"pending", "complete"}
                                     or set(previous) != {"schema", "version", "scope_sha256", "phase", "event", *(["receipt"] if previous.get("phase") == "complete" else [])}
                                     or previous.get("event") != frozen):
                        raise ValueError("LUT usage record conflict.")
                    if previous.get("phase") == "complete":
                        usage.validate_receipt(previous.get("receipt"), frozen)
                        self._usage_status(operation, stage, "complete", "recorded")
                        return
                capabilities = usage.check_capabilities(bridge)
                if self._hmb_node_deleted:
                    self._usage_status(operation, stage, "not_collected", "node_deleted")
                    return
                durable = {"schema": "hmb-color-lut-local-usage-v1", "version": 1,
                           "scope_sha256": scope, "phase": "pending", "event": frozen}
                with _USAGE_LOCK:
                    if not previous:
                        _write_usage_record(identity, durable)
                # Pending is durable before POST. Subsequent attempts only GET
                # this exact operation and stage, including after a restart.
                sent = True
                receipt = (usage.retrieve_event(bridge, frozen) if previous
                           else usage.submit_event(bridge, frozen, capabilities=capabilities))
                with _USAGE_LOCK:
                    _write_usage_record(identity, {**durable, "phase": "complete", "receipt": receipt})
                self._usage_status(operation, stage, "complete", "recorded")
            except Exception:
                self._usage_status(operation, stage, "pending" if sent else "not_collected",
                                   "same_operation_lookup_required" if sent else "statistics_unavailable")
                LOGGER.debug("Color LUT optional usage collection deferred")
            finally:
                if claimed:
                    with _USAGE_LOCK:
                        _USAGE_ACTIVE.discard(identity)
        threading.Thread(target=contextvars.copy_context().run, args=(collect,), name="HMB LUT usage metadata", daemon=True).start()

    def _record_export_proof(self, state: dict[str, Any], result: dict[str, Any], cancel: threading.Event) -> None:
        """Private durable receipt, never accepted from browser state."""
        if state["shot"].get("shot_uuid"):
            self._upload_graph_context(state)
        path = Path(result["path"]).resolve()
        info = path.stat()
        captured = state.get("_usage_export")
        artifact = captured.get("artifact") if isinstance(captured, dict) else None
        if isinstance(captured, dict) and (not isinstance(artifact, dict)
                or (artifact.get("size"), artifact.get("mtime_ns"), artifact.get("device"), artifact.get("inode"))
                   != (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)):
            raise ValueError("Verified export identity is unavailable.")
        proof = {"schema": "hmb-color-lut-local-export-v1", "source_identity": list(_source_identity(state["source"])),
                 "selection": _export_selection(state), "settings": normalize_settings(state["settings"]), "output": _output(state["output"]),
                 "audio_mix": _audio_mix_identity(state),
                 "path": str(path), "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                 "sha256": artifact["sha256"] if artifact else _file_digest(path, cancel), "job_id": result["job_id"]}
        if state.get("audio_mix", {}).get("enabled"):
            proof["sound_contract_sha256"] = result.get("sound_contract_sha256")
        # New exports retain the source title while using their actual delivery
        # container suffix. Older proofs keep their original idempotency identity.
        proof["upload_name_suffix"] = path.suffix.lower()
        if isinstance(captured, dict) and captured.get("event"):
            proof["usage_event"] = copy.deepcopy(captured["event"])
        identity = _digest(proof)
        _write_upload_receipt(identity, proof)
        result["web_export_proof"] = identity

    def _export_upload_proof(self, state: dict[str, Any], *, recheck_file: bool = True) -> dict[str, Any]:
        result = state["result"]
        proof = _read_upload_receipt(str(result.get("web_export_proof") or "")) if result.get("web_export_proof") else {}
        if proof.get("schema") != "hmb-color-lut-local-export-v1" or _digest(proof) != result.get("web_export_proof"):
            raise ValueError("현재 설정으로 최종 출력한 보정 영상이 필요합니다.")
        if proof.get("path") != result.get("path"):
            raise ValueError("보정 영상 경로가 변경되었습니다.")
        if proof.get("sound_contract_sha256"):
            current_sound = state.get("_sound_snapshot") if isinstance(state.get("_sound_snapshot"), dict) else self._capture_sound_snapshot(state)
            if proof["sound_contract_sha256"] != _digest(current_sound):
                raise ValueError("Sound direction changed. Export a new video before uploading.")
        path = Path(proof["path"]).resolve()
        info = path.stat()
        if (proof.get("schema") != "hmb-color-lut-local-export-v1" or _digest(proof) != result.get("web_export_proof")
                or proof.get("settings") != normalize_settings(state["settings"])
                or proof.get("audio_mix", normalize_audio_mix({})) != _audio_mix_identity(state)
                or ("output" in proof and proof["output"] != _output(state["output"]))
                or proof.get("source_identity") != list(_source_identity(state["source"]))
                or proof.get("selection") != _export_selection(state) or proof.get("path") != str(path)
                or proof.get("size") != info.st_size or proof.get("mtime_ns") != info.st_mtime_ns
                or (recheck_file and proof.get("sha256") != _file_digest(path))):
            raise ValueError("현재 설정으로 최종 출력한 보정 영상이 필요합니다.")
        return proof

    def _prepare_upload_context(self, state: dict[str, Any], *, recheck_file: bool = True,
                                artifact: str = "export") -> dict[str, Any]:
        context = self._upload_source_context(state)
        if artifact == "source":
            path = Path(state["source"]["path"]).resolve()
            info = path.stat()
            cache_key = (str(path), info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)
            with self._lock:
                facts = copy.deepcopy(self._upload_source_facts.get(cache_key))
            if recheck_file or not facts:
                facts = _verified_export_hash(path, threading.Event())
                with self._lock:
                    self._upload_source_facts[cache_key] = copy.deepcopy(facts)
                    while len(self._upload_source_facts) > 4:
                        del self._upload_source_facts[next(iter(self._upload_source_facts))]
            # These bytes are the original, regardless of the preview sliders.
            proof = {**facts, "settings": default_settings()}
        elif artifact == "export":
            proof = self._export_upload_proof(state, recheck_file=recheck_file)
            path = Path(proof["path"])
            info = path.stat()
        else:
            raise ValueError("Unknown upload artifact.")
        context["artifact"] = artifact
        bridge = _upload_bridge(context["server_url"])
        capabilities = bridge.review_capabilities()
        cap = capabilities.get("color_lut_manual_upload" if context.get("manual") else "color_lut_upload", {})
        client_media = isinstance(cap, dict) and cap.get("client_review_media") == "client-v1"
        context["workstation_media"] = (client_media and (cap.get("workstation_review_media") == "pc-v1"
                                         or capabilities.get("workstation_review_media") == "pc-v1"))
        if context.get("manual"):
            if (not isinstance(cap, dict) or cap.get("schema") != COLOR_LUT_MANUAL_UPLOAD_SCHEMA
                    or type(cap.get("version")) is not int or cap["version"] != 1 or cap.get("enabled") is not True
                    or cap.get("display_name") != "HMB Color LUT"
                    or not _advertised_api_path_matches(cap.get("upload_path"), COLOR_LUT_MANUAL_UPLOAD_PATH, context["server_url"])
                    or not _advertised_api_path_matches(cap.get("status_path"), COLOR_LUT_MANUAL_UPLOAD_PATH + "/{idempotency_key}", context["server_url"])
                    or not _advertised_api_path_matches(cap.get("projects_path"), COLOR_LUT_MANUAL_UPLOAD_PATH + "/projects", context["server_url"])):
                raise ValueError("브로커의 Only Color LUT 업로드 지원·활성화를 확인하세요.")
            maximum = cap.get("max_bytes")
            if type(maximum) is not int or not 1 <= maximum <= 536870912 or info.st_size > maximum:
                raise ValueError("보정 영상이 서버의 업로드 용량 제한을 초과했습니다.")
            if path.suffix.lower() not in {".mov", ".mp4"}:
                raise ValueError("이 출력 형식은 웹 업로드를 지원하지 않습니다.")
            explicit = cap.get("group_destination") == "group-v1" and context["project_id"] != "my-box"
            # Private uploads stay on the existing contract even if a public
            # project permission or grouping service is currently unavailable.
            projects, group_rows = self._manual_upload_catalog(bridge, explicit=explicit)
            if {"id": context["project_id"], "name": context["project_name"]} not in projects:
                raise ValueError("선택한 프로젝트가 서버의 업로드 목록에 없습니다. 프로젝트를 다시 선택하세요.")
            me = bridge._request_json("GET", "/api/me", payload=None, timeout=5)
            owner = str(me.get("id") or me.get("user_id") or (me.get("user") or {}).get("id") or "")
            if not owner:
                raise ValueError("브로커 로그인 계정을 확인하세요.")
            self._check_upload_company(bridge, capabilities, context, me, state,
                                       _writable_upload_groups(group_rows, projects) if explicit else None)
            if artifact == "export" and proof.get("upload_name_suffix") == path.suffix.lower():
                context["source_file_name"] = context["file_name"]
                context["file_name"] = str(Path(context["file_name"]).with_suffix(path.suffix.lower()))
            if client_media:
                context.update(client_review_media="client-v1", st_dev=info.st_dev, st_ino=info.st_ino)
            context.update(path=str(path), size=info.st_size, mtime_ns=info.st_mtime_ns, sha256=proof["sha256"],
                           settings=proof["settings"], owner_id=owner, bridge=bridge, state_stamp=self._upload_state_stamp(state),
                           settings_sha256=_digest(proof["settings"]))
            destination = (("hmb-color-lut-manual-group-v1", context["group_id"], context["project_id"], context["episode"])
                           if "group_id" in context else ("hmb-color-lut-manual-upload-v1", context["project_id"]))
            context["upload_id"] = hashlib.sha256("\n".join((*destination, context["file_name"], context["sha256"],
                                                            context["settings_sha256"])).encode("utf-8")).hexdigest()
            context["receipt_id"] = _digest([context["server_url"], context["owner_id"], context["upload_id"]])
            return context
        if (not isinstance(cap, dict) or cap.get("schema") != COLOR_LUT_UPLOAD_SCHEMA or type(cap.get("version")) is not int or cap.get("version") != 1
                or cap.get("enabled") is not True or cap.get("display_name") != "HMB Color LUT"
                or not _advertised_api_path_matches(cap.get("upload_path"),
                    "/api/v1/reviews/tasks/{source_task_id}/color-lut", context["server_url"])):
            raise ValueError("브로커가 Color LUT 웹 업로드를 아직 지원하지 않습니다. 서버 업데이트가 필요합니다.")
        maximum = cap.get("max_bytes")
        if type(maximum) is not int or not 1 <= maximum <= 536870912 or info.st_size > maximum:
            raise ValueError("보정 영상이 서버의 업로드 용량 제한을 초과했습니다.")
        if path.suffix.lower() not in {".mov", ".mp4"}:
            raise ValueError("이 출력 형식은 웹 업로드를 지원하지 않습니다.")
        eligibility = bridge._request_json("GET", "/api/v1/reviews/tasks/" + quote(context["source_task_id"], safe="") + "/color-lut", payload=None, timeout=5)
        bound = eligibility.get("shot") if isinstance(eligibility.get("shot"), dict) else {}
        if (eligibility.get("schema") != COLOR_LUT_UPLOAD_SCHEMA or type(eligibility.get("version")) is not int or eligibility.get("version") != 1
                or eligibility.get("enabled") is not True or eligibility.get("eligible") is not True
                or eligibility.get("display_name") != "HMB Color LUT"
                or any(eligibility.get(key) != context[key] for key in ("source_task_id", "project_id", "project_name"))
                or any(bound.get(key) != context[key] for key in ("channel_uuid", "shot_uuid", "source_node_instance_id"))
                or not _advertised_api_path_matches(eligibility.get("upload_path"),
                    "/api/v1/reviews/tasks/" + quote(context["source_task_id"], safe="") + "/color-lut", context["server_url"])
                or type(eligibility.get("max_bytes")) is not int or not info.st_size <= eligibility["max_bytes"] <= maximum
                or re.fullmatch(r"[a-f0-9]{64}", str(eligibility.get("source_sha256") or "")) is None
                or re.fullmatch(r"[a-f0-9]{64}", str(eligibility.get("source_revision") or "")) is None):
            raise ValueError("서버에서 본인 소유의 동일 프로젝트·샷 원본을 확인하지 못했습니다.")
        # UUID/task/project checks above establish the completed result. A
        # later hierarchy edit must not relabel those existing video bytes.
        import _hmb_review as review
        captured_name = review._public_shot_name(bound.get("name"))
        if not captured_name or captured_name != bound.get("name"):
            raise ValueError("서버에 저장된 생성 당시 샷 이름을 확인하지 못했습니다.")
        context["library_shot_name"] = context["shot_name"]
        context["shot_name"] = captured_name
        me = bridge._request_json("GET", "/api/me", payload=None, timeout=5)
        owner = str(me.get("id") or me.get("user_id") or (me.get("user") or {}).get("id") or "")
        if not owner:
            raise ValueError("브로커 로그인 계정을 확인하세요.")
        self._check_upload_company(bridge, capabilities, context, me, state)
        if client_media and eligibility.get("client_review_media") == "client-v1":
            context.update(client_review_media="client-v1", st_dev=info.st_dev, st_ino=info.st_ino)
        context.update(path=str(path), size=info.st_size, mtime_ns=info.st_mtime_ns, sha256=proof["sha256"],
                       settings=proof["settings"], owner_id=owner, bridge=bridge, state_stamp=self._upload_state_stamp(state),
                       source_revision=eligibility["source_revision"], settings_sha256=_digest(proof["settings"]))
        context["upload_id"] = _bound_upload_id(context)
        context["receipt_id"] = _digest([context["server_url"], context["owner_id"], context["upload_id"]])
        context["publication_stamp"] = _digest([context["state_stamp"], _output(state["output"])])
        context["legacy_publication_matches_grade"] = (artifact == "export" or
            (proof["settings"] == normalize_settings(state["settings"]) and not _audio_mix_identity(state)["enabled"]))
        return context

    def _published_export_context(self, state, context):
        # A source-upload button and a graded export use different receipts.
        # Derive the export's identity once per ready context, entirely locally.
        if not context.get("shot_uuid") or not state.get("result", {}).get("web_export_proof"):
            return None
        try:
            proof = self._export_upload_proof(state, recheck_file=False)
        except (OSError, ValueError, RuntimeError):
            return None
        export = {**context, "sha256": proof["sha256"], "size": proof["size"], "legacy_publication_matches_grade": True,
                  "settings_sha256": _digest(proof["settings"])}
        export["upload_id"] = _bound_upload_id(export)
        export["receipt_id"] = _digest([export["server_url"], export["owner_id"], export["upload_id"]])
        return export

    def _schedule_upload_probe(self) -> None:
        with self._lock:
            if self._hmb_node_deleted:
                return
            state = copy.deepcopy(self._hmb_color_lut_state)
            stamp = self._upload_state_stamp(state)
            if not state["source"].get("path"):
                return
            if not state["shot"].get("shot_uuid") and not _upload_project(state.get("manual_project")):
                return
            if self._web_upload_probe_key == stamp and (self._web_upload_context.get("bridge") is not None
                    or self._web_upload_probe is not None and self._web_upload_probe.is_alive()):
                return
            self._web_upload_probe_key = stamp
            self._web_upload_pending = state
            self._web_upload_wake.set()
            if self._web_upload_probe is not None and self._web_upload_probe.is_alive():
                return
        def prepare() -> None:
            retry = 0
            selected = None
            monitored = None
            export_context = None
            while True:
                with self._lock:
                    if self._hmb_node_deleted:
                        self._web_upload_probe = None
                        return
                    if self._web_upload_pending is not None:
                        selected, self._web_upload_pending = self._web_upload_pending, None
                        retry = 0
                        monitored = None
                        export_context = None
                    if selected is None:
                        self._web_upload_probe = None
                        return
                    selected_stamp = self._upload_state_stamp(selected)
                    token, epoch = self._source_token, self._web_upload_epoch
                    previous_view = self._web_upload
                    self._web_upload_wake.clear()
                if previous_view["phase"] == "uploading":
                    monitored = None
                    if self._upload_retry_wait(5):
                        with self._lock:
                            self._web_upload_probe = None
                        return
                    continue
                context, error, local_error, offline = {}, "", False, False
                try:
                    # Invalid local ownership/route is not an offline service.
                    # Do not hold a readiness worker waiting for the Broker.
                    self._upload_source_context(selected)
                    if not Path(selected["source"]["path"]).is_file():
                        raise ValueError("업로드할 로컬 영상 파일이 없습니다.")
                except Exception as exc:
                    error, local_error = str(exc), True
                try:
                    if local_error:
                        raise ValueError(error)
                    if monitored is None:
                        context = self._prepare_upload_context(selected, recheck_file=False, artifact="source")
                        export_context = self._published_export_context(selected, context)
                    else:
                        # Read reachability only while idle. Verify full ownership
                        # again on recovery and before any actual upload.
                        monitored["bridge"].review_capabilities()
                        context = monitored
                except Exception as exc:
                    error = str(exc)
                    offline = not local_error and _upload_broker_offline(exc)
                with self._lock:
                    if (self._hmb_node_deleted or selected_stamp != self._upload_state_stamp(self._hmb_color_lut_state)
                            or token != self._source_token or epoch != self._web_upload_epoch):
                        selected = None
                        monitored = None
                        continue
                    if self._web_upload is not previous_view:
                        monitored = None
                        continue
                    old_context = self._web_upload_context
                    self._web_upload_context = context or {"state_stamp": selected_stamp, "source_token": token, "route_epoch": epoch}
                    receipt = _read_upload_receipt(context["receipt_id"]) if context else {}
                    complete = receipt.get("phase") == "complete"
                    pending = receipt.get("phase") in {"pending", "unknown"}
                    absent = receipt.get("phase") == "absent"
                    retry_media = (complete and context.get("workstation_media")
                                   and receipt.get("client_review_media") == "client-v1"
                                   and receipt.get("review_media_state") != "ready")
                    if retry_media and receipt.get("review_media_state") == "fallback":
                        reason = "원본 업로드 완료 · 서버에서 미리보기 준비 중"
                    elif complete:
                        reason = "원본 업로드 완료 · 미리보기 상태 확인 및 복구" if retry_media else "원본 웹 업로드 완료"
                    elif pending or absent:
                        reason = receipt.get("reason") or (_UPLOAD_ABSENT_REASON if absent else _UPLOAD_PENDING_REASON)
                    else:
                        reason = error or "최종 출력 없이 원본 영상을 바로 업로드합니다."
                    if context and context.get("library_shot_name") and context["library_shot_name"] != context.get("shot_name"):
                        reason += " 생성 당시 샷: " + context["shot_name"]
                    if offline:
                        reason = "브로커가 응답하지 않아 웹 업로드를 사용할 수 없습니다."
                    view = {"enabled": bool(context) and (not complete or bool(retry_media)), "phase": "media_retry" if retry_media else "complete" if complete else
                            "unknown" if pending else "absent" if absent else "ready" if context else "offline" if offline else "unavailable",
                            "reason": reason}
                    if context and (not receipt or complete) and (_confirmed_publication(context, receipt) or
                            (export_context and _confirmed_publication(export_context,
                                _read_upload_receipt(export_context["receipt_id"])))):
                        view["published_shot"] = {"channel_uuid": context["channel_uuid"], "shot_uuid": context["shot_uuid"]}
                    if context.get("upload_destination_issue") and not (complete or pending):
                        view.update(enabled=False, phase="unavailable", reason=context["upload_destination_issue"])
                    changed = (view != self._web_upload or bool(context) != bool(old_context.get("bridge"))
                               or any(old_context.get(key) != self._web_upload_context.get(key)
                                      for key in ("state_stamp", "source_token", "route_epoch")))
                    if changed:
                        self._web_upload = view
                        self._hmb_color_lut_state["revision"] += 1
                if changed:
                    try:
                        self._publish()
                    except Exception:
                        LOGGER.debug("Color LUT readiness notification deferred", exc_info=True)
                if local_error:
                    selected = None
                    monitored = None
                    continue
                # A successful probe expires too: an idle ready button cannot
                # stay enabled after the Broker goes offline. This repeats
                # only advisory reads; unchanged video bytes are not rehashed.
                if context:
                    retry = 0
                monitored = context or None
                if self._upload_retry_wait(30 if context else min(60, 5 * 2**min(retry, 4))):
                    with self._lock:
                        self._web_upload_probe = None
                    return
                if not context:
                    retry += 1
        self._web_upload_probe = threading.Thread(target=contextvars.copy_context().run, args=(prepare,), name="HMB LUT upload readiness", daemon=True)
        self._web_upload_probe.start()

    def _upload_retry_wait(self, seconds: float) -> bool:
        self._web_upload_wake.wait(seconds)
        return self._hmb_node_deleted

    def _upload_metadata(self, context: dict[str, Any]) -> dict[str, Any]:
        if context.get("manual"):
            return {"schema": COLOR_LUT_MANUAL_UPLOAD_SCHEMA, "version": 1,
                    **{key: context[key] for key in ("project_id", "file_name", "settings_sha256")},
                    **({"group_id": context["group_id"], "episode": context["episode"]} if "group_id" in context else {}),
                    "workflow_id": context["flow"], "color_lut_node_id": self._web_node_id,
                    "export_sha256": context["sha256"], "export_bytes": context["size"],
                    "output_format": Path(context["path"]).suffix.lower().lstrip(".")}
        return {"schema": COLOR_LUT_UPLOAD_SCHEMA, "version": 1,
                **{key: context[key] for key in ("source_task_id", "source_revision", "channel_uuid", "shot_uuid", "settings_sha256")},
                "workflow_id": context["flow"], "generator_node_id": context["source_node_instance_id"],
                "color_lut_node_id": self._web_node_id, "export_sha256": context["sha256"],
                "export_bytes": context["size"], "output_format": Path(context["path"]).suffix.lower().lstrip(".")}

    def _upload_request(self, context: dict[str, Any], *, retrieve: bool, cancel: threading.Event) -> dict[str, Any]:
        from _hmb_broker_transport import _broker_require_exact_response_url, _broker_read_json
        from _hmb_broker_config import join_broker_url
        from urllib.request import Request
        from urllib.parse import quote as urlquote
        bridge, identity = context["bridge"], context["upload_id"]
        path = (COLOR_LUT_MANUAL_UPLOAD_PATH if context.get("manual") else
                "/api/v1/reviews/tasks/" + urlquote(context["source_task_id"], safe="") + "/color-lut")
        metadata = context.get("frozen_metadata") or self._upload_metadata(context)
        if retrieve:
            return bridge._request_json("GET", path + "/" + identity, payload=None, timeout=30)
        boundary = "hmb-color-lut-" + uuid.uuid4().hex
        extension = Path(context["path"]).suffix.lower()
        prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n"
                  + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
                  + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"color-lut{extension}\"\r\nContent-Type: {'video/quicktime' if extension == '.mov' else 'video/mp4'}\r\n\r\n").encode("utf-8")
        suffix = f"\r\n--{boundary}--\r\n".encode()
        node = self
        class Body:
            def __iter__(self):
                yield prefix
                with Path(context["path"]).open("rb") as stream:
                    stat = os.fstat(stream.fileno())
                    if (stat.st_size != context["size"] or stat.st_mtime_ns != context["mtime_ns"]
                            or "st_ino" in context and (stat.st_dev, stat.st_ino) != (context["st_dev"], context["st_ino"])):
                        raise ValueError("보정 영상 파일이 변경되었습니다.")
                    digest = hashlib.sha256()
                    while block := stream.read(1024 * 1024):
                        with node._lock:
                            if (cancel.is_set() or node._hmb_node_deleted
                                    or context["state_stamp"] != node._upload_state_stamp(node._hmb_color_lut_state)
                                    or context["source_token"] != node._source_token or context["route_epoch"] != node._web_upload_epoch):
                                raise ValueError("보정 영상 또는 샷이 변경되어 업로드를 중단했습니다.")
                        digest.update(block)
                        yield block
                    if digest.hexdigest() != context["sha256"]:
                        raise ValueError("보정 영상 파일이 변경되었습니다.")
                yield suffix
        request = Request(join_broker_url(bridge.server_url, path), data=Body(), method="POST", headers={
            "Authorization": "Bearer " + bridge._load_access_token(), "Accept": "application/json",
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Content-Length": str(len(prefix) + context["size"] + len(suffix)), "Idempotency-Key": identity,
            **({"X-HMB-Review-Media": "client-v1"} if context.get("client_review_media") == "client-v1" else {})})
        try:
            with bridge._opener.open(request, timeout=300) as response:
                _broker_require_exact_response_url(response, request.full_url)
                return _broker_read_json(response, max_bytes=65536)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(4096))
                if isinstance(detail, dict) and detail.get("error_code") == "color_lut_storage_unavailable":
                    exc.lut_error_code = "color_lut_storage_unavailable"
            except (OSError, ValueError, TypeError, RecursionError):
                pass
            finally:
                exc.close()
            raise

    def _upload_review_media(self, context: dict[str, Any], derived_task_id: str, poster_path: Path, preview_path: Path,
                             *, cancel: threading.Event) -> dict[str, Any]:
        from _hmb_broker_transport import _broker_read_json, _broker_require_exact_response_url
        from _hmb_broker_config import join_broker_url
        from urllib.request import Request

        source_sha = context["sha256"]
        key = context["upload_id"]
        if (context.get("client_review_media") != "client-v1" or not isinstance(derived_task_id, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", derived_task_id) is None
                or not isinstance(source_sha, str) or re.fullmatch(r"[a-f0-9]{64}", source_sha) is None
                or not isinstance(key, str) or re.fullmatch(r"[a-f0-9]{64}", key) is None):
            raise ValueError("미리보기 업로드의 영상 또는 원본 등록 정보를 확인할 수 없습니다.")
        if cancel.is_set():
            raise ValueError("미리보기 업로드가 취소되었습니다.")
        bridge = context["bridge"]
        url = join_broker_url(bridge.server_url, "/api/v1/reviews/tasks/" + quote(derived_task_id, safe="") + "/color-lut/media")
        with Path(poster_path).open("rb") as poster, Path(preview_path).open("rb") as preview:
            poster_size = os.fstat(poster.fileno()).st_size
            preview_size = os.fstat(preview.fileno()).st_size
            if poster_size <= 0 or preview_size <= 0:
                raise ValueError("미리보기 파일이 비어 있습니다.")

            def body():
                for stream, remaining in ((poster, poster_size), (preview, preview_size)):
                    while remaining:
                        if cancel.is_set():
                            raise ValueError("미리보기 업로드가 취소되었습니다.")
                        block = stream.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError("미리보기 전송 중 파일 크기가 변경되었습니다.")
                        remaining -= len(block)
                        yield block

            request = Request(url, data=body(), method="POST", headers={
                "Authorization": "Bearer " + bridge._load_access_token(), "Accept": "application/json",
                "Idempotency-Key": key, "Content-Type": "application/octet-stream",
                "Content-Length": str(poster_size + preview_size), "X-HMB-Poster-Bytes": str(poster_size),
                "X-HMB-Source-SHA256": source_sha})
            try:
                with bridge._opener.open(request, timeout=300) as response:
                    _broker_require_exact_response_url(response, url)
                    if response.status not in (200, 201):
                        raise ValueError("서버가 미리보기 게시를 확인하지 못했습니다.")
                    result = _broker_read_json(response, max_bytes=65536)
            except HTTPError as exc:
                exc.close()
                raise
        if (not isinstance(result, dict) or result.get("state") != "ready"
                or result.get("derived_task_id") != derived_task_id or result.get("source_sha256") != source_sha):
            raise ValueError("서버가 동일 영상의 미리보기 게시를 확인하지 못했습니다.")
        return result

    def _finish_review_media(self, context, task_id, encoded, cancel, workstation):
        """Attach to the accepted original, including after a lost attachment response."""
        with ExitStack() as scope:
            lease = None
            if workstation:
                from _hmb_client_review_media import get_workstation_media_state, workstation_media_heartbeat
                if encoded is None:
                    status = get_workstation_media_state(context["bridge"], task_id)
                    if (status.get("task_id") != task_id or status.get("source_sha256") != context["sha256"]
                            or status.get("source_bytes") != context["size"] or status.get("state") not in {"ready", "waiting", "fallback"}):
                        raise ValueError("미리보기와 원본의 연결을 확인하지 못했습니다.")
                    if status["state"] in ("ready", "fallback"):
                        return status["state"]
                lease = scope.enter_context(workstation_media_heartbeat(
                    context["bridge"], heartbeat_url=f"/api/v1/reviews/tasks/{quote(task_id, safe='')}/workstation-media/heartbeat",
                    task_id=task_id, source_sha256=context["sha256"], idempotency_key=context["upload_id"],
                    cancel_event=cancel))
            try:
                if lease and lease.state in ("ready", "fallback"):
                    return lease.state
                if encoded is None:
                    from _hmb_color_lut import make_review_media
                    directory = scope.enter_context(tempfile.TemporaryDirectory(prefix="hmb-lut-review-"))
                    poster, preview = make_review_media(Path(context["path"]), Path(directory), cancel,
                                                        expected_sha256=context["sha256"])
                else:
                    poster, preview = encoded.result()
                if lease and lease.confirm() in ("ready", "fallback"):
                    return lease.state
                if cancel.is_set():
                    raise InterruptedError("LUT review media cancelled")
                self._upload_review_media(context, task_id, poster, preview, cancel=cancel)
                return "ready"
            except Exception:
                if lease and lease.state in ("ready", "fallback"):
                    return lease.state
                raise

    def _complete_web_upload(self, context, response, durable, media_state=""):
        """Commit the verified original independently of optional review media."""
        record = {**durable, "schema": COLOR_LUT_UPLOAD_SCHEMA, "phase": "complete",
                  "upload_id": context["upload_id"], "response": response}
        if context.get("publication_stamp"):
            record["publication_stamp"] = context["publication_stamp"]
        if media_state:
            record["review_media_state"] = media_state
        try:
            _write_upload_receipt(context["receipt_id"], record)
        except OSError:
            LOGGER.debug("Color LUT completed upload receipt could not be saved", exc_info=True)
        messages = {"encoding": "웹 업로드 완료 · 이 PC에서 미리보기 준비 중",
                    "ready": "웹 업로드 완료 · 썸네일과 미리보기 준비 완료",
                    "pc_pending": "영상 업로드 완료 · 미리보기 상태 확인 및 복구",
                    "fallback": "웹 업로드 완료 · 서버에서 미리보기 준비 중",
                    "server": "웹 업로드 완료 · 미리보기 상태는 로동 페이지에서 확인하세요."}
        with self._lock:
            if (self._hmb_node_deleted or context["state_stamp"] != self._upload_state_stamp(self._hmb_color_lut_state)
                    or context["source_token"] != self._source_token or context["route_epoch"] != self._web_upload_epoch):
                return
            self._web_upload_context = context
            retry_media = media_state in ("pc_pending", "fallback")
            if context.get("artifact") == "export":
                result = self._hmb_color_lut_state["result"]
                if retry_media or (media_state == "encoding" and context.get("workstation_media")):
                    result["review_media_retry"] = {"receipt": context["receipt_id"], "stamp": context["state_stamp"],
                                                    "output": copy.deepcopy(self._hmb_color_lut_state["output"])}
                else:
                    result.pop("review_media_retry", None)
                self._remember_selection()
            self._web_upload = {"enabled": retry_media, "phase": "media_retry" if retry_media else "complete",
                                "reason": messages.get(media_state, "웹 업로드 완료 · HMB Color LUT")}
            if _confirmed_publication(context, record):
                self._web_upload["published_shot"] = {"channel_uuid": context["channel_uuid"], "shot_uuid": context["shot_uuid"]}
            self._hmb_color_lut_state["revision"] += 1

    def _start_web_upload(self, state: dict[str, Any], *, artifact: str = "export",
                          chained: bool = False, cancel_event: threading.Event | None = None,
                          check_only: bool = False, repair_receipt: str = "") -> None:
        # Only upload_web or the explicit export_upload command may submit.
        if not chained and not self._upload_projection().get("enabled"):
            self._status("error", self._upload_projection().get("reason", "웹 업로드 준비가 필요합니다."))
            # A command can carry the latest edit before the property update
            # arrives. Keep it fail-closed, but recheck the newly captured state.
            if self._web_upload_context.get("state_stamp") != self._upload_state_stamp(self._hmb_color_lut_state):
                self._schedule_upload_probe()
            return
        check_only = check_only or (not chained and self._web_upload.get("phase") == "unknown")
        self._web_upload = {"enabled": False, "phase": "uploading",
                            "reason": "업로드 기록 확인 중…" if check_only else "웹 업로드 중…"}
        cancel = self._cancel = cancel_event if cancel_event is not None else threading.Event()
        def upload() -> None:
            identity, sent, claimed, retrieve, offline, context, durable = "", False, False, False, False, {}, {}
            resources = ExitStack()
            encoded = None
            source_accepted = False
            try:
                if cancel.is_set() or self._hmb_node_deleted:
                    return
                context = self._prepare_upload_context(state, artifact=artifact)
                identity = context["upload_id"]
                if repair_receipt and repair_receipt != context["receipt_id"]:
                    raise ValueError("미리보기를 복구할 영상이나 계정이 변경되었습니다.")
                current = self._upload_source_context(state)
                if any(current.get(key) != (context.get("source_file_name", context.get(key)) if key == "file_name"
                                            else context.get(key)) for key in current):
                    raise ValueError("원본 Generator 또는 샷 연결이 변경되었습니다.")
                with self._lock:
                    if (cancel.is_set() or self._hmb_node_deleted or context["state_stamp"] != self._upload_state_stamp(self._hmb_color_lut_state)
                            or context["source_token"] != self._source_token or context["route_epoch"] != self._web_upload_epoch):
                        raise ValueError("현재 샷 또는 보정 설정이 변경되었습니다.")
                with _UPLOAD_LOCK:
                    if identity in _UPLOAD_ACTIVE:
                        raise ValueError("동일한 보정 영상의 웹 업로드가 진행 중입니다.")
                    previous = _read_upload_receipt(context["receipt_id"])
                    if (context.get("upload_destination_issue") and not check_only
                            and previous.get("phase") not in {"complete", "pending", "unknown"}):
                        raise ValueError(context["upload_destination_issue"])
                    if repair_receipt and previous.get("phase") != "complete":
                        raise ValueError("미리보기를 복구할 기존 업로드 영수증을 확인하세요.")
                    if previous.get("phase") == "complete":
                        response = previous.get("response", {})
                        durable = previous
                        _UPLOAD_ACTIVE.add(identity)
                        claimed = True
                    else:
                        metadata = self._upload_metadata(context)
                        if previous.get("metadata"):
                            frozen = previous["metadata"]
                            # A retry retains its original workflow/node IDs,
                            # while media/shot/source/settings preconditions
                            # must still be identical to the frozen operation.
                            if (not isinstance(frozen, dict) or set(frozen) != set(metadata)
                                    or any(frozen.get(key) != metadata[key] for key in metadata
                                           if key not in {"workflow_id", "color_lut_node_id"})):
                                raise ValueError("미확인 업로드의 원본 정보가 변경되었습니다. 기존 업로드 상태를 먼저 확인하세요.")
                            metadata = frozen
                        context["frozen_metadata"] = copy.deepcopy(metadata)
                        durable = {"schema": COLOR_LUT_UPLOAD_SCHEMA, "phase": "pending", "upload_id": identity, "metadata": metadata}
                        if retrieve_issue := previous.get("submission_issue"):
                            durable["submission_issue"] = retrieve_issue
                        _UPLOAD_ACTIVE.add(identity)
                        claimed = True
                        retrieve = check_only or previous.get("phase") in {"pending", "unknown"}
                        if retrieve:
                            if previous.get("client_review_media") == "client-v1":
                                durable["client_review_media"] = "client-v1"
                        elif context.get("client_review_media") == "client-v1":
                            durable["client_review_media"] = "client-v1"
                        _write_upload_receipt(context["receipt_id"], durable)
                        response = None
                if response is None:
                    if not retrieve and durable.get("client_review_media") == "client-v1":
                        try:
                            from _hmb_color_lut import make_review_media
                            directory = resources.enter_context(tempfile.TemporaryDirectory(prefix="hmb-lut-review-"))
                            pool = resources.enter_context(ThreadPoolExecutor(max_workers=1, thread_name_prefix="HMB LUT media"))
                            encoded = pool.submit(make_review_media, Path(context["path"]), Path(directory),
                                                  cancel, expected_sha256=context["sha256"])
                        except Exception:
                            # The original receipt and review media have independent outcomes.
                            LOGGER.warning("Could not start local LUT review media preparation", exc_info=True)
                    # Persist pending before crossing the network boundary. An
                    # uncertain response is retrieved with the same ID only.
                    sent = True
                    try:
                        response = self._upload_request(context, retrieve=retrieve, cancel=cancel)
                    except HTTPError as submit_error:
                        status = _upload_error_status(submit_error)
                        if retrieve or status not in {500, 502, 503, 504} or cancel.is_set():
                            raise
                        try:
                            response = self._upload_request(context, retrieve=True, cancel=cancel)
                        except Exception:
                            raise submit_error from None
                manual = context.get("manual") is True
                expected_schema = "hmb-color-lut-manual-upload-result" if manual else "hmb-color-lut-upload-result"
                identity_fields = ("project_id", "project_name", "sha256", "file_name") if manual else ("source_task_id", "project_id", "project_name", "channel_uuid", "shot_uuid", "sha256", "shot_name")
                if manual and "group_id" in context:
                    identity_fields += ("group_id", "episode")
                if (not isinstance(response, dict) or response.get("schema") != expected_schema or type(response.get("version")) is not int or response.get("version") != 1
                        or any(response.get(key) != context[key] for key in
                               identity_fields)
                        or (manual and (response.get("manual") is not True or any(response.get(key) is not None for key in ("source_task_id", "channel_uuid", "shot_uuid", "shot_name"))))
                        or type(response.get("bytes")) is not int or response.get("bytes") != context["size"] or type(response.get("created")) is not bool
                        or response.get("display_name") != "HMB Color LUT" or response.get("source_kind") != "HMB Color LUT"
                        or not isinstance(response.get("asset_id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", response["asset_id"]) is None
                        or not isinstance(response.get("derived_task_id"), str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", response["derived_task_id"]) is None):
                    raise ValueError("서버가 동일 보정 영상의 업로드 완료를 확인하지 못했습니다.")
                source_accepted = True
                media_state = durable.get("review_media_state", "")
                needs_media = durable.get("client_review_media") == "client-v1" and media_state != "ready"
                workstation = needs_media and context.get("workstation_media") and context.get("client_review_media") == "client-v1"
                if needs_media:
                    media_state = "encoding" if encoded is not None or workstation else "server"
                self._complete_web_upload(context, response, durable, media_state)
                if encoded is not None or workstation:
                    try:
                        self._publish()
                    except Exception:
                        LOGGER.debug("Color LUT receipt notification deferred", exc_info=True)
                    try:
                        media_state = self._finish_review_media(context, response["derived_task_id"], encoded, cancel, workstation)
                    except Exception:
                        LOGGER.info("Original LUT accepted; review media attachment was not confirmed", exc_info=True)
                        media_state = "pc_pending" if workstation else "server"
                    self._complete_web_upload(context, response, durable, media_state)
            except Exception as exc:
                if source_accepted:
                    # A projection or follow-up error cannot invalidate the verified original.
                    LOGGER.warning("Color LUT original accepted; local completion update was interrupted", exc_info=True)
                    return
                offline = not sent and _upload_broker_offline(exc)
                absent = bool(sent and retrieve and _upload_error_status(exc) == 404)
                if sent and not retrieve:
                    durable["submission_issue"] = _upload_failure_summary(exc)
                reason = (" ".join(filter(None, (durable.get("submission_issue"), _UPLOAD_ABSENT_REASON))) if absent else _unknown_upload_reason(exc) if sent else
                          "브로커가 응답하지 않아 웹 업로드를 사용할 수 없습니다." if offline else str(exc))
                if sent and identity:
                    try:
                        _write_upload_receipt(context["receipt_id"], {**durable, "schema": COLOR_LUT_UPLOAD_SCHEMA,
                                              "phase": "absent" if absent else "unknown", "upload_id": identity, "reason": reason})
                    except OSError:
                        LOGGER.debug("Color LUT pending upload receipt could not be saved", exc_info=True)
                with self._lock:
                    if (not self._hmb_node_deleted and self._upload_state_stamp(state) == self._upload_state_stamp(self._hmb_color_lut_state)
                            and (not context or context.get("source_token") == self._source_token and context.get("route_epoch") == self._web_upload_epoch)):
                        self._web_upload = {"enabled": bool(sent), "phase": "absent" if absent else "unknown" if sent else "offline" if offline else "unavailable",
                                            "reason": reason}
            finally:
                if encoded is not None and not encoded.done():
                    cancel.set()
                try:
                    resources.close()
                except OSError:
                    LOGGER.warning("Color LUT temporary media cleanup failed", exc_info=True)
                with _UPLOAD_LOCK:
                    if claimed:
                        _UPLOAD_ACTIVE.discard(identity)
                self._publish()
                if artifact == "export" or offline:
                    # The separate Web Upload button always represents the raw
                    # source. The output button retries its own frozen export.
                    with self._lock:
                        self._web_upload_probe_key = ""
                    self._schedule_upload_probe()
        self._web_upload_worker = threading.Thread(target=contextvars.copy_context().run, args=(upload,), name="HMB LUT web upload", daemon=True)
        self._web_upload_worker.start()
        self._publish()

    def _status(self, phase: str, message: str = "", progress: float = 0) -> None:
        with self._lock:
            if self._hmb_color_lut_state["language"] == "ko":
                message = {"Loading video…": "영상을 불러오는 중…", "Processing original source…": "원본 영상 처리 중…",
                    "Encoding original source…": "원본 영상 인코딩 중…", "Preset saved.": "프리셋을 저장했습니다.",
                    "Preset deleted.": "프리셋을 삭제했습니다.",
                    "A local operation is already running.": "로컬 작업이 이미 진행 중입니다."}.get(message, message)
            status = {"phase": phase, "message": message, "progress": progress}
            if status == self._hmb_color_lut_state["status"]:
                return
            self._hmb_color_lut_state["status"] = status
        self._publish()

    def _remember_selection(self) -> None:
        self._hmb_color_lut_state["shot_states"][_selection_key(self._hmb_color_lut_state)] = copy.deepcopy({
            key: self._hmb_color_lut_state[key] for key in ("settings", "audio_mix", "output", "source", "result", "preset_name", "preset_id")})
        while len(self._hmb_color_lut_state["shot_states"]) > 128:
            del self._hmb_color_lut_state["shot_states"][next(iter(self._hmb_color_lut_state["shot_states"]))]

    def _publish_result_url(self, value: str = "") -> None:
        set_output(self, "video_url", value)
        publish = getattr(self, "publish_update_to_parameter", None)
        if callable(publish):
            publish("video_url", value)

    @hmb_binding_mutation
    def _switch(self, shot: Any, project: str | None = None) -> None:
        self._remember_selection()
        if shot != self._hmb_color_lut_state["shot"]:
            selected = (_upload_project(self._hmb_color_lut_state.get("manual_project")) if not shot.get("shot_uuid")
                        else getattr(self, "_bound_project", {}))
            if selected:
                project = str(selected.get("id") or "")
                self._hmb_color_lut_state["project"] = copy.deepcopy(selected)
        self._hmb_color_lut_state["shot"] = copy.deepcopy(shot)
        if project is not None:
            self._hmb_color_lut_state["project_id"] = project
        saved = self._hmb_color_lut_state["shot_states"].get(_selection_key(self._hmb_color_lut_state), {})
        saved = saved if isinstance(saved, Mapping) else {}
        self._hmb_color_lut_state["settings"] = normalize_settings(saved.get("settings"))
        self._hmb_color_lut_state["audio_mix"] = normalize_audio_mix(saved.get("audio_mix"))
        self._hmb_color_lut_state["preset_name"] = str(saved.get("preset_name") or "")
        self._hmb_color_lut_state["preset_id"] = _profile_id(saved.get("preset_id"))
        self._hmb_color_lut_state["output"] = _output(saved.get("output"))
        self._hmb_color_lut_state["result"] = copy.deepcopy(saved.get("result", {}))
        self._restoring_source = copy.deepcopy(saved.get("source", {}))
        self._hmb_color_lut_state["source"] = {}
        _set_parameter_silently(self, SOURCE, {})
        self._publish_result_url()
        self._hmb_color_lut_state["status"] = {"phase": "idle", "message": "", "progress": 0}
        self._source_token += 1
        self._web_upload_wake.set()
        self._pending_source_key = None
        if not shot.get("shot_uuid") and saved.get("source", {}).get("path"):
            self._queue_source(saved["source"])

    @hmb_binding_mutation
    def _apply_ui(self, value: Any, *, initial_setup: bool = False) -> None:
        if not isinstance(value, Mapping):
            return
        command = None if initial_setup else value.get("__hmb_color_lut_command__")
        with self._lock:
            if self._hmb_node_deleted:
                return
            # A serialized backend state contains shot_states; a live widget
            # edit deliberately does not. Never hydrate read-only source data
            # back from that first compact edit after automatic routing.
            initial = initial_setup or (not self._hydrated and isinstance(value.get("shot_states"), Mapping))
            self._hydrated = True
            supplied_project = str(value.get("project_id") or "")
            current_project = self._hmb_color_lut_state["project_id"]
            initial_manual = bool(initial and isinstance(value.get("shot"), Mapping) and not value["shot"].get("shot_uuid")
                                  and _upload_project(value.get("manual_project")))
            if ("project_id" in value and supplied_project != current_project
                    and (not initial or (self._project_authoritative and supplied_project and not initial_manual))):
                # A debounced edit/command can arrive after ImageAsset has
                # changed the project. Never reinterpret its settings as an
                # edit of the newly selected project, even at a higher UI rev.
                if not initial_setup:
                    self._publish()
                return
            if initial_setup:
                if re.fullmatch(r"[a-f0-9]{32}", str(value.get("_web_node_id") or "")):
                    self._web_node_id = value["_web_node_id"]
                # Registration may already have queued an older Shot probe.
                # Its late result must not replace the restored Shot's source.
                self._source_token += 1
                self._source_pending = None
                self._pending_source_key = None
                self._restoring_source = {}
            if initial:
                self._hydrated = True
                histories = value.get("shot_states")
                if isinstance(histories, dict):
                    self._hmb_color_lut_state["shot_states"] = copy.deepcopy(histories)
                if not self._project_authoritative:
                    self._hmb_color_lut_state["project_id"] = str(value.get("project_id") or "")
                    self._hmb_color_lut_state["project"] = dict(value.get("project") or {}) if isinstance(value.get("project"), Mapping) else {}
                self._hmb_color_lut_state["manual_project"] = _upload_project(value.get("manual_project"))
                self._hmb_color_lut_state["manual_episode"] = _episode_code(value.get("manual_episode"))
                group_id = value.get("manual_group_id")
                group_owner = value.get("manual_group_owner")
                self._hmb_color_lut_state.update(manual_group_id="", manual_group_owner="")
                if (isinstance(group_id, str) and re.fullmatch(r"ungrouped|grp-[a-f0-9]{32}", group_id)
                        and isinstance(group_owner, str) and re.fullmatch(r"[0-9a-f]{64}", group_owner)):
                    self._hmb_color_lut_state.update(manual_group_id=group_id, manual_group_owner=group_owner)
                    if self._group_owner and self._group_catalog:
                        if group_owner != self._group_owner or not self._group_selectable or group_id not in self._group_catalog:
                            self._hmb_color_lut_state.update(manual_group_id="", manual_group_owner="", manual_episode="")
                if self._group_owner and self._group_catalog:
                    self._apply_group_view(self._group_catalog.get(self._member_group_id, {}), self._upload_group_status)
                if initial_manual:
                    manual = self._hmb_color_lut_state["manual_project"]
                    self._hmb_color_lut_state.update(project_id=manual["id"], project=copy.deepcopy(manual))
                if isinstance(value.get("shot_catalog"), Mapping):
                    self._hmb_color_lut_state["shot_catalog"] = _normalize_shot_catalog(value["shot_catalog"], allow_sparse=True)
            try:
                revision = max(0, int(value.get("revision") or 0))
            except (TypeError, ValueError, OverflowError):
                revision = self._hmb_color_lut_state["revision"]
            if revision < self._hmb_color_lut_state["revision"] and not initial:
                if command:
                    self._command(command)
                return
            shot = _normalize_shot_selection(value.get("shot"), self._hmb_color_lut_state["shot_catalog"])
            project = self._hmb_color_lut_state["project_id"]  # ImageAsset owns this field.
            changed = shot != self._hmb_color_lut_state["shot"] or project != self._hmb_color_lut_state["project_id"]
            if changed and not initial:
                self._switch(shot, project)
            else:
                self._hmb_color_lut_state["shot"], self._hmb_color_lut_state["project_id"] = shot, project
                self._hmb_color_lut_state["settings"] = normalize_settings(value.get("settings", self._hmb_color_lut_state["settings"]))
                self._hmb_color_lut_state["audio_mix"] = normalize_audio_mix(value.get("audio_mix", self._hmb_color_lut_state["audio_mix"]))
                self._hmb_color_lut_state["output"] = _output(value.get("output"))
                if initial:
                    self._hmb_color_lut_state["result"] = copy.deepcopy(value.get("result")) if isinstance(value.get("result"), Mapping) else {}
                    self._hmb_color_lut_state["source"] = copy.deepcopy(value.get("source")) if isinstance(value.get("source"), Mapping) else {}
                    src = self._hmb_color_lut_state["source"]
                    if shot.get("shot_uuid") and (src.get("shot_uuid") != shot["shot_uuid"] or src.get("channel_uuid") != shot["channel_uuid"] or src.get("completed") is not True):
                        self._hmb_color_lut_state["source"], self._hmb_color_lut_state["result"] = {}, {}
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_color_lut_state["language"] = "en" if value.get("language") == "en" else "ko"
            if initial or not changed:
                self._hmb_color_lut_state["preset_name"] = str(value.get("preset_name") or "")[:80]
                self._hmb_color_lut_state["preset_id"] = _profile_id(value.get("preset_id"))
            self._hmb_color_lut_state["revision"] = revision if initial_setup else max(revision, self._hmb_color_lut_state["revision"]) + 1
            self._remember_selection()
            if initial and not initial_setup and not shot.get("shot_uuid") and self._hmb_color_lut_state["source"].get("path"):
                self._queue_source(self._hmb_color_lut_state["source"])
        if initial_setup:
            # Native DeserializeFlow suppresses after_value_set. Restore only
            # private authoring here, before deferred routing can publish a
            # default state over the saved value. Never replay saved commands,
            # probe media, publish or reconcile during partial hydration.
            return
        self._publish()
        if changed:
            self._reconcile()
        self._schedule_upload_probe()
        if command:
            self._command(command)

    def _queue_source(self, snapshot: Any) -> None:
        if not isinstance(snapshot, Mapping) or not snapshot:
            return
        snap = copy.deepcopy(snapshot)
        with self._lock:
            shot = self._hmb_color_lut_state["shot"]
            if not shot.get("shot_uuid") and snap.get("shot_uuid"):
                return
            if shot.get("shot_uuid") and (snap.get("shot_uuid") != shot["shot_uuid"] or snap.get("channel_uuid") != shot["channel_uuid"] or snap.get("completed") is not True):
                return
            path = str(snap.get("path") or "")
            if not path:
                return
            key = (_selection_key(self._hmb_color_lut_state), *_source_identity(snap))
            if key == self._pending_source_key:
                return
            self._pending_source_key = key
            if getattr(self, "_mov_preview_cancel", None) is not None:
                self._mov_preview_cancel.set()
            self._source_token += 1
            self._web_upload_wake.set()
            token = self._source_token
            queue_warnings = []
            if _source_identity(self._hmb_color_lut_state["source"] or self._restoring_source) != _source_identity(snap):
                self._hmb_color_lut_state["result"] = {}
                try:
                    self._publish_result_url()
                except Exception as exc:
                    queue_warnings.append(("output_notification", exc))
            self._restoring_source = {}
            self._hmb_color_lut_state["source"] = {}
            self._hmb_color_lut_state["status"] = {"phase": "probing", "message": "", "progress": 0}
            self._source_pending = (token, snap, path, queue_warnings)
            try:
                self._publish()
            except Exception as exc:
                queue_warnings.append(("ui_notification", exc))
            if self._source_worker is not None and self._source_worker.is_alive():
                return
        def load() -> None:
            while True:
                with self._lock:
                    pending = self._source_pending
                    self._source_pending = None
                    if pending is None or self._hmb_node_deleted:
                        self._source_worker = None
                        return
                token, snap, path, warnings = pending
                try:
                    try:
                        info = probe_source(path)
                    except UnsupportedGrade as exc:
                        if Path(path).suffix.lower() != ".mov":
                            raise
                        info = exc.media
                    media = Path(str(info.get("path") or path)).resolve()
                    source = {**snap, **info, "_reference_path": str(snap.get("_reference_path") or path),
                              "path": str(media), "url": "", "name": media.name,
                              "fps": float(info.get("frame_rate") or info.get("fps") or 0),
                              "revision": str(snap.get("result_revision") or media.stat().st_mtime_ns)}
                    with self._lock:
                        if token != self._source_token or self._hmb_node_deleted:
                            continue
                        result = copy.deepcopy(self._hmb_color_lut_state["result"])
                    if result.get("path") and result.get("source_path") != source["path"]:
                        raise ValueError("The saved Color LUT video does not belong to this source.")
                    restored = bool(result.get("path") and result.get("source_path") == source["path"]
                                    and Path(result["path"]).suffix.lower() != ".cube")
                    if restored:
                        # A saved path or existing filename is not proof of a
                        # playable grade. Validate it before declaring success.
                        result_probe = probe_source(result["path"])
                        if (result_probe.get("width"), result_probe.get("height")) != (info.get("width"), info.get("height")):
                            raise ValueError("The saved Color LUT video dimensions do not match its source.")
                    try:
                        source["url"] = _media_url(media)
                    except Exception as exc:
                        # A native preview outage is independent of a probed
                        # local source, including restoration of a saved grade.
                        warnings.append(("preview", exc))
                    if restored:
                        try:
                            result["url"] = _media_url(Path(result["path"]))
                        except Exception as exc:
                            result["url"] = ""
                            warnings.append(("preview", exc))
                except Exception as exc:
                    with self._lock:
                        if token != self._source_token or self._hmb_node_deleted:
                            continue
                        self._pending_source_key = None
                        self._hmb_color_lut_state["result"] = {}
                        self._hmb_color_lut_state["status"] = {"phase": "error", "message": str(exc), "progress": 0}
                        try:
                            self._publish_result_url()
                            self._status("error", str(exc))
                            self._publish()
                        except Exception:
                            LOGGER.debug("Color LUT invalid media notification deferred", exc_info=True)
                    continue
                with self._lock:
                    if token != self._source_token or self._hmb_node_deleted:
                        continue
                    self._hmb_color_lut_state["source"] = source
                    self._hmb_color_lut_state["result"] = result
                    self._hmb_color_lut_state["status"] = {"phase": "complete" if restored else "idle", "message": str(result["path"]) if restored else "", "progress": 1 if restored else 0}
                    def remember_warning(stage: str, exc: Exception) -> None:
                        owner = result if restored else source
                        self._export_warning(owner, stage, exc)
                        self._hmb_color_lut_state["status"]["message"] = (str(result["path"]) + ". " if restored else "") + "; ".join(
                            f"{item['stage']}: {item['message']}" for item in owner.get("postprocess_warnings", []))
                    for stage, exc in warnings:
                        remember_warning(stage, exc)
                    callbacks = [("output_notification", lambda: self._publish_result_url(result.get("url", "")))] if restored else []
                    callbacks += [("selection_cache", self._remember_selection), ("upload_probe", self._schedule_upload_probe), ("ui_notification", self._publish)]
                    for stage, callback in callbacks:
                        if token != self._source_token or self._hmb_node_deleted:
                            break
                        try:
                            callback()
                        except Exception as exc:
                            if token != self._source_token or self._hmb_node_deleted:
                                break
                            # Preview/UI/cache failures cannot undo either a
                            # validated local source or a validated saved grade.
                            remember_warning(stage, exc)
                            if stage == "selection_cache":
                                self._hmb_color_lut_state["shot_states"][_selection_key(self._hmb_color_lut_state)] = copy.deepcopy({
                                    key: self._hmb_color_lut_state[key] for key in ("settings", "output", "source", "result", "preset_name", "preset_id")})
                            if stage == "ui_notification":
                                try:
                                    _set_parameter_silently(self, UI, copy.deepcopy(self._hmb_color_lut_state))
                                except Exception as storage_error:
                                    remember_warning("state_storage", storage_error)
                            LOGGER.debug("Color LUT restored media notification deferred: %s", stage, exc_info=True)
                    if token == self._source_token and not self._hmb_node_deleted:
                        # Cache the final warning-bearing result even if an
                        # earlier optional cache or native notification failed.
                        self._hmb_color_lut_state["shot_states"][_selection_key(self._hmb_color_lut_state)] = copy.deepcopy({
                            key: self._hmb_color_lut_state[key] for key in ("settings", "output", "source", "result", "preset_name", "preset_id")})
                if (media.suffix.lower() == ".mov" and info.get("video_codec")
                        and (info["video_codec"] != "h264" or info.get("pixel_format") not in ("yuv420p", "yuvj420p")
                             or info.get("audio_codec") not in ("", "aac", "mp3"))):
                    # The original is already available for upload while this preview is built.
                    with self._lock:
                        if self._hmb_node_deleted or token != self._source_token:
                            continue
                        cancel = self._mov_preview_cancel = threading.Event()
                    preview_dir = tempfile.TemporaryDirectory(prefix="hmb-lut-preview-", ignore_cleanup_errors=True)
                    try:
                        preview = make_mov_preview(media, info, Path(preview_dir.name), cancel)
                        url = _media_url(preview)
                        with self._lock:
                            if self._hmb_node_deleted or token != self._source_token:
                                continue
                            self._mov_preview_dir = preview_dir
                            source["url"] = url
                            self._publish()
                    except Exception as exc:
                        if not cancel.is_set():
                            LOGGER.warning("MOV preview unavailable for %s: %s", media.name, exc)
                    finally:
                        if getattr(self, "_mov_preview_dir", None) is not preview_dir:
                            preview_dir.cleanup()
        with self._lock:
            self._source_worker = threading.Thread(target=contextvars.copy_context().run, args=(load,), name="HMB LUT source", daemon=True)
            self._source_worker.start()

    def _command(self, value: Any) -> None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return
        if not isinstance(value, Mapping) or self._hmb_node_deleted:
            return
        request_id = str(value.get("id") or "")
        with self._lock:
            if not request_id or request_id in self._seen_commands:
                return
            self._hydrated = True
            self._seen_commands = (self._seen_commands + [request_id])[-128:]
            action = str(value.get("action") or "")
            if action == "cancel":
                self._cancel.set()
                return
            if action == "refresh_upload_projects":
                self._schedule_manual_projects()
                return
            if action == "refresh_upload_episodes":
                self._schedule_episodes()
                return
            if action in {"export", "export_upload", "browse_video", "upload_web"} and self._worker is not None and self._worker.is_alive():
                self._status("busy", "A local operation is already running.")
                return
            if action in {"upload_web", "export", "export_upload", "browse_video"} and self._web_upload_worker is not None and self._web_upload_worker.is_alive():
                return
            if action == "delete_profile" and any(worker is not None and worker.is_alive()
                    for worker in (self._worker, self._source_worker, self._web_upload_worker)):
                self._status("busy", "A local operation is already running.")
                return
            captured = copy.deepcopy(self._hmb_color_lut_state)
            # Commands may arrive before the debounced property update. Capture the
            # current UI settings, but never trust a UI-supplied source/provenance.
            authored = value.get("state")
            if isinstance(authored, Mapping) and _selection_key(authored) != _selection_key(captured):
                # Delayed buttons belong to their original Project/Shot.
                # Cancellation was handled above and may still stop that job.
                return
            if action == "select_upload_group" and any(
                    worker is not None and worker.is_alive() for worker in (self._worker, self._web_upload_worker)):
                self._publish()
                return
            if "group_id" in value and action in {"select_upload_project", "select_upload_episode"} and value["group_id"] != self._upload_group.get("id", ""):
                self._publish()
                return
            if (action in {"upload_web", "export_upload"} and isinstance(authored, Mapping)
                    and (authored.get("manual_group_id") or "") != (captured.get("manual_group_id") or "")):
                self._publish()
                return
            if action == "select_upload_group":
                from _hmb_broker_config import load_broker_base_url
                identity = value.get("group_id")
                if (captured["shot"].get("shot_uuid") or not self._group_selectable or not isinstance(identity, str)
                        or identity not in self._group_catalog or self._manual_projects_origin != load_broker_base_url()):
                    self._publish()
                    return
                if identity == self._upload_group.get("id"):
                    return
                state = self._hmb_color_lut_state
                self._remember_selection()
                state.update(manual_group_id=identity if identity != self._member_group_id else "", manual_group_owner=self._group_owner)
                self._apply_group_view(self._group_catalog.get(self._member_group_id, {}), self._upload_group_status)
                project_id = state["manual_project"].get("id", "")
                if self._explicit_upload_groups or project_id and not any(p["id"] == project_id for p in self._manual_projects):
                    state.update(manual_project={}, project={}, project_id="", preset_id="")
                cached = self._episode_cache.get((self._manual_projects_origin, identity, project_id))
                if self._explicit_upload_groups or not cached or state.get("manual_episode") not in cached[1]:
                    state["manual_episode"] = ""
                state["revision"] += 1
                self._episode_key, self._episode_codes = None, []
                self._web_upload_epoch += 1
                self._web_upload_context, self._web_upload_probe_key = {}, ""
                self._publish()
                self._schedule_episodes()
                self._schedule_upload_probe()
                return
            if action == "select_upload_episode":
                project_id = captured["manual_project"].get("id")
                if (captured["shot"].get("shot_uuid") or not project_id or project_id == "my-box"
                        or value.get("project_id") != project_id):
                    return
                raw = value.get("episode")
                episode = _episode_code(raw)
                if raw != "" and not episode:
                    self._status("error", "에피소드는 e001부터 e999까지 선택하세요.")
                    return
                self._hmb_color_lut_state["manual_episode"] = episode
                self._hmb_color_lut_state["revision"] += 1
                self._web_upload_epoch += 1
                self._web_upload_context = {}
                self._web_upload_probe_key = ""
                self._publish()
                self._schedule_upload_probe()
                return
            if action == "select_upload_project":
                if captured["shot"].get("shot_uuid"):
                    return
                from _hmb_broker_config import load_broker_base_url
                identity = value.get("project_id")
                projects = self._manual_projects if self._manual_projects_origin == load_broker_base_url() else []
                project = next((row for row in projects if row["id"] == identity), None) if identity else {}
                if project is None:
                    self._status("error", "서버 프로젝트 목록에서 선택하세요.")
                    self._schedule_manual_projects()
                    return
                self._remember_selection()
                if project != captured["manual_project"]:
                    self._hmb_color_lut_state["manual_episode"] = ""
                    self._episode_key, self._episode_codes = None, []
                self._hmb_color_lut_state.update(manual_project=copy.deepcopy(project), project=copy.deepcopy(project), project_id=project.get("id", ""))
                self._hmb_color_lut_state["preset_id"] = ""
                try:
                    revision = max(0, min(2**53 - 2, int(authored.get("revision") or 0))) if isinstance(authored, Mapping) else 0
                except (TypeError, ValueError, OverflowError):
                    revision = 0
                self._hmb_color_lut_state["revision"] = max(captured["revision"], revision) + 1
                self._web_upload_epoch += 1
                self._web_upload_probe_key = ""
                self._web_upload_context = {}
                self._remember_selection()
                self._publish()
                self._schedule_upload_probe()
                self._schedule_episodes()
                return
            if action == "delete_profile":
                # Deletion never reapplies authored grading/media/output fields.
                try:
                    revision = max(0, min(2**53 - 2, int(authored.get("revision") or 0))) if isinstance(authored, Mapping) else 0
                except (TypeError, ValueError, OverflowError):
                    revision = 0
                self._hmb_color_lut_state["revision"] = max(self._hmb_color_lut_state["revision"], revision) + 1
                self._delete_profile(captured, value, authored)
                return
            if isinstance(authored, Mapping) and _selection_key(authored) == _selection_key(captured):
                # A native onCommand need not echo the property edit first.
                # Advance beyond that captured browser revision so worker
                # readiness/completion publications are accepted immediately.
                try:
                    authored_revision = max(0, min(2**53 - 2, int(authored.get("revision") or 0)))
                except (TypeError, ValueError, OverflowError):
                    authored_revision = self._hmb_color_lut_state["revision"]
                self._hmb_color_lut_state["revision"] = max(self._hmb_color_lut_state["revision"], authored_revision) + 1
                captured["settings"] = normalize_settings(authored.get("settings", captured["settings"]))
                captured["audio_mix"] = normalize_audio_mix(authored.get("audio_mix", captured["audio_mix"]))
                captured["preset_name"] = str(authored.get("preset_name") or "")[:80]
                captured["preset_id"] = _profile_id(authored.get("preset_id", captured.get("preset_id")))
                raw = authored.get("output")
                if isinstance(raw, Mapping):
                    captured["output"] = _output(raw)
                self._hmb_color_lut_state["settings"] = copy.deepcopy(captured["settings"])
                self._hmb_color_lut_state["audio_mix"] = copy.deepcopy(captured["audio_mix"])
                self._hmb_color_lut_state["output"] = copy.deepcopy(captured["output"])
                self._hmb_color_lut_state["preset_name"] = captured["preset_name"]
                self._hmb_color_lut_state["preset_id"] = captured["preset_id"]
                self._remember_selection()
            if action == "save_profile":
                self._save_profile(captured, authored)
                return
            if action == "upload_web":
                retry_context = self._web_upload_context if self._web_upload.get("phase") == "media_retry" else {}
                self._start_web_upload(captured, artifact=retry_context.get("artifact", "source"),
                                       check_only=value.get("check_only") is True, repair_receipt=retry_context.get("receipt_id", ""))
                return
            if action not in {"export", "export_upload", "browse_video"}:
                return
            self._cancel = threading.Event()
            self._job_id = request_id
            if action in {"export", "export_upload"}:
                if captured["audio_mix"]["enabled"]:
                    try:
                        captured["_sound_snapshot"] = self._capture_sound_snapshot(captured)
                    except Exception as exc:
                        self._status("error", str(exc))
                        return
                if action == "export_upload":
                    retry = captured.get("result", {}).get("review_media_retry", {})
                    if (isinstance(retry, dict) and retry.get("receipt") and retry.get("stamp") == self._upload_state_stamp(captured)
                            and retry.get("output") == captured["output"]):
                        self._start_web_upload(captured, artifact="export", chained=True, repair_receipt=retry["receipt"])
                        return
                    try:
                        if self._upload_projection().get("phase") == "offline":
                            raise ValueError("브로커가 응답하지 않아 웹 업로드를 사용할 수 없습니다.")
                        self._upload_source_context(captured)
                        if CODEC_EXTENSIONS[captured["output"]["codec"]] not in {".mov", ".mp4"}:
                            raise ValueError("웹 업로드에는 MOV 또는 MP4 출력 형식을 선택하세요.")
                    except Exception as exc:
                        self._status("error", str(exc))
                        return
                    captured["_upload_chain"] = {"stamp": self._export_operation_stamp(captured),
                        "source_token": self._source_token, "route_epoch": self._web_upload_epoch}
                # Capture before dispatch: changing the active workflow mid-export
                # must not redirect this export's collection to another project.
                try:
                    captured["data_directory"] = str(_workflow_data_directory())
                except Exception as exc:
                    self._status("error", f"Unable to resolve the workflow data folder: {exc}")
                    return
                if action == "export":
                    try:
                        self._capture_usage_operation(captured)
                    except Exception:
                        LOGGER.debug("Color LUT optional usage snapshot unavailable")
            key, cancel = _selection_key(captured), self._cancel
            self._status("working", "Loading video…" if action == "browse_video" else "Processing original source…")
            self._worker = threading.Thread(target=contextvars.copy_context().run, args=(self._run_command, action, captured, request_id, key, cancel), name="HMB LUT export", daemon=True)
            self._worker.start()

    def _save_profile(self, state: dict[str, Any], authored: Any) -> None:
        try:
            with _PROFILE_LOCK:
                rows = _read_profile_rows()
                name = str((authored if isinstance(authored, Mapping) else state).get("preset_name") or "").strip()[:80]
                if not name:
                    raise ValueError("프리셋 이름을 입력하세요. / Enter a preset name.")
                matches = [p for p in rows if isinstance(p, Mapping) and p.get("project_id", "") == state["project_id"] and p.get("name") == name]
                if len(matches) > 1:
                    raise ValueError("Duplicate personal preset names are protected. Save with a different name.")
                item = matches[0] if matches else None
                if item is None:
                    item = {"id": uuid.uuid4().hex, "project_id": state["project_id"], "name": name,
                            "scope": "local_user", "user_created": True}
                    rows.append(item)
                elif item.get("id") in (None, "") and _profile_deletable(item, allow_missing_id=True):
                    # Explicit Save upgrades only this unambiguous legacy
                    # personal row. Merely reading it never grants delete rights.
                    item["id"] = uuid.uuid4().hex
                elif not _profile_deletable(item) or sum(isinstance(p, Mapping) and p.get("id") == item["id"] for p in rows) != 1:
                    raise ValueError("This preset is protected. Save your settings with a different name.")
                item["settings"] = normalize_settings(state["settings"])
                _write_profile_rows(rows)
                self._hmb_color_lut_state["profiles"] = _profiles(rows)
                self._hmb_color_lut_state["preset_name"] = name
                self._hmb_color_lut_state["preset_id"] = item["id"]
                self._remember_selection()
        except Exception as exc:
            self._status("error", str(exc))
            return
        self._profile_committed_status("Preset saved.")

    def _delete_profile(self, state: dict[str, Any], command: Mapping[str, Any], authored: Any) -> None:
        try:
            selected = authored if isinstance(authored, Mapping) else state
            identity, project, name = command.get("preset_id"), command.get("project_id"), command.get("preset_name")
            if (not _profile_id(identity) or not isinstance(project, str) or not isinstance(name, str)
                    or project != state["project_id"] or identity != selected.get("preset_id")
                    or name != selected.get("preset_name") or not name or len(name) > 80):
                raise ValueError("Select the exact personal preset before deleting it.")
            with _PROFILE_LOCK:
                rows = _read_profile_rows()
                matches = [i for i, p in enumerate(rows) if isinstance(p, Mapping) and p.get("id") == identity]
                if len(matches) != 1:
                    raise ValueError("The selected personal preset is missing or ambiguous; nothing was deleted.")
                index = matches[0]
                item = rows[index]
                if item.get("project_id", "") != project or item.get("name") != name or not _profile_deletable(item):
                    raise ValueError("The selected preset is protected or changed; nothing was deleted.")
                _write_profile_rows(rows[:index] + rows[index + 1:])
                self._hmb_color_lut_state["profiles"] = _profiles(rows[:index] + rows[index + 1:])
                self._hmb_color_lut_state["preset_name"] = name
                self._hmb_color_lut_state["preset_id"] = ""
                self._remember_selection()
        except Exception as exc:
            self._status("error", str(exc))
            return
        self._profile_committed_status("Preset deleted.")

    def _profile_committed_status(self, message: str) -> None:
        try:
            self._status("complete", message)
        except Exception:
            # The atomic personal-store edit already succeeded. An optional
            # editor notification cannot turn that durable success into failure.
            LOGGER.debug("Color LUT committed preset notification was unavailable", exc_info=True)

    def _archive_grade(self, state: dict[str, Any], result: dict[str, Any], job_id: str) -> dict[str, str]:
        directory = Path(state["data_directory"])
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"color_lut_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:12]}"
        cube = directory / f"{stem}.cube"
        metadata = directory / f"{stem}.json"
        write_cube(cube, state["settings"])
        record = {"schema": "hmb-color-lut-export", "version": 1, "created_at": time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            "project": state.get("project", {}), "project_id": state["project_id"], "preset_name": state.get("preset_name", ""),
            "shot": state["shot"], "source_path": state["source"].get("path", ""), "output_path": result["path"],
            "generation_id": state["source"].get("generation_id", ""), "settings": state["settings"],
            "audio_mix": _audio_mix_identity(state), "sound_tracks": result.get("sound_tracks", []),
            "codec": state["output"]["codec"], "lut_path": str(cube), "job_id": job_id}
        record["source_media"] = {key: state["source"].get(key) for key in ("width", "height", "fps", "duration", "pixel_format")}
        record["output_media"] = {key: result.get(key) for key in ("width", "height", "frame_rate", "duration", "video_codec", "pixel_format", "working_space", "cube_size", "interpolation", "color_assumptions")}
        with metadata.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
        return {"lut_path": str(cube), "metadata_path": str(metadata)}

    @staticmethod
    def _export_warning(result: dict[str, Any], stage: str, error: Exception) -> None:
        raw = result.get("postprocess_warnings")
        warnings = [{"stage": item["stage"][:80], "message": item["message"][:1024]}
                    for item in (raw if isinstance(raw, list) else [])
                    if isinstance(item, Mapping) and isinstance(item.get("stage"), str) and isinstance(item.get("message"), str)][-15:]
        warning = {"stage": stage, "message": str(error)[:1024]}
        if warning not in warnings:
            warnings.append(warning)
        result["postprocess_warnings"] = warnings

    def _retain_export_result(self, state: Mapping[str, Any], result: dict[str, Any], key: str, job_id: str) -> bool:
        """Commit the verified file independently of archive and editor services."""
        with self._lock:
            if self._hmb_node_deleted or self._job_id != job_id:
                return False
            history = self._hmb_color_lut_state["shot_states"].get(key)
            if isinstance(history, dict) and _source_identity(history.get("source")) == _source_identity(state["source"]):
                history["result"] = copy.deepcopy(result)
            current = (key == _selection_key(self._hmb_color_lut_state)
                       and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]))
            if current:
                self._hmb_color_lut_state["result"] = copy.deepcopy(result)
                warnings = result.get("postprocess_warnings", [])
                message = str(result["path"])
                if warnings:
                    prefix = "영상 저장 완료 · 후처리 경고" if self._hmb_color_lut_state["language"] == "ko" else "Video saved · Postprocessing warning"
                    message = f"{prefix}: {message}. " + "; ".join(f"{item['stage']}: {item['message']}" for item in warnings)
                self._hmb_color_lut_state["status"] = {"phase": "complete", "message": message, "progress": 1}
            return current

    def _finish_local_export(self, state: dict[str, Any], result: dict[str, Any], key: str, job_id: str,
                             cancel: threading.Event, *, upload_after_save: bool = False) -> None:
        # export_video has already probed the complete artifact and published
        # it exclusively. Cancellation before this commit still publishes no
        # result; cancellation during optional work cannot undo a saved file.
        with self._lock:
            if self._hmb_node_deleted or self._job_id != job_id:
                return
            if cancel.is_set():
                if key == _selection_key(self._hmb_color_lut_state) and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]):
                    try:
                        self._status("cancelled", "취소되었습니다." if self._hmb_color_lut_state["language"] == "ko" else "Cancelled.")
                    except Exception:
                        LOGGER.debug("Color LUT cancellation notification deferred", exc_info=True)
                return
            self._retain_export_result(state, result, key, job_id)
        # Only/manual exports did not previously need a checksum. Publish the
        # saved player first so this new optional read cannot leave it loading.
        early_preview = bool(not state["shot"].get("shot_uuid") and state.get("_usage_export"))
        if early_preview:
            result["usage_collection"] = {"export_operation_id": state["_usage_export"]["operation_id"],
                "local_export": {"phase": "pending", "reason": "checksum_pending"}}
            try:
                result["url"] = _media_url(Path(result["path"]))
            except Exception as exc:
                result["url"] = ""
                self._export_warning(result, "preview", exc)
            current = self._retain_export_result(state, result, key, job_id)
            if current:
                for stage, callback in (("output_notification", lambda: self._publish_result_url(result.get("url", ""))),
                                        ("ui_notification", self._publish)):
                    with self._lock:
                        if (self._hmb_node_deleted or self._job_id != job_id
                                or key != _selection_key(self._hmb_color_lut_state)
                                or _source_identity(state["source"]) != _source_identity(self._hmb_color_lut_state["source"])):
                            break
                        try:
                            callback()
                        except Exception as exc:
                            self._export_warning(result, stage, exc)
        usage_event: dict[str, Any] = {}
        try:
            usage_event = self._capture_usage_artifact(state, result, cancel)
        except Exception:
            captured = state.get("_usage_export") or {}
            operation = captured.get("operation_id", "")
            result["usage_collection"] = {"export_operation_id": operation,
                "local_export": {"phase": "not_collected", "reason": "cancelled" if cancel.is_set()
                                 else "statistics_metadata_unavailable" if captured.get("artifact") else "export_hash_unavailable"}}
            LOGGER.debug("Color LUT verified export usage hash unavailable")
        archive_ok = False
        try:
            result.update(self._archive_grade(state, result, job_id))
            archive_ok = True
        except Exception as exc:
            result.pop("web_export_proof", None)
            self._export_warning(result, "archive", exc)
        if not early_preview:
            try:
                result["url"] = _media_url(Path(result["path"]))
            except Exception as exc:
                result["url"] = ""
                self._export_warning(result, "preview", exc)
        if archive_ok:
            try:
                self._record_export_proof(state, result, cancel)
            except Exception as exc:
                result.pop("web_export_proof", None)
                self._export_warning(result, "web_receipt", exc)
        current = self._retain_export_result(state, result, key, job_id)
        if upload_after_save and current and result.get("web_export_proof"):
            try:
                self._continue_export_upload(state, cancel, result["web_export_proof"])
            except Exception as exc:
                self._export_warning(result, "web_upload", exc)
        # Each notification is independent: a broken output subscriber or UI
        # bridge must not reclassify a successfully saved local video as error.
        callbacks = [("output_notification", lambda: self._publish_result_url(result.get("url", "")))] if current and not early_preview else []
        callbacks.append(("upload_probe", self._schedule_upload_probe))
        for stage, callback in callbacks:
            with self._lock:
                if self._hmb_node_deleted or self._job_id != job_id:
                    return
                if stage == "output_notification" and (key != _selection_key(self._hmb_color_lut_state)
                        or _source_identity(self._hmb_color_lut_state["source"]) != _source_identity(state["source"])):
                    continue
                try:
                    callback()
                except Exception as exc:
                    self._export_warning(result, stage, exc)
                    self._retain_export_result(state, result, key, job_id)
                    LOGGER.debug("Color LUT saved export notification deferred: %s", stage, exc_info=True)
        # Publish the final dashboard once. Only use a silent recovery write if
        # the native publication path fails; normal exports need no duplicate
        # full-state publication.
        with self._lock:
            if self._hmb_node_deleted or self._job_id != job_id:
                return
            self._retain_export_result(state, result, key, job_id)
            try:
                self._publish()
            except Exception as exc:
                self._export_warning(result, "ui_notification", exc)
                self._retain_export_result(state, result, key, job_id)
                try:
                    _set_parameter_silently(self, UI, copy.deepcopy(self._hmb_color_lut_state))
                except Exception as storage_error:
                    self._export_warning(result, "state_storage", storage_error)
                    self._retain_export_result(state, result, key, job_id)
                LOGGER.debug("Color LUT saved export UI notification deferred", exc_info=True)
        if usage_event:
            try:
                captured = state["_usage_export"]
                self._queue_usage_event(usage_event, captured["origin"],
                                        captured_bridge=captured["bridge"], captured_login=True)
            except Exception:
                self._usage_status(usage_event["export_operation_id"], "local_export", "not_collected", "statistics_unavailable")
                LOGGER.debug("Color LUT optional usage dispatch unavailable")

    def _hmb_follow_image_asset_project(self, project: Any) -> None:
        project = dict(project) if isinstance(project, Mapping) else {}
        with self._lock:
            self._project_authoritative = True
            self._bound_project = copy.deepcopy(project)
            state = self._hmb_color_lut_state
            if not state["shot"].get("shot_uuid") and state.get("manual_project"):
                return
            if state["project"] == project:
                return
            project_id = str(project.get("id") or "")
            if project_id != state["project_id"]:
                # On first discovery retain the already-authored grade and source;
                # later project changes are isolated like Shot changes.
                if not state["project_id"]:
                    state["project_id"] = project_id
                else:
                    self._switch(state["shot"], project_id)
            state["project"] = project
            state["revision"] += 1
            self._remember_selection()
        self._publish()

    def _run_command(self, action: str, state: dict[str, Any], job_id: str, key: str, cancel: threading.Event) -> None:
        try:
            if action == "browse_video":
                path = _browse()
                with self._lock:
                    if path and key == _selection_key(self._hmb_color_lut_state) and not self._hmb_node_deleted and not cancel.is_set():
                        if self._hmb_color_lut_state["shot"].get("shot_uuid"):
                            raise ValueError("Use Only for a manual file, or use the matching Shot's Generator result.")
                        self._queue_source({"path": path})
                self._status("idle")
                return
            source = str(state["source"].get("path") or "")
            shot, src = state["shot"], state["source"]
            if shot.get("shot_uuid") and (src.get("shot_uuid") != shot["shot_uuid"] or src.get("channel_uuid") != shot["channel_uuid"] or src.get("completed") is not True):
                raise ValueError("The completed video does not belong to this Shot.")
            output = state["output"]
            codec = str(output.get("codec") or "hevc10")
            if codec not in CODEC_EXTENSIONS:
                raise ValueError("Unknown output codec.")
            if output.get("manual_output_enabled"):
                if not str(output.get("path") or "").strip():
                    raise ValueError("Enter the destination file path.")
                destination = Path(output["path"]).expanduser()
                if not destination.is_absolute():
                    raise ValueError("Output must be an absolute file path.")
                # Saved HEVC destinations used MP4 before MOV became the
                # delivery container. Only a new export changes its suffix;
                # existing results, receipts and their upload identity stay intact.
                if codec == "hevc10" and destination.suffix.lower() == ".mp4":
                    destination = destination.with_suffix(".mov")
            else:
                if not source:
                    raise ValueError("Load a video or explicitly choose an output path.")
                suffix = CODEC_EXTENSIONS[codec]
                original = Path(source)
                destination = original.with_name(f"{original.stem}_LUT_{time.strftime('%Y%m%d_%H%M%S')}_{job_id[-6:]}{suffix}")
            if cancel.is_set():
                if key == _selection_key(self._hmb_color_lut_state):
                    self._status("cancelled", "취소되었습니다." if self._hmb_color_lut_state["language"] == "ko" else "Cancelled.")
                return
            if action == "export_upload" and state["result"].get("web_export_proof"):
                try:
                    reusable = self._export_upload_proof(state)
                    if reusable.get("output") != _output(state["output"]):
                        raise ValueError("Choose a fresh export for the current output settings.")
                except (ValueError, OSError):
                    pass
                else:
                    # Also after restart/unknown receipt: retrieve the same
                    # exported bytes rather than re-encoding a replacement.
                    self._continue_export_upload(state, cancel, state["result"]["web_export_proof"])
                    return
            if action in {"export", "export_upload"}:
                if not source:
                    raise ValueError("No matching completed video is loaded.")
                directory = Path(state["data_directory"])
                directory.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=directory):
                    pass
                last_update = [0.0]
                def progress(value: Any) -> None:
                    now = time.monotonic()
                    if now - last_update[0] < .2:
                        return
                    last_update[0] = now
                    if key == _selection_key(self._hmb_color_lut_state) and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"]) and not self._hmb_node_deleted:
                        self._status("working", "Encoding original source…", float(value))
                audio_kwargs = {}
                if state.get("audio_mix", {}).get("enabled"):
                    from _hmb_sound import resolve_sound_tracks
                    tracks = resolve_sound_tracks(state["_sound_snapshot"], channel_uuid=shot.get("channel_uuid", ""),
                        shot_uuid=shot.get("shot_uuid", ""), project_id=state["_sound_snapshot"].get("project_id", ""))
                    tracks = [track for track in tracks if track.get("purpose", "both") in {"mix", "both"}]
                    audio_kwargs = {"sound_tracks": tracks, "original_audio": state["audio_mix"]["original_audio"]}
                result = export_video(source, destination, state["settings"], codec=codec, cancel_event=cancel, progress=progress, **audio_kwargs)
                if state.get("audio_mix", {}).get("enabled"):
                    result["sound_contract_sha256"] = _digest(state["_sound_snapshot"])
            result = {**result, "shot": state["shot"], "project_id": state["project_id"], "settings": state["settings"], "job_id": job_id}
            if action in {"export", "export_upload"}:
                self._finish_local_export(state, result, key, job_id, cancel, upload_after_save=action == "export_upload")
        except Exception as exc:
            with self._lock:
                if (self._job_id == job_id and key == _selection_key(self._hmb_color_lut_state)
                        and _source_identity(self._hmb_color_lut_state["source"]) == _source_identity(state["source"])
                        and not self._hmb_node_deleted):
                    try:
                        self._status("cancelled" if cancel.is_set() else "error", str(exc))
                    except Exception:
                        LOGGER.debug("Color LUT failed operation notification deferred", exc_info=True)

    def _export_operation_stamp(self, state: Mapping[str, Any]) -> str:
        return _digest([_selection_key(state), _source_identity(state.get("source")),
                        normalize_settings(state.get("settings")), _audio_mix_identity(state), _output(state.get("output")),
                        state.get("manual_project"), state.get("manual_episode") if not state["shot"].get("shot_uuid") else ""])

    def _continue_export_upload(self, state: dict[str, Any], cancel: threading.Event, proof_id: str) -> None:
        chain = state.get("_upload_chain", {})
        with self._lock:
            current = self._hmb_color_lut_state
            if (cancel.is_set() or self._hmb_node_deleted
                    or current["result"].get("web_export_proof") != proof_id
                    or chain.get("stamp") != self._export_operation_stamp(current)
                    or chain.get("source_token") != self._source_token
                    or chain.get("route_epoch") != self._web_upload_epoch):
                return
            captured = copy.deepcopy(current)
            current["status"] = {"phase": "complete", "message": str(current["result"].get("path") or ""), "progress": 1}
        # This continuation is authorized by the output-and-upload click. A
        # failed upload never changes the completed local file into a failure.
        self._start_web_upload(captured, artifact="export", chained=True, cancel_event=cancel)

    def _hmb_shot_channel_subscription(self) -> dict[str, Any]:
        shot = self._hmb_color_lut_state["shot"]
        enabled = bool(shot.get("channel_uuid") and shot.get("shot_uuid") and not self._hmb_node_deleted)
        return {"schema": "hmb-shot-channel-subscription", "version": 1, "participant_kind": "color_lut",
            "enabled": enabled, "channel_uuid": shot.get("channel_uuid", "") if enabled else "",
            "shot_uuid": shot.get("shot_uuid", "") if enabled else "", "shot_number": shot.get("number", 1), "shot_name": shot.get("name", "Only")}

    def _hmb_prepare_initial_shot_selection(self, shot_uuid: Any = "") -> None:
        if self._hmb_initial_shot_autoclaim_pending:
            self._hmb_initial_shot_preferred_uuid = str(shot_uuid or "")

    @hmb_binding_mutation
    def _hmb_reconcile_shot_routing(self, snapshot: Any) -> None:
        catalog = _normalize_shot_catalog(snapshot, strict=True)
        with self._lock:
            previous = self._hmb_color_lut_state["shot_catalog"]
            if previous.get("channel_uuid") == catalog.get("channel_uuid") and int(previous.get("generation", 0)) > catalog["generation"]:
                return
            self._hmb_color_lut_state["shot_catalog"] = catalog
            shot = _normalize_shot_selection(self._hmb_color_lut_state["shot"], catalog)
            if self._hmb_initial_shot_autoclaim_pending and self._hmb_initial_shot_preferred_uuid:
                match = next((s for s in catalog["shots"] if s["shot_uuid"] == self._hmb_initial_shot_preferred_uuid), None)
                if match:
                    shot = {"channel_uuid": catalog["channel_uuid"], **{k: match[k] for k in ("shot_uuid", "number", "name")}}
                    self._hmb_initial_shot_autoclaim_pending = False
            if shot != self._hmb_color_lut_state["shot"]:
                self._switch(shot)
                self._hmb_color_lut_state["revision"] += 1
        self._publish()

    @hmb_binding_mutation
    def _hmb_clear_shot_routing_catalog(self, reason: str = "publisher_unavailable") -> dict[str, Any]:
        with self._lock:
            self._hmb_color_lut_state["shot_catalog"] = {}
            self._switch(_shot_only())
            self._hmb_initial_shot_autoclaim_pending = False
            self._hmb_color_lut_state["revision"] += 1
        self._publish()
        return self._hmb_shot_channel_subscription()

    def _hmb_shot_routing_status(self, value: Any) -> None:
        self._route_status = copy.deepcopy(value)
        if isinstance(value, Mapping) and value.get("code") != "ready":
            with self._lock:
                shot = self._hmb_color_lut_state["shot"]
                # A successful Only reconciliation confirms there is no Shot
                # route. Manual upload is owned by the local source and project.
                if (value.get("code") == "only" and value.get("ok") is True
                        and not shot.get("channel_uuid") and not shot.get("shot_uuid")):
                    return
                self._web_upload_context = {}
                self._web_upload_probe_key = ""
                self._web_upload_epoch += 1
                self._web_upload_wake.set()
                self._web_upload["enabled"] = False
            self._publish()
        else:
            self._schedule_upload_probe()

    def _hmb_hydrate_color_lut_from_source(self, source: Any, source_parameter: str = "HMB_GENERATED_VIDEO_SOURCE") -> bool:
        reader = getattr(source, "_hmb_generated_video_source_snapshot", None)
        snapshot = reader() if callable(reader) else None
        if not isinstance(snapshot, Mapping) or not snapshot:
            return False
        shot = self._hmb_color_lut_state["shot"]
        if snapshot.get("shot_uuid") != shot.get("shot_uuid") or snapshot.get("channel_uuid") != shot.get("channel_uuid"):
            return False
        _set_parameter_silently(self, SOURCE, snapshot)
        self._queue_source(snapshot)
        return True

    def _reconcile(self) -> None:
        try:
            from _hmb_shot_routing import reconcile_shot_routing
            reconcile_shot_routing(self)
        except Exception:
            LOGGER.debug("Color LUT routing deferred", exc_info=True)

    def _hmb_post_registration_shot_discovery(self) -> None:
        if not self._hmb_node_deleted:
            self._reconcile()
            self._hmb_post_hydration_state_restore()
            self._schedule_manual_projects()

    def _hmb_post_hydration_state_restore(self) -> None:
        with self._lock:
            state = self._hmb_color_lut_state
            if not self._hmb_node_deleted and self._hydrated:
                self._receive_sound(_raw_parameter(self, SOUND_IN))
            if not self._hmb_node_deleted and self._hydrated and not state["shot"].get("shot_uuid") and state["source"].get("path"):
                self._queue_source(state["source"])
            if self._hydrated and state.get("manual_group_id"):
                self._schedule_episodes()

    @hmb_binding_mutation
    def set_parameter_value(self, name: str, value: Any, *args: Any, **kwargs: Any) -> Any:
        lock = getattr(self, "_lock", None)
        if lock is None:
            return super().set_parameter_value(name, value, *args, **kwargs)
        # Publication owns this same lock. A concurrent saved value must wait
        # until _syncing clears; only same-thread publication echoes may skip it.
        with lock:
            saved = (kwargs.get("initial_setup") is True and name == UI
                     and not self._syncing and not self._hmb_node_deleted and isinstance(value, Mapping))
            if saved:
                value = copy.deepcopy(value)
                value.pop("__hmb_color_lut_command__", None)
                supplied_project = str(value.get("project_id") or "")
                current_project = str(self._hmb_color_lut_state.get("project_id") or "")
                manual = _upload_project(value.get("manual_project"))
                manual_restore = bool(manual and supplied_project == manual["id"] and isinstance(value.get("shot"), Mapping) and not value["shot"].get("shot_uuid"))
                if self._project_authoritative and supplied_project != current_project and not manual_restore:
                    value = copy.deepcopy(self._hmb_color_lut_state)
            result = super().set_parameter_value(name, value, *args, **kwargs)
            if saved:
                self._apply_ui(value, initial_setup=True)
                # Mirror only the normalized private state. Foreign source or
                # stale project fields must not remain visible in native UI.
                super().set_parameter_value(name, copy.deepcopy(self._hmb_color_lut_state), *args, **kwargs)
        if saved and not self._hmb_node_deleted:
            try:
                from _hmb_shot_routing import schedule_post_hydration_reconcile
                schedule_post_hydration_reconcile(self)
            except Exception:
                LOGGER.debug("Color LUT hydration discovery deferred", exc_info=True)
        return result

    @hmb_binding_mutation
    def after_value_set(self, parameter: Any, value: Any) -> Any:
        # Wait for another thread\'s publication; only same-thread echoes may be skipped.
        with self._lock:
            parent = getattr(super(), "after_value_set", None)
            result = parent(parameter, value) if callable(parent) else None
            if self._syncing or self._hmb_node_deleted:
                return result
            name = str(getattr(parameter, "name", ""))
            if name == UI:
                self._apply_ui(value)
            elif name == COMMAND:
                self._command(value)
            elif name == SOURCE:
                self._queue_source(value)
            elif name == SOUND_IN:
                self._receive_sound(value)
            return result

    def process(self) -> None:
        # Workflow traversal only refreshes the source; paid upstream generation
        # is never invoked by the widget's local preview/export commands.
        # _queue_source publishes when the source actually changes. A second
        # unconditional full-state publication here duplicates that large
        # payload and can stall the editor without changing any output.
        self._queue_source(_raw_parameter(self, SOURCE))
        self._receive_sound(_raw_parameter(self, SOUND_IN))

    def after_node_deleted(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._hmb_node_deleted:
                return None
            self._hmb_node_deleted = True
            if getattr(self, "_mov_preview_cancel", None) is not None:
                self._mov_preview_cancel.set()
            self._source_token += 1
            self._cancel.set()
            self._web_upload_wake.set()
        try:
            from _hmb_shot_routing import prepare_node_deletion, release_node_lifecycle, schedule_post_deletion_reconcile
            prepare_node_deletion(self)
            release_node_lifecycle(self)
            schedule_post_deletion_reconcile(self)
        except Exception:
            LOGGER.debug("Color LUT deletion reconciliation deferred", exc_info=True)
        parent = getattr(super(), "after_node_deleted", None)
        return parent(*args, **kwargs) if callable(parent) else None
