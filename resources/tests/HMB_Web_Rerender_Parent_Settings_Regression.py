"""Offline parent-setting authority, sparse wire identity, and no-paid-call gates."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from _hmb_web_rerender_settings_fixtures import freeze_command, wire_settings
import _hmb_web_rerender as web
import HMB_Seedance_Web_Rerender_Regression as fixture
import HMB_Web_Rerender_Worker_Regression as worker_fixture

g = fixture.target


class ParentSettingsRegression(unittest.TestCase):
    def test_draft_parent_capability_is_literal_optional_and_downgrade_safe(self):
        command = worker_fixture.command()
        for offered in (True, False, "true", None):
            calls = []
            capability = {"project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA, "project_ids": sorted(web.PROJECT_IDS)},
                          "parent_settings_contract": web.PARENT_SETTINGS_SCHEMA}
            if offered is not None: capability["parent_draft_preserved"] = offered
            reply = {**capability, "schema": web.PROTOCOL, "worker_id": command["operation_id"],
                     "session_id": command["session_id"], "registered": True, "user_id": 17}
            def request(method, path, **kwargs):
                calls.append((method, deepcopy(kwargs.get("payload"))))
                return deepcopy(capability if method == "GET" else reply)
            protocol = web.BrokerProtocol(SimpleNamespace(_request_json=request), command["operation_id"], command["session_id"])
            with self.subTest(offered=offered):
                protocol.heartbeat([{"target_id": command["target_id"], "supports_draft_parent_settings": True}], register=True)
                self.assertIs(protocol.parent_draft_preserved, offered is True)
                sent = calls[-1][1]["targets"][0]
                self.assertEqual(sent.get("supports_draft_parent_settings"), True if offered is True else None)
                self.assertTrue(protocol.parent_settings_ready)  # Ordinary remains compatible.
                reply.pop("parent_draft_preserved", None)
                protocol.heartbeat([])
                self.assertIs(protocol.parent_draft_preserved, False)

    def test_optional_draft_flag_is_literal_and_requires_25_480(self):
        request = worker_fixture.command()
        draft = {**wire_settings(), "quality": "480p", "resolution": "480p", "draft": True}
        accepted = web.parent_generation_settings(freeze_command(request, draft))
        self.assertIs(accepted["draft"], True)
        settings, context = g._web_rerender_parent_execution_settings(accepted)
        self.assertEqual(settings["draft_action"], g.DRAFT_ACTION_PREVIEW)
        self.assertEqual(context["draft_action"], g.DRAFT_ACTION_PREVIEW)
        for bad in ({**draft, "draft": "true"}, {**draft, "draft": 1}, {**draft, "draft": None},
                    {**draft, "quality": "720p"}, {**draft, "resolution": "1080p"},
                    {**draft, "model": g.SEEDANCE_2_0_MODEL_ID}, {**draft, "draft_job_id": "job-" + "a" * 32}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                web.parent_generation_settings(freeze_command(request, bad))

    def test_ordinary_absent_or_false_draft_remains_off_without_source_inheritance(self):
        for frozen in (wire_settings(), {**wire_settings(), "draft": False}):
            settings, _ = g._web_rerender_parent_execution_settings(frozen)
            params = g._web_rerender_apply_parent_settings(
                {"draft_job_id": "job-" + "a" * 32, "_hmb_draft_source": {"completed": True},
                 "reference_images": ["same-image"]}, settings)
            self.assertEqual(params["draft_action"], g.DRAFT_ACTION_OFF)
            self.assertEqual(params["draft_job_id"], "")
            self.assertNotIn("_hmb_draft_source", params)
            self.assertEqual(params["reference_images"], ["same-image"])

    def test_strict_digest_and_parent_project_binding(self):
        request = worker_fixture.command()
        self.assertEqual(web.parent_generation_settings(request), request["frozen_generation_settings"])
        for field, replacement in (("parent_task_id", "other-parent"), ("project_id", "katuri8"),
                                   ("frozen_generation_settings_sha256", "0" * 64),
                                   ("frozen_generation_settings_binding_sha256", "0" * 64)):
            changed = deepcopy(request); changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                web.parent_generation_settings(changed)
        changed = deepcopy(request); changed["frozen_generation_settings"]["duration_seconds"] = 8
        with self.assertRaisesRegex(ValueError, "integrity_failed"):
            web.parent_generation_settings(changed)

    def test_incomplete_unsupported_and_type_confusions_fail(self):
        request, good = worker_fixture.command(), wire_settings()
        for field in ("model", "input_mode", "generate_audio", "duration_seconds"):
            missing = deepcopy(good); missing.pop(field)
            with self.subTest(missing=field), self.assertRaises(ValueError):
                web.parent_generation_settings(freeze_command(request, missing))
        no_size = {key: value for key, value in good.items() if key not in {"quality", "resolution"}}
        bad = [no_size, {**good, "codec": "h264"}, {**good, "seed": 0}, {**good, "camera_fixed": False},
               {**good, "generate_audio": "OFF"}, {**good, "generate_audio": 0},
               {**good, "priority": False}, {**good, "duration_seconds": True},
               {**good, "duration": 9}, {**good, "ratio": "9:16"}]
        for settings in bad:
            with self.subTest(keys=list(settings)), self.assertRaises(ValueError):
                web.parent_generation_settings(freeze_command(request, settings))

    def test_parent_controls_replace_current_while_sources_remain(self):
        original = {"model_id": g.SEEDANCE_2_0_MODEL_ID, "resolution": "1080p", "duration": 10,
                    "generate_audio": True, "priority": 9, "seed": 555, "camera_fixed": True,
                    "reference_images": ["image-a"], "video_references": ["picker-b"],
                    "project_id": "superwings12", "poll_interval_seconds": 1}
        before = deepcopy(original)
        settings, context = g._web_rerender_parent_execution_settings(wire_settings())
        result = g._web_rerender_apply_parent_settings(original, settings)
        self.assertEqual(result["model_id"], g.SEEDANCE_2_5_MODEL_ID)
        self.assertEqual((result["resolution"], result["duration"], result["priority"]), ("720p", 4, 0))
        self.assertIs(result["generate_audio"], False)
        self.assertNotIn("seed", result); self.assertNotIn("camera_fixed", result)
        self.assertEqual(result["reference_images"], ["image-a"])
        self.assertEqual(result["video_references"], ["picker-b"])
        self.assertNotIn("watermark", context); self.assertNotIn("output_format", context)
        self.assertEqual(original, before)
        result["reference_images"].append("different")
        self.assertEqual(original, before)

    def test_task_variants_and_unsupported_model_fail_before_agent(self):
        for omni, task, duration in (("reference", g.TASK_REFERENCE_TO_VIDEO, 4),
                                    ("edit", g.TASK_VIDEO_EDITING, -1),
                                    ("extend", g.TASK_VIDEO_EXTENSION, 6)):
            settings, context = g._web_rerender_parent_execution_settings({
                **wire_settings(), "omni_reference_task_type": omni, "duration_seconds": duration})
            self.assertEqual(settings["task"], task)
            self.assertEqual(context["duration"], duration)
        for settings in ({**wire_settings(), "model": "retired-or-invented"},
                         {**wire_settings(), "omni_reference_task_type": "invented"},
                         {**wire_settings(), "input_mode": "Text Only"},
                         {**wire_settings(), "resolution": "1080p"}):
            with self.assertRaises(ValueError):
                g._web_rerender_parent_execution_settings(settings)

    def test_scalar_aliases_map_without_defaults_in_context(self):
        wire = {"model": g.SEEDANCE_2_0_MODEL_ID, "input_mode": g.INPUT_MODE_TEXT_ONLY,
                "resolution": "1080p", "duration": -1, "ratio": "9:16", "generate_audio": False}
        validated = web.parent_generation_settings(freeze_command(worker_fixture.command(), wire))
        settings, context = g._web_rerender_parent_execution_settings(validated)
        self.assertEqual((settings["resolution"], settings["duration"], settings["ratio"]), ("1080p", -1, "9:16"))
        self.assertNotIn("priority", context)
        self.assertNotIn("output_format", context)

    def test_sparse_wire_is_exact_and_media_prompt_untouched(self):
        request = worker_fixture.command()
        sparse = {key: value for key, value in wire_settings().items() if key not in {"priority", "aspect_ratio", "quality"}}
        request = freeze_command(request, sparse)
        protocol = worker_fixture.Protocol()
        text = "resolved web output"
        result = {"text": text, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                  "policy_identity": {"mode": "preserved_parent", "reinjected": False}}
        body = {"model": sparse["model"], "prompt": text, "client_request_id": request["render_key"],
                "project_id": request["project_id"], "project_name": request["project_name"],
                "resolution": "1080p", "quality": "1080p", "duration_seconds": 9, "generate_audio": True,
                "watermark": True, "priority": 9, "output_format": "mov", "aspect_ratio": "9:16",
                "image_urls": ["unchanged-image"], "video_urls": ["unchanged-picker"]}
        with tempfile.TemporaryDirectory() as root:
            journal = web.OperationJournal(root)
            entry = journal.accept(origin=protocol.bridge.server_url, owner_key="17",
                                   command={**request, "command_id": request["operation_id"]})
            journal.transition(entry["operation_key"], {"accepted"}, "render_preparing")
            live = threading.Event(); live.set()
            opener = web.CommandSubmissionOpener(protocol, protocol, request, journal, entry["operation_key"], result, live)
            wire = Request(protocol.bridge.server_url + "/api/v1/generate/video", data=json.dumps(body).encode(),
                           headers={"Idempotency-Key": request["render_key"], "Content-Length": "1"}, method="POST")
            opener.open(wire, timeout=1)
            posted = protocol.posts[0][1]
            self.assertEqual({key: value for key, value in posted.items() if key in web.PARENT_SETTINGS_FIELDS}, sparse)
            self.assertEqual(posted["image_urls"], body["image_urls"])
            self.assertEqual(posted["video_urls"], body["video_urls"])
            self.assertEqual(posted["prompt"], text)
            self.assertIsNone(wire.get_header("Content-length"))
            self.assertEqual(protocol.events[0][1]["render_payload_sha256"], web.request_fingerprint(posted))

    def test_old_server_disables_before_registration(self):
        requests = []
        def request(method, path, **kwargs):
            requests.append((method, path))
            return {"project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA, "project_ids": sorted(web.PROJECT_IDS)}}
        command = worker_fixture.command()
        bridge = SimpleNamespace(_request_json=request)
        protocol = web.BrokerProtocol(bridge, command["operation_id"], command["session_id"])
        with self.assertRaisesRegex(ValueError, "parent_settings_server_upgrade_required"):
            protocol.heartbeat([], register=True)
        self.assertEqual([method for method, _ in requests], ["GET"])

    def test_old_server_worker_receipt_is_not_ready_with_specific_reason(self):
        async def run():
            with tempfile.TemporaryDirectory() as root:
                calls = []
                def request(method, path, **kwargs):
                    calls.append((method, path))
                    return {"project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA, "project_ids": sorted(web.PROJECT_IDS)}}
                command = worker_fixture.command()
                bridge = SimpleNamespace(server_url="https://broker.example", _request_json=request)
                protocol = web.BrokerProtocol(bridge, command["operation_id"], command["session_id"])
                engine, node = worker_fixture.Engine(), worker_fixture.Generator()
                worker = web.EngineWorker(engine, web.OperationJournal(root))
                descriptor = {"target_id": command["target_id"], "ready": True}
                worker.protocols[bridge.server_url] = protocol
                worker._nodes = lambda: [node]
                worker._target = mock.AsyncMock(return_value=(protocol, descriptor, {}, worker_fixture.Agent()))
                await worker.tick()
                saved = json.loads((Path(root) / ("worker-" + worker.session_id + ".json")).read_text(encoding="utf-8"))
                self.assertIs(saved["targets"][0]["ready"], False)
                self.assertEqual(saved["error_code"], "parent_settings_server_upgrade_required")
                self.assertEqual([method for method, _ in calls], ["GET"])
                self.assertEqual(saved["active_commands"], 0)
        asyncio.run(run())

    def test_heartbeat_reply_contract_downgrade_is_fenced(self):
        command = worker_fixture.command()
        capability = {"project_routing": {"schema": web.PROJECT_ROUTING_SCHEMA, "project_ids": sorted(web.PROJECT_IDS)},
                      "parent_settings_contract": web.PARENT_SETTINGS_SCHEMA}
        reply = {**capability, "schema": web.PROTOCOL, "worker_id": command["operation_id"],
                 "session_id": command["session_id"], "registered": True, "user_id": 17}
        bridge = SimpleNamespace(_request_json=lambda method, path, **kwargs: deepcopy(capability if method == "GET" else reply))
        protocol = web.BrokerProtocol(bridge, command["operation_id"], command["session_id"])
        protocol.heartbeat([], register=True)
        self.assertTrue(protocol.parent_settings_ready)
        reply.pop("parent_settings_contract")
        with self.assertRaisesRegex(ValueError, "parent_settings_server_upgrade_required"):
            protocol.heartbeat([])
        self.assertFalse(protocol.parent_settings_ready)

    def test_unsupported_parent_stops_before_agent_or_video(self):
        async def run():
            with tempfile.TemporaryDirectory() as root:
                engine, node, agent, protocol = worker_fixture.Engine(), worker_fixture.Generator(), worker_fixture.Agent(), worker_fixture.Protocol()
                journal = web.OperationJournal(root); worker = web.EngineWorker(engine, journal)
                request = freeze_command(worker_fixture.command(), {**wire_settings(), "seed": 0})
                await worker.execute(node, agent, {"params": {}}, protocol, request)
                self.assertEqual((agent.calls, node.executions, len(protocol.posts)), (0, 0, 0))
                self.assertEqual(journal.read(journal.key(protocol.bridge.server_url, "17", request["operation_id"]))["state"], "failed")
        asyncio.run(run())

    def test_typed_agent_output_failure_is_terminal_not_uncertain(self):
        class InvalidOutput(RuntimeError):
            _hmb_web_output_contract_failed = True
        class Agent(worker_fixture.Agent):
            async def _hmb_run_web_rerender(self, *args):
                self.calls += 1
                raise InvalidOutput("private invalid model output")
        async def run():
            with tempfile.TemporaryDirectory() as root:
                engine, node, agent, protocol = worker_fixture.Engine(), worker_fixture.Generator(), Agent(), worker_fixture.Protocol()
                journal = web.OperationJournal(root); worker = web.EngineWorker(engine, journal)
                request = worker_fixture.command()
                await worker.execute(node, agent, {"params": {}}, protocol, request)
                row = journal.read(journal.key(protocol.bridge.server_url, "17", request["operation_id"]))
                self.assertEqual(row["state"], "failed")
                self.assertEqual(row["document"]["error_code"], "web_rerender_output_contract_invalid")
                await worker.execute(node, agent, {"params": {}}, protocol, request)
                self.assertEqual((agent.calls, node.executions, len(protocol.posts)), (1, 0, 0))
        asyncio.run(run())

    def test_real_generator_claim_applies_parent_without_changing_owner(self):
        async def run(root):
            node = fixture.new_node()
            before = deepcopy(node.parameter_values)
            snapshot = node._hmb_web_rerender_capture_inputs()
            async with node._hmb_web_rerender_claim(snapshot) as claim:
                node._hmb_web_rerender_bind_parent_settings(claim, wire_settings())
                await node._hmb_web_rerender_prepare_media(claim)
                self.assertEqual(claim.prepared_params["model_id"], g.SEEDANCE_2_5_MODEL_ID)
                self.assertEqual(claim.prepared_params["duration"], 4)
                self.assertEqual(claim.prepared_params["reference_images"], snapshot["params"]["reference_images"])
                self.assertEqual(node.parameter_values, before)
                with self.assertRaisesRegex(ValueError, "parent_settings_changed"):
                    node._hmb_web_rerender_bind_parent_settings(claim, {**wire_settings(), "duration_seconds": 6})
            fixture.unchanged(node)
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {"LOCALAPPDATA": root}))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_runtime_node_is_live", lambda self, **kw: True))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_manual_agent_prompt_source", lambda self: fixture.agent))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_exact_incoming_source", lambda self, *a, **kw: None))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_has_incoming_parameter_connection", lambda self, name: False))
            stack.enter_context(mock.patch.object(g.GriptapeNodes, "NodeManager", lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "flow-web"), create=True))
            asyncio.run(run(root))

    def test_owner_draft_controls_dormant_before_read_view_claim_parent_bind(self):
        async def run():
            for action in (g.DRAFT_ACTION_PREVIEW, g.DRAFT_ACTION_FINAL):
                node = fixture.new_node()
                node.parameter_values.update({"model_id": g.SEEDANCE_2_5_MODEL_ID,
                    "draft_action": action, "resolution": "480p", "output_format": "mp4",
                    "task": g.TASK_REFERENCE_TO_VIDEO, "draft_job_id": "job-" + "a" * 32,
                    g.SHOT_SELECTOR_PARAMETER: g.SHOT_ONLY_LABEL})
                before = deepcopy(node.parameter_values)
                view_params = g._HMBWebRerenderExecution.read_view(node)._get_parameters()
                self.assertEqual(view_params["draft_action"], g.DRAFT_ACTION_OFF)
                snapshot = node._hmb_web_rerender_capture_inputs()
                self.assertEqual(snapshot["params"]["draft_action"], g.DRAFT_ACTION_OFF)
                async with node._hmb_web_rerender_claim(snapshot) as claim:
                    node._hmb_web_rerender_bind_parent_settings(claim, wire_settings())
                    await node._hmb_web_rerender_prepare_media(claim)
                    self.assertEqual(claim.prepared_params["resolution"], "720p")
                    self.assertEqual(claim.prepared_params["draft_action"], g.DRAFT_ACTION_OFF)
                    self.assertEqual(node.parameter_values, before)
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {"LOCALAPPDATA": root}))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_runtime_node_is_live", lambda self, **kw: True))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_manual_agent_prompt_source", lambda self: fixture.agent))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_exact_incoming_source", lambda self, *a, **kw: None))
            stack.enter_context(mock.patch.object(g.HMBSeedanceGeneration, "_has_incoming_parameter_connection", lambda self, name: False))
            stack.enter_context(mock.patch.object(g.GriptapeNodes, "NodeManager", lambda: SimpleNamespace(get_node_parent_flow_by_name=lambda name: "flow-web"), create=True))
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
