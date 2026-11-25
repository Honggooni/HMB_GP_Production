"""Per-workstation registration folders shared by ImageAsset and Sound."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import asyncio
import contextvars
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


DEFAULT = {"links": [], "write_site_id": "hq", "selected_site_id": "", "revision": "0", "generation": 0}
_ID = re.compile(r"site-[0-9a-f]{32}\Z")
_CACHE = {}
_CACHE_LOCK = threading.RLock()
_DIRECTORY_LOCKS = {}
_DIRECTORY_STATUS = {}
_PROFILE_DIRECTORIES = set()
_EXECUTION_WORKSPACE = contextvars.ContextVar("hmb_image_site_execution_workspace", default=None)


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
    execution_path = _EXECUTION_WORKSPACE.get()
    if execution_path is not None:
        return execution_path
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


@contextmanager
def image_execution_workspace():
    """Read the engine's configured (un-pinned) workspace once for this run."""
    directory = os.environ.get("GTN_CONFIG_WORKSPACE_DIRECTORY")
    fallback = _desktop_workspace(os.environ.get("APPDATA", ""))
    if not directory:
        try:
            from griptape_nodes.retained_mode.engine import has_current_engine
            from griptape_nodes.retained_mode.events.config_events import GetConfigLayersRequest, GetConfigValueRequest
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            if has_current_engine():
                result = GriptapeNodes.handle_request(GetConfigValueRequest(category_and_key="workspace_directory", broadcast_result=False))
                if result.succeeded():
                    directory = result.value
                    if result.source.layer == "runtime":
                        # The current project's temporary pin must not redirect
                        # workstation-wide folder settings into its workspace.
                        layers = GriptapeNodes.handle_request(GetConfigLayersRequest(broadcast_result=False))
                        directory = next((layer.values["workspace_directory"] for layer in reversed(layers.layers)
                                          if layer.layer != "runtime" and layer.values.get("workspace_directory")), None)
        except (ImportError, AttributeError, RuntimeError, OSError, ValueError):
            directory = None
    path = Path(directory).expanduser().resolve() if directory else fallback
    token = _EXECUTION_WORKSPACE.set(path)
    try:
        yield
    finally:
        _EXECUTION_WORKSPACE.reset(token)


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
    return _workspace() / ".json" / "hmb_image_asset_sites" / _station() / _profile_filename(project_root, media)


@lru_cache(maxsize=1024)
def _profile_filename(project_root, media):
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
    return key + "." + media + ".json"


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
    # Version 2 preferences predating the explicit Done control remain readable.
    value.setdefault("generation", 1)
    value.setdefault("selected_site_id", value["write_site_id"] if value["write_site_id"] != "hq"
                     else next((link["id"] for link in value["links"]), ""))
    if (type(value["generation"]) is not int or value["generation"] < 0 or not isinstance(value["selected_site_id"], str) or
            (value["selected_site_id"] and value["selected_site_id"] not in ids - {"hq"})):
        raise ValueError("저장된 폴더 선택 설정을 확인하세요.")
    return {key: value[key] for key in DEFAULT}


def _copy_profile(value):
    return {**value, "links": [dict(link) for link in value["links"]]}


def site_profiles(projects, media):
    """Publish previously linked folders from this workstation, without touching media roots."""
    if not projects:
        return {}
    directory = _workspace() / ".json" / "hmb_image_asset_sites" / _station()
    with _CACHE_LOCK:
        if (directory, media) not in _PROFILE_DIRECTORIES:
            try:
                for path in directory.glob("*." + media + ".json"):
                    if path not in _CACHE:
                        try:
                            _CACHE[path] = _read(path)
                        except (OSError, ValueError):
                            continue  # An unrelated profile must not hide healthy projects.
            except OSError:
                pass
            _PROFILE_DIRECTORIES.add((directory, media))
        if not any(p.parent == directory and p.name.endswith("." + media + ".json") and v["revision"] != "0"
                   for p, v in _CACHE.items()):
            return {}
        visible = {}
        for row in projects:
            uid = row.get("project_uid") or row.get("project_id")
            root = row.get("path") or row.get("project_root")
            if uid and root:
                profile = _CACHE.get(directory / _profile_filename(root, media))
                if profile and profile["revision"] != "0":
                    visible[uid] = _copy_profile(profile)
        return visible


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


def _ensure_plain_subdirectory(path):
    try:
        _plain_directory(path)
    except FileNotFoundError:
        path.mkdir(exist_ok=True)
        _plain_directory(path)


def _prepare_selected_folder(root):
    # Only called after the chosen root was strictly resolved and its route checked.
    # Keep existing media and registries intact, including on a repeated confirmation.
    for name in ("add", ".json"):
        try:
            _ensure_plain_subdirectory(root / name)
        except OSError as exc:
            raise ValueError(f"등록 폴더를 준비할 수 없습니다 ({root / name}). 공유 폴더 권한을 확인하세요.") from exc


def ensure_registration_directory(media_root, *, refresh=False, vendor=False):
    """Prepare metadata on a catalog read; never create the source root or a registry file."""
    root = _media_root(media_root)
    with _CACHE_LOCK:
        lock = _DIRECTORY_LOCKS.get(root)
        if lock is None:
            lock = _DIRECTORY_LOCKS[root] = threading.Lock()
    with lock:
        key = (root, vendor)
        if not refresh and key in _DIRECTORY_STATUS:
            return _DIRECTORY_STATUS[key]
        _DIRECTORY_STATUS.pop(key, None)
        status = ""
        try:
            _check_directory_route(root)
            directory = root / ".json"
            _ensure_plain_subdirectory(directory)
            if vendor:
                directory = root / "add"
                _ensure_plain_subdirectory(directory)
        except OSError as error:
            status = (f"등록 폴더를 준비할 수 없습니다 ({root}). "
                      f"공유 폴더 연결과 권한을 확인한 뒤 새로고침하세요. {error}")
        _DIRECTORY_STATUS[key] = status
        return status


def _external_folder(project, value, *, check_headquarters=True):
    if not isinstance(value, str) or any(ord(ch) < 32 for ch in value):
        raise ValueError("외주 공유 폴더의 절대 경로를 입력하세요.")
    value = value.strip()
    external = _media_root(value)
    try:
        _check_directory_route(external)
    except OSError as error:
        raise ValueError("접근할 수 있는 외주 프로젝트 폴더를 선택하세요.") from error
    resolved = external.resolve(strict=True)
    headquarters = Path(project).resolve(strict=True) if check_headquarters else _mapped_path(Path(project))
    if (not resolved.name or any(part.casefold() == ".json" for part in resolved.parts)
            or resolved.is_relative_to(headquarters) or headquarters.is_relative_to(resolved)):
        raise ValueError("본사 폴더와 겹치지 않는 별도의 외주 프로젝트 폴더를 선택하세요.")
    # Keep the user's drive spelling, including P:, instead of persisting resolved UNC.
    return external.as_posix(), resolved


def _mapped_path(path):
    """Expand the workstation's drive mapping without opening files on the share."""
    if os.name == "nt" and len(path.drive) == 2:
        import ctypes
        name = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(name))
        if ctypes.windll.mpr.WNetGetConnectionW(path.drive, name, ctypes.byref(size)) == 0:
            return Path(name.value, *path.parts[1:])
    return path


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


def save_site_settings(project_root, links, write_site_id, expected_revision=None, *, media="image",
                       existing_only=False):
    path = settings_path(project_root, media)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _settings_lock(path):
        current = _read(path)
        if expected_revision is not None and current["revision"] != expected_revision:
            raise ValueError("다른 창에서 등록 폴더 설정이 변경됐습니다. 다시 열어 확인하세요.")
        if existing_only:
            if not isinstance(expected_revision, str) or not isinstance(links, list) or any(
                    item not in current["links"] for item in links):
                raise ValueError("현재 등록된 폴더만 선택하거나 해제할 수 있습니다.")
        validated, target = _links_for_save(project_root, current, links, write_site_id)
        return _store_profile(path, current, validated, target)


def _store_profile(path, current, links, target, selected=None):
    if selected is None:
        selected = current["selected_site_id"]
        if selected not in {link["id"] for link in links}:
            selected = target if target != "hq" else next((link["id"] for link in links), "")
    result = current
    links_changed = current["links"] != links or current["write_site_id"] != target
    if links_changed or current["selected_site_id"] != selected:
        # The registration revision keys media scans and open Add commands.
        # Selecting a card only advances the presentation generation.
        result = {"links": links, "write_site_id": target, "selected_site_id": selected,
                  "revision": uuid.uuid4().hex if links_changed else current["revision"],
                  "generation": current["generation"] + 1}
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


def add_site_folder(project_root, selected, media):
    """Append to the latest profile under its lock. Inspect only the folder just chosen."""
    root, physical = _external_folder(project_root, selected, check_headquarters=False)
    site_id = _folder_identity(physical)
    path = settings_path(project_root, media)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _settings_lock(path):
        profile = _read(path)
        links = list(profile["links"])
        if not any(item["id"] == site_id for item in links):
            if len(links) >= 128:
                raise ValueError("연결 가능한 폴더 수를 초과했습니다.")
            for item in links:
                other = _mapped_path(Path(item["root"]))
                if physical.is_relative_to(other) or other.is_relative_to(physical):
                    raise ValueError("이미 연결된 폴더와 겹칩니다.")
            name = Path(root).name
            links.append({"id": site_id, "label": name[:128], "root": root})
        if media == "image":
            _prepare_selected_folder(physical)
        return _store_profile(path, profile, links, profile["write_site_id"], site_id), site_id


def confirm_site_folder(project_root, media, expected_revision, selected):
    """Verify the committed selection, preparing registration storage for images."""
    path = settings_path(project_root, media)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _settings_lock(path):
        profile = _read(path)
        # When a widget does not yet have a revision it may only acknowledge
        # the existing profile. It cannot silently overwrite someone else's selection.
        if expected_revision and expected_revision != profile["revision"]:
            raise ValueError("다른 창에서 폴더 설정이 변경되었습니다. 표시된 목록을 확인하고 완료를 다시 누르세요.")
        if media == "image" and selected == "hq":
            root = _media_root(project_root)
            _check_directory_route(root)
            _prepare_selected_folder(root)
            return _store_profile(path, profile, profile["links"], profile["write_site_id"], "")
        if selected is None or selected == "" or not expected_revision:
            selected = profile["selected_site_id"]
        if not isinstance(selected, str):
            raise ValueError("추가된 폴더 중에서 선택하세요.")
        if selected:
            link = next((item for item in profile["links"] if item["id"] == selected), None)
            if not link:
                raise ValueError("추가된 폴더 중에서 선택하세요.")
            _, physical = _external_folder(project_root, link["root"], check_headquarters=False)
            if _folder_identity(physical) != selected:
                raise ValueError("선택한 폴더의 연결 대상이 변경되었습니다. 등록 폴더를 다시 선택하세요.")
            if media == "image":
                _prepare_selected_folder(physical)
        return _store_profile(path, profile, profile["links"], profile["write_site_id"], selected)


def _windows_directory_dialog():
    """Windows Shell Common Item Dialog in folder mode (shobjidl_core.h)."""
    import ctypes as ct
    from ctypes import wintypes

    ole = ct.WinDLL("ole32")
    user = ct.WinDLL("user32")
    ptr = ct.c_void_p
    dialog, item, path = ptr(), ptr(), ptr()

    def check(hr):
        if hr < 0:
            raise OSError(f"Windows 폴더 선택 오류 (HRESULT 0x{hr & 0xffffffff:08X})")

    def method(interface, slot, *arguments):
        table = ct.cast(interface, ct.POINTER(ct.POINTER(ptr))).contents
        return ct.WINFUNCTYPE(ct.c_long, ptr, *arguments)(table[slot])

    # Only the foreground Desktop that launched this engine may own its modal.
    # A separate editor, another Desktop instance or this test harness keeps
    # its own focus and remains usable.
    user.GetForegroundWindow.restype = wintypes.HWND
    window = user.GetForegroundWindow()
    owner = None
    if window:
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(wintypes.HWND(window), ct.byref(pid))
        if pid.value in (os.getpid(), os.getppid()):
            title = ct.create_unicode_buffer(512)
            user.GetWindowTextW(wintypes.HWND(window), title, len(title))
            if "griptape" in title.value.casefold():
                owner = window

    clsid = uuid.UUID("dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7").bytes_le  # FileOpenDialog
    iid = uuid.UUID("42f85136-db7e-439c-85f1-e4075d135fc8").bytes_le    # IFileDialog
    check(ole.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED, on the picker worker
    try:
        check(ole.CoCreateInstance(clsid, None, 1, iid, ct.byref(dialog)))
        # IFileDialog::GetOptions / SetOptions; PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST
        flags = wintypes.DWORD()
        check(method(dialog, 10, ct.POINTER(wintypes.DWORD))(dialog, ct.byref(flags)))
        check(method(dialog, 9, wintypes.DWORD)(dialog, flags.value | 0x20 | 0x40 | 0x800))
        check(method(dialog, 17, wintypes.LPCWSTR)(dialog, "등록할 폴더 선택"))
        check(method(dialog, 18, wintypes.LPCWSTR)(dialog, "확인"))
        shown = method(dialog, 3, wintypes.HWND)(dialog, owner)
        if shown & 0xffffffff == 0x800704c7:  # HRESULT_FROM_WIN32(ERROR_CANCELLED)
            return ""
        check(shown)
        check(method(dialog, 20, ct.POINTER(ptr))(dialog, ct.byref(item)))  # GetResult
        check(method(item, 5, wintypes.DWORD, ct.POINTER(ptr))(item, 0x80058000, ct.byref(path)))
        return ct.wstring_at(path)  # IShellItem::GetDisplayName(SIGDN_FILESYSPATH)
    finally:
        if path:
            ole.CoTaskMemFree(path)
        if item:
            method(item, 2)(item)
        if dialog:
            method(dialog, 2)(dialog)
        ole.CoUninitialize()


def choose_site_folder():
    """Show an OS directory chooser on the workstation running the Desktop engine."""
    if os.name == "nt":
        return _windows_directory_dialog()
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    try:
        return filedialog.askdirectory(parent=window, title="등록할 폴더 선택", mustexist=True)
    finally:
        window.destroy()


def run_site_folder_command(node, project, uid, request, media, publish, *, prepare_catalog=None):
    """Run one picker or confirmation per node. Report to its originating host context."""
    request_id = request["request_id"]
    receipt = {"request_id": request_id, "project_uid": uid, "base_root": project}
    history = getattr(node, "_hmb_folder_dialog_history", None)
    if history is None:
        history = node._hmb_folder_dialog_history = {}
    if request_id in history:
        if history[request_id] is not None:
            publish(dict(history[request_id]))
        return
    if any(result is None for result in history.values()):
        publish({**receipt, "ok": False, "message": "열려 있는 폴더 선택창을 먼저 확인해 주세요."})
        return
    if len(history) >= 32:
        history.pop(next(iter(history)))
    history[request_id] = None
    context = contextvars.copy_context()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
            loop = GriptapeNodes.EventManager().event_loop
        except (ImportError, AttributeError, RuntimeError):
            loop = None

    def finish():
        if not getattr(node, "_hmb_node_deleted", False):
            history[request_id] = dict(receipt)
            publish(receipt)

    def worker():
        try:
            if request["action"] == "confirm":
                profile = confirm_site_folder(project, media, request.get("expected_revision"), request.get("selected_site_id"))
                if prepare_catalog is not None:
                    prepare_catalog(profile)
                    latest = get_site_settings(project, media, fresh=True)
                    if latest["generation"] != profile["generation"]:
                        raise ValueError("폴더 설정이 변경되었습니다. 최신 목록에서 완료를 다시 누르세요.")
                receipt.update(profile, ok=True, message="")
            else:
                selected = choose_site_folder()
                if getattr(node, "_hmb_node_deleted", False):
                    return
                if selected:
                    profile, selected_id = add_site_folder(project, selected, media)
                    receipt.update(profile, ok=True, added_site_id=selected_id, message="")
                else:
                    receipt.update(get_site_settings(project, media, fresh=True), ok=True, cancelled=True, message="")
        except (ValueError, OSError) as exc:
            receipt.update(ok=False, message=str(exc))
            try:
                receipt.update(get_site_settings(project, media, fresh=True))
            except (ValueError, OSError):
                pass
        except Exception:
            receipt.update(ok=False, message="폴더 선택창을 열 수 없습니다. Desktop에서 다시 시도하세요.")
        if loop is not None and loop.is_running() and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(context.copy().run, finish)
                return
            except RuntimeError:
                pass
        finish()

    threading.Thread(target=lambda: context.copy().run(worker), daemon=True, name="HMB-Project-Folder").start()
