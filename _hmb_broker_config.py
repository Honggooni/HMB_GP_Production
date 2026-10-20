"""Durable, user-wide Broker configuration and strict gateway URL handling.

This file stores an address only. Credentials and original task endpoints keep
their separate storage. Merely reading settings never creates files or requests.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import threading
from typing import Callable
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import uuid4
import weakref

DEFAULT_BROKER_BASE_URL = "https://app.funnyflux.kr/GripTapeServer"
LEGACY_INTERNAL_ORIGIN = "http://192.168.203.245:8080"
_LOCK = threading.RLock()
_LISTENERS: list[weakref.WeakMethod] = []
_MAX_BYTES = 8192


def normalize_broker_base_url(value: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("FN AI Broker server URL is invalid.")
    value = value.strip()
    if not value and allow_empty:
        return ""
    if not value or len(value) > 2048 or any(c.isspace() for c in value) or any(c in value for c in "\\%?#"):
        raise ValueError("Enter a valid HTTPS Broker address in Settings.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname or ""
    except ValueError as exc:
        raise ValueError("FN AI Broker server URL is invalid.") from exc
    if parsed.scheme not in {"http", "https"} or not host or "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ValueError("FN AI Broker address must not contain credentials.")
    if port == 0 or parsed.netloc.endswith(":"):
        raise ValueError("FN AI Broker server port is invalid.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        host = host.lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host) or any(
            not part or len(part) > 63 or part.startswith("-") or part.endswith("-") for part in host.split(".")
        ) or re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1]):
            raise ValueError("FN AI Broker server host is invalid.")
    else:
        host = f"[{address.compressed}]" if address.version == 6 else str(address)
    path = parsed.path
    if "//" in path or any(part in {".", ".."} for part in path.split("/")) or (path and not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/?", path)):
        raise ValueError("FN AI Broker gateway path is invalid.")
    authority = host + (f":{port}" if port and port != (443 if parsed.scheme == "https" else 80) else "")
    canonical = urlunsplit((parsed.scheme, authority, path.rstrip("/"), "", ""))
    if parsed.scheme != "https" and canonical != LEGACY_INTERNAL_ORIGIN:
        raise ValueError("Other FN AI Broker servers require HTTPS.")
    return canonical


def join_broker_url(base: str, path: str, *, allow_prefixed: bool = False) -> str:
    """Attach a backend absolute path while retaining the approved gateway."""
    base = normalize_broker_base_url(base)
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or any(c in path for c in "\\#") or any(ord(c) <= 32 for c in path):
        raise ValueError("FN AI Broker request path is invalid.")
    parsed = urlsplit(path)
    decoded = unquote(parsed.path, errors="strict")
    if (parsed.scheme or parsed.netloc or "//" in decoded or "\\" in decoded or "%" in decoded
            or any(ord(c) < 32 for c in decoded) or any(p in {".", ".."} for p in decoded.split("/"))
            or re.search(r"%(?:2f|5c)", parsed.path, re.IGNORECASE)):
        raise ValueError("FN AI Broker request path is invalid.")
    prefix = urlsplit(base).path
    if allow_prefixed and prefix and (parsed.path == prefix or parsed.path.startswith(prefix + "/")):
        origin = base[:-len(prefix)]
        return origin + path
    return base + path


def broker_settings_path() -> Path:
    root = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    return root / "FNAIBroker" / "connection.json"


def load_broker_base_url() -> str:
    path = broker_settings_path()
    with _LOCK:
        try:
            with path.open("rb") as stream:
                raw = stream.read(_MAX_BYTES + 1)
        except FileNotFoundError:
            return DEFAULT_BROKER_BASE_URL
        if len(raw) > _MAX_BYTES:
            raise ValueError("Saved Broker settings are invalid. Save the address again in Settings.")
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("schema") != "hmb-broker-connection" or value.get("version") != 1:
                raise ValueError("invalid schema")
            return normalize_broker_base_url(value["base_url"], allow_empty=True)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ValueError("Saved Broker settings are invalid. Save the address again in Settings.") from exc


def subscribe_broker_changes(callback: Callable[[str], None]) -> None:
    with _LOCK:
        _LISTENERS.append(weakref.WeakMethod(callback))


def save_broker_base_url(value: str) -> str:
    canonical = normalize_broker_base_url(value, allow_empty=True)
    with _LOCK:
        path = broker_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = {"schema": "hmb-broker-connection", "version": 1, "base_url": canonical}
        try:
            with temporary.open("xb") as stream:
                stream.write((json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        listeners = [(reference, reference()) for reference in _LISTENERS]
        _LISTENERS[:] = [reference for reference, callback in listeners if callback is not None]
    for _, callback in listeners:
        if callback is not None:
            try:
                callback(canonical)
            except Exception:
                # A detached/closed editor cannot undo a durable user setting.
                continue
    return canonical
