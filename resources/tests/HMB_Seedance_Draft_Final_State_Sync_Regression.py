"""Exact Draft/account-scoped advisory GET; never creates a provider task."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
spec = importlib.util.spec_from_file_location("draft_state_fixture", Path(__file__).with_name("HMB_Seedance_Draft_Shot_Regression.py"))
fixture = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture
spec.loader.exec_module(fixture)
t = fixture.t
JOB = fixture.JOB
CHILD = "job-" + "c" * 32


def projection(source, state="available", **changes):
    value = {"schema": "hmb-review-draft-final-v1", "state_schema": "hmb-draft-final-state-v1",
        "source_task_id": source["draft_job_id"], "state": state, "is_draft": True,
        "eligible": state == "available", "consumed": False if state == "available" else None,
        "checked_at": int(time.time()), "expires_at": int(time.time()) + 604800,
        "owner_user_id": 7, "project_id": source["project_id"], "project_name": source["project_name"],
        "child_task_id": None, "child_status": None,
        "idempotency_key": t._seedance_draft_final_request_id(source["draft_job_id"])}
    value.update(changes)
    return value


class Response(io.BytesIO):
    status = 200
    def __init__(self, value, url):
        super().__init__(json.dumps(value).encode())
        self.url = url
    def geturl(self):
        return self.url


class Opener:
    def __init__(self):
        self.calls = []
        self.reply = None
    def open(self, request, timeout=None):
        self.calls.append((request.method, request.selector, timeout))
        if request.method == "GET" and request.selector == "/api/v1/maintenance-intake/capabilities":
            import urllib.error
            raise urllib.error.HTTPError(request.full_url, 404, "Synthetic native-only Broker", {}, io.BytesIO(b'{}'))
        if request.method != "GET":
            raise AssertionError("State synchronization must never write or create")
        reply = self.reply(request) if callable(self.reply) else self.reply
        if isinstance(reply, Exception):
            raise reply
        return Response(deepcopy(reply), request.full_url)


class Node(fixture.Node):
    _store_draft_source = t.HMBSeedanceGeneration._store_draft_source

    def __init__(self, *, shot=True):
        super().__init__(shot=shot)
        self.opener = Opener()
        self.credential = "offline-account-A"
        self.bridge = t._HMBAIBrokerBridge(opener=self.opener, server_url=fixture.ORIGIN)
        self.bridge._load_access_token = lambda: self.credential
        self._schedule_draft_final_status_sync = mock.Mock()
        self._sync_seedance_shot_widget = mock.Mock()
        self.source = fixture.completed_source(self)
        self._store_draft_source(self.source)
        self.opener.reply = projection(self.source)

    def query(self):
        return asyncio.run(self._query_draft_final_server_state(self._draft_source_record()))


class DraftFinalStateSyncTests(unittest.TestCase):
    def setUp(self):
        # The scenario explicitly selects its synthetic Draft's original
        # Broker; production defaults are unrelated to this saved Task.
        selected = mock.patch.object(t._broker_config, "load_broker_base_url", return_value=fixture.ORIGIN)
        selected.start()
        self.addCleanup(selected.stop)
        self.guard = mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unmocked HTTP"))
        self.guard.start()
    def tearDown(self):
        self.guard.stop()
        while fixture.base.TEMPORARIES:
            fixture.base.TEMPORARIES.pop().cleanup()

    def test_get_exact_source_subset_and_no_prompt_or_submit_payload_retention(self):
        node = Node()
        node.opener.reply.update(prompt="PRIVATE", submit_payload={"prompt": "PRIVATE"}, token="SECRET")
        result = node.query()
        self.assertEqual(node.opener.calls, [("GET", f"/api/v1/reviews/tasks/{JOB}/draft-final", 5.0)])
        self.assertTrue(result["eligible"])
        self.assertFalse({"prompt", "token", "submit_payload"} & result.keys())
        self.assertNotIn("PRIVATE", repr(node._hmb_draft_final_status_cache))

    def test_actual_server_synthetic_projection_contract_all_thirteen_cases(self):
        data = json.loads(Path(__file__).with_name("_hmb_draft_final_state_contract_fixtures.json").read_text(encoding="utf-8"))
        self.assertEqual(data["source_fixture_sha256"], "76e051b1d8705730b812e82b7639276eb70450c47510640393ccfe235f5294b1")
        self.assertEqual(len(data["cases"]), 13)
        source = {**fixture.base.SOURCE, **data["fixture_identity"]}
        source["draft_job_id"] = source.pop("source_task_id")
        for row in data["cases"]:
            with self.subTest(case=row["name"]), mock.patch.object(t.time, "time", return_value=data["fixture_checked_at"]):
                projection = row["projection"]
                if projection["owner_user_id"] is None or projection["source_task_id"] is None:
                    with self.assertRaises(t._BrokerProtocolError):
                        t._seedance_draft_final_state_value(projection, source)
                else:
                    result = t._seedance_draft_final_state_value(projection, source)
                    self.assertEqual(result["state"], projection["state"])
                    self.assertEqual(result["eligible"], projection["state"] == "available")
                    self.assertEqual(result["child_task_id"], projection["child_task_id"])
                    if row["name"] == "completed_after_source_expiry":
                        self.assertEqual(result["state"], "completed")

    def test_local_completed_source_waits_for_get_and_available_arms_without_authored_writes(self):
        node = Node()
        before = deepcopy(node.parameter_values)
        initial = node._draft_ui_state()
        self.assertEqual(initial["final_state"], "checking")
        self.assertFalse(initial["final_available"])
        node.query()
        self.assertTrue(node._draft_ui_state()["final_available"])
        self.assertEqual(node.parameter_values, before)

    def test_same_draft_web_running_disables_completed_hides_and_keeps_child(self):
        node = Node()
        node.query()
        for state, status, visible in (("reserved", "submitting", True), ("running", "downloading", True),
                                       ("completed", "completed", False)):
            node.opener.reply = projection(node.source, state, consumed=True, child_task_id=CHILD, child_status=status)
            node.query()
            ui = node._draft_ui_state()
            self.assertEqual((ui["final_state"], ui["final_visible"], ui["final_task_id"]), (state, visible, CHILD))
            self.assertFalse(ui["final_available"])
        self.assertEqual(node._draft_source_record()["final_job_id"], CHILD)

    def test_unknown_keeps_child_and_idempotency_identity_never_arms(self):
        node = Node()
        node.opener.reply = projection(node.source, "unknown", child_task_id=CHILD, child_status=None)
        result = node.query()
        self.assertEqual(result["idempotency_key"], t._seedance_draft_final_request_id(JOB))
        self.assertFalse(node._draft_ui_state()["final_available"])
        self.assertTrue(node._draft_ui_state()["final_visible"])

    def test_stale_available_and_expiry_cannot_clear_known_consumed_child(self):
        node = Node()
        node.opener.reply = projection(node.source, "completed", consumed=True, child_task_id=CHILD, child_status="completed")
        node.query()
        for late in (projection(node.source), projection(node.source, "expired")):
            node.opener.reply = late
            node.query()
            ui = node._draft_ui_state()
            self.assertFalse(ui["final_available"])
            self.assertFalse(ui["final_visible"])
            self.assertEqual(ui["final_task_id"], CHILD)

    def test_existing_final_recovery_keeps_server_child_after_reload_without_cache(self):
        node = Node()
        recovered = {**node.source, "final_request_id": t._seedance_draft_final_request_id(JOB)}
        node._generation_recovery_state = mock.Mock(return_value={"draft_source": recovered})
        node.opener.reply = projection(node.source, "completed", consumed=True,
                                      child_task_id=CHILD, child_status="completed")
        node.query()
        node._hmb_draft_final_status_cache = {}
        self.assertEqual(node._draft_source_record()["final_job_id"], CHILD)
        self.assertFalse(node._draft_ui_state()["final_available"])
        self.assertFalse(node._draft_ui_state()["final_visible"])

    def test_response_account_and_source_switches_are_discarded(self):
        for change in ("account", "source", "project", "origin"):
            with self.subTest(change=change):
                node = Node()
                def late(request):
                    result = projection(node.source)
                    if change == "account":
                        node.credential = "offline-account-B"
                    elif change == "source":
                        node._store_draft_source(fixture.completed_source(node, draft_job_id="job-" + "d" * 32))
                    elif change == "project":
                        node.current_project = {"project_id": "katuri8", "project_name": "까투리8"}
                    else:
                        node.bridge._server_url = "http://127.0.0.1:8089"
                    return result
                node.opener.reply = late
                if change in {"account", "source", "origin"}:
                    with self.assertRaises(t._BrokerProtocolError):
                        node.query()
                elif change == "project":
                    node.query()
                    self.assertFalse(node._draft_ui_state()["final_available"])

    def test_new_native_draft_rearms_but_web_source_never_overwrites_owner(self):
        node = Node()
        node.opener.reply = projection(node.source, "consumed", consumed=True, child_task_id=CHILD, child_status="failed")
        node.query()
        old = deepcopy(node.parameter_values)
        view = t._HMBWebRerenderExecution.read_view(node)
        view._store_draft_source(fixture.completed_source(node, draft_job_id="job-" + "e" * 32))
        self.assertEqual(node.parameter_values, old)
        self.assertFalse(view._draft_ui_state()["final_available"])
        source = fixture.completed_source(node, draft_job_id="job-" + "d" * 32)
        node._store_draft_source(source)
        node.opener.reply = projection(source)
        self.assertFalse(node._draft_ui_state()["final_available"])
        node.query()
        self.assertTrue(node._draft_ui_state()["final_available"])

    def test_401_and_http_errors_are_read_only_and_preserve_consumption(self):
        for code in (401, 403, 404, 429, 503):
            with self.subTest(code=code):
                node = Node()
                node._store_draft_source({**node.source, "final_request_id": t._seedance_draft_final_request_id(JOB)})
                node.bridge._clear_access_token = mock.Mock(side_effect=AssertionError("Credential deletion"))
                node.opener.reply = urllib.error.HTTPError(fixture.ORIGIN + "/x", code, "synthetic", {}, io.BytesIO(b"{}"))
                with self.assertRaises(t._BrokerError):
                    node.query()
                self.assertFalse(node._draft_ui_state()["final_available"])
                self.assertIn("final_request_id", node._draft_source_record())
                node.bridge._clear_access_token.assert_not_called()

    def test_malformed_or_wrong_identity_never_arms(self):
        node = Node()
        base = projection(node.source)
        for changes in ({"source_task_id": CHILD}, {"project_id": "katuri8"}, {"owner_user_id": None},
                        {"eligible": 1}, {"consumed": None}, {"checked_at": True},
                        {"checked_at": int(time.time()) - 301},
                        {"idempotency_key": "job-" + "f" * 32}, {"state_schema": "future"},
                        {"child_task_id": CHILD}, {"child_status": "completed"},
                        {"expires_at": None}, {"expires_at": int(time.time()) - 1},
                        {"state": "future"}, {"is_draft": False},
                        {"state": "running", "eligible": False, "consumed": True},
                        {"state": "completed", "eligible": False, "child_task_id": CHILD,
                         "child_status": "completed", "consumed": False}):
            with self.subTest(changes=changes):
                node.opener.reply = {**base, **changes}
                with self.assertRaises(t._BrokerProtocolError):
                    node.query()
                self.assertFalse(node._draft_ui_state()["final_available"])

    def test_owner_drift_locks_without_erasing_stable_owner_even_after_get_failure(self):
        node = Node()
        node.query()
        for owner in (8, 9):
            node.opener.reply = projection(node.source, owner_user_id=owner)
            with self.assertRaises(t._BrokerProtocolError):
                node.query()
            self.assertEqual(node._hmb_draft_final_status_cache["owner_user_id"], 7)
            self.assertEqual(node._draft_ui_state()["final_state"], "unknown")
            self.assertFalse(node._draft_ui_state()["final_available"])

    def test_get_failure_immediately_disables_previously_available_cache(self):
        node = Node()
        node.query()
        self.assertTrue(node._draft_ui_state()["final_available"])
        node.opener.reply = urllib.error.URLError("synthetic timeout")
        with self.assertRaises(t._BrokerError):
            node.query()
        self.assertEqual(node._draft_ui_state()["final_state"], "unknown")
        self.assertFalse(node._draft_ui_state()["final_available"])

    def test_expired_cache_disables_without_inline_http_and_refreshes_in_background(self):
        node = Node()
        node.query()
        calls = len(node.opener.calls)
        node._hmb_draft_final_status_cache["received_at"] -= 30
        ui = node._draft_ui_state()
        self.assertEqual(ui["final_state"], "checking")
        self.assertFalse(ui["final_available"])
        self.assertEqual(len(node.opener.calls), calls)
        node._schedule_draft_final_status_sync.assert_called()

    def test_background_watch_is_bounded_read_only_and_stops_on_consumption(self):
        async def scenario():
            node = Node()
            identity = node._draft_final_status_identity(node.source)
            count = 0
            def response(request):
                nonlocal count
                count += 1
                return projection(node.source) if count == 1 else projection(node.source, "completed",
                    consumed=True, child_task_id=CHILD, child_status="completed")
            node.opener.reply = response
            sleep = mock.AsyncMock()
            with mock.patch.object(t.asyncio, "sleep", sleep):
                await node._poll_draft_final_server_state(node.source, identity)
            self.assertEqual(count, 2)
            sleep.assert_awaited_once_with(t._DRAFT_FINAL_SYNC_SECONDS)
            self.assertEqual(node._sync_seedance_shot_widget.call_count, 2)
            self.assertFalse(node._draft_ui_state()["final_visible"])
        asyncio.run(scenario())

    def test_failed_background_get_locks_existing_draft_without_clearing_key_or_repeating_create(self):
        async def scenario():
            node = Node()
            node._store_draft_source({**node.source, "final_request_id": t._seedance_draft_final_request_id(JOB)})
            identity = node._draft_final_status_identity(node.source)
            node.opener.reply = urllib.error.URLError("synthetic timeout")
            async def stop(_seconds):
                node.live = False
            with mock.patch.object(t.asyncio, "sleep", stop):
                await node._poll_draft_final_server_state(node.source, identity)
            self.assertEqual(node._hmb_draft_final_status_cache["value"]["state"], "unknown")
            self.assertEqual(len(node.opener.calls), 1)
            self.assertEqual(node._draft_source_record()["final_request_id"], t._seedance_draft_final_request_id(JOB))
        asyncio.run(scenario())

    def test_unrelated_preview_busy_hides_old_final_and_has_no_native_cancel(self):
        node = Node()
        node.opener.reply = projection(node.source, "running", consumed=True, child_task_id=CHILD, child_status="running")
        node.query()
        node._generation_run_active.set()
        node._hmb_active_draft_action = t.DRAFT_ACTION_PREVIEW
        ui = node._draft_ui_state()
        self.assertFalse(ui["final_visible"])
        self.assertFalse(ui["final_busy"])
        self.assertFalse(ui["cancel_available"])

    def test_only_current_project_change_disables_old_draft_but_legacy_missing_project_is_retained(self):
        node = Node(shot=False)
        node.query()
        self.assertTrue(node._draft_ui_state()["final_available"])
        node.current_project = {"project_id": "katuri8", "project_name": "까투리8"}
        self.assertFalse(node._draft_ui_state()["final_available"])
        self.assertIn("project", node._draft_ui_state()["reason"])
        with self.assertRaisesRegex(ValueError, "Only project"):
            node._validated_draft_final_source()
        node._hmb_generation_project = mock.Mock(side_effect=t._ProjectSelectionRequired("no project source"))
        self.assertTrue(node._draft_ui_state()["final_available"])
        self.assertEqual(node._validated_draft_final_source()["project_id"], node.source["project_id"])
        node._hmb_generation_project = mock.Mock(side_effect=ValueError("invalid registered project route"))
        self.assertFalse(node._draft_ui_state()["final_available"])

    def test_click_forces_fresh_get_and_web_consumed_draft_never_posts(self):
        async def scenario():
            node = Node()
            node.opener.reply = projection(node.source, "completed", consumed=True, child_task_id=CHILD, child_status="completed")
            node.bridge.generate_seedance = mock.Mock(side_effect=AssertionError("Duplicate Final create"))
            # Run the real process until the new authenticated advisory gate.
            node._ensure_broker_connected = mock.AsyncMock(return_value=node.bridge)
            with fixture.run_boundaries(node):
                await node._run_draft_final(node._draft_source_record(), "native-final-click")
            node.bridge.generate_seedance.assert_not_called()
            self.assertEqual(node.opener.calls[0][0], "GET")
            self.assertFalse(node._draft_ui_state()["final_visible"])
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
