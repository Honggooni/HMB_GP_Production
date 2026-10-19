"""Offline generation-mode provenance boundaries for web rerender and sparse Final.

Uses the production builders, request fingerprint and command-bound final opener.
Only explicit deterministic transport stand-ins run; no engine, provider, uploads,
user graph or installed runtime is used or changed.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
import HMB_Seedance_Web_Rerender_Regression as fixture
import HMB_Web_Rerender_Worker_Regression as worker_fixture
from _hmb_web_rerender_settings_fixtures import freeze_command, wire_settings
import _hmb_web_rerender as web

g = fixture.target
META = {"hmb_generation_mode", "hmb_generation_task"}
PRIVATE_MODE = "_hmb_generation_mode"
JOB = "job-" + "a" * 32
PROJECT = {"project_id": "superwings12", "project_name": "슈퍼윙즈12"}


def forbidden(*args, **kwargs):
    raise AssertionError("Generation-mode regression must not use real transport or media preparation")


class GenerationModeWebRegression(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="hmb-mode-web-"))
        self.stack.enter_context(mock.patch.dict(os.environ, {"LOCALAPPDATA": self.temp}))
        self.stack.enter_context(mock.patch.object(socket, "create_connection", forbidden))
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_runtime_node_is_live", lambda self, **kw: not self._hmb_node_deleted))
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_reconcile_shared_shot_routing", lambda self, **kw: {"ok": True, "changed": 0}))
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_manual_agent_prompt_source", lambda self: fixture.agent))
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_exact_incoming_source", lambda *args, **kw: None))
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_has_incoming_parameter_connection", lambda *args: False))
        self.stack.enter_context(mock.patch.object(g.GriptapeNodes, "NodeManager", lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "offline-mode-flow"), create=True))
        # URL encoding is the sole media boundary needed by these builders.
        # It is a deterministic stand-in, never an upload or model execution.
        self.stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_prepare_media_reference", lambda self, kind, value: value))

    def test_metadata_changes_null_and_absence_have_identical_render_fingerprints(self):
        request = {**wire_settings(), "provider": "volcengine_ark", "prompt": "literal {{SIGN}}",
            "image_urls": ["https://fixture.invalid/image.png"], "client_request_id": "hmb-mode-one", **PROJECT}
        original = deepcopy(request)
        expected = web.request_fingerprint(request)
        for mode, task in (("only", "Reference to Video"), ("shot", "Reference to Video"), (None, None), ("only", None)):
            with self.subTest(mode=mode, task=task):
                self.assertEqual(web.request_fingerprint({**request, "hmb_generation_mode": mode, "hmb_generation_task": task}), expected)
        self.assertEqual(request, original)
        # Excluding provenance must never exclude an actual render change.
        for change in ({"prompt": "different"}, {"duration_seconds": 7},
                {"omni_reference_task_type": "edit"}, {"image_urls": ["https://fixture.invalid/other.png"]}):
            self.assertNotEqual(web.request_fingerprint({**request, **change}), expected)

    def test_provenance_does_not_enter_digest_bound_parent_render_settings(self):
        current = worker_fixture.command()
        original = deepcopy(current)
        frozen = web.parent_generation_settings(current)
        for mode, task in (("only", "Reference to Video"), ("shot", "Video Editing"), (None, None)):
            candidate = {**current, "hmb_generation_mode": mode, "hmb_generation_task": task}
            self.assertEqual(web.parent_generation_settings(candidate), frozen)
            self.assertEqual(candidate["frozen_generation_settings_sha256"], original["frozen_generation_settings_sha256"])
            settings, context = g._web_rerender_parent_execution_settings(web.parent_generation_settings(candidate))
            self.assertFalse(META & settings.keys()); self.assertFalse(META & context.keys())
        for field in META:
            mixed = {**frozen, field: "only" if field.endswith("mode") else "Reference to Video"}
            with self.assertRaises(ValueError):
                web.parent_generation_settings(freeze_command(current, mixed))
        self.assertEqual(current, original)

    def test_command_opener_preserves_sparse_parent_keys_and_semantic_prepared_hash(self):
        sparse = {key: value for key, value in wire_settings().items() if key not in {"quality", "aspect_ratio", "priority"}}
        command = freeze_command(worker_fixture.command(), sparse)
        before = deepcopy(command)
        protocol = worker_fixture.Protocol()
        text = "web {{LITERAL}} output"
        result = {"text": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "policy_identity": {"mode": "preserved_parent", "reinjected": False}}
        journal = web.OperationJournal(self.temp)
        entry = journal.accept(origin=protocol.bridge.server_url, owner_key="17", command={**command, "command_id": command["operation_id"]})
        journal.transition(entry["operation_key"], {"accepted"}, "render_preparing")
        live = threading.Event(); live.set()
        opener = web.CommandSubmissionOpener(protocol, protocol, command, journal, entry["operation_key"], result, live)
        body = {"model": sparse["model"], "prompt": text, "client_request_id": command["render_key"], **PROJECT,
            "resolution": "1080p", "duration_seconds": 9, "generate_audio": True, "priority": 8,
            "image_urls": ["same-image"], "video_urls": ["same-picker"],
            "hmb_generation_mode": "only", "hmb_generation_task": "Reference to Video"}
        request = Request(protocol.bridge.server_url + "/api/v1/generate/video", data=json.dumps(body).encode(),
            headers={"Idempotency-Key": command["render_key"], "Content-Length": "1"}, method="POST")
        opener.open(request, timeout=1)
        self.assertEqual(len(protocol.posts), 1)
        posted = protocol.posts[0][1]
        self.assertEqual({key: value for key, value in posted.items() if key in web.PARENT_SETTINGS_FIELDS}, sparse)
        self.assertEqual(posted["prompt"], text); self.assertEqual(posted["image_urls"], body["image_urls"])
        self.assertEqual(posted["video_urls"], body["video_urls"])
        self.assertEqual(request.get_header("Idempotency-key"), command["render_key"])
        self.assertEqual(protocol.events[0][0], "prepared")
        self.assertEqual(protocol.events[0][1]["render_payload_sha256"], web.request_fingerprint({key: value for key, value in posted.items() if key not in META}))
        self.assertEqual(command, before)
        with self.assertRaises(RuntimeError):
            opener.open(request, timeout=1)
        self.assertEqual(len(protocol.posts), 1, "A provenance update must never retry a submitted web command")

    def test_web_unknown_parent_never_inherits_current_generator_only_or_shot_mode(self):
        for current_mode in ("only", "shot"):
            with self.subTest(current_mode=current_mode):
                owner = fixture.new_node()
                owner.parameter_values[g.SHOT_SELECTOR_PARAMETER] = g.SHOT_ONLY_LABEL
                snapshot = owner._hmb_web_rerender_capture_inputs()
                frozen = wire_settings(snapshot["generation_settings"])
                settings, _ = g._web_rerender_parent_execution_settings(frozen)
                prepared = g._web_rerender_apply_parent_settings(snapshot["params"], settings)
                # Simulate either current native mode surviving into a private
                # view. It is never proof of the old parent operation's origin.
                prepared[PRIVATE_MODE] = current_mode
                prepared["prompt"] = "fresh web result"
                if current_mode == "shot":
                    owner.parameter_values.update({g.SHOT_SELECTOR_PARAMETER: "01 · renamed current Shot",
                        g.SHOT_CHANNEL_UUID_PARAMETER: "11111111-1111-4111-8111-111111111111",
                        g.SHOT_UUID_PARAMETER: "22222222-2222-4222-8222-222222222222",
                        g.SHOT_NUMBER_PARAMETER: 1, g.SHOT_NAME_PARAMETER: "renamed current Shot"})
                view = g._HMBWebRerenderExecution.read_view(owner)
                native_before = deepcopy(owner.parameter_values)
                with mock.patch.object(g.HMBSeedanceGeneration, "get_parameter_value", side_effect=AssertionError("Payload reread mutable native controls")):
                    payload = view._build_broker_payload(deepcopy(prepared))
                self.assertFalse(META & payload.keys(), payload)
                self.assertEqual(payload["prompt"], "fresh web result")
                self.assertEqual(payload["image_urls"], snapshot["params"]["reference_images"])
                self.assertEqual(owner.parameter_values, native_before)
                self.assertFalse(META & frozen.keys())

    def test_sparse_final_builder_and_actual_bridge_keep_exact_original_reference(self):
        owner = fixture.new_node()
        view = g._HMBWebRerenderExecution.read_view(owner)
        for mode in ("only", "shot", None):
            params = owner._get_parameters()
            params.update(model_id=g.SEEDANCE_2_5_MODEL_ID, draft_action=g.DRAFT_ACTION_FINAL,
                draft_job_id=JOB, resolution="1080p", output_format="mov", return_last_frame=False,
                _hmb_draft_supported=True, _hmb_draft_source={"draft_job_id": JOB, **PROJECT}, **PROJECT)
            params[PRIVATE_MODE] = mode
            params.update(hmb_generation_mode="only", hmb_generation_task="Video Editing")
            payload = view._build_broker_payload(params)
            expected = {"provider": "volcengine_ark", "model": g.SEEDANCE_2_5_MODEL_ID,
                "draft_job_id": JOB, "resolution": "1080p", "output_format": "mov", **PROJECT}
            self.assertEqual(payload, expected)
            payload["client_request_id"] = "hmb-final-fixed"
            bridge = g._HMBAIBrokerBridge(server_url=g.AI_BROKER_INTERNAL_ORIGIN)
            bridge.require_seedance_draft_features = mock.Mock(return_value="mov")
            requests = []
            def request(method, path, **kwargs):
                requests.append((method, path, deepcopy(kwargs)))
                return {"job_id": "job-" + "b" * 32}
            bridge._request_json = request
            bridge.generate_seedance(payload, timeout=1)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0][:2], ("POST", "/api/v1/generate/video"))
            self.assertEqual(requests[0][2]["payload"], payload)
            self.assertEqual(requests[0][2]["idempotency_key"], "hmb-final-fixed")
            self.assertFalse(META & requests[0][2]["payload"].keys())
            bridge.require_seedance_draft_features.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
