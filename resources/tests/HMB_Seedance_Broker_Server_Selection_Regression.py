"""Offline regression for persistent shared FN AI Broker gateway selection.

The test uses clean-CI Griptape stubs, temporary token storage and a fake
opener. It never contacts a Broker, starts device authorization or creates a
billable render.
"""

from __future__ import annotations

import importlib.util
import atexit
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()
_isolated = tempfile.TemporaryDirectory(prefix="hmb-broker-shared-regression-")
atexit.register(_isolated.cleanup)
_isolated_environment = mock.patch.dict(os.environ, {
    "APPDATA": str(Path(_isolated.name) / "roaming"),
    "LOCALAPPDATA": str(Path(_isolated.name) / "local"),
})
_isolated_environment.start()
atexit.register(_isolated_environment.stop)
spec = importlib.util.spec_from_file_location(
    "hmb_seedance_broker_server_selection", ROOT / "HMBSeedanceGeneration.py"
)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


DEFAULT_URL = target._broker_config.DEFAULT_BROKER_BASE_URL
LEGACY_URL = target.AI_BROKER_INTERNAL_ORIGIN
SERVER_A = "https://broker-a.example:8443/StudioA"
SERVER_B = "https://broker-a.example:8443/StudioB"


def expect_invalid_server(value: str) -> None:
    try:
        target._broker_validated_server_url(value)
    except target._BrokerUnavailableError as exc:
        assert "secret" not in str(exc).lower(), (
            "URL validation must not echo credentials into the UI or logs."
        )
    else:
        raise AssertionError(f"Invalid Broker origin was accepted: {value!r}")


assert target._broker_validated_server_url() == DEFAULT_URL
assert target._broker_validated_server_url(SERVER_A) == SERVER_A
assert target._broker_validated_server_url(SERVER_B) == SERVER_B
assert target._broker_validated_server_url(SERVER_A + "/") == SERVER_A
assert target._broker_validated_server_url(LEGACY_URL) == LEGACY_URL
assert not target._broker_config.broker_settings_path().exists(), "Reading initial settings must not write a config."
for invalid in (
    "http://broker-a.example:8443",  # Only the installed LAN origin has an HTTP exception.
    "http://192.168.203.246:8080",
    "ftp://broker-a.example",
    "https://user:secret@broker-a.example",
    "https://broker-a.example/a/../path",
    "https://broker-a.example/a//path",
    "https://broker-a.example/a%2fpath",
    "https://@broker-a.example/path",
    "https://broker-a.example/?token=canary",
    "https://broker-a.example/#fragment",
    "https://broker-a.example:invalid",
    "https://broker-a.example:99999",
    "https://broker-a.example\nX-Injected: yes",
):
    expect_invalid_server(invalid)


def fake_dpapi(data: bytes, *, protect: bool) -> bytes:
    if protect:
        return b"test-protected:" + data
    prefix = b"test-protected:"
    if not data.startswith(prefix):
        raise RuntimeError("unexpected test-only token blob")
    return data[len(prefix):]


def fake_bounded_token_load(path: Path) -> str:
    """Read only the test-created blob, without calling Windows DPAPI."""

    return fake_dpapi(Path(path).read_bytes(), protect=False).decode("ascii")


class UnauthorizedOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout: float):
        assert timeout > 0
        self.requests.append(request)
        raise target.urllib.error.HTTPError(
            request.full_url, 401, "unauthorized", {}, io.BytesIO(b"{}")
        )


with tempfile.TemporaryDirectory(prefix="hmb-broker-origin-regression-") as temporary:
    with mock.patch.dict(os.environ, {"APPDATA": temporary, "LOCALAPPDATA": temporary}):
        default_path = target._broker_token_path(server_url=DEFAULT_URL)
        legacy_path = target._broker_token_path(server_url=LEGACY_URL)
        path_a = target._broker_token_path(server_url=SERVER_A)
        path_b = target._broker_token_path(server_url=SERVER_B)
        assert default_path != path_a != path_b
        assert path_a != path_b
        assert legacy_path.name == "access_token_v2.dpapi", (
            "The installed Broker and Agent must retain their legacy token path."
        )
        assert default_path != legacy_path
        assert path_a != path_b, "Separate gateways on the same host require separate tokens."

        with (
            mock.patch.object(target, "_broker_dpapi", side_effect=fake_dpapi),
            mock.patch.object(
                target, "_broker_load_bearer_token_from_path_readonly",
                side_effect=fake_bounded_token_load,
            ),
        ):
            target._broker_save_token("alternate-a-token", server_url=SERVER_A)
            target._broker_save_token("alternate-b-token", server_url=SERVER_B)
            assert target._broker_load_token(server_url=SERVER_A) == "alternate-a-token"
            assert target._broker_load_token(server_url=SERVER_B) == "alternate-b-token"

            # The pre-existing default/Agent credential is a separate file.
            default_path.write_bytes(b"existing-default-token-must-survive")
            legacy_path.write_bytes(b"existing-lan-token-must-survive")
            # A durable common override must not inherit a sibling gateway or
            # historical LAN credential. No node hydration may change it.
            with (
                mock.patch.object(
                    target, "_broker_load_bearer_token_readonly",
                    side_effect=AssertionError(
                        "The shared LAN token was read for another origin"
                    ),
                ),
            ):
                target._broker_config.save_broker_base_url(SERVER_B)
                assert target._broker_validated_server_url() == SERVER_B
                assert target._broker_token_path(server_url=SERVER_B) == path_b
                assert target._broker_load_token(server_url=SERVER_B) == "alternate-b-token"
                assert default_path.read_bytes() == b"existing-default-token-must-survive"
                assert legacy_path.read_bytes() == b"existing-lan-token-must-survive"

                with mock.patch.dict(os.environ, {"HMB_AI_BROKER_URL": SERVER_B}):
                    legacy_without_origin = target._seedance_recovery_value({
                        "task_id": "job-legacy-unknown-origin",
                        "task_identity": "broker_task",
                        "stage": "accepted",
                        "status": "running",
                    })
                    assert legacy_without_origin["broker_server_url"] == "", (
                        "A legacy task must not inherit a changed environment default."
                    )
                legacy_node = target.HMBSeedanceGeneration(
                    name="Legacy task with changed environment"
                )
                try:
                    legacy_node._broker_server_for_task(
                        "job-legacy-unknown-origin",
                        checkpoint=legacy_without_origin,
                    )
                except target._BrokerProtocolError:
                    pass
                else:
                    raise AssertionError(
                        "A legacy task with unknown origin was routed to the new server"
                    )

            opener = UnauthorizedOpener()
            bridge = target._HMBAIBrokerBridge(opener=opener, server_url=SERVER_A)
            try:
                bridge._request_json("GET", "/api/me", payload=None, timeout=1)
            except target._BrokerAuthenticationError as exc:
                assert exc.status_code == 401
            else:
                raise AssertionError("401 from the alternate Broker was accepted")
            assert len(opener.requests) == 1
            assert opener.requests[0].full_url == SERVER_A + "/api/me"
            assert opener.requests[0].get_header("Authorization") == (
                "Bearer alternate-a-token"
            )
            assert not path_a.exists(), "401 must clear only this server's token."
            assert path_b.exists(), "401 on server A must not log out server B."
            assert default_path.read_bytes() == b"existing-default-token-must-survive"
            assert legacy_path.read_bytes() == b"existing-lan-token-must-survive"


trusted_path = "/api/assets/" + "a" * 43
assert target.HMBSeedanceGeneration._broker_result_url(
    {"output": trusted_path}, server_url=SERVER_A
) == SERVER_A + trusted_path
normalized = target.HMBSeedanceGeneration._normalize_broker_task(
    {"job_id": "job-alt", "status": "completed", "output": trusted_path},
    server_url=SERVER_A,
)
assert normalized["content"]["video_url"] == SERVER_A + trusted_path
assert target._HMBAIBrokerBridge(server_url=SERVER_A).is_trusted_broker_url(
    SERVER_A + trusted_path
)
assert not target._HMBAIBrokerBridge(server_url=SERVER_A).is_trusted_broker_url(
    DEFAULT_URL + trusted_path
)
assert not target._HMBAIBrokerBridge(server_url=SERVER_A).is_trusted_broker_url(
    SERVER_B + trusted_path
), "An asset on a sibling gateway must never reuse this gateway's credentials."
assert not target._HMBAIBrokerBridge(server_url=SERVER_A).is_trusted_broker_url(
    "https://broker-a.example:8443" + trusted_path
)

# Older saved workflows have no address field. Their existing task IDs must
# continue to resolve against the previously installed/default Broker.
legacy_checkpoint = target._seedance_recovery_value({
    "task_id": "job-legacy", "task_identity": "broker_task",
    "stage": "accepted", "status": "running",
})
assert legacy_checkpoint["broker_server_url"] == LEGACY_URL


class NoNetworkOpener:
    def open(self, *_args, **_kwargs):
        raise AssertionError("Editing a Broker address must not make an HTTP request")


with (
    mock.patch.object(target, "_broker_build_opener", return_value=NoNetworkOpener()),
    mock.patch.object(
        target, "_broker_device_login",
        side_effect=AssertionError("Editing a Broker address started device login"),
    ),
    mock.patch.object(
        target._HMBAIBrokerBridge, "_request_json",
        side_effect=AssertionError("Editing a Broker address contacted the server"),
    ),
):
    fresh = target.HMBSeedanceGeneration(name="Fresh server selection")
    server_parameter = fresh.get_parameter_by_name("broker_server_url")
    assert server_parameter is not None
    assert server_parameter.serializable is False
    assert fresh.get_parameter_value("broker_server_url") == DEFAULT_URL, (
        "A fresh node displays the PC-wide built-in default until explicitly changed."
    )
    assert fresh._get_broker_bridge().server_url == DEFAULT_URL
    fresh.set_parameter_value("broker_server_url", SERVER_A)
    assert fresh.get_parameter_value("broker_server_url") == SERVER_A
    assert fresh._get_broker_bridge().server_url == SERVER_A

    reopened = target.HMBSeedanceGeneration(name="Reopened server selection")
    saved_settings = target._broker_config.broker_settings_path().read_bytes()
    reopened.set_parameter_value("broker_server_url", SERVER_B, initial_setup=True)
    assert reopened.get_parameter_value("broker_server_url") == SERVER_A
    assert reopened._get_broker_bridge().server_url == SERVER_A
    assert target._broker_config.broker_settings_path().read_bytes() == saved_settings, (
        "Restoring an old workflow must not overwrite the durable PC-wide setting."
    )

    # A durable task is inseparable from the origin on which it was submitted.
    checkpoint = reopened._set_generation_recovery_checkpoint(
        stage="pre_submit", task_id="hmb-origin-locked-task",
        task_identity="client_request", status="submitting",
    )
    assert checkpoint["broker_server_url"] == SERVER_A
    reopened.set_parameter_value("broker_server_url", SERVER_B)
    assert reopened.get_parameter_value("broker_server_url") == SERVER_B
    assert fresh.get_parameter_value("broker_server_url") == SERVER_B
    assert fresh._get_broker_bridge().server_url == SERVER_B
    assert reopened._generation_recovery_state()["broker_server_url"] == SERVER_A
    assert reopened._broker_server_for_task("hmb-origin-locked-task") == SERVER_A, (
        "The common address may change, but existing Tasks stay pinned to their original gateway."
    )
    assert reopened._get_broker_bridge(server_url=SERVER_A).server_url == SERVER_A
    assert reopened._get_broker_bridge().server_url == SERVER_B

    reopened.set_parameter_value("broker_server_url", "")
    assert reopened.get_parameter_value("broker_server_url") == ""
    assert fresh.get_parameter_value("broker_server_url") == ""
    assert target._broker_config.load_broker_base_url() == ""
    try:
        fresh._get_broker_bridge()
    except target._BrokerUnavailableError:
        pass
    else:
        raise AssertionError("An explicitly cleared common address must not fall back or connect.")
    assert reopened._broker_server_for_task("hmb-origin-locked-task") == SERVER_A

    restored = target.HMBSeedanceGeneration(name="Restored cleared server setting")
    restored.set_parameter_value("broker_server_url", SERVER_A, initial_setup=True)
    assert restored.get_parameter_value("broker_server_url") == ""
    restored.set_parameter_value("broker_server_url", SERVER_B)
    assert all(node.get_parameter_value("broker_server_url") == SERVER_B for node in (fresh, reopened, restored))
    # An in-flight operation cannot have its common target changed under it.
    fresh._generation_run_active.set()
    try:
        try:
            restored.set_parameter_value("broker_server_url", SERVER_A)
        except ValueError:
            pass
        else:
            raise AssertionError("Active Broker work must block a shared endpoint change.")
        assert target._broker_config.load_broker_base_url() == SERVER_B
    finally:
        fresh._generation_run_active.clear()


class DeviceResponse(io.BytesIO):
    def __init__(self, url: str, payload: dict, *, status: int) -> None:
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status
        self.url = url

    def geturl(self) -> str:
        return self.url


class DeviceOpener:
    def __init__(self, verification_url: str, *, start_status: int = 201,
                 redirected_token: bool = False) -> None:
        self.verification_url = verification_url
        self.start_status = start_status
        self.redirected_token = redirected_token
        self.requests = []

    def open(self, request, timeout: float):
        assert 0 < timeout <= 10
        assert request.method == "POST"
        assert request.get_header("Authorization") is None
        self.requests.append(request)
        if len(self.requests) == 1:
            assert request.full_url == SERVER_A + "/api/device/start"
            assert json.loads(request.data) == {}
            return DeviceResponse(request.full_url, {
                "device_code": "device-regression-01", "device_secret": "fixture-device-secret-not-live",
                "verification_url": self.verification_url,
            }, status=self.start_status)
        assert len(self.requests) == 2
        assert request.full_url == SERVER_A + "/api/device/token"
        assert json.loads(request.data) == {
            "device_code": "device-regression-01", "device_secret": "fixture-device-secret-not-live",
        }
        return DeviceResponse(SERVER_B + "/api/device/token" if self.redirected_token else request.full_url,
            {"access_token": "fixture-authorized-not-live"}, status=200)


for slash in ("", "/"):
    verification_url = SERVER_A + slash + "?device=device-regression-01"
    opener = DeviceOpener(verification_url)
    with (
        mock.patch.object(target.webbrowser, "open", return_value=True) as browser,
        mock.patch.object(target, "_broker_save_token") as save_token,
    ):
        assert target._broker_device_login(opener=opener, server_url=SERVER_A) == {"status": "connected"}
        browser.assert_called_once_with(verification_url, new=2, autoraise=True)
        save_token.assert_called_once_with("fixture-authorized-not-live", server_url=SERVER_A)
        assert len(opener.requests) == 2

for verification_url, status, redirected_token in (
    (SERVER_B + "/?device=device-regression-01", 201, False),
    ("https://broker-a.example:8443/?device=device-regression-01", 201, False),
    (SERVER_A + "/?device=device-regression-01#other", 201, False),
    (SERVER_A + "/?device=device-regression-01", 200, False),
    (SERVER_A + "/?device=device-regression-01", 201, True),
):
    opener = DeviceOpener(verification_url, start_status=status, redirected_token=redirected_token)
    with (
        mock.patch.object(target.webbrowser, "open", return_value=True) as browser,
        mock.patch.object(target, "_broker_save_token") as save_token,
    ):
        try:
            target._broker_device_login(opener=opener, server_url=SERVER_A)
        except target._BrokerProtocolError:
            pass
        else:
            raise AssertionError("Invalid gateway device authorization was accepted.")
        save_token.assert_not_called()
        if not redirected_token:
            browser.assert_not_called()

print(
    "HMB Seedance Broker server selection: PASS "
    "(gateway policy, per-gateway credentials/401, durable shared setting, "
    "hydration isolation, trusted result, pinned Tasks, gateway device login; "
    "no network/render)"
)
_isolated_environment.stop()
_isolated.cleanup()
