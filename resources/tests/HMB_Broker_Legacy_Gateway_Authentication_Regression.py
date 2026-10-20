"""Offline existing-user authentication migration to the official HTTPS gateway.

All credentials, DPAPI blobs and HTTP responses below are isolated fixtures.
No device authorization, media upload, render or real HTTP request is permitted.
"""
from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs

install_clean_ci_griptape_stubs()
_isolated = tempfile.TemporaryDirectory(prefix="hmb-gateway-auth-import-")
atexit.register(_isolated.cleanup)
_environment = mock.patch.dict(os.environ, {
    "APPDATA": str(Path(_isolated.name) / "roaming"),
    "LOCALAPPDATA": str(Path(_isolated.name) / "local"),
})
_environment.start()
atexit.register(_environment.stop)
spec = importlib.util.spec_from_file_location(
    "hmb_legacy_gateway_auth_regression", ROOT / "HMBSeedanceGeneration.py"
)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)

OFFICIAL = "https://app.funnyflux.kr/GripTapeServer"
CUSTOM = "https://studio.fixture.invalid/GripTapeServer"
LEGACY = target.AI_BROKER_INTERNAL_ORIGIN
LEGACY_TOKEN = "fixture-only-original-login-never-live"
SCOPED_TOKEN = "fixture-only-scoped-login-never-live"
IDENTITY = {"user": {"id": "fixture-owner", "display_name": "Fixture Owner"}}
checks = 0


def protected(value: bytes, *, protect: bool) -> bytes:
    prefix = b"fixture-protected:"
    if protect:
        return prefix + value
    if not value.startswith(prefix):
        raise RuntimeError("Invalid fixture DPAPI blob")
    return value[len(prefix):]


def load_path(path: Path) -> str:
    try:
        return protected(Path(path).read_bytes(), protect=False).decode("ascii")
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise RuntimeError("Fixture login unavailable") from exc


def load_legacy() -> str:
    root = Path(os.environ["APPDATA"])
    for path in (root / "FNAIBroker" / "access_token_v2.dpapi",
                 root / "CompanyAIBroker" / "access_token_v2.dpapi"):
        if path.is_file():
            return load_path(path)
    raise RuntimeError("Fixture legacy login unavailable")


def fingerprint(path: Path):
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns


class Response:
    def __init__(self, url: str, body=IDENTITY, *, status=200, raw=None):
        self.status = status
        self.url = url
        self.stream = io.BytesIO(json.dumps(body).encode("utf-8") if raw is None else raw)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def geturl(self):
        return self.url

    def read(self, count=-1):
        return self.stream.read(count)


class FixtureOpener:
    def __init__(self, *, outcome="ok", expected_token=LEGACY_TOKEN,
                 response_url=None, body=IDENTITY, pause=0):
        self.outcome = outcome
        self.expected_token = expected_token
        self.response_url = response_url
        self.body = body
        self.pause = pause
        self.requests = []
        self.lock = threading.Lock()

    def open(self, request, timeout):
        with self.lock:
            self.requests.append(request)
        assert request.get_method() == "GET", "Migration attempted a mutation"
        assert request.full_url == OFFICIAL + "/api/me", "Credential crossed the official gateway boundary"
        assert request.data is None, "Migration must not submit a body"
        assert request.get_header("Authorization") == "Bearer " + self.expected_token
        assert 0 < timeout <= 30, "Authentication must have a bounded request deadline"
        if self.pause:
            time.sleep(self.pause)
        if isinstance(self.outcome, int):
            raise target.urllib.error.HTTPError(
                request.full_url, self.outcome, "fixture rejection", {}, io.BytesIO(b"{}")
            )
        if self.outcome == "timeout":
            raise TimeoutError("fixture authentication timeout")
        if self.outcome == "network":
            raise target.urllib.error.URLError("fixture disconnected")
        if self.outcome == "invalid-json":
            return Response(request.full_url, raw=b"not-json")
        if self.outcome == "oversized":
            return Response(request.full_url, raw=b" " * (target.AI_BROKER_MAX_JSON_BYTES + 1))
        return Response(self.response_url or request.full_url, self.body)


@contextmanager
def fixture(*, opener=None, legacy=True, old_directory=False, scoped=False):
    with tempfile.TemporaryDirectory(prefix="hmb-gateway-auth-") as temporary, ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {"APPDATA": temporary, "LOCALAPPDATA": temporary}))
        stack.enter_context(mock.patch.object(target, "_broker_dpapi", side_effect=protected))
        legacy_loader = stack.enter_context(mock.patch.object(
            target, "_broker_load_bearer_token_readonly", side_effect=load_legacy
        ))
        stack.enter_context(mock.patch.object(target, "_broker_load_bearer_token_from_path_readonly", side_effect=load_path))
        stack.enter_context(mock.patch.object(target, "_broker_device_login", side_effect=AssertionError("Device login is forbidden")))
        # Never permit a forgotten/injected opener to reach the network.
        stack.enter_context(mock.patch.object(target.urllib.request.OpenerDirector, "open", side_effect=AssertionError("Real HTTP is forbidden")))
        stack.enter_context(mock.patch.object(target, "_broker_log_transport_error"))
        if opener is not None:
            stack.enter_context(mock.patch.object(target, "_broker_build_opener", return_value=opener))
        root = Path(temporary)
        legacy_path = root / ("CompanyAIBroker" if old_directory else "FNAIBroker") / "access_token_v2.dpapi"
        if legacy:
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_bytes(protected(LEGACY_TOKEN.encode("ascii"), protect=True))
        scoped_path = target._broker_token_path(server_url=OFFICIAL)
        if scoped:
            scoped_path.write_bytes(protected(SCOPED_TOKEN.encode("ascii"), protect=True))
        yield legacy_path, scoped_path, legacy_loader


# The real configured opener itself must reject redirects and machine proxies.
real_opener = target._broker_build_opener()
assert any(isinstance(handler, target._BrokerNoRedirectHandler) for handler in real_opener.handlers)
for handler in real_opener.handlers:
    if isinstance(handler, target.urllib.request.ProxyHandler):
        assert handler.proxies == {}
checks += 1

# A verified same-service migration persists only to the official scoped file.
for old_directory in (False, True):
    opener = FixtureOpener()
    with fixture(opener=opener, old_directory=old_directory) as (legacy_path, scoped_path, _):
        before = fingerprint(legacy_path)
        with mock.patch.object(target, "_broker_save_token", wraps=target._broker_save_token) as save:
            assert target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL) == LEGACY_TOKEN
            assert len(opener.requests) == 1
            save.assert_called_once_with(LEGACY_TOKEN, server_url=OFFICIAL, only_if_missing=True)
        assert load_path(scoped_path) == LEGACY_TOKEN
        assert fingerprint(legacy_path) == before, "Migration changed the existing login"
        assert not list(scoped_path.parent.glob("*.tmp"))
        assert not target._broker_config.broker_settings_path().exists(), "Authentication changed the selected server"
        checks += 1

# Existing per-gateway authentication always wins; no legacy credential is read.
native = FixtureOpener(expected_token=SCOPED_TOKEN)
with fixture(opener=FixtureOpener(), scoped=True) as (legacy_path, scoped_path, legacy_loader):
    before = fingerprint(legacy_path), fingerprint(scoped_path)
    with mock.patch.object(target, "_broker_migrate_legacy_gateway_token", side_effect=AssertionError("Scoped login must win")):
        state = target._HMBAIBrokerBridge(opener=native, server_url=OFFICIAL).account_snapshot(connect=False)
    assert state.connected and state.state == "connected" and state.account == "Fixture Owner"
    assert len(native.requests) == 1
    legacy_loader.assert_not_called()
    assert (fingerprint(legacy_path), fingerprint(scoped_path)) == before
    checks += 1

# Native account flow consumes the migrated credential, without device login.
migration, native = FixtureOpener(), FixtureOpener()
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)
    state = target._HMBAIBrokerBridge(opener=native, server_url=OFFICIAL).account_snapshot(connect=False)
    assert state.connected and state.state == "connected"
    assert len(migration.requests) == 1 and len(native.requests) == 1
    assert fingerprint(legacy_path) == before and load_path(scoped_path) == LEGACY_TOKEN
    checks += 1

# Five generators may race, but only one legacy credential verification/save runs.
migration = FixtureOpener(pause=0.03)
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)
    gate = threading.Barrier(5)

    def concurrent_migration(_):
        gate.wait(timeout=5)
        return target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)

    with mock.patch.object(target, "_broker_save_token", wraps=target._broker_save_token) as save:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(concurrent_migration, range(5)))
        assert results == [LEGACY_TOKEN] * 5
        assert len(migration.requests) == 1 and save.call_count == 1
    assert fingerprint(legacy_path) == before and load_path(scoped_path) == LEGACY_TOKEN
    checks += 1

# Five independent native generators verify once and keep independent snapshots.
migration, native = FixtureOpener(pause=0.03), FixtureOpener()
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)
    gate = threading.Barrier(5)

    def concurrent_snapshot(_):
        gate.wait(timeout=5)
        return target._HMBAIBrokerBridge(opener=native, server_url=OFFICIAL).account_snapshot(connect=False)

    with mock.patch.object(target, "_broker_save_token", wraps=target._broker_save_token) as save:
        with ThreadPoolExecutor(max_workers=5) as pool:
            states = list(pool.map(concurrent_snapshot, range(5)))
        assert all(state.connected and state.account == "Fixture Owner" for state in states)
        assert len(migration.requests) == 1 and save.call_count == 1
    assert len(native.requests) == 5
    assert fingerprint(legacy_path) == before and load_path(scoped_path) == LEGACY_TOKEN
    checks += 1

# Explicit sign-out/revocation is durable: a restart must not borrow the LAN login.
migration = FixtureOpener()
with fixture(opener=migration, scoped=True) as (legacy_path, scoped_path, legacy_loader):
    before = fingerprint(legacy_path)
    target._broker_clear_token(server_url=OFFICIAL)
    marker = target._broker_legacy_migration_block_path(server_url=OFFICIAL)
    assert marker.is_file() and not scoped_path.exists()
    assert LEGACY_TOKEN.encode("ascii") not in marker.read_bytes()
    assert SCOPED_TOKEN.encode("ascii") not in marker.read_bytes()
    legacy_loader.reset_mock()
    try:
        target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)
    except target._BrokerAuthenticationError:
        pass
    else:
        raise AssertionError("Explicit gateway logout silently reused the legacy login")
    state = target._HMBAIBrokerBridge(opener=FixtureOpener(), server_url=OFFICIAL).account_snapshot(connect=False)
    assert not state.connected and state.state == "login_required"
    legacy_loader.assert_not_called()
    assert migration.requests == [] and fingerprint(legacy_path) == before
    # A later real device authorization can establish the scoped login normally.
    target._broker_save_token(SCOPED_TOKEN, server_url=OFFICIAL)
    assert not marker.exists() and load_path(scoped_path) == SCOPED_TOKEN
    assert fingerprint(legacy_path) == before
    checks += 1

# A native 401 must not become an account change on the next account refresh.
native = FixtureOpener(outcome=401, expected_token=SCOPED_TOKEN)
migration = FixtureOpener()
with fixture(opener=migration, scoped=True) as (legacy_path, scoped_path, legacy_loader):
    before = fingerprint(legacy_path)
    first = target._HMBAIBrokerBridge(opener=native, server_url=OFFICIAL).account_snapshot(connect=False)
    assert not first.connected and first.state == "login_required"
    assert len(native.requests) == 1 and not scoped_path.exists()
    second = target._HMBAIBrokerBridge(opener=FixtureOpener(), server_url=OFFICIAL).account_snapshot(connect=False)
    assert not second.connected and second.state == "login_required"
    legacy_loader.assert_not_called()
    assert migration.requests == [] and fingerprint(legacy_path) == before
    checks += 1

# No other host, path or insecure HTTP endpoint may borrow the old login.
for destination in (CUSTOM, "https://app.funnyflux.kr/OtherService",
                    "https://app.funnyflux.kr/GripTapeServerOther",
                    "https://app.funnyflux.kr.evil.invalid/GripTapeServer",
                    "http://app.funnyflux.kr/GripTapeServer"):
    migration = FixtureOpener()
    with fixture(opener=migration) as (legacy_path, scoped_path, legacy_loader):
        before = fingerprint(legacy_path)
        try:
            target._broker_migrate_legacy_gateway_token(server_url=destination)
        except (target._BrokerError, ValueError):
            pass
        else:
            raise AssertionError("Unrelated service borrowed the historical login")
        assert migration.requests == [] and not scoped_path.exists()
        assert fingerprint(legacy_path) == before
        legacy_loader.assert_not_called()
        checks += 1

# Refusal/disconnect never copies, deletes or invalidates the old LAN login.
for outcome in (401, 403, 429, 500, 502, 503, "timeout", "network", "invalid-json", "oversized"):
    migration = FixtureOpener(outcome=outcome)
    with fixture(opener=migration) as (legacy_path, scoped_path, _):
        before = fingerprint(legacy_path)
        try:
            state = target._HMBAIBrokerBridge(opener=FixtureOpener(), server_url=OFFICIAL).account_snapshot(connect=False)
        except target._BrokerError as exc:
            assert LEGACY_TOKEN not in str(exc), "Authentication diagnostic exposed a credential"
        else:
            assert not state.connected and state.state != "connected"
        assert len(migration.requests) == 1
        assert not scoped_path.exists() and fingerprint(legacy_path) == before
        checks += 1

# 200 alone is insufficient: a useful account identity and exact response URL are required.
for body, response_url in (({}, None), ([], None), ({"user": {}}, None),
                           (IDENTITY, CUSTOM + "/api/me"),
                           (IDENTITY, OFFICIAL + "/login"),
                           (IDENTITY, "http://app.funnyflux.kr/GripTapeServer/api/me")):
    migration = FixtureOpener(body=body, response_url=response_url)
    with fixture(opener=migration) as (legacy_path, scoped_path, _):
        before = fingerprint(legacy_path)
        try:
            target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)
        except target._BrokerError:
            pass
        else:
            raise AssertionError("Invalid authentication response was accepted")
        assert len(migration.requests) == 1 and not scoped_path.exists()
        assert fingerprint(legacy_path) == before
        checks += 1

# Explicit approval or disabled-account refusals must not create scoped logins.
for refusal in ({"enabled": False}, {"approval_status": "pending"},
                {"approval_status": "rejected"}, {"approval_status": "blocked"}):
    for body in (dict(IDENTITY, **refusal), {"user": dict(IDENTITY["user"], **refusal)}):
        migration = FixtureOpener(body=body)
        with fixture(opener=migration) as (legacy_path, scoped_path, _):
            before = fingerprint(legacy_path)
            try:
                target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)
            except target._BrokerError:
                pass
            else:
                raise AssertionError("An unapproved or disabled account was accepted")
            assert len(migration.requests) == 1 and not scoped_path.exists()
            assert fingerprint(legacy_path) == before
            checks += 1

# A failed atomic publication must not report a successful/connected migration.
migration = FixtureOpener()
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)
    operation = "rename" if os.name == "nt" else "link"
    with mock.patch.object(target.os, operation, side_effect=OSError("fixture disk write failure")):
        try:
            target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)
        except target._BrokerUnavailableError:
            pass
        else:
            raise AssertionError("Failed credential persistence was reported as connected")
    assert len(migration.requests) == 1 and not scoped_path.exists()
    assert fingerprint(legacy_path) == before and not list(scoped_path.parent.glob("*.tmp"))
    checks += 1

# Another process may publish its newer scoped login during our final encryption.
migration = FixtureOpener()
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)

    def publish_newer_scoped(value, *, protect):
        if protect:
            scoped_path.write_bytes(protected(SCOPED_TOKEN.encode("ascii"), protect=True))
        return protected(value, protect=protect)

    with mock.patch.object(target, "_broker_dpapi", side_effect=publish_newer_scoped):
        assert target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL) == SCOPED_TOKEN
    assert load_path(scoped_path) == SCOPED_TOKEN, "Migration replaced a newer scoped login"
    assert fingerprint(legacy_path) == before
    assert not list(scoped_path.parent.glob("*.tmp"))
    checks += 1

# A logout racing final encryption must remain the final durable state.
migration = FixtureOpener()
with fixture(opener=migration) as (legacy_path, scoped_path, _):
    before = fingerprint(legacy_path)
    encrypting, release, clear_started = threading.Event(), threading.Event(), threading.Event()

    def pause_encryption(value, *, protect):
        if protect:
            encrypting.set()
            assert release.wait(timeout=5), "Migration encryption test stalled"
        return protected(value, protect=protect)

    def clear_during_encryption():
        clear_started.set()
        target._broker_clear_token(server_url=OFFICIAL)

    with mock.patch.object(target, "_broker_dpapi", side_effect=pause_encryption):
        with ThreadPoolExecutor(max_workers=2) as pool:
            migrate = pool.submit(target._broker_migrate_legacy_gateway_token, server_url=OFFICIAL)
            assert encrypting.wait(timeout=5), "Migration never reached encryption"
            clear = pool.submit(clear_during_encryption)
            assert clear_started.wait(timeout=5), "Concurrent logout never started"
            time.sleep(0.03)
            release.set()
            try:
                migrate.result(timeout=5)
            except target._BrokerAuthenticationError:
                pass
            clear.result(timeout=5)
    assert not scoped_path.exists(), "Migration undid the explicit concurrent logout"
    assert target._broker_legacy_migration_block_path(OFFICIAL).is_file()
    assert fingerprint(legacy_path) == before
    checks += 1

# An HTTP redirect must remain a refusal; no target is followed or persisted.
for status in (301, 302, 307, 308):
    migration = FixtureOpener(outcome=status)
    with fixture(opener=migration) as (legacy_path, scoped_path, _):
        before = fingerprint(legacy_path)
        try:
            target._broker_migrate_legacy_gateway_token(server_url=OFFICIAL)
        except target._BrokerError:
            pass
        else:
            raise AssertionError("Redirected authentication was accepted")
        assert len(migration.requests) == 1 and not scoped_path.exists()
        assert fingerprint(legacy_path) == before
        checks += 1

# Missing historical login cannot manufacture a connected state or request HTTP.
migration = FixtureOpener()
with fixture(opener=migration, legacy=False) as (_, scoped_path, _):
    state = target._HMBAIBrokerBridge(opener=FixtureOpener(), server_url=OFFICIAL).account_snapshot(connect=False)
    assert not state.connected and state.state == "login_required"
    assert migration.requests == [] and not scoped_path.exists()
    checks += 1

print(f"HMB legacy gateway authentication: PASS ({checks} checks; offline, five-way migration, no render or device login)")
