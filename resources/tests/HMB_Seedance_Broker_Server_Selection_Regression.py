"""Offline regression for per-node FN AI Broker server selection.

The test uses clean-CI Griptape stubs, temporary token storage and a fake
opener. It never contacts a Broker, starts device authorization or creates a
billable render.
"""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hmb_seedance_clean_ci_stubs import install_clean_ci_griptape_stubs


install_clean_ci_griptape_stubs()
spec = importlib.util.spec_from_file_location(
    "hmb_seedance_broker_server_selection", ROOT / "HMBSeedanceGeneration.py"
)
assert spec is not None and spec.loader is not None
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)


DEFAULT_URL = target.AI_BROKER_SERVER_URL
SERVER_A = "https://broker-a.example:8443"
SERVER_B = "https://broker-b.example"


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
for invalid in (
    "http://broker-a.example:8443",  # Only the installed LAN origin has an HTTP exception.
    "http://192.168.203.246:8080",
    "ftp://broker-a.example",
    "https://user:secret@broker-a.example",
    "https://broker-a.example/path",
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
    with mock.patch.dict(os.environ, {"APPDATA": temporary}):
        default_path = target._broker_token_path(server_url=DEFAULT_URL)
        path_a = target._broker_token_path(server_url=SERVER_A)
        path_b = target._broker_token_path(server_url=SERVER_B)
        assert default_path != path_a != path_b
        assert path_a != path_b
        assert default_path.name == "access_token_v2.dpapi", (
            "The installed Broker and Agent must retain their legacy token path."
        )

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
            # A later environment override must not inherit the shared LAN
            # credential, even when the node leaves its URL field empty.
            with (
                mock.patch.object(target, "AI_BROKER_SERVER_URL", SERVER_B),
                mock.patch.object(
                    target, "_broker_load_bearer_token_readonly",
                    side_effect=AssertionError(
                        "The shared LAN token was read for another origin"
                    ),
                ),
            ):
                assert target._broker_validated_server_url() == SERVER_B
                assert target._broker_token_path() == path_b
                assert target._broker_token_path() != default_path
                assert target._broker_load_token() == "alternate-b-token"
                assert default_path.read_bytes() == b"existing-default-token-must-survive"

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

# Older saved workflows have no address field. Their existing task IDs must
# continue to resolve against the previously installed/default Broker.
legacy_checkpoint = target._seedance_recovery_value({
    "task_id": "job-legacy", "task_identity": "broker_task",
    "stage": "accepted", "status": "running",
})
assert legacy_checkpoint["broker_server_url"] == DEFAULT_URL


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
    assert server_parameter.serializable is True
    assert fresh.get_parameter_value("broker_server_url") == "", (
        "A fresh node inherits the installed environment/default Broker."
    )
    assert fresh._get_broker_bridge().server_url == DEFAULT_URL
    fresh.set_parameter_value("broker_server_url", SERVER_A)
    assert fresh.get_parameter_value("broker_server_url") == SERVER_A
    assert fresh._get_broker_bridge().server_url == SERVER_A

    reopened = target.HMBSeedanceGeneration(name="Reopened server selection")
    reopened.set_parameter_value("broker_server_url", SERVER_A, initial_setup=True)
    assert reopened.get_parameter_value("broker_server_url") == SERVER_A
    assert reopened._get_broker_bridge().server_url == SERVER_A

    # A durable task is inseparable from the origin on which it was submitted.
    checkpoint = reopened._set_generation_recovery_checkpoint(
        stage="pre_submit", task_id="hmb-origin-locked-task",
        task_identity="client_request", status="submitting",
    )
    assert checkpoint["broker_server_url"] == SERVER_A
    try:
        reopened.set_parameter_value("broker_server_url", SERVER_B)
    except (target._BrokerError, ValueError):
        pass
    assert reopened.get_parameter_value("broker_server_url") == SERVER_A, (
        "An unresolved task must not be silently rebound to another Broker."
    )
    assert reopened._generation_recovery_state()["broker_server_url"] == SERVER_A

print(
    "HMB Seedance Broker server selection: PASS "
    "(origin policy, per-server credentials/401, changed-default "
    "isolation, trusted result, saved node, unresolved task binding; "
    "no network/render)"
)
