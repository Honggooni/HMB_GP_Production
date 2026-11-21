"""Publish poster/preview media for an existing completed Broker task from this workstation."""
from __future__ import annotations

from concurrent.futures import CancelledError, Future, wait
from contextlib import contextmanager
import errno
import hashlib
import http.client
import io
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from _hmb_broker_config import join_broker_url, normalize_broker_base_url
from _hmb_color_lut import ColorLUTError, make_review_media

_LOG = logging.getLogger(__name__)
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_CHUNK = 1024 * 1024
_MAX_SOURCE_BYTES = 16 * 1024**3
_SOURCE_EXTENSIONS = (".mov", ".mp4", ".m4v", ".webm")
_HEARTBEAT = 8
_WORK_SLOTS = threading.BoundedSemaphore(3)
# A disconnected node can abandon a promise without cancelling it. Release its claim
# without performing a competing download while its disposition remains unknown.
_SOURCE_WAIT_SECONDS = 30 * 60
_LOCK = threading.RLock()
_ACTIVE = {}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _task_path(task):
    _require(isinstance(task, str) and _TASK.fullmatch(task), "Invalid Broker task identity")
    return "/api/v1/reviews/tasks/" + quote(task, safe="") + "/workstation-media"


def _url(origin, route, task):
    # The server can return the API path or that path behind its mount. On a
    # gateway mounted at /api the leading /api in /api/v1 belongs to the API.
    mount = urlsplit(origin).path
    if isinstance(route, str) and mount and route.startswith(mount + "/api/v1/"):
        route = route[len(mount):]
    url = join_broker_url(origin, route)
    path = urlsplit(url[len(origin):]).path
    _require(path.startswith("/api/v1/") and quote(task, safe="") in path.split("/"),
             "Broker media route is not bound to the completed task")
    return url


class _Session:
    def __init__(self, bridge):
        self.origin = normalize_broker_base_url(bridge.server_url)
        self.opener = bridge._opener
        self.token = bridge._load_access_token()
        _require(isinstance(self.token, str) and self.token, "Broker login required")

    def open(self, url, *, data=None, headers=None, timeout=20):
        request = Request(url, data=data, headers={"Authorization": "Bearer " + self.token, **(headers or {})},
                          method="POST" if data is not None else "GET")
        response = self.opener.open(request, timeout=timeout)
        if response.geturl() != url:
            response.close()
            raise ValueError("Broker media response changed its URL")
        return response

    def get_json(self, url):
        with self.open(url, headers={"Accept": "application/json"}) as response:
            _require(response.status == 200, "Unexpected Broker metadata status")
            return _read_json(response)


def _read_json(response):
    data = response.read(65537)
    _require(len(data) <= 65536, "Oversized Broker metadata")
    obj = json.loads(data)
    _require(isinstance(obj, dict), "Invalid Broker media response")
    return obj


class _WorkstationHandoff(Exception):
    """A confirmed broker ownership change ends local work."""


class _WorkstationLease:
    def __init__(self, session, endpoint, task, sha, key, cancel_event):
        self.session, self.endpoint = session, endpoint
        self.task, self.sha = task, sha
        self.headers = {"X-HMB-Source-SHA256": sha, "Idempotency-Key": key, "Content-Length": "0"}
        self.state = "waiting"
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self._sending = threading.Lock()

    def confirm(self):
        """Renew ownership now, returning the confirmed state before a sidecar upload."""
        with self._sending:
            if self.state != "waiting":
                return self.state
            with self.session.open(self.endpoint, data=b"", headers=self.headers, timeout=4) as response:
                if response.status == 204:
                    return self.state
                _require(response.status == 200, "Heartbeat declined")
                result = _read_json(response)
            _require(result.get("task_id") == self.task and result.get("state") in ("waiting", "ready", "fallback")
                     and result.get("source_sha256", self.sha) == self.sha, "Invalid workstation heartbeat receipt")
            self.state = result["state"]
            if self.state != "waiting":
                self.cancel_event.set()
            return self.state

    def check(self):
        if self.state != "waiting":
            raise _WorkstationHandoff(self.state)
        if self.cancel_event.is_set():
            raise CancelledError()


@contextmanager
def workstation_media_heartbeat(bridge, *, heartbeat_url, task_id, source_sha256, idempotency_key, cancel_event=None):
    """Maintain the broker claim until local media publishing ends; never refresh credentials."""
    session = bridge if isinstance(bridge, _Session) else _Session(bridge)
    endpoint = _url(session.origin, heartbeat_url, task_id)
    _require(endpoint == join_broker_url(session.origin, _task_path(task_id) + "/heartbeat")
             and isinstance(source_sha256, str) and _SHA.fullmatch(source_sha256) and _valid_key(idempotency_key),
             "Invalid workstation heartbeat identity")
    stop = threading.Event()
    lease = _WorkstationLease(session, endpoint, task_id, source_sha256, idempotency_key, cancel_event)

    def renew():
        try:
            lease.confirm()
        except HTTPError as exc:
            exc.close()
        except (OSError, ValueError, http.client.HTTPException):
            pass

    def beat():
        due = first_beat + _HEARTBEAT
        while lease.state == "waiting" and not stop.wait(max(0, due - time.monotonic())):
            due = time.monotonic() + _HEARTBEAT
            renew()

    first_beat = time.monotonic()
    lease.confirm()
    thread = threading.Thread(target=beat, name="HMBReviewHeartbeat", daemon=True)
    thread.start()
    try:
        yield lease
    finally:
        stop.set()
        thread.join()


def _valid_key(key):
    return isinstance(key, str) and bool(_SHA.fullmatch(key))


def _state(session, task):
    state = session.get_json(join_broker_url(session.origin, _task_path(task)))
    _require(state.get("task_id") == task and state.get("state") in ("waiting", "ready", "fallback") and
             isinstance(state.get("source_sha256"), str) and _SHA.fullmatch(state["source_sha256"]),
             "Invalid Broker workstation media state")
    if state["state"] == "waiting":
        _require(type(state.get("source_bytes")) is int and 0 < state["source_bytes"] <= _MAX_SOURCE_BYTES and
                 _valid_key(state.get("idempotency_key")), "Invalid Broker original identity")
        base = _task_path(task)
        normal_original = base.removesuffix("/workstation-media") + "/download"
        private_original = "/api/v1/only/my-box/items/" + quote(task, safe="") + "/media?download=1"
        expected = {"heartbeat_url": (base + "/heartbeat",),
                    "original_url": (private_original if task.startswith("job-mybox-") else normal_original,),
                    "upload_url": (base, base.removesuffix("workstation-media") + "color-lut/media")}
        for field, routes in expected.items():
            actual = _url(session.origin, state[field], task)
            _require(any(actual == join_broker_url(session.origin, route) for route in routes), "Unexpected " + field)
    return state


def get_workstation_media_state(bridge, task_id):
    """Authenticated read for an already negotiated pc-v1 task, without download or submission."""
    return _state(_Session(bridge), task_id)


def _cache_directory(session, task, state):
    me = session.get_json(join_broker_url(session.origin, "/api/me"))
    principal = me.get("id", me.get("user_id"))
    if type(principal) is not int or principal <= 0:
        principal = me.get("username")
        _require(isinstance(principal, str) and 0 < len(principal) <= 256, "Missing authenticated account identity")
    key = hashlib.sha256(json.dumps([session.origin, principal, task], ensure_ascii=True).encode()).hexdigest()
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache"))
    return root / "HMB_GP_Production" / "ReviewMedia" / key / state["source_sha256"]


@contextmanager
def _file_lock(directory, lease=None):
    """OS locks release on process exit, including exit during a large original download."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "work.lock").open("a+b") as lock:
        lock.seek(0)
        waited = False
        while True:
            if lease is not None:
                lease.check()
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                waited = True
                time.sleep(.15)
        # Closing the descriptor releases the lock on both platforms.
        yield waited


def _valid_file(path, length, sha, lease=None):
    if not path.is_file() or path.stat().st_size != length:
        return False
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        while block := stream.read(_CHUNK):
            if lease is not None:
                lease.check()
            digest.update(block)
    return digest.hexdigest() == sha


def _verified_local_path(path, length, sha, lease=None):
    try:
        resolved = path.resolve(strict=True)
        if resolved.suffix.lower() in _SOURCE_EXTENSIONS and _valid_file(resolved, length, sha, lease):
            return resolved
    except (OSError, RuntimeError, ValueError):
        # A node's result or a recorded location can disappear between callbacks.
        pass
    return None


def _save_stream(stream, directory, length, sha, lease=None):
    digest, size = hashlib.sha256(), 0
    temporary = directory / "source.part"
    try:
        with temporary.open("wb") as out:
            while True:
                if lease is not None:
                    lease.check()
                block = stream.read(min(_CHUNK, length - size + 1))
                if not block:
                    break
                size += len(block)
                _require(size <= length, "Original exceeds the authorized size")
                digest.update(block)
                out.write(block)
            if size < length:
                raise EOFError("Original ended before its authorized length")
            _require(digest.hexdigest() == sha, "Original SHA-256 mismatch")
            out.flush()
            os.fsync(out.fileno())
        with temporary.open("rb") as verified:
            head = verified.read(16)
        suffix = ".mov"
        if head.startswith(b"\x1a\x45\xdf\xa3"):
            suffix = ".webm"
        elif head.startswith(b"\x00\x00\x01") or head[4:11] == b"ftypM4V":
            suffix = ".m4v"
        elif head[4:8] == b"ftyp" and head[8:12] != b"qt  ":
            suffix = ".mp4"
        dest = directory / ("source" + suffix)
        if lease is not None:
            lease.check()
        os.replace(temporary, dest)
        return dest
    finally:
        temporary.unlink(missing_ok=True)


def _original(session, task, state, directory, local_source, lease=None):
    length, sha = state["source_bytes"], state["source_sha256"]
    pointer = directory / "local-source.json"
    if local_source is not None and not isinstance(local_source, bytes):
        path = _verified_local_path(Path(local_source), length, sha, lease)
        if path is not None:
            temporary = pointer.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps({"path": str(path)}, ensure_ascii=True), encoding="utf-8")
                os.replace(temporary, pointer)
            finally:
                temporary.unlink(missing_ok=True)
            return path
    for suffix in _SOURCE_EXTENSIONS:
        cached = directory / ("source" + suffix)
        if _valid_file(cached, length, sha, lease):
            return cached
    if isinstance(local_source, bytes):
        with io.BytesIO(local_source) as stream:
            return _save_stream(stream, directory, length, sha, lease)
    if pointer.is_file():
        try:
            with pointer.open("rb") as record:
                path = Path(json.loads(record.read(16384))["path"])
            if path.is_absolute() and path != local_source:
                path = _verified_local_path(path, length, sha, lease)
                if path is not None:
                    return path
        except (OSError, KeyError, ValueError, TypeError):
            pass
    url = _url(session.origin, state["original_url"], task)
    for attempt in range(2):
        if lease is not None:
            lease.check()
        try:
            with session.open(url, headers={"Accept": "video/quicktime, video/mp4, video/webm, video/x-m4v",
                                            "Accept-Encoding": "identity"},
                              timeout=120) as response:
                _require(response.status == 200 and not response.headers.get("Content-Range") and
                         response.headers.get("Content-Encoding", "identity").lower() == "identity",
                         "Invalid original media response")
                advertised = response.headers.get("Content-Length")
                _require(advertised is None or advertised == str(length), "Broker original Content-Length mismatch")
                return _save_stream(response, directory, length, sha, lease)
        except (HTTPError, URLError, ConnectionError, TimeoutError, EOFError, http.client.IncompleteRead) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
                if exc.code not in (408, 429, 502, 503, 504):
                    raise
            if attempt:
                raise
            time.sleep(.25)


def _attach(session, task, state, poster, preview, lease):
    url = _url(session.origin, state["upload_url"], task)
    def body():
        for path in (poster, preview):
            with path.open("rb") as stream:
                while block := stream.read(_CHUNK):
                    lease.check()
                    yield block
    poster_bytes = poster.stat().st_size
    lease.check()
    with session.open(url, data=body(), timeout=180, headers={"Content-Type": "application/octet-stream",
            "X-HMB-Source-SHA256": state["source_sha256"], "Idempotency-Key": state["idempotency_key"],
            "X-HMB-Poster-Bytes": str(poster_bytes), "Content-Length": str(poster_bytes + preview.stat().st_size)}) as resp:
        _require(resp.status in (200, 201), "Unexpected media upload response")
        result = _read_json(resp)
    _require(result.get("derived_task_id") == task and result.get("state") == "ready" and
             result.get("source_sha256") == state["source_sha256"], "Unconfirmed workstation media receipt")


def _work(session, task, local_source):
    try:
        caps = session.get_json(join_broker_url(session.origin, "/api/v1/reviews/capabilities"))
        if caps.get("workstation_review_media") != "pc-v1" or caps.get("workstation_fallback_seconds") != 30:
            return {"state": "unsupported"}
        state = _state(session, task)
    except HTTPError as exc:
        if exc.code not in (404, 405, 501):
            raise
        exc.close()
        return {"state": "unsupported"}
    sha = state["source_sha256"]
    receipt = {"state": "ready", "derived_task_id": task, "source_sha256": sha}
    if state["state"] != "waiting":
        return {**receipt, "state": state["state"]}
    _require(_url(session.origin, state["upload_url"], task) == join_broker_url(session.origin, _task_path(task)),
             "This task requires the existing LUT-specific publishing operation")
    with workstation_media_heartbeat(session, heartbeat_url=state["heartbeat_url"], task_id=task,
            source_sha256=sha, idempotency_key=state["idempotency_key"]) as lease:
        try:
            lease.check()
            claimed_at = time.monotonic()
            directory = _cache_directory(session, task, state)
            if isinstance(local_source, Future):
                deadline = time.monotonic() + _SOURCE_WAIT_SECONDS
                while not local_source.done():
                    lease.check()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("The original source did not finish")
                    wait((local_source,), timeout=min(.25, remaining))
                lease.check()
                local_source = local_source.result()
            with _file_lock(directory, lease) as waited:
                while not _WORK_SLOTS.acquire(timeout=.25):
                    lease.check()
                try:
                    lease.check()
                    recheck = waited or time.monotonic() - claimed_at >= _HEARTBEAT
                    return _publish_locked(session, task, state, receipt, directory, local_source, recheck, lease)
                finally:
                    _WORK_SLOTS.release()
        except _WorkstationHandoff as handoff:
            return {**receipt, "state": handoff.args[0]}
        except (OSError, http.client.HTTPException, ColorLUTError):
            if lease.state != "waiting":
                return {**receipt, "state": lease.state}
            raise


def _publish_locked(session, task, state, receipt, directory, local_source, waited, lease):
    sha = state["source_sha256"]
    completed = directory / "receipt.json"
    if waited or completed.exists():
        current = _state(session, task)
        _require(current["source_sha256"] == sha, "The workstation source changed while waiting")
        if current["state"] != "waiting":
            return {**receipt, "state": current["state"]}
        _require(current["idempotency_key"] == state["idempotency_key"], "The workstation upload key changed")
        state = current
    lease.check()
    original = _original(session, task, state, directory, local_source, lease)
    with tempfile.TemporaryDirectory(prefix="encode-", dir=directory) as work:
        lease.check()
        try:
            poster, preview = make_review_media(original, Path(work), lease.cancel_event, expected_sha256=sha)
        except (ColorLUTError, OSError):
            lease.check()
            if original.parent == directory or _verified_local_path(original, state["source_bytes"], sha, lease) is not None:
                raise
            # An external result can move or change after verification, even mid-encode.
            # Retry once from the same task's verified cache or authenticated original.
            original = _original(session, task, state, directory, None, lease)
            lease.check()
            poster, preview = make_review_media(original, Path(work), lease.cancel_event, expected_sha256=sha)
        lease.confirm()
        lease.check()
        try:
            _attach(session, task, state, poster, preview, lease)
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
            # Acceptance and the network response can happen on opposite sides of a disconnect.
            current = _state(session, task)
            if current["source_sha256"] != sha or current["state"] == "waiting":
                raise
            if current["state"] == "fallback":
                return {**receipt, "state": "fallback"}
    temporary = completed.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        os.replace(temporary, completed)
    except OSError as exc:
        # A verified Broker receipt remains valid even when this PC cannot cache it.
        _LOG.warning("Confirmed review media receipt could not be cached (%s).", type(exc).__name__)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return receipt


def schedule_completed_review_media(bridge, task_id, *, local_source=None, private=False) -> Future:
    """Schedule independent media work, optionally sharing the node's pending original Future."""
    try:
        _task_path(task_id)
        _require(bool(private) == task_id.startswith("job-mybox-"), "Private task scope mismatch")
        origin = normalize_broker_base_url(bridge.server_url)
        # Regular generation has already authenticated this bridge. For an injected
        # origin-scoped session, share only that exact bridge until GET /api/me.
        fingerprint = getattr(bridge, "_reference_auth_digest", "")
        identity = fingerprint or id(bridge)
        key = (origin, identity, task_id)
        with _LOCK:
            active = _ACTIVE.get(key)
            if active is not None and not active.done():
                return active
            job = Future()
            _ACTIVE[key] = job
            def run():
                try:
                    if job.set_running_or_notify_cancel():
                        # A missing credential can invoke legacy migration I/O. Keep
                        # all authentication and network work off the caller's thread.
                        session = _Session(bridge)
                        _require(session.origin == origin and (not fingerprint or
                                 hashlib.sha256(session.token.encode()).hexdigest() == fingerprint),
                                 "Broker account changed before media preparation")
                        job.set_result(_work(session, task_id, local_source))
                except Exception as exc:
                    if not isinstance(exc, CancelledError):
                        _LOG.warning("Review media preparation deferred (%s).", type(exc).__name__)
                    job.set_exception(exc)
                finally:
                    with _LOCK:
                        if _ACTIVE.get(key) is job:
                            del _ACTIVE[key]
            # A queue of large downloads must not delay the start of another task's
            # 30-second Broker claim. Only transfer and encoding occupy the heavy slots.
            try:
                threading.Thread(target=run, name="HMBReviewMedia", daemon=True).start()
            except RuntimeError:
                del _ACTIVE[key]
                raise
            return job
    except Exception as exc:
        job = Future()
        job.set_exception(exc)
        return job
