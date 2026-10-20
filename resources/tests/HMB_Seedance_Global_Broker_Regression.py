"""Five Generator global settings, frozen Tasks/auth, gateway request transport."""
from __future__ import annotations
import importlib.util
import ast
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock
from types import SimpleNamespace
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs
install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location("seedance_global_broker", ROOT / "HMBSeedanceGeneration.py")
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
config = target._broker_config
checks = 0

class Response:
    status = 200
    def __init__(self, url, body):
        self.url, self.body = url, json.dumps(body).encode()
    def geturl(self): return self.url
    def read(self, _limit): return self.body
    def __enter__(self): return self
    def __exit__(self, *_args): pass

class Opener:
    def __init__(self): self.requests = []
    def open(self, request, **_kwargs):
        self.requests.append(request)
        return Response(request.full_url, {"ok": True})

with tempfile.TemporaryDirectory(prefix="hmb-global-broker-" ) as temporary, mock.patch.dict(os.environ,
        {"APPDATA": temporary, "LOCALAPPDATA": temporary}), mock.patch.object(target, "_broker_device_login", side_effect=AssertionError("Unexpected login")):
    with mock.patch.object(target.urllib.request.OpenerDirector, "open", side_effect=AssertionError("Live HTTP forbidden")):
        nodes = [target.HMBSeedanceGeneration(name=f"Generator {i}") for i in range(1, 6)]
        assert all(n._selected_broker_server_url() == config.DEFAULT_BROKER_BASE_URL for n in nodes)
        assert not config.broker_settings_path().exists()
        checks += 2
        server_a = "https://broker.example/Company/Gateway"
        server_b = "https://other.example/OtherGateway"
        nodes[0].set_parameter_value("broker_server_url", server_a + "/")
        assert all(n._selected_broker_server_url() == server_a for n in nodes)
        assert all(n.get_parameter_value("broker_server_url") == server_a for n in nodes)
        checks += 2
        saved = config.broker_settings_path().read_bytes()
        reopened = target.HMBSeedanceGeneration(name="Old workflow reopened")
        for old in (server_b, "", config.LEGACY_INTERNAL_ORIGIN):
            reopened.set_parameter_value("broker_server_url", old, initial_setup=True)
            assert config.broker_settings_path().read_bytes() == saved
            assert reopened.get_parameter_value("broker_server_url") == server_a
            assert reopened._selected_broker_server_url() == server_a
            checks += 3
        checkpoint = nodes[1]._set_generation_recovery_checkpoint(stage="accepted", task_id="job-pinned",
            task_identity="broker_task", status="running")
        assert checkpoint["broker_server_url"] == server_a
        checks += 1
        nodes[4]._generation_run_active.set()
        try:
            nodes[0].set_parameter_value("broker_server_url", server_b)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed the common endpoint while another Generator was active")
        assert config.broker_settings_path().read_bytes() == saved
        nodes[4]._generation_run_active.clear()
        checks += 2
        nodes[0].set_parameter_value("broker_server_url", server_b)
        assert all(n._selected_broker_server_url() == server_b for n in nodes)
        assert nodes[1]._broker_server_for_task("job-pinned") == server_a
        assert nodes[1]._generation_recovery_state()["task_id"] == "job-pinned"
        checks += 3
        opener = Opener()
        bridge = target._HMBAIBrokerBridge(opener=opener, server_url=server_a)
        with mock.patch.object(target, "_broker_load_token", return_value="test-token") as token:
            bridge._request_json("GET", "/api/me", payload=None, timeout=1)
            assert opener.requests[-1].full_url == server_a + "/api/me"
            token.assert_called_once_with(server_url=server_a)
        checks += 2
        media_path = "/api/assets/" + "a" * 43
        result = target.HMBSeedanceGeneration._broker_result_url(media_path, server_url=server_a)
        assert result == server_a + media_path
        assert bridge.is_trusted_broker_url(result)
        assert not bridge.is_trusted_broker_url("https://broker.example" + media_path)
        assert not bridge.is_trusted_broker_url("https://broker.example/Company/Other" + media_path)
        collision_base = "https://broker.example/api"
        collision_bridge = target._HMBAIBrokerBridge(opener=opener, server_url=collision_base)
        collision_result = target.HMBSeedanceGeneration._broker_result_url(media_path, server_url=collision_base)
        assert collision_result == collision_base + media_path
        assert collision_bridge.is_trusted_broker_url(collision_result)
        assert target.HMBSeedanceGeneration._broker_result_url("/api" + media_path, server_url=collision_base) == collision_result
        checks += 7
        bridge._clear_access_token = mock.Mock()
        class Unauthorized:
            def open(self, request, **_kwargs):
                raise urllib.error.HTTPError(request.full_url, 401, "test", {}, io.BytesIO(b"{}"))
        bridge._opener = Unauthorized()
        with mock.patch.object(target, "_broker_load_token", return_value="test-token"):
            try: bridge._request_json("GET", "/api/me", payload=None, timeout=1)
            except target._BrokerAuthenticationError: pass
            else: raise AssertionError("401 accepted")
        bridge._clear_access_token.assert_called_once()
        checks += 1
        frozen = object.__new__(target._HMBWebRerenderExecution)
        frozen._web_params = {"_hmb_broker_server_url": server_a}
        assert frozen._selected_broker_server_url() == server_a
        checks += 1
        nodes[0].set_parameter_value("broker_server_url", "")
        assert all(n.get_parameter_value("broker_server_url") == "" for n in nodes)
        try: nodes[0]._selected_broker_server_url()
        except target._BrokerUnavailableError: pass
        else: raise AssertionError("Cleared settings silently selected a default server")
        assert nodes[1]._broker_server_for_task("job-pinned") == server_a
        checks += 3
        pinned = nodes[1]
        pinned._runtime_node_is_live = lambda **_kwargs: True
        pinned._force_save_generation_recovery_checkpoint = mock.AsyncMock(return_value=True)
        pinned._set_status_results = mock.Mock()
        pinned.status_component = SimpleNamespace(clear_execution_status=lambda **_kwargs: None)
        retrieval = SimpleNamespace(refresh_job=lambda *_args, **_kwargs: {"status": "failed", "job_id": "job-pinned"})
        pinned._ensure_broker_connected = mock.AsyncMock(return_value=retrieval)
        asyncio.run(pinned._refresh_async())
        pinned._ensure_broker_connected.assert_awaited_once_with(server_url=server_a)
        assert pinned._generation_recovery_state()["terminal"] is True
        checks += 2
        tree = ast.parse((ROOT / "HMBSeedanceGeneration.py").read_text(encoding="utf-8-sig"))
        node_class = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "HMBSeedanceGeneration")
        for name in ("_refresh_async", "_process_generation_impl"):
            method = next(item for item in node_class.body if isinstance(item, ast.AsyncFunctionDef) and item.name == name)
            calls = [item for item in ast.walk(method) if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute) and item.func.attr == "_ensure_broker_connected"]
            assert calls and all(any(k.arg == "server_url" for k in call.keywords) for call in calls), "A pinned retrieval depended on the cleared common address"
            checks += 1
print(f"HMB global Broker Generators: PASS ({checks} checks; five nodes, task/auth pin, no network/render)")
