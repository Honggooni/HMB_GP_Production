"""Per-workstation registration folders shared by ImageAsset and Sound."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import stat
import tempfile
import threading
import unicodedata
import uuid


DEFAULT = {"links": [], "write_site_id": "hq", "revision": "0"}
_ID = re.compile(r"site-[0-9a-f]{32}\Z")
_CACHE = {}
_CACHE_LOCK = threading.RLock()
_DIRECTORY_LOCKS = {}
_DIRECTORY_STATUS = {}


def _default():
    return {**DEFAULT, "links": []}


@lru_cache(maxsize=4)
def _desktop_workspace(appdata):
    if appdata:
        try:
            config = Path(appdata) / "Griptape Nodes" / "gtn-workspace.json"
            value = json.loads(config.read_text(encoding="utf-8-sig"))["workspaceDirectory"]
            if value and Path(value).is_absolute():
                return Path(value)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return Path.home() / "Documents" / "GriptapeNodes"


def _workspace():
    directory = os.environ.get("GTN_CONFIG_WORKSPACE_DIRECTORY", "")
    try:
        from griptape_nodes.retained_mode.engine import has_current_engine
        from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
        if has_current_engine():
            directory = GriptapeNodes.ConfigManager().configured_global_workspace_path()
    except (ImportError, AttributeError, RuntimeError, OSError, ValueError):
        pass
    if directory and Path(directory).is_absolute():
        return Path(directory)
    return _desktop_workspace(os.environ.get("APPDATA", ""))


@lru_cache(maxsize=1)
def _station():
    # A shared Griptape workspace can be mounted by both studios.
    material = platform.node().casefold() + "\n" + str(Path.home()).casefold()
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def settings_path(project_root, media="image"):
    if media not in ("image", "sound"):
        raise ValueError("등록 폴더의 미디어 종류를 확인하세요.")
    if not project_root:
        raise ValueError("프로젝트를 먼저 선택하세요.")
    root = Path(project_root)
    if not root.is_absolute() and PureWindowsPath(project_root).is_absolute():
        root = PureWindowsPath(project_root)
    if not root.is_absolute():
        raise ValueError("본사 프로젝트 절대 경로를 확인하세요.")
    # Use the existing logical project key for Griptape project/Ai_Ct_image roots,
    # which must work when a saved workflow uses a different mount spelling.
    project = root.parent.name if root.name.casefold() in ("ai_ct_image", "ai_ct_audio") else root.name
    if not project:
        raise ValueError("프로젝트 이름을 확인하세요.")
    key = hashlib.sha256(unicodedata.normalize("NFC", project).casefold().encode("utf-8")).hexdigest()
    return _workspace() / ".json" / "hmb_image_asset_sites" / _station() / (key + "." + media + ".json")


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return _default()
    if (not isinstance(value, dict) or value.get("version") != 2
            or not isinstance(value.get("links"), list)
            or not isinstance(value.get("revision"), str) or not value["revision"]):
        raise ValueError("저장된 등록 폴더 설정을 읽을 수 없습니다.")
    ids = {"hq"}
    for link in value["links"]:
        if (not isinstance(link, dict) or not _ID.fullmatch(str(link.get("id")))
                or link["id"] in ids or not isinstance(link.get("root"), str)
                or not Path(link["root"]).is_absolute() or not isinstance(link.get("label"), str)):
            raise ValueError("저장된 등록 폴더 정보를 확인하세요.")
        ids.add(link["id"])
    if value.get("write_site_id") not in ids:
        raise ValueError("저장된 Add 대상이 연결 목록에 없습니다.")
    return {key: value[key] for key in DEFAULT}


def _copy_profile(value):
    return {**value, "links": [dict(link) for link in value["links"]]}


def get_site_settings(project_root, media="image", *, fresh=False):
    if not project_root:
        return _default()
    path = settings_path(project_root, media)
    with _CACHE_LOCK:
        if fresh or path not in _CACHE:
            _CACHE[path] = _read(path)
        return _copy_profile(_CACHE[path])


def _media_root(value):
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("원본 미디어 폴더의 절대 경로를 선택하세요.")
    raw = os.fspath(value)
    path = Path(raw)
    windows = raw.replace("/", "\\")
    if (not path.is_absolute() or not path.name or ".." in path.parts
            or any(ord(c) < 32 for c in raw) or windows.startswith(("\\\\?\\", "\\\\.\\"))
            or any(part.casefold() == ".json" for part in path.parts)):
        raise ValueError("원본 미디어 폴더의 절대 경로를 선택하세요.")
    return path


def _plain_directory(path):
    attributes = path.lstat()
    if (stat.S_ISLNK(attributes.st_mode)
            or getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f"연결 경로 대신 실제 등록 폴더를 선택하세요: {path}")
    if not stat.S_ISDIR(attributes.st_mode):
        raise ValueError(f"등록 폴더 경로에 같은 이름의 파일이 있습니다: {path}")


def _check_directory_route(path):
    for ancestor in reversed(path.parents):
        _plain_directory(ancestor)
    _plain_directory(path)


def ensure_registration_directory(media_root, *, refresh=False):
    """Prepare metadata on a catalog read; never create the source root or a registry file."""
    root = _media_root(media_root)
    with _CACHE_LOCK:
        lock = _DIRECTORY_LOCKS.get(root)
        if lock is None:
            lock = _DIRECTORY_LOCKS[root] = threading.Lock()
    with lock:
        if not refresh and root in _DIRECTORY_STATUS:
            return _DIRECTORY_STATUS[root]
        _DIRECTORY_STATUS.pop(root, None)
        status = ""
        try:
            _check_directory_route(root)
            directory = root / ".json"
            try:
                _plain_directory(directory)
            except FileNotFoundError:
                try:
                    directory.mkdir()
                except FileExistsError:
                    pass  # Another workstation can initialize this folder concurrently.
                _plain_directory(directory)
        except OSError as error:
            status = (f"등록 폴더를 준비할 수 없습니다 ({root / '.json'}). "
                      f"공유 폴더 연결과 권한을 확인한 뒤 새로고침하세요. {error}")
        _DIRECTORY_STATUS[root] = status
        return status


def _external_folder(project, value):
    if not isinstance(value, str) or any(ord(ch) < 32 for ch in value):
        raise ValueError("외주 공유 폴더의 절대 경로를 입력하세요.")
    value = value.strip()
    external = _media_root(value)
    try:
        _check_directory_route(external)
    except OSError as error:
        raise ValueError("접근할 수 있는 외주 프로젝트 폴더를 선택하세요.") from error
    resolved = external.resolve(strict=True)
    headquarters = Path(project).resolve(strict=True)
    if (not resolved.name or any(part.casefold() == ".json" for part in resolved.parts)
            or resolved.is_relative_to(headquarters) or headquarters.is_relative_to(resolved)):
        raise ValueError("본사 폴더와 겹치지 않는 별도의 외주 프로젝트 폴더를 선택하세요.")
    # Keep the user's drive spelling, including P:, instead of persisting resolved UNC.
    return external.as_posix(), resolved


def _folder_identity(resolved):
    # Windows expands a mapped drive to UNC. Include the server and share:
    # two studios can both have projects/show/Ai_Ct_image on separate servers.
    anchor = unicodedata.normalize("NFC", os.path.normcase(str(resolved)))
    return "site-" + hashlib.sha256(anchor.encode("utf-8")).hexdigest()[:32]


def verify_folder_identity(root, project, site_id):
    """Resolve a stored route before I/O so a remapped drive cannot change its owner."""
    _, resolved = _external_folder(project, str(root))
    if _folder_identity(resolved) != site_id:
        raise ValueError("공유 폴더의 연결 대상이 변경됐습니다. 프로젝트 Add에서 경로를 확인하세요.")
    return resolved


@contextmanager
def _settings_lock(path):
    with path.with_suffix(".lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if not lock.tell():
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def _links_for_save(project_root, current, links, write_site_id):
    if not isinstance(links, list) or len(links) > 128 or not isinstance(write_site_id, str):
        raise ValueError("등록 폴더 목록과 Add 대상을 확인하세요.")
    old = {item["id"]: item for item in current["links"]}
    ids = {"hq": "hq"}
    keys = set()
    resolved_roots = []
    result = []
    for item in links:
        if not isinstance(item, dict):
            raise ValueError("등록 폴더 정보를 확인하세요.")
        draft_id, label, value = (item.get(k) for k in ("id", "label", "root"))
        if (not isinstance(draft_id, str) or not draft_id or len(draft_id) > 128 or draft_id in ids
                or not isinstance(label, str) or not label.strip() or len(label) > 128
                or any(ord(c) < 32 for c in label)):
            raise ValueError("각 등록 폴더에 고유한 식별자와 표시 이름을 지정하세요.")
        retained = old.get(draft_id)
        same = retained is not None and value == retained["root"]
        if same:
            # An unplugged read-only peer must not block changing other links,
            # including selecting a healthy Add target or removing the peer.
            root = retained["root"]
            resolved = Path(root)
            site_id = retained["id"]
        else:
            root, resolved = _external_folder(project_root, value)
            site_id = _folder_identity(resolved)
            if retained and site_id != retained["id"]:
                raise ValueError("다른 폴더는 새 연결로 추가하세요.")
        if (site_id in keys or any(resolved.is_relative_to(other) or other.is_relative_to(resolved)
                                   for other in resolved_roots)):
            raise ValueError("같거나 겹치는 등록 폴더를 두 번 연결할 수 없습니다.")
        keys.add(site_id)
        resolved_roots.append(resolved)
        result.append({"id": site_id, "label": label.strip(), "root": root})
        ids[draft_id] = site_id
    if write_site_id not in ids:
        raise ValueError("연결된 폴더 하나를 Add 대상으로 선택하세요.")
    return result, ids[write_site_id]


def save_site_settings(project_root, links, write_site_id, expected_revision=None, *, media="image"):
    path = settings_path(project_root, media)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _settings_lock(path):
        current = _read(path)
        if expected_revision is not None and current["revision"] != expected_revision:
            raise ValueError("다른 창에서 등록 폴더 설정이 변경됐습니다. 다시 열어 확인하세요.")
        validated, target = _links_for_save(project_root, current, links, write_site_id)
        if current["links"] == validated and current["write_site_id"] == target:
            with _CACHE_LOCK:
                _CACHE[path] = current
            return _copy_profile(current)
        result = {"links": validated, "write_site_id": target, "revision": uuid.uuid4().hex}
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"version": 2, **result}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        with _CACHE_LOCK:
            _CACHE[path] = result
    return _copy_profile(result)
