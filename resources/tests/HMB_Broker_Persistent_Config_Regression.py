"""Durable Broker settings, subprocess restart and gateway path checks; no HTTP."""
from __future__ import annotations
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import _hmb_broker_config as config

checks = 0
with tempfile.TemporaryDirectory(prefix="hmb-persistent-broker-") as temporary, mock.patch.dict(os.environ, {"APPDATA": temporary}):
    path = config.broker_settings_path()
    assert config.load_broker_base_url() == "https://app.funnyflux.kr/GripTapeServer"
    assert not path.exists(), "Reading the built-in default must not write settings"
    checks += 2
    for raw, expected in (
        ("https://BROKER.example:443/Company/Gateway/", "https://broker.example/Company/Gateway"),
        ("https://[::1]:8443/gateway/", "https://[::1]:8443/gateway"),
        ("", ""), ("https://broker.example/", "https://broker.example"),
        (config.LEGACY_INTERNAL_ORIGIN, config.LEGACY_INTERNAL_ORIGIN),
    ):
        assert config.normalize_broker_base_url(raw, allow_empty=True) == expected
        checks += 1
    for bad in ("https://user:password@broker.example", "https://@broker.example", "http://outside.example",
                "https://broker.example//a", "https://broker.example/a/../b", "https://broker.example/./a",
                "https://broker.example/%2f", "https://broker.example/a?token=x", "https://broker.example/#x",
                "https://broker.example/a\\b", "https://broker.example/\na", "https://broker.example:0/a"):
        try:
            config.normalize_broker_base_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unsafe Broker endpoint accepted: {bad}")
        checks += 1
    endpoint = "https://broker.example/Company/Gateway"
    config.save_broker_base_url(endpoint + "/")
    assert config.load_broker_base_url() == endpoint
    assert json.loads(path.read_text())["base_url"] == endpoint
    assert set(json.loads(path.read_text())) == {"schema", "version", "base_url"}
    checks += 3
    child = subprocess.run([sys.executable, "-c",
        "import _hmb_broker_config as c; print(c.load_broker_base_url())"], cwd=ROOT,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, timeout=15, check=True)
    assert child.stdout.strip() == endpoint, "A new process lost the saved address"
    checks += 1
    with mock.patch.object(config, "DEFAULT_BROKER_BASE_URL", "https://new-shipped-default.example"):
        assert config.load_broker_base_url() == endpoint, "An update overwrote the saved address"
    before = path.read_bytes()
    with mock.patch.object(config.os, "replace", side_effect=OSError("test disk failure")):
        try:
            config.save_broker_base_url("https://other.example")
        except OSError:
            pass
        else:
            raise AssertionError("A failed atomic save was reported as successful")
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))
    checks += 3
    for path_part in ("/api/me", "/api/v1/jobs/job%3Aone/refresh", "/api/reviews?cursor=abc%2Bdef%3D"):
        assert config.join_broker_url(endpoint, path_part) == endpoint + path_part
        checks += 1
    assert config.join_broker_url(endpoint, "/Company/Gateway/api/me", allow_prefixed=True) == endpoint + "/api/me"
    assert config.join_broker_url("https://broker.example/api", "/api/me") == "https://broker.example/api/api/me"
    checks += 2
    for bad in ("//evil.example/api", "https://evil.example/api", "/api/../outside", "/api/%2e%2e/x",
                "/api/%2foutside", "/api/%255c", "/api\\x"):
        try:
            config.join_broker_url(endpoint, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe gateway path accepted")
        checks += 1
    config.save_broker_base_url("")
    assert config.load_broker_base_url() == "", "An explicit clear silently restored the default"
    importlib.reload(config)
    assert config.load_broker_base_url() == ""
    checks += 2
    path.write_text("not json", encoding="utf-8")
    try:
        config.load_broker_base_url()
    except ValueError:
        pass
    else:
        raise AssertionError("Corrupt settings silently redirected the Broker")
    config.save_broker_base_url(endpoint)
    assert config.load_broker_base_url() == endpoint
    checks += 2
print(f"HMB persistent Broker configuration: PASS ({checks} checks; subprocess restart, durable override, no HTTP)")
