from __future__ import annotations

import atexit
import json
import threading
from collections.abc import Callable
from typing import Any


_SESSION_PAYLOAD_MAX_BYTES = 1024 * 1024
_STATE_EMPTY = "empty"
_STATE_LOADING = "loading"
_STATE_READY = "ready"
_STATE_FAILED = "failed"
_STATE_CLOSED = "closed"
_SESSION_UNAVAILABLE_MESSAGE = (
    "HMB Agent policy session is unavailable until Griptape restarts."
)

_condition = threading.Condition(threading.RLock())
_state = _STATE_EMPTY
_payload_bytes: bytearray | None = None


def _wipe(value: bytearray | None) -> None:
    """Overwrite one owned mutable buffer without making a best-effort claim absolute."""

    if value is None:
        return
    for index in range(len(value)):
        value[index] = 0


def _encode_private_snapshot(payload: dict[str, Any]) -> bytearray:
    """Own one canonical mutable representation of the verified policy payload."""

    if type(payload) is not dict:
        raise TypeError("verified Agent policy payload must be an object")
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if not encoded or len(encoded) > _SESSION_PAYLOAD_MAX_BYTES:
        raise ValueError("verified Agent policy payload has an invalid size")
    return bytearray(encoded)


def _decode_private_snapshot(value: bytearray) -> dict[str, Any]:
    """Return a new object so an Agent execution cannot mutate session authority."""

    decoded = json.loads(bytes(value).decode("utf-8"))
    if type(decoded) is not dict:
        raise RuntimeError(_SESSION_UNAVAILABLE_MESSAGE)
    return decoded


def _unavailable() -> RuntimeError:
    return RuntimeError(_SESSION_UNAVAILABLE_MESSAGE)


def bootstrap_once(
    enabled: bool,
    provenance_probe: Callable[[], bool],
    loader: Callable[[], dict[str, Any]],
) -> None:
    """Initialize once only for the authenticated Desktop bootstrap process.

    Every first decision is terminal for this engine process. In particular, an
    ordinary unmarked import closes the lazy-fetch loophole by transitioning to
    FAILED without invoking provenance or transport. Hot reloads observe the
    existing READY/FAILED state and never initialize a second session.
    """

    if not isinstance(enabled, bool):
        raise TypeError("Agent policy bootstrap decision must be boolean")
    if not callable(provenance_probe) or not callable(loader):
        raise TypeError("Agent policy bootstrap callbacks must be callable")

    global _payload_bytes, _state
    with _condition:
        while _state == _STATE_LOADING:
            _condition.wait()
        if _state == _STATE_READY:
            return
        if _state in {_STATE_FAILED, _STATE_CLOSED}:
            raise _unavailable()
        if _state != _STATE_EMPTY:
            _state = _STATE_FAILED
            _condition.notify_all()
            raise _unavailable()
        if not enabled:
            _state = _STATE_FAILED
            _condition.notify_all()
            raise _unavailable()
        _state = _STATE_LOADING

    candidate: bytearray | None = None
    try:
        if provenance_probe() is not True:
            raise RuntimeError("Agent policy launcher provenance is unavailable")
        candidate = _encode_private_snapshot(loader())
    except BaseException as exc:
        with _condition:
            if _state != _STATE_CLOSED:
                _state = _STATE_FAILED
            _condition.notify_all()
        _wipe(candidate)
        if isinstance(exc, Exception):
            raise _unavailable() from None
        raise

    with _condition:
        if _state == _STATE_CLOSED:
            _wipe(candidate)
            _condition.notify_all()
            raise _unavailable()
        _payload_bytes = candidate
        _state = _STATE_READY
        _condition.notify_all()


def bootstrap_once_authorized(
    authorization_probe: Callable[[], bool],
    loader: Callable[[], dict[str, Any]],
) -> None:
    """Claim the one-shot session atomically, then load outside its lock.

    ``authorization_probe`` is intentionally evaluated while the process cell
    is still EMPTY.  This keeps consumption of a one-shot launcher marker and
    the EMPTY -> LOADING decision indivisible without holding ``_condition``
    across TLS, Broker I/O, signature verification, or payload encoding.
    READY readers therefore remain responsive while the first Agent is
    authorizing, and concurrent bootstraps still share exactly one terminal
    result.
    """

    if not callable(authorization_probe) or not callable(loader):
        raise TypeError("Agent policy bootstrap callbacks must be callable")

    global _payload_bytes, _state
    with _condition:
        while _state == _STATE_LOADING:
            _condition.wait()
        if _state == _STATE_READY:
            return
        if _state in {_STATE_FAILED, _STATE_CLOSED}:
            raise _unavailable()
        if _state != _STATE_EMPTY:
            _state = _STATE_FAILED
            _condition.notify_all()
            raise _unavailable()
        try:
            enabled = authorization_probe() is True
        except BaseException:
            _state = _STATE_FAILED
            _condition.notify_all()
            raise _unavailable() from None
        if not enabled:
            _state = _STATE_FAILED
            _condition.notify_all()
            raise _unavailable()
        _state = _STATE_LOADING

    candidate: bytearray | None = None
    try:
        candidate = _encode_private_snapshot(loader())
    except BaseException as exc:
        with _condition:
            if _state != _STATE_CLOSED:
                _state = _STATE_FAILED
            _condition.notify_all()
        _wipe(candidate)
        if isinstance(exc, Exception):
            raise _unavailable() from None
        raise

    with _condition:
        if _state == _STATE_CLOSED:
            _wipe(candidate)
            _condition.notify_all()
            raise _unavailable()
        _payload_bytes = candidate
        _state = _STATE_READY
        _condition.notify_all()


def read_ready() -> dict[str, Any]:
    """Return a defensive copy of READY state and never invoke a loader."""

    global _payload_bytes, _state
    with _condition:
        if _state != _STATE_READY or _payload_bytes is None:
            raise _unavailable()
        try:
            return _decode_private_snapshot(_payload_bytes)
        except Exception:
            owned = _payload_bytes
            _payload_bytes = None
            _state = _STATE_FAILED
            _wipe(owned)
            _condition.notify_all()
            raise _unavailable() from None


def _expire_for_process_shutdown() -> None:
    """Expire the in-memory snapshot when the Griptape engine process exits."""

    global _payload_bytes, _state
    with _condition:
        owned = _payload_bytes
        _payload_bytes = None
        _state = _STATE_CLOSED
        _wipe(owned)
        _condition.notify_all()


def _status_for_regression() -> tuple[str, int]:
    """Expose no policy bytes; return only bounded lifecycle diagnostics."""

    with _condition:
        return _state, len(_payload_bytes) if _payload_bytes is not None else 0


atexit.register(_expire_for_process_shutdown)
