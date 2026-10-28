"""Register cold-canvas and singleton guards plus completed-load migration."""
from __future__ import annotations

import importlib.util
import ast
import asyncio
import hashlib
import inspect
import ipaddress
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap
import threading
import types
import weakref
from typing import Any
from uuid import UUID

from griptape_nodes.node_library.advanced_node_library import AdvancedNodeLibrary
from griptape_nodes.node_library.library_registry import LibraryRegistry
from griptape_nodes.node_library.workflow_registry import WorkflowRegistry
try:
    from griptape_nodes.retained_mode.engine import current_engine
except ImportError:
    # Keep import possible so the library-load hook can report the required
    # deletion-protection API explicitly, rather than silently omitting it.
    current_engine = None
from griptape_nodes.retained_mode.events.context_events import (
    EnsureWorkflowAndFlowRequest,
    EnsureWorkflowAndFlowResultSuccess,
)
from griptape_nodes.retained_mode.events.base_events import ResultDetails
from griptape_nodes.retained_mode.events.node_events import (
    CreateNodeRequest,
    CreateNodeResultFailure,
)
from griptape_nodes.retained_mode.events.parameter_events import SetParameterValueRequest
try:
    from griptape_nodes.retained_mode.events.node_events import (
        DeserializeSelectedNodesFromCommandsRequest,
        DeserializeSelectedNodesFromCommandsResultFailure,
    )
except ImportError:
    DeserializeSelectedNodesFromCommandsRequest = None
    DeserializeSelectedNodesFromCommandsResultFailure = None
try:
    from griptape_nodes.retained_mode.events.node_events import (
        DuplicateSelectedNodesRequest,
        DuplicateSelectedNodesResultFailure,
    )
except ImportError:
    DuplicateSelectedNodesRequest = None
    DuplicateSelectedNodesResultFailure = None

_LIBRARY_NAME = "HMB_GP_Production"
_NODE_TYPE = "HMBSeedanceGeneration"
_IMAGE_NODE_TYPE = "HMBImageGeneration"
_PROMPT_NODE_TYPE = "HMBPromptLibrary"
_AGENT_NODE_TYPE = "HMBAgentLibrary"
_FINISH_NODE_TYPE = "HMBFinishLookLibrary"
_BASH_NODE_TYPE = "HMBImageBash"
_EDITOR_NODE_TYPES = (_PROMPT_NODE_TYPE, _AGENT_NODE_TYPE, _FINISH_NODE_TYPE, _BASH_NODE_TYPE)
_PROMPT_SINGLE_LOAD_MESSAGE = (
    "HMBPromptLibrary is already loaded in this flow. "
    "Use its Shot controls to manage all Shots; another Prompt was not created."
)
_EMPTY_CONTEXT_MESSAGE = (
    "Attempted to create Node in the Current Context. Failed because the Current Context was empty."
)
_REGISTRY_LOCK = threading.RLock()
_REGISTRATIONS: Any = weakref.WeakKeyDictionary()
_DELETION_GATE_ATTRIBUTE = "_hmb_connected_deletion_lifetime_v2"
_DELETION_PROTECTION_VERSION = 2
_WINDOWS_CLOSE_GUARD_MARKER = "_hmb_windows_transport_close_guard_v1"
_WINDOWS_CLOSE_GUARD_AST_SHA256 = "1726d603431044758617fdb85927f558ed7c179445672c34e73ce1712bdc1958"
_WINDOWS_CLOSE_GUARD_LOCK_KEY = "_hmb_windows_transport_close_lock_v1"
_HMB_NATIVE_EDITOR_STATE_MODULE = "_hmb_gp_production_native_editor_update_state_v1"
_HMB_NATIVE_EDITOR_RESPONSE_LIMIT = 1024 * 1024
_HMB_NATIVE_EDITOR_TIMEOUT_SECONDS = 20


def _hmb_native_editor_documents_path() -> Path:
    """Use the Windows Documents known folder, including redirected folders."""
    if os.name != "nt":
        raise LookupError("unsupported_platform")
    import ctypes
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    identity = Guid.from_buffer_copy(UUID("fdd39ad0-238f-46af-adb4-6c85480369c7").bytes_le)
    shell, memory = ctypes.windll.shell32, ctypes.windll.ole32
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(Guid), wintypes.DWORD,
        wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = wintypes.LONG
    memory.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    memory.CoTaskMemFree.restype = None
    allocated = ctypes.c_void_p()
    try:
        if shell.SHGetKnownFolderPath(ctypes.byref(identity), 0, None, ctypes.byref(allocated)) or not allocated.value:
            raise OSError("The Windows Documents folder is unavailable")
        path = Path(ctypes.wstring_at(allocated.value))
        if not path.is_absolute():
            raise OSError("The Windows Documents folder is not absolute")
        return path
    finally:
        if allocated.value:
            memory.CoTaskMemFree(allocated)


def _hmb_native_editor_plain_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked native editor source is unsupported")
    return absolute


def _hmb_native_editor_sources(engine: Any, library_data: Any) -> tuple[Path, Path, dict[str, str], dict[str, Any]]:
    """Only the registered Documents installation may spawn the fixed updater.

    Developer checkouts and SDK fixtures exit before opening support files or
    creating a process. No caller can supply an alternative app target.
    """
    if getattr(library_data, "name", None) != _LIBRARY_NAME:
        raise LookupError("not_hmb_library")
    root = _hmb_native_editor_plain_path(Path(__file__).parent)
    documents = _hmb_native_editor_documents_path()
    expected = Path(os.path.abspath(documents / "GriptapeNodes/libraries/HMB_GP_Production"))
    if os.path.normcase(str(root)) != os.path.normcase(str(expected)):
        raise LookupError("not_installed_library")
    _hmb_native_editor_plain_path(expected)
    manager = getattr(engine, "library_manager", None)
    lookup = getattr(manager, "get_library_info_by_library_name", None)
    if getattr(manager, "is_worker", None) is not False or not callable(lookup):
        raise LookupError("not_registered_orchestrator")
    manifest = _hmb_native_editor_plain_path(root / "griptape-nodes-library.json")
    info = lookup(_LIBRARY_NAME)
    if info is None or _hmb_native_editor_plain_path(Path(info.library_path)) != manifest:
        raise LookupError("registered_library_path_changed")
    paths = {
        "manifest": manifest, "bootstrap": _hmb_native_editor_plain_path(Path(__file__)),
        "descriptor": _hmb_native_editor_plain_path(root / "resources/editor/native-editor-patch.json"),
        "patcher": _hmb_native_editor_plain_path(root / "tools/hmb_color_lut_native_header_patch.py"),
        "helper": _hmb_native_editor_plain_path(root / "resources/editor/hmb-color-lut-native-header.js"),
    }
    contents = {}
    for key, path in paths.items():
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("native_support_source_missing_or_oversized")
        contents[key] = path.read_bytes()
    metadata = json.loads(contents["manifest"].decode("utf-8-sig"))
    if (metadata.get("name") != _LIBRARY_NAME or metadata.get("advanced_library_path") != "_hmb_library_bootstrap.py"
            or paths["bootstrap"] != root / "_hmb_library_bootstrap.py"):
        raise ValueError("native_support_manifest_owner_changed")
    descriptor = json.loads(contents["descriptor"].decode("utf-8-sig"))
    if ("editor_version" in descriptor or descriptor.get("schema") != "hmb-native-editor-patch-release" or type(descriptor.get("version")) is not int
            or descriptor["version"] != 1 or descriptor.get("source_profile") != "reviewed-stock"
            or descriptor.get("bundle_name") != "index-DEZU41rc.js"
            or descriptor.get("helper_path") != "resources/editor/hmb-color-lut-native-header.js"
            or descriptor.get("patcher_path") != "tools/hmb_color_lut_native_header_patch.py"):
        raise ValueError("native_support_descriptor_unsupported")
    hashes = {key: hashlib.sha256(value).hexdigest() for key, value in contents.items()}
    for key in ("patcher", "helper"):
        if descriptor.get(key + "_sha256") != hashes[key]:
            raise ValueError("native_support_" + key + "_hash_changed")
    profiles = descriptor.get("additional_profiles", [])
    if not isinstance(profiles, list) or len(profiles) > 16:
        raise ValueError("native_support_profiles_invalid")
    for profile in profiles:
        required = {"source_sha256", "candidate_sha256", "adapter_path", "adapter_sha256", "structural_fallback"}
        if (not isinstance(profile, dict) or not required.issubset(profile)
                or set(profile) - required - {"previous_candidate_sha256"}
                or profile.get("adapter_path") != "tools/hmb_native_semantic_adapter.py"
                or type(profile.get("structural_fallback")) is not bool):
            raise ValueError("native_support_profile_invalid")
        for key in ("source_sha256", "candidate_sha256", "adapter_sha256"):
            value = profile.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("native_support_profile_hash_invalid")
        previous = profile.get("previous_candidate_sha256", [])
        if (not isinstance(previous, list) or len(previous) > 16
                or any(not isinstance(value, str) or len(value) != 64
                       or any(c not in "0123456789abcdef" for c in value) for value in previous)
                or len(set(previous)) != len(previous)
                or any(value in (profile["source_sha256"], profile["candidate_sha256"]) for value in previous)):
            raise ValueError("native_support_previous_profile_hash_invalid")
        adapter = _hmb_native_editor_plain_path(root / profile["adapter_path"])
        if not adapter.is_file() or adapter.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("native_support_adapter_missing_or_oversized")
        adapter_hash = hashlib.sha256(adapter.read_bytes()).hexdigest()
        if adapter_hash != profile["adapter_sha256"]:
            raise ValueError("native_support_adapter_hash_changed")
        hashes["adapter:" + profile["adapter_path"]] = adapter_hash
    candidate = descriptor.get("candidate_sha256")
    if not isinstance(candidate, str) or len(candidate) != 64 or any(c not in "0123456789abcdef" for c in candidate):
        raise ValueError("native_support_candidate_hash_invalid")
    python = Path(sys.executable).resolve(strict=True)
    if sys.version_info[:2] != (3, 12) or python.is_relative_to(root) or not python.is_file():
        raise ValueError("native_support_external_python_required")
    return root, python, hashes, descriptor


def _hmb_native_editor_runtime_fingerprint() -> tuple[str, str, str]:
    """Fingerprint the *active* editor, so vendor updates invalidate a cache.

    This is read-only and bounded. Never trust a supplied or cached target:
    the release updater repeats its own stricter preflight before any write.
    """
    import re

    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise ValueError("native_editor_local_appdata_missing")
    root = _hmb_native_editor_plain_path(Path(local) / "ai.griptape.nodes.desktop/current/resources/editor-bundle")
    entry = _hmb_native_editor_plain_path(root / "index-editor.html")

    def read_stable(path: Path, limit: int) -> bytes:
        before = path.stat()
        if not path.is_file() or before.st_size > limit:
            raise ValueError("native_editor_file_missing_or_oversized")
        encoded = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(encoded) != before.st_size:
            raise ValueError("native_editor_file_changed_during_read")
        return encoded

    html = read_stable(entry, 1024 * 1024)
    matches = re.findall(r'''\bsrc\s*=\s*["']\./assets/(index-[A-Za-z0-9_-]+\.js)["']''', html.decode("utf-8"))
    if len(matches) != 1:
        raise ValueError("native_editor_entry_ambiguous")
    target = _hmb_native_editor_plain_path(root / "assets" / matches[0])
    encoded = read_stable(target, 64 * 1024 * 1024)
    if read_stable(entry, 1024 * 1024) != html:
        raise ValueError("native_editor_entry_changed_during_read")
    return str(target), hashlib.sha256(html).hexdigest(), hashlib.sha256(encoded).hexdigest()


def _hmb_native_editor_state() -> Any:
    candidate = types.ModuleType(_HMB_NATIVE_EDITOR_STATE_MODULE)
    candidate.schema = 1
    candidate.lock = threading.RLock()
    candidate.jobs = {}
    state = sys.modules.setdefault(_HMB_NATIVE_EDITOR_STATE_MODULE, candidate)
    if (type(state) is not types.ModuleType or getattr(state, "schema", None) != 1
            or not isinstance(getattr(state, "jobs", None), dict)
            or not callable(getattr(getattr(state, "lock", None), "acquire", None))):
        raise ValueError("native_coordinator_owner_changed")
    return state


def _hmb_native_editor_summary(status: str, reason: str, *, restart_required: bool = False) -> dict[str, Any]:
    return {"schema": "hmb-native-editor-git-override", "version": 1, "status": status,
        "reason": reason, "disk_ready": False, "restart_required": restart_required, "renderer_verified": False}


def _hmb_native_editor_child(root: Path, python: Path, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Fresh CLI process, no import-cache mutation, bounded lifetime and output."""
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "LOCALAPPDATA", "APPDATA",
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP") if key in os.environ}
    command = [str(python), "-I", "-B", str(root / "tools/hmb_color_lut_native_header_patch.py"), "--apply-git-override"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, cwd=str(root), env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    close_job = None
    try:
        close_job = _hmb_environment_job(process)
        output, _ = process.communicate(timeout=_HMB_NATIVE_EDITOR_TIMEOUT_SECONDS)
        if len(output) > _HMB_NATIVE_EDITOR_RESPONSE_LIMIT:
            raise ValueError("native_update_response_oversized")
        value = json.loads(output)
        if (not isinstance(value, dict) or value.get("schema") != "hmb-native-editor-git-override"
                or type(value.get("version")) is not int or value["version"] != 1
                or value.get("status") not in {"current", "applied", "pending", "unsupported", "error"}
                or any(type(value.get(key)) is not bool for key in ("disk_ready", "restart_required", "renderer_verified"))
                or value["renderer_verified"] is not False or not isinstance(value.get("reason"), str)
                or len(value["reason"]) > 4096 or any(ord(c) < 32 for c in value["reason"])):
            raise ValueError("native_update_response_invalid")
        success = value["status"] in {"current", "applied"}
        candidates = {descriptor["candidate_sha256"]}
        candidates.update(p["candidate_sha256"] for p in descriptor.get("additional_profiles", []))
        candidate = value.get("candidate_sha256")
        if success and (process.returncode != 0 or value["disk_ready"] is not True
                or candidate not in candidates
                or value.get("source_profile") not in {"reviewed-stock", "reviewed-adapter"}
                or "editor_version" in value
                or value["status"] == "applied" and value["restart_required"] is not True):
            raise ValueError("native_update_success_unverified")
        if not success and value["disk_ready"] is not False:
            raise ValueError("native_update_failure_claimed_ready")
        return value
    finally:
        if close_job is not None:
            close_job()
        if process.poll() is None:
            process.kill()
            try:
                process.communicate(timeout=2)
            except Exception:
                pass


def _hmb_native_editor_publish(owner: Any, engine: Any, identity: Any, summary: dict[str, Any]) -> None:
    if getattr(owner, "_hmb_native_editor_update_identity", None) == identity:
        owner._hmb_native_editor_update_summary = dict(summary)
    if getattr(engine, "_hmb_native_editor_update_identity", None) == identity:
        engine._hmb_native_editor_update_summary = dict(summary)


def _hmb_coordinate_native_editor_update(owner: Any, engine: Any, library_data: Any) -> dict[str, Any]:
    """Start at most one asynchronous Git/Override disk update per source pin.

    Native disk readiness never grants deletion permission or claims that the
    renderer switched code. A cold app restart clears old Python/JS generations.
    """
    try:
        root, python, hashes, descriptor = _hmb_native_editor_sources(engine, library_data)
        state = _hmb_native_editor_state()
        runtime = _hmb_native_editor_runtime_fingerprint()
        identity = (str(root), tuple(sorted(hashes.items())), runtime)
    except LookupError as exc:
        summary = _hmb_native_editor_summary("unsupported", str(exc))
        owner._hmb_native_editor_update_identity = None
        engine._hmb_native_editor_update_identity = None
        _hmb_native_editor_publish(owner, engine, None, summary)
        return summary
    except Exception as exc:
        summary = _hmb_native_editor_summary("error", "native_support_check_failed:" + type(exc).__name__, restart_required=True)
        owner._hmb_native_editor_update_identity = None
        engine._hmb_native_editor_update_identity = None
        _hmb_native_editor_publish(owner, engine, None, summary)
        logging.getLogger(__name__).warning("[HMB_NATIVE_EDITOR_UPDATE] %s", summary["reason"])
        return summary
    with state.lock:
        owner._hmb_native_editor_update_identity = identity
        engine._hmb_native_editor_update_identity = identity
        existing = state.jobs.get(identity)
        if existing is not None:
            summary = dict(existing["summary"], cached=True)
            _hmb_native_editor_publish(owner, engine, identity, summary)
            return summary
        summary = _hmb_native_editor_summary("pending", "native_update_check_running", restart_required=True)
        state.jobs[identity] = {"summary": dict(summary)}
        _hmb_native_editor_publish(owner, engine, identity, summary)
    def update() -> None:
        final_runtime = None
        try:
            result = _hmb_native_editor_child(root, python, descriptor)
            final_runtime = _hmb_native_editor_runtime_fingerprint()
            if (final_runtime[:2] != runtime[:2]
                    or (result.get("status") in {"current", "applied"}
                        and final_runtime[2] != result.get("candidate_sha256"))
                    or (result.get("status") not in {"current", "applied"}
                        and final_runtime[2] != runtime[2])):
                result = _hmb_native_editor_summary("pending", "native_editor_changed_during_update", restart_required=True)
        except subprocess.TimeoutExpired:
            result = _hmb_native_editor_summary("pending", "native_update_timeout", restart_required=True)
        except Exception as exc:
            result = _hmb_native_editor_summary("error", "native_update_failed:" + type(exc).__name__, restart_required=True)
        with state.lock:
            # An applied transaction replaces the bytes represented by its
            # original cache key. Keeping a successful result under that key
            # would later misreport ready if an app update restores those
            # exact original bytes. A future check must run again instead.
            if result.get("status") == "applied" and final_runtime != runtime:
                state.jobs.pop(identity, None)
            else:
                state.jobs[identity] = {"summary": dict(result)}
            live_owner, live_engine = owner_ref(), engine_ref()
            if live_owner is not None and live_engine is not None:
                _hmb_native_editor_publish(live_owner, live_engine, identity, result)
        if result["status"] == "current":
            logging.getLogger(__name__).info("[HMB_NATIVE_EDITOR_UPDATE] current; 편집기 파일이 최신입니다. 실행 중인 화면 확인은 별도입니다.")
        elif result["status"] == "applied":
            logging.getLogger(__name__).warning("[HMB_NATIVE_EDITOR_UPDATE] %s; 편집기 파일 확인 완료. 현재 작업을 저장하고 Griptape를 정상 재시작하면 새 UI가 적용됩니다. 실행 중인 화면 확인은 별도입니다.", result["status"])
        else:
            logging.getLogger(__name__).warning("[HMB_NATIVE_EDITOR_UPDATE] %s: %s; 자동 적용을 확인하지 못했습니다. 현재 작업을 저장하고 로그와 복구 파일을 확인한 뒤 정상 재시작하여 다시 확인하세요.", result["status"], result["reason"])
    try:
        owner_ref, engine_ref = weakref.ref(owner), weakref.ref(engine)
        thread = threading.Thread(target=update, name="HMB native editor update", daemon=True)
        thread.start()
    except Exception as exc:
        result = _hmb_native_editor_summary("error", "native_update_start_failed:" + type(exc).__name__, restart_required=True)
        with state.lock:
            state.jobs[identity] = {"summary": dict(result)}
            _hmb_native_editor_publish(owner, engine, identity, result)
        return result
    return summary


# Fixed child program. This literal has no import-time execution; both the
# public installer and the guarded library coordinator use the same bytes.
_HMB_TOS_ENVIRONMENT_REPAIR_SOURCE = r'''
"""Isolated migration implementation, embedded verbatim in the shipped bootstrap."""
import ast
import csv
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

MAX_RESPONSE = 1024 * 1024
LEGACY = frozenset(('tos', 'wrapt', 'deprecated'))
ENGINE_BACKED = frozenset(('anyio', 'charset-normalizer', 'idna', 'urllib3'))


def _norm(value):
    return re.sub(r'[-_.]+', '-', value).lower()


def _digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _local(root, path):
    path = Path(os.path.abspath(path))
    current = path
    while current != root:
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise RuntimeError('Linked dependency environment is not supported')
        if current == current.parent or not current.resolve().is_relative_to(root):
            raise RuntimeError('Dependency environment escaped the installed library')
        current = current.parent
    return path


def _root(request):
    raw = request.get('library_root')
    if type(raw) is not str or not Path(raw).is_absolute():
        raise RuntimeError('Unsupported migration library root')
    root = Path(raw).resolve(strict=True)
    if sys.version_info[:2] != (3, 12) or not root.is_dir():
        raise RuntimeError('Unsupported migration runtime or library root')
    manifest = _local(root, root / 'griptape-nodes-library.json')
    if manifest.stat().st_size > 2 * 1024 * 1024:
        raise RuntimeError('Unsupported migration manifest')
    data = json.loads(manifest.read_text('utf-8-sig'))
    if data.get('name') != 'HMB_GP_Production':
        raise RuntimeError('Unsupported migration library identity')
    expected = request.get('expected_manifest_sha256')
    if expected is not None and (type(expected) is not str or expected != _digest(manifest)):
        raise RuntimeError('The migration manifest changed')
    return root, _digest(manifest)


def _inventory(root, directory):
    rows = {}
    for path in directory.rglob('*'):
        _local(root, path)
        if path.is_file():
            info = path.stat()
            rows[path.relative_to(directory).as_posix()] = {
                'sha256': _digest(path), 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns,
            }
    return rows


def _write_json(root, path, value):
    _local(root, path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _audit(request, *, active_transaction=None, installer=False):
    root, manifest_sha = _root(request)
    edit = _local(root, root / '.venv')
    site = edit / 'Lib/site-packages'
    python = edit / 'Scripts/python.exe'
    report = {
        'version': 1, 'ok': True, 'status': 'clean', 'schema': 'hmb-tos-isolation-install/v1',
        'prepared': False, 'legacy_packages_removed': [], 'engine_backed_duplicates_removed': [],
        'removed_versions': {}, 'removal_paths': [], 'needs_tos_runtime': False,
        'provider_calls': 0, 'credentials_read': False,
    }
    needed = _local(root, root / '.hmb-tos-runtime-needed.json')
    if needed.is_file():
        report['needs_tos_runtime'] = True
    transactions = _local(root, root / '.hmb-environment-backups')
    if transactions.exists():
        for directory in transactions.iterdir():
            _local(root, directory)
            if active_transaction is not None and directory == active_transaction:
                continue
            journal = _local(root, directory / 'transaction.json')
            if not directory.is_dir() or not journal.is_file() or journal.stat().st_size > 8 * 1024 * 1024:
                report.update(ok=False, status='integrity_unknown', rollback_verified=False)
                return report
            try:
                transaction = json.loads(journal.read_text('utf-8'))
            except (OSError, ValueError):
                transaction = {}
            if transaction.get('version') != 1 or transaction.get('phase') not in ('committed', 'rolled_back', 'aborted'):
                report.update(ok=False, status='integrity_unknown', rollback_verified=False)
                return report
    if not edit.exists():
        report['inspected_fingerprint'] = _json_digest([manifest_sha, 'no-edit-environment'])
        return report
    if not python.is_file() or not site.is_dir():
        raise RuntimeError('The legacy edit environment is incomplete; its files were preserved')
    _local(root, site)
    distributions = {}
    for item in metadata.distributions(path=[str(site)]):
        name = _norm(item.metadata['Name'])
        if name in distributions:
            raise RuntimeError('Duplicate edit dependency metadata is not supported')
        distributions[name] = item
    from packaging.version import Version
    from packaging.requirements import Requirement
    legacy = LEGACY & distributions.keys()
    known_legacy_versions = {'tos': '2.9.2', 'wrapt': '1.16.0', 'deprecated': '1.3.1'}
    if not installer and any(distributions[name].version != known_legacy_versions[name] for name in legacy):
        report.update(ok=False, status='refused', reason='unrecognized_legacy_version')
        return report
    engine_versions = {name: metadata.version(name) for name in ENGINE_BACKED}
    backed = {name for name in ENGINE_BACKED & distributions.keys()
              if Version(distributions[name].version) < Version(engine_versions[name])}
    removable = legacy | backed
    for name, item in distributions.items():
        if name in removable:
            continue
        for raw in item.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is not None and not requirement.marker.evaluate({'extra': ''}):
                continue
            dependency = _norm(requirement.name)
            if dependency in legacy:
                raise RuntimeError('A custom edit dependency needs a legacy TOS package; original environment preserved')
            if dependency in backed and (requirement.url is not None or not
                    requirement.specifier.contains(engine_versions[dependency], prereleases=True)):
                raise RuntimeError('A custom edit dependency rejects the engine component; original environment preserved')
    files = {}
    metadata_rows = []
    for name, item in sorted(distributions.items()):
        metadata_path = _local(root, Path(item._path) / 'METADATA')
        metadata_rows.append([name, item.version, _digest(metadata_path)])
        if name not in removable:
            continue
        record = item.read_text('RECORD')
        if record is None or not record or len(record) > 2 * 1024 * 1024:
            raise RuntimeError('A removable package has no file inventory; original environment preserved')
        for member in csv.reader(io.StringIO(record)):
            if not member or not member[0] or len(member) != 3:
                raise RuntimeError('A removable package has an invalid file inventory; original environment preserved')
            path = Path(os.path.abspath(item.locate_file(member[0])))
            if not path.resolve().is_relative_to(edit.resolve()):
                raise RuntimeError('A package file escaped its edit environment; original environment preserved')
            _local(root, path)
            if path.exists() and not path.is_file():
                raise RuntimeError('A removable package recorded a non-file path')
            rel = path.relative_to(edit).as_posix()
            files[rel] = {'sha256': _digest(path), 'bytes': path.stat().st_size} if path.is_file() else None
            # uv also removes CPython bytecode generated from recorded .py
            # sources. Prove the exact source/name relation; do not grant the
            # whole package directory or arbitrary .pyc files deletion rights.
            if path.suffix == '.py':
                for optimization in ('', '.opt-1', '.opt-2'):
                    cache = path.parent / '__pycache__' / (path.stem + '.' + sys.implementation.cache_tag + optimization + '.pyc')
                    _local(root, cache)
                    if cache.is_file():
                        files[cache.relative_to(edit).as_posix()] = {'sha256': _digest(cache), 'bytes': cache.stat().st_size}
    # A retained wheel may share a RECORD member. Targeted cleanup may not
    # remove another owner's file, even when the two wheels recorded it.
    if removable:
        for name, item in distributions.items():
            if name in removable:
                continue
            record = item.read_text('RECORD') or ''
            for member in csv.reader(io.StringIO(record)):
                if member and member[0]:
                    path = Path(os.path.abspath(item.locate_file(member[0])))
                    if path.is_relative_to(edit) and path.relative_to(edit).as_posix() in files:
                        raise RuntimeError('A removable file is also owned by a retained edit dependency')
    report.update(status='needed' if removable else 'clean',
                  legacy_packages_removed=sorted(legacy), engine_backed_duplicates_removed=sorted(backed),
                  removed_versions={name: distributions[name].version for name in sorted(removable)},
                  removal_paths=[str(edit / value) for value in sorted(files)],
                  needs_tos_runtime=report['needs_tos_runtime'] or 'tos' in legacy)
    report['inspected_fingerprint'] = _json_digest([manifest_sha, metadata_rows, engine_versions, files])
    if len(json.dumps(report).encode()) > MAX_RESPONSE - 2048:
        raise RuntimeError('The dependency audit exceeded its response limit')
    return report


def _run(args, *, data=None, timeout=300):
    result = subprocess.run(args, input=data, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Isolated dependency setup failed; no credentials or provider request was used')
    if len(result.stdout.encode('utf-8')) > MAX_RESPONSE:
        raise RuntimeError('The isolated dependency response exceeded its limit')
    return result.stdout


def _lock(root, name):
    path = _local(root, root / name)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    token = uuid.uuid4().hex
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(json.dumps({'pid': os.getpid(), 'token': token, 'library_root': str(root)}))
    return path, token


def _unlock(lock):
    path, token = lock
    try:
        if path.stat().st_size <= 4096 and json.loads(path.read_text('utf-8')).get('token') == token:
            path.unlink()
    except (OSError, ValueError):
        # Keeping a stale lock is safer than replacing an integrity result or
        # deleting a different owner's lock. Its recovery is explicit.
        pass


def _empty_uv_lock_identity(root, path):
    _local(root, path)
    if not path.exists():
        return None
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size != 0:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _remove_owned_empty_uv_lock(root, path, expected):
    """Delete only our unchanged, unused new uv housekeeping file."""
    descriptor = None
    try:
        if _empty_uv_lock_identity(root, path) != expected:
            return False
        if os.name == 'nt':
            import ctypes
            import msvcrt
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            create.restype = wintypes.HANDLE
            # No sharing: a live uv owner prevents deletion. The handle stays
            # open through identity validation and atomic disposition marking.
            handle = create(str(path), 0x80000000 | 0x00010000, 0, None, 3, 0x00200000, None)
            if handle in (None, ctypes.c_void_p(-1).value):
                return False
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != expected:
                return False
            dispose = kernel.SetFileInformationByHandle
            dispose.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
            dispose.restype = wintypes.BOOL
            remove = ctypes.c_ubyte(1)
            return bool(dispose(handle, 4, ctypes.byref(remove), ctypes.sizeof(remove)))
        import fcntl
        descriptor = os.open(path, os.O_RDONLY)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != expected:
            return False
        if _empty_uv_lock_identity(root, path) != expected:
            return False
        path.unlink()
        return True
    except (OSError, ValueError):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _repair(request):
    root, _ = _root(request)
    lock = _lock(root, '.hmb-tos-migration.lock')
    if lock is None:
        return {'version': 1, 'ok': True, 'status': 'busy', 'provider_calls': 0}
    try:
        audit = _audit(request, installer=request.get('transaction_mode') == 'installer')
        if audit.get('ok') is not True:
            return audit
        if request.get('expected_fingerprint') != audit['inspected_fingerprint']:
            raise RuntimeError('The dependency environment changed after inspection')
        if audit['status'] == 'clean':
            return audit
        mode = request.get('transaction_mode', 'auto')
        if mode not in ('auto', 'installer'):
            raise RuntimeError('Unsupported dependency transaction mode')
        edit = root / '.venv'
        backup = None
        before = None
        if mode == 'auto':
            before = _inventory(root, edit)
            base = _local(root, root / '.hmb-environment-backups')
            base.mkdir(exist_ok=True)
            directory = _local(root, base / uuid.uuid4().hex)
            directory.mkdir()
            backup = directory / '.venv'
            shutil.copytree(edit, backup, copy_function=shutil.copy2)
            if _inventory(root, backup) != before or _inventory(root, edit) != before:
                raise RuntimeError('The environment backup did not match its inspected source')
            _write_json(root, directory / 'transaction.json', {
                'version': 1, 'phase': 'backed-up', 'inspected_fingerprint': audit['inspected_fingerprint'],
                'files': before, 'removed_versions': audit['removed_versions'],
            })
        # Copy/backup can take time. Do not use a previously validated wheel
        # inventory after a concurrent update changed the source.
        if _audit(request, active_transaction=backup.parent if backup is not None else None,
                  installer=mode == 'installer').get('inspected_fingerprint') != audit['inspected_fingerprint']:
            if backup is not None:
                _write_json(root, backup.parent / 'transaction.json', {
                    'version': 1, 'phase': 'aborted', 'inspected_fingerprint': audit['inspected_fingerprint'],
                    'files': before, 'removed_versions': audit['removed_versions'],
                })
            raise RuntimeError('The dependency environment changed before cleanup')
        if audit['needs_tos_runtime']:
            _write_json(root, root / '.hmb-tos-runtime-needed.json', {'version': 1, 'needed': True})
        uv_lock = _local(root, edit / '.lock')
        had_uv_lock = uv_lock.exists()
        generated_uv_lock = None
        try:
            try:
                _run([sys.executable, '-I', '-B', '-m', 'uv', 'pip', 'uninstall', '--python',
                      str(edit / 'Scripts/python.exe'), *sorted(audit['removed_versions'])])
            finally:
                if not had_uv_lock:
                    generated_uv_lock = _empty_uv_lock_identity(root, uv_lock)
            remaining = {_norm(item.metadata['Name']) for item in metadata.distributions(path=[str(edit / 'Lib/site-packages')])}
            if set(audit['removed_versions']) & remaining:
                raise RuntimeError('Legacy TOS editor packages were not removed')
            if any(Path(path).exists() for path in audit['removal_paths']):
                raise RuntimeError('Targeted dependency code or metadata remained after cleanup')
            if before is not None:
                allowed = {Path(path).relative_to(edit).as_posix() for path in audit['removal_paths']}
                after = _inventory(root, edit)
                if any(after.get(name) != value for name, value in before.items() if name not in allowed):
                    raise RuntimeError('Cleanup changed an unrelated environment file')
                allowed_new = {'.lock'} if generated_uv_lock is not None else set()
                if (set(after) - set(before)) - allowed_new:
                    raise RuntimeError('Cleanup introduced an unverified environment file')
            audit.update(status='repaired', removed_files=[path for path in audit['removal_paths'] if not Path(path).exists()])
            audit['generated_housekeeping_paths'] = [str(uv_lock)] if generated_uv_lock is not None else []
            if backup is not None:
                audit['backup_path'] = str(backup)
                _write_json(root, backup.parent / 'transaction.json', {
                    'version': 1, 'phase': 'committed', 'inspected_fingerprint': audit['inspected_fingerprint'],
                    'files': before, 'removed_versions': audit['removed_versions'],
                })
            return audit
        except Exception:
            if backup is None:
                raise
            # Restore only original absent files. A different present value is
            # a concurrent writer or an unknown partial mutation, never consent
            # to overwrite it. Full original inventory is then verified.
            verified = False
            try:
                verified = True
                if generated_uv_lock is not None:
                    verified = _remove_owned_empty_uv_lock(root, uv_lock, generated_uv_lock)
                for name, value in before.items():
                    target = _local(root, edit / name)
                    saved = _local(root, backup / name)
                    if target.exists():
                        if not target.is_file() or _digest(target) != value['sha256']:
                            verified = False
                        continue
                    if not saved.is_file() or _digest(saved) != value['sha256']:
                        verified = False
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(saved, target)
                verified = verified and _inventory(root, edit) == before
            except Exception:
                verified = False
            audit.update(ok=False, status='rolled_back' if verified else 'integrity_unknown',
                         rollback_verified=verified, backup_path=str(backup))
            try:
                _write_json(root, backup.parent / 'transaction.json', {
                    'version': 1, 'phase': audit['status'], 'inspected_fingerprint': audit['inspected_fingerprint'],
                    'files': before, 'removed_versions': audit['removed_versions'],
                })
            except Exception:
                pass
            return audit
    finally:
        _unlock(lock)


def _probe(root, runtime):
    source = _local(root, root / 'HMBSeedanceGeneration.py')
    values = [ast.literal_eval(node.value) for node in ast.parse(source.read_text('utf-8-sig')).body
              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                  target.id == '_TOS_HELPER_SOURCE' for target in node.targets)]
    if len(values) != 1 or type(values[0]) is not str or len(values[0]) > 65536:
        raise RuntimeError('The verified TOS helper is unavailable')
    python = _local(root, runtime / 'Scripts/python.exe')
    config = _local(root, runtime / 'pyvenv.cfg')
    if not python.is_file() or not config.is_file() or config.stat().st_size > 16384:
        raise RuntimeError('An incomplete TOS environment exists; its files were preserved')
    request = json.dumps({'version': 1, 'runtime_root': str(runtime), 'operation': 'probe'})
    probe = json.loads(_run([str(python), '-I', '-B', '-c', values[0]], data=request, timeout=30))
    if not (probe.get('version') == 1 and probe.get('ok') is True and probe.get('isolated') is True
            and Path(probe.get('runtime_root', '')).resolve() == runtime
            and probe.get('tos_version') == '2.9.2' and probe.get('wrapt_version') == '1.16.0'):
        raise RuntimeError('TOS runtime isolation probe failed')
    return probe, hashlib.sha256(values[0].encode()).hexdigest()


def _prepare(request):
    root, manifest_sha = _root(request)
    source = _local(root, root / 'HMBSeedanceGeneration.py')
    source_sha = _digest(source)
    def same_identity():
        if _root(request)[1] != manifest_sha or _digest(source) != source_sha:
            raise RuntimeError('The TOS preparation owner changed; staging files were preserved')
    lock = _lock(root, '.hmb-tos-prepare.lock')
    if lock is None:
        return {'version': 1, 'ok': True, 'status': 'busy', 'prepared': False, 'provider_calls': 0}
    try:
        runtime = _local(root, root / '.venv-tos')
        stage = None
        if not runtime.exists():
            stage = _local(root, root / ('.venv-tos-stage-' + uuid.uuid4().hex))
            _run([sys.executable, '-I', '-B', '-m', 'uv', 'venv', '--python', sys.executable, str(stage)])
            _run([sys.executable, '-I', '-B', '-m', 'uv', 'pip', 'install', '--python',
                  str(stage / 'Scripts/python.exe'), 'tos==2.9.2'])
            _probe(root, stage)
            same_identity()
            # The lock excludes our own preparers. An unrelated writer may
            # still create the final path; preserve both instead of replacing.
            if runtime.exists():
                raise RuntimeError('Another TOS environment appeared; both copies were preserved')
            os.rename(stage, runtime)
        probe, helper_sha = _probe(root, runtime)
        same_identity()
        _write_json(root, root / '.hmb-tos-runtime-ready.json', {
            'version': 1, 'runtime_root': str(runtime), 'helper_sha256': helper_sha,
            'tos_version': '2.9.2', 'wrapt_version': '1.16.0',
        })
        needed = _local(root, root / '.hmb-tos-runtime-needed.json')
        if needed.is_file():
            needed.unlink()
        return {'version': 1, 'ok': True, 'status': 'prepared', 'prepared': True,
                'runtime_probe': probe, 'provider_calls': 0, 'credentials_read': False}
    finally:
        _unlock(lock)


def _repair_request(request):
    if type(request) is not dict or request.get('version') != 1:
        raise RuntimeError('Unsupported dependency migration protocol')
    operation = request.get('operation')
    if operation == 'audit':
        return _audit(request)
    if operation == 'repair':
        return _repair(request)
    if operation == 'prepare':
        return _prepare(request)
    if operation == 'install':
        report = _audit(request, installer=True)
        if report.get('ok') is True and request.get('clean_legacy') is True:
            report = _repair(dict(request, operation='repair', transaction_mode='installer',
                                  expected_fingerprint=report['inspected_fingerprint']))
        if report.get('ok') is True and request.get('prepare_runtime') is True:
            prepared = _prepare(dict(request, operation='prepare'))
            report.update(prepared=prepared.get('prepared', False))
            if prepared.get('runtime_probe'):
                report['runtime_probe'] = prepared['runtime_probe']
            if prepared.get('status') != 'prepared':
                report.update(ok=False, status=prepared.get('status', 'refused'))
        return report
    raise RuntimeError('Unsupported dependency migration operation')


def _main():
    try:
        data = sys.stdin.buffer.read(32769)
        if len(data) > 32768:
            raise RuntimeError('Dependency migration request exceeded its limit')
        report = _repair_request(json.loads(data))
    except Exception:
        report = {'version': 1, 'ok': False, 'status': 'refused',
                  'error': 'Dependency migration was refused; original files or recovery copies were preserved',
                  'provider_calls': 0, 'credentials_read': False}
    output = json.dumps(report, ensure_ascii=True, separators=(',', ':'))
    if len(output.encode()) > MAX_RESPONSE:
        output = '{"version":1,"ok":false,"status":"refused","error":"Migration response exceeded its limit"}'
    print(output, flush=True)


if __name__ == '__main__':
    _main()
'''


_HMB_ENV_STATE_MODULE = "_hmb_gp_production_environment_state_v1"
_HMB_ENV_RESPONSE_LIMIT = 1024 * 1024
_HMB_ENV_NODE_FILES = frozenset({"HMBAgentLibrary.py", "HMBImageAssetLibrary.py", "HMBVideoPickerLibrary.py",
    "HMBPromptLibrary.py", "HMBFinishLookLibrary.py", "HMBColorLUTLibrary.py", "HMBSeedanceGeneration.py"})


def _hmb_environment_state() -> Any:
    state = sys.modules.get(_HMB_ENV_STATE_MODULE)
    if state is None:
        candidate = types.ModuleType(_HMB_ENV_STATE_MODULE)
        candidate.schema = 1
        candidate.lock = threading.RLock()
        candidate.attempts = {}
        candidate.jobs = {}
        candidate.completed = {}
        candidate.notices = set()
        state = sys.modules.setdefault(_HMB_ENV_STATE_MODULE, candidate)
    if (type(state) is not types.ModuleType or getattr(state, "schema", None) != 1
            or not isinstance(getattr(state, "attempts", None), dict)
            or not isinstance(getattr(state, "jobs", None), dict)
            or not isinstance(getattr(state, "completed", None), dict)
            or not isinstance(getattr(state, "notices", None), set)):
        raise RuntimeError("HMB environment ownership is unavailable. Restart Griptape before updating this library.")
    return state


def _hmb_environment_notice(state: Any, key: Any, text: str) -> None:
    with state.lock:
        if key in state.notices:
            return
        state.notices.add(key)
    logging.getLogger(__name__).warning(text)


def _hmb_environment_root() -> tuple[Path, str]:
    root = Path(__file__).resolve(strict=True).parent
    manifest = root / "griptape-nodes-library.json"
    if manifest.is_symlink() or getattr(manifest, "is_junction", lambda: False)():
        raise ValueError("Linked HMB manifest")
    raw = manifest.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Oversized HMB manifest")
    data = json.loads(raw.decode("utf-8-sig"))
    advanced = data.get("advanced_library_path")
    if (data.get("name") != _LIBRARY_NAME or not isinstance(advanced, str)
            or (root / advanced).resolve(strict=True) != Path(__file__).resolve(strict=True)):
        raise ValueError("HMB manifest does not own this Advanced Library")
    engine = current_engine() if callable(current_engine) else None
    manager = getattr(engine, "library_manager", None)
    lookup = getattr(manager, "get_library_info_by_library_name", None)
    if manager is None or not callable(lookup) or getattr(manager, "is_worker", None) is not False:
        raise LookupError("The registered orchestrator owns the HMB edit environment")
    info = lookup(_LIBRARY_NAME)
    if info is None:
        raise LookupError("No registered HMB environment owns this constructor")
    if Path(info.library_path).resolve(strict=True) != manifest.resolve(strict=True):
        raise ValueError("Another registered HMB library owns this environment")
    edit = root / ".venv"
    if edit.is_symlink() or getattr(edit, "is_junction", lambda: False)():
        raise ValueError("Linked HMB edit environment")
    return root, hashlib.sha256(raw).hexdigest()


def _hmb_environment_python(root: Path) -> Path:
    python = Path(sys.executable).resolve(strict=True)
    if sys.version_info[:2] != (3, 12) or python.is_relative_to(root) or not python.is_file():
        raise ValueError("A separate Griptape Python 3.12 is required")
    return python


def _hmb_environment_loaded(root: Path, paths: list[Path] | None = None) -> str:
    targets = {os.path.normcase(str(path)) for path in paths or []}
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            spec = getattr(module, "__spec__", None)
            values = (getattr(module, "__file__", None), getattr(spec, "origin", None))
            for value in values:
                if not isinstance(value, str) or not value or value in {"built-in", "frozen"}:
                    continue
                path = Path(value).resolve()
                if path.parent == root and path.name in _HMB_ENV_NODE_FILES:
                    return "HMB node code is already loaded"
                if os.path.normcase(str(path)) in targets:
                    return "An affected edit dependency is already loaded"
        except (OSError, ValueError, TypeError, AttributeError):
            if paths:
                return "Loaded module ownership could not be verified"
    return ""


def _hmb_environment_stamp(root: Path) -> str:
    """A read-only cache invalidator, never authority to delete a dependency."""
    rows = []
    for directory in (root / ".venv", root / ".hmb-environment-backups"):
        if not directory.exists():
            rows.append((directory.name, None))
            continue
        for path in (directory, *directory.rglob("*")):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Linked environment cache member")
            stat = path.stat()
            rows.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()


def _hmb_environment_job(process: Any) -> Any:
    """Own helper descendants before sending stdin; close kills only this job."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    class Limits(ctypes.Structure):
        _fields_ = [("per_process", ctypes.c_int64), ("per_job", ctypes.c_int64),
            ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
            ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD)]
    class Io(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class Extended(ctypes.Structure):
        _fields_ = [("basic", Limits), ("io", Io), ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateJobObjectW
    create.argtypes, create.restype = [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    handle = create(None, None)
    if not handle:
        raise RuntimeError("HMB helper process ownership is unavailable")
    try:
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configure = kernel.SetInformationJobObject
        configure.argtypes, configure.restype = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL
        assign = kernel.AssignProcessToJobObject
        assign.argtypes, assign.restype = [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL
        if not configure(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not assign(handle, wintypes.HANDLE(int(process._handle))):
            raise RuntimeError("HMB helper process ownership could not be established")
    except BaseException:
        close(handle)
        raise
    return lambda: close(handle)


def _hmb_environment_mapped_dlls(paths: list[Path]) -> bool:
    targets = {os.path.normcase(str(path)) for path in paths if path.suffix.lower() in {".pyd", ".dll"}}
    if not targets or sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel.GetCurrentProcess
    process.restype = wintypes.HANDLE
    enum = kernel.K32EnumProcessModules
    enum.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    enum.restype = wintypes.BOOL
    filename = kernel.K32GetModuleFileNameExW
    filename.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    filename.restype = wintypes.DWORD
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    handle = process()
    if not enum(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed)) or needed.value > ctypes.sizeof(modules):
        raise RuntimeError("Mapped dependency ownership could not be verified")
    for index in range(needed.value // ctypes.sizeof(wintypes.HMODULE)):
        buffer = ctypes.create_unicode_buffer(32768)
        size = filename(handle, modules[index], buffer, len(buffer))
        if not size or size >= len(buffer):
            raise RuntimeError("Mapped dependency path could not be verified")
        if os.path.normcase(str(Path(buffer.value).resolve())) in targets:
            return True
    return False


def _hmb_environment_child(python: Path, source: str, request: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    data = json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    if len(data) > 32768:
        raise RuntimeError("HMB environment request exceeded its limit")
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    process = subprocess.Popen([str(python), "-I", "-B", "-c", source], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(python.parent), env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    close_job = None
    try:
        close_job = _hmb_environment_job(process)
        output, _ = process.communicate(data, timeout=timeout)
        if process.returncode or len(output) > _HMB_ENV_RESPONSE_LIMIT:
            raise RuntimeError("HMB environment helper did not return a verified result")
        result = json.loads(output)
        if (not isinstance(result, dict) or type(result.get("version")) is not int or result["version"] != 1
                or type(result.get("ok")) is not bool or type(result.get("status")) is not str):
            raise RuntimeError("HMB environment helper returned an invalid result")
        return result
    finally:
        # Release the entire owned job before draining inherited pipe handles;
        # an uv descendant may otherwise keep the helper's stdout open.
        if close_job is not None:
            close_job()
        if process.poll() is None:
            process.kill()
            try:
                process.communicate(timeout=2)
            except Exception:
                pass


def _hmb_environment_prepare(state: Any, key: Any, python: Path, source: str, request: dict[str, Any]) -> None:
    with state.lock:
        if key in state.jobs:
            return
        state.jobs[key] = {"status": "preparing"}
    def prepare() -> None:
        try:
            result = _hmb_environment_child(python, source, {**request, "operation": "prepare"}, timeout=660)
            ready = result.get("ok") is True and result.get("status") == "prepared"
        except Exception:
            ready = False
        with state.lock:
            state.jobs[key] = {"status": "ready" if ready else "pending"}
        if not ready:
            _hmb_environment_notice(state, (key, "prepare"), "HMB optional TOS preparation is pending. Cloud generation, saved Tasks and video previews remain available.")
    threading.Thread(target=prepare, name="HMB isolated TOS preparation", daemon=True).start()


def _hmb_coordinate_environment_repair() -> dict[str, Any]:
    """One guarded cold repair; live reloads defer without editing active files."""
    state = _hmb_environment_state()
    try:
        root, manifest_sha = _hmb_environment_root()
        python = _hmb_environment_python(root)
    except (OSError, ValueError, LookupError, TypeError):
        return {"status": "unavailable", "restart_required": False}
    source = _HMB_TOS_ENVIRONMENT_REPAIR_SOURCE
    if not isinstance(source, str) or not source or len(source) > 256 * 1024:
        raise RuntimeError("HMB environment repair code is unavailable. Restore the verified library before loading it.")
    identity = (str(root), manifest_sha, hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        str(python), python.stat().st_size, python.stat().st_mtime_ns)
    try:
        stamp = _hmb_environment_stamp(root)
    except (OSError, ValueError):
        stamp = None
    completed = state.completed.get(identity)
    if stamp is not None and completed is not None and completed["stamp"] == stamp:
        return {**completed["summary"], "cached": True}
    loaded_hmb = _hmb_environment_loaded(root)
    if loaded_hmb and completed is None:
        _hmb_environment_notice(state, (identity, "loaded"), "HMB code is already loaded. Restart Griptape once to finish the environment update; active library files were preserved.")
        return {"status": "pending", "restart_required": True, "reason": "loaded_hmb_code"}
    if not state.lock.acquire(blocking=False):
        return {"status": "pending", "restart_required": True, "reason": "another_environment_check"}
    saved_paths: list[tuple[int, str]] = []
    try:
        site = (root / ".venv" / ("Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages")).resolve()
        # The SDK inserts this path before the Advanced constructor. Quarantine
        # only that owned path while checking/deleting unloaded RECORD members.
        for index in reversed(range(len(sys.path))):
            try:
                matches = bool(sys.path[index]) and Path(sys.path[index]).resolve() == site
            except (OSError, ValueError, TypeError):
                matches = False
            if matches:
                saved_paths.append((index, sys.path.pop(index)))
        request = {"version": 1, "operation": "audit", "library_root": str(root),
            "expected_manifest_sha256": manifest_sha, "transaction_mode": "auto"}
        try:
            audit = _hmb_environment_child(python, source, request, timeout=45)
        except Exception:
            _hmb_environment_notice(state, (identity, "audit"), "HMB environment verification is pending. Existing files were preserved; restart Griptape or use the verified updater.")
            return {"status": "pending", "restart_required": True, "reason": "audit_unavailable"}
        if audit.get("status") == "integrity_unknown":
            raise RuntimeError("HMB environment recovery could not be verified. Restore its verified backup before loading the updated library.")
        if audit.get("ok") is not True or audit.get("status") not in {"clean", "needed"}:
            _hmb_environment_notice(state, (identity, "refused"), "HMB automatic environment update was deferred. Original files were preserved; use the verified updater or restart Griptape.")
            return {"status": "pending", "restart_required": True, "reason": "audit_refused"}
        fingerprint = audit.get("inspected_fingerprint")
        paths = audit.get("removal_paths")
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint)
                or not isinstance(paths, list) or len(paths) > 10000 or type(audit.get("needs_tos_runtime")) is not bool):
            raise RuntimeError("HMB environment ownership report is invalid. Restore the verified library before loading it.")
        edit = (root / ".venv").resolve()
        targets = []
        for raw in paths:
            if not isinstance(raw, str) or not Path(raw).is_absolute():
                raise RuntimeError("HMB dependency ownership could not be verified.")
            path = Path(raw).resolve()
            if not path.is_relative_to(edit) or path == edit:
                raise RuntimeError("HMB dependency ownership escaped its environment.")
            targets.append(path)
        attempt = (*identity, fingerprint)
        if audit["status"] == "needed":
            if attempt in state.attempts:
                previous = state.attempts[attempt]
                if previous.get("status") in {"clean", "repaired"}:
                    previous = {"status": "pending", "restart_required": True, "reason": "reexposed_environment"}
                    state.attempts[attempt] = previous
                    _hmb_environment_notice(state, (identity, "reexposed"), "HMB legacy dependencies were restored after cleanup. Restart Griptape once to verify the environment; automatic cleanup was not repeated.")
                return dict(previous)
            try:
                loaded = loaded_hmb or _hmb_environment_loaded(root, targets) or _hmb_environment_mapped_dlls(targets)
            except Exception:
                loaded = True  # Unknown DLL ownership never authorizes cleanup.
            if loaded:
                result = {"status": "pending", "restart_required": True, "reason": "loaded_dependency"}
                state.attempts[attempt] = result
                _hmb_environment_notice(state, (identity, "loaded_dependency"), "HMB dependencies are in use. Restart Griptape once to finish the update; no dependency file was changed.")
                return dict(result)
            state.attempts[attempt] = {"status": "pending", "restart_required": True, "reason": "repair_attempted"}
            try:
                result = _hmb_environment_child(python, source, {**request, "operation": "repair", "expected_fingerprint": fingerprint}, timeout=360)
            except Exception:
                raise RuntimeError("HMB environment repair ended without verified recovery. Restore the verified backup before loading the updated library.") from None
            if result.get("status") == "integrity_unknown" or (result.get("status") == "rolled_back" and result.get("rollback_verified") is not True):
                raise RuntimeError("HMB environment recovery could not be verified. Restore its verified backup before loading the updated library.")
            if result.get("ok") is not True or result.get("status") not in {"repaired", "clean"}:
                pending = {"status": "pending", "restart_required": True, "reason": "verified_rollback" if result.get("rollback_verified") is True else "repair_refused"}
                state.attempts[attempt] = pending
                _hmb_environment_notice(state, (identity, "rollback"), "HMB environment update is pending. Original files or the verified rollback were preserved; use the verified updater before retrying.")
                return dict(pending)
            summary = {"status": result["status"], "restart_required": False,
                "removed_distributions": list(result.get("removed_versions", {}))}
            state.attempts[attempt] = summary
            # A repair response is not a completed clean-environment fingerprint.
            verified = _hmb_environment_child(python, source, request, timeout=45)
            if verified.get("ok") is not True or verified.get("status") != "clean":
                raise RuntimeError("HMB repaired environment could not be verified. Use the verified updater before loading it.")
            fingerprint = verified.get("inspected_fingerprint")
        else:
            summary = {"status": "clean", "restart_required": False, "removed_distributions": []}
        try:
            completed_stamp = _hmb_environment_stamp(root)
        except (OSError, ValueError):
            completed_stamp = None
        if completed_stamp is not None:
            state.completed[identity] = {"stamp": completed_stamp, "fingerprint": fingerprint, "summary": dict(summary)}
        if audit["needs_tos_runtime"]:
            _hmb_environment_prepare(state, identity, python, source, request)
            summary["optional_tos"] = "preparing"
        return dict(summary)
    finally:
        for index, value in sorted(saved_paths):
            sys.path.insert(min(index, len(sys.path)), value)
        state.lock.release()


def _windows_transport_close_class() -> Any:
    if sys.platform != "win32" or getattr(sys.implementation, "name", "") != "cpython":
        return None
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
        return _ProactorBasePipeTransport
    except ImportError:
        return None


def _windows_transport_close_lock() -> Any:
    # Advanced libraries can be imported under different module names. The
    # CPython module is the process-wide anchor; setdefault is atomic here.
    module = sys.modules.get("asyncio.proactor_events")
    if module is None:
        return None
    lock = vars(module).setdefault(_WINDOWS_CLOSE_GUARD_LOCK_KEY, threading.RLock())
    return lock if type(lock) is type(threading.RLock()) else None


def _announce_windows_close_guard(state: dict[str, Any]) -> None:
    with state["lock"]:
        if state.get("install_announced"):
            return
        state["install_announced"] = True
        owners = len(state["owners"])
    try:
        logging.getLogger(__name__).info(
            "HMB Windows normal-teardown compatibility guard enabled "
            "(recognized CPython stdlib, process-wide, owner_count=%s)", owners)
    except Exception:
        pass


def _known_windows_close_function(candidate: Any, transport_class: Any) -> bool:
    """Unknown runtimes/foreign wrappers retain their exact original behavior."""
    if (not inspect.isfunction(candidate) or hasattr(candidate, "__wrapped__")
            or candidate.__module__ != "asyncio.proactor_events"
            or candidate.__qualname__ != "_ProactorBasePipeTransport._call_connection_lost"
            or candidate.__globals__ is not vars(sys.modules["asyncio.proactor_events"])
            or candidate.__defaults__ is not None or candidate.__kwdefaults__ is not None
            or candidate is not transport_class.__dict__.get("_call_connection_lost")):
        return False
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(candidate)))
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            return False
        canonical = ast.dump(tree.body[0], annotate_fields=True, include_attributes=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == _WINDOWS_CLOSE_GUARD_AST_SHA256
    except (OSError, TypeError, SyntaxError, ValueError):
        return False


def _windows_close_diagnostic(transport: Any, sock: Any) -> dict[str, Any]:
    extra = getattr(transport, "_extra", None)
    extra = extra if isinstance(extra, dict) else {}
    def address(key: str, getter: str) -> Any:
        value = extra.get(key)
        if value is None:
            try:
                value = getattr(sock, getter)()
            except Exception:
                value = None
        return value
    local, peer = address("sockname", "getsockname"), address("peername", "getpeername")
    def port(value: Any) -> int | None:
        return value[1] if (isinstance(value, tuple) and len(value) >= 2
            and type(value[1]) is int and 0 <= value[1] <= 65535) else None
    loopback = None
    if isinstance(peer, tuple) and peer:
        try:
            loopback = ipaddress.ip_address(peer[0]).is_loopback
        except (TypeError, ValueError):
            pass
    protocol_type = type(transport._protocol)
    return {"protocol_class": (protocol_type.__module__ + "." + protocol_type.__qualname__)[:200],
        "local_port": port(local), "peer_loopback": loopback, "remote_port": port(peer)}


def _record_windows_close_reset(state: dict[str, Any], diagnostic: dict[str, Any]) -> None:
    with state["lock"]:
        state["handled_count"] = min(2 ** 31 - 1, state["handled_count"] + 1)
        first = state["first_diagnostic"] is None
        if first:
            state["first_diagnostic"] = diagnostic
    if first:
        try:
            logging.getLogger(__name__).info(
                "HMB Windows transport teardown cleanup completed after peer reset: "
                "protocol=%s local_port=%s peer_loopback=%s remote_port=%s",
                diagnostic["protocol_class"], diagnostic["local_port"],
                diagnostic["peer_loopback"], diagnostic["remote_port"])
        except Exception:
            pass  # Optional diagnostics must never replace a protocol failure.


def _acquire_windows_transport_close_guard(owner: Any) -> bool:
    """Own one process-wide, recognized CPython cleanup compatibility patch."""
    transport_class = _windows_transport_close_class()
    if transport_class is None:
        return False
    try:
        weakref.ref(owner)
        lock = _windows_transport_close_lock()
        if lock is None:
            return False
        with lock:
            current = transport_class.__dict__.get("_call_connection_lost")
            state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None)
            if state is not None:
                if (type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER
                        or not isinstance(state.get("owners"), weakref.WeakSet)
                        or getattr(state.get("wrapper"), "_hmb_windows_close_guard_state", None) is not state
                        or (current is not state.get("original") and current is not state.get("wrapper"))):
                    return False
                with state["lock"]:
                    state["owners"].add(owner)
                    if current is state["original"]:
                        transport_class._call_connection_lost = state["wrapper"]
                    _announce_windows_close_guard(state)
                return True
            if not _known_windows_close_function(current, transport_class):
                return False
            state = {"schema": _WINDOWS_CLOSE_GUARD_MARKER, "original": current,
                "owners": weakref.WeakSet(), "lock": threading.RLock(),
                "handled_count": 0, "first_diagnostic": None, "install_announced": False}
            def close(transport: Any, exc: Any) -> None:
                with state["lock"]:
                    active = bool(state["owners"])
                if not active:
                    return state["original"](transport, exc)
                if transport._called_connection_lost:
                    return
                # Recognized CPython/PSF teardown sequence: preserve callback,
                # shutdown, close, detach and completion ordering. Only normal
                # teardown's known Windows shutdown reset is recoverable here.
                diagnostic = None
                try:
                    transport._protocol.connection_lost(exc)
                finally:
                    if hasattr(transport._sock, "shutdown") and transport._sock.fileno() != -1:
                        try:
                            transport._sock.shutdown(socket.SHUT_RDWR)
                        except ConnectionResetError as error:
                            if exc is not None or getattr(error, "winerror", None) != 10054:
                                raise
                            diagnostic = _windows_close_diagnostic(transport, transport._sock)
                    transport._sock.close()
                    transport._sock = None
                    server = transport._server
                    if server is not None:
                        server._detach()
                        transport._server = None
                    transport._called_connection_lost = True
                    if diagnostic is not None:
                        _record_windows_close_reset(state, diagnostic)
            state["wrapper"] = close
            close._hmb_windows_close_guard_state = state
            # Another module/owner may have changed the method during source
            # inspection. Never replace a function we did not just recognize.
            if (transport_class.__dict__.get("_call_connection_lost") is not current
                    or getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None) is not None):
                return False
            state["owners"].add(owner)
            setattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, state)
            transport_class._call_connection_lost = close
            _announce_windows_close_guard(state)
            return True
    except Exception:
        return False  # Optional compatibility cannot block library editing.


def _release_windows_transport_close_guard(owner: Any) -> None:
    transport_class = _windows_transport_close_class()
    if transport_class is None:
        return
    try:
        lock = _windows_transport_close_lock()
        if lock is None:
            return
        with lock:
            state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None)
            if (type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER
                    or not isinstance(state.get("owners"), weakref.WeakSet)
                    or getattr(state.get("wrapper"), "_hmb_windows_close_guard_state", None) is not state):
                return
            with state["lock"]:
                state["owners"].discard(owner)
                if (not state["owners"]
                        and transport_class.__dict__.get("_call_connection_lost") is state["wrapper"]):
                    transport_class._call_connection_lost = state["original"]
    except Exception:
        return  # Unknown foreign state cannot break library unload.


def _windows_transport_close_guard_diagnostics() -> dict[str, Any]:
    transport_class = _windows_transport_close_class()
    state = getattr(transport_class, _WINDOWS_CLOSE_GUARD_MARKER, None) if transport_class else None
    if type(state) is not dict or state.get("schema") != _WINDOWS_CLOSE_GUARD_MARKER:
        return {"supported": transport_class is not None, "installed": False, "owner_count": 0, "handled_count": 0}
    with state["lock"]:
        return {"supported": True,
            "installed": transport_class.__dict__.get("_call_connection_lost") is state["wrapper"],
            "owner_count": len(state["owners"]), "handled_count": state["handled_count"],
            "first_diagnostic": dict(state["first_diagnostic"]) if state["first_diagnostic"] else None}

try:
    from griptape_nodes.retained_mode.events.flow_events import DeserializeFlowFromCommandsRequest
    from griptape_nodes.retained_mode.events.workflow_events import (
        RunWorkflowFromScratchRequest, RunWorkflowWithCurrentStateRequest,
        RunWorkflowFromRegistryRequest,
    )
    from griptape_nodes.retained_mode.managers.workflow.loading import is_loading_workflow
    _LOAD_TYPES = (DeserializeFlowFromCommandsRequest, RunWorkflowFromScratchRequest,
        RunWorkflowWithCurrentStateRequest, RunWorkflowFromRegistryRequest)
except ImportError:
    _LOAD_TYPES = ()
    is_loading_workflow = lambda: False

try:
    from griptape_nodes.retained_mode.events import flow_events, node_events, workflow_events
    _SERIALIZE_TYPES = tuple(value for module, name in (
        (flow_events, "SerializeFlowToCommandsRequest"),
        (node_events, "SerializeNodeToCommandsRequest"),
        (node_events, "SerializeSelectedNodesToCommandsRequest"),
    ) if isinstance(value := getattr(module, name, None), type))
    _SAVE_TYPES = tuple(value for name in (
        "SaveWorkflowRequest", "SaveWorkflowFileFromSerializedFlowRequest", "SaveSubflowToWorkflowRequest",
    ) if isinstance(value := getattr(workflow_events, name, None), type))
except ImportError:
    _SERIALIZE_TYPES, _SAVE_TYPES = (), ()

_CONTEXT_SNAPSHOT_BUSY_MESSAGE = (
    "The workflow is still loading, consolidating, or being serialized. "
    "Wait for it to finish, then retry this request. "
    "This request was refused; it was not queued and no workflow file was written."
)


def _context_snapshot_owner() -> tuple[int, int]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), id(task) if task is not None else 0


def _migration_module() -> Any:
    path = Path(__file__).with_name("_hmb_workflow_migration.py")
    name = "_hmb_workflow_migration"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    elif Path(module.__file__).resolve() != path.resolve():
        raise RuntimeError("Another installed HMB migration module owns this process")
    return module


def _kind_metadata(node: Any) -> Any:
    metadata = getattr(node, "metadata", None)
    return metadata.get("node_type") if isinstance(metadata, dict) and metadata.get("library") == _LIBRARY_NAME else None


def _empty_maps(engine: Any) -> tuple[dict, dict, dict] | None:
    """Require positive evidence of no retained objects, not a missing API.

    These SDK inventory maps are read only. The object table also rules out an
    untracked/intermediate object whose ownership map is not populated yet.
    Unknown layouts leave the stock CreateNode failure untouched.
    """
    maps = (
        getattr(engine.flow_manager, "_name_to_parent_name", None),
        getattr(engine.node_manager, "_name_to_parent_flow_name", None),
        getattr(engine.object_manager, "_name_to_objects", None),
    )
    if all(type(mapping) is dict and not mapping for mapping in maps):
        return maps
    return None


def _native_failure() -> CreateNodeResultFailure:
    return CreateNodeResultFailure(result_details=_EMPTY_CONTEXT_MESSAGE)


def _registered_unsaved_workflow(name: Any) -> bool:
    """Do not bootstrap a saved/unknown workflow that may still be loading."""
    if not isinstance(name, str) or not name.startswith("unsaved:"):
        return False
    try:
        identity = UUID(name[len("unsaved:"):])
        if name != "unsaved:" + str(identity):
            return False
        if WorkflowRegistry.has_workflow_with_name(name) is not True:
            return False
        return WorkflowRegistry.get_workflow_by_name(name).is_saved is False
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


class _DeletionProtectionError(RuntimeError):
    """A critical editor safety seam was not installed; never optional success."""


class _DeletionLifetimeGate:
    """Engine-owned guard independent of unloadable library registration leases."""
    protection_version = _DELETION_PROTECTION_VERSION

    def __init__(self, engine: Any, manager: Any, callback: Any) -> None:
        self.engine_ref = weakref.ref(engine)
        self.manager_ref = weakref.ref(manager)
        self.callback = callback
        self.installed = False
        self.ready = False
        self.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 초기화가 완료되지 않았습니다."
        self.hook = self.before_dispatch

    def is_registered(self) -> bool:
        manager = self.manager_ref()
        if manager is None:
            return False
        hooks = getattr(manager, "_pre_dispatch_hooks", None)
        lock = getattr(manager, "_pre_dispatch_hooks_lock", None) or getattr(manager, "_lock", None)
        if not isinstance(hooks, list) or not hasattr(lock, "__enter__") or not hasattr(lock, "__exit__"):
            raise RuntimeError("The SDK deletion-hook inventory is unavailable")
        with lock:
            return any(hook is self.hook for hook in hooks)

    def before_dispatch(self, request: Any, _result_context: Any) -> Any:
        if type(request).__name__ not in {"DeleteNodeRequest", "ResetNodeToDefaultsRequest",
                "DeleteFlowRequest", "ClearAllObjectStateRequest", "DeleteWorkflowRequest"}:
            return None
        engine, manager = self.engine_ref(), self.manager_ref()
        if engine is None or manager is None:
            return None
        # A trusted consolidation transaction transfers retained identities
        # before removing obsolete instances. Request flags never grant this.
        try:
            inventory = engine.node_manager._name_to_parent_flow_name
            if not isinstance(inventory, dict):
                raise RuntimeError("Retained HMB inventory is unavailable")
            has_hmb = False
            for name in tuple(inventory):
                node = engine.node_manager.get_node_by_name(name)
                metadata = getattr(node, "metadata", None)
                if node is None or not isinstance(metadata, dict):
                    raise RuntimeError("Retained node ownership is unavailable")
                has_hmb = has_hmb or metadata.get("library") == _LIBRARY_NAME
            if not has_hmb:
                return None  # A positively inventoried standard-only graph is native-owned.
            if not self.ready:
                raise RuntimeError("The HMB deletion gate is not ready")
            migration = sys.modules.get("_hmb_workflow_migration")
            if migration is not None and migration.mutation_is_internal():
                return None
            if engine.event_manager is not manager or not callable(self.callback):
                raise RuntimeError("The engine deletion gate lost its request handler")
            return self.callback(engine, request)
        except Exception:
            from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
            return GenericResultFailure(result_details=(
                "[HMB_DELETE_CHECK_FAILED] 삭제 보호 상태를 확인하지 못해 요청을 중단했습니다. "
                "Griptape를 다시 시작하세요. 기존 데이터는 유지됩니다."))


def _install_deletion_lifetime_gate(engine: Any, manager: Any) -> tuple[Any, Any]:
    required = ("add_pre_dispatch_hook", "remove_pre_dispatch_hook", "register_request_handlers")
    if any(not callable(getattr(manager, name, None)) for name in required):
        error = (
            "[HMB_DELETE_GUARD_UNSUPPORTED] HMB 삭제 보호에 필요한 "
            "predispatch/request-handler 기능을 확인할 수 없습니다. 현재 작업을 저장하고 지원 상태를 확인하세요.")
        existing = getattr(manager, _DELETION_GATE_ATTRIBUTE, None)
        if (getattr(existing, "protection_version", None) == _DELETION_PROTECTION_VERSION
                and callable(getattr(existing, "engine_ref", None))
                and existing.engine_ref() is engine):
            existing.ready = False
            existing.readiness_error = error
        raise _DeletionProtectionError(error)
    gate = getattr(manager, _DELETION_GATE_ATTRIBUTE, None)
    if gate is None:
        gate = _DeletionLifetimeGate(engine, manager, None)
        manager.add_pre_dispatch_hook(gate.hook)
        setattr(manager, _DELETION_GATE_ATTRIBUTE, gate)
    elif (getattr(gate, "protection_version", None) != _DELETION_PROTECTION_VERSION
            or not callable(getattr(gate, "engine_ref", None))
            or gate.engine_ref() is not engine
            or not callable(getattr(gate, "manager_ref", None))
            or gate.manager_ref() is not manager
            or not callable(getattr(gate, "is_registered", None))):
        raise _DeletionProtectionError("[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 등록의 소유권을 확인하지 못했습니다. Griptape를 다시 시작하세요.")
    gate.ready = False
    # A previous hot-loaded gate may still be an older class that does not
    # consult `ready`. Remove its callable until the stronger barrier is proven.
    gate.callback = None
    gate.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 초기화가 완료되지 않았습니다."
    if not gate.is_registered():
        manager.add_pre_dispatch_hook(gate.hook)
    if not gate.is_registered():
        raise _DeletionProtectionError(gate.readiness_error)
    gate.installed = True
    try:
        module = importlib.import_module("_hmb_deletion_guard")
    except Exception as exc:
        raise _DeletionProtectionError(gate.readiness_error) from exc
    expected = Path(__file__).with_name("_hmb_deletion_guard.py").resolve()
    if Path(getattr(module, "__file__", "")).resolve() != expected:
        gate.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 다른 HMB 설치의 삭제 보호 모듈이 로드되어 있습니다. Griptape를 다시 시작하세요."
        raise _DeletionProtectionError(gate.readiness_error)
    callback = getattr(module, "guard_request", None)
    # Git updates do not necessarily evict this helper from sys.modules. Keep
    # its exact old guard callable alive; never re-register SDK payload types.
    if (getattr(module, "PROTECTION_VERSION", None) != _DELETION_PROTECTION_VERSION
            or not callable(getattr(module, "protection_readiness", None))
            or not callable(getattr(module, "install_reentrant_barrier", None))):
        gate.ready = False
        gate.readiness_error = "[HMB_DELETE_GUARD_RESTART_REQUIRED] 이전 삭제 보호 코드가 메모리에 남아 있습니다. Griptape를 완전히 종료한 뒤 다시 시작하세요."
        raise _DeletionProtectionError(gate.readiness_error)
    if not callable(callback):
        gate.ready = False
        gate.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 함수가 준비되지 않았습니다."
        raise _DeletionProtectionError(gate.readiness_error)
    return gate, module


class _Registration:
    def __init__(self, engine: Any, manager: Any) -> None:
        self.engine = weakref.ref(engine)
        self.manager = weakref.ref(manager)
        self.owners: Any = weakref.WeakKeyDictionary()
        self.lock = threading.RLock()
        self.active = True
        # Store this exact callable for matching add/remove across lifecycle.
        self.hook = self.before_create
        self.prompt_post_hook = self.after_prompt_request
        self.prompt_post_types: list[Any] = []
        self.prompt_pending: dict[Any, tuple[Any, Any]] = {}
        self.load_requests: dict[int, Any] = {}
        self.load_post_hook = self.after_workflow_load
        self.load_post_types: list[Any] = []
        self.snapshot_requests: dict[int, tuple[Any, tuple[int, int]]] = {}
        self.snapshot_refused_loads: dict[int, Any] = {}
        self.snapshot_post_hook = self.after_context_snapshot
        self.snapshot_post_types: list[Any] = []
        self.web_worker_module = None
        self.deletion_handlers = None
        self.deletion_protection = None
        self.connection_handlers = None

    def start_web_worker(self) -> None:
        engine = self.engine()
        if not self.active or not self.owners or engine is None:
            return
        try:
            loop = engine.event_manager.event_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                return
            if self.web_worker_module is None:
                path = Path(__file__).with_name("_hmb_web_rerender.py")
                name = "_hmb_web_rerender"
                module = sys.modules.get(name)
                if module is None:
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    sys.modules[name] = module
                elif Path(module.__file__).resolve() != path.resolve():
                    return  # Do not bind another installed library's worker.
                self.web_worker_module = module
            self.web_worker_module.ensure_engine_worker(engine)
        except Exception:
            # Older hosts and optional Broker failures cannot block editing.
            return

    def before_create(self, request: Any, _result_context: Any) -> Any:
        # Dispatch is also the late-loop wakeup after a desktop startup that
        # loaded libraries before initializing its event queue.
        self.start_web_worker()
        snapshot_failure = self._guard_context_snapshot_request(request)
        if snapshot_failure is not None:
            return snapshot_failure
        migration_failure = self._guard_migration_mutation(request)
        if migration_failure is not None:
            if type(request) in _LOAD_TYPES:
                with self.lock:
                    self.load_requests.pop(id(request), None)
                    self.snapshot_refused_loads[id(request)] = weakref.ref(request)
            return migration_failure
        if type(request).__name__ == "GetWorkflowMetadataRequest":
            try:
                from _hmb_workflow_serialization_compat import recover_workflow_metadata
                recovered_metadata = recover_workflow_metadata(self, request)
                if recovered_metadata is not None:
                    return recovered_metadata
            except ImportError:
                pass  # Unknown/older SDKs retain the native metadata result.
        deletion_failure = self._guard_connected_deletion(request)
        if deletion_failure is not None:
            return deletion_failure
        connection_failure = self._guard_managed_connections(request)
        if connection_failure is not None:
            return connection_failure
        self._observe_workflow_load(request)
        prompt_failure = self._guard_prompt_creation(request)
        if prompt_failure is not None:
            return prompt_failure
        if (
            type(request) is not CreateNodeRequest
            or request.node_type not in (_NODE_TYPE, _IMAGE_NODE_TYPE)
            or request.specific_library_name not in (None, _LIBRARY_NAME)
            or request.override_parent_flow_name is not None
            or request.initial_setup is not False
            or request.set_as_new_context is not False
        ):
            return None
        attempted_bootstrap = False
        try:
            with self.lock:
                engine = self.engine()
                manager = self.manager()
                if (
                    not self.active
                    or not self.owners
                    or engine is None
                    or manager is None
                    or current_engine() is not engine
                    or engine.event_manager is not manager
                    or engine.library_manager.is_worker is not False
                ):
                    return None
                resolved = LibraryRegistry.get_library_for_node_type(
                    node_type=request.node_type,
                    specific_library_name=request.specific_library_name,
                )
                if (
                    resolved.get_library_data().name != _LIBRARY_NAME
                    or not any(reference() is resolved for reference in self.owners.values())
                ):
                    return None
                context = engine.context_manager
                if context.has_current_flow():
                    return None
                maps = _empty_maps(engine)
                if maps is None:
                    return None
                had_workflow = context.has_current_workflow()
                previous_workflow = context.get_current_workflow_name() if had_workflow else None
                if had_workflow and not _registered_unsaved_workflow(previous_workflow):
                    return None
                # Recheck immediately before any mutation. This guard's lock
                # serializes its own bootstrap requests and unload callbacks.
                current_maps = _empty_maps(engine)
                if (
                    context.has_current_flow()
                    or current_maps is None
                    or not all(current is previous for current, previous in zip(current_maps, maps))
                    or context.has_current_workflow() != had_workflow
                    or (had_workflow and context.get_current_workflow_name() != previous_workflow)
                    or (had_workflow and not _registered_unsaved_workflow(previous_workflow))
                ):
                    return None
                attempted_bootstrap = True
                ensured = engine.handle_request(EnsureWorkflowAndFlowRequest(display_name="Untitled"))
                if not isinstance(ensured, EnsureWorkflowAndFlowResultSuccess):
                    return _native_failure()
                flow_name = ensured.flow_name
                if not isinstance(flow_name, str) or not flow_name:
                    return _native_failure()
                flow = engine.flow_manager.get_flow_by_name(flow_name)
                # No other retained data may have appeared while the official
                # bootstrap ran. Pin its exact flow rather than rediscovering
                # a different ambient canvas during the original CreateNode.
                if (
                    not self.active
                    or engine.library_manager.is_worker is not False
                    or ensured.created_flow is not True
                    or ensured.created_workflow is not (not had_workflow)
                    or not context.has_current_flow()
                    or context.get_current_flow() is not flow
                    or context.get_current_workflow_name() != ensured.workflow_name
                    or (had_workflow and ensured.workflow_name != previous_workflow)
                    or not _registered_unsaved_workflow(ensured.workflow_name)
                    or engine.flow_manager._name_to_parent_name != {flow_name: None}
                    or engine.node_manager._name_to_parent_flow_name
                    or set(engine.object_manager._name_to_objects) != {flow_name}
                    or engine.object_manager._name_to_objects[flow_name] is not flow
                ):
                    return _native_failure()
                request.override_parent_flow_name = flow_name
                return None
        except Exception:
            # Unsupported APIs and preflight failures retain native behavior.
            # Once bootstrap was attempted, do not continue against an unknown
            # newly changed context and accidentally create in another canvas.
            return _native_failure() if attempted_bootstrap else None

    def _guard_connected_deletion(self, request: Any) -> Any:
        if type(request).__name__ not in {
            "DeleteNodeRequest", "ResetNodeToDefaultsRequest", "DeleteFlowRequest",
            "ClearAllObjectStateRequest", "DeleteWorkflowRequest",
        }:
            return None
        engine, manager = self.engine(), self.manager()
        gate = getattr(manager, _DELETION_GATE_ATTRIBUTE, None)
        try:
            if gate is not None and gate.is_registered():
                return None  # The engine-owned gate already ran before this lease.
        except Exception:
            pass  # An active legacy lease still protects an unverifiable gate.
        if not self._prompt_owner(engine, manager):
            return None
        # Consolidation transfers retained identities/results before removing
        # obsolete instances. Only its private scoped transaction may bypass
        # artist deletion protection; no request flag grants this privilege.
        migration = sys.modules.get("_hmb_workflow_migration")
        if migration is not None and migration.mutation_is_internal():
            return None
        from _hmb_deletion_guard import guard_request
        return guard_request(engine, request)

    def _guard_managed_connections(self, request: Any) -> Any:
        if type(request).__name__ not in {"CreateConnectionRequest", "ResolveNodeRequest"}:
            return None
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return None
        from _hmb_connection_management import guard_request
        return guard_request(engine, request)

    def _prompt_owner(self, engine: Any, manager: Any) -> bool:
        return bool(
            self.active and self.owners and engine is not None and manager is not None
            and callable(current_engine) and current_engine() is engine
            and engine.event_manager is manager and engine.library_manager.is_worker is False
        )

    def _is_hmb_prompt_create(self, request: Any) -> bool:
        if (type(request) is not CreateNodeRequest or request.node_type not in _EDITOR_NODE_TYPES
                or request.specific_library_name not in (None, _LIBRARY_NAME)):
            return False
        try:
            library = LibraryRegistry.get_library_for_node_type(
                node_type=request.node_type, specific_library_name=request.specific_library_name)
            return bool(library.get_library_data().name == _LIBRARY_NAME
                and any(reference() is library for reference in self.owners.values()))
        except Exception:
            return False

    @staticmethod
    def _prompt_target_flow(engine: Any, create_request: Any) -> Any:
        parent_name = create_request.override_parent_flow_name
        if parent_name is not None:
            try:
                return engine.flow_manager.get_flow_by_name(parent_name)
            except (KeyError, ValueError, TypeError):
                return None  # Preserve the native invalid-parent error.
        context = engine.context_manager
        return context.get_current_flow() if context.has_current_flow() else None

    @staticmethod
    def _flow_has_prompt(flow: Any, node_type: str = _PROMPT_NODE_TYPE) -> bool:
        nodes = getattr(flow, "nodes", None)
        if not isinstance(nodes, dict):
            return False
        for node in nodes.values():
            metadata = getattr(node, "metadata", None)
            if (isinstance(metadata, dict)
                    and metadata.get("library") == _LIBRARY_NAME
                    and metadata.get("node_type") == node_type
                    and not bool(getattr(node, "_hmb_node_deleted", False))):
                return True
        return False

    def _guard_prompt_creation(self, request: Any) -> Any:
        is_create = type(request) is CreateNodeRequest
        is_paste = (DeserializeSelectedNodesFromCommandsRequest is not None
            and type(request) is DeserializeSelectedNodesFromCommandsRequest)
        is_duplicate = (DuplicateSelectedNodesRequest is not None
            and type(request) is DuplicateSelectedNodesRequest)
        if not is_create and not is_paste and not is_duplicate:
            return None
        # Saved hydration restores every original first. Completed-load migration
        # takes a recovery snapshot before consolidating those instances.
        if is_create and (request.initial_setup is not False or not self._is_hmb_prompt_create(request)):
            return None
        with self.lock:
            engine, manager = self.engine(), self.manager()
            if not self._prompt_owner(engine, manager):
                return None
            creates = [request]
            if is_duplicate:
                creates = []
                try:
                    for item in request.nodes_to_duplicate:
                        node = engine.node_manager.get_node_by_name(item[0])
                        metadata = getattr(node, "metadata", None)
                        if not isinstance(metadata, dict):
                            continue
                        node_type = metadata.get("node_type")
                        if node_type not in _EDITOR_NODE_TYPES or metadata.get("library") != _LIBRARY_NAME:
                            continue
                        create = CreateNodeRequest(node_type=node_type, specific_library_name=_LIBRARY_NAME)
                        if self._is_hmb_prompt_create(create):
                            creates.append(create)
                except (KeyError, ValueError, TypeError, IndexError, AttributeError):
                    return None  # Preserve native malformed/missing-node errors.
            if is_paste:
                reader = getattr(engine.node_manager, "_read_copied_commands", None)
                if not callable(reader):
                    return None  # Older unsupported clipboard layouts stay native.
                try:
                    # The SDK's clipboard parser validates the same command
                    # envelope its paste handler consumes. No parameter values
                    # are read and no constructors/engine requests run here.
                    commands = reader(request.deserialize_commands)
                    creates = [item.create_node_command for item in commands.serialized_node_commands
                        if self._is_hmb_prompt_create(item.create_node_command)]
                except Exception:
                    return None  # Native paste reports corrupt clipboard input.
            destinations: dict[tuple[int, str], tuple[Any, int]] = {}
            for create in creates:
                flow = self._prompt_target_flow(engine, create)
                if flow is None:
                    continue
                key = (id(flow), create.node_type)
                destinations[key] = (flow, destinations.get(key, (None, 0))[1] + 1)
            for key, (flow, count) in destinations.items():
                pending = self.prompt_pending.get(key)
                if pending is not None and (pending[0]() is not flow or pending[1]() is None):
                    self.prompt_pending.pop(key, None)
                    pending = None
                if count > 1 or self._flow_has_prompt(flow, key[1]) or (pending is not None and pending[1]() is not request):
                    failure = (CreateNodeResultFailure if is_create else
                        DuplicateSelectedNodesResultFailure if is_duplicate else
                        DeserializeSelectedNodesFromCommandsResultFailure)
                    message = ((key[1] + " is already loaded in this flow. Use the existing Image Bash workspace; "
                        "another editor was not created.") if key[1] == _BASH_NODE_TYPE else
                        (key[1] + " is already loaded in this flow. Use its Shot controls to manage all Shots; "
                        "another editor was not created."))
                    # This is an expected admission decision, not a broken
                    # node. Keep the typed failure so a paste/duplicate caller
                    # cannot apply copied values or edges to the existing
                    # editor. Authored INFO details suppress the error toast
                    # without mutating the request or hiding native failures.
                    return failure(result_details=ResultDetails(message=message, level=logging.INFO))
            if type(request) in self.prompt_post_types:
                for key, (flow, _count) in destinations.items():
                    self.prompt_pending[key] = (weakref.ref(flow), weakref.ref(request))
        return None

    async def after_prompt_request(self, request: Any, _result: Any) -> None:
        # Notification-only official post-dispatch callback. Release a claim
        # after both success and failure; never alter the request, graph or UI.
        with self.lock:
            for key, (_flow, owner) in tuple(self.prompt_pending.items()):
                if owner() is None or owner() is request:
                    self.prompt_pending.pop(key, None)

    def _observe_workflow_load(self, request: Any) -> None:
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return
        if type(request) in _LOAD_TYPES:
            with self.lock:
                self.load_requests[id(request)] = weakref.ref(request)
            return
        if type(request) is SetParameterValueRequest and request.initial_setup is True:
            # SDK before_value_set runs even for initial_setup and transforms
            # request.value before the node's setter sees it. Capture original
            # saved identity here; never change that request or its value.
            name = request.node_name
            if name is None and engine.context_manager.has_current_node():
                name = engine.context_manager.get_current_node().name
            try:
                node = engine.node_manager.get_node_by_name(name)
            except (KeyError, ValueError, TypeError):
                node = None
            hook = getattr(node, "_hmb_capture_saved_parameter_value", None)
            if (_kind_metadata(node) in (_AGENT_NODE_TYPE, _FINISH_NODE_TYPE) and callable(hook)
                    and (is_loading_workflow() or self.load_requests)):
                hook(request.parameter_name, request.value, is_output=request.is_output)
            return
        if (type(request) is CreateNodeRequest and request.initial_setup is True
                and self._is_hmb_prompt_create(request)
                and (is_loading_workflow() or self.load_requests)):
            flow = self._prompt_target_flow(engine, request)
            if flow is not None:
                _migration_module().mark_flow_migration_pending(engine, flow.name)

    async def after_workflow_load(self, request: Any, result: Any) -> None:
        """Notification only: coordinator requests run on a later empty context."""
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return
        with self.lock:
            refused = self.snapshot_refused_loads.pop(id(request), None)
            if refused is not None and refused() is request:
                return  # A refused load never owned migration/load state.
            self.load_requests.pop(id(request), None)
            self.load_requests = {key: owner for key, owner in self.load_requests.items() if owner() is not None}
            if self.load_requests:
                return
        migration = _migration_module()
        if result.succeeded():
            migration.schedule_loaded_flow_migrations(engine)
        else:
            for name in migration.pending_flow_names(engine):
                migration.clear_flow_migration_pending(engine, name)

    def _guard_context_snapshot_request(self, request: Any) -> Any:
        """Refuse overlapping SDK scopes without repairing or guessing a Flow.

        SDK serialization enters process-shared Flow/Node context stacks. A
        second thread/task must not enter those scopes while a load or another
        serializer owns them. Only short registry updates hold ``self.lock``;
        it is never held across a handler, await, or detached post hook.
        """
        request_type = type(request)
        if request_type not in (*_SERIALIZE_TYPES, *_SAVE_TYPES, *_LOAD_TYPES):
            return None
        engine, manager = self.engine(), self.manager()
        if not self._prompt_owner(engine, manager):
            return None
        migration = sys.modules.get("_hmb_workflow_migration")
        internal = bool(migration is not None and migration.mutation_is_internal())
        owner = _context_snapshot_owner()
        with self.lock:
            self.load_requests = {key: reference for key, reference in self.load_requests.items() if reference() is not None}
            self.snapshot_requests = {key: value for key, value in self.snapshot_requests.items() if value[0]() is not None}
            another_serializer = any(value[1] != owner for value in self.snapshot_requests.values())
            if request_type in _LOAD_TYPES:
                busy = another_serializer
            else:
                loading = bool(self.load_requests) and not is_loading_workflow()
                migrating = bool(migration is not None and migration.flow_migration_inflight(engine))
                busy = bool(not internal and (loading or migrating))
                if request_type in _SERIALIZE_TYPES:
                    busy = busy or another_serializer
            if busy:
                if request_type in _LOAD_TYPES:
                    self.snapshot_refused_loads[id(request)] = weakref.ref(request)
                from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
                return GenericResultFailure(result_details=_CONTEXT_SNAPSHOT_BUSY_MESSAGE)
            if request_type in _LOAD_TYPES:
                # Publish the admission while still holding the same lock as
                # the serializer check. Waiting until _observe_workflow_load
                # leaves a window where another thread can admit a snapshot.
                self.load_requests[id(request)] = weakref.ref(request)
            if request_type in _SERIALIZE_TYPES and request_type in self.snapshot_post_types:
                # Nested SerializeNode/Flow requests in the same synchronous
                # owner are balanced native scopes, as are sequential requests
                # whose detached completion notifications have not run yet.
                self.snapshot_requests[id(request)] = (weakref.ref(request), owner)
        return None

    async def after_context_snapshot(self, request: Any, _result: Any) -> None:
        """Release only this request's admission, including native failures."""
        with self.lock:
            previous = self.snapshot_requests.get(id(request))
            if previous is not None and previous[0]() is request:
                self.snapshot_requests.pop(id(request), None)

    def _guard_migration_mutation(self, request: Any) -> Any:
        engine = self.engine()
        if engine is None:
            return None
        migration = sys.modules.get("_hmb_workflow_migration")
        if migration is None or migration.mutation_is_internal() or not migration.flow_migration_inflight(engine):
            return None
        name = type(request).__name__
        execution = name in {"StartFlowRequest", "StartLocalSubflowRequest", "StartFlowFromNodeRequest",
            "ContinueExecutionStepRequest", "ExecuteNodeRequest", "ResolveNodeRequest",
            "RunWorkflowFromScratchRequest", "RunWorkflowWithCurrentStateRequest", "RunWorkflowFromRegistryRequest"}
        if not execution and not name.startswith(("Create", "Delete", "Remove", "Set", "Alter", "Add", "Move", "Rename", "Reset", "Resolve", "Run", "Clear", "Deserialize", "Duplicate", "Import", "Unregister", "Reload")):
            return None
        flows = {getattr(request, key, None) for key in ("flow_name", "override_parent_flow_name", "parent_flow_name")}
        flows.discard(None)
        for key in ("node_name", "source_node_name", "target_node_name"):
            node_name = getattr(request, key, None)
            parent = engine.node_manager._name_to_parent_flow_name.get(node_name)
            if parent is not None:
                flows.add(parent)
        for key in ("node_names", "nodes_to_delete", "nodes_to_duplicate"):
            for item in getattr(request, key, ()) or ():
                node_name = item[0] if isinstance(item, (list, tuple)) and item else item
                if isinstance(node_name, str):
                    parent = engine.node_manager._name_to_parent_flow_name.get(node_name)
                    if parent is not None:
                        flows.add(parent)
        if not flows and engine.context_manager.has_current_flow():
            flows.add(engine.context_manager.get_current_flow().name)
        # Native migration deletion is permitted only while the whole engine is
        # idle, so execution in a different flow must wait for consolidation too.
        global_mutation = execution or type(request) in _LOAD_TYPES or name.startswith(("ClearAll", "DeleteWorkflow", "ResetWorkflow", "UnregisterLibrary", "ReloadLibrary"))
        if global_mutation or not flows or any(migration.flow_migration_inflight(engine, flow_name) for flow_name in flows):
            from griptape_nodes.retained_mode.events.generic_events import GenericResultFailure
            return GenericResultFailure(result_details="HMB editor consolidation is updating this flow. Retry after it finishes; no render was started.")
        return None


class HMBProductionLibrary(AdvancedNodeLibrary):
    def __init__(self) -> None:
        self._registrations: set[_Registration] = set()
        # The SDK may log and continue after a before-load hook throws. Arm
        # the engine-owned deletion boundaries in the constructor, whose
        # failure rejects registration before HMB node classes are loaded.
        if not callable(current_engine):
            raise _DeletionProtectionError("[HMB_DELETE_GUARD_UNSUPPORTED] Engine 보호 컨텍스트를 확인할 수 없습니다.")
        engine = current_engine()
        manager = getattr(engine, "library_manager", None) if engine is not None else None
        is_worker = getattr(manager, "is_worker", None)
        if is_worker is not True and is_worker is not False:
            raise _DeletionProtectionError("[HMB_DELETE_GUARD_NOT_READY] Engine 편집기 소유권을 확인할 수 없습니다.")
        if is_worker is False:
            with _REGISTRY_LOCK:
                gate, deletion_module = _install_deletion_lifetime_gate(engine, engine.event_manager)
                deletion_module.install_reentrant_barrier(engine)
                deletion_module.install_handler_barrier(engine)
        self._hmb_environment_repair_summary = _hmb_coordinate_environment_repair()

    def before_library_nodes_loaded(self, library_data: Any, library: Any) -> None:
        """Register at library load, before the first lazy CreateNode check."""
        if library_data.name != _LIBRARY_NAME:
            return
        if not callable(current_engine):
            self._hmb_deletion_readiness_error = "[HMB_DELETE_GUARD_UNSUPPORTED] Engine 현재 컨텍스트 API를 사용할 수 없습니다. Griptape를 업데이트하세요."
            raise _DeletionProtectionError(self._hmb_deletion_readiness_error)
        engine = current_engine()
        if engine is None:
            self._hmb_deletion_readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 현재 Engine 컨텍스트를 확인하지 못했습니다. Griptape를 다시 시작하세요."
            raise _DeletionProtectionError(self._hmb_deletion_readiness_error)
        if engine.library_manager.is_worker is True:
            return  # Worker execution is not the retained desktop editor.
        if engine.library_manager.is_worker is not False:
            self._hmb_deletion_readiness_error = "[HMB_DELETE_GUARD_NOT_READY] Engine 편집기/worker 소유권을 확인하지 못했습니다."
            raise _DeletionProtectionError(self._hmb_deletion_readiness_error)
        # A Git/Override update may retain an older guard module. Schedule the
        # cache-free, independently validated disk update before that explicit
        # restart-required boundary; its outcome never grants deletion access.
        try:
            _hmb_coordinate_native_editor_update(self, engine, library_data)
        except Exception as exc:
            # This optional disk/UI step must never skip the required engine
            # protection below, including unexpected coordinator failures.
            summary = _hmb_native_editor_summary("error", "native_coordinator_failed:" + type(exc).__name__, restart_required=True)
            self._hmb_native_editor_update_identity = None
            engine._hmb_native_editor_update_identity = None
            _hmb_native_editor_publish(self, engine, None, summary)
            logging.getLogger(__name__).warning("[HMB_NATIVE_EDITOR_UPDATE] %s", summary["reason"])
        manager = engine.event_manager
        try:
            with _REGISTRY_LOCK:
                gate, deletion_module = _install_deletion_lifetime_gate(engine, manager)
        except Exception as exc:
            error = str(exc) if isinstance(exc, _DeletionProtectionError) else "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 초기화에 실패했습니다. Griptape를 다시 시작하세요."
            self._hmb_deletion_readiness_error = error
            if isinstance(exc, _DeletionProtectionError):
                raise
            raise _DeletionProtectionError(error) from exc
        gate.ready = False
        gate.readiness_error = "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 등록이 완료되지 않았습니다."
        try:
            library_reference = weakref.ref(library)
            with _REGISTRY_LOCK:
                registration = _REGISTRATIONS.get(manager)
                if registration is None or not registration.active:
                    registration = _Registration(engine, manager)
                    manager.add_pre_dispatch_hook(registration.hook)
                    if callable(getattr(manager, "add_post_dispatch_hook", None)) and callable(getattr(manager, "remove_post_dispatch_hook", None)):
                        for request_type in (CreateNodeRequest, DeserializeSelectedNodesFromCommandsRequest):
                            if request_type is not None:
                                manager.add_post_dispatch_hook(request_type, registration.prompt_post_hook)
                                registration.prompt_post_types.append(request_type)
                        for request_type in _LOAD_TYPES:
                            manager.add_post_dispatch_hook(request_type, registration.load_post_hook)
                            registration.load_post_types.append(request_type)
                        for request_type in _SERIALIZE_TYPES:
                            manager.add_post_dispatch_hook(request_type, registration.snapshot_post_hook)
                            registration.snapshot_post_types.append(request_type)
                    _REGISTRATIONS[manager] = registration
                elif registration.engine() is not engine:
                    raise _DeletionProtectionError("[HMB_DELETE_GUARD_NOT_READY] 등록된 Engine 소유권이 변경되었습니다.")
                with registration.lock:
                    registration.owners[self] = library_reference
                    self._registrations.add(registration)
                    registration.deletion_protection = gate
                    if registration.deletion_handlers is None:
                        registration.deletion_handlers = deletion_module.install_request_handlers(engine, registration)
                    if registration.deletion_handlers is None:
                        raise _DeletionProtectionError("[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 요청 핸들러가 등록되지 않았습니다.")
                    barrier = deletion_module.install_reentrant_barrier(engine)
                    if (not callable(getattr(barrier, "is_installed", None))
                            or not barrier.is_installed()
                            or not callable(getattr(barrier, "engine_ref", None))
                            or barrier.engine_ref() is not engine):
                        raise _DeletionProtectionError("[HMB_DELETE_GUARD_NOT_READY] 재진입 삭제 보호가 준비되지 않았습니다.")
                    gate.callback = deletion_module.guard_request
                    gate.ready = True
                    gate.readiness_error = ""
                    self._hmb_deletion_readiness_error = ""
                    if registration.connection_handlers is None:
                        from _hmb_connection_management import install_request_handlers
                        registration.connection_handlers = install_request_handlers(engine, registration)
                    _acquire_windows_transport_close_guard(registration)
                    try:
                        from _hmb_workflow_serialization_compat import acquire as acquire_save_identity_guard
                        acquire_save_identity_guard(registration)
                    except ImportError:
                        pass  # Older hosts can omit this optional SDK seam.
                    registration.start_web_worker()
        except Exception as exc:
            if not gate.ready:
                gate.readiness_error = (str(exc) if "[HMB_DELETE_GUARD_RESTART_REQUIRED]" in str(exc)
                    else "[HMB_DELETE_GUARD_NOT_READY] 삭제 보호 초기화에 실패했습니다. Griptape를 다시 시작하세요.")
                self._hmb_deletion_readiness_error = gate.readiness_error
                raise _DeletionProtectionError(gate.readiness_error) from exc
            # Windows compatibility, environment coordination and the web
            # worker are optional. Their failure must not remove a ready gate.
            logging.getLogger(__name__).warning("[HMB_OPTIONAL_BOOTSTRAP_FAILED] %s", type(exc).__name__)

    def before_library_unregistered(self, _library_data: Any, _library: Any) -> None:
        with _REGISTRY_LOCK:
            for registration in tuple(self._registrations):
                with registration.lock:
                    registration.owners.pop(self, None)
                    if registration.owners:
                        continue
                    registration.active = False
                    _release_windows_transport_close_guard(registration)
                    try:
                        from _hmb_workflow_serialization_compat import release as release_save_identity_guard
                        release_save_identity_guard(registration)
                    except ImportError:
                        pass
                    registration.prompt_pending.clear()
                    registration.load_requests.clear()
                    registration.snapshot_requests.clear()
                    registration.snapshot_refused_loads.clear()
                    engine = registration.engine()
                    migration = sys.modules.get("_hmb_workflow_migration")
                    if migration is not None and engine is not None:
                        migration.cancel_queued_flow_migrations(engine)
                    if registration.web_worker_module is not None and engine is not None:
                        registration.web_worker_module.stop_engine_worker(engine)
                    manager = registration.manager()
                    if manager is not None:
                        handler = registration.connection_handlers
                        if handler is not None and handler.owner_ref() is registration:
                            try:
                                manager.remove_pre_dispatch_hook(handler.protect_detached_ports)
                            except Exception:
                                pass  # An inactive owner cannot remove leased ports.
                        try:
                            manager.remove_pre_dispatch_hook(registration.hook)
                        except Exception:
                            pass  # Inactive stale callbacks cannot bootstrap.
                        for request_type in registration.prompt_post_types:
                            try:
                                manager.remove_post_dispatch_hook(request_type, registration.prompt_post_hook)
                            except Exception:
                                pass
                        registration.prompt_post_types.clear()
                        for request_type in registration.load_post_types:
                            try:
                                manager.remove_post_dispatch_hook(request_type, registration.load_post_hook)
                            except Exception:
                                pass
                        registration.load_post_types.clear()
                        for request_type in registration.snapshot_post_types:
                            try:
                                manager.remove_post_dispatch_hook(request_type, registration.snapshot_post_hook)
                            except Exception:
                                pass
                        registration.snapshot_post_types.clear()
                        if _REGISTRATIONS.get(manager) is registration:
                            _REGISTRATIONS.pop(manager, None)
            self._registrations.clear()
